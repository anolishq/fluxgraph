#include "exact.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <cstddef>

namespace fluxgraph::v2::detail {

BigUint::BigUint(std::uint64_t value) {
    while (value != 0) {
        limbs_.push_back(static_cast<std::uint32_t>(value & 0xFFFFFFFFu));
        value >>= 32;
    }
}

void BigUint::multiply(std::uint32_t factor) {
    std::uint64_t carry = 0;
    for (std::uint32_t &limb : limbs_) {
        // A limb and a factor are each under 2^32, so the product and a carry under 2^32 fit in 64 bits.
        const std::uint64_t product = static_cast<std::uint64_t>(limb) * factor + carry;
        limb = static_cast<std::uint32_t>(product & 0xFFFFFFFFu);
        carry = product >> 32;
    }
    if (carry != 0) {
        limbs_.push_back(static_cast<std::uint32_t>(carry));
    }
    while (!limbs_.empty() && limbs_.back() == 0) {
        limbs_.pop_back();
    }
}

void BigUint::add(std::uint32_t addend) {
    std::uint64_t carry = addend;
    for (std::uint32_t &limb : limbs_) {
        if (carry == 0) {
            return;
        }
        const std::uint64_t sum = static_cast<std::uint64_t>(limb) + carry;
        limb = static_cast<std::uint32_t>(sum & 0xFFFFFFFFu);
        carry = sum >> 32;
    }
    if (carry != 0) {
        limbs_.push_back(static_cast<std::uint32_t>(carry));
    }
}

std::uint32_t BigUint::divide(std::uint32_t divisor) {
    std::uint64_t remainder = 0;
    for (std::size_t i = limbs_.size(); i-- > 0;) {
        // The remainder is under the divisor, so under 2^32, and shifted up beside a limb it fits in 64 bits.
        const std::uint64_t part = (remainder << 32) | limbs_[i];
        limbs_[i] = static_cast<std::uint32_t>(part / divisor);
        remainder = part % divisor;
    }
    while (!limbs_.empty() && limbs_.back() == 0) {
        limbs_.pop_back();
    }
    return static_cast<std::uint32_t>(remainder);
}

BigUint BigUint::times(const BigUint &other) const {
    BigUint product;
    if (is_zero() || other.is_zero()) {
        return product;
    }
    product.limbs_.assign(limbs_.size() + other.limbs_.size(), 0);
    for (std::size_t i = 0; i < limbs_.size(); ++i) {
        std::uint64_t carry = 0;
        for (std::size_t j = 0; j < other.limbs_.size(); ++j) {
            // (2^32 - 1)^2 + 2 * (2^32 - 1) is 2^64 - 1: the product, the limb already there and the carry fit.
            const std::uint64_t sum =
                static_cast<std::uint64_t>(limbs_[i]) * other.limbs_[j] + product.limbs_[i + j] + carry;
            product.limbs_[i + j] = static_cast<std::uint32_t>(sum & 0xFFFFFFFFu);
            carry = sum >> 32;
        }
        product.limbs_[i + other.limbs_.size()] = static_cast<std::uint32_t>(carry);
    }
    while (!product.limbs_.empty() && product.limbs_.back() == 0) {
        product.limbs_.pop_back();
    }
    return product;
}

std::size_t BigUint::bits() const {
    if (limbs_.empty()) {
        return 0;
    }
    std::size_t top = 0;
    for (std::uint32_t limb = limbs_.back(); limb != 0; limb >>= 1) {
        ++top;
    }
    return (limbs_.size() - 1) * 32 + top;
}

BigUint BigUint::divided_by(const BigUint &divisor, BigUint &remainder) const {
    // Long division a bit at a time: slow, and only ever run when a graph is compiled.
    const auto less = [](const BigUint &a, const BigUint &b) {
        if (a.limbs_.size() != b.limbs_.size()) {
            return a.limbs_.size() < b.limbs_.size();
        }
        for (std::size_t i = a.limbs_.size(); i-- > 0;) {
            if (a.limbs_[i] != b.limbs_[i]) {
                return a.limbs_[i] < b.limbs_[i];
            }
        }
        return false;
    };
    BigUint quotient;
    remainder = BigUint();
    for (std::size_t bit = bits(); bit-- > 0;) {
        remainder.multiply(2);
        remainder.add((limbs_[bit / 32] >> (bit % 32)) & 1u);
        quotient.multiply(2);
        if (!less(remainder, divisor)) {
            // remainder -= divisor: it is at least the divisor, so the borrow runs out within it.
            std::uint64_t borrow = 0;
            for (std::size_t i = 0; i < remainder.limbs_.size(); ++i) {
                const std::uint64_t take = (i < divisor.limbs_.size() ? divisor.limbs_[i] : 0) + borrow;
                const std::uint64_t have = remainder.limbs_[i];
                borrow = have < take ? 1 : 0;
                remainder.limbs_[i] = static_cast<std::uint32_t>((have + (borrow << 32)) - take);
            }
            while (!remainder.limbs_.empty() && remainder.limbs_.back() == 0) {
                remainder.limbs_.pop_back();
            }
            quotient.add(1);
        }
    }
    return quotient;
}

bool BigUint::to_u64(std::uint64_t &value) const {
    if (limbs_.size() > 2) {
        return false;
    }
    value = 0;
    if (!limbs_.empty()) {
        value = limbs_[0];
    }
    if (limbs_.size() == 2) {
        value |= static_cast<std::uint64_t>(limbs_[1]) << 32;
    }
    return true;
}

std::string BigUint::decimal() const {
    if (is_zero()) {
        return "0";
    }
    BigUint rest = *this;
    std::string digits;
    while (!rest.is_zero()) {
        digits.push_back(static_cast<char>('0' + rest.divide(10)));
    }
    std::reverse(digits.begin(), digits.end());
    return digits;
}

namespace {

bool is_digit(char c) { return c >= '0' && c <= '9'; }

struct Unit {
    std::string_view name;
    std::uint32_t factor;  // nanoseconds are factor * 10^tens
    unsigned tens;
};

constexpr std::array<Unit, 6> kUnits = {{
    {"ns", 1, 0},
    {"us", 1, 3},
    {"ms", 1, 6},
    {"s", 1, 9},
    {"m", 6, 10},
    {"h", 36, 11},
}};

}  // namespace

bool parse_length(std::string_view text, Length &length) {
    std::size_t at = 0;
    BigUint digits;
    while (at < text.size() && is_digit(text[at])) {
        digits.multiply(10);
        digits.add(static_cast<std::uint32_t>(text[at] - '0'));
        ++at;
    }
    if (at == 0) {
        return false;
    }
    unsigned fraction = 0;
    if (at < text.size() && text[at] == '.') {
        ++at;
        const std::size_t first = at;
        while (at < text.size() && is_digit(text[at])) {
            digits.multiply(10);
            digits.add(static_cast<std::uint32_t>(text[at] - '0'));
            ++at;
            ++fraction;
        }
        if (at == first) {
            return false;
        }
    }
    const std::string_view unit = text.substr(at);
    for (const Unit &known : kUnits) {
        if (unit == known.name) {
            digits.multiply(known.factor);
            for (unsigned i = 0; i < known.tens; ++i) {
                digits.multiply(10);
            }
            length.scaled = std::move(digits);
            length.fraction_digits = fraction;
            return true;
        }
    }
    return false;
}

WholeLength whole_nanoseconds(const Length &length, Time &nanoseconds) {
    BigUint whole = length.scaled;
    for (unsigned i = 0; i < length.fraction_digits; ++i) {
        if (whole.divide(10) != 0) {
            return WholeLength::not_whole;
        }
    }
    std::uint64_t value = 0;
    if (!whole.to_u64(value) || value > kTimeMaxUnsigned) {
        return WholeLength::too_large;
    }
    nanoseconds = static_cast<Time>(value);
    return WholeLength::ok;
}

bool is_zero(const Length &length) { return length.scaled.is_zero(); }

namespace {

// 10^digits, to put a length's fraction on the other side of a ratio.
BigUint power_of_ten(unsigned digits) {
    BigUint power(1);
    for (unsigned i = 0; i < digits; ++i) {
        power.multiply(10);
    }
    return power;
}

}  // namespace

double period_over(Time period, const Length &length) {
    // period / (scaled / 10^f) is (period * 10^f) / scaled. The quotient is taken with enough bits below the
    // point that its top 64 are all of the quotient that a double can show, and what is dropped is kept as one
    // "something was there" bit, so the rounding to 53 bits is the rounding of the true ratio.
    const BigUint top = BigUint(static_cast<std::uint64_t>(period)).times(power_of_ten(length.fraction_digits));
    const std::size_t shift = 64 + length.scaled.bits();
    BigUint scaled_up = top;
    for (std::size_t i = 0; i < shift; ++i) {
        scaled_up.multiply(2);
    }
    BigUint remainder;
    BigUint quotient = scaled_up.divided_by(length.scaled, remainder);  // at least 2^64, since top is at least 1
    bool sticky = !remainder.is_zero();
    std::size_t dropped = 0;
    while (quotient.bits() > 64) {
        sticky = quotient.divide(2) != 0 || sticky;
        ++dropped;
    }
    std::uint64_t leading = 0;
    quotient.to_u64(leading);  // exactly 64 bits: the top one is set
    std::uint64_t mantissa = leading >> 11;
    const bool half = ((leading >> 10) & 1u) != 0;
    sticky = sticky || (leading & 0x3FFu) != 0;
    if (half && (sticky || (mantissa & 1u) != 0)) {
        ++mantissa;  // to nearest, ties to even; at most 2^53, which a double holds
    }
    // The exponent is small beside an int: the lengths are a few hundred bits at the very most.
    const int exponent = 11 + static_cast<int>(dropped) - static_cast<int>(shift);
    return std::ldexp(static_cast<double>(mantissa), exponent);
}

bool periods_rounded_up(const Length &length, std::uint32_t times, Time period, std::uint64_t &ticks) {
    BigUint top = length.scaled;
    top.multiply(times);
    const BigUint bottom = BigUint(static_cast<std::uint64_t>(period)).times(power_of_ten(length.fraction_digits));
    BigUint remainder;
    BigUint quotient = top.divided_by(bottom, remainder);
    if (!remainder.is_zero()) {
        quotient.add(1);
    }
    return quotient.to_u64(ticks);
}

std::uint64_t ceil_of_fraction(double fraction, std::uint64_t count) {
    // Shortest scientific form: one digit, perhaps a point and more digits, then e, a sign and an exponent.
    std::array<char, 64> buffer{};
    const std::to_chars_result written =
        std::to_chars(buffer.data(), buffer.data() + buffer.size(), fraction, std::chars_format::scientific);
    const std::string_view text(buffer.data(), static_cast<std::size_t>(written.ptr - buffer.data()));
    BigUint digits;
    int exponent = 0;
    std::size_t at = 0;
    bool after_point = false;
    for (; at < text.size() && text[at] != 'e'; ++at) {
        if (text[at] == '.') {
            after_point = true;
            continue;
        }
        digits.multiply(10);
        digits.add(static_cast<std::uint32_t>(text[at] - '0'));
        if (after_point) {
            --exponent;
        }
    }
    int written_exponent = 0;
    if (at < text.size()) {
        const char *first = text.data() + at + 1;
        if (first < text.data() + text.size() && *first == '+') {
            ++first;
        }
        std::from_chars(first, text.data() + text.size(), written_exponent);
    }
    exponent += written_exponent;  // the fraction is digits * 10^exponent, exactly as written

    BigUint product = digits.times(BigUint(count));
    for (; exponent > 0; --exponent) {
        product.multiply(10);
    }
    bool remainder = false;
    for (; exponent < 0 && !product.is_zero(); ++exponent) {
        remainder = product.divide(10) != 0 || remainder;
    }
    if (remainder) {
        product.add(1);
    }
    std::uint64_t result = 0;
    if (!product.to_u64(result) || result > count) {
        return count;  // not reached for a fraction of at most one
    }
    return result;
}

}  // namespace fluxgraph::v2::detail

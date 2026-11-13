#include "exact.hpp"

#include <algorithm>
#include <array>
#include <charconv>
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

double nanoseconds_as_double(const Length &length) {
    // The exact decimal, read by the library's correctly rounded conversion.
    std::string text = length.scaled.decimal();
    text += "e-";
    text += std::to_string(length.fraction_digits);
    double value = 0.0;
    std::from_chars(text.data(), text.data() + text.size(), value);
    return value;
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

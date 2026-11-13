#pragma once

// Arithmetic that has to be exact: times, which are 64 bits wide and must not wrap (rules 6.2 and 6.11), and the
// lengths and fractions a graph gives, which are worked from their decimal text (rule 6.3). Nothing here uses a
// type wider than 64 bits: the wide cases go through BigUint.

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

#include "fluxgraph/v2/value.hpp"

namespace fluxgraph::v2::detail {

inline constexpr Time kTimeMax = INT64_MAX;
inline constexpr std::uint64_t kTimeMaxUnsigned = static_cast<std::uint64_t>(INT64_MAX);

/// How far `later` is after `earlier`, for `later >= earlier`: the true difference, which always fits unsigned
/// (at most 2^64 - 1) though it may not fit signed. Unsigned subtraction of the two's complement patterns is
/// that difference exactly.
constexpr std::uint64_t span_between(Time earlier, Time later) {
    return static_cast<std::uint64_t>(later) - static_cast<std::uint64_t>(earlier);
}

/// Whether `a` is after `b` by more than `limit`, for `limit >= 0`, however far apart the two are.
constexpr bool after_by_more_than(Time a, Time b, Time limit) {
    return a > b && span_between(b, a) > static_cast<std::uint64_t>(limit);
}

/// `base + offset`, for an offset that is not negative. False where the sum is past the largest time.
constexpr bool add_span(Time base, std::uint64_t offset, Time &sum) {
    if (offset > span_between(base, kTimeMax)) {
        return false;
    }
    // The sum fits signed, so adding the patterns unsigned and reading the result signed gives it exactly.
    sum = static_cast<Time>(static_cast<std::uint64_t>(base) + offset);
    return true;
}

/// A whole number of any size, not negative.
class BigUint {
public:
    BigUint() = default;
    explicit BigUint(std::uint64_t value);

    bool is_zero() const { return limbs_.empty(); }
    void multiply(std::uint32_t factor);
    void add(std::uint32_t addend);
    /// Divides in place and returns the remainder. `divisor` is not zero.
    std::uint32_t divide(std::uint32_t divisor);
    BigUint times(const BigUint &other) const;
    /// False where the value does not fit.
    bool to_u64(std::uint64_t &value) const;
    std::string decimal() const;

private:
    std::vector<std::uint32_t> limbs_;  // least significant first, with no zero at the top
};

/// A length of time as a graph writes it (rule 9.3), kept exactly: `scaled / 10^fraction_digits` nanoseconds.
struct Length {
    BigUint scaled;
    unsigned fraction_digits = 0;
};

/// False where `text` is not a number and a unit with nothing between them.
bool parse_length(std::string_view text, Length &length);

enum class WholeLength { ok, not_whole, too_large };
/// The length in whole nanoseconds, where it is one and fits in 64 bits, signed.
WholeLength whole_nanoseconds(const Length &length, Time &nanoseconds);
/// The length in nanoseconds as the nearest double, for a setting that only scales a value (rule 6.3).
double nanoseconds_as_double(const Length &length);

/// `fraction * count` rounded up to a whole number, worked exactly from the shortest decimal that reads back as
/// `fraction` (rule 6.3). For a finite fraction more than zero and at most one, so the result is at most `count`.
std::uint64_t ceil_of_fraction(double fraction, std::uint64_t count);

}  // namespace fluxgraph::v2::detail

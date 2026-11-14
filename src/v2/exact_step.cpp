#include "exact_step.hpp"

#include <cmath>
#include <cstdint>

namespace fluxgraph::v2::detail {

namespace {

// A number kept as an unevaluated sum of two doubles, the second less than half a unit in the last place of the
// first: about 32 significant digits. The sums and products below are the classical error-free ones (Dekker,
// Knuth); each is exact but for a last rounding at about 10^-32 of the result.
struct Wide {
    double hi = 0.0;
    double lo = 0.0;
};

Wide sum_of(double a, double b) {  // exact, for any a and b
    const double s = a + b;
    const double bb = s - a;
    return Wide{s, (a - (s - bb)) + (b - bb)};
}

Wide quick_sum_of(double a, double b) {  // exact where a is not the smaller in size
    const double s = a + b;
    return Wide{s, b - (s - a)};
}

Wide product_of(double a, double b) {  // exact
    const double p = a * b;
    return Wide{p, std::fma(a, b, -p)};
}

Wide add(Wide x, Wide y) {
    Wide s = sum_of(x.hi, y.hi);
    const Wide t = sum_of(x.lo, y.lo);
    s.lo += t.hi;
    s = quick_sum_of(s.hi, s.lo);
    s.lo += t.lo;
    return quick_sum_of(s.hi, s.lo);
}

Wide multiply(Wide x, Wide y) {
    Wide p = product_of(x.hi, y.hi);
    p.lo += x.hi * y.lo + x.lo * y.hi;
    return quick_sum_of(p.hi, p.lo);
}

Wide negative(Wide x) { return Wide{-x.hi, -x.lo}; }

Wide divide(Wide x, double d) {
    // Long division, two digits and a correction: each quotient digit is a double.
    const double q1 = x.hi / d;
    Wide rest = add(x, negative(product_of(q1, d)));
    const double q2 = rest.hi / d;
    rest = add(rest, negative(product_of(q2, d)));
    const double q3 = rest.hi / d;
    const Wide q = quick_sum_of(q1, q2);
    return add(q, Wide{q3, 0.0});
}

Wide halved(Wide x, int times) { return Wide{std::ldexp(x.hi, -times), std::ldexp(x.lo, -times)}; }  // exact

double rounded(Wide x) { return x.hi + x.lo; }

// The period in seconds. The period is split so that each half is exact in a double.
Wide seconds(Time period) {
    const std::uint64_t whole = static_cast<std::uint64_t>(period);  // more than zero
    const Wide nanoseconds =
        sum_of(std::ldexp(static_cast<double>(whole >> 32), 32), static_cast<double>(whole & 0xFFFFFFFFu));
    return divide(nanoseconds, 1e9);
}

using Matrix = std::vector<Wide>;  // by rows

// c = a * b, each n by n.
void multiply(const Matrix &a, const Matrix &b, std::size_t n, Matrix &c) {
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t j = 0; j < n; ++j) {
            Wide sum;
            for (std::size_t k = 0; k < n; ++k) {
                sum = add(sum, multiply(a[i * n + k], b[k * n + j]));
            }
            c[i * n + j] = sum;
        }
    }
}

}  // namespace

double stiffness(const std::vector<double> &a, std::size_t n, Time period) {
    double largest = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        double row = 0.0;
        for (std::size_t j = 0; j < n; ++j) {
            row += std::fabs(a[i * n + j]);
        }
        largest = row > largest || std::isnan(row) ? row : largest;
    }
    return largest * (static_cast<double>(period) / 1e9);
}

void exact_step(const std::vector<double> &a, std::size_t n, const std::vector<double> &b, std::size_t m, Time period,
                std::vector<double> &ad, std::vector<double> &bd) {
    // Scaling and squaring. With X = A * period / 2^s small, two series are summed:
    //   E = exp(X)                      = I + X + X^2/2! + ...
    //   P = (exp(X) - I) / X, in effect = I + X/2! + X^2/3! + ...
    // P times the length of the step is the integral of exp(A t) over the step. Doubling the step s times:
    //   P <- (P + E P) / 2,   E <- E E
    // since the integral over two steps is the integral over one, and that again carried forward by E.
    const Wide length = seconds(period);
    int halvings = 0;
    for (double size = stiffness(a, n, period); size > 0.5 && halvings < 1100; size /= 2.0) {
        ++halvings;  // a size that is not a number, or is past any double, stops at once or at the cap
    }
    Matrix x(n * n);
    for (std::size_t i = 0; i < n * n; ++i) {
        x[i] = halved(multiply(Wide{a[i], 0.0}, length), halvings);
    }
    Matrix e(n * n);
    Matrix p(n * n);
    Matrix term(n * n);
    Matrix next(n * n);
    for (std::size_t i = 0; i < n; ++i) {
        e[i * n + i] = p[i * n + i] = term[i * n + i] = Wide{1.0, 0.0};
    }
    // The size of X is at most a half, so term k is under 0.5^k / k!: by k = 30 it is far below the 32nd digit.
    for (int k = 1; k <= 30; ++k) {
        multiply(term, x, n, next);
        for (std::size_t i = 0; i < n * n; ++i) {
            term[i] = divide(next[i], static_cast<double>(k));  // X^k / k!
            e[i] = add(e[i], term[i]);
            p[i] = add(p[i], divide(term[i], static_cast<double>(k + 1)));
        }
    }
    for (int doubling = 0; doubling < halvings; ++doubling) {
        multiply(e, p, n, next);
        for (std::size_t i = 0; i < n * n; ++i) {
            p[i] = halved(add(p[i], next[i]), 1);
        }
        multiply(e, e, n, next);
        e.swap(next);
    }
    ad.assign(n * n, 0.0);
    for (std::size_t i = 0; i < n * n; ++i) {
        ad[i] = rounded(e[i]);
    }
    // Bd = (period * P) * B: the integral first, and B only then.
    bd.assign(n * m, 0.0);
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t k = 0; k < m; ++k) {
            Wide sum;
            for (std::size_t j = 0; j < n; ++j) {
                sum = add(sum, multiply(multiply(p[i * n + j], length), Wide{b[j * m + k], 0.0}));
            }
            bd[i * m + k] = rounded(sum);
        }
    }
}

}  // namespace fluxgraph::v2::detail

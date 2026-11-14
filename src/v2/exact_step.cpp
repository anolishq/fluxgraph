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

namespace {

// E = exp(A * period), P = the integral of exp(A t) over the period, over the period, and, where `q` is given,
// N = the integral of exp(A t) Q exp(A' t) over the period, with Q having `q` on its diagonal.
//
// Scaling and squaring. With X = A * period / 2^s small, series are summed:
//   E = exp(X)                      = I + X + X^2/2! + ...
//   P = (exp(X) - I) / X, in effect = I + X/2! + X^2/3! + ...
//   N / (the small step)            = Q + L1/2! + L2/3! + ...,  with L0 = Q and L(k+1) = X Lk + Lk X'
// the last because the k-th derivative of exp(A t) Q exp(A' t) at zero is Lk in units of the small step.
// Doubling the step s times:
//   N <- N + E N E',   P <- (P + E P) / 2,   E <- E E
// since what is added over two steps is what is added over one, and that again carried forward by E.
struct Worked {
    Wide length;  // the period, in seconds
    Matrix e;
    Matrix p;
    Matrix noise;
};

Worked work(const std::vector<double> &a, std::size_t n, Time period, const std::vector<double> *q) {
    Worked w;
    w.length = seconds(period);
    int halvings = 0;
    for (double size = stiffness(a, n, period); size > 0.5 && halvings < 1100; size /= 2.0) {
        ++halvings;  // a size that is not a number, or is past any double, stops at once or at the cap
    }
    Matrix x(n * n);
    for (std::size_t i = 0; i < n * n; ++i) {
        x[i] = halved(multiply(Wide{a[i], 0.0}, w.length), halvings);
    }
    w.e.assign(n * n, Wide{});
    w.p.assign(n * n, Wide{});
    Matrix term(n * n);
    Matrix next(n * n);
    Matrix other(n * n);
    Matrix layer(q != nullptr ? n * n : 0);
    for (std::size_t i = 0; i < n; ++i) {
        w.e[i * n + i] = w.p[i * n + i] = term[i * n + i] = Wide{1.0, 0.0};
        if (q != nullptr) {
            layer[i * n + i] = Wide{(*q)[i], 0.0};
        }
    }
    w.noise = layer;
    // The size of X is at most a half, so term k is under 0.5^k / k!, and layer k under 1 / (k + 1)! of Q: by
    // k = 30 both are far below the 32nd digit.
    for (int k = 1; k <= 30; ++k) {
        multiply(term, x, n, next);
        for (std::size_t i = 0; i < n * n; ++i) {
            term[i] = divide(next[i], static_cast<double>(k));  // X^k / k!
            w.e[i] = add(w.e[i], term[i]);
            w.p[i] = add(w.p[i], divide(term[i], static_cast<double>(k + 1)));
        }
        if (q != nullptr) {
            multiply(x, layer, n, next);  // X Lk
            for (std::size_t i = 0; i < n; ++i) {
                for (std::size_t j = 0; j < n; ++j) {
                    Wide sum;  // Lk X', whose entry (i, j) is the sum over c of Lk(i, c) X(j, c)
                    for (std::size_t c = 0; c < n; ++c) {
                        sum = add(sum, multiply(layer[i * n + c], x[j * n + c]));
                    }
                    other[i * n + j] = divide(add(next[i * n + j], sum), static_cast<double>(k));  // Lk / k!
                }
            }
            layer = other;
            for (std::size_t i = 0; i < n * n; ++i) {
                w.noise[i] = add(w.noise[i], divide(layer[i], static_cast<double>(k + 1)));
            }
        }
    }
    if (q != nullptr) {
        const Wide step = halved(w.length, halvings);
        for (Wide &entry : w.noise) {
            entry = multiply(entry, step);
        }
    }
    for (int doubling = 0; doubling < halvings; ++doubling) {
        if (q != nullptr) {
            multiply(w.e, w.noise, n, next);  // E N
            for (std::size_t i = 0; i < n; ++i) {
                for (std::size_t j = 0; j < n; ++j) {
                    Wide sum;  // (E N) E'
                    for (std::size_t c = 0; c < n; ++c) {
                        sum = add(sum, multiply(next[i * n + c], w.e[j * n + c]));
                    }
                    other[i * n + j] = add(w.noise[i * n + j], sum);
                }
            }
            w.noise = other;
        }
        multiply(w.e, w.p, n, next);
        for (std::size_t i = 0; i < n * n; ++i) {
            w.p[i] = halved(add(w.p[i], next[i]), 1);
        }
        multiply(w.e, w.e, n, next);
        w.e.swap(next);
    }
    return w;
}

}  // namespace

void exact_step(const std::vector<double> &a, std::size_t n, const std::vector<double> &b, std::size_t m, Time period,
                std::vector<double> &ad, std::vector<double> &bd) {
    const Worked w = work(a, n, period, nullptr);
    ad.assign(n * n, 0.0);
    for (std::size_t i = 0; i < n * n; ++i) {
        ad[i] = rounded(w.e[i]);
    }
    // Bd = (period * P) * B: the integral first, and B only then.
    bd.assign(n * m, 0.0);
    for (std::size_t i = 0; i < n; ++i) {
        for (std::size_t k = 0; k < m; ++k) {
            Wide sum;
            for (std::size_t j = 0; j < n; ++j) {
                sum = add(sum, multiply(multiply(w.p[i * n + j], w.length), Wide{b[j * m + k], 0.0}));
            }
            bd[i * m + k] = rounded(sum);
        }
    }
}

void exact_noise(const std::vector<double> &a, std::size_t n, const std::vector<double> &q, Time period,
                 std::vector<double> &noise) {
    const Worked w = work(a, n, period, &q);
    noise.assign(n * n, 0.0);
    for (std::size_t i = 0; i < n * n; ++i) {
        noise[i] = rounded(w.noise[i]);
    }
}

}  // namespace fluxgraph::v2::detail

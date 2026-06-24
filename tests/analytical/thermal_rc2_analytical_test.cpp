#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <stdexcept>

#include "fluxgraph/model/thermal_rc2.hpp"

using namespace fluxgraph;

namespace {

struct Vec2 {
    double a = 0.0;
    double b = 0.0;
};

struct Mat2 {
    double a11 = 0.0;
    double a12 = 0.0;
    double a21 = 0.0;
    double a22 = 0.0;
};

Mat2 identity() { return Mat2{1.0, 0.0, 0.0, 1.0}; }

Mat2 add(const Mat2 &lhs, const Mat2 &rhs) {
    return Mat2{lhs.a11 + rhs.a11, lhs.a12 + rhs.a12, lhs.a21 + rhs.a21, lhs.a22 + rhs.a22};
}

Mat2 sub(const Mat2 &lhs, const Mat2 &rhs) {
    return Mat2{lhs.a11 - rhs.a11, lhs.a12 - rhs.a12, lhs.a21 - rhs.a21, lhs.a22 - rhs.a22};
}

Mat2 mul(const Mat2 &m, double s) { return Mat2{m.a11 * s, m.a12 * s, m.a21 * s, m.a22 * s}; }

Vec2 mul(const Mat2 &m, const Vec2 &v) { return Vec2{m.a11 * v.a + m.a12 * v.b, m.a21 * v.a + m.a22 * v.b}; }

Mat2 inverse(const Mat2 &m) {
    const double det = m.a11 * m.a22 - m.a12 * m.a21;
    if (det == 0.0) {
        throw std::runtime_error("Singular matrix");
    }
    const double inv_det = 1.0 / det;
    return Mat2{m.a22 * inv_det, -m.a12 * inv_det, -m.a21 * inv_det, m.a11 * inv_det};
}

Mat2 expm_2x2(const Mat2 &A, double t) {
    // For 2x2 matrices:
    // exp(A t) = exp(m t) * (cosh(d t) I + (sinh(d t)/d) * (A - m I))
    // where m = trace(A)/2 and d = sqrt(m^2 - det(A)).
    const double trace = A.a11 + A.a22;
    const double det = A.a11 * A.a22 - A.a12 * A.a21;
    const double m = 0.5 * trace;
    const double d2 = std::max(0.0, m * m - det);
    const double d = std::sqrt(d2);
    const double exp_mt = std::exp(m * t);

    Mat2 I = identity();
    Mat2 B = sub(A, mul(I, m));

    const double dt = d * t;
    const double cosh_dt = std::cosh(dt);
    const double sinh_dt = std::sinh(dt);

    double scale = 0.0;
    if (d == 0.0) {
        // lim_{d->0} sinh(d t)/d = t
        scale = t;
    } else {
        scale = sinh_dt / d;
    }

    Mat2 term = add(mul(I, cosh_dt), mul(B, scale));
    return mul(term, exp_mt);
}

Vec2 exact_solution(const Mat2 &A, const Vec2 &c, const Vec2 &x0, double t) {
    const Mat2 expA = expm_2x2(A, t);
    const Mat2 invA = inverse(A);
    const Mat2 exp_minus_I = sub(expA, identity());

    const Vec2 term1 = mul(expA, x0);
    const Vec2 term2 = mul(invA, mul(exp_minus_I, c));
    return Vec2{term1.a + term2.a, term1.b + term2.b};
}

}  // namespace

TEST(ThermalRc2Analytical, MatchesClosedFormForConstantInputs) {
    SignalNamespace ns;
    SignalStore store;

    constexpr double Ca = 1000.0;
    constexpr double Cb = 2000.0;
    constexpr double ha = 10.0;
    constexpr double hb = 8.0;
    constexpr double k = 6.0;
    constexpr double Tamb = 20.0;
    constexpr double power = 50.0;
    constexpr double Ta0 = 30.0;
    constexpr double Tb0 = 10.0;

    ThermalRc2Model model("ref", Ca, Cb, ha, hb, k, Ta0, Tb0, "a.temp", "b.temp", "heater.power", "ambient.temp", ns,
                          ThermalIntegrationMethod::Rk4);

    const auto temp_a_id = ns.resolve("a.temp");
    const auto temp_b_id = ns.resolve("b.temp");
    const auto power_id = ns.resolve("heater.power");
    const auto ambient_id = ns.resolve("ambient.temp");

    store.write(power_id, power, "W");
    store.write(ambient_id, Tamb, "degC");

    const Mat2 A{-(ha + k) / Ca, k / Ca, k / Cb, -(hb + k) / Cb};
    const Vec2 c{(power + ha * Tamb) / Ca, (hb * Tamb) / Cb};
    const Vec2 x0{Ta0, Tb0};

    constexpr double dt = 0.05;
    constexpr int steps = 200;  // 10 seconds
    double t = 0.0;

    for (int i = 0; i < steps; ++i) {
        model.tick(dt, store);
        t += dt;

        const Vec2 exact = exact_solution(A, c, x0, t);
        EXPECT_NEAR(store.read_value(temp_a_id), exact.a, 0.05);
        EXPECT_NEAR(store.read_value(temp_b_id), exact.b, 0.05);
    }
}

#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <stdexcept>

#include "fluxgraph/model/second_order_process.hpp"

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
    // exp(A t) = exp(m t) * (cosh(d t) I + (sinh(d t)/d) * (A - m I))
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

    const double scale = (d == 0.0) ? t : (sinh_dt / d);
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

TEST(SecondOrderProcessAnalytical, MatchesClosedFormForConstantInput) {
    SignalNamespace ns;
    SignalStore store;

    constexpr double gain = 2.0;
    constexpr double zeta = 2.0;
    constexpr double omega = 3.0;
    constexpr double y0 = 1.0;
    constexpr double ydot0 = -0.5;
    constexpr double u = 1.5;

    SecondOrderProcessModel model("ref", gain, zeta, omega, y0, ydot0, "y", "u", ns, IntegrationMethod::Rk4);

    const auto y_id = ns.resolve("y");
    const auto u_id = ns.resolve("u");
    store.write(u_id, u, "dimensionless");

    const Mat2 A{0.0, 1.0, -omega * omega, -2.0 * zeta * omega};
    const Vec2 c{0.0, omega * omega * gain * u};
    const Vec2 x0{y0, ydot0};

    constexpr double dt = 0.01;
    constexpr int steps = 800;
    double t = 0.0;

    for (int i = 0; i < steps; ++i) {
        model.tick(dt, store);
        t += dt;
        const Vec2 exact = exact_solution(A, c, x0, t);
        EXPECT_NEAR(store.read_value(y_id), exact.a, 1e-3);
    }
}

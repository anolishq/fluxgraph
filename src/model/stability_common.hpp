#pragma once

#include <cmath>
#include <complex>
#include <limits>

#include "fluxgraph/model/integration.hpp"

namespace fluxgraph::detail {

inline std::complex<double> stability_function(IntegrationMethod method, const std::complex<double> z) {
    if (method == IntegrationMethod::ForwardEuler) {
        return std::complex<double>(1.0, 0.0) + z;
    }

    // Classic RK4 stability function: R(z) = sum_{k=0..4} z^k/k!
    const std::complex<double> z2 = z * z;
    const std::complex<double> z3 = z2 * z;
    const std::complex<double> z4 = z2 * z2;
    return std::complex<double>(1.0, 0.0) + z + z2 / 2.0 + z3 / 6.0 + z4 / 24.0;
}

inline bool is_stable_step(IntegrationMethod method, const std::complex<double> lambda, double dt) {
    const std::complex<double> z = lambda * dt;
    const std::complex<double> r = stability_function(method, z);
    // Numerical tolerance: avoids treating boundary points as unstable due to
    // floating error (notably relevant for RK methods on the stability boundary).
    return std::abs(r) <= 1.0 + 1e-12;
}

inline double forward_euler_stability_limit(const std::complex<double> lambda) {
    // Forward Euler is stable iff |1 + lambda * dt| <= 1.
    // For lambda = a + i b and dt >= 0:
    //   (1 + a dt)^2 + (b dt)^2 <= 1
    //   => 2 a dt + (a^2 + b^2) dt^2 <= 0
    //   => dt <= -2a / (a^2 + b^2) for a < 0, else dt <= 0.
    if (lambda == std::complex<double>(0.0, 0.0)) {
        return std::numeric_limits<double>::infinity();
    }

    const double a = lambda.real();
    if (!(a < 0.0)) {
        return 0.0;
    }

    const double denom = std::norm(lambda);
    if (!(denom > 0.0)) {
        return std::numeric_limits<double>::infinity();
    }

    return (-2.0 * a) / denom;
}

inline double ray_stability_limit(IntegrationMethod method, const std::complex<double> lambda) {
    if (lambda == std::complex<double>(0.0, 0.0)) {
        return std::numeric_limits<double>::infinity();
    }

    if (lambda.real() > 0.0) {
        return 0.0;
    }

    double dt_lo = 0.0;
    double dt_hi = 1.0 / std::abs(lambda);

    // Ensure dt_hi is unstable; along a ray, stable dt values form [0, dt_max].
    for (int i = 0; i < 80; ++i) {
        if (!is_stable_step(method, lambda, dt_hi)) {
            break;
        }
        dt_hi *= 2.0;
    }

    if (is_stable_step(method, lambda, dt_hi)) {
        return std::numeric_limits<double>::infinity();
    }

    for (int iter = 0; iter < 80; ++iter) {
        const double dt_mid = 0.5 * (dt_lo + dt_hi);
        if (is_stable_step(method, lambda, dt_mid)) {
            dt_lo = dt_mid;
        } else {
            dt_hi = dt_mid;
        }
    }

    return dt_lo;
}

}  // namespace fluxgraph::detail

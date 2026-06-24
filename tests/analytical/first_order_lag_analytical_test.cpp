#include <gtest/gtest.h>

#include <cmath>

#include "fluxgraph/transform/first_order_lag.hpp"

using namespace fluxgraph;

TEST(FirstOrderLagAnalytical, StepResponse) {
    // System: dy/dt = (u - y) / tau
    // Step input: u(t) = 1 for t > 0, initial y(0) = 0
    // Analytical solution: y(t) = 1 - exp(-t/tau)

    FirstOrderLagTransform lag(1.0);  // tau = 1.0 second
    double dt = 0.01;                 // 10ms timestep
    double t = 0.0;

    lag.apply(0.0, 0.0);  // Initialize to 0

    for (int i = 0; i < 500; ++i) {  // Simulate 5 seconds (5*tau)
        t += dt;
        double y_numerical = lag.apply(1.0, dt);
        double y_analytical = 1.0 - std::exp(-t);

        EXPECT_NEAR(y_numerical, y_analytical, 1e-3)
            << "t=" << t << ", numerical=" << y_numerical << ", analytical=" << y_analytical;
    }
}

TEST(FirstOrderLagAnalytical, MultipleTimeConstants) {
    // Test with different time constants
    std::vector<double> tau_values = {0.1, 0.5, 1.0, 2.0, 5.0};

    for (double tau_s : tau_values) {
        FirstOrderLagTransform lag(tau_s);
        double dt = tau_s / 100.0;  // 100 steps per time constant
        double t = 0.0;

        lag.apply(0.0, 0.0);

        for (int i = 0; i < 500; ++i) {
            t += dt;
            double y_numerical = lag.apply(1.0, dt);
            double y_analytical = 1.0 - std::exp(-t / tau_s);

            EXPECT_NEAR(y_numerical, y_analytical, 1e-3) << "tau=" << tau_s << ", t=" << t;
        }
    }
}

TEST(FirstOrderLagAnalytical, ConvergenceRate) {
    // After tau: 63.2% of final value
    // After 3*tau: 95% of final value
    // After 5*tau: 99.3% of final value

    FirstOrderLagTransform lag(1.0);
    double dt = 0.01;

    lag.apply(0.0, 0.0);

    // Simulate to 1*tau
    for (int i = 0; i < 100; ++i) {
        lag.apply(1.0, dt);
    }
    double y_1tau = lag.apply(1.0, dt);
    EXPECT_NEAR(y_1tau, 0.632, 0.01);  // 63.2%

    // Continue to 3*tau
    for (int i = 0; i < 200; ++i) {
        lag.apply(1.0, dt);
    }
    double y_3tau = lag.apply(1.0, dt);
    EXPECT_NEAR(y_3tau, 0.95, 0.01);  // 95%

    // Continue to 5*tau
    for (int i = 0; i < 200; ++i) {
        lag.apply(1.0, dt);
    }
    double y_5tau = lag.apply(1.0, dt);
    EXPECT_NEAR(y_5tau, 0.993, 0.01);  // 99.3%
}

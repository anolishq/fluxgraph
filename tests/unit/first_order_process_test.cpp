#include "fluxgraph/model/first_order_process.hpp"

#include <gtest/gtest.h>

#include <cmath>
#include <limits>

using namespace fluxgraph;

TEST(FirstOrderProcessTest, ConstructorRejectsInvalidParams) {
    SignalNamespace ns;
    EXPECT_THROW(FirstOrderProcessModel("bad", 1.0, 0.0, 0.0, "y", "u", ns), std::invalid_argument);
    EXPECT_THROW(FirstOrderProcessModel("bad", std::numeric_limits<double>::infinity(), 1.0, 0.0, "y", "u", ns),
                 std::invalid_argument);
    EXPECT_THROW(FirstOrderProcessModel("bad", 1.0, 1.0, std::numeric_limits<double>::quiet_NaN(), "y", "u", ns),
                 std::invalid_argument);
}

TEST(FirstOrderProcessTest, StepResponseApproachesGain) {
    SignalNamespace ns;
    SignalStore store;

    FirstOrderProcessModel model("pt1", 2.0, 1.0, 0.0, "y", "u", ns, IntegrationMethod::Rk4);

    const auto y_id = ns.resolve("y");
    const auto u_id = ns.resolve("u");
    constexpr double u = 3.0;
    store.write(u_id, u, "dimensionless");

    constexpr double dt = 0.01;
    constexpr int steps = 500;
    for (int i = 0; i < steps; ++i) {
        model.tick(dt, store);
    }

    const double y = store.read_value(y_id);
    // Closed-form solution for dy/dt = (gain*u - y)/tau with constant input.
    constexpr double gain = 2.0;
    constexpr double tau_s = 1.0;
    constexpr double y0 = 0.0;
    const double t = static_cast<double>(steps) * dt;
    const double y_expected = gain * u + (y0 - gain * u) * std::exp(-t / tau_s);
    EXPECT_NEAR(y, y_expected, 1e-9);
    EXPECT_TRUE(store.is_physics_driven(y_id));
}

TEST(FirstOrderProcessTest, ResetRestoresInitialState) {
    SignalNamespace ns;
    SignalStore store;

    FirstOrderProcessModel model("pt1", 1.0, 1.0, 5.0, "y", "u", ns, IntegrationMethod::ForwardEuler);

    const auto y_id = ns.resolve("y");
    const auto u_id = ns.resolve("u");

    store.write(u_id, 10.0, "dimensionless");
    model.tick(0.1, store);
    EXPECT_NE(store.read_value(y_id), 5.0);

    model.reset();
    model.tick(0.0, store);
    EXPECT_NEAR(store.read_value(y_id), 5.0, 1e-12);
}

TEST(FirstOrderProcessTest, StabilityLimitMatchesExpected) {
    SignalNamespace ns;

    constexpr double tau_s = 3.0;
    FirstOrderProcessModel euler("euler", 1.0, tau_s, 0.0, "y", "u", ns, IntegrationMethod::ForwardEuler);
    FirstOrderProcessModel rk4("rk4", 1.0, tau_s, 0.0, "y2", "u2", ns, IntegrationMethod::Rk4);

    EXPECT_NEAR(euler.compute_stability_limit(), 2.0 * tau_s, 1e-12);
    EXPECT_NEAR(rk4.compute_stability_limit(), kRk4NegativeRealAxisStabilityLimit * tau_s, 1e-12);
}

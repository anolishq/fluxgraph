#include "fluxgraph/model/second_order_process.hpp"

#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <limits>

using namespace fluxgraph;

namespace {

double expected_overdamped_limit(double zeta, double omega, double limit) {
    const double trace = -2.0 * zeta * omega;
    const double disc = std::max(0.0, trace * trace - 4.0 * omega * omega);
    const double sqrt_disc = std::sqrt(disc);
    const double lambda1 = 0.5 * (trace + sqrt_disc);
    const double lambda2 = 0.5 * (trace - sqrt_disc);
    const double most_negative = std::min(lambda1, lambda2);
    return limit / std::abs(most_negative);
}

}  // namespace

TEST(SecondOrderProcessTest, ConstructorRejectsInvalidParams) {
    SignalNamespace ns;
    EXPECT_THROW(SecondOrderProcessModel("bad", 1.0, 0.0, 0.0, 0.0, 0.0, "y", "u", ns), std::invalid_argument);
    EXPECT_THROW(
        SecondOrderProcessModel("bad", std::numeric_limits<double>::infinity(), 0.1, 1.0, 0.0, 0.0, "y", "u", ns),
        std::invalid_argument);
    EXPECT_THROW(SecondOrderProcessModel("bad", 1.0, -1.0, 1.0, 0.0, 0.0, "y", "u", ns), std::invalid_argument);
}

TEST(SecondOrderProcessTest, StepResponseMovesTowardGain) {
    SignalNamespace ns;
    SignalStore store;

    SecondOrderProcessModel model("pt2", 2.0, 0.7, 4.0, 0.0, 0.0, "y", "u", ns, IntegrationMethod::Rk4);

    const auto y_id = ns.resolve("y");
    const auto u_id = ns.resolve("u");
    store.write(u_id, 1.0, "dimensionless");

    for (int i = 0; i < 400; ++i) {
        model.tick(0.01, store);
    }

    const double y = store.read_value(y_id);
    EXPECT_GT(y, 0.0);
    EXPECT_NEAR(y, 2.0, 0.2);
    EXPECT_TRUE(store.is_physics_driven(y_id));
}

TEST(SecondOrderProcessTest, ResetRestoresInitialState) {
    SignalNamespace ns;
    SignalStore store;

    SecondOrderProcessModel model("pt2", 1.0, 0.5, 2.0, 3.0, -1.0, "y", "u", ns, IntegrationMethod::ForwardEuler);

    const auto y_id = ns.resolve("y");
    const auto u_id = ns.resolve("u");
    store.write(u_id, 10.0, "dimensionless");
    model.tick(0.1, store);
    EXPECT_NE(store.read_value(y_id), 3.0);

    model.reset();
    model.tick(0.0, store);
    EXPECT_NEAR(store.read_value(y_id), 3.0, 1e-12);
}

TEST(SecondOrderProcessTest, StabilityLimitMatchesOverdampedEigenvalueBound) {
    SignalNamespace ns;

    constexpr double zeta = 2.0;
    constexpr double omega = 3.0;

    SecondOrderProcessModel euler("euler", 1.0, zeta, omega, 0.0, 0.0, "y", "u", ns, IntegrationMethod::ForwardEuler);
    SecondOrderProcessModel rk4("rk4", 1.0, zeta, omega, 0.0, 0.0, "y2", "u2", ns, IntegrationMethod::Rk4);

    const double expected_euler = expected_overdamped_limit(zeta, omega, 2.0);
    const double expected_rk4 = expected_overdamped_limit(zeta, omega, kRk4NegativeRealAxisStabilityLimit);

    EXPECT_NEAR(euler.compute_stability_limit(), expected_euler, 1e-4);
    EXPECT_NEAR(rk4.compute_stability_limit(), expected_rk4, 1e-4);
}

TEST(SecondOrderProcessTest, UndampedOscillatorEulerIsUnstableForAnyDt) {
    SignalNamespace ns;

    SecondOrderProcessModel euler("euler", 1.0, 0.0, 10.0, 0.0, 0.0, "y", "u", ns, IntegrationMethod::ForwardEuler);
    EXPECT_NEAR(euler.compute_stability_limit(), 0.0, 1e-9);

    SecondOrderProcessModel rk4("rk4", 1.0, 0.0, 10.0, 0.0, 0.0, "y2", "u2", ns, IntegrationMethod::Rk4);
    const double dt_limit = rk4.compute_stability_limit();
    EXPECT_GT(dt_limit, 0.1);
    EXPECT_LT(dt_limit, 0.4);
}

#include "fluxgraph/model/mass_spring_damper.hpp"

#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <limits>

using namespace fluxgraph;

namespace {

double expected_overdamped_limit(double mass, double damping, double spring, double limit) {
    const double trace = -damping / mass;
    const double det = spring / mass;
    const double disc = std::max(0.0, trace * trace - 4.0 * det);
    const double sqrt_disc = std::sqrt(disc);
    const double lambda1 = 0.5 * (trace + sqrt_disc);
    const double lambda2 = 0.5 * (trace - sqrt_disc);
    const double most_negative = std::min(lambda1, lambda2);
    return limit / std::abs(most_negative);
}

}  // namespace

TEST(MassSpringDamperTest, ConstructorRejectsInvalidParams) {
    SignalNamespace ns;

    EXPECT_THROW(MassSpringDamperModel("bad", 0.0, 0.0, 1.0, 0.0, 0.0, "x", "v", "F", ns), std::invalid_argument);
    EXPECT_THROW(
        MassSpringDamperModel("bad", std::numeric_limits<double>::infinity(), 0.0, 1.0, 0.0, 0.0, "x", "v", "F", ns),
        std::invalid_argument);

    EXPECT_THROW(MassSpringDamperModel("bad", 1.0, -1.0, 1.0, 0.0, 0.0, "x", "v", "F", ns), std::invalid_argument);
    EXPECT_THROW(MassSpringDamperModel("bad", 1.0, 0.0, -1.0, 0.0, 0.0, "x", "v", "F", ns), std::invalid_argument);

    EXPECT_THROW(
        MassSpringDamperModel("bad", 1.0, 0.0, 1.0, std::numeric_limits<double>::quiet_NaN(), 0.0, "x", "v", "F", ns),
        std::invalid_argument);
    EXPECT_THROW(
        MassSpringDamperModel("bad", 1.0, 0.0, 1.0, 0.0, std::numeric_limits<double>::quiet_NaN(), "x", "v", "F", ns),
        std::invalid_argument);
}

TEST(MassSpringDamperTest, StepResponseMovesTowardEquilibrium) {
    SignalNamespace ns;
    SignalStore store;

    // Overdamped to avoid oscillation and make the behavior more deterministic.
    MassSpringDamperModel model("msd", 1.0, 10.0, 10.0, 0.0, 0.0, "x", "v", "F", ns, IntegrationMethod::Rk4);

    const auto x_id = ns.resolve("x");
    const auto v_id = ns.resolve("v");
    const auto f_id = ns.resolve("F");

    store.write(f_id, 1.0, "N");

    for (int i = 0; i < 400; ++i) {
        model.tick(0.01, store);
    }

    const double x = store.read_value(x_id);
    const double v = store.read_value(v_id);
    EXPECT_GT(x, 0.0);
    EXPECT_NEAR(x, 0.1, 0.01);  // steady-state: x = F/k = 0.1 m
    EXPECT_NEAR(v, 0.0, 0.05);
    EXPECT_TRUE(store.is_physics_driven(x_id));
    EXPECT_TRUE(store.is_physics_driven(v_id));
}

TEST(MassSpringDamperTest, ResetRestoresInitialState) {
    SignalNamespace ns;
    SignalStore store;

    MassSpringDamperModel model("msd", 2.0, 1.0, 10.0, 3.0, -1.0, "x", "v", "F", ns, IntegrationMethod::ForwardEuler);

    const auto x_id = ns.resolve("x");
    const auto v_id = ns.resolve("v");
    const auto f_id = ns.resolve("F");

    store.write(f_id, 1.0, "N");
    model.tick(0.1, store);
    EXPECT_NE(store.read_value(x_id), 3.0);

    model.reset();
    model.tick(0.0, store);
    EXPECT_NEAR(store.read_value(x_id), 3.0, 1e-12);
    EXPECT_NEAR(store.read_value(v_id), -1.0, 1e-12);
}

TEST(MassSpringDamperTest, StabilityLimitMatchesOverdampedEigenvalueBound) {
    SignalNamespace ns;

    constexpr double mass = 1.0;
    constexpr double damping = 10.0;
    constexpr double spring = 10.0;

    MassSpringDamperModel euler("euler", mass, damping, spring, 0.0, 0.0, "x1", "v1", "F1", ns,
                                IntegrationMethod::ForwardEuler);
    MassSpringDamperModel rk4("rk4", mass, damping, spring, 0.0, 0.0, "x2", "v2", "F2", ns, IntegrationMethod::Rk4);

    const double expected_euler = expected_overdamped_limit(mass, damping, spring, 2.0);
    const double expected_rk4 = expected_overdamped_limit(mass, damping, spring, kRk4NegativeRealAxisStabilityLimit);

    EXPECT_NEAR(euler.compute_stability_limit(), expected_euler, 1e-4);
    EXPECT_NEAR(rk4.compute_stability_limit(), expected_rk4, 1e-4);
}

TEST(MassSpringDamperTest, UndampedOscillatorEulerIsUnstableForAnyDt) {
    SignalNamespace ns;

    MassSpringDamperModel euler("euler", 1.0, 0.0, 100.0, 0.0, 0.0, "x", "v", "F", ns, IntegrationMethod::ForwardEuler);
    EXPECT_NEAR(euler.compute_stability_limit(), 0.0, 1e-9);

    MassSpringDamperModel rk4("rk4", 1.0, 0.0, 100.0, 0.0, 0.0, "x2", "v2", "F2", ns, IntegrationMethod::Rk4);
    const double dt_limit = rk4.compute_stability_limit();
    EXPECT_GT(dt_limit, 0.1);
    EXPECT_LT(dt_limit, 0.4);
}

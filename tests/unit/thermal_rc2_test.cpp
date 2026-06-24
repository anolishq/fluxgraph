#include "fluxgraph/model/thermal_rc2.hpp"

#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <limits>

using namespace fluxgraph;

namespace {

double expected_stability_limit(double Ca, double Cb, double ha, double hb, double k, double rk4_limit) {
    const double a11 = -(ha + k) / Ca;
    const double a22 = -(hb + k) / Cb;
    const double a12 = k / Ca;
    const double a21 = k / Cb;

    const double trace = a11 + a22;
    const double det = a11 * a22 - a12 * a21;
    const double disc = std::max(0.0, trace * trace - 4.0 * det);
    const double sqrt_disc = std::sqrt(disc);

    const double lambda1 = 0.5 * (trace + sqrt_disc);
    const double lambda2 = 0.5 * (trace - sqrt_disc);
    const double most_negative = std::min(lambda1, lambda2);
    return rk4_limit / std::abs(most_negative);
}

}  // namespace

TEST(ThermalRc2Test, ConstructorRejectsInvalidParams) {
    SignalNamespace ns;
    EXPECT_THROW(ThermalRc2Model("bad", 0.0, 1.0, 1.0, 1.0, 0.0, 20.0, 20.0, "a", "b", "power", "ambient", ns),
                 std::invalid_argument);
    EXPECT_THROW(ThermalRc2Model("bad", 1.0, 1.0, 1.0, 1.0, -1.0, 20.0, 20.0, "a", "b", "power", "ambient", ns),
                 std::invalid_argument);
    EXPECT_THROW(ThermalRc2Model("bad", 1.0, 1.0, 1.0, 1.0, 0.0, std::numeric_limits<double>::infinity(), 20.0, "a",
                                 "b", "power", "ambient", ns),
                 std::invalid_argument);
}

TEST(ThermalRc2Test, HeatingCouplesToSecondNode) {
    SignalNamespace ns;
    SignalStore store;

    constexpr double Ca = 1000.0;
    constexpr double Cb = 1500.0;
    constexpr double ha = 10.0;
    constexpr double hb = 8.0;
    constexpr double k = 6.0;
    constexpr double Ta0 = 20.0;
    constexpr double Tb0 = 20.0;

    ThermalRc2Model model("test", Ca, Cb, ha, hb, k, Ta0, Tb0, "a.temp", "b.temp", "heater.power", "ambient.temp", ns,
                          ThermalIntegrationMethod::ForwardEuler);

    const auto temp_a_id = ns.resolve("a.temp");
    const auto temp_b_id = ns.resolve("b.temp");
    const auto power_id = ns.resolve("heater.power");
    const auto ambient_id = ns.resolve("ambient.temp");

    store.write(ambient_id, 20.0, "degC");
    store.write(power_id, 100.0, "W");

    for (int i = 0; i < 200; ++i) {
        model.tick(0.1, store);
    }

    const double Ta = store.read_value(temp_a_id);
    const double Tb = store.read_value(temp_b_id);
    EXPECT_GT(Ta, 20.0);
    EXPECT_GT(Tb, 20.0);
    EXPECT_GT(Ta, Tb);
    EXPECT_TRUE(store.is_physics_driven(temp_a_id));
    EXPECT_TRUE(store.is_physics_driven(temp_b_id));
}

TEST(ThermalRc2Test, ResetRestoresInitialState) {
    SignalNamespace ns;
    SignalStore store;

    ThermalRc2Model model("test", 1000.0, 1000.0, 10.0, 10.0, 5.0, 25.0, 30.0, "a.temp", "b.temp", "heater.power",
                          "ambient.temp", ns, ThermalIntegrationMethod::ForwardEuler);

    const auto temp_a_id = ns.resolve("a.temp");
    const auto temp_b_id = ns.resolve("b.temp");
    const auto power_id = ns.resolve("heater.power");
    const auto ambient_id = ns.resolve("ambient.temp");

    store.write(ambient_id, 20.0, "degC");
    store.write(power_id, 500.0, "W");

    model.tick(1.0, store);
    EXPECT_NE(store.read_value(temp_a_id), 25.0);
    EXPECT_NE(store.read_value(temp_b_id), 30.0);

    model.reset();
    model.tick(0.0, store);

    EXPECT_NEAR(store.read_value(temp_a_id), 25.0, 1e-9);
    EXPECT_NEAR(store.read_value(temp_b_id), 30.0, 1e-9);
}

TEST(ThermalRc2Test, StabilityLimitMatchesEigenvalueBound) {
    SignalNamespace ns;

    constexpr double Ca = 1000.0;
    constexpr double Cb = 2000.0;
    constexpr double ha = 10.0;
    constexpr double hb = 5.0;
    constexpr double k = 4.0;

    ThermalRc2Model euler("euler", Ca, Cb, ha, hb, k, 20.0, 20.0, "a.temp", "b.temp", "heater.power", "ambient.temp",
                          ns, ThermalIntegrationMethod::ForwardEuler);
    ThermalRc2Model rk4("rk4", Ca, Cb, ha, hb, k, 20.0, 20.0, "a2.temp", "b2.temp", "heater2.power", "ambient2.temp",
                        ns, ThermalIntegrationMethod::Rk4);

    const double expected_euler = expected_stability_limit(Ca, Cb, ha, hb, k, 2.0);
    const double expected_rk4 = expected_stability_limit(Ca, Cb, ha, hb, k, kRk4NegativeRealAxisStabilityLimit);

    EXPECT_NEAR(euler.compute_stability_limit(), expected_euler, 1e-9);
    EXPECT_NEAR(rk4.compute_stability_limit(), expected_rk4, 1e-9);
}

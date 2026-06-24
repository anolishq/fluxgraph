#include "fluxgraph/model/dc_motor.hpp"

#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <limits>

using namespace fluxgraph;

namespace {

double expected_overdamped_limit(double a11, double a12, double a21, double a22, double limit) {
    const double trace = a11 + a22;
    const double det = a11 * a22 - a12 * a21;
    const double disc = std::max(0.0, trace * trace - 4.0 * det);
    const double sqrt_disc = std::sqrt(disc);
    const double lambda1 = 0.5 * (trace + sqrt_disc);
    const double lambda2 = 0.5 * (trace - sqrt_disc);
    const double most_negative = std::min(lambda1, lambda2);
    return limit / std::abs(most_negative);
}

}  // namespace

TEST(DcMotorTest, ConstructorRejectsInvalidParams) {
    SignalNamespace ns;

    EXPECT_THROW(DcMotorModel("bad", 0.0, 0.1, 0.1, 0.1, 0.01, 0.0, 0.0, 0.0, "w", "i", "tau", "V", "load", ns),
                 std::invalid_argument);
    EXPECT_THROW(DcMotorModel("bad", 1.0, 0.0, 0.1, 0.1, 0.01, 0.0, 0.0, 0.0, "w", "i", "tau", "V", "load", ns),
                 std::invalid_argument);
    EXPECT_THROW(DcMotorModel("bad", 1.0, 0.1, 0.0, 0.1, 0.01, 0.0, 0.0, 0.0, "w", "i", "tau", "V", "load", ns),
                 std::invalid_argument);
    EXPECT_THROW(DcMotorModel("bad", 1.0, 0.1, 0.1, 0.0, 0.01, 0.0, 0.0, 0.0, "w", "i", "tau", "V", "load", ns),
                 std::invalid_argument);
    EXPECT_THROW(DcMotorModel("bad", 1.0, 0.1, 0.1, 0.1, 0.0, 0.0, 0.0, 0.0, "w", "i", "tau", "V", "load", ns),
                 std::invalid_argument);

    EXPECT_THROW(DcMotorModel("bad", 1.0, 0.1, 0.1, 0.1, 0.01, -1.0, 0.0, 0.0, "w", "i", "tau", "V", "load", ns),
                 std::invalid_argument);

    EXPECT_THROW(DcMotorModel("bad", 1.0, 0.1, 0.1, 0.1, 0.01, 0.0, std::numeric_limits<double>::quiet_NaN(), 0.0, "w",
                              "i", "tau", "V", "load", ns),
                 std::invalid_argument);
}

TEST(DcMotorTest, StepResponseMovesTowardSteadyState) {
    SignalNamespace ns;
    SignalStore store;

    constexpr double R = 2.0;
    constexpr double L = 0.5;
    constexpr double Kt = 0.1;
    constexpr double Ke = 0.1;
    constexpr double J = 0.02;
    constexpr double b = 0.2;

    DcMotorModel model("motor", R, L, Kt, Ke, J, b, 0.0, 0.0, "omega", "i", "tau", "V", "load", ns,
                       IntegrationMethod::Rk4);

    const auto omega_id = ns.resolve("omega");
    const auto i_id = ns.resolve("i");
    const auto tau_id = ns.resolve("tau");
    const auto v_id = ns.resolve("V");
    const auto load_id = ns.resolve("load");

    constexpr double V = 12.0;
    constexpr double load = 0.0;
    store.write(v_id, V, "V");
    store.write(load_id, load, "N*m");

    for (int i = 0; i < 500; ++i) {
        model.tick(0.01, store);
    }

    const double omega = store.read_value(omega_id);
    const double i = store.read_value(i_id);
    const double tau = store.read_value(tau_id);

    const double omega_ss = V / (Ke + R * b / Kt);
    const double i_ss = (b / Kt) * omega_ss;
    const double tau_ss = Kt * i_ss;

    EXPECT_GT(omega, 0.0);
    EXPECT_NEAR(omega, omega_ss, 0.05);
    EXPECT_NEAR(i, i_ss, 0.2);
    EXPECT_NEAR(tau, tau_ss, 0.05);
    EXPECT_TRUE(store.is_physics_driven(omega_id));
    EXPECT_TRUE(store.is_physics_driven(i_id));
    EXPECT_TRUE(store.is_physics_driven(tau_id));
}

TEST(DcMotorTest, ResetRestoresInitialState) {
    SignalNamespace ns;
    SignalStore store;

    DcMotorModel model("motor", 2.0, 0.5, 0.1, 0.1, 0.02, 0.2, 1.0, 3.0, "omega", "i", "tau", "V", "load", ns,
                       IntegrationMethod::ForwardEuler);

    const auto omega_id = ns.resolve("omega");
    const auto i_id = ns.resolve("i");
    const auto v_id = ns.resolve("V");
    const auto load_id = ns.resolve("load");

    store.write(v_id, 12.0, "V");
    store.write(load_id, 0.0, "N*m");
    model.tick(0.1, store);

    model.reset();
    model.tick(0.0, store);
    EXPECT_NEAR(store.read_value(i_id), 1.0, 1e-12);
    EXPECT_NEAR(store.read_value(omega_id), 3.0, 1e-12);
}

TEST(DcMotorTest, StabilityLimitMatchesEigenvalueBoundForRealEigenvalues) {
    SignalNamespace ns;

    constexpr double R = 2.0;
    constexpr double L = 0.5;
    constexpr double Kt = 0.1;
    constexpr double Ke = 0.1;
    constexpr double J = 0.02;
    constexpr double b = 0.2;

    DcMotorModel euler("euler", R, L, Kt, Ke, J, b, 0.0, 0.0, "w1", "i1", "t1", "V1", "load1", ns,
                       IntegrationMethod::ForwardEuler);
    DcMotorModel rk4("rk4", R, L, Kt, Ke, J, b, 0.0, 0.0, "w2", "i2", "t2", "V2", "load2", ns, IntegrationMethod::Rk4);

    const double a11 = -R / L;
    const double a12 = -Ke / L;
    const double a21 = Kt / J;
    const double a22 = -b / J;

    const double expected_euler = expected_overdamped_limit(a11, a12, a21, a22, 2.0);
    const double expected_rk4 = expected_overdamped_limit(a11, a12, a21, a22, kRk4NegativeRealAxisStabilityLimit);

    EXPECT_NEAR(euler.compute_stability_limit(), expected_euler, 1e-4);
    EXPECT_NEAR(rk4.compute_stability_limit(), expected_rk4, 1e-4);
}

#include <gtest/gtest.h>

#include <cmath>

#include "fluxgraph/model/first_order_process.hpp"

using namespace fluxgraph;

namespace {

double exact_pt1(double t, double gain, double tau_s, double u, double y0) {
    const double y_ss = gain * u;
    return y_ss + (y0 - y_ss) * std::exp(-t / tau_s);
}

}  // namespace

TEST(FirstOrderProcessAnalytical, MatchesClosedFormForConstantInput) {
    SignalNamespace ns;
    SignalStore store;

    constexpr double gain = 1.5;
    constexpr double tau_s = 2.0;
    constexpr double y0 = -1.0;
    constexpr double u = 3.0;

    FirstOrderProcessModel model("ref", gain, tau_s, y0, "y", "u", ns, IntegrationMethod::Rk4);

    const auto y_id = ns.resolve("y");
    const auto u_id = ns.resolve("u");
    store.write(u_id, u, "dimensionless");

    constexpr double dt = 0.01;
    constexpr int steps = 500;
    double t = 0.0;

    for (int i = 0; i < steps; ++i) {
        model.tick(dt, store);
        t += dt;
        const double expected = exact_pt1(t, gain, tau_s, u, y0);
        EXPECT_NEAR(store.read_value(y_id), expected, 1e-3);
    }
}

#include <gtest/gtest.h>

#include <cmath>

#include "fluxgraph/model/state_space_siso_discrete.hpp"

using namespace fluxgraph;

TEST(StateSpaceSisoDiscreteAnalytical, MatchesClosedFormForOneStateConstantInput) {
    SignalNamespace ns;
    SignalStore store;

    // x[k+1] = a x[k] + b u, y[k] = x[k]
    constexpr double a = 0.8;
    constexpr double b = 0.5;
    constexpr double x0 = -1.0;
    constexpr double u = 2.0;

    StateSpaceSisoDiscreteModel model("ss", {{a}}, {b}, {1.0}, 0.0, {x0}, "y", "u", ns);

    const SignalId y_id = ns.resolve("y");
    const SignalId u_id = ns.resolve("u");
    store.write(u_id, u, "dimensionless");

    for (int k = 0; k < 40; ++k) {
        model.tick(0.01, store);

        // Closed form for k-th output (y[k] = x[k] before state update in tick).
        const double a_pow_k = std::pow(a, static_cast<double>(k));
        const double x_k = x0 * a_pow_k + b * u * (1.0 - a_pow_k) / (1.0 - a);
        EXPECT_NEAR(store.read_value(y_id), x_k, 1e-12);
    }
}

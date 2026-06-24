#include "fluxgraph/model/state_space_siso_discrete.hpp"

#include <gtest/gtest.h>

#include <limits>

using namespace fluxgraph;

TEST(StateSpaceSisoDiscreteTest, ConstructorRejectsInvalidShapes) {
    SignalNamespace ns;

    EXPECT_THROW((StateSpaceSisoDiscreteModel("bad_empty", {}, {1.0}, {1.0}, 0.0, {0.0}, "y", "u", ns)),
                 std::invalid_argument);

    EXPECT_THROW((StateSpaceSisoDiscreteModel("bad_nonsquare", {{1.0, 0.0}}, {1.0}, {1.0}, 0.0, {0.0}, "y", "u", ns)),
                 std::invalid_argument);

    EXPECT_THROW((StateSpaceSisoDiscreteModel("bad_b", {{1.0}}, {1.0, 2.0}, {1.0}, 0.0, {0.0}, "y", "u", ns)),
                 std::invalid_argument);
}

TEST(StateSpaceSisoDiscreteTest, TickFollowsDifferenceEquations) {
    SignalNamespace ns;
    SignalStore store;

    // x[k+1] = A x[k] + B u[k], y[k] = C x[k]
    // A = [[1, 1], [0, 1]], B = [0.5, 1], C = [1, 0], D = 0, x0 = [0, 0]
    StateSpaceSisoDiscreteModel model("ss", {{1.0, 1.0}, {0.0, 1.0}}, {0.5, 1.0}, {1.0, 0.0}, 0.0, {0.0, 0.0}, "y", "u",
                                      ns);

    const SignalId y_id = ns.resolve("y");
    const SignalId u_id = ns.resolve("u");
    store.write(u_id, 1.0, "dimensionless");

    model.tick(0.01, store);
    EXPECT_DOUBLE_EQ(store.read_value(y_id), 0.0);

    model.tick(0.01, store);
    EXPECT_DOUBLE_EQ(store.read_value(y_id), 0.5);

    model.tick(0.01, store);
    EXPECT_DOUBLE_EQ(store.read_value(y_id), 2.0);

    EXPECT_TRUE(store.is_physics_driven(y_id));
}

TEST(StateSpaceSisoDiscreteTest, ResetRestoresInitialCondition) {
    SignalNamespace ns;
    SignalStore store;

    StateSpaceSisoDiscreteModel model("ss", {{0.9}}, {0.1}, {1.0}, 0.0, {2.0}, "y", "u", ns);

    const SignalId y_id = ns.resolve("y");
    const SignalId u_id = ns.resolve("u");
    store.write(u_id, 0.0, "dimensionless");

    model.tick(0.01, store);
    EXPECT_DOUBLE_EQ(store.read_value(y_id), 2.0);

    model.tick(0.01, store);
    EXPECT_DOUBLE_EQ(store.read_value(y_id), 1.8);

    model.reset();
    model.tick(0.01, store);
    EXPECT_DOUBLE_EQ(store.read_value(y_id), 2.0);
}

TEST(StateSpaceSisoDiscreteTest, StabilityLimitIsInfinity) {
    SignalNamespace ns;
    StateSpaceSisoDiscreteModel model("ss", {{1.0}}, {0.0}, {1.0}, 0.0, {0.0}, "y", "u", ns);

    EXPECT_EQ(model.compute_stability_limit(), std::numeric_limits<double>::infinity());
}

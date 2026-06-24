#include <gtest/gtest.h>

#include <cmath>

#include "fluxgraph/transform/first_order_lag.hpp"

using namespace fluxgraph;

TEST(FirstOrderLagTest, InitializesToFirstInput) {
    FirstOrderLagTransform tf(1.0);
    EXPECT_EQ(tf.apply(100.0, 0.1), 100.0);
}

TEST(FirstOrderLagTest, ApproachesInput) {
    FirstOrderLagTransform tf(1.0);  // tau_s = 1 second

    tf.apply(100.0, 0.1);  // Initialize

    // After multiple time steps, should approach input
    double output = 0.0;
    for (int i = 0; i < 100; ++i) {
        output = tf.apply(100.0, 0.1);
    }

    EXPECT_NEAR(output, 100.0, 0.01);  // Should be very close after 10 seconds
}

TEST(FirstOrderLagTest, ExponentialDecay) {
    FirstOrderLagTransform tf(1.0);

    tf.apply(100.0, 0.1);                // Initialize to 100
    double output = tf.apply(0.0, 1.0);  // Step to 0 with dt=1 (one tau)

    // After one time constant, should be at ~36.8% (1/e) of initial
    EXPECT_NEAR(output, 100.0 * std::exp(-1.0), 1.0);
}

TEST(FirstOrderLagTest, ZeroTauPassthrough) {
    FirstOrderLagTransform tf(0.0);
    EXPECT_EQ(tf.apply(50.0, 0.1), 50.0);
    EXPECT_EQ(tf.apply(100.0, 0.1), 100.0);
}

TEST(FirstOrderLagTest, Reset) {
    FirstOrderLagTransform tf(1.0);

    tf.apply(100.0, 0.1);
    tf.apply(100.0, 0.1);

    tf.reset();

    EXPECT_EQ(tf.apply(50.0, 0.1), 50.0);  // Should reinitialize
}

TEST(FirstOrderLagTest, Clone) {
    FirstOrderLagTransform tf(1.0);
    tf.apply(100.0, 0.1);
    tf.apply(100.0, 0.1);

    ITransform *copy = tf.clone();

    // Clone should have same state
    double orig = tf.apply(0.0, 0.1);
    tf.reset();
    tf.apply(100.0, 0.1);
    tf.apply(100.0, 0.1);
    double from_copy = copy->apply(0.0, 0.1);

    EXPECT_NEAR(orig, from_copy, 0.01);

    delete copy;
}

TEST(FirstOrderLagTest, SmallTimeStep) {
    FirstOrderLagTransform tf(1.0);
    tf.apply(0.0, 0.001);

    // Small step changes should be smooth
    double y1 = tf.apply(100.0, 0.001);
    EXPECT_LT(y1, 1.0);  // Should change slowly with small dt
}

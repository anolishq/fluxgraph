#include <gtest/gtest.h>

#include "fluxgraph/transform/delay.hpp"

using namespace fluxgraph;

TEST(DelayTransformTest, ZeroDelayPassthrough) {
    DelayTransform tf(0.0);
    EXPECT_EQ(tf.apply(100.0, 0.1), 100.0);
    EXPECT_EQ(tf.apply(200.0, 0.1), 200.0);
}

TEST(DelayTransformTest, SimpleDelay) {
    DelayTransform tf(0.2);  // 0.2 second delay

    double y0 = tf.apply(10.0, 0.1);  // t=0, buffer=[10]
    EXPECT_EQ(y0, 10.0);              // First output = first input

    double y1 = tf.apply(20.0, 0.1);  // t=0.1, buffer=[10, 20]
    EXPECT_EQ(y1, 10.0);              // Delayed by one step

    double y2 = tf.apply(30.0, 0.1);  // t=0.2, buffer=[10, 20, 30]
    EXPECT_EQ(y2, 10.0);              // Delayed by two steps

    double y3 = tf.apply(40.0, 0.1);  // t=0.3, buffer=[20, 30, 40] (removed 10)
    EXPECT_EQ(y3, 20.0);              // Now seeing input from t=0.1
}

TEST(DelayTransformTest, ExactDelayMatch) {
    DelayTransform tf(0.3);

    tf.apply(1.0, 0.1);
    tf.apply(2.0, 0.1);
    tf.apply(3.0, 0.1);
    double y = tf.apply(4.0, 0.1);

    EXPECT_EQ(y, 1.0);  // After 0.3s delay, see first input
}

TEST(DelayTransformTest, Reset) {
    DelayTransform tf(0.2);

    tf.apply(10.0, 0.1);
    tf.apply(20.0, 0.1);
    tf.apply(30.0, 0.1);

    tf.reset();

    double y = tf.apply(100.0, 0.1);
    EXPECT_EQ(y, 100.0);  // Reset clears buffer
}

TEST(DelayTransformTest, Clone) {
    DelayTransform tf(0.2);

    tf.apply(10.0, 0.1);
    tf.apply(20.0, 0.1);

    ITransform *copy = tf.clone();

    double y1 = tf.apply(30.0, 0.1);
    double y2 = copy->apply(30.0, 0.1);

    EXPECT_EQ(y1, y2);  // Clone should have same buffer state

    delete copy;
}

TEST(DelayTransformTest, LargeDelay) {
    DelayTransform tf(1.0);  // 1 second delay

    for (int i = 0; i < 20; ++i) {
        tf.apply(static_cast<double>(i), 0.1);
    }

    // After 2 seconds (20 steps), should see input from 1 second ago
    double y = tf.apply(20.0, 0.1);
    EXPECT_EQ(y, 10.0);  // Input from t=1.0 when current t=2.0
}

TEST(DelayTransformTest, VariableTimeStep) {
    DelayTransform tf(0.5);

    tf.apply(1.0, 0.2);
    tf.apply(2.0, 0.2);
    double y = tf.apply(3.0, 0.1);

    EXPECT_EQ(y, 1.0);  // First sample after 0.5s
}

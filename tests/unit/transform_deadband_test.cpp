#include <gtest/gtest.h>

#include "fluxgraph/transform/deadband.hpp"

using namespace fluxgraph;

TEST(DeadbandTransformTest, BelowThresholdReturnsZero) {
    DeadbandTransform tf(10.0);
    EXPECT_EQ(tf.apply(5.0, 0.1), 0.0);
    EXPECT_EQ(tf.apply(-5.0, 0.1), 0.0);
    EXPECT_EQ(tf.apply(9.9, 0.1), 0.0);
    EXPECT_EQ(tf.apply(-9.9, 0.1), 0.0);
}

TEST(DeadbandTransformTest, AboveThresholdPassthrough) {
    DeadbandTransform tf(10.0);
    EXPECT_EQ(tf.apply(15.0, 0.1), 15.0);
    EXPECT_EQ(tf.apply(-15.0, 0.1), -15.0);
    EXPECT_EQ(tf.apply(100.0, 0.1), 100.0);
}

TEST(DeadbandTransformTest, ExactThreshold) {
    DeadbandTransform tf(10.0);
    EXPECT_EQ(tf.apply(10.0, 0.1), 10.0);
    EXPECT_EQ(tf.apply(-10.0, 0.1), -10.0);
}

TEST(DeadbandTransformTest, ZeroThreshold) {
    DeadbandTransform tf(0.0);
    EXPECT_EQ(tf.apply(5.0, 0.1), 5.0);
    EXPECT_EQ(tf.apply(-5.0, 0.1), -5.0);
    EXPECT_EQ(tf.apply(0.0, 0.1), 0.0);
}

TEST(DeadbandTransformTest, SmallThreshold) {
    DeadbandTransform tf(0.1);
    EXPECT_EQ(tf.apply(0.05, 0.1), 0.0);
    EXPECT_EQ(tf.apply(0.2, 0.1), 0.2);
}

TEST(DeadbandTransformTest, Clone) {
    DeadbandTransform tf(5.0);
    ITransform *copy = tf.clone();

    EXPECT_EQ(copy->apply(3.0, 0.1), 0.0);
    EXPECT_EQ(copy->apply(10.0, 0.1), 10.0);

    delete copy;
}

TEST(DeadbandTransformTest, Reset) {
    DeadbandTransform tf(10.0);
    tf.apply(5.0, 0.1);
    tf.reset();  // No-op for stateless transform
    EXPECT_EQ(tf.apply(5.0, 0.1), 0.0);
}

TEST(DeadbandTransformTest, TimeStepIndependent) {
    DeadbandTransform tf(10.0);
    EXPECT_EQ(tf.apply(5.0, 0.01), tf.apply(5.0, 1.0));
}

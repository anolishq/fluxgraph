#include <gtest/gtest.h>

#include "fluxgraph/transform/saturation.hpp"

using namespace fluxgraph;

TEST(SaturationTransformTest, WithinBoundsPassthrough) {
    SaturationTransform tf(0.0, 100.0);
    EXPECT_EQ(tf.apply(50.0, 0.1), 50.0);
    EXPECT_EQ(tf.apply(0.0, 0.1), 0.0);
    EXPECT_EQ(tf.apply(100.0, 0.1), 100.0);
}

TEST(SaturationTransformTest, ClampToMax) {
    SaturationTransform tf(0.0, 100.0);
    EXPECT_EQ(tf.apply(150.0, 0.1), 100.0);
    EXPECT_EQ(tf.apply(200.0, 0.1), 100.0);
}

TEST(SaturationTransformTest, ClampToMin) {
    SaturationTransform tf(0.0, 100.0);
    EXPECT_EQ(tf.apply(-50.0, 0.1), 0.0);
    EXPECT_EQ(tf.apply(-100.0, 0.1), 0.0);
}

TEST(SaturationTransformTest, NegativeBounds) {
    SaturationTransform tf(-50.0, -10.0);
    EXPECT_EQ(tf.apply(-30.0, 0.1), -30.0);  // Within bounds
    EXPECT_EQ(tf.apply(-5.0, 0.1), -10.0);   // Clamp to max
    EXPECT_EQ(tf.apply(-60.0, 0.1), -50.0);  // Clamp to min
}

TEST(SaturationTransformTest, SymmetricBounds) {
    SaturationTransform tf(-10.0, 10.0);
    EXPECT_EQ(tf.apply(5.0, 0.1), 5.0);
    EXPECT_EQ(tf.apply(-5.0, 0.1), -5.0);
    EXPECT_EQ(tf.apply(15.0, 0.1), 10.0);
    EXPECT_EQ(tf.apply(-15.0, 0.1), -10.0);
}

TEST(SaturationTransformTest, Clone) {
    SaturationTransform tf(-50.0, 50.0);
    ITransform *copy = tf.clone();

    EXPECT_EQ(copy->apply(100.0, 0.1), 50.0);
    EXPECT_EQ(copy->apply(-100.0, 0.1), -50.0);

    delete copy;
}

TEST(SaturationTransformTest, Reset) {
    SaturationTransform tf(0.0, 100.0);
    tf.apply(150.0, 0.1);
    tf.reset();  // No-op for stateless transform
    EXPECT_EQ(tf.apply(150.0, 0.1), 100.0);
}

TEST(SaturationTransformTest, TimeStepIndependent) {
    SaturationTransform tf(0.0, 100.0);
    EXPECT_EQ(tf.apply(150.0, 0.01), tf.apply(150.0, 1.0));
}

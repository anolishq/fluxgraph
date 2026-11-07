#include <gtest/gtest.h>

#include <cmath>
#include <limits>
#include <stdexcept>

#include "fluxgraph/transform/linear.hpp"

using namespace fluxgraph;

TEST(LinearTransformTest, ScaleOnly) {
    LinearTransform tf(2.0, 0.0);
    EXPECT_EQ(tf.apply(10.0, 0.1), 20.0);
    EXPECT_EQ(tf.apply(-5.0, 0.1), -10.0);
}

TEST(LinearTransformTest, OffsetOnly) {
    LinearTransform tf(1.0, 10.0);
    EXPECT_EQ(tf.apply(5.0, 0.1), 15.0);
    EXPECT_EQ(tf.apply(-5.0, 0.1), 5.0);
}

TEST(LinearTransformTest, ScaleAndOffset) {
    LinearTransform tf(2.0, 5.0);
    EXPECT_EQ(tf.apply(10.0, 0.1), 25.0);  // 2*10 + 5
    EXPECT_EQ(tf.apply(0.0, 0.1), 5.0);    // 2*0 + 5
}

TEST(LinearTransformTest, ClampMax) {
    LinearTransform tf(2.0, 0.0, -std::numeric_limits<double>::infinity(), 10.0);
    EXPECT_EQ(tf.apply(3.0, 0.1), 6.0);    // Within bounds
    EXPECT_EQ(tf.apply(10.0, 0.1), 10.0);  // Clamped to max
}

TEST(LinearTransformTest, ClampMin) {
    LinearTransform tf(2.0, 0.0, 0.0, std::numeric_limits<double>::infinity());
    EXPECT_EQ(tf.apply(5.0, 0.1), 10.0);  // Within bounds
    EXPECT_EQ(tf.apply(-5.0, 0.1), 0.0);  // Clamped to min
}

TEST(LinearTransformTest, ClampBoth) {
    LinearTransform tf(1.0, 0.0, -10.0, 10.0);
    EXPECT_EQ(tf.apply(5.0, 0.1), 5.0);      // Within bounds
    EXPECT_EQ(tf.apply(15.0, 0.1), 10.0);    // Clamped to max
    EXPECT_EQ(tf.apply(-15.0, 0.1), -10.0);  // Clamped to min
}

TEST(LinearTransformTest, Clone) {
    LinearTransform tf(3.0, 7.0, 0.0, 100.0);
    ITransform *copy = tf.clone();

    EXPECT_EQ(copy->apply(10.0, 0.1), 37.0);  // 3*10 + 7

    delete copy;
}

TEST(LinearTransformTest, Reset) {
    LinearTransform tf(2.0, 0.0);
    tf.apply(10.0, 0.1);
    tf.reset();  // Should be no-op for stateless transform
    EXPECT_EQ(tf.apply(10.0, 0.1), 20.0);
}

TEST(LinearTransformTest, TimeStepIndependent) {
    LinearTransform tf(2.0, 3.0);
    EXPECT_EQ(tf.apply(5.0, 0.01), tf.apply(5.0, 1.0));
}

// std::clamp requires !(hi < lo); inverted clamp bounds were undefined behaviour (#145).
TEST(LinearTransformTest, ConstructorRejectsInvertedClampBounds) {
    EXPECT_THROW(LinearTransform(1.0, 0.0, 10.0, 0.0), std::invalid_argument);
}

// A NaN clamp bound silently disabled that side of the clamp (#145).
TEST(LinearTransformTest, ConstructorRejectsNaNClampBounds) {
    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double inf = std::numeric_limits<double>::infinity();
    EXPECT_THROW(LinearTransform(1.0, 0.0, nan, inf), std::invalid_argument);
    EXPECT_THROW(LinearTransform(1.0, 0.0, -inf, nan), std::invalid_argument);
}

TEST(LinearTransformTest, EqualClampBoundsAreValid) {
    LinearTransform tf(2.0, 1.0, 3.0, 3.0);
    EXPECT_EQ(tf.apply(-10.0, 0.1), 3.0);
    EXPECT_EQ(tf.apply(10.0, 0.1), 3.0);
}

TEST(LinearTransformTest, DefaultClampBoundsAreUnbounded) {
    LinearTransform tf(1.0, 0.0);
    EXPECT_EQ(tf.apply(-1e300, 0.1), -1e300);
    EXPECT_EQ(tf.apply(1e300, 0.1), 1e300);
}

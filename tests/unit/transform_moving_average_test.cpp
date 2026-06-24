#include <gtest/gtest.h>

#include "fluxgraph/transform/moving_average.hpp"

using namespace fluxgraph;

TEST(MovingAverageTest, SingleSample) {
    MovingAverageTransform tf(3);
    EXPECT_EQ(tf.apply(10.0, 0.1), 10.0);
}

TEST(MovingAverageTest, TwoSamples) {
    MovingAverageTransform tf(3);
    tf.apply(10.0, 0.1);
    double y = tf.apply(20.0, 0.1);
    EXPECT_EQ(y, 15.0);  // (10 + 20) / 2
}

TEST(MovingAverageTest, ThreeSamples) {
    MovingAverageTransform tf(3);
    tf.apply(10.0, 0.1);
    tf.apply(20.0, 0.1);
    double y = tf.apply(30.0, 0.1);
    EXPECT_EQ(y, 20.0);  // (10 + 20 + 30) / 3
}

TEST(MovingAverageTest, WindowSliding) {
    MovingAverageTransform tf(3);
    tf.apply(10.0, 0.1);
    tf.apply(20.0, 0.1);
    tf.apply(30.0, 0.1);
    double y = tf.apply(40.0, 0.1);  // Window full, remove 10
    EXPECT_EQ(y, 30.0);              // (20 + 30 + 40) / 3
}

TEST(MovingAverageTest, WindowSize1) {
    MovingAverageTransform tf(1);
    EXPECT_EQ(tf.apply(10.0, 0.1), 10.0);
    EXPECT_EQ(tf.apply(20.0, 0.1), 20.0);  // Always current value
}

TEST(MovingAverageTest, LargeWindow) {
    MovingAverageTransform tf(100);

    double sum = 0.0;
    for (int i = 1; i <= 10; ++i) {
        sum += i;
        double y = tf.apply(static_cast<double>(i), 0.1);
        EXPECT_EQ(y, sum / i);
    }
}

TEST(MovingAverageTest, ConstantInput) {
    MovingAverageTransform tf(5);

    for (int i = 0; i < 10; ++i) {
        double y = tf.apply(42.0, 0.1);
        EXPECT_EQ(y, 42.0);
    }
}

TEST(MovingAverageTest, Reset) {
    MovingAverageTransform tf(3);
    tf.apply(10.0, 0.1);
    tf.apply(20.0, 0.1);
    tf.apply(30.0, 0.1);

    tf.reset();

    double y = tf.apply(100.0, 0.1);
    EXPECT_EQ(y, 100.0);  // Reset clears window
}

TEST(MovingAverageTest, Clone) {
    MovingAverageTransform tf(3);
    tf.apply(10.0, 0.1);
    tf.apply(20.0, 0.1);

    ITransform *copy = tf.clone();

    double y1 = tf.apply(30.0, 0.1);
    double y2 = copy->apply(30.0, 0.1);

    EXPECT_EQ(y1, y2);  // Clone has same window state

    delete copy;
}

TEST(MovingAverageTest, TimeStepIndependent) {
    MovingAverageTransform tf(3);

    // Moving average doesn't depend on dt, only sample count
    tf.apply(10.0, 0.01);
    tf.apply(20.0, 1.0);
    double y = tf.apply(30.0, 0.5);

    EXPECT_EQ(y, 20.0);
}

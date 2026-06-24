#include <gtest/gtest.h>

#include "fluxgraph/transform/rate_limiter.hpp"

using namespace fluxgraph;

TEST(RateLimiterTest, InitializesToFirstInput) {
    RateLimiterTransform tf(10.0);
    EXPECT_EQ(tf.apply(100.0, 0.1), 100.0);
}

TEST(RateLimiterTest, LimitRiseRate) {
    RateLimiterTransform tf(10.0);  // 10 units/sec max

    tf.apply(0.0, 0.1);               // Initialize
    double y = tf.apply(100.0, 0.1);  // Try to jump 100 units

    EXPECT_EQ(y, 1.0);  // Limited to 10 * 0.1 = 1.0
}

TEST(RateLimiterTest, LimitFallRate) {
    RateLimiterTransform tf(10.0);

    tf.apply(100.0, 0.1);           // Initialize
    double y = tf.apply(0.0, 0.1);  // Try to drop 100 units

    EXPECT_EQ(y, 99.0);  // Limited to -10 * 0.1 = -1.0
}

TEST(RateLimiterTest, GradualApproach) {
    RateLimiterTransform tf(10.0);

    tf.apply(0.0, 0.1);

    // Step to 100 with rate limit of 10/sec
    for (int i = 0; i < 10; ++i) {
        double y = tf.apply(100.0, 1.0);
        EXPECT_NEAR(y, (i + 1) * 10.0, 0.01);
    }
}

TEST(RateLimiterTest, WithinRatePassthrough) {
    RateLimiterTransform tf(10.0);

    tf.apply(0.0, 0.1);
    double y = tf.apply(0.5, 0.1);  // Change of 0.5 in 0.1s = 5/s

    EXPECT_EQ(y, 0.5);  // Within rate limit
}

TEST(RateLimiterTest, ZeroRatePassthrough) {
    RateLimiterTransform tf(0.0);

    tf.apply(0.0, 0.1);
    double y = tf.apply(100.0, 0.1);

    EXPECT_EQ(y, 100.0);  // Zero rate = no limiting
}

TEST(RateLimiterTest, Reset) {
    RateLimiterTransform tf(10.0);

    tf.apply(0.0, 0.1);
    tf.apply(50.0, 0.1);

    tf.reset();

    EXPECT_EQ(tf.apply(100.0, 0.1), 100.0);  // Reinitialize
}

TEST(RateLimiterTest, Clone) {
    RateLimiterTransform tf(10.0);

    tf.apply(0.0, 0.1);
    tf.apply(50.0, 1.0);

    ITransform *copy = tf.clone();

    double y1 = tf.apply(100.0, 1.0);
    tf.reset();
    tf.apply(0.0, 0.1);
    tf.apply(50.0, 1.0);
    double y2 = copy->apply(100.0, 1.0);

    EXPECT_NEAR(y1, y2, 0.01);

    delete copy;
}

TEST(RateLimiterTest, VariableTimeStep) {
    RateLimiterTransform tf(10.0);

    tf.apply(0.0, 0.1);

    double y1 = tf.apply(100.0, 0.5);  // 0.5s step
    EXPECT_EQ(y1, 5.0);                // Limited to 10 * 0.5

    double y2 = tf.apply(100.0, 0.2);  // 0.2s step
    EXPECT_EQ(y2, 7.0);                // Limited to 5.0 + 10 * 0.2
}

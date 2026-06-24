#include <gtest/gtest.h>

#include <cmath>
#include <vector>

#include "fluxgraph/transform/deadband.hpp"
#include "fluxgraph/transform/linear.hpp"
#include "fluxgraph/transform/moving_average.hpp"
#include "fluxgraph/transform/rate_limiter.hpp"
#include "fluxgraph/transform/saturation.hpp"

using namespace fluxgraph;

// ===== LinearTransform Analytical Tests =====

TEST(LinearTransformAnalytical, ExactScaleAndOffset) {
    LinearTransform tf(2.5, 10.0);

    // Test exact floating-point arithmetic
    EXPECT_DOUBLE_EQ(tf.apply(0.0, 0.1), 10.0);
    EXPECT_DOUBLE_EQ(tf.apply(4.0, 0.1), 20.0);     // 2.5*4 + 10
    EXPECT_DOUBLE_EQ(tf.apply(-4.0, 0.1), 0.0);     // 2.5*(-4) + 10
    EXPECT_DOUBLE_EQ(tf.apply(100.0, 0.1), 260.0);  // 2.5*100 + 10
}

TEST(LinearTransformAnalytical, InverseTransform) {
    // If y = ax + b, then x = (y - b) / a
    double scale = 3.0;
    double offset = 7.0;
    LinearTransform forward(scale, offset);
    LinearTransform inverse(1.0 / scale, -offset / scale);

    std::vector<double> test_values = {0.0, 1.0, -1.0, 10.0, -10.0, 42.5};
    for (double x : test_values) {
        double y = forward.apply(x, 0.1);
        double x_recovered = inverse.apply(y, 0.1);
        EXPECT_NEAR(x_recovered, x, 1e-10) << "Original=" << x;
    }
}

// ===== SaturationTransform Analytical Tests =====

TEST(SaturationTransformAnalytical, ExactClamping) {
    SaturationTransform sat(-10.0, 10.0);

    // Exact clamping (should be bit-exact)
    EXPECT_DOUBLE_EQ(sat.apply(-20.0, 0.1), -10.0);  // Below min
    EXPECT_DOUBLE_EQ(sat.apply(-10.0, 0.1), -10.0);  // At min
    EXPECT_DOUBLE_EQ(sat.apply(-5.0, 0.1), -5.0);    // In range
    EXPECT_DOUBLE_EQ(sat.apply(0.0, 0.1), 0.0);      // In range
    EXPECT_DOUBLE_EQ(sat.apply(5.0, 0.1), 5.0);      // In range
    EXPECT_DOUBLE_EQ(sat.apply(10.0, 0.1), 10.0);    // At max
    EXPECT_DOUBLE_EQ(sat.apply(20.0, 0.1), 10.0);    // Above max
}

TEST(SaturationTransformAnalytical, NoOvershoot) {
    SaturationTransform sat(0.0, 100.0);

    // No overshoot: output never exceeds bounds
    for (double input = -1000.0; input <= 1000.0; input += 0.1) {
        double output = sat.apply(input, 0.1);
        EXPECT_GE(output, 0.0);
        EXPECT_LE(output, 100.0);
    }
}

// ===== DeadbandTransform Analytical Tests =====

TEST(DeadbandTransformAnalytical, ExactThreshold) {
    DeadbandTransform db(5.0);

    EXPECT_DOUBLE_EQ(db.apply(0.0, 0.1), 0.0);
    EXPECT_DOUBLE_EQ(db.apply(4.9, 0.1), 0.0);    // Just below threshold
    EXPECT_DOUBLE_EQ(db.apply(5.0, 0.1), 5.0);    // At threshold
    EXPECT_DOUBLE_EQ(db.apply(5.1, 0.1), 5.1);    // Just above threshold
    EXPECT_DOUBLE_EQ(db.apply(-4.9, 0.1), 0.0);   // Just below threshold (negative)
    EXPECT_DOUBLE_EQ(db.apply(-5.0, 0.1), -5.0);  // At threshold (negative)
    EXPECT_DOUBLE_EQ(db.apply(-5.1, 0.1),
                     -5.1);  // Just above threshold (negative)
}

// ===== RateLimiterTransform Analytical Tests =====

TEST(RateLimiterTransformAnalytical, SlopeConstraint) {
    RateLimiterTransform rl(10.0);  // 10 units/sec max rate

    rl.apply(0.0, 0.1);  // Initialize

    // Large step should be rate-limited
    double y1 = rl.apply(100.0, 0.1);  // Request 100 in 0.1s = 1000/s
    EXPECT_DOUBLE_EQ(y1, 1.0);         // Limited to 10 * 0.1 = 1.0

    // Next step
    double y2 = rl.apply(100.0, 0.1);
    EXPECT_DOUBLE_EQ(y2, 2.0);  // Limited to 1.0 + 10 * 0.1 = 2.0

    // Verify constant slope
    for (int i = 0; i < 98; ++i) {
        double y = rl.apply(100.0, 0.1);
        EXPECT_NEAR(y, 3.0 + i, 1e-10);
    }
}

TEST(RateLimiterTransformAnalytical, BidirectionalLimit) {
    RateLimiterTransform rl(5.0);

    rl.apply(50.0, 0.1);  // Initialize to 50

    // Large negative step
    double y1 = rl.apply(0.0, 0.1);
    EXPECT_DOUBLE_EQ(y1, 49.5);  // Limited to 50 - 5*0.1 = 49.5

    // Continue descending
    for (int i = 0; i < 99; ++i) {
        double y = rl.apply(0.0, 0.1);
        double expected = 49.5 - (i + 1) * 0.5;
        EXPECT_NEAR(y, expected, 1e-10);
    }
}

// ===== MovingAverageTransform Analytical Tests =====

TEST(MovingAverageTransformAnalytical, ConstantInput) {
    MovingAverageTransform ma(5);

    // Constant input should converge to that value
    for (int i = 0; i < 10; ++i) {
        double y = ma.apply(42.0, 0.1);
        EXPECT_DOUBLE_EQ(y, 42.0);
    }
}

TEST(MovingAverageTransformAnalytical, WindowAverage) {
    MovingAverageTransform ma(3);

    double y1 = ma.apply(1.0, 0.1);
    EXPECT_DOUBLE_EQ(y1, 1.0);  // [1]

    double y2 = ma.apply(2.0, 0.1);
    EXPECT_DOUBLE_EQ(y2, 1.5);  // [1, 2] avg

    double y3 = ma.apply(3.0, 0.1);
    EXPECT_DOUBLE_EQ(y3, 2.0);  // [1, 2, 3] avg

    double y4 = ma.apply(4.0, 0.1);
    EXPECT_DOUBLE_EQ(y4, 3.0);  // [2, 3, 4] avg (1 dropped)

    double y5 = ma.apply(5.0, 0.1);
    EXPECT_DOUBLE_EQ(y5, 4.0);  // [3, 4, 5] avg
}

TEST(MovingAverageTransformAnalytical, StepResponse) {
    MovingAverageTransform ma(10);

    // Initialize window with zeros
    for (int i = 0; i < 10; ++i) {
        ma.apply(0.0, 0.1);
    }

    // Step from 0 to 1 - window gradually fills with 1s
    for (int i = 0; i < 10; ++i) {
        double y = ma.apply(1.0, 0.1);
        double expected = (i + 1) / 10.0;  // Window filling with 1s
        EXPECT_DOUBLE_EQ(y, expected) << "Sample " << i << ": moving average should be " << expected;
    }

    // Window now full with 1s, should be 1.0
    double y_full = ma.apply(1.0, 0.1);
    EXPECT_DOUBLE_EQ(y_full, 1.0);
}

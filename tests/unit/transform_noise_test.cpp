#include <gtest/gtest.h>

#include <cmath>
#include <vector>

#include "fluxgraph/transform/noise.hpp"

using namespace fluxgraph;

TEST(NoiseTransformTest, AddsNoise) {
    NoiseTransform tf(1.0, 42);

    double input = 100.0;
    double output = tf.apply(input, 0.1);

    EXPECT_NE(output, input);  // Should add noise
}

TEST(NoiseTransformTest, DeterministicWithSeed) {
    NoiseTransform tf1(1.0, 42);
    NoiseTransform tf2(1.0, 42);

    for (int i = 0; i < 10; ++i) {
        double y1 = tf1.apply(100.0, 0.1);
        double y2 = tf2.apply(100.0, 0.1);
        EXPECT_EQ(y1, y2);  // Same seed = same sequence
    }
}

TEST(NoiseTransformTest, DifferentSeedsDifferentOutput) {
    NoiseTransform tf1(1.0, 42);
    NoiseTransform tf2(1.0, 43);

    double y1 = tf1.apply(100.0, 0.1);
    double y2 = tf2.apply(100.0, 0.1);

    EXPECT_NE(y1, y2);  // Different seeds = different sequences
}

TEST(NoiseTransformTest, StatisticalProperties) {
    NoiseTransform tf(2.0, 12345);

    // Generate many samples
    std::vector<double> samples;
    double input = 0.0;
    for (int i = 0; i < 10000; ++i) {
        samples.push_back(tf.apply(input, 0.1));
    }

    // Compute mean and stddev
    double sum = 0.0;
    for (double s : samples) {
        sum += s;
    }
    double mean = sum / samples.size();

    double variance = 0.0;
    for (double s : samples) {
        variance += (s - mean) * (s - mean);
    }
    variance /= samples.size();
    double stddev = std::sqrt(variance);

    // Mean should be close to 0 (input + N(0, amplitude))
    EXPECT_NEAR(mean, input, 0.1);

    // Stddev should be close to amplitude
    EXPECT_NEAR(stddev, 2.0, 0.1);
}

TEST(NoiseTransformTest, Reset) {
    NoiseTransform tf(1.0, 42);

    double y1 = tf.apply(100.0, 0.1);
    tf.reset();
    double y2 = tf.apply(100.0, 0.1);

    EXPECT_EQ(y1, y2);  // Reset should restart sequence
}

TEST(NoiseTransformTest, Clone) {
    NoiseTransform tf(1.0, 42);

    tf.apply(100.0, 0.1);
    tf.apply(100.0, 0.1);

    ITransform *copy = tf.clone();

    // Both should produce same next values (same RNG state)
    double y1 = tf.apply(100.0, 0.1);
    tf.reset();
    tf.apply(100.0, 0.1);
    tf.apply(100.0, 0.1);
    double y2 = copy->apply(100.0, 0.1);

    EXPECT_EQ(y1, y2);

    delete copy;
}

TEST(NoiseTransformTest, ZeroAmplitude) {
    NoiseTransform tf(0.0, 42);

    double input = 100.0;
    double output = tf.apply(input, 0.1);

    EXPECT_EQ(output, input);  // Zero amplitude = no noise
}

TEST(NoiseTransformTest, AmplitudeParameterSemantics) {
    // Verify parameter name amplitude (not stddev)
    NoiseTransform tf(5.0, 999);  // amplitude in same units as signal

    double y = tf.apply(50.0, 0.1);
    EXPECT_GT(y, 40.0);  // Likely within a few stddevs
    EXPECT_LT(y, 60.0);
}

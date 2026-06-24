#define _USE_MATH_DEFINES
#include <gtest/gtest.h>

#include <cmath>
#include <vector>

#include "fluxgraph/transform/delay.hpp"

using namespace fluxgraph;

TEST(DelayTransformAnalytical, ExactTimeShift) {
    DelayTransform delay(1.0);  // 1 second delay

    double dt = 0.01;  // 10ms
    std::vector<double> input_signal;
    std::vector<double> output_signal;

    // Input: step function at t=0.5s
    for (int i = 0; i < 200; ++i) {
        double t = i * dt;
        double input = (t >= 0.5) ? 1.0 : 0.0;
        double output = delay.apply(input, dt);

        input_signal.push_back(input);
        output_signal.push_back(output);
    }

    // Output should match input shifted by 1.0/dt = 100 samples
    int delay_samples = static_cast<int>(1.0 / dt);
    for (int i = delay_samples; i < 200; ++i) {
        EXPECT_NEAR(output_signal[i], input_signal[i - delay_samples], 1e-6)
            << "Sample " << i << ": output doesn't match delayed input";
    }
}

TEST(DelayTransformAnalytical, SineWavePhaseShift) {
    // Delay a sine wave and verify phase shift
    DelayTransform delay(0.25);  // 0.25 second delay

    double dt = 0.01;
    double freq = 1.0;  // 1 Hz
    double period = 1.0 / freq;
    double phase_shift = 2.0 * M_PI * delay.apply(0.0, 0.0);  // Get delay value... wait, can't access private

    std::vector<double> input_signal;
    std::vector<double> output_signal;

    for (int i = 0; i < 200; ++i) {
        double t = i * dt;
        double input = std::sin(2.0 * M_PI * freq * t);
        double output = delay.apply(input, dt);

        input_signal.push_back(input);
        output_signal.push_back(output);
    }

    // After delay_samples, output should match input shifted by 0.25/dt = 25
    // samples
    int delay_samples = static_cast<int>(0.25 / dt);
    for (int i = delay_samples + 50; i < 200; ++i) {  // Skip transient
        EXPECT_NEAR(output_signal[i], input_signal[i - delay_samples], 1e-3) << "Sample " << i;
    }
}

TEST(DelayTransformAnalytical, RampSignal) {
    DelayTransform delay(0.5);
    double dt = 0.01;

    std::vector<double> input_signal;
    std::vector<double> output_signal;

    // Input: ramp function
    for (int i = 0; i < 200; ++i) {
        double t = i * dt;
        double input = t;  // Linear ramp
        double output = delay.apply(input, dt);

        input_signal.push_back(input);
        output_signal.push_back(output);
    }

    int delay_samples = static_cast<int>(0.5 / dt);
    for (int i = delay_samples; i < 200; ++i) {
        EXPECT_NEAR(output_signal[i], input_signal[i - delay_samples], 0.01) << "Sample " << i;
    }
}

#include <gtest/gtest.h>

#include <algorithm>
#include <cmath>
#include <limits>
#include <memory>
#include <stdexcept>
#include <vector>

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

namespace {

// Drives `tf` with input = current time, so (t - output) is the delay actually applied.
// Tick 0 is t = 0; each later call advances t by its dt. Returns the applied delay per call.
std::vector<double> applied_delays(DelayTransform &tf, double &t, bool &first, const std::vector<double> &dts) {
    std::vector<double> delays;
    for (double dt : dts) {
        if (!first) {
            t += dt;
        }
        first = false;
        delays.push_back(t - tf.apply(t, dt));
    }
    return delays;
}

std::vector<double> repeat(double dt, int n) { return std::vector<double>(static_cast<size_t>(n), dt); }

}  // namespace

// #146: after dt grows, the buffer kept the old sample count, so the applied
// delay settled at count * new_dt (5 s for 10 samples at 0.5 s) instead of 1 s.
TEST(DelayTransformTest, DelayHoldsWhenDtGrows) {
    DelayTransform tf(1.0);
    double t = 0.0;
    bool first = true;
    (void)applied_delays(tf, t, first, repeat(0.1, 20));  // t = 1.9, history filled
    const auto delays = applied_delays(tf, t, first, repeat(0.5, 40));
    for (size_t i = 0; i < delays.size(); ++i) {
        // The output is the stored sample nearest t - delay_sec, so the error is at
        // most half the coarser sample spacing (0.25 s), well within one sample.
        EXPECT_LE(std::abs(delays[i] - 1.0), 0.25 + 1e-9) << "step " << i << " after dt grew";
    }
    // Once the history is all at the new dt, the delay is exact (1.0 = 2 * 0.5).
    EXPECT_NEAR(delays.back(), 1.0, 1e-9);
}

// #146: after dt shrinks, nothing was popped until the buffer reached the new
// sample count, so the output held one stale value while time moved on.
TEST(DelayTransformTest, DelayHoldsWhenDtShrinks) {
    DelayTransform tf(1.0);
    double t = 0.0;
    bool first = true;
    (void)applied_delays(tf, t, first, repeat(0.5, 6));  // t = 2.5
    const auto delays = applied_delays(tf, t, first, repeat(0.1, 40));
    for (size_t i = 0; i < delays.size(); ++i) {
        EXPECT_LE(std::abs(delays[i] - 1.0), 0.25 + 1e-9) << "step " << i << " after dt shrank";
    }
    EXPECT_NEAR(delays.back(), 1.0, 1e-9);
}

// At a constant dt the lag is N ticks: delay_sec / dt rounded to the nearest
// integer, minimum 1, with a half (n + 0.5, to within 1e-9 of a tick) rounding up
// to the older sample. A ratio meant to be n.5 counts as a half even when its
// floating-point quotient lands just below it: 0.15 / 0.1 is 1.4999999999999998,
// for which llround (the rule before #146) gives 1; here N = 2.
TEST(DelayTransformTest, ConstantDtMatchesTickCount) {
    struct Case {
        double delay_sec;
        double dt;
        int n;
    };
    for (const Case c : {Case{1.0, 0.1, 10}, Case{0.25, 0.1, 3}, Case{0.24, 0.1, 2}, Case{0.04, 0.1, 1},
                         Case{0.3, 0.01, 30}, Case{0.15, 0.1, 2}}) {
        DelayTransform tf(c.delay_sec);
        for (int k = 0; k < 100; ++k) {
            const double y = tf.apply(static_cast<double>(k), c.dt);
            EXPECT_EQ(y, static_cast<double>(std::max(0, k - c.n)))
                << "delay_sec=" << c.delay_sec << " dt=" << c.dt << " k=" << k << " N=" << c.n;
        }
    }
}

// The lag at a constant dt must not change over a long run. With the clock kept
// as a plain accumulated double, rounding grew with the clock until a half-tick
// tie flipped: 0.25 / 0.1 went from lag 3 to lag 2 at tick 10,485,762.
TEST(DelayTransformTest, ConstantDtLagIsStableOverLongRuns) {
    constexpr long kTicks = 11000000;  // past the tick where the lag used to flip
    DelayTransform tf(0.25);
    long mismatches = 0;
    long first_mismatch = -1;
    for (long k = 0; k < kTicks; ++k) {
        const double y = tf.apply(static_cast<double>(k), 0.1);
        if (k >= 3 && y != static_cast<double>(k - 3)) {
            if (first_mismatch < 0) {
                first_mismatch = k;
            }
            ++mismatches;
        }
    }
    EXPECT_EQ(mismatches, 0) << "lag left 3 ticks first at tick " << first_mismatch;
}

// #146: dt == 0 used to call llround(inf); dt < 0 a negative count. Both are now
// rejected, as Engine::tick rejects them.
TEST(DelayTransformTest, RejectsNonPositiveDt) {
    DelayTransform tf(1.0);
    EXPECT_THROW(tf.apply(1.0, 0.0), std::runtime_error);
    EXPECT_THROW(tf.apply(1.0, -0.1), std::runtime_error);

    DelayTransform passthrough(0.0);
    EXPECT_THROW(passthrough.apply(1.0, 0.0), std::runtime_error);
}

// A rejected call leaves the state unchanged.
TEST(DelayTransformTest, RejectedDtDoesNotDisturbState) {
    DelayTransform tf(0.2);
    tf.apply(10.0, 0.1);
    tf.apply(20.0, 0.1);
    EXPECT_THROW(tf.apply(99.0, 0.0), std::runtime_error);
    EXPECT_EQ(tf.apply(30.0, 0.1), 10.0);
    EXPECT_EQ(tf.apply(40.0, 0.1), 20.0);
}

// The clone carries the sample times, so it applies the same delay after dt changes.
TEST(DelayTransformTest, CloneCarriesSampleTimes) {
    DelayTransform tf(1.0);
    double t = 0.0;
    bool first = true;
    (void)applied_delays(tf, t, first, repeat(0.1, 20));

    std::unique_ptr<ITransform> copy(tf.clone());
    for (int i = 0; i < 10; ++i) {
        t += 0.5;
        const double y_orig = tf.apply(t, 0.5);
        const double y_copy = copy->apply(t, 0.5);
        EXPECT_EQ(y_orig, y_copy);
        EXPECT_LE(std::abs((t - y_copy) - 1.0), 0.25 + 1e-9);
    }
}

// Reset drops the stored history: the next output is the next input, and the
// delay is correct again once delay_sec of new history has accumulated.
TEST(DelayTransformTest, ResetClearsHistory) {
    DelayTransform tf(1.0);
    double t = 0.0;
    bool first = true;
    (void)applied_delays(tf, t, first, repeat(0.5, 10));
    tf.reset();
    t = 0.0;
    first = true;
    const auto delays = applied_delays(tf, t, first, repeat(0.1, 30));
    EXPECT_NEAR(delays[0], 0.0, 1e-12);  // first output after reset is the first input
    EXPECT_NEAR(delays.back(), 1.0, 1e-9);
}

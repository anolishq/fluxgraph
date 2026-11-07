#pragma once

#include <cmath>
#include <cstddef>
#include <deque>
#include <stdexcept>

#include "fluxgraph/transform/interface.hpp"

namespace fluxgraph {

/// Time delay: y(t) = x(t - delay_sec), sampled at the times apply() was called.
///
/// Each call advances the transform's clock by `dt` (the first call after
/// construction or reset() is t = 0) and stores the input with that time. The
/// output is the stored input whose time is nearest to t - delay_sec, excluding
/// the current call's input (except on the first call after construction or
/// reset(), when that input is the only one stored and is returned). Samples
/// older than the one returned are dropped,
/// so the applied delay follows delay_sec when dt changes. Until t reaches
/// delay_sec (and, on a tie, for one call after) the output is the first input.
///
/// A tie goes to the older sample. Two candidates count as tied when their
/// distances to t - delay_sec differ by less than 1e-9 of their spacing, so a
/// delay meant to fall halfway between samples is treated as a half even when
/// floating-point rounding puts it a hair to one side.
///
/// With a constant dt the delay is therefore N calls: delay_sec / dt rounded to
/// the nearest integer with halves rounding up, minimum 1. This is
/// max(1, llround(delay_sec / dt)) except where the floating-point quotient
/// lands within 1e-9 below n + 0.5: 0.15 / 0.1 evaluates to 1.4999999999999998,
/// llround gives 1, and N here is 2.
///
/// The clock is a compensated (two-double) sum and sample ages are taken
/// relative to the current time, so the decision does not drift as the clock
/// grows over a long run.
class DelayTransform : public ITransform {
public:
    /// @param delay_sec Delay time in seconds; <= 0 passes the input through.
    explicit DelayTransform(double delay_sec) : delay_sec_(delay_sec) {}

    /// @throws std::runtime_error if dt is not positive and finite (Engine::tick
    /// rejects dt <= 0 the same way). The transform's state is left unchanged.
    double apply(double input, double dt) override {
        if (!(dt > 0.0) || !std::isfinite(dt)) {
            throw std::runtime_error("DelayTransform: dt must be positive and finite");
        }
        if (delay_sec_ <= 0.0) {
            return input;  // No delay
        }

        if (!buffer_.empty()) {
            now_.add(dt);
        }
        buffer_.push_back(Sample{now_, input});

        // Advance past samples while the next one is closer to the target time
        // t - delay_sec. The newest sample (this call's input) is never a
        // candidate, so the delay is at least one call.
        while (buffer_.size() > 2) {
            const double older_age = now_.minus(buffer_[0].time);
            const double newer_age = now_.minus(buffer_[1].time);
            const double older_distance = older_age - delay_sec_;  // older is before the target
            const double newer_distance = delay_sec_ - newer_age;  // newer is after it when negative
            const double tolerance = 1e-9 * (older_age - newer_age);
            if (newer_distance < older_distance - tolerance) {
                buffer_.pop_front();
            } else {
                break;
            }
        }

        return buffer_.front().value;
    }

    void reset() override {
        buffer_.clear();
        now_ = Clock{};
    }

    ITransform *clone() const override {
        auto *copy = new DelayTransform(delay_sec_);
        copy->buffer_ = buffer_;
        copy->now_ = now_;
        return copy;
    }

private:
    /// Time as an unevaluated sum hi + lo, accumulated with an error-free
    /// two-sum, so it carries the exact sum of the dt values to well below the
    /// rounding of a plain double.
    struct Clock {
        double hi = 0.0;
        double lo = 0.0;

        void add(double dt) {
            const double sum = hi + dt;
            const double dt_part = sum - hi;
            const double error = (hi - (sum - dt_part)) + (dt - dt_part);
            const double lo_sum = lo + error;
            hi = sum + lo_sum;
            lo = lo_sum - (hi - sum);
        }

        /// this - other, for an earlier time `other`.
        double minus(const Clock &other) const { return (hi - other.hi) + (lo - other.lo); }
    };

    struct Sample {
        Clock time;
        double value;
    };

    double delay_sec_;
    std::deque<Sample> buffer_;
    Clock now_;  // Clock time of the newest sample in buffer_
};

}  // namespace fluxgraph

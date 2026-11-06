#pragma once

#include <cstddef>
#include <deque>
#include <stdexcept>

#include "fluxgraph/transform/interface.hpp"

namespace fluxgraph {

/// Time delay: y(t) = x(t - delay_sec), sampled at the times apply() was called.
///
/// Each call advances the transform's clock by `dt` (the first call after
/// construction or reset() is t = 0) and stores the input with that time. The
/// output is the stored input whose time is nearest to t - delay_sec, never the
/// input of the current call; a tie goes to the older sample. Before t reaches
/// delay_sec the output is the first input. Samples older than the one returned
/// are dropped, so the applied delay follows delay_sec when dt changes.
///
/// With a constant dt this is the input from N calls earlier,
/// N = max(1, llround(delay_sec / dt)).
class DelayTransform : public ITransform {
public:
    /// @param delay_sec Delay time in seconds; <= 0 passes the input through.
    explicit DelayTransform(double delay_sec) : delay_sec_(delay_sec) {}

    /// @throws std::runtime_error if dt <= 0, as Engine::tick does.
    double apply(double input, double dt) override {
        if (dt <= 0.0) {
            throw std::runtime_error("DelayTransform: dt must be positive");
        }
        if (delay_sec_ <= 0.0) {
            return input;  // No delay
        }

        if (!buffer_.empty()) {
            now_ += dt;
        }
        buffer_.push_back(Sample{now_, input});

        // Advance past samples while the next one is closer to the target time.
        // The newest sample (this call's input) is never a candidate, so the
        // delay is at least one call.
        const double target = now_ - delay_sec_;
        while (buffer_.size() > 2) {
            const Sample &older = buffer_[0];
            const Sample &newer = buffer_[1];
            // Relative tolerance so a tie that differs only by rounding in the
            // accumulated clock resolves to the older sample.
            const double tolerance = 1e-9 * (newer.time - older.time);
            if (newer.time - target < target - older.time - tolerance) {
                buffer_.pop_front();
            } else {
                break;
            }
        }

        return buffer_.front().value;
    }

    void reset() override {
        buffer_.clear();
        now_ = 0.0;
    }

    ITransform *clone() const override {
        auto *copy = new DelayTransform(delay_sec_);
        copy->buffer_ = buffer_;
        copy->now_ = now_;
        return copy;
    }

private:
    struct Sample {
        double time;
        double value;
    };

    double delay_sec_;
    std::deque<Sample> buffer_;
    double now_ = 0.0;  // Clock time of the newest sample in buffer_
};

}  // namespace fluxgraph

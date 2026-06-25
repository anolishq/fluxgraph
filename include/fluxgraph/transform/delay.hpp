#pragma once

#include <cmath>
#include <cstddef>
#include <deque>

#include "fluxgraph/transform/interface.hpp"

namespace fluxgraph {

/// Time delay using ring buffer: y(t) = x(t - delay_sec)
class DelayTransform : public ITransform {
public:
    /// @param delay_sec Delay time in seconds
    explicit DelayTransform(double delay_sec) : delay_sec_(delay_sec), buffer_(), time_accumulated_(0.0) {}

    double apply(double input, double dt) override {
        if (delay_sec_ <= 0.0) {
            return input;  // No delay
        }

        // Compute required buffer size (samples needed for delay)
        size_t required_samples = static_cast<size_t>(std::llround(delay_sec_ / dt));
        if (required_samples == 0) {
            required_samples = 1;
        }

        // Add new sample to  buffer
        buffer_.push_back(input);

        // Return oldest sample if buffer is full, otherwise return first input
        if (buffer_.size() > required_samples) {
            double output = buffer_.front();
            buffer_.pop_front();
            return output;
        }

        return buffer_.front();
    }

    void reset() override {
        buffer_.clear();
        time_accumulated_ = 0.0;
    }

    ITransform *clone() const override {
        auto *copy = new DelayTransform(delay_sec_);
        copy->buffer_ = buffer_;
        copy->time_accumulated_ = time_accumulated_;
        return copy;
    }

private:
    double delay_sec_;
    std::deque<double> buffer_;
    double time_accumulated_;
};

}  // namespace fluxgraph

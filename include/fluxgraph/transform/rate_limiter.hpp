#pragma once

#include <algorithm>
#include <cmath>

#include "fluxgraph/transform/interface.hpp"

namespace fluxgraph {

/// Rate limiter: limits dy/dt to max_rate_per_sec
class RateLimiterTransform : public ITransform {
public:
    /// @param max_rate_per_sec Maximum rate of change per second
    explicit RateLimiterTransform(double max_rate_per_sec)
        : max_rate_(max_rate_per_sec), last_output_(0.0), initialized_(false) {}

    double apply(double input, double dt) override {
        if (!initialized_) {
            last_output_ = input;
            initialized_ = true;
            return last_output_;
        }

        if (max_rate_ <= 0.0 || dt <= 0.0) {
            last_output_ = input;
            return last_output_;
        }

        double max_change = max_rate_ * dt;
        double delta = input - last_output_;

        // Clamp delta to [-max_change, +max_change]
        delta = std::clamp(delta, -max_change, max_change);

        last_output_ += delta;
        return last_output_;
    }

    void reset() override {
        last_output_ = 0.0;
        initialized_ = false;
    }

    ITransform *clone() const override {
        auto *copy = new RateLimiterTransform(max_rate_);
        copy->last_output_ = last_output_;
        copy->initialized_ = initialized_;
        return copy;
    }

private:
    double max_rate_;
    double last_output_;
    bool initialized_;
};

}  // namespace fluxgraph

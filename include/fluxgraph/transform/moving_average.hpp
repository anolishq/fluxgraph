#pragma once

#include <deque>
#include <numeric>

#include "fluxgraph/transform/interface.hpp"

namespace fluxgraph {

/// Moving average: y = mean(x[t-N+1]...x[t])
class MovingAverageTransform : public ITransform {
public:
    explicit MovingAverageTransform(size_t window_size) : window_size_(window_size), samples_() {}

    double apply(double input, double dt) override {
        (void)dt;  // Unused

        samples_.push_back(input);

        // Remove old samples if window is full
        if (samples_.size() > window_size_) {
            samples_.pop_front();
        }

        // Compute average
        if (samples_.empty()) {
            return 0.0;
        }

        double sum = std::accumulate(samples_.begin(), samples_.end(), 0.0);
        return sum / static_cast<double>(samples_.size());
    }

    void reset() override { samples_.clear(); }

    ITransform *clone() const override {
        auto *copy = new MovingAverageTransform(window_size_);
        copy->samples_ = samples_;
        return copy;
    }

private:
    size_t window_size_;
    std::deque<double> samples_;
};

}  // namespace fluxgraph

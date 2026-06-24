#pragma once

#include <cmath>

#include "fluxgraph/transform/interface.hpp"

namespace fluxgraph {

/// Deadband: y = 0 if |x| < threshold, else y = x
class DeadbandTransform : public ITransform {
public:
    explicit DeadbandTransform(double threshold) : threshold_(threshold) {}

    double apply(double input, double dt) override {
        (void)dt;  // Unused
        if (std::abs(input) < threshold_) {
            return 0.0;
        }
        return input;
    }

    void reset() override {
        // No state to reset
    }

    ITransform *clone() const override { return new DeadbandTransform(threshold_); }

private:
    double threshold_;
};

}  // namespace fluxgraph

#pragma once

#include <algorithm>

#include "fluxgraph/transform/interface.hpp"

namespace fluxgraph {

/// Saturation (clipping): y = clamp(x, min, max)
class SaturationTransform : public ITransform {
public:
    SaturationTransform(double min_value, double max_value) : min_(min_value), max_(max_value) {}

    double apply(double input, double dt) override {
        (void)dt;  // Unused
        return std::clamp(input, min_, max_);
    }

    void reset() override {
        // No state to reset
    }

    ITransform *clone() const override { return new SaturationTransform(min_, max_); }

private:
    double min_;
    double max_;
};

}  // namespace fluxgraph

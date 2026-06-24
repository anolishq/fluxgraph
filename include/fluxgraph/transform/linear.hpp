#pragma once

#include <algorithm>
#include <limits>

#include "fluxgraph/transform/interface.hpp"

namespace fluxgraph {

/// Linear scaling and offset: y = scale * x + offset
/// Optional clamping to [clamp_min, clamp_max]
class LinearTransform : public ITransform {
public:
    LinearTransform(double scale, double offset, double clamp_min = -std::numeric_limits<double>::infinity(),
                    double clamp_max = std::numeric_limits<double>::infinity())
        : scale_(scale), offset_(offset), clamp_min_(clamp_min), clamp_max_(clamp_max) {}

    double apply(double input, double dt) override {
        (void)dt;  // Unused for linear transform
        double result = scale_ * input + offset_;
        return std::clamp(result, clamp_min_, clamp_max_);
    }

    void reset() override {
        // No state to reset
    }

    ITransform *clone() const override { return new LinearTransform(scale_, offset_, clamp_min_, clamp_max_); }

private:
    double scale_;
    double offset_;
    double clamp_min_;
    double clamp_max_;
};

}  // namespace fluxgraph

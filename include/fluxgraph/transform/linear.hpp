#pragma once

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

#include "fluxgraph/transform/interface.hpp"

namespace fluxgraph {

/// Linear scaling and offset: y = scale * x + offset
/// Optional clamping to [clamp_min, clamp_max]
class LinearTransform : public ITransform {
public:
    /// @throws std::invalid_argument if a clamp bound is NaN or clamp_min > clamp_max
    /// (std::clamp is undefined for inverted bounds). Equal bounds are allowed.
    LinearTransform(double scale, double offset, double clamp_min = -std::numeric_limits<double>::infinity(),
                    double clamp_max = std::numeric_limits<double>::infinity())
        : scale_(scale), offset_(offset), clamp_min_(clamp_min), clamp_max_(clamp_max) {
        if (std::isnan(clamp_min) || std::isnan(clamp_max)) {
            throw std::invalid_argument("LinearTransform: clamp_min and clamp_max must not be NaN");
        }
        if (clamp_min > clamp_max) {
            throw std::invalid_argument("LinearTransform: clamp_min must be <= clamp_max");
        }
    }

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

#pragma once

#include <algorithm>
#include <cmath>
#include <stdexcept>

#include "fluxgraph/transform/interface.hpp"

namespace fluxgraph {

/// Saturation (clipping): y = clamp(x, min, max)
class SaturationTransform : public ITransform {
public:
    /// @throws std::invalid_argument if a bound is NaN or min_value > max_value
    /// (std::clamp is undefined for inverted bounds). Equal bounds are allowed.
    SaturationTransform(double min_value, double max_value) : min_(min_value), max_(max_value) {
        if (std::isnan(min_value) || std::isnan(max_value)) {
            throw std::invalid_argument("SaturationTransform: min_value and max_value must not be NaN");
        }
        if (min_value > max_value) {
            throw std::invalid_argument("SaturationTransform: min_value must be <= max_value");
        }
    }

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

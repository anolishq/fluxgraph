#pragma once

#include <cmath>

#include "fluxgraph/transform/interface.hpp"

namespace fluxgraph {

/// First-order lag (low-pass filter): dy/dt = (x - y) / tau
/// Exponential approach to input with time constant tau_s
class FirstOrderLagTransform : public ITransform {
public:
    /// @param tau_s Time constant in seconds
    explicit FirstOrderLagTransform(double tau_s) : tau_s_(tau_s), output_(0.0), initialized_(false) {}

    double apply(double input, double dt) override {
        if (!initialized_) {
            output_ = input;
            initialized_ = true;
            return output_;
        }

        if (tau_s_ <= 0.0) {
            output_ = input;  // No filtering if tau <= 0
            return output_;
        }

        // Exponential smoothing: y(t+dt) = y(t) + (x - y(t)) * (1 - e^(-dt/tau))
        double alpha = 1.0 - std::exp(-dt / tau_s_);
        output_ += alpha * (input - output_);
        return output_;
    }

    void reset() override {
        output_ = 0.0;
        initialized_ = false;
    }

    ITransform *clone() const override {
        auto *copy = new FirstOrderLagTransform(tau_s_);
        copy->output_ = output_;
        copy->initialized_ = initialized_;
        return copy;
    }

private:
    double tau_s_;
    double output_;
    bool initialized_;
};

}  // namespace fluxgraph

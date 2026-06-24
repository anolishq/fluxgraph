#pragma once

#include <random>

#include "fluxgraph/transform/interface.hpp"

namespace fluxgraph {

/// Additive Gaussian noise: y = x + N(0, amplitude)
/// Deterministic via explicit seed
class NoiseTransform : public ITransform {
public:
    /// @param amplitude Noise amplitude (not stddev)
    /// @param seed Random seed for deterministic behavior
    NoiseTransform(double amplitude, uint32_t seed)
        : amplitude_(amplitude),
          seed_(seed),
          rng_(seed),
          dist_(0.0, amplitude > 0.0 ? amplitude : 1.0) {}  // Avoid zero stddev

    double apply(double input, double dt) override {
        (void)dt;  // Unused
        if (amplitude_ <= 0.0) {
            return input;  // No noise
        }
        return input + dist_(rng_);
    }

    void reset() override {
        rng_.seed(seed_);  // Reset to initial seed
        dist_.reset();
    }

    ITransform *clone() const override {
        auto *copy = new NoiseTransform(amplitude_, seed_);
        copy->rng_ = rng_;  // Copy RNG state
        return copy;
    }

private:
    double amplitude_;
    uint32_t seed_;
    std::mt19937 rng_;
    std::normal_distribution<double> dist_;
};

}  // namespace fluxgraph

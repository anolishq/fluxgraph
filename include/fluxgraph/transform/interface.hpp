#pragma once

namespace fluxgraph {

/// Base interface for all signal transforms
/// Transforms are stateful and process signals over time
class ITransform {
public:
    virtual ~ITransform() = default;

    /// Apply transform to input value
    /// @param input Current input value
    /// @param dt Time step in seconds
    /// @return Transformed output value
    virtual double apply(double input, double dt) = 0;

    /// Reset internal state to initial conditions
    virtual void reset() = 0;

    /// Create a deep copy of this transform (including state)
    virtual ITransform *clone() const = 0;
};

}  // namespace fluxgraph

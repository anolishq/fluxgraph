#pragma once

#include "fluxgraph/core/signal_store.hpp"
#include <string>
#include <vector>

namespace fluxgraph {

/// Base interface for physics simulation models
/// Models update signal values based on differential equations
class IModel {
public:
  virtual ~IModel() = default;

  /// Advance model simulation by dt seconds
  /// @param dt Time step in seconds
  /// @param store Signal storage for reading inputs and writing outputs
  virtual void tick(double dt, SignalStore &store) = 0;

  /// Reset model to initial conditions
  virtual void reset() = 0;

  /// Compute maximum stable time step for this model
  /// Based on Forward Euler stability criteria
  /// @return Maximum safe dt in seconds
  virtual double compute_stability_limit() const = 0;

  /// Get human-readable description of model
  virtual std::string describe() const = 0;

  /// Return all signals written by this model during tick().
  /// Used by compile-time ownership checks to enforce single-writer semantics.
  virtual std::vector<SignalId> output_signal_ids() const = 0;
};

} // namespace fluxgraph

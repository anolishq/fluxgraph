#pragma once

#include "fluxgraph/core/types.hpp"
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace fluxgraph {

/// Represents a signal with its value and unit metadata
struct Signal {
  double value = 0.0;
  std::string unit = "dimensionless";

  Signal() = default;
  Signal(double v, const std::string &u = "dimensionless")
      : value(v), unit(u) {}
};

/// Central storage for all signal values and metadata
/// Single-writer by design - no internal synchronization
class SignalStore {
public:
  SignalStore();
  ~SignalStore();

  /// Write a signal value with unit metadata
  void write(SignalId id, double value,
             const std::string &unit = "dimensionless");

  /// Write value to target signal using unit metadata from source signal.
  /// Falls back to "dimensionless" when source is invalid/unwritten.
  void write_with_source_unit(SignalId target, double value, SignalId source);

  /// Write a value using the target signal contract unit when available.
  /// This is used for internal edge propagation to avoid source-unit copying.
  void write_with_contract_unit(SignalId id, double value);

  /// Read a signal (value + unit)
  Signal read(SignalId id) const;

  /// Read only the value (convenience method)
  double read_value(SignalId id) const;

  /// Read only the unit (convenience method)
  const std::string &read_unit(SignalId id) const;

  /// Check if a signal is driven by physics simulation
  bool is_physics_driven(SignalId id) const;

  /// Mark a signal as physics-driven (set by graph compilation)
  void mark_physics_driven(SignalId id, bool driven);

  /// Declare expected unit for a signal (enforced on write)
  void declare_unit(SignalId id, const std::string &expected_unit);

  /// Validate that a unit matches the declared unit for a signal
  /// Throws std::runtime_error if mismatch
  void validate_unit(SignalId id, const std::string &unit) const;

  bool has_declared_unit(SignalId id) const;
  const std::string &declared_unit(SignalId id) const;

  /// Pre-allocate storage for signals (optimization)
  void reserve(size_t max_signals);

  /// Get current preallocated slot count
  size_t capacity() const;

  /// Get number of signals currently stored
  size_t size() const;

  /// Clear all signals
  void clear();

private:
  void ensure_index(SignalId id);
  static const std::string &dimensionless_unit();

  std::vector<Signal> signals_;
  std::vector<uint8_t> has_signal_;
  std::vector<uint8_t> physics_driven_;
  std::vector<std::string> declared_units_;
  std::vector<uint8_t> has_declared_unit_;
  size_t signal_count_ = 0;
};

} // namespace fluxgraph

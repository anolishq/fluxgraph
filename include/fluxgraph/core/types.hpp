#pragma once

#include <cstdint>
#include <string>
#include <variant>

namespace fluxgraph {

/// Unique identifier for a signal in the graph
using SignalId = uint32_t;

/// Unique identifier for a device
using DeviceId = uint32_t;

/// Unique identifier for a function/command
using FunctionId = uint32_t;

/// Sentinel value for invalid signal ID
constexpr SignalId INVALID_SIGNAL = 0xFFFFFFFF;

/// Sentinel value for invalid device ID
constexpr DeviceId INVALID_DEVICE = 0xFFFFFFFF;

/// Sentinel value for invalid function ID
constexpr FunctionId INVALID_FUNCTION = 0xFFFFFFFF;

/// Unit kind classification for dimensional validation and conversion rules.
enum class UnitKind : uint8_t {
  generic = 0,
  absolute_temp = 1,
  delta_temp = 2,
};

/// Fixed base-dimension exponent vector (M, L, T, I, Theta, N, J).
struct DimensionVector {
  int8_t m = 0;
  int8_t l = 0;
  int8_t t = 0;
  int8_t i = 0;
  int8_t theta = 0;
  int8_t n = 0;
  int8_t j = 0;

  bool operator==(const DimensionVector &other) const {
    return m == other.m && l == other.l && t == other.t && i == other.i &&
           theta == other.theta && n == other.n && j == other.j;
  }

  bool operator!=(const DimensionVector &other) const {
    return !(*this == other);
  }
};

/// Canonical unit definition used by the unit registry.
struct UnitDef {
  std::string symbol;
  DimensionVector dimension;
  double scale_to_si = 1.0;
  double offset_to_si = 0.0;
  UnitKind kind = UnitKind::generic;
};

/// Conversion coefficients where y = x * scale + offset.
struct UnitConversion {
  double scale = 1.0;
  double offset = 0.0;
};

/// Variant type for command arguments and signal values
using Variant = std::variant<double, int64_t, bool, std::string>;

} // namespace fluxgraph

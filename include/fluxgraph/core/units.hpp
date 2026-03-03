#pragma once

#include "fluxgraph/core/types.hpp"
#include <string>
#include <string_view>
#include <unordered_map>

namespace fluxgraph {

/// Curated unit registry with dimensional and conversion semantics.
class UnitRegistry {
public:
  static const UnitRegistry &instance();

  const UnitDef *find(std::string_view symbol) const;
  bool contains(std::string_view symbol) const;

  /// Resolve conversion from `from_symbol` to `to_symbol`.
  /// Throws std::runtime_error when units are missing or incompatible.
  UnitConversion resolve_conversion(const std::string &from_symbol,
                                    const std::string &to_symbol) const;

  /// Returns true when both symbols exist and share the same dimension vector.
  bool are_dimensionally_compatible(const std::string &lhs_symbol,
                                    const std::string &rhs_symbol) const;

private:
  UnitRegistry();

  std::unordered_map<std::string, UnitDef> units_;
};

} // namespace fluxgraph

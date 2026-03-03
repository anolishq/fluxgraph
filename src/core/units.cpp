#include "fluxgraph/core/units.hpp"
#include <stdexcept>

namespace fluxgraph {

namespace {

bool is_temperature_kind(UnitKind kind) {
  return kind == UnitKind::absolute_temp || kind == UnitKind::delta_temp;
}

} // namespace

UnitRegistry::UnitRegistry() {
  auto dim = [](int m, int l, int t, int i, int theta, int n, int j) {
    DimensionVector v;
    v.m = static_cast<int8_t>(m);
    v.l = static_cast<int8_t>(l);
    v.t = static_cast<int8_t>(t);
    v.i = static_cast<int8_t>(i);
    v.theta = static_cast<int8_t>(theta);
    v.n = static_cast<int8_t>(n);
    v.j = static_cast<int8_t>(j);
    return v;
  };

  units_.emplace("dimensionless", UnitDef{"dimensionless", {}, 1.0, 0.0,
                                          UnitKind::generic});
  units_.emplace("W", UnitDef{"W", dim(1, 2, -3, 0, 0, 0, 0), 1.0, 0.0,
                              UnitKind::generic});
  units_.emplace("K", UnitDef{"K", dim(0, 0, 0, 0, 1, 0, 0), 1.0, 0.0,
                              UnitKind::absolute_temp});
  units_.emplace("degC",
                 UnitDef{"degC", dim(0, 0, 0, 0, 1, 0, 0), 1.0, 273.15,
                                 UnitKind::absolute_temp});
  units_.emplace("delta_K",
                 UnitDef{"delta_K", dim(0, 0, 0, 0, 1, 0, 0), 1.0, 0.0,
                         UnitKind::delta_temp});
  units_.emplace("delta_degC",
                 UnitDef{"delta_degC", dim(0, 0, 0, 0, 1, 0, 0), 1.0, 0.0,
                         UnitKind::delta_temp});
  units_.emplace("J/K", UnitDef{"J/K", dim(1, 2, -2, 0, -1, 0, 0), 1.0, 0.0,
                                UnitKind::generic});
  units_.emplace("W/K", UnitDef{"W/K", dim(1, 2, -3, 0, -1, 0, 0), 1.0, 0.0,
                                UnitKind::generic});
}

const UnitRegistry &UnitRegistry::instance() {
  static const UnitRegistry kInstance;
  return kInstance;
}

const UnitDef *UnitRegistry::find(std::string_view symbol) const {
  const auto it = units_.find(std::string(symbol));
  if (it == units_.end()) {
    return nullptr;
  }
  return &it->second;
}

bool UnitRegistry::contains(std::string_view symbol) const {
  return find(symbol) != nullptr;
}

bool UnitRegistry::are_dimensionally_compatible(
    const std::string &lhs_symbol, const std::string &rhs_symbol) const {
  const UnitDef *lhs = find(lhs_symbol);
  const UnitDef *rhs = find(rhs_symbol);
  return lhs != nullptr && rhs != nullptr && lhs->dimension == rhs->dimension;
}

UnitConversion UnitRegistry::resolve_conversion(
    const std::string &from_symbol, const std::string &to_symbol) const {
  const UnitDef *from = find(from_symbol);
  if (from == nullptr) {
    throw std::runtime_error("Unknown unit symbol: '" + from_symbol + "'");
  }

  const UnitDef *to = find(to_symbol);
  if (to == nullptr) {
    throw std::runtime_error("Unknown unit symbol: '" + to_symbol + "'");
  }

  if (from->dimension != to->dimension) {
    throw std::runtime_error("Incompatible unit dimensions: '" + from_symbol +
                             "' -> '" + to_symbol + "'");
  }

  if (is_temperature_kind(from->kind) != is_temperature_kind(to->kind)) {
    throw std::runtime_error("Incompatible unit kinds: '" + from_symbol +
                             "' -> '" + to_symbol + "'");
  }

  if ((from->kind == UnitKind::absolute_temp &&
       to->kind == UnitKind::delta_temp) ||
      (from->kind == UnitKind::delta_temp &&
       to->kind == UnitKind::absolute_temp)) {
    throw std::runtime_error("Disallowed absolute/delta temperature conversion: '" +
                             from_symbol + "' -> '" + to_symbol + "'");
  }

  UnitConversion conversion;
  conversion.scale = from->scale_to_si / to->scale_to_si;
  conversion.offset = (from->offset_to_si - to->offset_to_si) / to->scale_to_si;
  return conversion;
}

} // namespace fluxgraph

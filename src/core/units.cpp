#include "fluxgraph/core/units.hpp"

#include <stdexcept>
#include <unordered_map>

namespace fluxgraph {

namespace {

bool is_temperature_kind(UnitKind kind) { return kind == UnitKind::absolute_temp || kind == UnitKind::delta_temp; }

DimensionVector dim(int m, int l, int t, int i, int theta, int n, int j) {
    DimensionVector v{};
    v.m = static_cast<int8_t>(m);
    v.l = static_cast<int8_t>(l);
    v.t = static_cast<int8_t>(t);
    v.i = static_cast<int8_t>(i);
    v.theta = static_cast<int8_t>(theta);
    v.n = static_cast<int8_t>(n);
    v.j = static_cast<int8_t>(j);
    return v;
}

void add_unit(std::unordered_map<std::string, UnitDef> &units, const std::string &symbol,
              const DimensionVector &dimension, UnitKind kind = UnitKind::generic, double scale_to_si = 1.0,
              double offset_to_si = 0.0) {
    units.emplace(symbol, UnitDef{symbol, dimension, scale_to_si, offset_to_si, kind});
}

void register_base_time_units(std::unordered_map<std::string, UnitDef> &units) {
    add_unit(units, "dimensionless", {});
    add_unit(units, "rad", {});
    add_unit(units, "s", dim(0, 0, 1, 0, 0, 0, 0));
    add_unit(units, "1/s", dim(0, 0, -1, 0, 0, 0, 0));
    add_unit(units, "rad/s", dim(0, 0, -1, 0, 0, 0, 0));
}

void register_mechanical_units(std::unordered_map<std::string, UnitDef> &units) {
    add_unit(units, "m", dim(0, 1, 0, 0, 0, 0, 0));
    add_unit(units, "m/s", dim(0, 1, -1, 0, 0, 0, 0));
    add_unit(units, "kg", dim(1, 0, 0, 0, 0, 0, 0));
    add_unit(units, "kg*m^2", dim(1, 2, 0, 0, 0, 0, 0));
    add_unit(units, "N", dim(1, 1, -2, 0, 0, 0, 0));
    add_unit(units, "N/m", dim(1, 0, -2, 0, 0, 0, 0));
    add_unit(units, "N*s/m", dim(1, 0, -1, 0, 0, 0, 0));
    add_unit(units, "N*m", dim(1, 2, -2, 0, 0, 0, 0));
    add_unit(units, "N*m*s/rad", dim(1, 2, -1, 0, 0, 0, 0));
}

void register_electrical_rotational_units(std::unordered_map<std::string, UnitDef> &units) {
    add_unit(units, "A", dim(0, 0, 0, 1, 0, 0, 0));
    add_unit(units, "V", dim(1, 2, -3, -1, 0, 0, 0));
    add_unit(units, "Ohm", dim(1, 2, -3, -2, 0, 0, 0));
    add_unit(units, "H", dim(1, 2, -2, -2, 0, 0, 0));
    add_unit(units, "N*m/A", dim(1, 2, -2, -1, 0, 0, 0));
    add_unit(units, "V*s/rad", dim(1, 2, -2, -1, 0, 0, 0));
    add_unit(units, "W", dim(1, 2, -3, 0, 0, 0, 0));
}

void register_thermal_units(std::unordered_map<std::string, UnitDef> &units) {
    add_unit(units, "K", dim(0, 0, 0, 0, 1, 0, 0), UnitKind::absolute_temp);
    add_unit(units, "degC", dim(0, 0, 0, 0, 1, 0, 0), UnitKind::absolute_temp, 1.0, 273.15);
    add_unit(units, "delta_K", dim(0, 0, 0, 0, 1, 0, 0), UnitKind::delta_temp);
    add_unit(units, "delta_degC", dim(0, 0, 0, 0, 1, 0, 0), UnitKind::delta_temp);
    add_unit(units, "J/K", dim(1, 2, -2, 0, -1, 0, 0));
    add_unit(units, "W/K", dim(1, 2, -3, 0, -1, 0, 0));
}

}  // namespace

UnitRegistry::UnitRegistry() {
    register_base_time_units(units_);
    register_mechanical_units(units_);
    register_electrical_rotational_units(units_);
    register_thermal_units(units_);
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

bool UnitRegistry::contains(std::string_view symbol) const { return find(symbol) != nullptr; }

bool UnitRegistry::are_dimensionally_compatible(const std::string &lhs_symbol, const std::string &rhs_symbol) const {
    const UnitDef *lhs = find(lhs_symbol);
    const UnitDef *rhs = find(rhs_symbol);
    return lhs != nullptr && rhs != nullptr && lhs->dimension == rhs->dimension;
}

UnitConversion UnitRegistry::resolve_conversion(const std::string &from_symbol, const std::string &to_symbol) const {
    const UnitDef *from = find(from_symbol);
    if (from == nullptr) {
        throw std::runtime_error("Unknown unit symbol: '" + from_symbol + "'");
    }

    const UnitDef *to = find(to_symbol);
    if (to == nullptr) {
        throw std::runtime_error("Unknown unit symbol: '" + to_symbol + "'");
    }

    if (from->dimension != to->dimension) {
        throw std::runtime_error("Incompatible unit dimensions: '" + from_symbol + "' -> '" + to_symbol + "'");
    }

    if (is_temperature_kind(from->kind) != is_temperature_kind(to->kind)) {
        throw std::runtime_error("Incompatible unit kinds: '" + from_symbol + "' -> '" + to_symbol + "'");
    }

    if ((from->kind == UnitKind::absolute_temp && to->kind == UnitKind::delta_temp) ||
        (from->kind == UnitKind::delta_temp && to->kind == UnitKind::absolute_temp)) {
        throw std::runtime_error("Disallowed absolute/delta temperature conversion: '" + from_symbol + "' -> '" +
                                 to_symbol + "'");
    }

    UnitConversion conversion;
    conversion.scale = from->scale_to_si / to->scale_to_si;
    conversion.offset = (from->offset_to_si - to->offset_to_si) / to->scale_to_si;
    return conversion;
}

}  // namespace fluxgraph

#pragma once

#include "fluxgraph/model/thermal_integration.hpp"

namespace fluxgraph {

/// Generic ODE integration method selection.
///
/// This is the preferred name for new model code; `ThermalIntegrationMethod`
/// remains available for backwards compatibility.
using IntegrationMethod = ThermalIntegrationMethod;

inline IntegrationMethod parse_integration_method(const std::string &method) {
    return parse_thermal_integration_method(method);
}

}  // namespace fluxgraph

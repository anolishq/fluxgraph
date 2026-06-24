#pragma once

#include <string>

namespace fluxgraph {

enum class ThermalIntegrationMethod {
    ForwardEuler,
    Rk4,
};

// Negative real-axis stability limit for classic RK4.
// See docs/numerical-methods.md for the derivation/interpretation used here.
constexpr double kRk4NegativeRealAxisStabilityLimit = 2.785293563405282;

const char *to_string(ThermalIntegrationMethod method);
ThermalIntegrationMethod parse_thermal_integration_method(const std::string &method_name);

}  // namespace fluxgraph

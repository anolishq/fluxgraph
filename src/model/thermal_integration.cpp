#include "fluxgraph/model/thermal_integration.hpp"

#include <stdexcept>

namespace fluxgraph {

const char *to_string(ThermalIntegrationMethod method) {
    switch (method) {
        case ThermalIntegrationMethod::ForwardEuler:
            return "forward_euler";
        case ThermalIntegrationMethod::Rk4:
            return "rk4";
    }
    return "forward_euler";
}

ThermalIntegrationMethod parse_thermal_integration_method(const std::string &method_name) {
    if (method_name == "forward_euler") {
        return ThermalIntegrationMethod::ForwardEuler;
    }
    if (method_name == "rk4") {
        return ThermalIntegrationMethod::Rk4;
    }

    throw std::invalid_argument("Unknown thermal integration method '" + method_name +
                                "' (expected one of: forward_euler, rk4)");
}

}  // namespace fluxgraph

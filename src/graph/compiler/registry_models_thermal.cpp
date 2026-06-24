#include <stdexcept>

#include "common.hpp"
#include "fluxgraph/model/thermal_integration.hpp"
#include "fluxgraph/model/thermal_mass.hpp"
#include "fluxgraph/model/thermal_rc2.hpp"
#include "registry_builtins.hpp"

namespace fluxgraph::compiler_internal {

void register_builtin_models_thermal(FactoryRegistry &registry) {
    ModelSignature thermal_signature;
    thermal_signature.signal_param_units.emplace("power_signal", "W");
    thermal_signature.signal_param_units.emplace("ambient_signal", "degC");
    thermal_signature.signal_param_units.emplace("temp_signal", "degC");
    thermal_signature.scalar_param_signatures.emplace(
        "thermal_mass", ScalarParamSignature{"J/K", ScalarConstraint::greater_than(0.0), true});
    thermal_signature.scalar_param_signatures.emplace(
        "heat_transfer_coeff", ScalarParamSignature{"W/K", ScalarConstraint::greater_than(0.0), true});
    thermal_signature.scalar_param_signatures.emplace(
        "initial_temp", ScalarParamSignature{"degC", ScalarConstraint::finite_only(), true});

    register_builtin_model(
        registry, "thermal_mass",
        [](const ModelSpec &spec, SignalNamespace &ns) -> std::unique_ptr<IModel> {
            const std::string context = "model[" + spec.id + ":thermal_mass]";
            const std::string thermal_mass_path = context + "/thermal_mass";
            const std::string heat_transfer_coeff_path = context + "/heat_transfer_coeff";
            const std::string initial_temp_path = context + "/initial_temp";
            double thermal_mass = as_double(require_param(spec.params, "thermal_mass", context), thermal_mass_path);
            double heat_transfer_coeff =
                as_double(require_param(spec.params, "heat_transfer_coeff", context), heat_transfer_coeff_path);
            double initial_temp = as_double(require_param(spec.params, "initial_temp", context), initial_temp_path);

            require_finite_positive(thermal_mass, thermal_mass_path);
            require_finite_positive(heat_transfer_coeff, heat_transfer_coeff_path);
            require_finite(initial_temp, initial_temp_path);

            std::string temp_path =
                as_string(require_param(spec.params, "temp_signal", context), context + "/temp_signal");
            std::string power_path =
                as_string(require_param(spec.params, "power_signal", context), context + "/power_signal");
            std::string ambient_path =
                as_string(require_param(spec.params, "ambient_signal", context), context + "/ambient_signal");
            ThermalIntegrationMethod integration_method = ThermalIntegrationMethod::ForwardEuler;
            if (auto it = spec.params.find("integration_method"); it != spec.params.end()) {
                const std::string method_name = as_string(it->second, context + "/integration_method");
                try {
                    integration_method = parse_thermal_integration_method(method_name);
                } catch (const std::invalid_argument &e) {
                    throw std::runtime_error("Invalid parameter at " + context + "/integration_method: " + e.what());
                }
            }

            return std::make_unique<ThermalMassModel>(spec.id, thermal_mass, heat_transfer_coeff, initial_temp,
                                                      temp_path, power_path, ambient_path, ns, integration_method);
        },
        thermal_signature);

    ModelSignature thermal_rc2_signature;
    thermal_rc2_signature.signal_param_units.emplace("power_signal", "W");
    thermal_rc2_signature.signal_param_units.emplace("ambient_signal", "degC");
    thermal_rc2_signature.signal_param_units.emplace("temp_signal_a", "degC");
    thermal_rc2_signature.signal_param_units.emplace("temp_signal_b", "degC");

    thermal_rc2_signature.scalar_param_signatures.emplace(
        "thermal_mass_a", ScalarParamSignature{"J/K", ScalarConstraint::greater_than(0.0), true});
    thermal_rc2_signature.scalar_param_signatures.emplace(
        "thermal_mass_b", ScalarParamSignature{"J/K", ScalarConstraint::greater_than(0.0), true});
    thermal_rc2_signature.scalar_param_signatures.emplace(
        "heat_transfer_coeff_a", ScalarParamSignature{"W/K", ScalarConstraint::greater_than(0.0), true});
    thermal_rc2_signature.scalar_param_signatures.emplace(
        "heat_transfer_coeff_b", ScalarParamSignature{"W/K", ScalarConstraint::greater_than(0.0), true});
    thermal_rc2_signature.scalar_param_signatures.emplace(
        "coupling_coeff", ScalarParamSignature{"W/K", ScalarConstraint::greater_equal(0.0), true});
    thermal_rc2_signature.scalar_param_signatures.emplace(
        "initial_temp_a", ScalarParamSignature{"degC", ScalarConstraint::finite_only(), true});
    thermal_rc2_signature.scalar_param_signatures.emplace(
        "initial_temp_b", ScalarParamSignature{"degC", ScalarConstraint::finite_only(), true});

    register_builtin_model(
        registry, "thermal_rc2",
        [](const ModelSpec &spec, SignalNamespace &ns) -> std::unique_ptr<IModel> {
            const std::string context = "model[" + spec.id + ":thermal_rc2]";

            const std::string thermal_mass_a_path = context + "/thermal_mass_a";
            const std::string thermal_mass_b_path = context + "/thermal_mass_b";
            const std::string heat_transfer_coeff_a_path = context + "/heat_transfer_coeff_a";
            const std::string heat_transfer_coeff_b_path = context + "/heat_transfer_coeff_b";
            const std::string coupling_coeff_path = context + "/coupling_coeff";
            const std::string initial_temp_a_path = context + "/initial_temp_a";
            const std::string initial_temp_b_path = context + "/initial_temp_b";

            double thermal_mass_a =
                as_double(require_param(spec.params, "thermal_mass_a", context), thermal_mass_a_path);
            double thermal_mass_b =
                as_double(require_param(spec.params, "thermal_mass_b", context), thermal_mass_b_path);
            double heat_transfer_coeff_a =
                as_double(require_param(spec.params, "heat_transfer_coeff_a", context), heat_transfer_coeff_a_path);
            double heat_transfer_coeff_b =
                as_double(require_param(spec.params, "heat_transfer_coeff_b", context), heat_transfer_coeff_b_path);
            double coupling_coeff =
                as_double(require_param(spec.params, "coupling_coeff", context), coupling_coeff_path);
            double initial_temp_a =
                as_double(require_param(spec.params, "initial_temp_a", context), initial_temp_a_path);
            double initial_temp_b =
                as_double(require_param(spec.params, "initial_temp_b", context), initial_temp_b_path);

            require_finite_positive(thermal_mass_a, thermal_mass_a_path);
            require_finite_positive(thermal_mass_b, thermal_mass_b_path);
            require_finite_positive(heat_transfer_coeff_a, heat_transfer_coeff_a_path);
            require_finite_positive(heat_transfer_coeff_b, heat_transfer_coeff_b_path);
            require_finite_non_negative(coupling_coeff, coupling_coeff_path);
            require_finite(initial_temp_a, initial_temp_a_path);
            require_finite(initial_temp_b, initial_temp_b_path);

            std::string temp_a_path =
                as_string(require_param(spec.params, "temp_signal_a", context), context + "/temp_signal_a");
            std::string temp_b_path =
                as_string(require_param(spec.params, "temp_signal_b", context), context + "/temp_signal_b");
            std::string power_path =
                as_string(require_param(spec.params, "power_signal", context), context + "/power_signal");
            std::string ambient_path =
                as_string(require_param(spec.params, "ambient_signal", context), context + "/ambient_signal");

            ThermalIntegrationMethod integration_method = ThermalIntegrationMethod::ForwardEuler;
            if (auto it = spec.params.find("integration_method"); it != spec.params.end()) {
                const std::string method_name = as_string(it->second, context + "/integration_method");
                try {
                    integration_method = parse_thermal_integration_method(method_name);
                } catch (const std::invalid_argument &e) {
                    throw std::runtime_error("Invalid parameter at " + context + "/integration_method: " + e.what());
                }
            }

            return std::make_unique<ThermalRc2Model>(spec.id, thermal_mass_a, thermal_mass_b, heat_transfer_coeff_a,
                                                     heat_transfer_coeff_b, coupling_coeff, initial_temp_a,
                                                     initial_temp_b, temp_a_path, temp_b_path, power_path, ambient_path,
                                                     ns, integration_method);
        },
        thermal_rc2_signature);
}

}  // namespace fluxgraph::compiler_internal

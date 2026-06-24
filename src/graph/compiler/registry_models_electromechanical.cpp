#include <stdexcept>

#include "common.hpp"
#include "fluxgraph/model/dc_motor.hpp"
#include "fluxgraph/model/integration.hpp"
#include "registry_builtins.hpp"

namespace fluxgraph::compiler_internal {

void register_builtin_models_electromechanical(FactoryRegistry &registry) {
    ModelSignature dc_motor_signature;
    dc_motor_signature.signal_param_units.emplace("voltage_signal", "V");
    dc_motor_signature.signal_param_units.emplace("load_torque_signal", "N*m");
    dc_motor_signature.signal_param_units.emplace("speed_signal", "rad/s");
    dc_motor_signature.signal_param_units.emplace("current_signal", "A");
    dc_motor_signature.signal_param_units.emplace("torque_signal", "N*m");

    dc_motor_signature.scalar_param_signatures.emplace(
        "resistance_ohm", ScalarParamSignature{"Ohm", ScalarConstraint::greater_than(0.0), true});
    dc_motor_signature.scalar_param_signatures.emplace(
        "inductance_h", ScalarParamSignature{"H", ScalarConstraint::greater_than(0.0), true});
    dc_motor_signature.scalar_param_signatures.emplace(
        "torque_constant", ScalarParamSignature{"N*m/A", ScalarConstraint::greater_than(0.0), true});
    dc_motor_signature.scalar_param_signatures.emplace(
        "back_emf_constant", ScalarParamSignature{"V*s/rad", ScalarConstraint::greater_than(0.0), true});
    dc_motor_signature.scalar_param_signatures.emplace(
        "inertia", ScalarParamSignature{"kg*m^2", ScalarConstraint::greater_than(0.0), true});
    dc_motor_signature.scalar_param_signatures.emplace(
        "viscous_friction", ScalarParamSignature{"N*m*s/rad", ScalarConstraint::greater_equal(0.0), true});
    dc_motor_signature.scalar_param_signatures.emplace(
        "initial_current", ScalarParamSignature{"A", ScalarConstraint::finite_only(), true});
    dc_motor_signature.scalar_param_signatures.emplace(
        "initial_speed", ScalarParamSignature{"rad/s", ScalarConstraint::finite_only(), true});

    register_builtin_model(
        registry, "dc_motor",
        [](const ModelSpec &spec, SignalNamespace &ns) -> std::unique_ptr<IModel> {
            const std::string context = "model[" + spec.id + ":dc_motor]";

            const std::string resistance_path = context + "/resistance_ohm";
            const std::string inductance_path = context + "/inductance_h";
            const std::string torque_constant_path = context + "/torque_constant";
            const std::string back_emf_constant_path = context + "/back_emf_constant";
            const std::string inertia_path = context + "/inertia";
            const std::string viscous_friction_path = context + "/viscous_friction";
            const std::string initial_current_path = context + "/initial_current";
            const std::string initial_speed_path = context + "/initial_speed";

            const double resistance_ohm =
                as_double(require_param(spec.params, "resistance_ohm", context), resistance_path);
            const double inductance_h = as_double(require_param(spec.params, "inductance_h", context), inductance_path);
            const double torque_constant =
                as_double(require_param(spec.params, "torque_constant", context), torque_constant_path);
            const double back_emf_constant =
                as_double(require_param(spec.params, "back_emf_constant", context), back_emf_constant_path);
            const double inertia = as_double(require_param(spec.params, "inertia", context), inertia_path);
            const double viscous_friction =
                as_double(require_param(spec.params, "viscous_friction", context), viscous_friction_path);
            const double initial_current =
                as_double(require_param(spec.params, "initial_current", context), initial_current_path);
            const double initial_speed =
                as_double(require_param(spec.params, "initial_speed", context), initial_speed_path);

            require_finite_positive(resistance_ohm, resistance_path);
            require_finite_positive(inductance_h, inductance_path);
            require_finite_positive(torque_constant, torque_constant_path);
            require_finite_positive(back_emf_constant, back_emf_constant_path);
            require_finite_positive(inertia, inertia_path);
            require_finite_non_negative(viscous_friction, viscous_friction_path);
            require_finite(initial_current, initial_current_path);
            require_finite(initial_speed, initial_speed_path);

            const std::string speed_path =
                as_string(require_param(spec.params, "speed_signal", context), context + "/speed_signal");
            const std::string current_path =
                as_string(require_param(spec.params, "current_signal", context), context + "/current_signal");
            const std::string torque_path =
                as_string(require_param(spec.params, "torque_signal", context), context + "/torque_signal");
            const std::string voltage_path =
                as_string(require_param(spec.params, "voltage_signal", context), context + "/voltage_signal");
            const std::string load_torque_path =
                as_string(require_param(spec.params, "load_torque_signal", context), context + "/load_torque_signal");

            IntegrationMethod integration_method = IntegrationMethod::ForwardEuler;
            if (auto it = spec.params.find("integration_method"); it != spec.params.end()) {
                const std::string method_name = as_string(it->second, context + "/integration_method");
                try {
                    integration_method = parse_integration_method(method_name);
                } catch (const std::invalid_argument &e) {
                    throw std::runtime_error("Invalid parameter at " + context + "/integration_method: " + e.what());
                }
            }

            return std::make_unique<DcMotorModel>(spec.id, resistance_ohm, inductance_h, torque_constant,
                                                  back_emf_constant, inertia, viscous_friction, initial_current,
                                                  initial_speed, speed_path, current_path, torque_path, voltage_path,
                                                  load_torque_path, ns, integration_method);
        },
        dc_motor_signature);
}

}  // namespace fluxgraph::compiler_internal

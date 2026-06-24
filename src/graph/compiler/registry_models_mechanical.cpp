#include <stdexcept>

#include "common.hpp"
#include "fluxgraph/model/integration.hpp"
#include "fluxgraph/model/mass_spring_damper.hpp"
#include "registry_builtins.hpp"

namespace fluxgraph::compiler_internal {

void register_builtin_models_mechanical(FactoryRegistry &registry) {
    ModelSignature mass_spring_signature;
    mass_spring_signature.signal_param_units.emplace("force_signal", "N");
    mass_spring_signature.signal_param_units.emplace("position_signal", "m");
    mass_spring_signature.signal_param_units.emplace("velocity_signal", "m/s");
    mass_spring_signature.scalar_param_signatures.emplace(
        "mass", ScalarParamSignature{"kg", ScalarConstraint::greater_than(0.0), true});
    mass_spring_signature.scalar_param_signatures.emplace(
        "damping_coeff", ScalarParamSignature{"N*s/m", ScalarConstraint::greater_equal(0.0), true});
    mass_spring_signature.scalar_param_signatures.emplace(
        "spring_constant", ScalarParamSignature{"N/m", ScalarConstraint::greater_equal(0.0), true});
    mass_spring_signature.scalar_param_signatures.emplace(
        "initial_position", ScalarParamSignature{"m", ScalarConstraint::finite_only(), true});
    mass_spring_signature.scalar_param_signatures.emplace(
        "initial_velocity", ScalarParamSignature{"m/s", ScalarConstraint::finite_only(), true});

    register_builtin_model(
        registry, "mass_spring_damper",
        [](const ModelSpec &spec, SignalNamespace &ns) -> std::unique_ptr<IModel> {
            const std::string context = "model[" + spec.id + ":mass_spring_damper]";

            const std::string mass_path = context + "/mass";
            const std::string damping_path = context + "/damping_coeff";
            const std::string spring_path = context + "/spring_constant";
            const std::string initial_position_path = context + "/initial_position";
            const std::string initial_velocity_path = context + "/initial_velocity";

            const double mass = as_double(require_param(spec.params, "mass", context), mass_path);
            const double damping_coeff = as_double(require_param(spec.params, "damping_coeff", context), damping_path);
            const double spring_constant =
                as_double(require_param(spec.params, "spring_constant", context), spring_path);
            const double initial_position =
                as_double(require_param(spec.params, "initial_position", context), initial_position_path);
            const double initial_velocity =
                as_double(require_param(spec.params, "initial_velocity", context), initial_velocity_path);

            require_finite_positive(mass, mass_path);
            require_finite_non_negative(damping_coeff, damping_path);
            require_finite_non_negative(spring_constant, spring_path);
            require_finite(initial_position, initial_position_path);
            require_finite(initial_velocity, initial_velocity_path);

            const std::string position_path =
                as_string(require_param(spec.params, "position_signal", context), context + "/position_signal");
            const std::string velocity_path =
                as_string(require_param(spec.params, "velocity_signal", context), context + "/velocity_signal");
            const std::string force_path =
                as_string(require_param(spec.params, "force_signal", context), context + "/force_signal");

            IntegrationMethod integration_method = IntegrationMethod::ForwardEuler;
            if (auto it = spec.params.find("integration_method"); it != spec.params.end()) {
                const std::string method_name = as_string(it->second, context + "/integration_method");
                try {
                    integration_method = parse_integration_method(method_name);
                } catch (const std::invalid_argument &e) {
                    throw std::runtime_error("Invalid parameter at " + context + "/integration_method: " + e.what());
                }
            }

            return std::make_unique<MassSpringDamperModel>(spec.id, mass, damping_coeff, spring_constant,
                                                           initial_position, initial_velocity, position_path,
                                                           velocity_path, force_path, ns, integration_method);
        },
        mass_spring_signature);
}

}  // namespace fluxgraph::compiler_internal

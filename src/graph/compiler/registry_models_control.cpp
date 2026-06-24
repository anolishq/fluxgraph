#include <stdexcept>

#include "common.hpp"
#include "fluxgraph/model/first_order_process.hpp"
#include "fluxgraph/model/integration.hpp"
#include "fluxgraph/model/second_order_process.hpp"
#include "registry_builtins.hpp"

namespace fluxgraph::compiler_internal {

void register_builtin_models_control(FactoryRegistry &registry) {
    ModelSignature first_order_signature;
    first_order_signature.signal_param_units.emplace("input_signal", "dimensionless");
    first_order_signature.signal_param_units.emplace("output_signal", "dimensionless");
    first_order_signature.scalar_param_signatures.emplace(
        "gain", ScalarParamSignature{"dimensionless", ScalarConstraint::finite_only(), true});
    first_order_signature.scalar_param_signatures.emplace(
        "tau_s", ScalarParamSignature{"s", ScalarConstraint::greater_than(0.0), true});
    first_order_signature.scalar_param_signatures.emplace(
        "initial_output", ScalarParamSignature{"dimensionless", ScalarConstraint::finite_only(), true});

    register_builtin_model(
        registry, "first_order_process",
        [](const ModelSpec &spec, SignalNamespace &ns) -> std::unique_ptr<IModel> {
            const std::string context = "model[" + spec.id + ":first_order_process]";

            const std::string gain_path = context + "/gain";
            const std::string tau_path = context + "/tau_s";
            const std::string initial_output_path = context + "/initial_output";

            const double gain = as_double(require_param(spec.params, "gain", context), gain_path);
            const double tau_s = as_double(require_param(spec.params, "tau_s", context), tau_path);
            const double initial_output =
                as_double(require_param(spec.params, "initial_output", context), initial_output_path);

            require_finite(gain, gain_path);
            require_finite_positive(tau_s, tau_path);
            require_finite(initial_output, initial_output_path);

            const std::string output_path =
                as_string(require_param(spec.params, "output_signal", context), context + "/output_signal");
            const std::string input_path =
                as_string(require_param(spec.params, "input_signal", context), context + "/input_signal");

            IntegrationMethod integration_method = IntegrationMethod::ForwardEuler;
            if (auto it = spec.params.find("integration_method"); it != spec.params.end()) {
                const std::string method_name = as_string(it->second, context + "/integration_method");
                try {
                    integration_method = parse_integration_method(method_name);
                } catch (const std::invalid_argument &e) {
                    throw std::runtime_error("Invalid parameter at " + context + "/integration_method: " + e.what());
                }
            }

            return std::make_unique<FirstOrderProcessModel>(spec.id, gain, tau_s, initial_output, output_path,
                                                            input_path, ns, integration_method);
        },
        first_order_signature);

    ModelSignature second_order_signature;
    second_order_signature.signal_param_units.emplace("input_signal", "dimensionless");
    second_order_signature.signal_param_units.emplace("output_signal", "dimensionless");
    second_order_signature.scalar_param_signatures.emplace(
        "gain", ScalarParamSignature{"dimensionless", ScalarConstraint::finite_only(), true});
    second_order_signature.scalar_param_signatures.emplace(
        "zeta", ScalarParamSignature{"dimensionless", ScalarConstraint::greater_equal(0.0), true});
    second_order_signature.scalar_param_signatures.emplace(
        "omega_n_rad_s", ScalarParamSignature{"1/s", ScalarConstraint::greater_than(0.0), true});
    second_order_signature.scalar_param_signatures.emplace(
        "initial_output", ScalarParamSignature{"dimensionless", ScalarConstraint::finite_only(), true});
    second_order_signature.scalar_param_signatures.emplace(
        "initial_output_rate", ScalarParamSignature{"1/s", ScalarConstraint::finite_only(), true});

    register_builtin_model(
        registry, "second_order_process",
        [](const ModelSpec &spec, SignalNamespace &ns) -> std::unique_ptr<IModel> {
            const std::string context = "model[" + spec.id + ":second_order_process]";

            const std::string gain_path = context + "/gain";
            const std::string zeta_path = context + "/zeta";
            const std::string omega_path = context + "/omega_n_rad_s";
            const std::string initial_output_path = context + "/initial_output";
            const std::string initial_output_rate_path = context + "/initial_output_rate";

            const double gain = as_double(require_param(spec.params, "gain", context), gain_path);
            const double zeta = as_double(require_param(spec.params, "zeta", context), zeta_path);
            const double omega_n_rad_s = as_double(require_param(spec.params, "omega_n_rad_s", context), omega_path);
            const double initial_output =
                as_double(require_param(spec.params, "initial_output", context), initial_output_path);
            const double initial_output_rate =
                as_double(require_param(spec.params, "initial_output_rate", context), initial_output_rate_path);

            require_finite(gain, gain_path);
            require_finite_non_negative(zeta, zeta_path);
            require_finite_positive(omega_n_rad_s, omega_path);
            require_finite(initial_output, initial_output_path);
            require_finite(initial_output_rate, initial_output_rate_path);

            const std::string output_path =
                as_string(require_param(spec.params, "output_signal", context), context + "/output_signal");
            const std::string input_path =
                as_string(require_param(spec.params, "input_signal", context), context + "/input_signal");

            IntegrationMethod integration_method = IntegrationMethod::ForwardEuler;
            if (auto it = spec.params.find("integration_method"); it != spec.params.end()) {
                const std::string method_name = as_string(it->second, context + "/integration_method");
                try {
                    integration_method = parse_integration_method(method_name);
                } catch (const std::invalid_argument &e) {
                    throw std::runtime_error("Invalid parameter at " + context + "/integration_method: " + e.what());
                }
            }

            return std::make_unique<SecondOrderProcessModel>(spec.id, gain, zeta, omega_n_rad_s, initial_output,
                                                             initial_output_rate, output_path, input_path, ns,
                                                             integration_method);
        },
        second_order_signature);
}

}  // namespace fluxgraph::compiler_internal

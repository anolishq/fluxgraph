#include "dimensional.hpp"

#include <stdexcept>

#include "common.hpp"

namespace fluxgraph::compiler_internal {

void emit_warning(const CompilationOptions &options, const std::string &message) {
    if (options.warning_handler) {
        options.warning_handler(message);
    }
}

bool is_unit_known(const UnitRegistry &registry, const std::string &unit) { return registry.contains(unit); }

bool has_compatible_dimension_and_kind(const UnitRegistry &registry, const std::string &lhs_unit,
                                       const std::string &rhs_unit) {
    const UnitDef *lhs = registry.find(lhs_unit);
    const UnitDef *rhs = registry.find(rhs_unit);
    if (lhs == nullptr || rhs == nullptr) {
        return false;
    }
    return lhs->dimension == rhs->dimension && lhs->kind == rhs->kind;
}

std::string resolve_signal_contract_or_empty(const std::unordered_map<SignalId, std::string> &signal_contracts,
                                             SignalId id) {
    auto it = signal_contracts.find(id);
    if (it == signal_contracts.end()) {
        return "";
    }
    return it->second;
}

void validate_model_signature_contracts(const ModelSpec &model_spec, const ModelSignature &signature,
                                        SignalNamespace &signal_ns,
                                        const std::unordered_map<SignalId, std::string> &signal_contracts,
                                        const UnitRegistry &unit_registry, const CompilationOptions &options,
                                        bool strict) {
    for (const auto &[param_name, expected_unit] : signature.signal_param_units) {
        auto param_it = model_spec.params.find(param_name);
        if (param_it == model_spec.params.end()) {
            continue;
        }

        const std::string path =
            as_string(param_it->second, "model[" + model_spec.id + ":" + model_spec.type + "]/{" + param_name + "}");
        const SignalId id = signal_ns.intern(path);
        const std::string actual_unit = resolve_signal_contract_or_empty(signal_contracts, id);

        if (actual_unit.empty()) {
            if (strict) {
                throw std::runtime_error(
                    "GraphCompiler: strict mode requires declared signal contract "
                    "for model '" +
                    model_spec.id + "' parameter '" + param_name + "' (path '" + path + "')");
            }
            continue;
        }

        if (!expected_unit.empty() && actual_unit != expected_unit) {
            const std::string message = "GraphCompiler: model '" + model_spec.id + "' parameter '" + param_name +
                                        "' expects unit '" + expected_unit + "' but found '" + actual_unit + "'";
            if (strict) {
                throw std::runtime_error(message);
            }
            emit_warning(options, message);
        }
    }

    for (const auto &[param_name, param_signature] : signature.scalar_param_signatures) {
        auto param_it = model_spec.params.find(param_name);
        const std::string path = "model[" + model_spec.id + ":" + model_spec.type + "]/" + param_name;

        if (param_it == model_spec.params.end()) {
            if (strict && param_signature.required) {
                throw std::runtime_error(
                    "GraphCompiler: strict mode requires scalar "
                    "parameter '" +
                    param_name + "' for model '" + model_spec.id + "'");
            }
            if (!strict && param_signature.required) {
                emit_warning(options, "GraphCompiler: missing required scalar parameter '" + param_name +
                                          "' for model '" + model_spec.id + "'");
            }
            continue;
        }

        if (!param_signature.unit_symbol.empty() && !is_unit_known(unit_registry, param_signature.unit_symbol)) {
            const std::string message = "GraphCompiler: model signature for type '" + model_spec.type +
                                        "' references unknown scalar unit symbol '" + param_signature.unit_symbol +
                                        "' for parameter '" + param_name + "'";
            if (strict) {
                throw std::runtime_error(message);
            }
            emit_warning(options, message);
        }

        const double value = as_double(param_it->second, path);
        if (!satisfies_scalar_constraint(value, param_signature.constraint)) {
            const std::string message = "Invalid parameter at " + path + ": expected " +
                                        format_scalar_constraint_rule(param_signature.constraint);
            if (strict) {
                throw std::runtime_error(message);
            }
            emit_warning(options, message);
        }
    }

    if (signature.structured_param_validator) {
        signature.structured_param_validator(model_spec, strict, options);
    }
}

}  // namespace fluxgraph::compiler_internal

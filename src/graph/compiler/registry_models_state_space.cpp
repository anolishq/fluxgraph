#include <stdexcept>
#include <utility>
#include <vector>

#include "common.hpp"
#include "fluxgraph/model/state_space_siso_discrete.hpp"
#include "registry_builtins.hpp"

namespace fluxgraph::compiler_internal {

namespace {

struct StateSpaceSisoDiscreteConfig {
    std::vector<std::vector<double>> a_d;
    std::vector<double> b_d;
    std::vector<double> c;
    double d = 0.0;
    std::vector<double> x0;
    std::string output_signal;
    std::string input_signal;
};

std::vector<double> parse_numeric_vector(const ParamValue &value, const std::string &path) {
    const ParamArray &array = as_array(value, path);
    if (array.empty()) {
        throw std::runtime_error("Invalid parameter at " + path + ": expected non-empty array");
    }

    std::vector<double> out;
    out.reserve(array.size());
    for (std::size_t i = 0; i < array.size(); ++i) {
        const std::string element_path = path + "[" + std::to_string(i) + "]";
        const double parsed = as_double(array[i], element_path);
        require_finite(parsed, element_path);
        out.push_back(parsed);
    }
    return out;
}

std::vector<std::vector<double>> parse_numeric_matrix(const ParamValue &value, const std::string &path) {
    const ParamArray &rows = as_array(value, path);
    if (rows.empty()) {
        throw std::runtime_error("Invalid parameter at " + path + ": expected non-empty array");
    }

    std::vector<std::vector<double>> matrix;
    matrix.reserve(rows.size());

    std::size_t expected_columns = 0;
    for (std::size_t row_index = 0; row_index < rows.size(); ++row_index) {
        const std::string row_path = path + "[" + std::to_string(row_index) + "]";
        const std::vector<double> row = parse_numeric_vector(rows[row_index], row_path);

        if (row_index == 0) {
            expected_columns = row.size();
        } else if (row.size() != expected_columns) {
            throw std::runtime_error("Invalid parameter at " + row_path + ": expected row length " +
                                     std::to_string(expected_columns) + ", got " + std::to_string(row.size()));
        }

        matrix.push_back(row);
    }

    return matrix;
}

StateSpaceSisoDiscreteConfig decode_state_space_siso_discrete_config(const ModelSpec &spec) {
    const std::string context = "model[" + spec.id + ":state_space_siso_discrete]";

    StateSpaceSisoDiscreteConfig config;
    config.a_d = parse_numeric_matrix(require_param(spec.params, "A_d", context), context + "/A_d");
    config.b_d = parse_numeric_vector(require_param(spec.params, "B_d", context), context + "/B_d");
    config.c = parse_numeric_vector(require_param(spec.params, "C", context), context + "/C");

    const std::string d_path = context + "/D";
    config.d = as_double(require_param(spec.params, "D", context), d_path);
    require_finite(config.d, d_path);

    config.x0 = parse_numeric_vector(require_param(spec.params, "x0", context), context + "/x0");

    config.output_signal = as_string(require_param(spec.params, "output_signal", context), context + "/output_signal");
    config.input_signal = as_string(require_param(spec.params, "input_signal", context), context + "/input_signal");

    const std::size_t n = config.a_d.size();
    if (config.a_d.front().size() != n) {
        throw std::runtime_error("Invalid parameter at " + context + "/A_d: expected square matrix");
    }
    if (config.b_d.size() != n) {
        throw std::runtime_error("Invalid parameter at " + context + "/B_d: expected vector length " +
                                 std::to_string(n));
    }
    if (config.c.size() != n) {
        throw std::runtime_error("Invalid parameter at " + context + "/C: expected vector length " + std::to_string(n));
    }
    if (config.x0.size() != n) {
        throw std::runtime_error("Invalid parameter at " + context + "/x0: expected vector length " +
                                 std::to_string(n));
    }

    return config;
}

void validate_structured_params(const ModelSpec &spec, bool strict, const CompilationOptions &options) {
    try {
        (void)decode_state_space_siso_discrete_config(spec);
    } catch (const std::exception &e) {
        if (strict) {
            throw;
        }
        if (options.warning_handler) {
            options.warning_handler(
                "GraphCompiler: state_space_siso_discrete structured parameter "
                "validation warning for model '" +
                spec.id + "': " + e.what());
        }
    }
}

}  // namespace

void register_builtin_models_state_space(FactoryRegistry &registry) {
    ModelSignature state_space_signature;
    // Empty expected-unit symbols mean "declared contract required in strict
    // mode, but unit symbol is model-agnostic".
    state_space_signature.signal_param_units.emplace("input_signal", "");
    state_space_signature.signal_param_units.emplace("output_signal", "");
    state_space_signature.structured_param_validator = validate_structured_params;

    register_builtin_model(
        registry, "state_space_siso_discrete",
        [](const ModelSpec &spec, SignalNamespace &ns) -> std::unique_ptr<IModel> {
            StateSpaceSisoDiscreteConfig config = decode_state_space_siso_discrete_config(spec);

            return std::make_unique<StateSpaceSisoDiscreteModel>(spec.id, std::move(config.a_d), std::move(config.b_d),
                                                                 std::move(config.c), config.d, std::move(config.x0),
                                                                 config.output_signal, config.input_signal, ns);
        },
        state_space_signature);
}

}  // namespace fluxgraph::compiler_internal

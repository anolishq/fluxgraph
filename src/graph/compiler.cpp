#include "fluxgraph/graph/compiler.hpp"
#include "fluxgraph/core/units.hpp"
#include "fluxgraph/model/thermal_mass.hpp"
#include "fluxgraph/transform/deadband.hpp"
#include "fluxgraph/transform/delay.hpp"
#include "fluxgraph/transform/first_order_lag.hpp"
#include "fluxgraph/transform/linear.hpp"
#include "fluxgraph/transform/moving_average.hpp"
#include "fluxgraph/transform/noise.hpp"
#include "fluxgraph/transform/rate_limiter.hpp"
#include "fluxgraph/transform/saturation.hpp"
#include "fluxgraph/transform/unit_convert.hpp"
#include <algorithm>
#include <cctype>
#include <limits>
#include <map>
#include <mutex>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <unordered_map>

namespace fluxgraph {

namespace {

const Variant &require_param(const std::map<std::string, Variant> &params,
                             const std::string &name,
                             const std::string &context) {
  auto it = params.find(name);
  if (it == params.end()) {
    throw std::runtime_error("Missing required parameter at " + context + "/" +
                             name);
  }
  return it->second;
}

std::string variant_type_name(const Variant &value) {
  if (std::holds_alternative<double>(value)) {
    return "double";
  }
  if (std::holds_alternative<int64_t>(value)) {
    return "int64";
  }
  if (std::holds_alternative<bool>(value)) {
    return "bool";
  }
  return "string";
}

double as_double(const Variant &value, const std::string &path) {
  if (std::holds_alternative<double>(value)) {
    return std::get<double>(value);
  }
  if (std::holds_alternative<int64_t>(value)) {
    return static_cast<double>(std::get<int64_t>(value));
  }
  throw std::runtime_error("Type error at " + path + ": expected number, got " +
                           variant_type_name(value));
}

int64_t as_int64(const Variant &value, const std::string &path) {
  if (std::holds_alternative<int64_t>(value)) {
    return std::get<int64_t>(value);
  }
  throw std::runtime_error("Type error at " + path + ": expected int64, got " +
                           variant_type_name(value));
}

std::string as_string(const Variant &value, const std::string &path) {
  if (std::holds_alternative<std::string>(value)) {
    return std::get<std::string>(value);
  }
  throw std::runtime_error("Type error at " + path + ": expected string, got " +
                           variant_type_name(value));
}

std::string trim_copy(const std::string &text) {
  auto begin = std::find_if_not(text.begin(), text.end(), [](unsigned char c) {
    return std::isspace(c) != 0;
  });
  auto end = std::find_if_not(text.rbegin(), text.rend(), [](unsigned char c) {
               return std::isspace(c) != 0;
             }).base();

  if (begin >= end) {
    return "";
  }
  return std::string(begin, end);
}

const std::regex &rule_comparator_regex() {
  static const std::regex kComparatorPattern(
      R"(^([A-Za-z0-9_./-]+)\s*(<=|>=|==|!=|<|>)\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)$)");
  return kComparatorPattern;
}

std::function<bool(const SignalStore &)>
compile_condition_expr(const std::string &expr, SignalNamespace &signal_ns,
                       const std::string &rule_id) {
  const std::string trimmed = trim_copy(expr);
  std::smatch match;
  if (!std::regex_match(trimmed, match, rule_comparator_regex())) {
    throw std::runtime_error("Unsupported rule condition syntax for rule '" +
                             rule_id +
                             "'. Supported form: <signal_path> <op> <number>");
  }

  const std::string signal_path = match[1].str();
  const std::string op = match[2].str();
  const double rhs = std::stod(match[3].str());
  const SignalId signal_id = signal_ns.intern(signal_path);

  if (op == "<") {
    return [signal_id, rhs](const SignalStore &store) {
      return store.read_value(signal_id) < rhs;
    };
  }
  if (op == "<=") {
    return [signal_id, rhs](const SignalStore &store) {
      return store.read_value(signal_id) <= rhs;
    };
  }
  if (op == ">") {
    return [signal_id, rhs](const SignalStore &store) {
      return store.read_value(signal_id) > rhs;
    };
  }
  if (op == ">=") {
    return [signal_id, rhs](const SignalStore &store) {
      return store.read_value(signal_id) >= rhs;
    };
  }
  if (op == "==") {
    return [signal_id, rhs](const SignalStore &store) {
      return store.read_value(signal_id) == rhs;
    };
  }

  return [signal_id, rhs](const SignalStore &store) {
    return store.read_value(signal_id) != rhs;
  };
}

struct TransformRegistryEntry {
  GraphCompiler::TransformFactory factory;
  bool has_signature = false;
  TransformSignature signature;
};

struct ModelRegistryEntry {
  GraphCompiler::ModelFactory factory;
  bool has_signature = false;
  ModelSignature signature;
};

struct FactoryRegistry {
  std::mutex mutex;
  bool defaults_registered = false;
  std::unordered_map<std::string, TransformRegistryEntry> transform_factories;
  std::unordered_map<std::string, ModelRegistryEntry> model_factories;
};

FactoryRegistry &factory_registry() {
  static FactoryRegistry registry;
  return registry;
}

void validate_registration_request(const std::string &type, bool has_factory,
                                   const std::string &kind) {
  if (trim_copy(type).empty()) {
    throw std::invalid_argument("GraphCompiler: " + kind +
                                " type must be non-empty");
  }
  if (!has_factory) {
    throw std::invalid_argument("GraphCompiler: " + kind +
                                " factory must be valid");
  }
}

void register_builtin_transform(FactoryRegistry &registry,
                                const std::string &type,
                                GraphCompiler::TransformFactory factory,
                                TransformSignature::Contract contract =
                                    TransformSignature::Contract::preserve) {
  TransformRegistryEntry entry;
  entry.factory = std::move(factory);
  entry.has_signature = true;
  entry.signature.contract = contract;
  registry.transform_factories.emplace(type, std::move(entry));
}

void register_builtin_model(FactoryRegistry &registry, const std::string &type,
                            GraphCompiler::ModelFactory factory,
                            ModelSignature signature) {
  ModelRegistryEntry entry;
  entry.factory = std::move(factory);
  entry.has_signature = true;
  entry.signature = std::move(signature);
  registry.model_factories.emplace(type, std::move(entry));
}

void ensure_default_factories_registered_locked(FactoryRegistry &registry) {
  if (registry.defaults_registered) {
    return;
  }

  register_builtin_transform(
      registry, "linear",
      [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
        const std::string context = "transform[linear]";
        double scale = as_double(require_param(spec.params, "scale", context),
                                 context + "/scale");
        double offset = as_double(require_param(spec.params, "offset", context),
                                  context + "/offset");
        double clamp_min = -std::numeric_limits<double>::infinity();
        double clamp_max = std::numeric_limits<double>::infinity();

        if (auto it = spec.params.find("clamp_min"); it != spec.params.end()) {
          clamp_min = as_double(it->second, context + "/clamp_min");
        }
        if (auto it = spec.params.find("clamp_max"); it != spec.params.end()) {
          clamp_max = as_double(it->second, context + "/clamp_max");
        }

        return std::make_unique<LinearTransform>(scale, offset, clamp_min,
                                                 clamp_max);
      },
      TransformSignature::Contract::linear_conditioning);

  register_builtin_transform(
      registry, "first_order_lag",
      [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
        const std::string context = "transform[first_order_lag]";
        double tau_s = as_double(require_param(spec.params, "tau_s", context),
                                 context + "/tau_s");
        return std::make_unique<FirstOrderLagTransform>(tau_s);
      });

  register_builtin_transform(
      registry, "delay",
      [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
        const std::string context = "transform[delay]";
        double delay_sec =
            as_double(require_param(spec.params, "delay_sec", context),
                      context + "/delay_sec");
        return std::make_unique<DelayTransform>(delay_sec);
      });

  register_builtin_transform(
      registry, "noise",
      [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
        const std::string context = "transform[noise]";
        double amplitude =
            as_double(require_param(spec.params, "amplitude", context),
                      context + "/amplitude");
        uint32_t seed = 0U;
        if (auto it = spec.params.find("seed"); it != spec.params.end()) {
          seed = static_cast<uint32_t>(as_int64(it->second, context + "/seed"));
        }
        return std::make_unique<NoiseTransform>(amplitude, seed);
      });

  register_builtin_transform(
      registry, "saturation",
      [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
        const std::string context = "transform[saturation]";
        double min_val = 0.0;
        double max_val = 0.0;
        if (auto it = spec.params.find("min"); it != spec.params.end()) {
          min_val = as_double(it->second, context + "/min");
        } else {
          min_val = as_double(require_param(spec.params, "min_value", context),
                              context + "/min_value");
        }

        if (auto it = spec.params.find("max"); it != spec.params.end()) {
          max_val = as_double(it->second, context + "/max");
        } else {
          max_val = as_double(require_param(spec.params, "max_value", context),
                              context + "/max_value");
        }
        return std::make_unique<SaturationTransform>(min_val, max_val);
      });

  register_builtin_transform(
      registry, "deadband",
      [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
        const std::string context = "transform[deadband]";
        double threshold =
            as_double(require_param(spec.params, "threshold", context),
                      context + "/threshold");
        return std::make_unique<DeadbandTransform>(threshold);
      });

  register_builtin_transform(
      registry, "rate_limiter",
      [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
        const std::string context = "transform[rate_limiter]";
        double max_rate = 0.0;
        if (auto it = spec.params.find("max_rate_per_sec");
            it != spec.params.end()) {
          max_rate = as_double(it->second, context + "/max_rate_per_sec");
        } else {
          max_rate = as_double(require_param(spec.params, "max_rate", context),
                               context + "/max_rate");
        }
        return std::make_unique<RateLimiterTransform>(max_rate);
      });

  register_builtin_transform(
      registry, "moving_average",
      [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
        const std::string context = "transform[moving_average]";
        int64_t window_size_raw =
            as_int64(require_param(spec.params, "window_size", context),
                     context + "/window_size");
        if (window_size_raw <= 0) {
          throw std::runtime_error("Invalid parameter at " + context +
                                   "/window_size: expected >= 1");
        }
        size_t window_size = static_cast<size_t>(window_size_raw);
        return std::make_unique<MovingAverageTransform>(window_size);
      });

  register_builtin_transform(
      registry, "unit_convert",
      [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
        const std::string context = "transform[unit_convert]";
        double resolved_scale =
            as_double(require_param(spec.params, "__resolved_scale", context),
                      context + "/__resolved_scale");
        double resolved_offset =
            as_double(require_param(spec.params, "__resolved_offset", context),
                      context + "/__resolved_offset");
        return std::make_unique<UnitConvertTransform>(resolved_scale,
                                                      resolved_offset);
      },
      TransformSignature::Contract::unit_convert);

  ModelSignature thermal_signature;
  thermal_signature.signal_param_units.emplace("power_signal", "W");
  thermal_signature.signal_param_units.emplace("ambient_signal", "degC");
  thermal_signature.signal_param_units.emplace("temp_signal", "degC");

  register_builtin_model(
      registry, "thermal_mass",
      [](const ModelSpec &spec,
         SignalNamespace &ns) -> std::unique_ptr<IModel> {
        const std::string context = "model[" + spec.id + ":thermal_mass]";
        double thermal_mass =
            as_double(require_param(spec.params, "thermal_mass", context),
                      context + "/thermal_mass");
        double heat_transfer_coeff = as_double(
            require_param(spec.params, "heat_transfer_coeff", context),
            context + "/heat_transfer_coeff");
        double initial_temp =
            as_double(require_param(spec.params, "initial_temp", context),
                      context + "/initial_temp");
        std::string temp_path =
            as_string(require_param(spec.params, "temp_signal", context),
                      context + "/temp_signal");
        std::string power_path =
            as_string(require_param(spec.params, "power_signal", context),
                      context + "/power_signal");
        std::string ambient_path =
            as_string(require_param(spec.params, "ambient_signal", context),
                      context + "/ambient_signal");
        ThermalIntegrationMethod integration_method =
            ThermalIntegrationMethod::ForwardEuler;
        if (auto it = spec.params.find("integration_method");
            it != spec.params.end()) {
          const std::string method_name =
              as_string(it->second, context + "/integration_method");
          try {
            integration_method = parse_thermal_integration_method(method_name);
          } catch (const std::invalid_argument &e) {
            throw std::runtime_error("Invalid parameter at " + context +
                                     "/integration_method: " + e.what());
          }
        }

        return std::make_unique<ThermalMassModel>(
            spec.id, thermal_mass, heat_transfer_coeff, initial_temp, temp_path,
            power_path, ambient_path, ns, integration_method);
      },
      thermal_signature);

  registry.defaults_registered = true;
}

const TransformRegistryEntry &
resolve_transform_entry_or_throw(FactoryRegistry &registry,
                                 const std::string &type) {
  auto it = registry.transform_factories.find(type);
  if (it == registry.transform_factories.end()) {
    throw std::runtime_error("Unknown transform type: " + type);
  }
  return it->second;
}

const ModelRegistryEntry &
resolve_model_entry_or_throw(FactoryRegistry &registry,
                             const std::string &type) {
  auto it = registry.model_factories.find(type);
  if (it == registry.model_factories.end()) {
    throw std::runtime_error("Unknown model type: " + type);
  }
  return it->second;
}

void emit_warning(const CompilationOptions &options,
                  const std::string &message) {
  if (options.warning_handler) {
    options.warning_handler(message);
  }
}

bool is_unit_known(const UnitRegistry &registry, const std::string &unit) {
  return registry.contains(unit);
}

bool has_compatible_dimension_and_kind(const UnitRegistry &registry,
                                       const std::string &lhs_unit,
                                       const std::string &rhs_unit) {
  const UnitDef *lhs = registry.find(lhs_unit);
  const UnitDef *rhs = registry.find(rhs_unit);
  if (lhs == nullptr || rhs == nullptr) {
    return false;
  }
  return lhs->dimension == rhs->dimension && lhs->kind == rhs->kind;
}

std::string resolve_signal_contract_or_empty(
    const std::unordered_map<SignalId, std::string> &signal_contracts,
    SignalId id) {
  auto it = signal_contracts.find(id);
  if (it == signal_contracts.end()) {
    return "";
  }
  return it->second;
}

} // namespace

GraphCompiler::GraphCompiler() = default;
GraphCompiler::~GraphCompiler() = default;

void GraphCompiler::register_transform_factory(const std::string &type,
                                               TransformFactory factory) {
  validate_registration_request(type, static_cast<bool>(factory), "transform");

  auto &registry = factory_registry();
  std::lock_guard<std::mutex> lock(registry.mutex);
  ensure_default_factories_registered_locked(registry);

  TransformRegistryEntry entry;
  entry.factory = std::move(factory);

  auto [_, inserted] =
      registry.transform_factories.emplace(type, std::move(entry));
  if (!inserted) {
    throw std::runtime_error("GraphCompiler: transform factory already "
                             "registered for type '" +
                             type + "'");
  }
}

void GraphCompiler::register_transform_factory_with_signature(
    const std::string &type, TransformFactory factory,
    const TransformSignature &signature) {
  validate_registration_request(type, static_cast<bool>(factory), "transform");

  auto &registry = factory_registry();
  std::lock_guard<std::mutex> lock(registry.mutex);
  ensure_default_factories_registered_locked(registry);

  TransformRegistryEntry entry;
  entry.factory = std::move(factory);
  entry.has_signature = true;
  entry.signature = signature;

  auto [_, inserted] =
      registry.transform_factories.emplace(type, std::move(entry));
  if (!inserted) {
    throw std::runtime_error("GraphCompiler: transform factory already "
                             "registered for type '" +
                             type + "'");
  }
}

void GraphCompiler::register_model_factory(const std::string &type,
                                           ModelFactory factory) {
  validate_registration_request(type, static_cast<bool>(factory), "model");

  auto &registry = factory_registry();
  std::lock_guard<std::mutex> lock(registry.mutex);
  ensure_default_factories_registered_locked(registry);

  ModelRegistryEntry entry;
  entry.factory = std::move(factory);

  auto [_, inserted] = registry.model_factories.emplace(type, std::move(entry));
  if (!inserted) {
    throw std::runtime_error("GraphCompiler: model factory already registered "
                             "for type '" +
                             type + "'");
  }
}

void GraphCompiler::register_model_factory_with_signature(
    const std::string &type, ModelFactory factory,
    const ModelSignature &signature) {
  validate_registration_request(type, static_cast<bool>(factory), "model");

  auto &registry = factory_registry();
  std::lock_guard<std::mutex> lock(registry.mutex);
  ensure_default_factories_registered_locked(registry);

  ModelRegistryEntry entry;
  entry.factory = std::move(factory);
  entry.has_signature = true;
  entry.signature = signature;

  auto [_, inserted] = registry.model_factories.emplace(type, std::move(entry));
  if (!inserted) {
    throw std::runtime_error("GraphCompiler: model factory already registered "
                             "for type '" +
                             type + "'");
  }
}

bool GraphCompiler::is_transform_registered(const std::string &type) {
  auto &registry = factory_registry();
  std::lock_guard<std::mutex> lock(registry.mutex);
  ensure_default_factories_registered_locked(registry);
  return registry.transform_factories.find(type) !=
         registry.transform_factories.end();
}

bool GraphCompiler::is_model_registered(const std::string &type) {
  auto &registry = factory_registry();
  std::lock_guard<std::mutex> lock(registry.mutex);
  ensure_default_factories_registered_locked(registry);
  return registry.model_factories.find(type) != registry.model_factories.end();
}

CompiledProgram GraphCompiler::compile(const GraphSpec &spec,
                                       SignalNamespace &signal_ns,
                                       FunctionNamespace &func_ns,
                                       double expected_dt) {
  CompilationOptions options;
  options.expected_dt = expected_dt;
  return compile(spec, signal_ns, func_ns, options);
}

CompiledProgram GraphCompiler::compile(const GraphSpec &spec,
                                       SignalNamespace &signal_ns,
                                       FunctionNamespace &func_ns,
                                       const CompilationOptions &options) {
  CompiledProgram program;
  const UnitRegistry &unit_registry = UnitRegistry::instance();

  const bool strict = options.dimensional_policy == DimensionalPolicy::strict;

  std::unordered_map<SignalId, std::string> signal_contracts;
  signal_contracts.reserve(spec.signals.size());

  for (size_t i = 0; i < spec.signals.size(); ++i) {
    const auto &signal_spec = spec.signals[i];
    if (trim_copy(signal_spec.path).empty()) {
      throw std::runtime_error("GraphCompiler: signals[" + std::to_string(i) +
                               "].path must be non-empty");
    }

    const std::string unit = trim_copy(signal_spec.unit);
    if (unit.empty()) {
      throw std::runtime_error("GraphCompiler: signals[" + std::to_string(i) +
                               "].unit must be non-empty");
    }

    const SignalId id = signal_ns.intern(signal_spec.path);
    const auto existing = signal_contracts.find(id);
    if (existing != signal_contracts.end() && existing->second != unit) {
      throw std::runtime_error(
          "GraphCompiler: duplicate signal contract for '" + signal_spec.path +
          "' with conflicting units ('" + existing->second + "' vs '" + unit +
          "')");
    }

    if (!is_unit_known(unit_registry, unit)) {
      if (strict) {
        throw std::runtime_error(
            "GraphCompiler: unknown unit symbol in signals "
            "contract for path '" +
            signal_spec.path + "': '" + unit + "'");
      }
      emit_warning(options,
                   "GraphCompiler: unknown unit symbol in permissive mode for "
                   "signal path '" +
                       signal_spec.path + "': '" + unit + "'");
    }

    signal_contracts[id] = unit;
  }

  {
    auto &registry = factory_registry();
    std::lock_guard<std::mutex> lock(registry.mutex);
    ensure_default_factories_registered_locked(registry);

    for (size_t i = 0; i < spec.models.size(); ++i) {
      const auto &model_spec = spec.models[i];
      const auto &entry =
          resolve_model_entry_or_throw(registry, model_spec.type);
      if (strict && !entry.has_signature) {
        throw std::runtime_error(
            "GraphCompiler: strict mode requires signature metadata for model "
            "type '" +
            model_spec.type + "' (model id '" + model_spec.id + "')");
      }

      if (entry.has_signature) {
        for (const auto &[param_name, expected_unit] :
             entry.signature.signal_param_units) {
          auto param_it = model_spec.params.find(param_name);
          if (param_it == model_spec.params.end()) {
            continue;
          }

          const std::string path = as_string(
              param_it->second, "model[" + model_spec.id + ":" +
                                    model_spec.type + "]/{" + param_name + "}");
          const SignalId id = signal_ns.intern(path);
          const std::string actual_unit =
              resolve_signal_contract_or_empty(signal_contracts, id);

          if (actual_unit.empty()) {
            if (strict) {
              throw std::runtime_error("GraphCompiler: strict mode requires "
                                       "declared signal contract "
                                       "for model '" +
                                       model_spec.id + "' parameter '" +
                                       param_name + "' (path '" + path + "')");
            }
            continue;
          }

          if (actual_unit != expected_unit) {
            const std::string message =
                "GraphCompiler: model '" + model_spec.id + "' parameter '" +
                param_name + "' expects unit '" + expected_unit +
                "' but found '" + actual_unit + "'";
            if (strict) {
              throw std::runtime_error(message);
            }
            emit_warning(options, message);
          }
        }
      }
    }
  }

  // Compile models.
  for (const auto &model_spec : spec.models) {
    auto *model = parse_model(model_spec, signal_ns);
    program.models.emplace_back(model);
  }

  if (options.expected_dt > 0.0) {
    validate_stability(program.models, options.expected_dt);
  }

  // Compile edges with dimensional checks.
  for (size_t edge_index = 0; edge_index < spec.edges.size(); ++edge_index) {
    const auto &edge_spec = spec.edges[edge_index];

    const SignalId src = signal_ns.intern(edge_spec.source_path);
    const SignalId tgt = signal_ns.intern(edge_spec.target_path);

    const std::string source_unit =
        resolve_signal_contract_or_empty(signal_contracts, src);
    const std::string target_unit =
        resolve_signal_contract_or_empty(signal_contracts, tgt);

    if (strict && source_unit.empty()) {
      throw std::runtime_error(
          "GraphCompiler: strict mode requires declared source signal contract "
          "for edge[" +
          std::to_string(edge_index) + "] ('" + edge_spec.source_path +
          "' -> '" + edge_spec.target_path + "')");
    }
    if (strict && target_unit.empty()) {
      throw std::runtime_error(
          "GraphCompiler: strict mode requires declared target signal contract "
          "for edge[" +
          std::to_string(edge_index) + "] ('" + edge_spec.source_path +
          "' -> '" + edge_spec.target_path + "')");
    }

    TransformRegistryEntry transform_entry;
    {
      auto &registry = factory_registry();
      std::lock_guard<std::mutex> lock(registry.mutex);
      ensure_default_factories_registered_locked(registry);
      const auto &entry =
          resolve_transform_entry_or_throw(registry, edge_spec.transform.type);
      transform_entry = entry;
    }

    if (strict && !transform_entry.has_signature) {
      throw std::runtime_error(
          "GraphCompiler: strict mode requires signature metadata for "
          "transform type '" +
          edge_spec.transform.type + "' on edge['" + edge_spec.source_path +
          "' -> '" + edge_spec.target_path + "']");
    }

    TransformSpec resolved_transform_spec = edge_spec.transform;

    const bool both_declared = !source_unit.empty() && !target_unit.empty();
    const bool both_known = both_declared &&
                            is_unit_known(unit_registry, source_unit) &&
                            is_unit_known(unit_registry, target_unit);

    const TransformSignature::Contract contract =
        transform_entry.has_signature ? transform_entry.signature.contract
                                      : TransformSignature::Contract::preserve;

    if (contract == TransformSignature::Contract::unit_convert) {
      const std::string edge_context =
          "edge[" + std::to_string(edge_index) + "]";

      const std::string to_unit = as_string(
          require_param(edge_spec.transform.params, "to_unit", edge_context),
          edge_context + "/transform/params/to_unit");
      if (!is_unit_known(unit_registry, to_unit)) {
        const std::string message =
            "GraphCompiler: unit_convert unknown to_unit '" + to_unit +
            "' at " + edge_context;
        if (strict) {
          throw std::runtime_error(message);
        }
        emit_warning(options, message);
      }

      std::string from_assertion;
      if (auto it = edge_spec.transform.params.find("from_unit");
          it != edge_spec.transform.params.end()) {
        from_assertion =
            as_string(it->second, edge_context + "/transform/params/from_unit");
      }

      if (!from_assertion.empty() && !source_unit.empty() &&
          from_assertion != source_unit) {
        const std::string message =
            "GraphCompiler: unit_convert from_unit assertion '" +
            from_assertion + "' does not match declared source unit '" +
            source_unit + "' at " + edge_context;
        if (strict) {
          throw std::runtime_error(message);
        }
        emit_warning(options, message);
      }

      if (!target_unit.empty() && target_unit != to_unit) {
        const std::string message =
            "GraphCompiler: unit_convert to_unit '" + to_unit +
            "' does not match declared target unit '" + target_unit +
            "' on edge['" + edge_spec.source_path + "' -> '" +
            edge_spec.target_path + "']";
        if (strict) {
          throw std::runtime_error(message);
        }
        emit_warning(options, message);
      }

      std::string from_unit = source_unit;
      if (from_unit.empty()) {
        from_unit = from_assertion;
      }

      UnitConversion conversion;
      conversion.scale = 1.0;
      conversion.offset = 0.0;

      if (!from_unit.empty() && !to_unit.empty()) {
        try {
          conversion = unit_registry.resolve_conversion(from_unit, to_unit);
        } catch (const std::exception &e) {
          if (strict) {
            throw std::runtime_error(
                "GraphCompiler: unit_convert conversion resolution failed on "
                "edge['" +
                edge_spec.source_path + "' -> '" + edge_spec.target_path +
                "']: " + e.what());
          }
          emit_warning(options,
                       "GraphCompiler: permissive unit_convert conversion "
                       "resolution failed on edge['" +
                           edge_spec.source_path + "' -> '" +
                           edge_spec.target_path + "']: " + e.what());
        }
      }

      resolved_transform_spec.params["__resolved_scale"] = conversion.scale;
      resolved_transform_spec.params["__resolved_offset"] = conversion.offset;
    } else if (both_known) {
      if (contract == TransformSignature::Contract::linear_conditioning) {
        if (strict && source_unit != target_unit) {
          throw std::runtime_error(
              "GraphCompiler: strict mode disallows unit-boundary crossing via "
              "linear transform on edge['" +
              edge_spec.source_path + "' -> '" + edge_spec.target_path +
              "']; use unit_convert");
        }

        if (!strict && !has_compatible_dimension_and_kind(
                           unit_registry, source_unit, target_unit)) {
          emit_warning(options,
                       "GraphCompiler: permissive linear boundary warning on "
                       "edge['" +
                           edge_spec.source_path + "' -> '" +
                           edge_spec.target_path + "'] (source unit '" +
                           source_unit + "', target unit '" + target_unit +
                           "')");
        }
      } else {
        if (!has_compatible_dimension_and_kind(unit_registry, source_unit,
                                               target_unit)) {
          const std::string message =
              "GraphCompiler: incompatible unit contracts on edge['" +
              edge_spec.source_path + "' -> '" + edge_spec.target_path +
              "'] (source='" + source_unit + "', target='" + target_unit + "')";
          if (strict) {
            throw std::runtime_error(message);
          }
          emit_warning(options, message);
        }
      }
    } else if (!strict && both_declared &&
               contract == TransformSignature::Contract::linear_conditioning) {
      emit_warning(
          options,
          "GraphCompiler: permissive linear boundary warning could not "
          "fully validate units on edge['" +
              edge_spec.source_path + "' -> '" + edge_spec.target_path +
              "'] because one or both units are unknown to registry");
    }

    ITransform *tf = parse_transform(resolved_transform_spec);
    const bool is_delay = edge_spec.transform.type == "delay";
    program.edges.emplace_back(src, tgt, tf, is_delay);
  }

  // Enforce single-writer ownership across model outputs and edge targets.
  std::map<SignalId, std::string> writer_owner;
  auto register_writer = [&writer_owner](SignalId id,
                                         const std::string &owner_desc) {
    auto [it, inserted] = writer_owner.emplace(id, owner_desc);
    if (!inserted) {
      throw std::runtime_error("Multiple writers for signal id " +
                               std::to_string(id) + ": '" + it->second +
                               "' conflicts with '" + owner_desc + "'");
    }
  };

  for (const auto &edge : program.edges) {
    register_writer(edge.target, "edge_target");
  }

  for (size_t model_index = 0; model_index < program.models.size();
       ++model_index) {
    const auto &model = program.models[model_index];
    const auto output_ids = model->output_signal_ids();
    for (SignalId output_id : output_ids) {
      if (output_id == INVALID_SIGNAL) {
        throw std::runtime_error(
            "Model output_signal_ids() returned INVALID_SIGNAL for model[" +
            std::to_string(model_index) + ":" + model->describe() + "]");
      }
      if (output_id >= signal_ns.size()) {
        throw std::runtime_error(
            "Model output_signal_ids() returned non-interned signal id " +
            std::to_string(output_id) + " for model[" +
            std::to_string(model_index) + ":" + model->describe() + "]");
      }
      register_writer(output_id, "model_output[" + std::to_string(model_index) +
                                     ":" + model->describe() + "]");
    }
  }

  detect_cycles(program.edges);
  topological_sort(program.edges);

  // Compile rules with threshold unit policy.
  for (const auto &rule_spec : spec.rules) {
    const std::string trimmed = trim_copy(rule_spec.condition);
    std::smatch match;
    if (std::regex_match(trimmed, match, rule_comparator_regex())) {
      const std::string signal_path = match[1].str();
      const SignalId signal_id = signal_ns.intern(signal_path);
      const std::string lhs_unit =
          resolve_signal_contract_or_empty(signal_contracts, signal_id);
      if (strict && lhs_unit.empty()) {
        throw std::runtime_error(
            "GraphCompiler: strict mode requires declared unit contract for "
            "rule LHS signal '" +
            signal_path + "' in rule '" + rule_spec.id + "'");
      }
      if (strict && !lhs_unit.empty() &&
          !is_unit_known(unit_registry, lhs_unit)) {
        throw std::runtime_error(
            "GraphCompiler: strict mode rule LHS signal '" + signal_path +
            "' uses unknown unit symbol '" + lhs_unit + "'");
      }
    }

    CompiledRule rule;
    rule.id = rule_spec.id;
    rule.on_error = rule_spec.on_error;

    rule.condition =
        compile_condition_expr(rule_spec.condition, signal_ns, rule_spec.id);

    for (const auto &action : rule_spec.actions) {
      DeviceId dev_id = func_ns.intern_device(action.device);
      FunctionId func_id = func_ns.intern_function(action.function);
      rule.device_functions.emplace_back(dev_id, func_id);
      rule.args_list.push_back(action.args);
    }

    program.rules.push_back(std::move(rule));
  }

  for (const auto &[id, unit] : signal_contracts) {
    program.signal_unit_contracts.emplace_back(id, unit);
  }
  std::sort(
      program.signal_unit_contracts.begin(),
      program.signal_unit_contracts.end(),
      [](const auto &lhs, const auto &rhs) { return lhs.first < rhs.first; });

  program.required_signal_capacity = signal_ns.size();

  for (const auto &rule : program.rules) {
    program.required_command_capacity += rule.device_functions.size();
  }

  return program;
}

ITransform *GraphCompiler::parse_transform(const TransformSpec &spec) {
  TransformFactory factory;
  {
    auto &registry = factory_registry();
    std::lock_guard<std::mutex> lock(registry.mutex);
    ensure_default_factories_registered_locked(registry);

    const auto &entry = resolve_transform_entry_or_throw(registry, spec.type);
    factory = entry.factory;
  }

  auto transform = factory(spec);
  if (!transform) {
    throw std::runtime_error("Transform factory returned null for type '" +
                             spec.type + "'");
  }
  return transform.release();
}

IModel *GraphCompiler::parse_model(const ModelSpec &spec, SignalNamespace &ns) {
  ModelFactory factory;
  {
    auto &registry = factory_registry();
    std::lock_guard<std::mutex> lock(registry.mutex);
    ensure_default_factories_registered_locked(registry);

    const auto &entry = resolve_model_entry_or_throw(registry, spec.type);
    factory = entry.factory;
  }

  auto model = factory(spec, ns);
  if (!model) {
    throw std::runtime_error("Model factory returned null for type '" +
                             spec.type + "'");
  }
  return model.release();
}

void GraphCompiler::topological_sort(std::vector<CompiledEdge> &edges) {
  std::vector<size_t> delay_indices;
  std::vector<size_t> immediate_indices;
  delay_indices.reserve(edges.size());
  immediate_indices.reserve(edges.size());

  for (size_t i = 0; i < edges.size(); ++i) {
    if (edges[i].is_delay) {
      delay_indices.push_back(i);
    } else {
      immediate_indices.push_back(i);
    }
  }

  std::map<SignalId, std::vector<size_t>> outgoing;
  std::map<SignalId, int> in_degree;
  std::set<SignalId> all_signals;

  for (size_t idx : immediate_indices) {
    all_signals.insert(edges[idx].source);
    all_signals.insert(edges[idx].target);
    outgoing[edges[idx].source].push_back(idx);
    in_degree[edges[idx].target]++;
  }

  std::set<SignalId> ready;
  for (SignalId sig : all_signals) {
    if (in_degree[sig] == 0) {
      ready.insert(sig);
    }
  }

  std::vector<size_t> sorted_immediate_indices;
  sorted_immediate_indices.reserve(immediate_indices.size());
  std::set<size_t> processed_edges;

  while (!ready.empty()) {
    SignalId sig = *ready.begin();
    ready.erase(ready.begin());

    auto it = outgoing.find(sig);
    if (it == outgoing.end()) {
      continue;
    }

    for (size_t idx : it->second) {
      if (!processed_edges.insert(idx).second) {
        continue;
      }
      sorted_immediate_indices.push_back(idx);
      if (--in_degree[edges[idx].target] == 0) {
        ready.insert(edges[idx].target);
      }
    }
  }

  if (sorted_immediate_indices.size() != immediate_indices.size()) {
    throw std::runtime_error(
        "GraphCompiler: topological sort failed for non-delay edges.");
  }

  std::vector<CompiledEdge> sorted;
  sorted.reserve(edges.size());

  for (size_t idx : delay_indices) {
    sorted.push_back(std::move(edges[idx]));
  }

  for (size_t idx : sorted_immediate_indices) {
    sorted.push_back(std::move(edges[idx]));
  }

  edges = std::move(sorted);
}

void GraphCompiler::detect_cycles(const std::vector<CompiledEdge> &edges) {
  std::map<SignalId, std::vector<SignalId>> graph;
  for (const auto &edge : edges) {
    if (edge.is_delay) {
      continue;
    }
    graph[edge.source].push_back(edge.target);
    if (graph.count(edge.target) == 0) {
      graph[edge.target] = {};
    }
  }

  std::map<SignalId, int> state;
  std::vector<SignalId> stack;
  std::vector<SignalId> cycle_path;
  bool found_cycle = false;

  std::function<void(SignalId)> dfs = [&](SignalId node) {
    if (found_cycle) {
      return;
    }

    state[node] = 1;
    stack.push_back(node);

    for (SignalId neighbor : graph[node]) {
      if (state[neighbor] == 0) {
        dfs(neighbor);
        if (found_cycle) {
          return;
        }
      } else if (state[neighbor] == 1) {
        auto start_it = std::find(stack.begin(), stack.end(), neighbor);
        cycle_path.assign(start_it, stack.end());
        cycle_path.push_back(neighbor);
        found_cycle = true;
        return;
      }
    }

    stack.pop_back();
    state[node] = 2;
  };

  for (const auto &[node, _] : graph) {
    if (state[node] == 0) {
      dfs(node);
    }
    if (found_cycle) {
      break;
    }
  }

  if (found_cycle) {
    std::ostringstream oss;
    oss << "GraphCompiler: Cycle detected in non-delay subgraph: ";
    for (size_t i = 0; i < cycle_path.size(); ++i) {
      if (i > 0) {
        oss << " -> ";
      }
      oss << cycle_path[i];
    }
    oss << ". Add a delay edge in feedback path.";
    throw std::runtime_error(oss.str());
  }
}

void GraphCompiler::validate_stability(
    const std::vector<std::unique_ptr<IModel>> &models, double expected_dt) {
  for (const auto &model : models) {
    double limit = model->compute_stability_limit();
    if (expected_dt > limit) {
      std::ostringstream oss;
      oss << "Stability violation: " << model->describe() << " requires dt < "
          << limit << "s, but dt = " << expected_dt << "s";
      throw std::runtime_error(oss.str());
    }
  }
}

} // namespace fluxgraph

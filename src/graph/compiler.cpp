#include "fluxgraph/graph/compiler.hpp"

#include <algorithm>
#include <format>
#include <map>
#include <mutex>
#include <regex>
#include <stdexcept>
#include <unordered_map>

#include "compiler/algorithms.hpp"
#include "compiler/common.hpp"
#include "compiler/dimensional.hpp"
#include "compiler/registry.hpp"
#include "fluxgraph/core/units.hpp"

namespace fluxgraph {

using compiler_internal::as_string;
using compiler_internal::compile_condition_expr;
using compiler_internal::detect_cycles_in_non_delay_subgraph;
using compiler_internal::emit_warning;
using compiler_internal::ensure_default_factories_registered_locked;
using compiler_internal::factory_registry;
using compiler_internal::has_compatible_dimension_and_kind;
using compiler_internal::is_unit_known;
using compiler_internal::ModelRegistryEntry;
using compiler_internal::require_param;
using compiler_internal::resolve_model_entry_or_throw;
using compiler_internal::resolve_signal_contract_or_empty;
using compiler_internal::resolve_transform_entry_or_throw;
using compiler_internal::rule_comparator_regex;
using compiler_internal::topological_sort_edges;
using compiler_internal::TransformRegistryEntry;
using compiler_internal::trim_copy;
using compiler_internal::validate_model_signature_contracts;
using compiler_internal::validate_model_stability_limits;
using compiler_internal::validate_registration_request;

GraphCompiler::GraphCompiler() = default;
GraphCompiler::~GraphCompiler() = default;

void GraphCompiler::register_transform_factory(const std::string &type, TransformFactory factory) {
    validate_registration_request(type, static_cast<bool>(factory), "transform");

    auto &registry = factory_registry();
    std::lock_guard<std::mutex> lock(registry.mutex);
    ensure_default_factories_registered_locked(registry);

    TransformRegistryEntry entry;
    entry.factory = std::move(factory);

    auto [_, inserted] = registry.transform_factories.emplace(type, std::move(entry));
    if (!inserted) {
        throw std::runtime_error(
            std::format("GraphCompiler: transform factory already registered for type '{}'", type));
    }
}

void GraphCompiler::register_transform_factory_with_signature(const std::string &type, TransformFactory factory,
                                                              const TransformSignature &signature) {
    validate_registration_request(type, static_cast<bool>(factory), "transform");

    auto &registry = factory_registry();
    std::lock_guard<std::mutex> lock(registry.mutex);
    ensure_default_factories_registered_locked(registry);

    TransformRegistryEntry entry;
    entry.factory = std::move(factory);
    entry.has_signature = true;
    entry.signature = signature;

    auto [_, inserted] = registry.transform_factories.emplace(type, std::move(entry));
    if (!inserted) {
        throw std::runtime_error(
            std::format("GraphCompiler: transform factory already registered for type '{}'", type));
    }
}

void GraphCompiler::register_model_factory(const std::string &type, ModelFactory factory) {
    validate_registration_request(type, static_cast<bool>(factory), "model");

    auto &registry = factory_registry();
    std::lock_guard<std::mutex> lock(registry.mutex);
    ensure_default_factories_registered_locked(registry);

    ModelRegistryEntry entry;
    entry.factory = std::move(factory);

    auto [_, inserted] = registry.model_factories.emplace(type, std::move(entry));
    if (!inserted) {
        throw std::runtime_error(std::format("GraphCompiler: model factory already registered for type '{}'", type));
    }
}

void GraphCompiler::register_model_factory_with_signature(const std::string &type, ModelFactory factory,
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
        throw std::runtime_error(std::format("GraphCompiler: model factory already registered for type '{}'", type));
    }
}

bool GraphCompiler::is_transform_registered(const std::string &type) {
    auto &registry = factory_registry();
    std::lock_guard<std::mutex> lock(registry.mutex);
    ensure_default_factories_registered_locked(registry);
    return registry.transform_factories.find(type) != registry.transform_factories.end();
}

bool GraphCompiler::is_model_registered(const std::string &type) {
    auto &registry = factory_registry();
    std::lock_guard<std::mutex> lock(registry.mutex);
    ensure_default_factories_registered_locked(registry);
    return registry.model_factories.find(type) != registry.model_factories.end();
}

CompiledProgram GraphCompiler::compile(const GraphSpec &spec, SignalNamespace &signal_ns, FunctionNamespace &func_ns,
                                       double expected_dt) {
    CompilationOptions options;
    options.expected_dt = expected_dt;
    return compile(spec, signal_ns, func_ns, options);
}

CompiledProgram GraphCompiler::compile(const GraphSpec &spec, SignalNamespace &signal_ns, FunctionNamespace &func_ns,
                                       const CompilationOptions &options) {
    CompiledProgram program;
    const UnitRegistry &unit_registry = UnitRegistry::instance();

    const bool strict = options.dimensional_policy == DimensionalPolicy::strict;

    std::unordered_map<SignalId, std::string> signal_contracts;
    signal_contracts.reserve(spec.signals.size());

    for (size_t i = 0; i < spec.signals.size(); ++i) {
        const auto &signal_spec = spec.signals[i];
        if (trim_copy(signal_spec.path).empty()) {
            throw std::runtime_error(std::format("GraphCompiler: signals[{}].path must be non-empty", i));
        }

        const std::string unit = trim_copy(signal_spec.unit);
        if (unit.empty()) {
            throw std::runtime_error(std::format("GraphCompiler: signals[{}].unit must be non-empty", i));
        }

        const SignalId id = signal_ns.intern(signal_spec.path);
        const auto existing = signal_contracts.find(id);
        if (existing != signal_contracts.end() && existing->second != unit) {
            throw std::runtime_error(
                std::format("GraphCompiler: duplicate signal contract for '{}' with conflicting units ('{}' vs '{}')",
                            signal_spec.path, existing->second, unit));
        }

        if (!is_unit_known(unit_registry, unit)) {
            if (strict) {
                throw std::runtime_error(
                    std::format("GraphCompiler: unknown unit symbol in signals contract for path '{}': '{}'",
                                signal_spec.path, unit));
            }
            emit_warning(options, std::format("GraphCompiler: unknown unit symbol in permissive mode for signal "
                                              "path '{}': '{}'",
                                              signal_spec.path, unit));
        }

        signal_contracts[id] = unit;
    }

    {
        auto &registry = factory_registry();
        std::lock_guard<std::mutex> lock(registry.mutex);
        ensure_default_factories_registered_locked(registry);

        for (size_t i = 0; i < spec.models.size(); ++i) {
            const auto &model_spec = spec.models[i];
            const auto &entry = resolve_model_entry_or_throw(registry, model_spec.type);
            if (strict && !entry.has_signature) {
                throw std::runtime_error(std::format(
                    "GraphCompiler: strict mode requires signature metadata for model type '{}' (model id '{}')",
                    model_spec.type, model_spec.id));
            }

            if (entry.has_signature) {
                validate_model_signature_contracts(model_spec, entry.signature, signal_ns, signal_contracts,
                                                   unit_registry, options, strict);
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

        const std::string source_unit = resolve_signal_contract_or_empty(signal_contracts, src);
        const std::string target_unit = resolve_signal_contract_or_empty(signal_contracts, tgt);

        if (strict && source_unit.empty()) {
            throw std::runtime_error(std::format(
                "GraphCompiler: strict mode requires declared source signal contract for edge[{}] ('{}' -> '{}')",
                edge_index, edge_spec.source_path, edge_spec.target_path));
        }
        if (strict && target_unit.empty()) {
            throw std::runtime_error(std::format(
                "GraphCompiler: strict mode requires declared target signal contract for edge[{}] ('{}' -> '{}')",
                edge_index, edge_spec.source_path, edge_spec.target_path));
        }

        TransformRegistryEntry transform_entry;
        {
            auto &registry = factory_registry();
            std::lock_guard<std::mutex> lock(registry.mutex);
            ensure_default_factories_registered_locked(registry);
            const auto &entry = resolve_transform_entry_or_throw(registry, edge_spec.transform.type);
            transform_entry = entry;
        }

        if (strict && !transform_entry.has_signature) {
            throw std::runtime_error(std::format(
                "GraphCompiler: strict mode requires signature metadata for transform type '{}' on edge['{}' -> '{}']",
                edge_spec.transform.type, edge_spec.source_path, edge_spec.target_path));
        }

        TransformSpec resolved_transform_spec = edge_spec.transform;

        const bool both_declared = !source_unit.empty() && !target_unit.empty();
        const bool both_known =
            both_declared && is_unit_known(unit_registry, source_unit) && is_unit_known(unit_registry, target_unit);

        const TransformSignature::Contract contract =
            transform_entry.has_signature ? transform_entry.signature.contract : TransformSignature::Contract::preserve;

        if (contract == TransformSignature::Contract::unit_convert) {
            const std::string edge_context = std::format("edge[{}]", edge_index);

            const std::string to_unit = as_string(require_param(edge_spec.transform.params, "to_unit", edge_context),
                                                  edge_context + "/transform/params/to_unit");
            if (!is_unit_known(unit_registry, to_unit)) {
                const std::string message =
                    std::format("GraphCompiler: unit_convert unknown to_unit '{}' at {}", to_unit, edge_context);
                if (strict) {
                    throw std::runtime_error(message);
                }
                emit_warning(options, message);
            }

            std::string from_assertion;
            if (auto it = edge_spec.transform.params.find("from_unit"); it != edge_spec.transform.params.end()) {
                from_assertion = as_string(it->second, edge_context + "/transform/params/from_unit");
            }

            if (!from_assertion.empty() && !source_unit.empty() && from_assertion != source_unit) {
                const std::string message = std::format(
                    "GraphCompiler: unit_convert from_unit assertion '{}' does not match declared "
                    "source unit '{}' at {}",
                    from_assertion, source_unit, edge_context);
                if (strict) {
                    throw std::runtime_error(message);
                }
                emit_warning(options, message);
            }

            if (!target_unit.empty() && target_unit != to_unit) {
                const std::string message = std::format(
                    "GraphCompiler: unit_convert to_unit '{}' does not match declared target unit "
                    "'{}' on edge['{}' -> '{}']",
                    to_unit, target_unit, edge_spec.source_path, edge_spec.target_path);
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
                        throw std::runtime_error(std::format(
                            "GraphCompiler: unit_convert conversion resolution failed on edge['{}' -> '{}']: {}",
                            edge_spec.source_path, edge_spec.target_path, e.what()));
                    }
                    emit_warning(
                        options,
                        std::format(
                            "GraphCompiler: permissive unit_convert conversion resolution failed on edge['{}' -> "
                            "'{}']: {}",
                            edge_spec.source_path, edge_spec.target_path, e.what()));
                }
            }

            resolved_transform_spec.params["__resolved_scale"] = conversion.scale;
            resolved_transform_spec.params["__resolved_offset"] = conversion.offset;
        } else if (both_known) {
            if (contract == TransformSignature::Contract::linear_conditioning) {
                if (strict && source_unit != target_unit) {
                    throw std::runtime_error(
                        std::format("GraphCompiler: strict mode disallows unit-boundary crossing via linear "
                                    "transform on edge['{}' -> '{}']; use unit_convert",
                                    edge_spec.source_path, edge_spec.target_path));
                }

                if (!strict && !has_compatible_dimension_and_kind(unit_registry, source_unit, target_unit)) {
                    emit_warning(options,
                                 std::format("GraphCompiler: permissive linear boundary warning on edge['{}' -> "
                                             "'{}'] (source unit '{}', target unit '{}')",
                                             edge_spec.source_path, edge_spec.target_path, source_unit, target_unit));
                }
            } else {
                if (!has_compatible_dimension_and_kind(unit_registry, source_unit, target_unit)) {
                    const std::string message = std::format(
                        "GraphCompiler: incompatible unit contracts on edge['{}' -> '{}'] (source='{}', "
                        "target='{}')",
                        edge_spec.source_path, edge_spec.target_path, source_unit, target_unit);
                    if (strict) {
                        throw std::runtime_error(message);
                    }
                    emit_warning(options, message);
                }
            }
        } else if (!strict && both_declared && contract == TransformSignature::Contract::linear_conditioning) {
            emit_warning(options,
                         std::format("GraphCompiler: permissive linear boundary warning could not fully validate "
                                     "units on edge['{}' -> '{}'] because one or both units are unknown to registry",
                                     edge_spec.source_path, edge_spec.target_path));
        }

        ITransform *tf = parse_transform(resolved_transform_spec);
        const bool is_delay = edge_spec.transform.type == "delay";
        program.edges.emplace_back(src, tgt, tf, is_delay);
    }

    // Enforce single-writer ownership across model outputs and edge targets.
    std::map<SignalId, std::string> writer_owner;
    auto register_writer = [&writer_owner](SignalId id, const std::string &owner_desc) {
        auto [it, inserted] = writer_owner.emplace(id, owner_desc);
        if (!inserted) {
            throw std::runtime_error(
                std::format("Multiple writers for signal id {}: '{}' conflicts with '{}'", id, it->second, owner_desc));
        }
    };

    for (const auto &edge : program.edges) {
        register_writer(edge.target, "edge_target");
    }

    for (size_t model_index = 0; model_index < program.models.size(); ++model_index) {
        const auto &model = program.models[model_index];
        const auto output_ids = model->output_signal_ids();
        for (SignalId output_id : output_ids) {
            if (output_id == INVALID_SIGNAL) {
                throw std::runtime_error(
                    std::format("Model output_signal_ids() returned INVALID_SIGNAL for model[{}:{}]", model_index,
                                model->describe()));
            }
            if (output_id >= signal_ns.size()) {
                throw std::runtime_error(
                    std::format("Model output_signal_ids() returned non-interned signal id {} for model[{}:{}]",
                                output_id, model_index, model->describe()));
            }
            register_writer(output_id, std::format("model_output[{}:{}]", model_index, model->describe()));
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
            const std::string lhs_unit = resolve_signal_contract_or_empty(signal_contracts, signal_id);
            if (strict && lhs_unit.empty()) {
                throw std::runtime_error(
                    std::format("GraphCompiler: strict mode requires declared unit contract for rule LHS "
                                "signal '{}' in rule '{}'",
                                signal_path, rule_spec.id));
            }
            if (strict && !lhs_unit.empty() && !is_unit_known(unit_registry, lhs_unit)) {
                throw std::runtime_error(
                    std::format("GraphCompiler: strict mode rule LHS signal '{}' uses unknown unit symbol '{}'",
                                signal_path, lhs_unit));
            }
        }

        CompiledRule rule;
        rule.id = rule_spec.id;
        rule.on_error = rule_spec.on_error;

        rule.condition = compile_condition_expr(rule_spec.condition, signal_ns, rule_spec.id);

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
    std::sort(program.signal_unit_contracts.begin(), program.signal_unit_contracts.end(),
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
        throw std::runtime_error("Transform factory returned null for type '" + spec.type + "'");
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
        throw std::runtime_error("Model factory returned null for type '" + spec.type + "'");
    }
    return model.release();
}

void GraphCompiler::topological_sort(std::vector<CompiledEdge> &edges) { topological_sort_edges(edges); }

void GraphCompiler::detect_cycles(const std::vector<CompiledEdge> &edges) {
    detect_cycles_in_non_delay_subgraph(edges);
}

void GraphCompiler::validate_stability(const std::vector<std::unique_ptr<IModel>> &models, double expected_dt) {
    validate_model_stability_limits(models, expected_dt);
}

}  // namespace fluxgraph

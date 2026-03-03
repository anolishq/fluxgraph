#pragma once

#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/graph/spec.hpp"
#include "fluxgraph/model/interface.hpp"
#include "fluxgraph/transform/interface.hpp"
#include <cstddef>
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <utility>
#include <vector>

namespace fluxgraph {

enum class DimensionalPolicy {
  permissive = 0,
  strict = 1,
};

struct TransformSignature {
  enum class Contract {
    preserve,
    linear_conditioning,
    unit_convert,
  };

  Contract contract = Contract::preserve;
};

struct ModelSignature {
  /// Mapping from model parameter name (signal path parameter) to expected unit
  /// symbol.
  std::map<std::string, std::string> signal_param_units;
};

struct CompilationOptions {
  double expected_dt = -1.0;
  DimensionalPolicy dimensional_policy = DimensionalPolicy::permissive;
  std::function<void(const std::string &)> warning_handler;
};

/// Compiled edge with resolved signal IDs and instantiated transform
struct CompiledEdge {
  SignalId source;
  SignalId target;
  std::unique_ptr<ITransform> transform;
  bool is_delay;

  CompiledEdge(SignalId src, SignalId tgt, ITransform *tf, bool delay)
      : source(src), target(tgt), transform(tf), is_delay(delay) {}
};

/// Compiled rule with condition evaluator
struct CompiledRule {
  std::string id;
  std::function<bool(const SignalStore &)> condition;
  std::vector<std::pair<DeviceId, FunctionId>> device_functions;
  std::vector<std::map<std::string, Variant>> args_list;
  std::string on_error;
};

/// Compiled program ready for execution
struct CompiledProgram {
  std::vector<CompiledEdge> edges;
  std::vector<std::unique_ptr<IModel>> models;
  std::vector<CompiledRule> rules;
  std::vector<std::pair<SignalId, std::string>> signal_unit_contracts;
  size_t required_signal_capacity = 0;
  size_t required_command_capacity = 0;
};

/// Compiles GraphSpec into executable CompiledProgram
class GraphCompiler {
public:
  using TransformFactory =
      std::function<std::unique_ptr<ITransform>(const TransformSpec &)>;
  using ModelFactory = std::function<std::unique_ptr<IModel>(
      const ModelSpec &, SignalNamespace &)>;

  GraphCompiler();
  ~GraphCompiler();

  /// Register transform factory by type.
  /// Lifecycle contract:
  /// - type must be non-empty
  /// - factory must be valid (non-empty std::function)
  /// - duplicate type registration is rejected
  static void register_transform_factory(const std::string &type,
                                         TransformFactory factory);
  static void register_transform_factory_with_signature(
      const std::string &type, TransformFactory factory,
      const TransformSignature &signature);

  /// Register model factory by type.
  /// Lifecycle contract:
  /// - type must be non-empty
  /// - factory must be valid (non-empty std::function)
  /// - duplicate type registration is rejected
  static void register_model_factory(const std::string &type,
                                     ModelFactory factory);
  static void
  register_model_factory_with_signature(const std::string &type,
                                        ModelFactory factory,
                                        const ModelSignature &signature);

  /// Query whether a transform/model type is currently registered.
  static bool is_transform_registered(const std::string &type);
  static bool is_model_registered(const std::string &type);

  /// Compile a graph specification
  /// @param spec Graph specification (POD)
  /// @param signal_ns Signal namespace for interning paths
  /// @param func_ns Function namespace for device/function IDs
  /// @param expected_dt Optional expected runtime timestep; if > 0, model
  /// stability validation is applied during compile.
  /// @return Compiled program ready for execution
  /// @throws std::runtime_error on compilation errors
  CompiledProgram compile(const GraphSpec &spec, SignalNamespace &signal_ns,
                          FunctionNamespace &func_ns,
                          double expected_dt = -1.0);

  /// Compile using explicit compilation options.
  CompiledProgram compile(const GraphSpec &spec, SignalNamespace &signal_ns,
                          FunctionNamespace &func_ns,
                          const CompilationOptions &options);

  // Public for testing
  ITransform *parse_transform(const TransformSpec &spec);
  IModel *parse_model(const ModelSpec &spec, SignalNamespace &ns);

private:
  // Scientific rigor: Graph validation
  void topological_sort(std::vector<CompiledEdge> &edges);
  void detect_cycles(const std::vector<CompiledEdge> &edges);
  void validate_stability(const std::vector<std::unique_ptr<IModel>> &models,
                          double expected_dt);
};

} // namespace fluxgraph

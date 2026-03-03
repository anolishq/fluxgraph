#include "fluxgraph/engine.hpp"
#include <limits>
#include <stdexcept>

namespace fluxgraph {

Engine::Engine() : loaded_(false) {}

Engine::~Engine() = default;

void Engine::load(CompiledProgram program) {
  constexpr size_t kCommandBacklogTicks = 4;

  required_signal_capacity_ = program.required_signal_capacity;
  required_command_capacity_ = program.required_command_capacity;
  signal_unit_contracts_ = std::move(program.signal_unit_contracts);
  edges_ = std::move(program.edges);
  models_ = std::move(program.models);
  rules_ = std::move(program.rules);
  pending_commands_.clear();

  size_t backlog_capacity = required_command_capacity_;
  if (required_command_capacity_ > 0 &&
      required_command_capacity_ <=
          std::numeric_limits<size_t>::max() / kCommandBacklogTicks) {
    backlog_capacity = required_command_capacity_ * kCommandBacklogTicks;
  }
  pending_commands_.reserve(backlog_capacity);
  loaded_ = true;
}

void Engine::tick(double dt, SignalStore &store) {
  if (!loaded_) {
    throw std::runtime_error("Engine: No program loaded");
  }
  if (dt <= 0.0) {
    throw std::runtime_error("Engine: dt must be positive");
  }

  if (required_signal_capacity_ > 0 &&
      store.capacity() < required_signal_capacity_) {
    store.reserve(required_signal_capacity_);
  }

  for (const auto &contract : signal_unit_contracts_) {
    store.declare_unit(contract.first, contract.second);
  }

  // Runtime stability contract: enforce model limits for supplied dt.
  for (const auto &model : models_) {
    const double limit = model->compute_stability_limit();
    if (dt > limit) {
      throw std::runtime_error("Engine: stability violation for model '" +
                               model->describe() +
                               "' (dt=" + std::to_string(dt) +
                               " exceeds limit=" + std::to_string(limit) + ")");
    }
  }

  // Stage 1: Input boundary freeze
  // (external writes are assumed complete before tick entry)

  // Stage 2: Update physics models
  update_models(dt, store);

  // Stage 3: Apply transforms in topological order with immediate propagation
  process_edges(dt, store);

  // Stage 4: Commit outputs (future: validation, dirty flags)
  commit_outputs(store);

  // Stage 5: Evaluate rules and emit commands
  evaluate_rules(store);
}

std::vector<Command> Engine::drain_commands() {
  std::vector<Command> drained;
  drained.reserve(pending_commands_.size());

  for (const auto &pending : pending_commands_) {
    Command cmd;
    cmd.device = pending.device;
    cmd.function = pending.function;
    if (pending.args != nullptr) {
      cmd.args = *pending.args;
    }
    drained.push_back(std::move(cmd));
  }

  pending_commands_.clear();
  return drained;
}

void Engine::reset() {
  // Reset all models
  for (auto &model : models_) {
    model->reset();
  }

  // Reset all transforms
  for (auto &edge : edges_) {
    edge.transform->reset();
  }

  // Clear pending commands
  pending_commands_.clear();
}

void Engine::process_edges(double dt, SignalStore &store) {
  for (auto &edge : edges_) {
    const double source_value = store.read_value(edge.source);
    double output = edge.transform->apply(source_value, dt);
    store.write_with_contract_unit(edge.target, output);
  }
}

void Engine::update_models(double dt, SignalStore &store) {
  for (auto &model : models_) {
    model->tick(dt, store);
  }
}

void Engine::commit_outputs(SignalStore &store) {
  // Future: Signal validation, dirty flag clearing, etc.
  // For now, this is a no-op
  (void)store;
}

void Engine::evaluate_rules(SignalStore &store) {
  for (const auto &rule : rules_) {
    if (rule.condition(store)) {
      // Emit commands for all actions
      for (size_t i = 0; i < rule.device_functions.size(); ++i) {
        if (pending_commands_.size() >= pending_commands_.capacity()) {
          throw std::runtime_error(
              "Engine: command backlog capacity exceeded; call "
              "drain_commands() more frequently");
        }

        PendingCommand cmd;
        cmd.device = rule.device_functions[i].first;
        cmd.function = rule.device_functions[i].second;
        cmd.args = &rule.args_list[i];
        pending_commands_.push_back(cmd);
      }
    }
  }
}

} // namespace fluxgraph

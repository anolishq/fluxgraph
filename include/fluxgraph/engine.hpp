#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>
#include <utility>
#include <vector>

#include "fluxgraph/command.hpp"
#include "fluxgraph/graph/compiler.hpp"

namespace fluxgraph {

/// Main simulation engine with five-stage tick execution
/// Execution model:
/// 1. Input boundary freeze (external writes before tick begin)
/// 2. Models: Update physics models
/// 3. Edges: Apply transforms in topological order (immediate propagation)
/// 4. Commit: Finalize signal values
/// 5. Rules: Evaluate conditions and emit commands
class Engine {
public:
    Engine();
    ~Engine();

    /// Load a compiled program into the engine
    /// @param program Compiled graph program
    void load(CompiledProgram program);

    /// Execute one simulation tick
    /// @param dt Time step in seconds
    /// @param store Signal storage
    void tick(double dt, SignalStore &store);

    /// Drain queued commands (for external processing)
    /// Runtime contract: drain frequently enough to avoid command backlog
    /// overflow during tick().
    /// @return All commands generated since last drain
    std::vector<Command> drain_commands();

    /// Reset all models and transforms to initial state
    void reset();

    /// Check if a program is loaded
    bool is_loaded() const { return loaded_; }

    /// Called with a rule's id and a message when the rule hits an error during
    /// tick(). The rule's on_error is log_and_continue: its remaining commands
    /// for that tick are dropped and the tick carries on. Today the only such
    /// error is command-backlog overflow. Optional (#141).
    using RuleErrorHandler = std::function<void(const std::string &rule_id, const std::string &message)>;
    void set_rule_error_handler(RuleErrorHandler handler) { rule_error_handler_ = std::move(handler); }

    /// Commands dropped by rule errors since construction, whether or not a
    /// handler is set.
    std::uint64_t dropped_rule_commands() const { return dropped_rule_commands_; }

private:
    struct PendingCommand {
        DeviceId device = INVALID_DEVICE;
        FunctionId function = INVALID_FUNCTION;
        const std::map<std::string, Variant> *args = nullptr;
    };

    bool loaded_;
    size_t required_signal_capacity_ = 0;
    size_t required_command_capacity_ = 0;
    std::vector<std::pair<SignalId, std::string>> signal_unit_contracts_;
    std::vector<CompiledEdge> edges_;
    std::vector<std::unique_ptr<IModel>> models_;
    std::vector<CompiledRule> rules_;
    std::vector<PendingCommand> pending_commands_;
    RuleErrorHandler rule_error_handler_;
    std::uint64_t dropped_rule_commands_ = 0;

    // Five-stage tick implementation
    void process_edges(double dt, SignalStore &store);
    void update_models(double dt, SignalStore &store);
    void commit_outputs(SignalStore &store);
    void evaluate_rules(SignalStore &store);
};

}  // namespace fluxgraph

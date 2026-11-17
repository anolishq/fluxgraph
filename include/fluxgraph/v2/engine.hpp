#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <span>
#include <string_view>
#include <vector>

#include "fluxgraph/v2/setting.hpp"
#include "fluxgraph/v2/status.hpp"
#include "fluxgraph/v2/value.hpp"

namespace fluxgraph::v2 {

/// What a call to tick says of itself (rule 6.10).
struct TickReport {
    /// How many ticks the call ran. Zero where none was due: nothing else here means anything then.
    std::uint32_t ran = 0;
    /// The call was a gap (section 8): one tick ran, and those before it were passed over.
    bool gap = false;
    /// False at a gap where nobody knows how many ticks were passed over.
    bool skipped_known = true;
    /// How many ticks were passed over. Zero where the call was not a gap.
    std::int64_t skipped = 0;
    /// The number and the time of the last tick the call ran.
    std::int64_t tick = 0;
    Time time = 0;
    /// Writes thrown away (rule 6.8) since the last call that ran a tick.
    std::uint64_t thrown = 0;
    /// Writes that still wait, over every input.
    std::uint64_t waiting = 0;
};

/// A published output: a name the graph's `out` gives, and what it is at the last tick run.
struct Output {
    std::string_view name;
    Value value;
};

/// A state written out by Engine::save (rule 8.2), for the same graph to take back.
struct SavedState {
    std::vector<std::uint8_t> bytes;
};

/// A compiled graph and its state. Calls and writes are made one at a time (rule 6.12).
class Engine {
public:
    /// Compiles a graph: a map in the shape of section 9 of the specification.
    static Result<Engine> compile(const Setting &graph);

    Engine(Engine &&) noexcept;
    Engine &operator=(Engine &&) noexcept;
    ~Engine();

    /// The graph's period.
    Time period() const;

    /// Writes an input (rule 6.7): a state, a value, and the time it was sampled. A value given with a state
    /// that is not usable is not looked at.
    Status write(std::string_view input, State state, double value, Time at);
    Status write(std::string_view input, State state, bool value, Time at);
    /// A write with no value: `bad` or `not_ready`, and the time that became so.
    Status write(std::string_view input, State state, Time at);

    /// Runs every tick that is due at `now` (rule 6.6).
    Result<TickReport> tick(Time now);

    /// Every published output, in the order the graph declares them, as the last tick run gave them. Before any
    /// tick each is `not_ready`. The span and the names in it last as long as the engine.
    std::span<const Output> outputs() const;

    /// The host's clock has stepped, and nobody knows how long the graph was away (rule 8.5).
    void rebase();
    /// The same, where the host knows: `away` is counted from the time of the last tick run.
    Status rebase(Time away);

    /// Back to the initial state (rule 8.1).
    void reset();

    SavedState save() const;
    Status restore(const SavedState &state);

private:
    struct Impl;
    explicit Engine(std::unique_ptr<Impl> impl);
    std::unique_ptr<Impl> impl_;
};

}  // namespace fluxgraph::v2

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
///
/// Every whole number is little-endian:
///
///     u64  the mark: the eight bytes "FGSTATE2"
///     u32  the format version
///     u64  the graph's fingerprint
///     u64  the number of the last tick run, or all ones where none has
///     u32  how many loops, then for each a byte and a u64: its doubt
///     u32  how many blocks, then for each a u32 length and that many bytes: what the block remembers
///
/// The version goes up with any change to what the engine or a block writes. A state of another version, of
/// another graph, cut short, or with a block's part not of the length that block reads is refused, and the engine
/// is left as it was. Nothing is promised of one version reading another's: a state is for the library that
/// saved it.
struct SavedState {
    std::vector<std::uint8_t> bytes;
};

/// An input of a compiled graph, looked up once by Engine::input so that a write need not look its name up
/// again. It is good for any engine compiled from the same graph, and is refused by one of another.
class InputHandle {
public:
    InputHandle() = default;

private:
    friend class Engine;
    InputHandle(std::uint64_t graph, std::size_t index) : graph_(graph), index_(index) {}
    std::uint64_t graph_ = 0;  // the fingerprint of the graph it is of
    std::size_t index_ = 0;
};

/// A compiled graph and its state. Calls and writes are made one at a time (rule 6.12).
///
/// Memory. `tick` allocates nothing. A write that is accepted allocates nothing while no more than 1,024 writes
/// wait on its input, or the graph's `max_waiting` where that is less: room for that many is taken when the graph
/// is compiled. `compile`, `save`, `restore`, `reset` and the message of anything refused allocate. Where memory
/// cannot be had the core does nothing about it: `std::bad_alloc` is thrown, or the process ends where exceptions
/// are off.
class Engine {
public:
    /// Compiles a graph: a map in the shape of section 9 of the specification.
    static Result<Engine> compile(const Setting &graph);

    Engine(Engine &&) noexcept;
    Engine &operator=(Engine &&) noexcept;
    ~Engine();

    /// The graph's period.
    Time period() const;

    /// The handle of an input, or a refusal where the graph has no input of that name.
    Result<InputHandle> input(std::string_view name) const;

    /// Writes an input (rule 6.7): a state, a value, and the time it was sampled. A value given with a state
    /// that is not usable is not looked at. By handle or by name: the two do the same, and a handle that is not
    /// of this graph is refused as a name that is not an input is.
    Status write(InputHandle input, State state, double value, Time at);
    Status write(InputHandle input, State state, bool value, Time at);
    Status write(InputHandle input, State state, Time at);
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
    Status owns(InputHandle input) const;
    std::unique_ptr<Impl> impl_;
};

}  // namespace fluxgraph::v2

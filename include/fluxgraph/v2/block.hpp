#pragma once

#include <cstddef>
#include <cstdint>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include "fluxgraph/v2/setting.hpp"
#include "fluxgraph/v2/status.hpp"
#include "fluxgraph/v2/value.hpp"

namespace fluxgraph::v2 {

/// An input port as a configured block declares it (rule 4.3).
struct InputPort {
    std::string name;
    /// Empty where the port takes either type, as a delay's and a formula's do.
    std::optional<Type> type;
    bool required = true;
    /// Read only in the second phase (rule 4.4). Declared by the block as it is configured, not by its type.
    bool deferred = false;
};

/// An output port as a configured block declares it.
struct OutputPort {
    std::string name;
    /// Empty until the block can say, which may wait on the types of its inputs (see Block::bind).
    std::optional<Type> type;
    /// The block gives this output its sample time itself (rule 3.7), as a formula and a delay do. Otherwise
    /// the engine gives a usable output the time of the tick.
    bool own_sample_time = false;
};

/// How one port of a block's `in` is connected: the compiler has not resolved signals when a block is configured.
struct Connection {
    std::string_view port;
    /// Given a constant in place of a signal (rule 4.7).
    bool constant = false;
};

/// What a block type is given to configure one block.
struct BlockSetup {
    std::string_view id;
    /// The block's `settings`: a map, with no keys where the graph gave none.
    const Setting *settings = nullptr;
    /// The ports the graph's `in` names, in the order it names them.
    std::span<const Connection> connections;
    /// The graph's period, more than zero.
    Time period = 0;
};

/// The tick a block is run at.
struct Tick {
    std::int64_t number = 0;
    Time time = 0;
};

/// Ticks nobody saw (rule 8.6).
struct Gap {
    /// False where nobody knows how many ticks were passed over: `ticks` then means nothing.
    bool known = false;
    std::uint64_t ticks = 0;
    /// A rebase and not a stall: every sample time the block remembers or holds is forgotten (rule 8.5).
    bool rebase = false;
};

/// Writes what a block remembers (rule 8.2).
class StateWriter {
public:
    void u64(std::uint64_t value);
    void f64(double value);
    void flag(bool value);
    void value(const Value &value);

    std::vector<std::uint8_t> &bytes() { return bytes_; }

private:
    std::vector<std::uint8_t> bytes_;
};

/// Reads back what a StateWriter wrote. Each call is false where the state ends early or holds what a writer
/// never writes.
class StateReader {
public:
    explicit StateReader(std::span<const std::uint8_t> bytes) : bytes_(bytes) {}

    bool u64(std::uint64_t &value);
    bool f64(double &value);
    bool flag(bool &value);
    bool value(Value &value);
    bool at_end() const { return bytes_.empty(); }

private:
    std::span<const std::uint8_t> bytes_;
};

/// One block of a compiled graph (section 4). The engine drives it and knows nothing of what it is.
///
/// A tick has two phases (rule 4.4). `give` is the first: the block gives its outputs from what it remembers and
/// its direct inputs. `update` is the second: it takes in every input, deferred ones among them. Neither
/// allocates. A block reads only what it is handed and writes only its own outputs (rule 4.5).
class Block {
public:
    virtual ~Block() = default;

    virtual std::span<const InputPort> inputs() const = 0;
    virtual std::span<const OutputPort> outputs() const = 0;

    /// Tells the block the types of its inputs, in the order of inputs(); an entry is empty for an input left
    /// unconnected, and for one whose type the compiler does not know yet. The block refuses a type it cannot
    /// take and fills in what it can of its outputs' types. Called again each time more is known, and a last
    /// time with every connected input's type known.
    virtual Status bind(std::span<const std::optional<Type>> input_types) = 0;

    /// Told, when the graph is compiled, that the block can reach its own input through some chain of inputs,
    /// direct or deferred. A block that cannot stand on a loop as it is configured refuses (rule 5.4).
    virtual Status on_loop() { return {}; }

    /// The first phase. `in` is in the order of inputs(); an entry for a deferred input, or for an input left
    /// unconnected, is `not_ready` and is not to be used. `out` is in the order of outputs(). The engine sees
    /// to rule 3.6, to fallbacks (section 7.10) and to the sample time of an output that is not the block's own.
    virtual void give(const Tick &tick, std::span<const Value> in, std::span<Value> out) = 0;

    /// The second phase: every input as it is at this tick.
    virtual void update(const Tick &tick, std::span<const Value> in) = 0;

    /// Before the tick a gap runs: do to what is remembered what the ticks passed over would have done
    /// (rule 8.6).
    virtual void gap(const Gap &gap) = 0;

    /// Back to the state the block was made in (rule 8.1).
    virtual void reset() = 0;

    virtual void save(StateWriter &writer) const = 0;
    /// False where the state is not one this block wrote. The block may then be left in any state: the engine
    /// puts back what it had.
    virtual bool restore(StateReader &reader) = 0;
};

/// The block types this build has, and those of the specification's catalogue that it does not have yet.
std::span<const std::string_view> built_block_types();
std::span<const std::string_view> planned_block_types();

}  // namespace fluxgraph::v2

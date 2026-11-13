#pragma once

// A compiled graph: what the compiler hands the engine.

#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "fluxgraph/v2/block.hpp"
#include "fluxgraph/v2/setting.hpp"
#include "fluxgraph/v2/status.hpp"
#include "fluxgraph/v2/value.hpp"

namespace fluxgraph::v2::detail {

/// An input from outside (section 7.2). Input i has signal slot i.
struct InputSpec {
    std::string name;
    Type type = Type::number;
    bool has_max_age = false;
    Time max_age = 0;
    Time max_ahead = 0;
    bool has_initial = false;
    Value initial;
};

/// Where one input port of a block gets its value.
struct Source {
    enum class Kind : std::uint8_t { unconnected, constant, signal };
    Kind kind = Kind::unconnected;
    bool deferred = false;
    std::size_t slot = 0;
    Value constant;
};

struct OutputSpec {
    Type type = Type::number;
    bool own_sample_time = false;
    bool has_fallback = false;
    Value fallback;
};

struct BlockSpec {
    std::string id;
    std::unique_ptr<Block> block;
    std::vector<Source> sources;      // one per input port
    std::vector<OutputSpec> outputs;  // one per output port
    std::size_t first_slot = 0;       // output port i has signal slot first_slot + i
};

struct Published {
    std::string name;
    std::size_t slot = 0;
};

struct Program {
    Time period = 0;
    std::uint32_t max_catch_up = 100;
    std::uint32_t max_waiting = 1024;
    std::vector<InputSpec> inputs;
    std::vector<BlockSpec> blocks;  // in the one evaluation order (section 5)
    std::vector<Published> published;
    std::vector<Type> slot_types;
    /// Stands for the graph in a saved state (rule 8.2).
    std::uint64_t fingerprint = 0;
};

Result<Program> compile_graph(const Setting &graph);

}  // namespace fluxgraph::v2::detail

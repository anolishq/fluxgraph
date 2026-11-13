// The compiler: a graph description in, a Program out, or the one fault the graph is refused for (rule 9.6).

#include <algorithm>
#include <cmath>
#include <format>
#include <map>
#include <optional>
#include <set>
#include <string_view>
#include <utility>

#include "blocks.hpp"
#include "exact.hpp"
#include "program.hpp"

namespace fluxgraph::v2::detail {

namespace {

using Kind = Setting::Kind;

constexpr std::int64_t kMaxCount = 2'147'483'647;  // Appendix A: the width of a count a graph gives

// One port of a block's `in`, before signals are resolved.
struct Wire {
    std::string port;
    bool constant = false;
    Value value;
    std::string signal;
};

// A block as the graph gives it, until every block is known.
struct Draft {
    std::string id;
    std::unique_ptr<Block> block;
    std::vector<Wire> wires;
    std::vector<Source> sources;
    std::vector<int> readers_of;  // for each input port, the draft whose output it reads, or -1
    std::vector<OutputSpec> outputs;
    std::size_t first_slot = 0;
};

bool has_key(std::initializer_list<std::string_view> keys, std::string_view key) {
    return std::find(keys.begin(), keys.end(), key) != keys.end();
}

// Rule 9.5: an unknown key is refused. Null where every key is known.
const std::string *unknown_key(const Setting &map, std::initializer_list<std::string_view> keys) {
    for (const std::string &key : map.as_map().keys) {
        if (!has_key(keys, key)) {
            return &key;
        }
    }
    return nullptr;
}

// A length the engine keeps as a time (rules 6.2 and 9.3): whole nanoseconds, in 64 bits.
Status kept_length(const Setting &setting, std::string_view what, Time &nanoseconds) {
    Length length;
    if (!setting.is(Kind::text) || !parse_length(setting.as_text(), length)) {
        return graph_error(std::format("{} is {}, and has to be a length of time: a number and a unit, as in '2s'",
                                       what, setting.shown()));
    }
    switch (whole_nanoseconds(length, nanoseconds)) {
        case WholeLength::not_whole:
            return graph_error(
                std::format("{} is {}, which is not a whole number of nanoseconds", what, setting.shown()));
        case WholeLength::too_large:
            return graph_error(
                std::format("{} is {}, which does not fit in 64 bits of nanoseconds", what, setting.shown()));
        case WholeLength::ok:
            break;
    }
    return {};
}

// Half a period, rounded up: a whole length is not less than half a period exactly when it is not less than this.
Time half_period(Time period) { return period / 2 + period % 2; }

Status count_setting(const Setting &graph, std::string_view key, std::uint32_t &value) {
    const Setting *setting = graph.find(key);
    if (setting == nullptr) {
        return {};
    }
    if (!setting->is(Kind::whole) || setting->as_whole() < 1 || setting->as_whole() > kMaxCount) {
        return graph_error(
            std::format("{} is {}, and has to be a whole number from 1 to {}", key, setting->shown(), kMaxCount));
    }
    value = static_cast<std::uint32_t>(setting->as_whole());
    return {};
}

// A constant of a port, an initial value or a fallback: a finite number, or true or false.
bool read_constant(const Setting &setting, Value &value) {
    if (setting.is(Kind::boolean)) {
        value = Value::of(setting.as_boolean());
        return true;
    }
    if (setting.is(Kind::whole)) {
        value = Value::of(static_cast<double>(setting.as_whole()));
        return true;
    }
    if (setting.is(Kind::number) && std::isfinite(setting.as_number())) {
        value = Value::of(setting.as_number());
        return true;
    }
    return false;
}

Status read_inputs(const Setting &graph, Program &program) {
    const Setting *inputs = graph.find("inputs");
    if (inputs == nullptr) {
        return {};
    }
    if (!inputs->is(Kind::map)) {
        return graph_error(std::format("inputs is {}, and has to be a map of inputs", inputs->kind_name()));
    }
    const Setting::Map &map = inputs->as_map();
    for (std::size_t i = 0; i < map.keys.size(); ++i) {
        const std::string &name = map.keys[i];
        const Setting &given = map.values[i];
        if (name.empty()) {
            return graph_error("an input has an empty name");
        }
        for (const InputSpec &other : program.inputs) {
            if (other.name == name) {
                return graph_error(std::format("input '{}' is declared twice", name));
            }
        }
        if (!given.is(Kind::map)) {
            return graph_error(std::format("input '{}' is {}, and has to be a map", name, given.kind_name()));
        }
        if (const std::string *key = unknown_key(given, {"type", "max_age", "unit", "initial", "max_ahead"})) {
            return graph_error(std::format("input '{}': '{}' is not a key of an input", name, *key));
        }
        InputSpec input;
        input.name = name;
        if (const Setting *type = given.find("type")) {
            if (type->is(Kind::text) && type->as_text() == "boolean") {
                input.type = Type::boolean;
            } else if (!type->is(Kind::text) || type->as_text() != "number") {
                return graph_error(
                    std::format("input '{}': type is {}, and has to be number or boolean", name, type->shown()));
            }
        }
        const Setting *max_age = given.find("max_age");
        if (max_age == nullptr) {
            return graph_error(std::format("input '{}' has no max_age: a length of time, or none", name));
        }
        if (!max_age->is(Kind::text) || max_age->as_text() != "none") {
            if (Status status = kept_length(*max_age, std::format("input '{}': max_age", name), input.max_age);
                !status) {
                return status;
            }
            if (input.max_age < half_period(program.period)) {  // section 7.2
                return graph_error(
                    std::format("input '{}': max_age is {}, which is less than half a period", name, max_age->shown()));
            }
            input.has_max_age = true;
        }
        input.max_ahead = program.period;  // rule 6.8: one period unless given
        if (const Setting *max_ahead = given.find("max_ahead")) {
            if (Status status = kept_length(*max_ahead, std::format("input '{}': max_ahead", name), input.max_ahead);
                !status) {
                return status;
            }
            if (input.max_ahead < half_period(program.period)) {
                return graph_error(std::format("input '{}': max_ahead is {}, which is less than half a period", name,
                                               max_ahead->shown()));
            }
        }
        if (const Setting *unit = given.find("unit"); unit != nullptr && !unit->is(Kind::text)) {
            return graph_error(std::format("input '{}': unit is {}, and has to be text", name, unit->shown()));
        }
        if (const Setting *initial = given.find("initial")) {
            if (!read_constant(*initial, input.initial) || input.initial.type != input.type) {
                return graph_error(std::format("input '{}': initial is {}, and has to be a {}", name, initial->shown(),
                                               input.type == Type::number ? "finite number" : "boolean"));
            }
            input.has_initial = true;
        }
        program.inputs.push_back(std::move(input));
    }
    return {};
}

std::size_t port_index(std::span<const InputPort> ports, std::string_view name) {
    for (std::size_t i = 0; i < ports.size(); ++i) {
        if (ports[i].name == name) {
            return i;
        }
    }
    return ports.size();
}

std::size_t port_index(std::span<const OutputPort> ports, std::string_view name) {
    for (std::size_t i = 0; i < ports.size(); ++i) {
        if (ports[i].name == name) {
            return i;
        }
    }
    return ports.size();
}

// Reads one entry of `blocks` as far as can be done without the other blocks: its id, its type, what its `in`
// names, and its settings, which configure the block.
Status read_block(const Setting &given, std::size_t position, Time period, const std::vector<Draft> &before,
                  Draft &draft) {
    if (!given.is(Kind::map)) {
        return graph_error(
            std::format("block {} of the graph is {}, and has to be a map", position + 1, given.kind_name()));
    }
    const Setting *id = given.find("id");
    if (id == nullptr) {
        return graph_error(std::format("block {} of the graph has no id", position + 1));
    }
    if (!id->is(Kind::text) || id->as_text().empty()) {
        return graph_error(std::format("block {} of the graph has the id {}, {}: an id is text, and not empty",
                                       position + 1, id->shown(), id->kind_name()));
    }
    draft.id = id->as_text();
    if (draft.id.find('.') != std::string::npos) {
        return graph_error(std::format("block '{}': an id holds no dot", draft.id));
    }
    for (const Draft &other : before) {
        if (other.id == draft.id) {
            return graph_error(std::format("block '{}': another block has this id", draft.id));
        }
    }
    if (const std::string *key = unknown_key(given, {"id", "type", "in", "settings", "out", "fallback"})) {
        return graph_error(std::format("block '{}': '{}' is not a key of a block", draft.id, *key));
    }
    const Setting *type = given.find("type");
    if (type == nullptr || !type->is(Kind::text)) {
        return graph_error(std::format("block '{}' has no type", draft.id));
    }
    const BlockMaker maker = find_block_maker(type->as_text());
    if (maker == nullptr) {
        if (is_planned_block_type(type->as_text())) {
            return Error{Errc::block_type_not_built,
                         std::format("block '{}': type '{}' is in the catalogue, and this build does not have it yet",
                                     draft.id, type->as_text())};
        }
        return graph_error(std::format("block '{}': '{}' is not a block type", draft.id, type->as_text()));
    }

    static const Setting kNoKeys;
    const Setting *in = given.find("in");
    if (in != nullptr && !in->is(Kind::map)) {
        return graph_error(std::format("block '{}': in is {}, and has to be a map", draft.id, in->kind_name()));
    }
    const Setting::Map &in_map = (in != nullptr ? *in : kNoKeys).as_map();
    for (std::size_t i = 0; i < in_map.keys.size(); ++i) {
        Wire wire;
        wire.port = in_map.keys[i];
        const Setting &to = in_map.values[i];
        if (wire.port.empty()) {
            return graph_error(std::format("block '{}': an input port has an empty name", draft.id));
        }
        for (const Wire &other : draft.wires) {
            if (other.port == wire.port) {
                return graph_error(std::format("block '{}': input '{}' is connected twice", draft.id, wire.port));
            }
        }
        if (to.is(Kind::text)) {
            if (to.as_text().empty()) {
                return graph_error(
                    std::format("block '{}': input '{}' is connected to a signal with no name", draft.id, wire.port));
            }
            wire.signal = to.as_text();
        } else if (read_constant(to, wire.value)) {  // rule 4.7
            wire.constant = true;
        } else {
            return graph_error(
                std::format("block '{}': input '{}' is given {}, and takes the name of a signal, a finite number, or "
                            "true or false",
                            draft.id, wire.port, to.shown()));
        }
        draft.wires.push_back(std::move(wire));
    }

    const Setting *settings = given.find("settings");
    if (settings != nullptr && !settings->is(Kind::map)) {
        return graph_error(
            std::format("block '{}': settings is {}, and has to be a map", draft.id, settings->kind_name()));
    }
    std::vector<Connection> connections;
    for (const Wire &wire : draft.wires) {
        connections.push_back(Connection{wire.port, wire.constant});
    }
    BlockSetup setup;
    setup.id = draft.id;
    setup.settings = settings != nullptr ? settings : &kNoKeys;
    setup.connections = connections;
    setup.period = period;
    Result<std::unique_ptr<Block>> made = maker(setup);
    if (!made) {
        return made.error();
    }
    draft.block = std::move(made.value());

    // Rule 9.5: an unknown port in `in`, and a required input left unconnected.
    const std::span<const InputPort> ports = draft.block->inputs();
    draft.sources.assign(ports.size(), Source{});
    draft.readers_of.assign(ports.size(), -1);
    for (const Wire &wire : draft.wires) {
        if (port_index(ports, wire.port) == ports.size()) {
            return graph_error(
                std::format("block '{}': '{}' is not an input of a {}", draft.id, wire.port, type->as_text()));
        }
    }
    for (std::size_t i = 0; i < ports.size(); ++i) {
        const bool connected = std::any_of(draft.wires.begin(), draft.wires.end(),
                                           [&](const Wire &wire) { return wire.port == ports[i].name; });
        if (ports[i].required && !connected) {
            return graph_error(std::format("block '{}': its input '{}' is not connected", draft.id, ports[i].name));
        }
        draft.sources[i].deferred = ports[i].deferred;
    }

    const std::span<const OutputPort> outputs = draft.block->outputs();
    draft.outputs.assign(outputs.size(), OutputSpec{});
    for (const char *key : {"out", "fallback"}) {
        const Setting *map = given.find(key);
        if (map == nullptr) {
            continue;
        }
        if (!map->is(Kind::map)) {
            return graph_error(
                std::format("block '{}': {} is {}, and has to be a map", draft.id, key, map->kind_name()));
        }
        for (const std::string &port : map->as_map().keys) {
            if (port_index(outputs, port) == outputs.size()) {
                return graph_error(std::format("block '{}': {} names '{}', which is not an output of a {}", draft.id,
                                               key, port, type->as_text()));
            }
        }
    }
    return {};
}

// FNV-1a over the graph as it was given, so that a saved state knows its graph again (rule 8.2).
void fingerprint(const Setting &setting, std::uint64_t &hash) {
    const auto mix = [&hash](std::string_view bytes) {
        for (char c : bytes) {
            hash = (hash ^ static_cast<unsigned char>(c)) * 0x100000001b3ULL;
        }
        hash = (hash ^ 0xFFu) * 0x100000001b3ULL;  // an end mark, so that "ab","c" is not "a","bc"
    };
    mix(std::format("{}", static_cast<int>(setting.kind())));
    switch (setting.kind()) {
        case Kind::whole:
            mix(std::format("{}", setting.as_whole()));
            break;
        case Kind::number:
            mix(std::format("{:a}", setting.as_number()));
            break;
        case Kind::boolean:
            mix(setting.as_boolean() ? "1" : "0");
            break;
        case Kind::text:
            mix(setting.as_text());
            break;
        case Kind::list:
            mix(std::format("{}", setting.as_list().size()));
            for (const Setting &item : setting.as_list()) {
                fingerprint(item, hash);
            }
            break;
        case Kind::map:
            mix(std::format("{}", setting.as_map().keys.size()));
            for (std::size_t i = 0; i < setting.as_map().keys.size(); ++i) {
                mix(setting.as_map().keys[i]);
                fingerprint(setting.as_map().values[i], hash);
            }
            break;
    }
}

// Whether `from` can reach `to` by following what each block reads, direct or deferred.
bool reads_through(const std::vector<Draft> &drafts, int from, int to) {
    std::vector<bool> seen(drafts.size(), false);
    std::vector<int> stack = {from};
    while (!stack.empty()) {
        const int at = stack.back();
        stack.pop_back();
        for (int read : drafts[static_cast<std::size_t>(at)].readers_of) {
            if (read == to) {
                return true;
            }
            if (read >= 0 && !seen[static_cast<std::size_t>(read)]) {
                seen[static_cast<std::size_t>(read)] = true;
                stack.push_back(read);
            }
        }
    }
    return false;
}

// Section 5: one order, in which a block comes after every block it reads through a direct input, with ties
// broken by block id. A loop of direct inputs is refused, and the blocks on it named.
Status evaluation_order(const std::vector<Draft> &drafts, std::vector<std::size_t> &order) {
    std::vector<std::size_t> waits_on(drafts.size(), 0);
    for (std::size_t i = 0; i < drafts.size(); ++i) {
        for (std::size_t port = 0; port < drafts[i].readers_of.size(); ++port) {
            if (drafts[i].readers_of[port] >= 0 && !drafts[i].sources[port].deferred) {
                ++waits_on[i];
            }
        }
    }
    std::set<std::pair<std::string_view, std::size_t>> ready;
    for (std::size_t i = 0; i < drafts.size(); ++i) {
        if (waits_on[i] == 0) {
            ready.emplace(drafts[i].id, i);
        }
    }
    while (!ready.empty()) {
        const std::size_t next = ready.begin()->second;
        ready.erase(ready.begin());
        order.push_back(next);
        for (std::size_t i = 0; i < drafts.size(); ++i) {
            for (std::size_t port = 0; port < drafts[i].readers_of.size(); ++port) {
                if (drafts[i].readers_of[port] == static_cast<int>(next) && !drafts[i].sources[port].deferred) {
                    if (--waits_on[i] == 0) {
                        ready.emplace(drafts[i].id, i);
                    }
                }
            }
        }
    }
    if (order.size() == drafts.size()) {
        return {};
    }
    // Every block left reads, directly, another block left. Walking back from any of them comes round.
    std::size_t at = 0;
    while (waits_on[at] == 0) {
        ++at;
    }
    std::vector<std::size_t> walk;
    for (;;) {
        const auto seen = std::find(walk.begin(), walk.end(), at);
        if (seen != walk.end()) {
            std::string names;
            for (auto it = seen; it != walk.end(); ++it) {
                names += std::format("{}'{}'", names.empty() ? "" : ", ", drafts[*it].id);
            }
            return graph_error(std::format("a loop of direct inputs, with no deferred input on it: blocks {}", names));
        }
        walk.push_back(at);
        for (std::size_t port = 0; port < drafts[at].readers_of.size(); ++port) {
            const int read = drafts[at].readers_of[port];
            if (read >= 0 && !drafts[at].sources[port].deferred && waits_on[static_cast<std::size_t>(read)] != 0) {
                at = static_cast<std::size_t>(read);
                break;
            }
        }
    }
}

}  // namespace

Result<Program> compile_graph(const Setting &graph) {
    if (!graph.is(Kind::map)) {
        return graph_error(std::format("a graph is a map, and this is {}", graph.kind_name()));
    }
    if (const std::string *key = unknown_key(graph, {"period", "max_catch_up", "max_waiting", "inputs", "blocks"})) {
        return graph_error(std::format("'{}' is not a key of a graph", *key));
    }
    Program program;
    const Setting *period = graph.find("period");
    if (period == nullptr) {
        return graph_error("the graph has no period");
    }
    if (Status status = kept_length(*period, "period", program.period); !status) {
        return status.error();
    }
    if (program.period <= 0) {
        return graph_error("period has to be more than zero");
    }
    if (Status status = count_setting(graph, "max_catch_up", program.max_catch_up); !status) {
        return status.error();
    }
    if (Status status = count_setting(graph, "max_waiting", program.max_waiting); !status) {
        return status.error();
    }
    if (Status status = read_inputs(graph, program); !status) {
        return status.error();
    }

    std::vector<Draft> drafts;
    if (const Setting *blocks = graph.find("blocks")) {
        if (!blocks->is(Kind::list)) {
            return graph_error(std::format("blocks is {}, and has to be a list", blocks->kind_name()));
        }
        for (std::size_t i = 0; i < blocks->as_list().size(); ++i) {
            Draft draft;
            if (Status status = read_block(blocks->as_list()[i], i, program.period, drafts, draft); !status) {
                return status.error();
            }
            drafts.push_back(std::move(draft));
        }
    }

    // Every signal has a slot: the inputs first, then each block's outputs. A signal is read by the name of an
    // input, by a published name, or as <block id>.<port> (rule 9.2).
    struct Named {
        std::size_t slot;
        int writer;  // the draft that writes it, or -1 for an input
    };
    std::map<std::string, Named, std::less<>> names;
    std::vector<std::optional<Type>> types;
    for (const InputSpec &input : program.inputs) {
        names.emplace(input.name, Named{types.size(), -1});
        types.emplace_back(input.type);
    }
    for (std::size_t i = 0; i < drafts.size(); ++i) {
        drafts[i].first_slot = types.size();
        for (const OutputPort &port : drafts[i].block->outputs()) {
            const std::string dotted = std::format("{}.{}", drafts[i].id, port.name);
            if (names.contains(dotted)) {
                return graph_error(
                    std::format("input '{}' has the name of an output of block '{}'", dotted, drafts[i].id));
            }
            names.emplace(dotted, Named{types.size(), static_cast<int>(i)});
            types.emplace_back(port.type);
        }
    }
    static const Setting::List kNoBlocks;
    const Setting *blocks_given = graph.find("blocks");
    const Setting::List &block_list = blocks_given != nullptr ? blocks_given->as_list() : kNoBlocks;
    for (std::size_t i = 0; i < drafts.size(); ++i) {
        const Setting *out = block_list[i].find("out");
        if (out == nullptr) {
            continue;
        }
        const std::span<const OutputPort> ports = drafts[i].block->outputs();
        for (std::size_t k = 0; k < out->as_map().keys.size(); ++k) {
            const std::string &port = out->as_map().keys[k];
            const Setting &name = out->as_map().values[k];
            if (!name.is(Kind::text) || name.as_text().empty()) {
                return graph_error(
                    std::format("block '{}': output '{}' is published as {}, and a published name is text, and not "
                                "empty",
                                drafts[i].id, port, name.shown()));
            }
            const auto taken = names.find(name.as_text());
            if (taken != names.end()) {  // rules 4.6 and 9.2
                const bool published = std::any_of(program.published.begin(), program.published.end(),
                                                   [&](const Published &p) { return p.name == name.as_text(); });
                return graph_error(std::format(
                    "block '{}': output '{}' is published as '{}', which {}", drafts[i].id, port, name.as_text(),
                    taken->second.writer < 0 ? "is an input: a signal written from outside is written by no block"
                    : published              ? "another output is published as: a signal has one writer"
                                             : "is the name of a block's output"));
            }
            const std::size_t slot = drafts[i].first_slot + port_index(ports, port);
            names.emplace(name.as_text(), Named{slot, static_cast<int>(i)});
            program.published.push_back(Published{name.as_text(), slot});
        }
    }

    // What each input port reads.
    for (std::size_t i = 0; i < drafts.size(); ++i) {
        Draft &draft = drafts[i];
        const std::span<const InputPort> ports = draft.block->inputs();
        for (const Wire &wire : draft.wires) {
            const std::size_t port = port_index(ports, wire.port);
            Source &source = draft.sources[port];
            if (wire.constant) {
                source.kind = Source::Kind::constant;
                source.constant = wire.value;
                continue;
            }
            const auto named = names.find(wire.signal);
            if (named == names.end()) {  // rule 9.1
                return graph_error(
                    std::format("block '{}': input '{}' reads '{}', which is neither an input of the "
                                "graph nor a block's output",
                                draft.id, wire.port, wire.signal));
            }
            source.kind = Source::Kind::signal;
            source.slot = named->second.slot;
            draft.readers_of[port] = named->second.writer;
        }
    }

    // A block that can reach its own input is on a loop, and is told so (rule 5.4).
    for (std::size_t i = 0; i < drafts.size(); ++i) {
        if (reads_through(drafts, static_cast<int>(i), static_cast<int>(i))) {
            if (Status status = drafts[i].block->on_loop(); !status) {
                return status.error();
            }
        }
    }

    // Types (rule 3.5). A block's outputs may wait on its inputs' types, so this goes round until nothing more
    // is learned: each round but the last settles at least one output.
    const auto input_types = [&](const Draft &draft) {
        std::vector<std::optional<Type>> given(draft.sources.size());
        for (std::size_t port = 0; port < draft.sources.size(); ++port) {
            const Source &source = draft.sources[port];
            if (source.kind == Source::Kind::constant) {
                given[port] = source.constant.type;
            } else if (source.kind == Source::Kind::signal) {
                given[port] = types[source.slot];
            }
        }
        return given;
    };
    for (bool learned = true; learned;) {
        learned = false;
        for (Draft &draft : drafts) {
            const std::vector<std::optional<Type>> given = input_types(draft);
            const std::span<const InputPort> ports = draft.block->inputs();
            for (std::size_t port = 0; port < ports.size(); ++port) {
                if (ports[port].type.has_value() && given[port].has_value() && *ports[port].type != *given[port]) {
                    const Wire &wire = *std::find_if(draft.wires.begin(), draft.wires.end(),
                                                     [&](const Wire &w) { return w.port == ports[port].name; });
                    return graph_error(
                        std::format("block '{}': input '{}' takes a {}, and {} is a {}", draft.id, ports[port].name,
                                    name_of(*ports[port].type),
                                    wire.constant ? "the constant it is given" : std::format("'{}'", wire.signal),
                                    name_of(*given[port])));
                }
            }
            if (Status status = draft.block->bind(given); !status) {
                return status.error();
            }
            const std::span<const OutputPort> outputs = draft.block->outputs();
            for (std::size_t port = 0; port < outputs.size(); ++port) {
                std::optional<Type> &known = types[draft.first_slot + port];
                if (!known.has_value() && outputs[port].type.has_value()) {
                    known = outputs[port].type;
                    learned = true;
                }
            }
        }
    }
    for (std::size_t i = 0; i < drafts.size(); ++i) {
        Draft &draft = drafts[i];
        const std::span<const OutputPort> outputs = draft.block->outputs();
        for (std::size_t port = 0; port < outputs.size(); ++port) {
            if (!outputs[port].type.has_value()) {
                return graph_error(
                    std::format("block '{}': nothing says whether its output '{}' is a number or a "
                                "boolean",
                                draft.id, outputs[port].name));
            }
            draft.outputs[port].type = *outputs[port].type;
            draft.outputs[port].own_sample_time = outputs[port].own_sample_time;
        }
        if (const Setting *fallback = block_list[i].find("fallback")) {  // section 7.10
            for (std::size_t k = 0; k < fallback->as_map().keys.size(); ++k) {
                const std::string &name = fallback->as_map().keys[k];
                const Setting &given = fallback->as_map().values[k];
                OutputSpec &output = draft.outputs[port_index(outputs, name)];
                if (!read_constant(given, output.fallback) || output.fallback.type != output.type) {
                    return graph_error(std::format("block '{}': the fallback of '{}' is {}, and has to be a {}",
                                                   draft.id, name, given.shown(),
                                                   output.type == Type::number ? "finite number" : "boolean"));
                }
                output.fallback.state = State::uncertain;
                output.has_fallback = true;
            }
        }
    }

    std::vector<std::size_t> order;
    if (Status status = evaluation_order(drafts, order); !status) {
        return status.error();
    }
    for (std::size_t index : order) {
        Draft &draft = drafts[index];
        BlockSpec spec;
        spec.id = std::move(draft.id);
        spec.block = std::move(draft.block);
        spec.sources = std::move(draft.sources);
        spec.outputs = std::move(draft.outputs);
        spec.first_slot = draft.first_slot;
        program.blocks.push_back(std::move(spec));
    }
    for (const std::optional<Type> &type : types) {
        program.slot_types.push_back(*type);
    }
    program.fingerprint = 0xcbf29ce484222325ULL;
    fingerprint(graph, program.fingerprint);
    return program;
}

}  // namespace fluxgraph::v2::detail

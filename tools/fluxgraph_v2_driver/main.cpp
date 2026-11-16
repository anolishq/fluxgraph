// fluxgraph_v2_driver: drives version 2 engines from another process, one line in and one line out.
//
// It exists for the conformance checks in conformance/ (see conformance/cpp/adapter.py), and is a thin binding:
// it turns a line into one call on fluxgraph::v2::Engine and the result into a line, and decides nothing itself.
//
// A line is tokens with one space between them. A token of text is `=` and the text, with every byte outside
// [A-Za-z0-9_./-] written as %XX. A whole number is decimal. A number is the shortest decimal that reads back
// to the same double, or `inf`, `-inf` or `nan`.
//
//   types                         -> ok <n> <built type>... <m> <planned type>...
//   new <setting>                 -> ok <engine>
//   free <engine>                 -> ok
//   write <engine> <=input> <state> <value> <at>     -> ok
//   tick <engine> <now>           -> ok 0
//                                 -> ok <ran> <gap 0|1> <skipped, or ?> <tick> <time> <thrown> <waiting> <n>
//                                    then n of: <=name> <state> <value>
//   rebase <engine> [<away>]      -> ok
//   reset <engine>                -> ok
//   save <engine>                 -> ok <hex>
//   restore <engine> <hex>        -> ok
//
// A <value> is `n <number>`, `b 0` or `b 1`, or `-` for none. A <setting> is, written before what it holds:
// `i <whole>`, `f <number>`, `b 0|1`, `s <=text>`, `l <count>` and that many settings, or `m <count>` and that
// many pairs of a <=key> and a setting. Anything refused answers `err <code> <=message>`, where the code is
// `graph`, `not_built`, `write`, `call`, `rebase` or `state` for the core's refusals and `request` for a line
// the driver could not read: a time that is not a whole number or does not fit in 64 bits among them, since
// such a time cannot be handed to the core at all.

#include <array>
#include <charconv>
#include <cstdint>
#include <iostream>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include "fluxgraph/v2/block.hpp"
#include "fluxgraph/v2/engine.hpp"
#include "fluxgraph/v2/setting.hpp"

namespace {

using fluxgraph::v2::Engine;
using fluxgraph::v2::Errc;
using fluxgraph::v2::Error;
using fluxgraph::v2::Setting;
using fluxgraph::v2::State;
using fluxgraph::v2::Type;
using fluxgraph::v2::Value;

// The tokens of one line, taken from the front.
class Tokens {
public:
    explicit Tokens(std::string_view line) : rest_(line) {}

    bool done() const { return rest_.empty(); }

    bool next(std::string_view &token) {
        if (rest_.empty()) {
            return false;
        }
        const std::size_t space = rest_.find(' ');
        token = rest_.substr(0, space);
        rest_ = space == std::string_view::npos ? std::string_view{} : rest_.substr(space + 1);
        return !token.empty();
    }

    template <typename Whole>
    bool whole(Whole &value) {
        std::string_view token;
        if (!next(token)) {
            return false;
        }
        const std::from_chars_result read = std::from_chars(token.data(), token.data() + token.size(), value);
        return read.ec == std::errc() && read.ptr == token.data() + token.size();
    }

    bool number(double &value) {
        std::string_view token;
        if (!next(token)) {
            return false;
        }
        const std::from_chars_result read = std::from_chars(token.data(), token.data() + token.size(), value);
        return read.ec == std::errc() && read.ptr == token.data() + token.size();
    }

    bool text(std::string &value) {
        std::string_view token;
        if (!next(token) || token[0] != '=') {
            return false;
        }
        value.clear();
        for (std::size_t i = 1; i < token.size(); ++i) {
            if (token[i] != '%') {
                value.push_back(token[i]);
                continue;
            }
            unsigned byte = 0;
            if (i + 2 >= token.size()) {
                return false;
            }
            const std::from_chars_result read = std::from_chars(token.data() + i + 1, token.data() + i + 3, byte, 16);
            if (read.ec != std::errc() || read.ptr != token.data() + i + 3) {
                return false;
            }
            value.push_back(static_cast<char>(byte));
            i += 2;
        }
        return true;
    }

private:
    std::string_view rest_;
};

std::string encoded(std::string_view text) {
    static constexpr std::string_view kHex = "0123456789ABCDEF";
    std::string token = "=";
    for (char c : text) {
        const bool plain = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' ||
                           c == '.' || c == '/' || c == '-';
        if (plain) {
            token.push_back(c);
        } else {
            const auto byte = static_cast<unsigned char>(c);
            token.push_back('%');
            token.push_back(kHex[byte >> 4]);
            token.push_back(kHex[byte & 0xFu]);
        }
    }
    return token;
}

std::string shown(double number) {
    std::array<char, 40> buffer{};
    const std::to_chars_result written = std::to_chars(buffer.data(), buffer.data() + buffer.size(), number);
    return std::string(buffer.data(), written.ptr);
}

// A setting, read from the front of the line. `depth` stops a line of nothing but `l 1 l 1 ...` short of the
// stack's end.
bool read_setting(Tokens &tokens, Setting &setting, int depth = 0) {
    std::string_view kind;
    if (depth > 64 || !tokens.next(kind) || kind.size() != 1) {
        return false;
    }
    switch (kind[0]) {
        case 'i': {
            std::int64_t whole = 0;
            if (!tokens.whole(whole)) {
                return false;
            }
            setting = Setting::whole(whole);
            return true;
        }
        case 'f': {
            double number = 0.0;
            if (!tokens.number(number)) {
                return false;
            }
            setting = Setting::number(number);
            return true;
        }
        case 'b': {
            unsigned flag = 0;
            if (!tokens.whole(flag) || flag > 1) {
                return false;
            }
            setting = Setting::boolean(flag == 1);
            return true;
        }
        case 's': {
            std::string text;
            if (!tokens.text(text)) {
                return false;
            }
            setting = Setting::text(std::move(text));
            return true;
        }
        case 'l': {
            std::size_t count = 0;
            if (!tokens.whole(count)) {
                return false;
            }
            setting = Setting::list();
            for (std::size_t i = 0; i < count; ++i) {
                Setting item;
                if (!read_setting(tokens, item, depth + 1)) {
                    return false;
                }
                setting.add(std::move(item));
            }
            return true;
        }
        case 'm': {
            std::size_t count = 0;
            if (!tokens.whole(count)) {
                return false;
            }
            setting = Setting::map();
            for (std::size_t i = 0; i < count; ++i) {
                std::string key;
                Setting value;
                if (!tokens.text(key) || !read_setting(tokens, value, depth + 1)) {
                    return false;
                }
                setting.set(std::move(key), std::move(value));
            }
            return true;
        }
        default:
            return false;
    }
}

std::string refusal(const Error &error) {
    std::string_view code = "request";
    switch (error.code) {
        case Errc::graph_refused:
            code = "graph";
            break;
        case Errc::block_type_not_built:
            code = "not_built";
            break;
        case Errc::write_refused:
            code = "write";
            break;
        case Errc::call_refused:
            code = "call";
            break;
        case Errc::rebase_refused:
            code = "rebase";
            break;
        case Errc::state_refused:
            code = "state";
            break;
    }
    return "err " + std::string(code) + " " + encoded(error.message);
}

std::string bad_request(std::string_view why) { return "err request " + encoded(why); }

// A state by its name. Any other name goes to the core as a state that is not one of the four, for the core to
// refuse (rule 6.11).
State state_named(std::string_view name) {
    for (State state : {State::bad, State::not_ready, State::uncertain, State::good}) {
        if (fluxgraph::v2::name_of(state) == name) {
            return state;
        }
    }
    return static_cast<State>(0xFF);
}

std::string value_tokens(const Value &value) {
    if (!value.is_usable()) {
        return "-";
    }
    if (value.type == Type::boolean) {
        return value.boolean ? "b 1" : "b 0";
    }
    return "n " + shown(value.number);
}

class Driver {
public:
    std::string answer(std::string_view line) {
        Tokens tokens(line);
        std::string_view command;
        if (!tokens.next(command)) {
            return bad_request("an empty line");
        }
        if (command == "types") {
            return types();
        }
        if (command == "new") {
            return make(tokens);
        }
        std::uint64_t id = 0;
        if (!tokens.whole(id)) {
            return bad_request("no engine named");
        }
        const auto found = engines_.find(id);
        if (found == engines_.end()) {
            return bad_request("no such engine");
        }
        Engine &engine = found->second;
        if (command == "free") {
            engines_.erase(found);
            return "ok";
        }
        if (command == "write") {
            return write(engine, tokens);
        }
        if (command == "tick") {
            return tick(engine, tokens);
        }
        if (command == "rebase") {
            return rebase(engine, tokens);
        }
        if (command == "reset") {
            engine.reset();
            return "ok";
        }
        if (command == "save") {
            return save(engine);
        }
        if (command == "restore") {
            return restore(engine, tokens);
        }
        return bad_request("an unknown command");
    }

private:
    static std::string types() {
        std::string reply = "ok";
        for (const auto names : {fluxgraph::v2::built_block_types(), fluxgraph::v2::planned_block_types()}) {
            reply += " " + std::to_string(names.size());
            for (std::string_view name : names) {
                reply += " " + std::string(name);
            }
        }
        return reply;
    }

    std::string make(Tokens &tokens) {
        Setting graph;
        if (!read_setting(tokens, graph) || !tokens.done()) {
            return bad_request("the graph could not be read");
        }
        fluxgraph::v2::Result<Engine> engine = Engine::compile(graph);
        if (!engine) {
            return refusal(engine.error());
        }
        const std::uint64_t id = next_id_++;
        engines_.emplace(id, std::move(engine.value()));
        return "ok " + std::to_string(id);
    }

    static std::string write(Engine &engine, Tokens &tokens) {
        std::string input;
        std::string_view state_name;
        std::string_view kind;
        if (!tokens.text(input) || !tokens.next(state_name) || !tokens.next(kind)) {
            return bad_request("a write names an input, a state and a value");
        }
        const State state = state_named(state_name);
        double number = 0.0;
        unsigned flag = 0;
        if ((kind == "n" && !tokens.number(number)) || (kind == "b" && (!tokens.whole(flag) || flag > 1)) ||
            (kind != "n" && kind != "b" && kind != "-")) {
            return bad_request("the value of the write could not be read");
        }
        fluxgraph::v2::Time at = 0;
        if (!tokens.whole(at) || !tokens.done()) {
            return bad_request("the time of a write is a whole number of nanoseconds that fits in 64 bits");
        }
        const fluxgraph::v2::Status status = kind == "n"   ? engine.write(input, state, number, at)
                                             : kind == "b" ? engine.write(input, state, flag == 1, at)
                                                           : engine.write(input, state, at);
        return status ? "ok" : refusal(status.error());
    }

    static std::string tick(Engine &engine, Tokens &tokens) {
        fluxgraph::v2::Time now = 0;
        if (!tokens.whole(now) || !tokens.done()) {
            return bad_request("the time of a call is a whole number of nanoseconds that fits in 64 bits");
        }
        const fluxgraph::v2::Result<fluxgraph::v2::TickReport> report = engine.tick(now);
        if (!report) {
            return refusal(report.error());
        }
        if (report->ran == 0) {
            return "ok 0";
        }
        std::string reply = "ok " + std::to_string(report->ran) + (report->gap ? " 1 " : " 0 ") +
                            (report->skipped_known ? std::to_string(report->skipped) : "?") + " " +
                            std::to_string(report->tick) + " " + std::to_string(report->time) + " " +
                            std::to_string(report->thrown) + " " + std::to_string(report->waiting) + " " +
                            std::to_string(engine.outputs().size());
        for (const fluxgraph::v2::Output &output : engine.outputs()) {
            reply += " " + encoded(output.name) + " " + std::string(fluxgraph::v2::name_of(output.value.state)) + " " +
                     value_tokens(output.value);
        }
        return reply;
    }

    static std::string rebase(Engine &engine, Tokens &tokens) {
        if (tokens.done()) {
            engine.rebase();
            return "ok";
        }
        fluxgraph::v2::Time away = 0;
        if (!tokens.whole(away) || !tokens.done()) {
            return bad_request("the length of a rebase is a whole number of nanoseconds that fits in 64 bits");
        }
        const fluxgraph::v2::Status status = engine.rebase(away);
        return status ? "ok" : refusal(status.error());
    }

    static std::string save(const Engine &engine) {
        static constexpr std::string_view kHex = "0123456789abcdef";
        std::string reply = "ok ";
        for (std::uint8_t byte : engine.save().bytes) {
            reply.push_back(kHex[byte >> 4]);
            reply.push_back(kHex[byte & 0xFu]);
        }
        return reply;
    }

    static std::string restore(Engine &engine, Tokens &tokens) {
        std::string_view hex;
        if (!tokens.next(hex) || !tokens.done() || hex.size() % 2 != 0) {
            return bad_request("a state is an even number of hexadecimal digits");
        }
        fluxgraph::v2::SavedState state;
        for (std::size_t i = 0; i < hex.size(); i += 2) {
            unsigned byte = 0;
            const std::from_chars_result read = std::from_chars(hex.data() + i, hex.data() + i + 2, byte, 16);
            if (read.ec != std::errc() || read.ptr != hex.data() + i + 2) {
                return bad_request("a state is an even number of hexadecimal digits");
            }
            state.bytes.push_back(static_cast<std::uint8_t>(byte));
        }
        const fluxgraph::v2::Status status = engine.restore(state);
        return status ? "ok" : refusal(status.error());
    }

    std::map<std::uint64_t, Engine> engines_;
    std::uint64_t next_id_ = 1;
};

}  // namespace

int main() {
    std::ios::sync_with_stdio(false);
    Driver driver;
    std::string line;
    while (std::getline(std::cin, line)) {
        std::cout << driver.answer(line) << '\n' << std::flush;
    }
    return 0;
}

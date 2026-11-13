#pragma once

#include <cstdint>
#include <string_view>

namespace fluxgraph::v2 {

/// A time or a length of time: whole nanoseconds (rule 6.2).
using Time = std::int64_t;

/// The state of a signal, worst first (rules 3.1 and 3.3). A lower value is a worse state.
enum class State : std::uint8_t { bad = 0, not_ready = 1, uncertain = 2, good = 3 };

/// The type of a signal or a port (rule 3.5).
enum class Type : std::uint8_t { number = 0, boolean = 1 };

constexpr bool usable(State state) { return state == State::good || state == State::uncertain; }
constexpr State worst(State a, State b) { return a < b ? a : b; }

std::string_view name_of(State state);
std::string_view name_of(Type type);

/// What a signal carries at a tick: a state, a value when the state is usable, and perhaps a sample time
/// (section 3). `number` or `boolean` holds the value, by `type`; neither means anything when the state is not
/// usable, and `time` means nothing unless `timed`.
struct Value {
    State state = State::not_ready;
    Type type = Type::number;
    bool boolean = false;
    bool timed = false;
    double number = 0.0;
    Time time = 0;

    static Value of(double number, State state = State::good) {
        Value v;
        v.state = state;
        v.number = number;
        return v;
    }
    static Value of(bool boolean, State state = State::good) {
        Value v;
        v.state = state;
        v.type = Type::boolean;
        v.boolean = boolean;
        return v;
    }
    /// A value of no use: `bad` or `not_ready`.
    static Value none(State state, Type type = Type::number) {
        Value v;
        v.state = state;
        v.type = type;
        return v;
    }

    bool is_usable() const { return usable(state); }
};

}  // namespace fluxgraph::v2

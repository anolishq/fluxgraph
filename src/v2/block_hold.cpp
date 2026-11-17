// `deadband`, `lowpass` and `rate_limit` (section 7.4): the blocks that hold a value and ride through.

#include <array>
#include <cmath>
#include <format>
#include <optional>

#include "blocks.hpp"
#include "exact.hpp"
#include "remembers.hpp"

namespace fluxgraph::v2::detail {

namespace {

// Rules 7.4.3 and 7.4.4, which all three share: with an unusable input the block gives what it holds, uncertain,
// while the last usable input was no more than `ride_through` ago, and past that forgets.
struct Ride {
    std::uint64_t limit = 0;  // `ride_through`, in ticks

    // Whether the `run + 1`-th unusable tick in a row is still within it.
    bool rides(std::uint64_t run) const { return run < limit; }
    // Whether a block that has seen `run` unusable ticks in a row, a gap's among them, still holds.
    bool holds(std::uint64_t run) const { return run <= limit; }
};

template <typename Memory>
class HoldBlock : public Committing<Memory> {
public:
    std::span<const InputPort> inputs() const override { return inputs_; }
    Status bind(std::span<const std::optional<Type>> /*input_types*/) override { return {}; }

protected:
    std::array<InputPort, 1> inputs_ = {{{"x", Type::number, true, false}}};
    Ride ride_;
};

// ---- deadband (rules 7.4.1 to 7.4.4)

struct DeadbandMemory {
    bool holding = false;
    double value = 0.0;
    std::uint64_t run = 0;  // unusable ticks in a row since the last usable input
};

class DeadbandBlock : public HoldBlock<DeadbandMemory> {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        if (!settings.not_negative("step", step_) && !settings.failed()) {
            settings.fail("has no 'step' setting");
        }
        settings.counted("ride_through", ride_.limit);
        return settings.finish();
    }

    std::span<const OutputPort> outputs() const override { return outputs_; }

protected:
    using Memory = DeadbandMemory;

    void step(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out, const Memory &now,
              Memory &next) const override {
        const Value &x = in[0];
        if (x.is_usable()) {
            // The first usable input is taken as it is; after that, one that has moved by `step` or more.
            if (!now.holding || std::fabs(x.number - now.value) >= step_) {
                next.value = x.number;
            }
            next.holding = true;
            next.run = 0;
            out[0] = Value::of(next.value, x.state);  // the state of the input at this tick
        } else if (now.holding && ride_.rides(now.run)) {
            next.run = now.run + 1;
            out[0] = Value::of(now.value, State::uncertain);
        } else {
            next = Memory{};
            out[0] = Value::none(x.state);
        }
    }

    void pass_over(const Gap &gap, Memory &now) const override {
        if (!gap.known) {
            now = Memory{};
        } else if (now.holding) {
            now.run += gap.ticks;  // counts of ticks: see Counters
            if (!ride_.holds(now.run)) {
                now = Memory{};
            }
        }
    }

    void describe(Fields &fields, Memory &memory) const override {
        fields(memory.holding);
        fields(memory.value);
        fields(memory.run);
    }

private:
    std::array<OutputPort, 1> outputs_ = {{{"y", Type::number, false}}};
    double step_ = 0.0;
};

// ---- lowpass (rules 7.4.5 to 7.4.8)

struct LowpassMemory {
    bool holding = false;
    double y = 0.0;
    std::uint64_t run = 0;
    bool doubted = false;
    std::int64_t doubt = 0;  // the number of the latest tick at which it took an uncertain input
};

class LowpassBlock : public HoldBlock<LowpassMemory> {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        double ratio = 1.0;
        // `settle` is three time constants, rounded up to whole ticks, unless given.
        if (!settings.period_over("tau", ratio, 3, settle_) && !settings.failed()) {
            settings.fail("has no 'tau' setting");
        }
        settings.counted("ride_through", ride_.limit);
        settings.counted("settle", settle_);
        decay_ = std::exp(-ratio);  // a = exp(-period / tau)
        return settings.finish();
    }

    std::span<const OutputPort> outputs() const override { return outputs_; }

    LoopRole loop_role() const override { return LoopRole{LoopRole::Kind::remembers, settle_, false}; }

protected:
    using Memory = LowpassMemory;

    void step(const Tick &tick, std::span<const Value> in, std::span<Value> out, const Memory &now,
              Memory &next) const override {
        const Value &x = in[0];
        if (x.is_usable()) {
            if (!now.holding) {
                next.y = x.number;
            } else {
                // The ticks it rode through decay too: m is the ticks since its last usable input.
                const double kept = now.run == 0 ? decay_ : std::pow(decay_, static_cast<double>(now.run) + 1.0);
                next.y = kept * now.y + (1.0 - kept) * x.number;
            }
            next.holding = true;
            next.run = 0;
            if (x.state == State::uncertain) {  // rule 7.4.7: its doubt, a first input among them
                next.doubted = true;
                next.doubt = tick.number;
            }
            // Rule 7.4.8: uncertain if the input is, and on the `settle` ticks after its doubt. A tick is never
            // before the doubt, so the difference is in order.
            const bool settling = next.doubted && span_between(next.doubt, tick.number) <= settle_;
            out[0] = Value::of(next.y, x.state == State::uncertain || settling ? State::uncertain : State::good);
        } else if (now.holding && ride_.rides(now.run)) {
            next.run = now.run + 1;
            out[0] = Value::of(now.y, State::uncertain);
        } else {
            next = Memory{};  // forgetting clears its doubt
            out[0] = Value::none(x.state);
        }
    }

    void pass_over(const Gap &gap, Memory &now) const override {
        if (!gap.known) {
            now = Memory{};
        } else if (now.holding) {
            now.run += gap.ticks;
            if (!ride_.holds(now.run)) {
                now = Memory{};
            }
        }
    }

    void settle(Memory &now) const override { now.doubted = false; }  // rule 7.8.8: its doubt is cleared

    void describe(Fields &fields, Memory &memory) const override {
        fields(memory.holding);
        fields(memory.y);
        fields(memory.run);
        fields(memory.doubted);
        fields(memory.doubt);
    }

private:
    std::array<OutputPort, 1> outputs_ = {{{"y", Type::number, false}}};
    double decay_ = 0.0;
    std::uint64_t settle_ = 0;  // in ticks
};

// ---- rate_limit (rules 7.4.9 to 7.4.14)

struct RateLimitMemory {
    bool holding = false;
    bool only_initial = false;  // what it holds is `initial`, and no output it has given
    double value = 0.0;
    std::uint64_t run = 0;  // ticks since it took a value: unusable ones in a row, and ones it followed blind
};

class RateLimitBlock : public HoldBlock<RateLimitMemory> {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        double up = 0.0;
        if (!settings.not_negative("up", up) && !settings.failed()) {
            settings.fail("has no 'up' setting");
        }
        double down = up;  // `down` is `up` unless given
        settings.not_negative("down", down);
        settings.counted("ride_through", ride_.limit);
        has_initial_ = settings.number("initial", initial_);
        const double period_seconds = static_cast<double>(setup.period) / 1e9;
        reach_up_ = up * period_seconds;  // per second, over one period
        reach_down_ = down * period_seconds;
        reset();
        bool tracks = false;
        for (const Connection &connection : setup.connections) {
            tracks = tracks || connection.port == "track";
            follows_ = follows_ || connection.port == "follow";
        }
        if (follows_ && !tracks && !settings.failed()) {
            settings.fail("has an input 'follow' and no 'track': 'follow' is given only where 'track' is");
        }
        return settings.finish();
    }

    std::span<const InputPort> inputs() const override { return ports_; }
    std::span<const OutputPort> outputs() const override { return outputs_; }

    CallRole call_role() const override { return CallRole{CallRole::Kind::shaper, 0}; }

protected:
    using Memory = RateLimitMemory;

    void step(const Tick &tick, std::span<const Value> in, std::span<Value> out, const Memory &now,
              Memory &next) const override {
        const Value &x = in[0];
        const Value &track = in[1];
        if (tick.acts_by_call && !tick.last_of_call) {
            // Rule 7.4.12: at a catch-up tick it takes nothing, moves nothing and forgets nothing. Where it
            // holds a value it took from an input, the tick is one with a usable input for rules 3 and 4.
            if (now.holding && !now.only_initial) {
                next.run = 0;
            }
            out[0] = Value::none(State::not_ready);  // held by the engine (rule 6.13): this is not looked at
            out[1] = x.is_usable() ? Value::of(now.holding && x.number != now.value, x.state)
                                   : Value::none(x.state, Type::boolean);
            return;
        }
        // Rule 7.4.14: it follows where `follow` is true, and where it is not usable: a block that is not told
        // it acts does not. It limits nothing and does not look at its input.
        const Value &follow = in[2];
        if (follows_ && (!follow.is_usable() || follow.boolean)) {
            if (track.is_usable()) {
                // It gives `track` and holds it as a value it took from an input at this tick.
                const State state = follow.is_usable() ? track.state : State::uncertain;
                next.holding = true;
                next.only_initial = false;
                next.value = track.number;
                next.run = 0;
                out[0] = Value::of(track.number, state);
                out[1] = Value::of(false, state);
            } else {
                // It holds what it held and forgets nothing, however many such ticks there are; the tick counts
                // towards `ride_through` when it next has an input it cannot use and does not follow.
                if (now.holding && !now.only_initial) {
                    next.run = now.run + 1;
                }
                out[0] = Value::none(track.state);
                out[1] = Value::none(track.state, Type::boolean);
            }
            return;
        }
        // At the last tick of a call its reach is that of the periods it acts for.
        const double periods = tick.acts_by_call ? static_cast<double>(tick.periods) : 1.0;
        if (x.is_usable()) {
            // Rule 7.4.13: where it holds no value it took from an input, and `track` is usable, it holds the
            // value of `track` in place of `initial` or of nothing.
            bool holding = now.holding;
            double held = now.value;
            if ((!now.holding || now.only_initial) && track.is_usable()) {
                holding = true;
                held = track.number;
            }
            double y = x.number;  // the first usable input, and one within reach, is taken as it is
            if (holding) {
                if (x.number - held > reach_up_ * periods) {
                    y = held + reach_up_ * periods;
                } else if (held - x.number > reach_down_ * periods) {
                    y = held - reach_down_ * periods;
                }
            }
            next.holding = true;
            next.only_initial = false;
            next.value = y;
            next.run = 0;
            out[0] = Value::of(y, x.state);
            out[1] = Value::of(y != x.number, x.state);  // `limited`: the output is not the input
            return;
        }
        // Holding `initial` and nothing else it does not ride through.
        if (now.holding && !now.only_initial && ride_.rides(now.run)) {
            next.run = now.run + 1;
            out[0] = Value::of(now.value, State::uncertain);
        } else {
            next = start();
            out[0] = Value::none(x.state);
        }
        out[1] = Value::none(x.state, Type::boolean);  // there is nothing to compare
    }

    void pass_over(const Gap &gap, Memory &now) const override {
        if (!gap.known) {
            now = start();
        } else if (now.holding && !now.only_initial) {
            now.run += gap.ticks;
            if (!ride_.holds(now.run)) {
                now = start();
            }
        }
    }

    void describe(Fields &fields, Memory &memory) const override {
        fields(memory.holding);
        fields(memory.only_initial);
        fields(memory.value);
        fields(memory.run);
    }

private:
    // As it is made, and as it is having forgotten: holding `initial` if it was given one.
    Memory start() const override { return Memory{has_initial_, has_initial_, initial_, 0}; }

    // `track` is where the actuator is, read back from it, and need not be connected (rule 7.4.13).
    // `follow` is what a host says while nothing acts on the output (rule 7.4.14).
    std::array<InputPort, 3> ports_ = {{{"x", Type::number, true, false},
                                        {"track", Type::number, false, false},
                                        {"follow", Type::boolean, false, false}}};
    std::array<OutputPort, 2> outputs_ = {{{"y", Type::number, false}, {"limited", Type::boolean, false}}};
    double reach_up_ = 0.0;
    double reach_down_ = 0.0;
    bool has_initial_ = false;
    double initial_ = 0.0;
    bool follows_ = false;  // `follow` is connected: left unconnected, the block acts
};

}  // namespace

Result<std::unique_ptr<Block>> make_deadband(const BlockSetup &setup) { return make_block<DeadbandBlock>(setup); }
Result<std::unique_ptr<Block>> make_lowpass(const BlockSetup &setup) { return make_block<LowpassBlock>(setup); }
Result<std::unique_ptr<Block>> make_rate_limit(const BlockSetup &setup) { return make_block<RateLimitBlock>(setup); }

}  // namespace fluxgraph::v2::detail

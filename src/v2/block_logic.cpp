// `hysteresis` (section 7.5) and `held_for`, `since_true` and `latch` (section 7.6): the blocks whose memory has
// no end, and that give counters for it (section 7, "Counters").

#include <array>
#include <format>
#include <optional>

#include "blocks.hpp"
#include "remembers.hpp"

namespace fluxgraph::v2::detail {

namespace {

enum Port : std::size_t { kY, kElapsed, kDoubtful, kGaps, kPorts };

// Counters that start again at the tick being run.
Counters restarted(bool gap_here) { return Counters{0, 0, gap_here ? std::uint64_t{1} : 0}; }

// What the four share: a boolean `y` and the three counters, and the knowledge that a gap's tick is the next to
// run, so that a count which starts again at that tick starts `gaps` at one (rule 8.6).
template <typename Memory>
class CountingBlock : public Committing<Memory> {
public:
    std::span<const OutputPort> outputs() const override { return outputs_; }
    Status bind(std::span<const std::optional<Type>> /*input_types*/) override { return {}; }

protected:
    std::array<OutputPort, kPorts> outputs_ = {{
        {"y", Type::boolean, false},
        {"elapsed", Type::number, false},
        {"doubtful", Type::number, false},
        {"gaps", Type::number, false},
    }};
    double period_seconds_ = 1.0;
};

// ---- hysteresis

struct HysteresisMemory {
    bool decided = false;
    bool side = false;
    Counters counters;
    bool gap_here = false;
};
// `gap_here` is not saved: a restore is a gap, and the gap sets it.

class HysteresisBlock : public CountingBlock<HysteresisMemory> {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        if (!settings.number("rise", rise_) && !settings.failed()) {
            settings.fail("has no 'rise' setting");
        }
        if (!settings.number("fall", fall_) && !settings.failed()) {
            settings.fail("has no 'fall' setting");
        }
        if (!settings.failed() && !(rise_ > fall_)) {
            settings.fail(
                std::format("'rise' is {} and 'fall' is {}: 'rise' has to be more than 'fall'", rise_, fall_));
        }
        has_initial_ = settings.boolean("initial", initial_);
        period_seconds_ = static_cast<double>(setup.period) / 1e9;
        reset();
        return settings.finish();
    }

    std::span<const InputPort> inputs() const override { return inputs_; }

protected:
    using Memory = HysteresisMemory;

    void step(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out, const Memory &now,
              Memory &next) const override {
        const Value &x = in[0];
        next.gap_here = false;
        if (x.is_usable()) {
            if (x.number >= rise_ || x.number <= fall_) {
                const bool side = x.number >= rise_;
                if (!now.decided || now.side != side) {
                    next.counters = restarted(now.gap_here);  // rule 7.5.4: from the tick its value last changed
                }
                next.decided = true;
                next.side = side;
            }
            out[kY] = next.decided ? Value::of(next.side, x.state) : Value::none(State::not_ready, Type::boolean);
        } else {
            out[kY] = Value::none(x.state, Type::boolean);  // it stays as it was
        }
        next.counters.elapsed += 1;
        next.counters.doubtful += x.state != State::good ? 1 : 0;
        next.counters.give(out, kElapsed, period_seconds_);
    }

    void pass_over(const Gap &gap, Memory &now) const override {
        now.counters.gaps += 1;
        now.gap_here = true;
        if (gap.known) {
            now.counters.elapsed += gap.ticks;
            now.counters.doubtful += gap.ticks;
        }
    }

    Memory start() const override {
        Memory made;
        made.decided = has_initial_;
        made.side = initial_;
        return made;
    }

    void describe(Fields &fields, Memory &memory) const override {
        fields(memory.decided);
        fields(memory.side);
        fields(memory.counters);
    }

private:
    std::array<InputPort, 1> inputs_ = {{{"x", Type::number, true, false}}};
    double rise_ = 0.0;
    double fall_ = 0.0;
    bool has_initial_ = false;
    bool initial_ = false;
};

// ---- held_for (rule 7.6.1)

struct HeldForMemory {
    bool running = false;
    std::uint64_t age = 0;      // ticks since the tick the timer started on
    std::uint64_t stretch = 0;  // unusable ticks in a row
    Counters counters;
    bool gap_here = false;
};
// `gap_here` is not saved: a restore is a gap, and the gap sets it.

class HeldForBlock : public CountingBlock<HeldForMemory> {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        if (!settings.counted("time", time_) && !settings.failed()) {
            settings.fail("has no 'time' setting");
        }
        std::string on_bad;
        if (!settings.text("on_bad", on_bad) && !settings.failed()) {
            settings.fail("has no 'on_bad' setting: reset or hold");
        }
        if (!settings.failed() && on_bad != "reset" && on_bad != "hold") {
            settings.fail(std::format("setting 'on_bad' is '{}', and has to be reset or hold", on_bad));
        }
        hold_ = on_bad == "hold";
        const bool limit_given = settings.counted("hold_limit", hold_limit_);
        if (!settings.failed() && hold_ != limit_given) {
            settings.fail(hold_ ? "'hold_limit' has to be given with 'on_bad: hold'"
                                : "'hold_limit' is given, and is only for 'on_bad: hold'");
        }
        period_seconds_ = static_cast<double>(setup.period) / 1e9;
        return settings.finish();
    }

    std::span<const InputPort> inputs() const override { return inputs_; }

protected:
    using Memory = HeldForMemory;

    void step(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out, const Memory &now,
              Memory &next) const override {
        const Value &x = in[0];
        next.gap_here = false;
        if (x.is_usable() && x.boolean) {
            if (!now.running) {
                next.running = true;
                next.age = 0;  // the tick on which the input becomes true counts as no time at all
                next.counters = restarted(now.gap_here);
            } else {
                next.age = now.age + 1;
            }
            next.stretch = 0;
            next.counters.elapsed += 1;
            next.counters.doubtful += x.state != State::good ? 1 : 0;
            out[kY] = Value::of(next.age > time_, x.state);
        } else if (x.is_usable()) {
            next = Memory{};  // a usable input that is false stops the timer
            out[kY] = Value::of(false, x.state);
        } else if (hold_ && now.running && now.stretch < hold_limit_) {
            // The timer runs on, and the output is uncertain: true once the time has run out.
            next.stretch = now.stretch + 1;
            next.age = now.age + 1;
            next.counters.elapsed += 1;
            next.counters.doubtful += 1;
            out[kY] = Value::of(next.age > time_, State::uncertain);
        } else {
            next = Memory{};
            out[kY] = Value::none(x.state, Type::boolean);
        }
        // Zero while the timer is not running: a stopped timer's memory is all zero.
        next.counters.give(out, kElapsed, period_seconds_);
    }

    void pass_over(const Gap &gap, Memory &now) const override {
        if (now.running) {
            if (!gap.known || (gap.ticks > 0 && !hold_)) {
                now = Memory{};  // nobody knows, or `reset`: the timer stops
            } else {
                // `hold`: the unusable stretch grows by the ticks passed over. A gap that passed over none stops
                // no timer.
                now.stretch += gap.ticks;
                if (now.stretch > hold_limit_) {
                    now = Memory{};
                } else {
                    now.age += gap.ticks;
                    now.counters.elapsed += gap.ticks;
                    now.counters.doubtful += gap.ticks;
                    now.counters.gaps += 1;
                }
            }
        }
        now.gap_here = true;
    }

    void describe(Fields &fields, Memory &memory) const override {
        fields(memory.running);
        fields(memory.age);
        fields(memory.stretch);
        fields(memory.counters);
    }

private:
    std::array<InputPort, 1> inputs_ = {{{"x", Type::boolean, true, false}}};
    std::uint64_t time_ = 0;  // in ticks
    bool hold_ = false;
    std::uint64_t hold_limit_ = 0;
};

// ---- since_true (rule 7.6.2)

struct SinceTrueMemory {
    bool started = false;
    bool lost = false;      // a gap of no known length, and the clock not set since
    std::uint64_t age = 0;  // the tick's number less the clock's
    Counters counters;
    bool gap_here = false;
};
// `gap_here` is not saved: a restore is a gap, and the gap sets it.

class SinceTrueBlock : public CountingBlock<SinceTrueMemory> {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        if (!settings.counted("time", time_) && !settings.failed()) {
            settings.fail("has no 'time' setting");
        }
        std::string on_bad;
        if (!settings.text("on_bad", on_bad) && !settings.failed()) {
            settings.fail("has no 'on_bad' setting: assume_false or unknown");
        }
        if (!settings.failed() && on_bad != "assume_false" && on_bad != "unknown") {
            settings.fail(std::format("setting 'on_bad' is '{}', and has to be assume_false or unknown", on_bad));
        }
        assume_false_ = on_bad == "assume_false";
        period_seconds_ = static_cast<double>(setup.period) / 1e9;
        return settings.finish();
    }

    std::span<const InputPort> inputs() const override { return inputs_; }

protected:
    using Memory = SinceTrueMemory;

    void step(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out, const Memory &now,
              Memory &next) const override {
        const Value &x = in[0];
        next.gap_here = false;
        if (!now.started) {
            next.started = true;  // its clock starts at the first tick
            next.age = 0;
        } else {
            next.age = now.age + 1;
        }
        if (x.is_usable() && x.boolean) {
            next.age = 0;  // the clock is set again
            next.lost = false;
            next.counters = restarted(now.gap_here);
        }
        next.counters.elapsed += 1;
        next.counters.doubtful += x.state != State::good ? 1 : 0;
        // After a gap of no known length the input was last true longer ago than `time`.
        const bool value = next.lost || next.age > time_;
        if (x.is_usable()) {
            out[kY] = Value::of(value, x.state);
        } else if (assume_false_) {
            out[kY] = Value::of(value, State::uncertain);
        } else {
            out[kY] = Value::none(x.state, Type::boolean);
        }
        next.counters.give(out, kElapsed, period_seconds_);
    }

    void pass_over(const Gap &gap, Memory &now) const override {
        now.gap_here = true;
        if (gap.known) {
            now.age += gap.ticks;  // the clock is not set
            now.counters.elapsed += gap.ticks;
            now.counters.doubtful += gap.ticks;
            now.counters.gaps += 1;
        } else {
            now.lost = true;
            now.counters = restarted(true);  // its counts start again at the gap's tick
        }
    }

    void describe(Fields &fields, Memory &memory) const override {
        fields(memory.started);
        fields(memory.lost);
        fields(memory.age);
        fields(memory.counters);
    }

private:
    std::array<InputPort, 1> inputs_ = {{{"x", Type::boolean, true, false}}};
    std::uint64_t time_ = 0;
    bool assume_false_ = false;
};

// ---- latch (rule 7.6.3)

struct LatchMemory {
    bool set = false;
    Counters counters;
    bool gap_here = false;
};
// `gap_here` is not saved: a restore is a gap, and the gap sets it.

class LatchBlock : public CountingBlock<LatchMemory> {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        period_seconds_ = static_cast<double>(setup.period) / 1e9;
        return settings.finish();
    }

    std::span<const InputPort> inputs() const override { return inputs_; }

protected:
    using Memory = LatchMemory;

    void step(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out, const Memory &now,
              Memory &next) const override {
        const Value &set = in[0];
        const Value &reset = in[1];
        next.gap_here = false;
        if (reset.is_usable() && reset.boolean) {
            next.set = false;
            next.counters = restarted(now.gap_here);  // `elapsed` counts from the tick it was last cleared
            out[kY] = Value::of(false, reset.state);
        } else if (now.set) {
            out[kY] = Value::of(true);  // `set` is not used
        } else if (set.is_usable()) {
            next.set = set.boolean;
            out[kY] = Value::of(set.boolean, set.state);
        } else {
            out[kY] = Value::none(set.state, Type::boolean);
        }
        next.counters.elapsed += 1;
        // Those on which it was not set when the tick began and `set` was not good.
        next.counters.doubtful += !now.set && set.state != State::good ? 1 : 0;
        next.counters.give(out, kElapsed, period_seconds_);
    }

    void pass_over(const Gap &gap, Memory &now) const override {
        now.counters.gaps += 1;
        now.gap_here = true;
        if (gap.known) {
            now.counters.elapsed += gap.ticks;
            now.counters.doubtful += now.set ? 0 : gap.ticks;
        }
    }

    void describe(Fields &fields, Memory &memory) const override {
        fields(memory.set);
        fields(memory.counters);
    }

private:
    std::array<InputPort, 2> inputs_ = {{{"set", Type::boolean, true, false}, {"reset", Type::boolean, false, false}}};
};

}  // namespace

Result<std::unique_ptr<Block>> make_hysteresis(const BlockSetup &setup) { return make_block<HysteresisBlock>(setup); }
Result<std::unique_ptr<Block>> make_held_for(const BlockSetup &setup) { return make_block<HeldForBlock>(setup); }
Result<std::unique_ptr<Block>> make_since_true(const BlockSetup &setup) { return make_block<SinceTrueBlock>(setup); }
Result<std::unique_ptr<Block>> make_latch(const BlockSetup &setup) { return make_block<LatchBlock>(setup); }

}  // namespace fluxgraph::v2::detail

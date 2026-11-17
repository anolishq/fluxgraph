// `hysteresis` (section 7.5) and `held_for`, `since_true` and `latch` (section 7.6): the blocks whose memory has
// no end, and that give counters for it (section 7, "Counters").

#include <array>
#include <format>
#include <optional>

#include "blocks.hpp"

namespace fluxgraph::v2::detail {

namespace {

enum Port : std::size_t { kY, kElapsed, kDoubtful, kGaps, kPorts };

// What the four share: a boolean `y` and the three counters, and the knowledge that a gap's tick is the next to
// run, so that a count which starts again at that tick starts `gaps` at one (rule 8.6).
class CountingBlock : public Block {
public:
    std::span<const OutputPort> outputs() const override { return outputs_; }
    Status bind(std::span<const std::optional<Type>> /*input_types*/) override { return {}; }

protected:
    // Counters that start again at the tick being run.
    static Counters restarted(bool gap_here) { return Counters{0, 0, gap_here ? std::uint64_t{1} : 0}; }

    std::array<OutputPort, kPorts> outputs_ = {{
        {"y", Type::boolean, false},
        {"elapsed", Type::number, false},
        {"doubtful", Type::number, false},
        {"gaps", Type::number, false},
    }};
    double period_seconds_ = 1.0;
};

// ---- hysteresis

class HysteresisBlock : public CountingBlock {
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

    void give(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out) override {
        const Value &x = in[0];
        next_ = now_;
        next_.gap_here = false;
        if (x.is_usable()) {
            if (x.number >= rise_ || x.number <= fall_) {
                const bool side = x.number >= rise_;
                if (!now_.decided || now_.side != side) {
                    next_.counters = restarted(now_.gap_here);  // rule 7.5.4: from the tick its value last changed
                }
                next_.decided = true;
                next_.side = side;
            }
            out[kY] = next_.decided ? Value::of(next_.side, x.state) : Value::none(State::not_ready, Type::boolean);
        } else {
            out[kY] = Value::none(x.state, Type::boolean);  // it stays as it was
        }
        next_.counters.elapsed += 1;
        next_.counters.doubtful += x.state != State::good ? 1 : 0;
        next_.counters.give(out, kElapsed, period_seconds_);
    }

    void update(const Tick & /*tick*/, std::span<const Value> /*in*/) override { now_ = next_; }

    void gap(const Gap &gap) override {
        now_.counters.gaps += 1;
        now_.gap_here = true;
        if (gap.known) {
            now_.counters.elapsed += gap.ticks;
            now_.counters.doubtful += gap.ticks;
        }
    }

    void reset() override {
        now_ = Memory{};
        now_.decided = has_initial_;
        now_.side = initial_;
    }

    void save(StateWriter &writer) const override {
        writer.flag(now_.decided);
        writer.flag(now_.side);
        now_.counters.save(writer);
    }

    bool restore(StateReader &reader) override {
        now_.gap_here = false;
        return reader.flag(now_.decided) && reader.flag(now_.side) && now_.counters.restore(reader);
    }

private:
    struct Memory {
        bool decided = false;
        bool side = false;
        Counters counters;
        bool gap_here = false;
    };

    std::array<InputPort, 1> inputs_ = {{{"x", Type::number, true, false}}};
    double rise_ = 0.0;
    double fall_ = 0.0;
    bool has_initial_ = false;
    bool initial_ = false;
    Memory now_;
    Memory next_;
};

// ---- held_for (rule 7.6.1)

class HeldForBlock : public CountingBlock {
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

    void give(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out) override {
        const Value &x = in[0];
        next_ = now_;
        next_.gap_here = false;
        if (x.is_usable() && x.boolean) {
            if (!now_.running) {
                next_.running = true;
                next_.age = 0;  // the tick on which the input becomes true counts as no time at all
                next_.counters = restarted(now_.gap_here);
            } else {
                next_.age = now_.age + 1;
            }
            next_.stretch = 0;
            next_.counters.elapsed += 1;
            next_.counters.doubtful += x.state != State::good ? 1 : 0;
            out[kY] = Value::of(next_.age > time_, x.state);
        } else if (x.is_usable()) {
            next_ = Memory{};  // a usable input that is false stops the timer
            out[kY] = Value::of(false, x.state);
        } else if (hold_ && now_.running && now_.stretch < hold_limit_) {
            // The timer runs on, and the output is uncertain: true once the time has run out.
            next_.stretch = now_.stretch + 1;
            next_.age = now_.age + 1;
            next_.counters.elapsed += 1;
            next_.counters.doubtful += 1;
            out[kY] = Value::of(next_.age > time_, State::uncertain);
        } else {
            next_ = Memory{};
            out[kY] = Value::none(x.state, Type::boolean);
        }
        // Zero while the timer is not running: a stopped timer's memory is all zero.
        next_.counters.give(out, kElapsed, period_seconds_);
    }

    void update(const Tick & /*tick*/, std::span<const Value> /*in*/) override { now_ = next_; }

    void gap(const Gap &gap) override {
        if (now_.running) {
            if (!gap.known || (gap.ticks > 0 && !hold_)) {
                now_ = Memory{};  // nobody knows, or `reset`: the timer stops
            } else {
                // `hold`: the unusable stretch grows by the ticks passed over. A gap that passed over none stops
                // no timer.
                now_.stretch += gap.ticks;
                if (now_.stretch > hold_limit_) {
                    now_ = Memory{};
                } else {
                    now_.age += gap.ticks;
                    now_.counters.elapsed += gap.ticks;
                    now_.counters.doubtful += gap.ticks;
                    now_.counters.gaps += 1;
                }
            }
        }
        now_.gap_here = true;
    }

    void reset() override { now_ = Memory{}; }

    void save(StateWriter &writer) const override {
        writer.flag(now_.running);
        writer.u64(now_.age);
        writer.u64(now_.stretch);
        now_.counters.save(writer);
    }

    bool restore(StateReader &reader) override {
        now_.gap_here = false;
        return reader.flag(now_.running) && reader.u64(now_.age) && reader.u64(now_.stretch) &&
               now_.counters.restore(reader);
    }

private:
    struct Memory {
        bool running = false;
        std::uint64_t age = 0;      // ticks since the tick the timer started on
        std::uint64_t stretch = 0;  // unusable ticks in a row
        Counters counters;
        bool gap_here = false;
    };

    std::array<InputPort, 1> inputs_ = {{{"x", Type::boolean, true, false}}};
    std::uint64_t time_ = 0;  // in ticks
    bool hold_ = false;
    std::uint64_t hold_limit_ = 0;
    Memory now_;
    Memory next_;
};

// ---- since_true (rule 7.6.2)

class SinceTrueBlock : public CountingBlock {
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

    void give(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out) override {
        const Value &x = in[0];
        next_ = now_;
        next_.gap_here = false;
        if (!now_.started) {
            next_.started = true;  // its clock starts at the first tick
            next_.age = 0;
        } else {
            next_.age = now_.age + 1;
        }
        if (x.is_usable() && x.boolean) {
            next_.age = 0;  // the clock is set again
            next_.lost = false;
            next_.counters = restarted(now_.gap_here);
        }
        next_.counters.elapsed += 1;
        next_.counters.doubtful += x.state != State::good ? 1 : 0;
        // After a gap of no known length the input was last true longer ago than `time`.
        const bool value = next_.lost || next_.age > time_;
        if (x.is_usable()) {
            out[kY] = Value::of(value, x.state);
        } else if (assume_false_) {
            out[kY] = Value::of(value, State::uncertain);
        } else {
            out[kY] = Value::none(x.state, Type::boolean);
        }
        next_.counters.give(out, kElapsed, period_seconds_);
    }

    void update(const Tick & /*tick*/, std::span<const Value> /*in*/) override { now_ = next_; }

    void gap(const Gap &gap) override {
        now_.gap_here = true;
        if (gap.known) {
            now_.age += gap.ticks;  // the clock is not set
            now_.counters.elapsed += gap.ticks;
            now_.counters.doubtful += gap.ticks;
            now_.counters.gaps += 1;
        } else {
            now_.lost = true;
            now_.counters = restarted(true);  // its counts start again at the gap's tick
        }
    }

    void reset() override { now_ = Memory{}; }

    void save(StateWriter &writer) const override {
        writer.flag(now_.started);
        writer.flag(now_.lost);
        writer.u64(now_.age);
        now_.counters.save(writer);
    }

    bool restore(StateReader &reader) override {
        now_.gap_here = false;
        return reader.flag(now_.started) && reader.flag(now_.lost) && reader.u64(now_.age) &&
               now_.counters.restore(reader);
    }

private:
    struct Memory {
        bool started = false;
        bool lost = false;      // a gap of no known length, and the clock not set since
        std::uint64_t age = 0;  // the tick's number less the clock's
        Counters counters;
        bool gap_here = false;
    };

    std::array<InputPort, 1> inputs_ = {{{"x", Type::boolean, true, false}}};
    std::uint64_t time_ = 0;
    bool assume_false_ = false;
    Memory now_;
    Memory next_;
};

// ---- latch (rule 7.6.3)

class LatchBlock : public CountingBlock {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        period_seconds_ = static_cast<double>(setup.period) / 1e9;
        return settings.finish();
    }

    std::span<const InputPort> inputs() const override { return inputs_; }

    void give(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out) override {
        const Value &set = in[0];
        const Value &reset = in[1];
        next_ = now_;
        next_.gap_here = false;
        if (reset.is_usable() && reset.boolean) {
            next_.set = false;
            next_.counters = restarted(now_.gap_here);  // `elapsed` counts from the tick it was last cleared
            out[kY] = Value::of(false, reset.state);
        } else if (now_.set) {
            out[kY] = Value::of(true);  // `set` is not used
        } else if (set.is_usable()) {
            next_.set = set.boolean;
            out[kY] = Value::of(set.boolean, set.state);
        } else {
            out[kY] = Value::none(set.state, Type::boolean);
        }
        next_.counters.elapsed += 1;
        // Those on which it was not set when the tick began and `set` was not good.
        next_.counters.doubtful += !now_.set && set.state != State::good ? 1 : 0;
        next_.counters.give(out, kElapsed, period_seconds_);
    }

    void update(const Tick & /*tick*/, std::span<const Value> /*in*/) override { now_ = next_; }

    void gap(const Gap &gap) override {
        now_.counters.gaps += 1;
        now_.gap_here = true;
        if (gap.known) {
            now_.counters.elapsed += gap.ticks;
            now_.counters.doubtful += now_.set ? 0 : gap.ticks;
        }
    }

    void reset() override { now_ = Memory{}; }

    void save(StateWriter &writer) const override {
        writer.flag(now_.set);
        now_.counters.save(writer);
    }

    bool restore(StateReader &reader) override {
        now_.gap_here = false;
        return reader.flag(now_.set) && now_.counters.restore(reader);
    }

private:
    struct Memory {
        bool set = false;
        Counters counters;
        bool gap_here = false;
    };

    std::array<InputPort, 2> inputs_ = {{{"set", Type::boolean, true, false}, {"reset", Type::boolean, false, false}}};
    Memory now_;
    Memory next_;
};

}  // namespace

Result<std::unique_ptr<Block>> make_hysteresis(const BlockSetup &setup) { return make_block<HysteresisBlock>(setup); }
Result<std::unique_ptr<Block>> make_held_for(const BlockSetup &setup) { return make_block<HeldForBlock>(setup); }
Result<std::unique_ptr<Block>> make_since_true(const BlockSetup &setup) { return make_block<SinceTrueBlock>(setup); }
Result<std::unique_ptr<Block>> make_latch(const BlockSetup &setup) { return make_block<LatchBlock>(setup); }

}  // namespace fluxgraph::v2::detail

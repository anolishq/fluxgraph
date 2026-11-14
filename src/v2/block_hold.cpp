// `deadband`, `lowpass` and `rate_limit` (section 7.4): the blocks that hold a value and ride through.

#include <array>
#include <cmath>
#include <format>
#include <optional>

#include "blocks.hpp"
#include "exact.hpp"

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

class HoldBlock : public Block {
public:
    std::span<const InputPort> inputs() const override { return inputs_; }
    Status bind(std::span<const std::optional<Type>> /*input_types*/) override { return {}; }

protected:
    std::array<InputPort, 1> inputs_ = {{{"x", Type::number, true, false}}};
    Ride ride_;
};

// ---- deadband (rules 7.4.1 to 7.4.4)

class DeadbandBlock : public HoldBlock {
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

    void give(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out) override {
        const Value &x = in[0];
        next_ = now_;
        if (x.is_usable()) {
            // The first usable input is taken as it is; after that, one that has moved by `step` or more.
            if (!now_.holding || std::fabs(x.number - now_.value) >= step_) {
                next_.value = x.number;
            }
            next_.holding = true;
            next_.run = 0;
            out[0] = Value::of(next_.value, x.state);  // the state of the input at this tick
        } else if (now_.holding && ride_.rides(now_.run)) {
            next_.run = now_.run + 1;
            out[0] = Value::of(now_.value, State::uncertain);
        } else {
            next_ = Memory{};
            out[0] = Value::none(x.state);
        }
    }

    void update(const Tick & /*tick*/, std::span<const Value> /*in*/) override { now_ = next_; }

    void gap(const Gap &gap) override {
        if (!gap.known) {
            now_ = Memory{};
        } else if (now_.holding) {
            now_.run += gap.ticks;  // counts of ticks: see Counters
            if (!ride_.holds(now_.run)) {
                now_ = Memory{};
            }
        }
    }

    void reset() override { now_ = Memory{}; }

    void save(StateWriter &writer) const override {
        writer.flag(now_.holding);
        writer.f64(now_.value);
        writer.u64(now_.run);
    }

    bool restore(StateReader &reader) override {
        return reader.flag(now_.holding) && reader.f64(now_.value) && reader.u64(now_.run);
    }

private:
    struct Memory {
        bool holding = false;
        double value = 0.0;
        std::uint64_t run = 0;  // unusable ticks in a row since the last usable input
    };

    std::array<OutputPort, 1> outputs_ = {{{"y", Type::number, false}}};
    double step_ = 0.0;
    Memory now_;
    Memory next_;
};

// ---- lowpass (rules 7.4.5 to 7.4.8)

class LowpassBlock : public HoldBlock {
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

    void give(const Tick &tick, std::span<const Value> in, std::span<Value> out) override {
        const Value &x = in[0];
        next_ = now_;
        if (x.is_usable()) {
            if (!now_.holding) {
                next_.y = x.number;
            } else {
                // The ticks it rode through decay too: m is the ticks since its last usable input.
                const double kept = now_.run == 0 ? decay_ : std::pow(decay_, static_cast<double>(now_.run) + 1.0);
                next_.y = kept * now_.y + (1.0 - kept) * x.number;
            }
            next_.holding = true;
            next_.run = 0;
            if (x.state == State::uncertain) {  // rule 7.4.7: its doubt, a first input among them
                next_.doubted = true;
                next_.doubt = tick.number;
            }
            // Rule 7.4.8: uncertain if the input is, and on the `settle` ticks after its doubt. A tick is never
            // before the doubt, so the difference is in order.
            const bool settling = next_.doubted && span_between(next_.doubt, tick.number) <= settle_;
            out[0] = Value::of(next_.y, x.state == State::uncertain || settling ? State::uncertain : State::good);
        } else if (now_.holding && ride_.rides(now_.run)) {
            next_.run = now_.run + 1;
            out[0] = Value::of(now_.y, State::uncertain);
        } else {
            next_ = Memory{};  // forgetting clears its doubt
            out[0] = Value::none(x.state);
        }
    }

    void update(const Tick & /*tick*/, std::span<const Value> /*in*/) override { now_ = next_; }

    void gap(const Gap &gap) override {
        if (!gap.known) {
            now_ = Memory{};
        } else if (now_.holding) {
            now_.run += gap.ticks;
            if (!ride_.holds(now_.run)) {
                now_ = Memory{};
            }
        }
    }

    void reset() override { now_ = Memory{}; }

    void save(StateWriter &writer) const override {
        writer.flag(now_.holding);
        writer.f64(now_.y);
        writer.u64(now_.run);
        writer.flag(now_.doubted);
        writer.u64(static_cast<std::uint64_t>(now_.doubt));
    }

    bool restore(StateReader &reader) override {
        std::uint64_t doubt = 0;
        if (!reader.flag(now_.holding) || !reader.f64(now_.y) || !reader.u64(now_.run) || !reader.flag(now_.doubted) ||
            !reader.u64(doubt)) {
            return false;
        }
        now_.doubt = static_cast<std::int64_t>(doubt);
        return true;
    }

private:
    struct Memory {
        bool holding = false;
        double y = 0.0;
        std::uint64_t run = 0;
        bool doubted = false;
        std::int64_t doubt = 0;  // the number of the latest tick at which it took an uncertain input
    };

    std::array<OutputPort, 1> outputs_ = {{{"y", Type::number, false}}};
    double decay_ = 0.0;
    std::uint64_t settle_ = 0;  // in ticks
    Memory now_;
    Memory next_;
};

// ---- rate_limit (rules 7.4.9 to 7.4.11)

class RateLimitBlock : public HoldBlock {
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
        return settings.finish();
    }

    std::span<const OutputPort> outputs() const override { return outputs_; }

    void give(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out) override {
        const Value &x = in[0];
        next_ = now_;
        if (x.is_usable()) {
            double y = x.number;  // the first usable input, and one within reach, is taken as it is
            if (now_.holding) {
                if (x.number - now_.value > reach_up_) {
                    y = now_.value + reach_up_;
                } else if (now_.value - x.number > reach_down_) {
                    y = now_.value - reach_down_;
                }
            }
            next_.holding = true;
            next_.only_initial = false;
            next_.value = y;
            next_.run = 0;
            out[0] = Value::of(y, x.state);
            out[1] = Value::of(y != x.number, x.state);  // `limited`: the output is not the input
            return;
        }
        // Holding `initial` and nothing else it does not ride through.
        if (now_.holding && !now_.only_initial && ride_.rides(now_.run)) {
            next_.run = now_.run + 1;
            out[0] = Value::of(now_.value, State::uncertain);
        } else {
            next_ = start();
            out[0] = Value::none(x.state);
        }
        out[1] = Value::none(x.state, Type::boolean);  // there is nothing to compare
    }

    void update(const Tick & /*tick*/, std::span<const Value> /*in*/) override { now_ = next_; }

    void gap(const Gap &gap) override {
        if (!gap.known) {
            now_ = start();
        } else if (now_.holding && !now_.only_initial) {
            now_.run += gap.ticks;
            if (!ride_.holds(now_.run)) {
                now_ = start();
            }
        }
    }

    void reset() override { now_ = start(); }

    void save(StateWriter &writer) const override {
        writer.flag(now_.holding);
        writer.flag(now_.only_initial);
        writer.f64(now_.value);
        writer.u64(now_.run);
    }

    bool restore(StateReader &reader) override {
        return reader.flag(now_.holding) && reader.flag(now_.only_initial) && reader.f64(now_.value) &&
               reader.u64(now_.run);
    }

private:
    struct Memory {
        bool holding = false;
        bool only_initial = false;  // what it holds is `initial`, and no output it has given
        double value = 0.0;
        std::uint64_t run = 0;
    };

    // As it is made, and as it is having forgotten: holding `initial` if it was given one.
    Memory start() const { return Memory{has_initial_, has_initial_, initial_, 0}; }

    std::array<OutputPort, 2> outputs_ = {{{"y", Type::number, false}, {"limited", Type::boolean, false}}};
    double reach_up_ = 0.0;
    double reach_down_ = 0.0;
    bool has_initial_ = false;
    double initial_ = 0.0;
    Memory now_;
    Memory next_;
};

}  // namespace

Result<std::unique_ptr<Block>> make_deadband(const BlockSetup &setup) { return make_block<DeadbandBlock>(setup); }
Result<std::unique_ptr<Block>> make_lowpass(const BlockSetup &setup) { return make_block<LowpassBlock>(setup); }
Result<std::unique_ptr<Block>> make_rate_limit(const BlockSetup &setup) { return make_block<RateLimitBlock>(setup); }

}  // namespace fluxgraph::v2::detail

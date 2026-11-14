// `pid` (rules 7.7.5 to 7.7.12): a controller whose integral is a running total.

#include <algorithm>
#include <array>
#include <cmath>
#include <format>
#include <optional>

#include "blocks.hpp"

namespace fluxgraph::v2::detail {

namespace {

enum In : std::size_t { kSetpoint, kMeasurement, kReset, kApplied };
enum Out : std::size_t { kY, kIntegral, kLimited, kElapsed, kDoubtful, kGaps, kPorts };

class PidBlock : public Block {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        if (!settings.number("kp", kp_) && !settings.failed()) {
            settings.fail("has no 'kp' setting");
        }
        settings.number("ki", ki_);
        settings.number("kd", kd_);
        double ratio = 0.0;
        const bool filtered = settings.period_over("filter", ratio);
        if (!settings.failed() && filtered != (kd_ != 0.0)) {
            // `filter` is given when `kd` is not zero and only then.
            settings.fail(filtered ? "'filter' is given, and is only for a 'kd' that is not zero"
                                   : "'filter' has to be given with a 'kd' that is not zero");
        }
        has_min_ = settings.number("min", min_);
        has_max_ = settings.number("max", max_);
        if (!settings.failed() && has_min_ && has_max_ && !(min_ < max_)) {
            settings.fail(std::format("'min' is {} and 'max' is {}: 'min' has to be less than 'max'", min_, max_));
        }
        settings.not_negative("applied_within", applied_within_);
        keep_ = std::exp(-ratio);  // a = exp(-period / filter)
        period_seconds_ = static_cast<double>(setup.period) / 1e9;
        return settings.finish();
    }

    std::span<const InputPort> inputs() const override { return inputs_; }
    std::span<const OutputPort> outputs() const override { return outputs_; }
    Status bind(std::span<const std::optional<Type>> /*input_types*/) override { return {}; }

    void give(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out) override {
        const Value &setpoint = in[kSetpoint];
        const Value &measurement = in[kMeasurement];
        const Value &reset = in[kReset];
        const bool resets = reset.is_usable() && reset.boolean;  // rule 10; any other reset is not used
        const bool reset_in_doubt = resets && reset.state == State::uncertain;
        next_ = now_;
        if (resets) {
            // The integral and the counts to zero and the derivative to its start, before this tick's addition.
            next_ = Memory{};
            next_.counters.gaps = now_.gap_here ? 1 : 0;  // rule 11: a gap whose tick is the reset's is counted
        }
        next_.gap_here = false;
        next_.counters.elapsed += 1;
        next_.counters.doubtful += setpoint.state != State::good || measurement.state != State::good ? 1 : 0;
        added_ = 0.0;
        before_ = next_.integral;

        const State state = worst(setpoint.state, measurement.state);
        if (!usable(state)) {
            // Rule 8: no value, the integral kept, and the derivative to start again when they are back.
            next_.has_last = false;
            next_.slope = 0.0;
            out[kY] = Value::none(state);
            out[kLimited] = Value::none(state, Type::boolean);
            out[kIntegral] = Value::of(next_.integral, reset_in_doubt ? State::uncertain : State::good);
            next_.counters.give(out, kElapsed, period_seconds_);
            return;
        }

        const double error = setpoint.number - measurement.number;
        // Rule 7: of the measurement, through a filter; with no tick before, zero.
        if (kd_ != 0.0 && next_.has_last) {
            const double moved = (measurement.number - next_.last) / period_seconds_;
            next_.slope = keep_ * next_.slope + (1.0 - keep_) * moved;
        } else {
            next_.slope = 0.0;
        }
        next_.has_last = true;
        next_.last = measurement.number;
        const double derivative = kd_ != 0.0 ? -kd_ * next_.slope : 0.0;
        const double proportional = kp_ * error;

        // Rule 6: an addition that would put the output before limiting past a limit is cut short.
        added_ = ki_ * error * period_seconds_;
        // Rule 5: the sum in one order. The proportional term and the derivative first, then the integral.
        const double rest = proportional + derivative;
        const double whole = rest + (before_ + added_);
        double y = 0.0;
        bool limited = false;
        if (has_max_ && added_ > 0.0 && whole > max_) {
            // What puts that output at `max`, or as it is if that is less than it has.
            next_.integral = std::max(before_, max_ - rest);
            y = max_;
            limited = true;
        } else if (has_min_ && added_ < 0.0 && whole < min_) {
            next_.integral = std::min(before_, min_ - rest);
            y = min_;
            limited = true;
        } else {
            next_.integral = before_ + added_;
            y = whole;
            if (has_max_ && y > max_) {
                y = max_;
                limited = true;
            } else if (has_min_ && y < min_) {
                y = min_;
                limited = true;
            }
        }
        given_ = y;
        const State y_state = reset_in_doubt ? State::uncertain : state;
        out[kY] = Value::of(y, y_state);
        out[kLimited] = Value::of(limited, y_state);
        out[kIntegral] = Value::of(next_.integral, y_state);
        next_.counters.give(out, kElapsed, period_seconds_);
    }

    void update(const Tick & /*tick*/, std::span<const Value> in) override {
        // Rule 12: what was applied. Where it fell short of `y` in the direction of this tick's addition by more
        // than `applied_within`, the addition is taken back: the integral is what it was before this tick.
        const Value &applied = in[kApplied];
        if (applied.is_usable() && ((added_ > 0.0 && given_ - applied.number > applied_within_) ||
                                    (added_ < 0.0 && applied.number - given_ > applied_within_))) {
            next_.integral = before_;
        }
        now_ = next_;
    }

    void gap(const Gap &gap) override {
        now_.counters.gaps += 1;
        now_.gap_here = true;
        if (!gap.known || gap.ticks > 0) {
            now_.has_last = false;  // the derivative starts again; the integral is unchanged
            now_.slope = 0.0;
        }
        if (gap.known) {
            now_.counters.elapsed += gap.ticks;
            now_.counters.doubtful += gap.ticks;
        }
    }

    void reset() override { now_ = Memory{}; }

    void save(StateWriter &writer) const override {
        writer.f64(now_.integral);
        writer.flag(now_.has_last);
        writer.f64(now_.last);
        writer.f64(now_.slope);
        now_.counters.save(writer);
    }

    bool restore(StateReader &reader) override {
        now_.gap_here = false;
        return reader.f64(now_.integral) && reader.flag(now_.has_last) && reader.f64(now_.last) &&
               reader.f64(now_.slope) && now_.counters.restore(reader);
    }

private:
    struct Memory {
        double integral = 0.0;
        bool has_last = false;  // there is a tick before, with both inputs usable, for the derivative
        double last = 0.0;      // its measurement
        double slope = 0.0;     // the filtered rate of the measurement, `f`
        Counters counters;
        bool gap_here = false;
    };

    std::array<InputPort, 4> inputs_ = {{
        {"setpoint", Type::number, true, false},
        {"measurement", Type::number, true, false},
        {"reset", Type::boolean, false, false},
        {"applied", Type::number, false, true},
    }};
    std::array<OutputPort, kPorts> outputs_ = {{
        {"y", Type::number, false},
        {"integral", Type::number, false},
        {"limited", Type::boolean, false},
        {"elapsed", Type::number, false},
        {"doubtful", Type::number, false},
        {"gaps", Type::number, false},
    }};
    double kp_ = 0.0;
    double ki_ = 0.0;
    double kd_ = 0.0;
    double keep_ = 0.0;
    bool has_min_ = false;
    bool has_max_ = false;
    double min_ = 0.0;
    double max_ = 0.0;
    double applied_within_ = 0.0;
    double period_seconds_ = 1.0;

    Memory now_;
    Memory next_;
    // Of the tick being run, from give() for update(): the addition made (zero where none was), the integral
    // before it, and the `y` given.
    double added_ = 0.0;
    double before_ = 0.0;
    double given_ = 0.0;
};

}  // namespace

Result<std::unique_ptr<Block>> make_pid(const BlockSetup &setup) { return make_block<PidBlock>(setup); }

}  // namespace fluxgraph::v2::detail

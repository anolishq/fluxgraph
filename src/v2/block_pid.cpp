// `pid` (rules 7.7.5 to 7.7.12): a controller whose integral is a running total.

#include <algorithm>
#include <array>
#include <cmath>
#include <format>
#include <optional>

#include "blocks.hpp"
#include "exact.hpp"

namespace fluxgraph::v2::detail {

namespace {

enum In : std::size_t { kSetpoint, kMeasurement, kReset, kApplied, kTrack };
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
        const bool filtered = settings.seconds("filter", filter_);
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
        period_seconds_ = static_cast<double>(setup.period) / 1e9;
        return settings.finish();
    }

    std::span<const InputPort> inputs() const override { return inputs_; }
    std::span<const OutputPort> outputs() const override { return outputs_; }
    Status bind(std::span<const std::optional<Type>> /*input_types*/) override { return {}; }

    CallRole call_role() const override { return CallRole{CallRole::Kind::controller, kY}; }

    void give(const Tick &tick, std::span<const Value> in, std::span<Value> out) override {
        // Rule 7.7.13: one that acts by the call adds nothing at a catch-up tick, and at the last tick of a call
        // adds for the periods it acts for. All else is as at any tick.
        const bool acts = !tick.acts_by_call || tick.last_of_call;
        const double periods = tick.acts_by_call ? static_cast<double>(tick.periods) : 1.0;
        const Value &track = in[kTrack];
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
            next_.waiting = false;  // rule 14: it stops waiting at the tick of a reset, whatever that tick reads
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
            next_.waiting = !resets;  // rule 14: it waits to track; a reset wins
            out[kY] = Value::none(state);
            out[kLimited] = Value::none(state, Type::boolean);
            out[kIntegral] = Value::of(next_.integral, reset_in_doubt ? State::uncertain : State::good);
            next_.counters.give(out, kElapsed, period_seconds_);
            return;
        }

        const double error = setpoint.number - measurement.number;
        // Rule 7: of the measurement, between samples. A measurement's time is its sample time, or the tick's
        // where it carries none.
        const Time taken_at = measurement.timed ? measurement.time : tick.time;
        if (kd_ == 0.0 || !next_.has_last) {
            next_.slope = 0.0;  // none remembered: f is zero, and the measurement is taken
            next_.has_last = true;
            next_.last = measurement.number;
            next_.last_time = taken_at;
        } else if (taken_at > next_.last_time) {
            // The time between the two, in seconds: the difference in nanoseconds, divided by 10^9.
            const double dt = static_cast<double>(span_between(next_.last_time, taken_at)) / 1e9;
            const double moved = (measurement.number - next_.last) / dt;
            const double keep = std::exp(-dt / filter_);  // a, with the filter over the time between them
            next_.slope = keep * next_.slope + (1.0 - keep) * moved;
            next_.last = measurement.number;
            next_.last_time = taken_at;
        }  // otherwise the sample last taken stands still, or this one is no later: nothing is taken, f stands
        const double derivative = kd_ != 0.0 ? -kd_ * next_.slope : 0.0;
        const double proportional = kp_ * error;

        // Rule 5: the sum in one order. The proportional term and the derivative first, then the integral.
        const double rest = proportional + derivative;
        // Rule 14: at the tick it stops waiting to track, which is not the tick of a reset, the integral is
        // set, before that tick's addition, to `track` less that first sum.
        if (next_.waiting && acts) {
            next_.waiting = false;
            if (track.is_usable()) {
                next_.integral = track.number - rest;
                before_ = next_.integral;
            }
        }
        // Rule 6: an addition that would put the output before limiting past a limit is cut short.
        added_ = acts ? ki_ * error * period_seconds_ * periods : 0.0;
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
        // The derivative starts again at a gap of either kind, one that passed over no tick among them: a rebase
        // forgets every sample time (rules 7.7.7 and 8.5). The integral is unchanged.
        now_.has_last = false;
        now_.slope = 0.0;
        if (!gap.known || gap.ticks > 0) {
            now_.waiting = true;  // and it waits to track (rule 7.7.14)
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
        // Not saved, and need not be: a restore is a gap of no known length, which sets it (rules 8.2, 8.6).
        now_.waiting = true;
        return reader.f64(now_.integral) && reader.flag(now_.has_last) && reader.f64(now_.last) &&
               reader.f64(now_.slope) && now_.counters.restore(reader);
    }

private:
    struct Memory {
        double integral = 0.0;
        bool has_last = false;  // there is a tick before, with both inputs usable, for the derivative
        double last = 0.0;      // its measurement
        Time last_time = 0;     // and its time; not saved, since a restore is a rebase, which forgets it
        double slope = 0.0;     // the filtered rate of the measurement, `f`
        Counters counters;
        bool gap_here = false;
        bool waiting = true;  // to track (rule 7.7.14): from the start
    };

    std::array<InputPort, 5> inputs_ = {{
        {"setpoint", Type::number, true, false},
        {"measurement", Type::number, true, false},
        {"reset", Type::boolean, false, false},
        {"applied", Type::number, false, true},
        {"track", Type::number, false, false},
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
    double filter_ = 1.0;  // in seconds
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

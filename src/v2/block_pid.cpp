// `pid` (rules 7.7.5 to 7.7.15): a controller whose integral is a running total.

#include <algorithm>
#include <array>
#include <cmath>
#include <format>
#include <optional>

#include "blocks.hpp"
#include "exact.hpp"
#include "remembers.hpp"

namespace fluxgraph::v2::detail {

namespace {

enum In : std::size_t { kSetpoint, kMeasurement, kReset, kApplied, kTrack, kFollow };
enum Out : std::size_t { kY, kIntegral, kLimited, kElapsed, kDoubtful, kGaps, kPorts };

// `last_time`, `gap_here` and `waiting` are not saved, and need not be: a restore is a gap of no known length,
// which forgets every sample time and sets the other two (rules 8.2, 8.5 and 8.6).
struct Memory {
    double integral = 0.0;
    bool has_last = false;  // there is a tick before, with both inputs usable, for the derivative
    double last = 0.0;      // its measurement
    Time last_time = 0;     // and its time
    double slope = 0.0;     // the filtered rate of the measurement, `f`
    Counters counters;
    bool gap_here = false;
    bool waiting = true;  // to track (rule 7.7.14): from the start
    // Of the tick being run, from the first phase for the second: the addition made (zero where none was), the
    // integral before it, and the `y` given. Not saved: the first phase sets them before the second reads them.
    double added = 0.0;
    double before = 0.0;
    double given = 0.0;
};

class PidBlock : public Committing<Memory> {
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

    std::span<const InputPort> inputs() const override { return inputs_; }
    std::span<const OutputPort> outputs() const override { return outputs_; }
    Status bind(std::span<const std::optional<Type>> /*input_types*/) override { return {}; }

    CallRole call_role() const override { return CallRole{CallRole::Kind::controller, kY}; }

protected:
    void step(const Tick &tick, std::span<const Value> in, std::span<Value> out, const Memory &now,
              Memory &next) const override {
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
        // Rule 15: it follows where `follow` is true, and where it is not usable, a catch-up tick among them.
        const Value &follow = in[kFollow];
        const bool follows = follows_ && (!follow.is_usable() || follow.boolean);
        if (resets) {
            // The integral and the counts to zero and the derivative to its start, before this tick's addition.
            next = Memory{};
            next.counters.gaps = now.gap_here ? 1 : 0;  // rule 11: a gap whose tick is the reset's is counted
            next.waiting = false;  // rule 14: it stops waiting at the tick of a reset, whatever that tick reads
        }
        next.gap_here = false;
        next.counters.elapsed += 1;
        next.counters.doubtful += setpoint.state != State::good || measurement.state != State::good ? 1 : 0;
        next.added = 0.0;
        next.before = next.integral;

        const State state = worst(setpoint.state, measurement.state);
        if (!usable(state)) {
            // Rule 8: no value, the integral kept, and the derivative to start again when they are back.
            next.has_last = false;
            next.slope = 0.0;
            next.waiting = !resets || follows;  // rule 14: it waits to track; a reset wins, unless it follows
            if (follows) {
                give_track(track, follow, out);  // it needs neither input to follow
            } else {
                out[kY] = Value::none(state);
                out[kLimited] = Value::none(state, Type::boolean);
            }
            out[kIntegral] = Value::of(next.integral, reset_in_doubt ? State::uncertain : State::good);
            next.counters.give(out, kElapsed, period_seconds_);
            return;
        }

        const double error = setpoint.number - measurement.number;
        // Rule 7: of the measurement, between samples. A measurement's time is its sample time, or the tick's
        // where it carries none.
        const Time taken_at = measurement.timed ? measurement.time : tick.time;
        if (kd_ == 0.0 || !next.has_last) {
            next.slope = 0.0;  // none remembered: f is zero, and the measurement is taken
            next.has_last = true;
            next.last = measurement.number;
            next.last_time = taken_at;
        } else if (taken_at > next.last_time) {
            // The time between the two, in seconds: the difference in nanoseconds, divided by 10^9.
            const double dt = static_cast<double>(span_between(next.last_time, taken_at)) / 1e9;
            const double moved = (measurement.number - next.last) / dt;
            const double keep = std::exp(-dt / filter_);  // a, with the filter over the time between them
            next.slope = keep * next.slope + (1.0 - keep) * moved;
            next.last = measurement.number;
            next.last_time = taken_at;
        }  // otherwise the sample last taken stands still, or this one is no later: nothing is taken, f stands
        const double derivative = kd_ != 0.0 ? -kd_ * next.slope : 0.0;
        const double proportional = kp_ * error;

        // Rule 5: the sum in one order. The proportional term and the derivative first, then the integral.
        const double rest = proportional + derivative;
        if (follows) {
            // Rule 15: it adds nothing, and its integral is set to `track` less that first sum where `track` is
            // usable and there is no reset. It waits to track from this tick, a tick of a reset among them.
            if (track.is_usable() && !resets) {
                next.integral = track.number - rest;
            }
            next.waiting = true;
            give_track(track, follow, out);
            // Its state is what rule 9 gives it at a tick where the PID does not follow.
            out[kIntegral] = Value::of(next.integral, reset_in_doubt ? State::uncertain : state);
            next.counters.give(out, kElapsed, period_seconds_);
            return;
        }
        // Rule 14: at the tick it stops waiting to track, which is not the tick of a reset, the integral is
        // set, before that tick's addition, to `track` less that first sum.
        if (next.waiting && acts) {
            next.waiting = false;
            if (track.is_usable()) {
                next.integral = track.number - rest;
                next.before = next.integral;
            }
        }
        // Rule 6: an addition that would put the output before limiting past a limit is cut short.
        next.added = acts ? ki_ * error * period_seconds_ * periods : 0.0;
        const double whole = rest + (next.before + next.added);
        double y = 0.0;
        bool limited = false;
        if (has_max_ && next.added > 0.0 && whole > max_) {
            // What puts that output at `max`, or as it is if that is less than it has.
            next.integral = std::max(next.before, max_ - rest);
            y = max_;
            limited = true;
        } else if (has_min_ && next.added < 0.0 && whole < min_) {
            next.integral = std::min(next.before, min_ - rest);
            y = min_;
            limited = true;
        } else {
            next.integral = next.before + next.added;
            y = whole;
            if (has_max_ && y > max_) {
                y = max_;
                limited = true;
            } else if (has_min_ && y < min_) {
                y = min_;
                limited = true;
            }
        }
        next.given = y;
        const State y_state = reset_in_doubt ? State::uncertain : state;
        out[kY] = Value::of(y, y_state);
        out[kLimited] = Value::of(limited, y_state);
        out[kIntegral] = Value::of(next.integral, y_state);
        next.counters.give(out, kElapsed, period_seconds_);
    }

    void take(const Tick & /*tick*/, std::span<const Value> in, const Memory & /*now*/, Memory &next) const override {
        // Rule 12: what was applied. Where it fell short of `y` in the direction of this tick's addition by more
        // than `applied_within`, the addition is taken back: the integral is what it was before this tick.
        const Value &applied = in[kApplied];
        if (applied.is_usable() && ((next.added > 0.0 && next.given - applied.number > applied_within_) ||
                                    (next.added < 0.0 && applied.number - next.given > applied_within_))) {
            next.integral = next.before;
        }
    }

    void pass_over(const Gap &gap, Memory &now) const override {
        now.counters.gaps += 1;
        now.gap_here = true;
        // The derivative starts again at a gap of either kind, one that passed over no tick among them: a rebase
        // forgets every sample time (rules 7.7.7 and 8.5). The integral is unchanged.
        now.has_last = false;
        now.slope = 0.0;
        if (!gap.known || gap.ticks > 0) {
            now.waiting = true;  // and it waits to track (rule 7.7.14)
        }
        if (gap.known) {
            now.counters.elapsed += gap.ticks;
            now.counters.doubtful += gap.ticks;
        }
    }

    void describe(Fields &fields, Memory &memory) const override {
        fields(memory.integral);
        fields(memory.has_last);
        fields(memory.last);
        fields(memory.slope);
        fields(memory.counters);
    }

private:
    // What a PID that follows gives (rule 15): `track` as it is, not held within `min` and `max`, and `limited`
    // false, each with the state of `track`, or `uncertain` in place of `good` where `follow` is not usable.
    static void give_track(const Value &track, const Value &follow, std::span<Value> out) {
        if (track.is_usable()) {
            const State state = follow.is_usable() ? track.state : State::uncertain;
            out[kY] = Value::of(track.number, state);
            out[kLimited] = Value::of(false, state);
        } else {
            out[kY] = Value::none(track.state);
            out[kLimited] = Value::none(track.state, Type::boolean);
        }
    }

    std::array<InputPort, 6> inputs_ = {{
        {"setpoint", Type::number, true, false},
        {"measurement", Type::number, true, false},
        {"reset", Type::boolean, false, false},
        {"applied", Type::number, false, true},
        {"track", Type::number, false, false},
        {"follow", Type::boolean, false, false},
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
    bool follows_ = false;  // `follow` is connected: left unconnected, the PID acts
};

}  // namespace

Result<std::unique_ptr<Block>> make_pid(const BlockSetup &setup) { return make_block<PidBlock>(setup); }

}  // namespace fluxgraph::v2::detail

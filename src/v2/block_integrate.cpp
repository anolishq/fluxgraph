// `integrate` (rules 7.7.1 to 7.7.4): a running total, and counts of what it lacks.

#include <array>
#include <format>
#include <optional>

#include "blocks.hpp"

namespace fluxgraph::v2::detail {

namespace {

enum Port : std::size_t { kTotal, kMissed, kDoubtful, kElapsed, kGaps, kPorts };

// The counts are of ticks. Every tick counted, run or passed over, has a number of its own that fits in 64 bits
// signed (rule 6.11), so no count passes 2^63 and none of the additions below can wrap.
struct Memory {
    double total = 0.0;
    std::uint64_t missed = 0;
    std::uint64_t doubtful = 0;
    std::uint64_t elapsed = 0;
    std::uint64_t gaps = 0;
    bool lost = false;      // a gap of no known length, with max_missed given: bad until a reset (rule 7.7.2)
    bool gap_here = false;  // a gap whose tick is the next to run: a reset at that tick still counts it
};

class IntegrateBlock : public Block {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        double per = 1e9;  // 1s
        if (settings.scale("per", per) && !(per > 0.0)) {
            settings.fail("setting 'per' has to be more than zero");
        }
        has_max_missed_ = settings.counted("max_missed", max_missed_);
        if (Status status = settings.finish(); !status) {
            return status;
        }
        scale_ = static_cast<double>(setup.period) / per;  // Appendix A: it adds x * period / per
        period_seconds_ = static_cast<double>(setup.period) / 1e9;
        return {};
    }

    std::span<const InputPort> inputs() const override { return inputs_; }
    std::span<const OutputPort> outputs() const override { return outputs_; }
    Status bind(std::span<const std::optional<Type>> /*input_types*/) override { return {}; }

    void give(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out) override {
        const Value &x = in[0];
        const Value &reset = in[1];
        const bool resets = reset.is_usable() && reset.boolean;  // rule 7.7.4; any other reset is not used
        next_ = now_;
        if (resets) {
            next_ = Memory{};
            next_.gaps = now_.gap_here ? 1 : 0;  // rule 7.7.3: a gap whose tick is the tick of the reset is counted
        }
        next_.gap_here = false;
        next_.elapsed += 1;
        if (x.is_usable()) {
            next_.total += x.number * scale_;  // rule 7.7.1: the value at a tick includes that tick's addition
            next_.doubtful += x.state == State::uncertain ? 1 : 0;
        } else {
            next_.missed += 1;
        }

        State state = State::good;  // rule 7.7.2, the first that applies
        if (next_.lost || (has_max_missed_ && next_.missed > max_missed_)) {
            state = State::bad;
        } else if (x.state == State::uncertain || (resets && reset.state == State::uncertain)) {
            state = State::uncertain;
        }
        out[kTotal] = usable(state) ? Value::of(next_.total, state) : Value::none(state);
        out[kMissed] = Value::of(static_cast<double>(next_.missed) * period_seconds_);
        out[kDoubtful] = Value::of(static_cast<double>(next_.doubtful) * period_seconds_);
        out[kElapsed] = Value::of(static_cast<double>(next_.elapsed) * period_seconds_);
        out[kGaps] = Value::of(static_cast<double>(next_.gaps));
    }

    void update(const Tick & /*tick*/, std::span<const Value> /*in*/) override { now_ = next_; }

    void gap(const Gap &gap) override {
        now_.gaps += 1;
        now_.gap_here = true;
        if (gap.known) {
            now_.missed += gap.ticks;
            now_.elapsed += gap.ticks;
        } else if (has_max_missed_) {
            now_.lost = true;  // what it missed is more than any max_missed
        }
    }

    void reset() override { now_ = Memory{}; }

    void save(StateWriter &writer) const override {
        writer.f64(now_.total);
        writer.u64(now_.missed);
        writer.u64(now_.doubtful);
        writer.u64(now_.elapsed);
        writer.u64(now_.gaps);
        writer.flag(now_.lost);
        writer.flag(now_.gap_here);
    }

    bool restore(StateReader &reader) override {
        return reader.f64(now_.total) && reader.u64(now_.missed) && reader.u64(now_.doubtful) &&
               reader.u64(now_.elapsed) && reader.u64(now_.gaps) && reader.flag(now_.lost) &&
               reader.flag(now_.gap_here);
    }

private:
    std::array<InputPort, 2> inputs_ = {{{"x", Type::number, true, false}, {"reset", Type::boolean, false, false}}};
    std::array<OutputPort, kPorts> outputs_ = {{
        {"y", Type::number, false},
        {"missed", Type::number, false},
        {"doubtful", Type::number, false},
        {"elapsed", Type::number, false},
        {"gaps", Type::number, false},
    }};
    bool has_max_missed_ = false;
    std::uint64_t max_missed_ = 0;  // in ticks
    double scale_ = 1.0;
    double period_seconds_ = 1.0;

    Memory now_;   // as the last tick left it
    Memory next_;  // as this tick leaves it, from give() until update() takes it
};

}  // namespace

Result<std::unique_ptr<Block>> make_integrate(const BlockSetup &setup) { return make_block<IntegrateBlock>(setup); }

}  // namespace fluxgraph::v2::detail

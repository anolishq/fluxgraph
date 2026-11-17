// `integrate` (rules 7.7.1 to 7.7.4): a running total, and counts of what it lacks.

#include <array>
#include <format>
#include <optional>

#include "blocks.hpp"
#include "exact.hpp"
#include "remembers.hpp"

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
    bool lost = false;      // a gap of no known length, with max_missed given: uncertain until a reset
    bool gap_here = false;  // a gap whose tick is the next to run: a reset at that tick still counts it
};

class IntegrateBlock : public Committing<Memory> {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        // Appendix A: it adds x times the ratio of the period to `per`, the ratio worked once, exactly.
        if (!settings.period_over("per", scale_) && !settings.failed()) {
            Length second;  // `per` is 1s unless given
            parse_length("1s", second);
            scale_ = detail::period_over(setup.period, second);
        }
        has_max_missed_ = settings.counted("max_missed", max_missed_);
        if (Status status = settings.finish(); !status) {
            return status;
        }
        period_seconds_ = static_cast<double>(setup.period) / 1e9;
        return {};
    }

    std::span<const InputPort> inputs() const override { return inputs_; }
    std::span<const OutputPort> outputs() const override { return outputs_; }
    Status bind(std::span<const std::optional<Type>> /*input_types*/) override { return {}; }

protected:
    void step(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out, const Memory &now,
              Memory &next) const override {
        const Value &x = in[0];
        const Value &reset = in[1];
        const bool resets = reset.is_usable() && reset.boolean;  // rule 7.7.4; any other reset is not used
        if (resets) {
            next = Memory{};
            next.gaps = now.gap_here ? 1 : 0;  // rule 7.7.3: a gap whose tick is the tick of the reset is counted
        }
        next.gap_here = false;
        next.elapsed += 1;
        if (x.is_usable()) {
            next.total += x.number * scale_;  // rule 7.7.1: the value at a tick includes that tick's addition
            next.doubtful += x.state == State::uncertain ? 1 : 0;
        } else {
            next.missed += 1;
        }

        // Rule 7.7.2: the total always has a value. It is uncertain past `max_missed` and after a gap of no known
        // length, until a reset, and on a tick where its input is uncertain or an uncertain reset cleared it.
        const bool past = next.lost || (has_max_missed_ && next.missed > max_missed_);
        const bool in_doubt = x.state == State::uncertain || (resets && reset.state == State::uncertain);
        out[kTotal] = Value::of(next.total, past || in_doubt ? State::uncertain : State::good);
        out[kMissed] = Value::of(static_cast<double>(next.missed) * period_seconds_);
        out[kDoubtful] = Value::of(static_cast<double>(next.doubtful) * period_seconds_);
        out[kElapsed] = Value::of(static_cast<double>(next.elapsed) * period_seconds_);
        out[kGaps] = Value::of(static_cast<double>(next.gaps));
    }

    void pass_over(const Gap &gap, Memory &now) const override {
        now.gaps += 1;
        now.gap_here = true;
        if (gap.known) {
            now.missed += gap.ticks;
            now.elapsed += gap.ticks;
        } else if (has_max_missed_) {
            now.lost = true;  // what it missed is more than any max_missed
        }
    }

    void describe(Fields &fields, Memory &memory) const override {
        fields(memory.total);
        fields(memory.missed);
        fields(memory.doubtful);
        fields(memory.elapsed);
        fields(memory.gaps);
        fields(memory.lost);
        fields(memory.gap_here);
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
};

}  // namespace

Result<std::unique_ptr<Block>> make_integrate(const BlockSetup &setup) { return make_block<IntegrateBlock>(setup); }

}  // namespace fluxgraph::v2::detail

// `window` (section 7.3 and Appendix A): statistics of the samples of its last n ticks.

#include <algorithm>
#include <array>
#include <format>
#include <optional>

#include "blocks.hpp"
#include "exact.hpp"

namespace fluxgraph::v2::detail {

namespace {

// What one tick of the window holds: a sample, `good` or `uncertain`, or none, and then the state it counts as
// in rule 7.3.3.
struct Slot {
    State state = State::not_ready;
    double value = 0.0;
};

enum Port : std::size_t { kMean, kMedian, kMin, kMax, kSpread, kSlope, kCount, kPorts };

class WindowBlock : public Block {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        std::uint64_t ticks = 0;
        double min_good = 1.0;
        if (!settings.counted("window", ticks) && !settings.failed()) {
            settings.fail("has no 'window' setting");
        }
        if (!settings.failed() && ticks < 1) {
            settings.fail("setting 'window' has to be at least one period");
        }
        const bool tolerance_given = settings.number("min_good", min_good);
        if (!settings.failed() && !(min_good > 0.0 && min_good <= 1.0)) {
            settings.fail(std::format("setting 'min_good' is {}, and has to be more than 0 and at most 1", min_good));
        }
        settings.boolean("only_new", only_new_);
        if (!settings.failed() && only_new_ && !tolerance_given) {
            settings.fail("'min_good' has to be given with 'only_new: true'");  // rule 7.3.8
        }
        if (Status status = settings.finish(); !status) {
            return status;
        }
        if (ticks > kMaxRememberedTicks) {
            return graph_error(
                std::format("block '{}': setting 'window' is {} periods, and this engine remembers no more than {}",
                            setup.id, ticks, kMaxRememberedTicks));
        }
        // Rule 7.3.2, worked exactly (rule 6.3), and at least 1.
        needed_ = std::max<std::uint64_t>(1, ceil_of_fraction(min_good, ticks));
        period_seconds_ = static_cast<double>(setup.period) / 1e9;
        slots_.assign(static_cast<std::size_t>(ticks), Slot{});
        sorted_.assign(static_cast<std::size_t>(ticks), 0.0);
        reset();
        return {};
    }

    std::span<const InputPort> inputs() const override { return inputs_; }
    std::span<const OutputPort> outputs() const override { return outputs_; }
    Status bind(std::span<const std::optional<Type>> /*input_types*/) override { return {}; }

    void give(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out) override {
        const Value &x = in[0];
        pending_ = Slot{x.state, x.number};
        pending_new_ = false;
        if (only_new_ && x.is_usable()) {  // rule 7.3.8
            if (x.timed && (!has_taken_ || x.time > taken_)) {
                pending_new_ = true;
                pending_time_ = x.time;
            } else {
                pending_ = Slot{};  // not another sample: the tick holds none, and counts as not_ready
            }
        }
        statistics(out);
    }

    void update(const Tick & /*tick*/, std::span<const Value> /*in*/) override {
        slots_[oldest_] = pending_;
        oldest_ = (oldest_ + 1) % slots_.size();
        if (pending_new_) {
            has_taken_ = true;
            taken_ = pending_time_;
        }
    }

    void gap(const Gap &gap) override {
        // Rule 8.6: the ticks passed over hold no sample, and count as not_ready. Nobody knowing how many, or a
        // rebase of a window that takes only new samples (rule 8.5), is all of them.
        std::size_t holes = slots_.size();
        if (gap.known && !(gap.rebase && only_new_)) {
            holes = static_cast<std::size_t>(std::min<std::uint64_t>(gap.ticks, slots_.size()));
        }
        for (std::size_t i = 0; i < holes; ++i) {
            slots_[oldest_] = Slot{};
            oldest_ = (oldest_ + 1) % slots_.size();
        }
        if (gap.rebase) {
            has_taken_ = false;  // rule 8.5: every sample time it remembers is forgotten
        }
    }

    void reset() override {
        std::fill(slots_.begin(), slots_.end(), Slot{});  // a tick from before the graph started holds none
        oldest_ = 0;
        has_taken_ = false;
        taken_ = 0;
    }

    void save(StateWriter &writer) const override {
        writer.u64(oldest_);
        writer.flag(has_taken_);
        writer.u64(static_cast<std::uint64_t>(taken_));
        for (const Slot &slot : slots_) {
            writer.u64(static_cast<std::uint64_t>(slot.state));
            writer.f64(slot.value);
        }
    }

    bool restore(StateReader &reader) override {
        std::uint64_t oldest = 0;
        std::uint64_t taken = 0;
        if (!reader.u64(oldest) || oldest >= slots_.size() || !reader.flag(has_taken_) || !reader.u64(taken)) {
            return false;
        }
        oldest_ = static_cast<std::size_t>(oldest);
        taken_ = static_cast<Time>(taken);
        for (Slot &slot : slots_) {
            std::uint64_t state = 0;
            if (!reader.u64(state) || state > 3 || !reader.f64(slot.value)) {
                return false;
            }
            slot.state = static_cast<State>(state);
        }
        return true;
    }

private:
    // The slot of the window's i-th tick, oldest first, at the tick being given: the last is this tick's.
    const Slot &at(std::size_t i) const {
        return i + 1 == slots_.size() ? pending_ : slots_[(oldest_ + 1 + i) % slots_.size()];
    }

    void statistics(std::span<Value> out) {
        const std::size_t n = slots_.size();
        std::uint64_t usable_count = 0;
        std::uint64_t good_count = 0;
        State worst_hole = State::good;
        for (std::size_t i = 0; i < n; ++i) {
            const Slot &slot = at(i);
            if (!usable(slot.state)) {
                worst_hole = worst(worst_hole, slot.state);
            } else {
                ++usable_count;
                good_count += slot.state == State::good ? 1 : 0;
            }
        }
        out[kCount] = Value::of(static_cast<double>(usable_count));  // rule 7.3.7: always good
        if (usable_count < needed_) {  // rule 7.3.3: the worst state among its ticks that hold none
            for (std::size_t port = kMean; port <= kSlope; ++port) {
                out[port] = Value::none(worst_hole);
            }
            return;
        }
        // Rules 7.3.4 and 7.3.5: of its good samples alone where there are enough of them, and good.
        const bool enough_good = good_count >= needed_;
        const State state = enough_good ? State::good : State::uncertain;
        std::size_t count = 0;
        double sum = 0.0;
        for (std::size_t i = 0; i < n; ++i) {
            const Slot &slot = at(i);
            if (slot.state == State::good || (!enough_good && slot.state == State::uncertain)) {
                sorted_[count++] = slot.value;
                sum += slot.value;  // a plain sum (rule 3.6)
            }
        }
        std::sort(sorted_.begin(), sorted_.begin() + static_cast<std::ptrdiff_t>(count));
        const double low = sorted_[0];
        const double high = sorted_[count - 1];
        const double median = count % 2 == 1 ? sorted_[count / 2] : (sorted_[count / 2 - 1] + sorted_[count / 2]) / 2.0;
        out[kMean] = Value::of(sum / static_cast<double>(count), state);
        out[kMedian] = Value::of(median, state);
        out[kMin] = Value::of(low, state);
        out[kMax] = Value::of(high, state);
        out[kSpread] = Value::of(high - low, state);
        // Rule 7.3.6: a slope needs two samples.
        if (enough_good && good_count >= 2) {
            out[kSlope] = Value::of(slope(false), State::good);
        } else if (usable_count >= 2) {
            out[kSlope] = Value::of(slope(true), State::uncertain);
        } else {
            out[kSlope] = Value::none(State::bad);
        }
    }

    // The least-squares slope of value against time, per second, of the good samples, or of the usable ones.
    double slope(bool of_usable) const {
        const std::size_t n = slots_.size();
        double count = 0.0;
        double sum_t = 0.0;
        double sum_v = 0.0;
        for (std::size_t i = 0; i < n; ++i) {
            const Slot &slot = at(i);
            if (slot.state == State::good || (of_usable && slot.state == State::uncertain)) {
                count += 1.0;
                sum_t += static_cast<double>(i) * period_seconds_;
                sum_v += slot.value;
            }
        }
        const double mean_t = sum_t / count;
        const double mean_v = sum_v / count;
        double above = 0.0;
        double below = 0.0;
        for (std::size_t i = 0; i < n; ++i) {
            const Slot &slot = at(i);
            if (slot.state == State::good || (of_usable && slot.state == State::uncertain)) {
                const double t = static_cast<double>(i) * period_seconds_ - mean_t;
                above += t * (slot.value - mean_v);
                below += t * t;
            }
        }
        return above / below;
    }

    std::array<InputPort, 1> inputs_ = {{{"x", Type::number, true, false}}};
    std::array<OutputPort, kPorts> outputs_ = {{
        {"mean", Type::number, false},
        {"median", Type::number, false},
        {"min", Type::number, false},
        {"max", Type::number, false},
        {"spread", Type::number, false},
        {"slope", Type::number, false},
        {"count", Type::number, false},
    }};
    bool only_new_ = false;
    std::uint64_t needed_ = 1;
    double period_seconds_ = 1.0;

    std::vector<Slot> slots_;  // the last n ticks; the oldest is at oldest_
    std::size_t oldest_ = 0;
    bool has_taken_ = false;  // with only_new: the sample time of the last sample it took
    Time taken_ = 0;

    Slot pending_;  // this tick's, from give() until update() takes it in
    bool pending_new_ = false;
    Time pending_time_ = 0;
    std::vector<double> sorted_;  // room to sort in, so that a tick allocates nothing
};

}  // namespace

Result<std::unique_ptr<Block>> make_window(const BlockSetup &setup) { return make_block<WindowBlock>(setup); }

}  // namespace fluxgraph::v2::detail

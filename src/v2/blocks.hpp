#pragma once

// What the block types of this build share: the table of them, and the reading of a block's settings.

#include <cstdint>
#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include "fluxgraph/v2/block.hpp"

namespace fluxgraph::v2::detail {

/// The most ticks one block may be asked to remember: a delay's `ticks`, a window's length. Rule 9's ranges are
/// widths and not sizes (Appendix A), and this is the size this engine stops at.
inline constexpr std::uint64_t kMaxRememberedTicks = std::uint64_t{1} << 24;

Error graph_error(std::string message);

/// Reads a block's settings. Each getter is false where the setting was not given, or was given wrongly; the
/// first fault is kept, and finish() gives it, or names a setting nobody asked for (rule 9.5).
class SettingsReader {
public:
    explicit SettingsReader(const BlockSetup &setup);

    bool given(std::string_view key) const;
    /// A whole number, written without a point (rule 9.4), from `least` to `most`.
    bool whole(std::string_view key, std::int64_t least, std::int64_t most, std::int64_t &value);
    /// A finite number, written with a point or without.
    bool number(std::string_view key, double &value);
    bool boolean(std::string_view key, bool &value);
    bool text(std::string_view key, std::string &value);
    /// A finite number or a boolean, as a good value.
    bool constant(std::string_view key, Value &value);
    /// A length of time the block counts: a whole number of periods (rule 6.3).
    bool counted(std::string_view key, std::uint64_t &ticks);
    /// A length of time that only scales a value: any length more than zero, as the ratio of the period to it.
    bool period_over(std::string_view key, double &ratio);
    /// The same, and with it `times` of the length in periods, rounded up to whole ticks.
    bool period_over(std::string_view key, double &ratio, std::uint32_t times, std::uint64_t &ticks);
    /// A number that is not negative.
    bool not_negative(std::string_view key, double &value);
    /// A number that is more than zero.
    bool positive(std::string_view key, double &value);
    /// A length of time that only scales a value: any length more than zero, in seconds.
    bool seconds(std::string_view key, double &value);
    /// The setting as it was given, for a block that reads it itself: a list or a map. Null where not given.
    const Setting *raw(std::string_view key) { return take(key); }
    Time period() const { return setup_.period; }
    std::string_view id() const { return setup_.id; }

    /// Records a fault of the block, unless one is held already. `what` follows "block '<id>': ".
    void fail(std::string what);
    bool failed() const { return !problem_.empty(); }
    Status finish();

private:
    const Setting *take(std::string_view key);

    const BlockSetup &setup_;
    std::vector<bool> taken_;
    std::string problem_;
};

/// The counters of section 7, as counts of ticks. Every tick counted has a number of its own that fits in 64
/// bits, signed, so none of these passes 2^63 and no addition to one can wrap.
struct Counters {
    std::uint64_t elapsed = 0;
    std::uint64_t doubtful = 0;
    std::uint64_t gaps = 0;

    void save(StateWriter &writer) const {
        writer.u64(elapsed);
        writer.u64(doubtful);
        writer.u64(gaps);
    }
    bool restore(StateReader &reader) { return reader.u64(elapsed) && reader.u64(doubtful) && reader.u64(gaps); }
    /// Gives `elapsed` and `doubtful` in seconds and `gaps` as a count, all good, to three ports in that order.
    void give(std::span<Value> out, std::size_t first, double period_seconds) const {
        out[first] = Value::of(static_cast<double>(elapsed) * period_seconds);
        out[first + 1] = Value::of(static_cast<double>(doubtful) * period_seconds);
        out[first + 2] = Value::of(static_cast<double>(gaps));
    }
};

using BlockMaker = Result<std::unique_ptr<Block>> (*)(const BlockSetup &setup);

/// The maker of a block type this build has, or null.
BlockMaker find_block_maker(std::string_view type);
bool is_planned_block_type(std::string_view type);

/// Makes a block of class B and configures it: B has `Status configure(const BlockSetup &)`.
template <typename B>
Result<std::unique_ptr<Block>> make_block(const BlockSetup &setup) {
    auto block = std::make_unique<B>();
    if (Status status = block->configure(setup); !status) {
        return status.error();
    }
    return std::unique_ptr<Block>(std::move(block));
}

Result<std::unique_ptr<Block>> make_formula(const BlockSetup &setup);
Result<std::unique_ptr<Block>> make_all_good(const BlockSetup &setup);
Result<std::unique_ptr<Block>> make_delay(const BlockSetup &setup);
Result<std::unique_ptr<Block>> make_window(const BlockSetup &setup);
Result<std::unique_ptr<Block>> make_integrate(const BlockSetup &setup);
Result<std::unique_ptr<Block>> make_deadband(const BlockSetup &setup);
Result<std::unique_ptr<Block>> make_lowpass(const BlockSetup &setup);
Result<std::unique_ptr<Block>> make_rate_limit(const BlockSetup &setup);
Result<std::unique_ptr<Block>> make_hysteresis(const BlockSetup &setup);
Result<std::unique_ptr<Block>> make_held_for(const BlockSetup &setup);
Result<std::unique_ptr<Block>> make_since_true(const BlockSetup &setup);
Result<std::unique_ptr<Block>> make_latch(const BlockSetup &setup);
Result<std::unique_ptr<Block>> make_pid(const BlockSetup &setup);
/// Any of the model blocks: `setup.type` says which model it hosts.
Result<std::unique_ptr<Block>> make_model(const BlockSetup &setup);

}  // namespace fluxgraph::v2::detail

#pragma once

// What the block types of this build share: the table of them, and the reading of a block's settings.

#include <cstdint>
#include <memory>
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
    /// A length of time that only scales a value: any length, as nanoseconds.
    bool scale(std::string_view key, double &nanoseconds);

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

}  // namespace fluxgraph::v2::detail

#include "blocks.hpp"

#include <array>
#include <cmath>
#include <format>

#include "exact.hpp"

namespace fluxgraph::v2 {

namespace {

struct BuiltType {
    std::string_view name;
    detail::BlockMaker make;
};

// Adding a block type is a row here and a maker: nothing in the compiler or the engine names a type.
constexpr std::array<BuiltType, 22> kBuilt = {{
    {"formula", &detail::make_formula},
    {"all_good", &detail::make_all_good},
    {"delay", &detail::make_delay},
    {"window", &detail::make_window},
    {"integrate", &detail::make_integrate},
    {"deadband", &detail::make_deadband},
    {"lowpass", &detail::make_lowpass},
    {"rate_limit", &detail::make_rate_limit},
    {"hysteresis", &detail::make_hysteresis},
    {"held_for", &detail::make_held_for},
    {"since_true", &detail::make_since_true},
    {"latch", &detail::make_latch},
    {"pid", &detail::make_pid},
    {"linear", &detail::make_model},
    {"thermal_mass", &detail::make_model},
    {"thermal_rc2", &detail::make_model},
    {"first_order_process", &detail::make_model},
    {"second_order_process", &detail::make_model},
    {"mass_spring_damper", &detail::make_model},
    {"dc_motor", &detail::make_model},
    {"state_space", &detail::make_model},
    {"estimator", &detail::make_estimator},
}};

constexpr std::array<std::string_view, 22> kBuiltNames = {
    "formula",
    "all_good",
    "delay",
    "window",
    "integrate",
    "deadband",
    "lowpass",
    "rate_limit",
    "hysteresis",
    "held_for",
    "since_true",
    "latch",
    "pid",
    "linear",
    "thermal_mass",
    "thermal_rc2",
    "first_order_process",
    "second_order_process",
    "mass_spring_damper",
    "dc_motor",
    "state_space",
    "estimator",
};

// The rest of Appendix A's catalogue: nothing, now.
constexpr std::array<std::string_view, 0> kPlannedNames = {};

}  // namespace

std::span<const std::string_view> built_block_types() { return kBuiltNames; }
std::span<const std::string_view> planned_block_types() { return kPlannedNames; }

namespace detail {

Error graph_error(std::string message) { return Error{Errc::graph_refused, std::move(message)}; }

BlockMaker find_block_maker(std::string_view type) {
    for (const BuiltType &built : kBuilt) {
        if (built.name == type) {
            return built.make;
        }
    }
    return nullptr;
}

bool is_planned_block_type(std::string_view type) {
    for (std::string_view planned : kPlannedNames) {
        if (planned == type) {
            return true;
        }
    }
    return false;
}

SettingsReader::SettingsReader(const BlockSetup &setup)
    : setup_(setup), taken_(setup.settings->as_map().keys.size(), false) {}

const Setting *SettingsReader::take(std::string_view key) {
    const Setting::Map &map = setup_.settings->as_map();
    for (std::size_t i = 0; i < map.keys.size(); ++i) {
        if (map.keys[i] == key) {
            taken_[i] = true;
            return &map.values[i];
        }
    }
    return nullptr;
}

bool SettingsReader::given(std::string_view key) const { return setup_.settings->find(key) != nullptr; }

void SettingsReader::fail(std::string what) {
    if (problem_.empty()) {
        problem_ = std::format("block '{}': {}", setup_.id, what);
    }
}

bool SettingsReader::whole(std::string_view key, std::int64_t least, std::int64_t most, std::int64_t &value) {
    const Setting *setting = take(key);
    if (setting == nullptr) {
        return false;
    }
    if (!setting->is(Setting::Kind::whole)) {
        fail(std::format("setting '{}' is {}, {}, and has to be a whole number written without a point", key,
                         setting->shown(), setting->kind_name()));
        return false;
    }
    if (setting->as_whole() < least || setting->as_whole() > most) {
        fail(std::format("setting '{}' is {}, and has to be from {} to {}", key, setting->as_whole(), least, most));
        return false;
    }
    value = setting->as_whole();
    return true;
}

bool SettingsReader::number(std::string_view key, double &value) {
    const Setting *setting = take(key);
    if (setting == nullptr) {
        return false;
    }
    if (setting->is(Setting::Kind::whole)) {
        value = static_cast<double>(setting->as_whole());
        return true;
    }
    if (!setting->is(Setting::Kind::number) || !std::isfinite(setting->as_number())) {
        fail(std::format("setting '{}' is {}, {}, and has to be a finite number", key, setting->shown(),
                         setting->kind_name()));
        return false;
    }
    value = setting->as_number();
    return true;
}

bool SettingsReader::boolean(std::string_view key, bool &value) {
    const Setting *setting = take(key);
    if (setting == nullptr) {
        return false;
    }
    if (!setting->is(Setting::Kind::boolean)) {
        fail(std::format("setting '{}' is {}, {}, and has to be true or false", key, setting->shown(),
                         setting->kind_name()));
        return false;
    }
    value = setting->as_boolean();
    return true;
}

bool SettingsReader::text(std::string_view key, std::string &value) {
    const Setting *setting = take(key);
    if (setting == nullptr) {
        return false;
    }
    if (!setting->is(Setting::Kind::text)) {
        fail(std::format("setting '{}' is {}, {}, and has to be text", key, setting->shown(), setting->kind_name()));
        return false;
    }
    value = setting->as_text();
    return true;
}

bool SettingsReader::constant(std::string_view key, Value &value) {
    const Setting *setting = take(key);
    if (setting == nullptr) {
        return false;
    }
    if (setting->is(Setting::Kind::boolean)) {
        value = Value::of(setting->as_boolean());
        return true;
    }
    if (setting->is(Setting::Kind::whole)) {
        value = Value::of(static_cast<double>(setting->as_whole()));
        return true;
    }
    if (!setting->is(Setting::Kind::number) || !std::isfinite(setting->as_number())) {
        fail(std::format("setting '{}' is {}, {}, and has to be a finite number or a boolean", key, setting->shown(),
                         setting->kind_name()));
        return false;
    }
    value = Value::of(setting->as_number());
    return true;
}

namespace {

bool read_length(const Setting &setting, Length &length) {
    return setting.is(Setting::Kind::text) && parse_length(setting.as_text(), length);
}

}  // namespace

bool SettingsReader::counted(std::string_view key, std::uint64_t &ticks) {
    const Setting *setting = take(key);
    if (setting == nullptr) {
        return false;
    }
    Length length;
    if (!read_length(*setting, length)) {
        fail(std::format("setting '{}' is {}, and has to be a length of time: a number and a unit, as in '2s'", key,
                         setting->shown()));
        return false;
    }
    Time nanoseconds = 0;
    const WholeLength whole = whole_nanoseconds(length, nanoseconds);
    if (whole == WholeLength::too_large) {
        fail(std::format("setting '{}' is {}, which does not fit in 64 bits of nanoseconds", key, setting->shown()));
        return false;
    }
    // Both are whole and not negative, and the period is more than zero.
    if (whole == WholeLength::not_whole || nanoseconds % setup_.period != 0) {
        fail(std::format("setting '{}' is {}, which is not a whole number of periods", key, setting->shown()));
        return false;
    }
    ticks = static_cast<std::uint64_t>(nanoseconds / setup_.period);
    return true;
}

bool SettingsReader::period_over(std::string_view key, double &ratio) {
    std::uint64_t unused = 0;
    return period_over(key, ratio, 0, unused);
}

bool SettingsReader::period_over(std::string_view key, double &ratio, std::uint32_t times, std::uint64_t &ticks) {
    const Setting *setting = take(key);
    if (setting == nullptr) {
        return false;
    }
    Length length;
    if (!read_length(*setting, length)) {
        fail(std::format("setting '{}' is {}, and has to be a length of time: a number and a unit, as in '2s'", key,
                         setting->shown()));
        return false;
    }
    if (is_zero(length)) {
        fail(std::format("setting '{}' is {}, and has to be more than zero", key, setting->shown()));
        return false;
    }
    ratio = detail::period_over(setup_.period, length);
    if (!std::isfinite(ratio) || !periods_rounded_up(length, times, setup_.period, ticks)) {
        fail(std::format("setting '{}' is {}, which is past what this engine can count", key, setting->shown()));
        return false;
    }
    return true;
}

bool SettingsReader::positive(std::string_view key, double &value) {
    double given = 0.0;
    if (!number(key, given)) {
        return false;
    }
    if (!(given > 0.0)) {
        fail(std::format("setting '{}' is {}, and has to be more than zero", key, given));
        return false;
    }
    value = given;
    return true;
}

bool SettingsReader::seconds(std::string_view key, double &value) {
    const Setting *setting = take(key);
    if (setting == nullptr) {
        return false;
    }
    Length length;
    if (!read_length(*setting, length)) {
        fail(std::format("setting '{}' is {}, and has to be a length of time: a number and a unit, as in '2s'", key,
                         setting->shown()));
        return false;
    }
    if (is_zero(length)) {
        fail(std::format("setting '{}' is {}, and has to be more than zero", key, setting->shown()));
        return false;
    }
    value = seconds_of(length);
    return true;
}

bool SettingsReader::not_negative(std::string_view key, double &value) {
    double given = 0.0;
    if (!number(key, given)) {
        return false;
    }
    if (given < 0.0) {
        fail(std::format("setting '{}' is {}, and is not to be negative", key, given));
        return false;
    }
    value = given;
    return true;
}

Status SettingsReader::finish() {
    if (problem_.empty()) {
        const Setting::Map &map = setup_.settings->as_map();
        for (std::size_t i = 0; i < map.keys.size(); ++i) {
            if (!taken_[i]) {
                fail(std::format("'{}' is not a setting of this block type", map.keys[i]));
                break;
            }
        }
    }
    if (problem_.empty()) {
        return {};
    }
    return graph_error(problem_);
}

}  // namespace detail

}  // namespace fluxgraph::v2

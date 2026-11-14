#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

namespace fluxgraph::v2 {

/// One value of a graph description: a whole number, a number, a boolean, text, a list or a map.
///
/// A graph is handed to the compiler as a Setting that is a map, in the shape of section 9 of the
/// specification. Whoever reads a graph file builds one of these and decides nothing else: what a key or a value
/// may be is judged by the compiler (rule 9.7). A whole number and a number are kept apart because rule 9.4
/// tells `2` from `2.0`. A map keeps its keys in the order they were added.
class Setting {
public:
    enum class Kind { whole, number, boolean, text, list, map };

    struct Map {
        std::vector<std::string> keys;
        std::vector<Setting> values;
    };
    using List = std::vector<Setting>;

    /// A map with no keys.
    Setting() : held_(Map{}) {}

    static Setting whole(std::int64_t value) { return Setting(Held(value)); }
    static Setting number(double value) { return Setting(Held(value)); }
    static Setting boolean(bool value) { return Setting(Held(value)); }
    static Setting text(std::string value) { return Setting(Held(std::move(value))); }
    static Setting list(List items = {}) { return Setting(Held(std::move(items))); }
    static Setting map() { return Setting(); }

    Kind kind() const { return static_cast<Kind>(held_.index()); }
    bool is(Kind kind) const { return this->kind() == kind; }

    /// Each of these is for a Setting of that kind and of no other.
    std::int64_t as_whole() const { return *std::get_if<std::int64_t>(&held_); }
    double as_number() const { return *std::get_if<double>(&held_); }
    bool as_boolean() const { return *std::get_if<bool>(&held_); }
    const std::string &as_text() const { return *std::get_if<std::string>(&held_); }
    const List &as_list() const { return *std::get_if<List>(&held_); }
    const Map &as_map() const { return *std::get_if<Map>(&held_); }

    /// For a map: the value under `key`, the first if there are several, or null.
    const Setting *find(std::string_view key) const;

    /// For a map: adds a key after those it has. Returns this, so that calls chain.
    Setting &set(std::string key, Setting value);
    /// For a list: adds an item at the end. Returns this.
    Setting &add(Setting item);

    /// What kind of thing this is, for a message: "a whole number", "text", and so on.
    std::string_view kind_name() const;
    /// The value as a message shows it.
    std::string shown() const;

private:
    using Held = std::variant<std::int64_t, double, bool, std::string, List, Map>;
    explicit Setting(Held held) : held_(std::move(held)) {}

    Held held_;
};

}  // namespace fluxgraph::v2

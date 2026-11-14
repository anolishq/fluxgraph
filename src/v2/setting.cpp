#include "fluxgraph/v2/setting.hpp"

#include <format>

#include "fluxgraph/v2/value.hpp"

namespace fluxgraph::v2 {

std::string_view name_of(State state) {
    switch (state) {
        case State::bad:
            return "bad";
        case State::not_ready:
            return "not_ready";
        case State::uncertain:
            return "uncertain";
        case State::good:
            return "good";
    }
    return "?";
}

std::string_view name_of(Type type) { return type == Type::number ? "number" : "boolean"; }

const Setting *Setting::find(std::string_view key) const {
    const Map *map = std::get_if<Map>(&held_);
    if (map == nullptr) {
        return nullptr;
    }
    for (std::size_t i = 0; i < map->keys.size(); ++i) {
        if (map->keys[i] == key) {
            return &map->values[i];
        }
    }
    return nullptr;
}

Setting &Setting::set(std::string key, Setting value) {
    if (Map *map = std::get_if<Map>(&held_)) {
        map->keys.push_back(std::move(key));
        map->values.push_back(std::move(value));
    }
    return *this;
}

Setting &Setting::add(Setting item) {
    if (List *list = std::get_if<List>(&held_)) {
        list->push_back(std::move(item));
    }
    return *this;
}

std::string_view Setting::kind_name() const {
    switch (kind()) {
        case Kind::whole:
            return "a whole number";
        case Kind::number:
            return "a number";
        case Kind::boolean:
            return "a boolean";
        case Kind::text:
            return "text";
        case Kind::list:
            return "a list";
        case Kind::map:
            return "a map";
    }
    return "?";
}

std::string Setting::shown() const {
    switch (kind()) {
        case Kind::whole:
            return std::format("{}", as_whole());
        case Kind::number:
            return std::format("{}", as_number());
        case Kind::boolean:
            return as_boolean() ? "true" : "false";
        case Kind::text:
            return std::format("'{}'", as_text());
        case Kind::list:
            return "a list";
        case Kind::map:
            return "a map";
    }
    return "?";
}

}  // namespace fluxgraph::v2

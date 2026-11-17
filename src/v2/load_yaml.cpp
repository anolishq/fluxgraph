// Reads a graph from YAML (rule 9.7): see fluxgraph/v2/load.hpp for what is decided here.
//
// yaml-cpp gives every scalar as text and leaves what it is to whoever asks. What a scalar that is not quoted is
// taken for follows the core schema of YAML 1.2 (section 10.3.2 of that specification), and nothing else does.

#include <yaml-cpp/yaml.h>

#include <charconv>
#include <cstddef>
#include <cstdint>
#include <format>
#include <limits>
#include <optional>
#include <string>
#include <string_view>
#include <system_error>
#include <utility>

#include "fluxgraph/v2/load.hpp"

namespace fluxgraph::v2 {

namespace {

constexpr std::string_view kPlain = "?";   // the tag yaml-cpp gives a scalar that is not quoted
constexpr std::string_view kQuoted = "!";  // and one that is quoted, or a block
constexpr std::string_view kText = "tag:yaml.org,2002:str";

bool is_digit(char c) { return c >= '0' && c <= '9'; }

bool all_of(std::string_view text, bool (*is)(char)) {
    for (char c : text) {
        if (!is(c)) {
            return false;
        }
    }
    return !text.empty();
}

// [-+]? [0-9]+
bool is_decimal(std::string_view text) {
    if (!text.empty() && (text[0] == '-' || text[0] == '+')) {
        text.remove_prefix(1);
    }
    return all_of(text, is_digit);
}

// [-+]? ( \. [0-9]+ | [0-9]+ ( \. [0-9]* )? ) ( [eE] [-+]? [0-9]+ )?
bool is_float(std::string_view text) {
    if (!text.empty() && (text[0] == '-' || text[0] == '+')) {
        text.remove_prefix(1);
    }
    std::size_t i = 0;
    const auto digits = [&] {
        const std::size_t from = i;
        while (i < text.size() && is_digit(text[i])) {
            ++i;
        }
        return i - from;
    };
    if (i < text.size() && text[i] == '.') {
        ++i;
        if (digits() == 0) {
            return false;
        }
    } else {
        if (digits() == 0) {
            return false;
        }
        if (i < text.size() && text[i] == '.') {
            ++i;
            digits();
        }
    }
    if (i < text.size() && (text[i] == 'e' || text[i] == 'E')) {
        ++i;
        if (i < text.size() && (text[i] == '-' || text[i] == '+')) {
            ++i;
        }
        if (digits() == 0) {
            return false;
        }
    }
    return i == text.size();
}

double as_double(std::string_view text) {
    if (!text.empty() && text[0] == '+') {
        text.remove_prefix(1);  // from_chars takes no plus sign
    }
    double value = 0.0;
    std::from_chars(text.data(), text.data() + text.size(), value);  // out of range gives an infinity or a zero
    return value;
}

// A whole number in `base`, or the nearest number where 64 bits, signed, do not hold it.
Setting whole_in(std::string_view digits, int base, bool negative) {
    std::uint64_t value = 0;
    const std::from_chars_result read = std::from_chars(digits.data(), digits.data() + digits.size(), value, base);
    const std::uint64_t most = static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max());
    if (read.ec == std::errc() && value <= most) {
        return Setting::whole(negative ? -static_cast<std::int64_t>(value) : static_cast<std::int64_t>(value));
    }
    if (read.ec == std::errc() && negative && value == most + 1) {
        return Setting::whole(std::numeric_limits<std::int64_t>::min());
    }
    if (base != 10) {
        return Setting::number(read.ec == std::errc() ? static_cast<double>(value)
                                                      : std::numeric_limits<double>::infinity());
    }
    const double nearest = as_double(digits);
    return Setting::number(negative ? -nearest : nearest);
}

// What a scalar that is not quoted is, by the core schema of YAML 1.2. Nothing where it is a null.
std::optional<Setting> resolved(std::string_view text) {
    if (text.empty() || text == "~" || text == "null" || text == "Null" || text == "NULL") {
        return std::nullopt;
    }
    if (text == "true" || text == "True" || text == "TRUE") {
        return Setting::boolean(true);
    }
    if (text == "false" || text == "False" || text == "FALSE") {
        return Setting::boolean(false);
    }
    if (is_decimal(text)) {
        const bool negative = text[0] == '-';
        return whole_in(text.substr(text[0] == '-' || text[0] == '+' ? 1 : 0), 10, negative);
    }
    if (text.starts_with("0o") && all_of(text.substr(2), [](char c) { return c >= '0' && c <= '7'; })) {
        return whole_in(text.substr(2), 8, false);
    }
    if (text.starts_with("0x") && all_of(text.substr(2), [](char c) {
            return is_digit(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
        })) {
        return whole_in(text.substr(2), 16, false);
    }
    if (is_float(text)) {
        return Setting::number(as_double(text));
    }
    std::string_view unsigned_text = text;
    const bool negative = text[0] == '-';
    if (text[0] == '-' || text[0] == '+') {
        unsigned_text.remove_prefix(1);
    }
    if (unsigned_text == ".inf" || unsigned_text == ".Inf" || unsigned_text == ".INF") {
        const double infinity = std::numeric_limits<double>::infinity();
        return Setting::number(negative ? -infinity : infinity);
    }
    if (text == ".nan" || text == ".NaN" || text == ".NAN") {
        return Setting::number(std::numeric_limits<double>::quiet_NaN());
    }
    return Setting::text(std::string(text));
}

Error refused(const YAML::Node &node, std::string_view path, std::string_view what) {
    const std::string where = path.empty() ? "the whole of it" : std::format("'{}'", path);
    return Error{Errc::file_refused, std::format("{} {}, at line {}", where, what, node.Mark().line + 1)};
}

Result<Setting> read(const YAML::Node &node, const std::string &path);

Result<Setting> read_scalar(const YAML::Node &node, const std::string &path) {
    const std::string &tag = node.Tag();
    if (tag == kQuoted || tag == kText) {
        return Setting::text(node.Scalar());
    }
    if (tag != kPlain) {
        return refused(node, path, std::format("has the tag '{}', and no tag but !!str is read", tag));
    }
    std::optional<Setting> value = resolved(node.Scalar());
    if (!value.has_value()) {
        return refused(node, path, "is null");
    }
    return std::move(*value);
}

Result<Setting> read_map(const YAML::Node &node, const std::string &path) {
    Setting map = Setting::map();
    for (const auto &entry : node) {
        const YAML::Node &key = entry.first;
        if (!key.IsScalar()) {
            return refused(key, path, "has a key that is not text");
        }
        Result<Setting> name = read_scalar(key, path);
        if (!name) {
            return name;  // a key that is null, or has a tag that is not read
        }
        if (!name->is(Setting::Kind::text)) {
            return refused(key, path,
                           std::format("has the key {}, which is {} and not text: put it in quotes", key.Scalar(),
                                       name->kind_name()));
        }
        const std::string &text = name->as_text();
        const std::string below = path.empty() ? text : std::format("{}.{}", path, text);
        if (map.find(text) != nullptr) {
            return refused(key, below, "is given twice");
        }
        Result<Setting> value = read(entry.second, below);
        if (!value) {
            return value;
        }
        map.set(text, std::move(value.value()));
    }
    return map;
}

Result<Setting> read(const YAML::Node &node, const std::string &path) {
    switch (node.Type()) {
        case YAML::NodeType::Scalar:
            return read_scalar(node, path);
        case YAML::NodeType::Sequence: {
            Setting list = Setting::list();
            std::size_t index = 0;
            for (const YAML::Node &item : node) {
                Result<Setting> value = read(item, std::format("{}[{}]", path, index++));
                if (!value) {
                    return value;
                }
                list.add(std::move(value.value()));
            }
            return list;
        }
        case YAML::NodeType::Map:
            return read_map(node, path);
        case YAML::NodeType::Null:
        case YAML::NodeType::Undefined:
            break;
    }
    return refused(node, path, "is null");
}

}  // namespace

Result<Setting> load_yaml(std::string_view text) {
    try {
        return read(YAML::Load(std::string(text)), "");
    } catch (const YAML::Exception &error) {
        return Error{Errc::file_refused, std::format("the text is not YAML: {}", error.what())};
    }
}

}  // namespace fluxgraph::v2

// Reads a graph from JSON (rule 9.7): see fluxgraph/v2/load.hpp for what is decided here, which is little.

#include <cstddef>
#include <cstdint>
#include <format>
#include <limits>
#include <nlohmann/json.hpp>
#include <string>
#include <utility>
#include <vector>

#include "fluxgraph/v2/load.hpp"

namespace fluxgraph::v2 {

namespace {

// Builds a Setting as the parser reports each thing it reads. The parser's own tree is not used: it keeps the
// last of two values under one key and says nothing.
class Builder : public nlohmann::json_sax<nlohmann::json> {
public:
    bool null() override { return fail("is null"); }
    bool boolean(bool value) override { return put(Setting::boolean(value)); }
    bool number_integer(number_integer_t value) override { return put(Setting::whole(value)); }
    bool number_unsigned(number_unsigned_t value) override {
        // One that 64 bits, signed, do not hold is given as the nearest number.
        if (value > static_cast<number_unsigned_t>(std::numeric_limits<std::int64_t>::max())) {
            return put(Setting::number(static_cast<double>(value)));
        }
        return put(Setting::whole(static_cast<std::int64_t>(value)));
    }
    bool number_float(number_float_t value, const string_t & /*written*/) override {
        return put(Setting::number(value));
    }
    bool string(string_t &value) override { return put(Setting::text(std::move(value))); }
    bool binary(binary_t & /*value*/) override { return fail("is binary"); }

    bool start_object(std::size_t /*elements*/) override {
        open_.push_back(Open{Setting::map(), {}, 0});
        return true;
    }
    bool key(string_t &value) override {
        Open &top = open_.back();
        if (top.value.find(value) != nullptr) {
            top.key = std::move(value);
            return fail("is given twice");
        }
        top.key = std::move(value);
        return true;
    }
    bool end_object() override { return close(); }

    bool start_array(std::size_t /*elements*/) override {
        open_.push_back(Open{Setting::list(), {}, 0});
        return true;
    }
    bool end_array() override { return close(); }

    bool parse_error(std::size_t position, const std::string & /*last_token*/,
                     const nlohmann::detail::exception &error) override {
        problem_ = std::format("the text is not JSON at byte {}: {}", position, error.what());
        return false;
    }

    Result<Setting> result() {
        if (!problem_.empty()) {
            return Error{Errc::file_refused, std::move(problem_)};
        }
        return std::move(read_);
    }

private:
    // A map or a list not yet closed: for a map the key whose value comes next, and for a list how many it has.
    struct Open {
        Setting value;
        std::string key;
        std::size_t count = 0;
    };

    // Where the value being read is, as a message names it: `blocks[2].settings.tau`.
    std::string where() const {
        std::string path;
        for (const Open &open : open_) {
            if (open.value.is(Setting::Kind::map)) {
                path += path.empty() ? open.key : "." + open.key;
            } else {
                path += std::format("[{}]", open.count);
            }
        }
        return path.empty() ? "the whole of it" : "'" + path + "'";
    }

    bool fail(std::string_view what) {
        problem_ = std::format("{} {}", where(), what);
        return false;
    }

    bool put(Setting value) {
        if (open_.empty()) {
            read_ = std::move(value);
            return true;
        }
        Open &top = open_.back();
        if (top.value.is(Setting::Kind::map)) {
            top.value.set(std::move(top.key), std::move(value));
        } else {
            top.value.add(std::move(value));
            top.count += 1;
        }
        return true;
    }

    bool close() {
        Setting closed = std::move(open_.back().value);
        open_.pop_back();
        return put(std::move(closed));
    }

    std::vector<Open> open_;
    Setting read_;
    std::string problem_;
};

}  // namespace

Result<Setting> load_json(std::string_view text) {
    Builder builder;
    nlohmann::json::sax_parse(text.begin(), text.end(), &builder);
    return builder.result();
}

}  // namespace fluxgraph::v2

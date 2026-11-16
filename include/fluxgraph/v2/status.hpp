#pragma once

#include <optional>
#include <string>
#include <utility>
#include <variant>

namespace fluxgraph::v2 {

/// Why something was refused. The message names the thing at fault; its wording is not a contract.
enum class Errc {
    graph_refused,         ///< The graph cannot be compiled (sections 3 to 5, 9 and Appendix A).
    block_type_not_built,  ///< The graph names a block type of the catalogue that this build does not have.
    write_refused,         ///< A write was refused (rule 6.11). Nothing changed.
    call_refused,          ///< A call to tick was refused (rule 6.11). Nothing changed.
    rebase_refused,        ///< A rebase was refused (rule 6.11). Nothing changed.
    state_refused,         ///< A saved state is not of this graph (rule 8.2). Nothing changed.
};

struct Error {
    Errc code;
    std::string message;
};

/// Success, or an Error. The core reports every refusal this way and throws nothing of its own.
class [[nodiscard]] Status {
public:
    Status() = default;
    Status(Error error) : error_(std::move(error)) {}  // NOLINT(google-explicit-constructor)

    explicit operator bool() const { return !error_.has_value(); }
    bool ok() const { return !error_.has_value(); }
    /// Only when not ok().
    const Error &error() const { return *error_; }

private:
    std::optional<Error> error_;
};

/// A T, or an Error.
template <typename T>
class [[nodiscard]] Result {
public:
    Result(T value) : held_(std::move(value)) {}      // NOLINT(google-explicit-constructor)
    Result(Error error) : held_(std::move(error)) {}  // NOLINT(google-explicit-constructor)

    explicit operator bool() const { return held_.index() == 0; }
    bool ok() const { return held_.index() == 0; }
    /// Only when ok().
    T &value() { return *std::get_if<0>(&held_); }
    const T &value() const { return *std::get_if<0>(&held_); }
    T *operator->() { return std::get_if<0>(&held_); }
    const T *operator->() const { return std::get_if<0>(&held_); }
    /// Only when not ok().
    const Error &error() const { return *std::get_if<1>(&held_); }

private:
    std::variant<T, Error> held_;
};

}  // namespace fluxgraph::v2

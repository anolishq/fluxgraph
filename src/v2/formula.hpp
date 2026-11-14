#pragma once

// The formula language of Appendix A, with the states of section 7.1.

#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>

#include "fluxgraph/v2/value.hpp"

namespace fluxgraph::v2::detail {

class Formula {
public:
    /// Whether `text` is a name the grammar allows for an input: not a keyword and not a function.
    static bool is_input_name(std::string_view text);

    /// Reads one formula. False for one the grammar refuses, with what is wrong in `problem`.
    bool parse(std::string_view text, std::string &problem);

    /// The names the formula uses, each once, in the order it first uses them.
    const std::vector<std::string> &names() const { return names_; }

    /// Says where each name's value is to be found in what `evaluate` is handed: `places[i]` is for `names()[i]`.
    void connect(std::span<const std::size_t> places);

    /// The type of the formula, given the type of each input by place; empty where it rests on a type not yet
    /// known. False for a formula whose types do not agree (Appendix A), with what is wrong in `problem`.
    bool type(std::span<const std::optional<Type>> inputs, std::optional<Type> &type, std::string &problem) const;

    /// The value and the state of the formula (section 7.1). The sample time is the block's business.
    Value evaluate(std::span<const Value> inputs);

    /// Whether the last evaluation used the input at `place`, as rule D counts it: not an operand that did not
    /// decide, not an uncertain operand beside a good one that decides by itself, not a branch it did not take.
    bool used(std::size_t place) const;

private:
    enum class Op : std::uint8_t {
        number,
        boolean,
        input,
        negate,
        add,
        subtract,
        multiply,
        divide,
        less,
        less_or_equal,
        greater,
        greater_or_equal,
        equal,
        not_equal,
        logical_not,
        logical_and,
        logical_or,
        abs,
        min,
        max,
        exp,
        ln,
        sqrt,
        pow,
        when,
    };

    struct Node {
        Op op = Op::number;
        bool boolean = false;
        double number = 0.0;
        std::size_t input = 0;  // an index into names_, and after connect() a place
        std::size_t a = 0;      // operands: each an earlier node
        std::size_t b = 0;
        std::size_t c = 0;
    };

    class Parser;

    static std::string_view shown(Op op);

    std::vector<Node> nodes_;  // every node comes after its operands; the last is the formula
    std::vector<std::string> names_;
    std::vector<Value> scratch_;  // one per node, so that evaluating allocates nothing
    // What the last evaluation used, worked out when first asked for.
    mutable bool used_known_ = false;
    mutable std::vector<bool> node_used_;
    mutable std::vector<bool> place_used_;
};

}  // namespace fluxgraph::v2::detail

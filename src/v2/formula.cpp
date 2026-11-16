#include "formula.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <format>
#include <utility>

namespace fluxgraph::v2::detail {

namespace {

bool is_digit(char c) { return c >= '0' && c <= '9'; }
bool is_letter(char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_'; }

struct Function {
    std::string_view name;
    std::size_t operands;
};

constexpr std::array<Function, 8> kFunctions = {{
    {"abs", 1},
    {"min", 2},
    {"max", 2},
    {"exp", 1},
    {"ln", 1},
    {"sqrt", 1},
    {"pow", 2},
    {"when", 3},
}};

constexpr std::array<std::string_view, 5> kKeywords = {"and", "or", "not", "true", "false"};

const Function *function_named(std::string_view name) {
    for (const Function &function : kFunctions) {
        if (function.name == name) {
            return &function;
        }
    }
    return nullptr;
}

bool is_keyword(std::string_view name) {
    for (std::string_view keyword : kKeywords) {
        if (keyword == name) {
            return true;
        }
    }
    return false;
}

// Whether a number the library could not hold is out of range for being small and not for being large: whether
// its first digit that is not zero, with the exponent applied, is after the point.
bool is_below_one(std::string_view number) {
    const std::size_t e = number.find_first_of("eE");
    const std::string_view mantissa = number.substr(0, e);
    const std::size_t point = std::min(mantissa.find('.'), mantissa.size());
    const std::size_t first = mantissa.find_first_of("123456789");
    if (first == std::string_view::npos) {
        return true;
    }
    // The power of ten of the first digit, which is at most the mantissa's length either way.
    long long magnitude =
        first < point ? static_cast<long long>(point - first) - 1 : -static_cast<long long>(first - point);
    if (e != std::string_view::npos) {
        std::string_view digits = number.substr(e + 1);
        const bool negative = !digits.empty() && digits[0] == '-';
        if (!digits.empty() && (digits[0] == '-' || digits[0] == '+')) {
            digits.remove_prefix(1);
        }
        long long exponent = 0;
        for (char c : digits) {
            if (exponent < 1'000'000'000'000LL) {  // more than any mantissa can outweigh; it stops growing here
                exponent = exponent * 10 + (c - '0');
            }
        }
        magnitude += negative ? -exponent : exponent;
    }
    return magnitude < 0;
}

// Brackets, function calls and prefix operators nest by recursion in the parser. This is the most it will follow:
// an engine's own limit, and far past any formula written by hand.
constexpr int kMaxNesting = 200;

}  // namespace

bool Formula::is_input_name(std::string_view text) {
    if (text.empty() || !is_letter(text[0])) {
        return false;
    }
    for (char c : text) {
        if (!is_letter(c) && !is_digit(c)) {
            return false;
        }
    }
    return !is_keyword(text) && function_named(text) == nullptr;
}

class Formula::Parser {
public:
    Parser(std::string_view text, Formula &formula) : text_(text), formula_(formula) {}

    bool run(std::string &problem) {
        std::size_t root = 0;
        if (!next() || !parse_or(root)) {
            problem = problem_;
            return false;
        }
        if (token_ != Token::end) {
            problem = std::format("unexpected {} at character {}", shown_token(), token_at_ + 1);
            return false;
        }
        return true;
    }

private:
    enum class Token { end, number, name, symbol };

    bool fail(std::string problem) {
        problem_ = std::move(problem);
        return false;
    }

    std::string shown_token() const {
        if (token_ == Token::end) {
            return "end of the formula";
        }
        return std::format("'{}'", word_);
    }

    // Reads the next token into token_ and word_.
    bool next() {
        while (at_ < text_.size() && (text_[at_] == ' ' || text_[at_] == '\t')) {
            ++at_;
        }
        token_at_ = at_;
        if (at_ == text_.size()) {
            token_ = Token::end;
            word_ = {};
            return true;
        }
        const char c = text_[at_];
        if (is_digit(c)) {
            return next_number();
        }
        if (is_letter(c)) {
            while (at_ < text_.size() && (is_letter(text_[at_]) || is_digit(text_[at_]))) {
                ++at_;
            }
            token_ = Token::name;
            word_ = text_.substr(token_at_, at_ - token_at_);
            return true;
        }
        const std::string_view two = text_.substr(at_, 2);
        if (two == "<=" || two == ">=" || two == "==" || two == "!=") {
            at_ += 2;
        } else if (std::string_view("<>+-*/(),").find(c) != std::string_view::npos) {
            at_ += 1;
        } else {
            return fail(std::format("'{}' at character {} is not part of a formula", c, at_ + 1));
        }
        token_ = Token::symbol;
        word_ = text_.substr(token_at_, at_ - token_at_);
        return true;
    }

    // Digits, an optional point and more digits, an optional exponent, and nothing else (Appendix A).
    bool next_number() {
        while (at_ < text_.size() && is_digit(text_[at_])) {
            ++at_;
        }
        if (at_ < text_.size() && text_[at_] == '.') {
            ++at_;
            if (at_ == text_.size() || !is_digit(text_[at_])) {
                return fail(
                    std::format("the number at character {} has a point with no digits after it", token_at_ + 1));
            }
            while (at_ < text_.size() && is_digit(text_[at_])) {
                ++at_;
            }
        }
        if (at_ < text_.size() && (text_[at_] == 'e' || text_[at_] == 'E')) {
            std::size_t after = at_ + 1;
            if (after < text_.size() && (text_[after] == '+' || text_[after] == '-')) {
                ++after;
            }
            if (after < text_.size() && is_digit(text_[after])) {
                at_ = after;
                while (at_ < text_.size() && is_digit(text_[at_])) {
                    ++at_;
                }
            }
        }
        if (at_ < text_.size() && (is_letter(text_[at_]) || text_[at_] == '.')) {
            return fail(std::format("the number at character {} runs into '{}'", token_at_ + 1, text_[at_]));
        }
        token_ = Token::number;
        word_ = text_.substr(token_at_, at_ - token_at_);
        return true;
    }

    bool is_symbol(std::string_view symbol) const { return token_ == Token::symbol && word_ == symbol; }
    bool is_word(std::string_view word) const { return token_ == Token::name && word_ == word; }

    std::size_t push(Node node) {
        formula_.nodes_.push_back(node);
        return formula_.nodes_.size() - 1;
    }

    std::size_t push(Op op, std::size_t a, std::size_t b = 0, std::size_t c = 0) {
        Node node;
        node.op = op;
        node.a = a;
        node.b = b;
        node.c = c;
        return push(node);
    }

    bool deeper() {
        if (++depth_ > kMaxNesting) {
            return fail(std::format("the formula nests more than {} deep", kMaxNesting));
        }
        return true;
    }

    bool parse_or(std::size_t &node) {
        if (!deeper() || !parse_and(node)) {
            return false;
        }
        while (is_word("or")) {
            std::size_t right = 0;
            if (!next() || !parse_and(right)) {
                return false;
            }
            node = push(Op::logical_or, node, right);
        }
        --depth_;
        return true;
    }

    bool parse_and(std::size_t &node) {
        if (!parse_not(node)) {
            return false;
        }
        while (is_word("and")) {
            std::size_t right = 0;
            if (!next() || !parse_not(right)) {
                return false;
            }
            node = push(Op::logical_and, node, right);
        }
        return true;
    }

    bool parse_not(std::size_t &node) {
        if (is_word("not")) {
            std::size_t operand = 0;
            if (!deeper() || !next() || !parse_not(operand)) {
                return false;
            }
            --depth_;
            node = push(Op::logical_not, operand);
            return true;
        }
        return parse_compare(node);
    }

    bool parse_compare(std::size_t &node) {
        if (!parse_sum(node)) {
            return false;
        }
        static constexpr std::array<std::pair<std::string_view, Op>, 6> kComparisons = {{
            {"<", Op::less},
            {"<=", Op::less_or_equal},
            {">", Op::greater},
            {">=", Op::greater_or_equal},
            {"==", Op::equal},
            {"!=", Op::not_equal},
        }};
        for (const auto &[symbol, op] : kComparisons) {
            if (is_symbol(symbol)) {
                std::size_t right = 0;
                if (!next() || !parse_sum(right)) {
                    return false;
                }
                node = push(op, node, right);
                for (const auto &[second, unused] : kComparisons) {
                    if (is_symbol(second)) {
                        return fail(std::format("comparisons do not chain: '{}' at character {} follows another",
                                                second, token_at_ + 1));
                    }
                }
                return true;
            }
        }
        return true;
    }

    bool parse_sum(std::size_t &node) {
        if (!parse_product(node)) {
            return false;
        }
        while (is_symbol("+") || is_symbol("-")) {
            const Op op = is_symbol("+") ? Op::add : Op::subtract;
            std::size_t right = 0;
            if (!next() || !parse_product(right)) {
                return false;
            }
            node = push(op, node, right);
        }
        return true;
    }

    bool parse_product(std::size_t &node) {
        if (!parse_unary(node)) {
            return false;
        }
        while (is_symbol("*") || is_symbol("/")) {
            const Op op = is_symbol("*") ? Op::multiply : Op::divide;
            std::size_t right = 0;
            if (!next() || !parse_unary(right)) {
                return false;
            }
            node = push(op, node, right);
        }
        return true;
    }

    bool parse_unary(std::size_t &node) {
        if (is_symbol("-")) {
            std::size_t operand = 0;
            if (!deeper() || !next() || !parse_unary(operand)) {
                return false;
            }
            --depth_;
            node = push(Op::negate, operand);
            return true;
        }
        return parse_primary(node);
    }

    bool parse_primary(std::size_t &node) {
        if (token_ == Token::number) {
            Node number;
            number.op = Op::number;
            const std::from_chars_result read =
                std::from_chars(word_.data(), word_.data() + word_.size(), number.number);
            if (read.ec == std::errc::result_out_of_range && is_below_one(word_)) {
                number.number = 0.0;  // too small for a double: the nearest one is zero
            } else if (read.ec != std::errc() || !std::isfinite(number.number)) {
                return fail(std::format("the number {} is too large for a double", word_));
            }
            node = push(number);
            return next();
        }
        if (is_symbol("(")) {
            if (!next() || !parse_or(node)) {
                return false;
            }
            if (!is_symbol(")")) {
                return fail(std::format("expected ')' and found {} at character {}", shown_token(), token_at_ + 1));
            }
            return next();
        }
        if (token_ != Token::name) {
            return fail(std::format("expected a value and found {} at character {}", shown_token(), token_at_ + 1));
        }
        if (word_ == "true" || word_ == "false") {
            Node boolean;
            boolean.op = Op::boolean;
            boolean.boolean = word_ == "true";
            node = push(boolean);
            return next();
        }
        if (is_keyword(word_)) {
            return fail(std::format("expected a value and found '{}' at character {}", word_, token_at_ + 1));
        }
        if (const Function *function = function_named(word_)) {
            return parse_call(*function, node);
        }
        Node input;
        input.op = Op::input;
        input.input = formula_.names_.size();
        for (std::size_t i = 0; i < formula_.names_.size(); ++i) {
            if (formula_.names_[i] == word_) {
                input.input = i;
            }
        }
        if (input.input == formula_.names_.size()) {
            formula_.names_.emplace_back(word_);
        }
        node = push(input);
        return next();
    }

    bool parse_call(const Function &function, std::size_t &node) {
        if (!next()) {
            return false;
        }
        if (!is_symbol("(")) {
            return fail(std::format("'{}' is a function, and is not followed by '('", function.name));
        }
        std::array<std::size_t, 3> operands{};
        std::size_t count = 0;
        do {
            std::size_t operand = 0;
            if (!next() || !parse_or(operand)) {
                return false;
            }
            if (count < operands.size()) {
                operands[count] = operand;
            }
            ++count;
        } while (is_symbol(","));
        if (!is_symbol(")")) {
            return fail(std::format("expected ')' and found {} at character {}", shown_token(), token_at_ + 1));
        }
        if (count != function.operands) {
            return fail(std::format("'{}' takes {} and is given {}", function.name, function.operands, count));
        }
        Op op = Op::when;
        for (Op candidate : {Op::abs, Op::min, Op::max, Op::exp, Op::ln, Op::sqrt, Op::pow, Op::when}) {
            if (Formula::shown(candidate) == function.name) {
                op = candidate;
            }
        }
        node = push(op, operands[0], operands[1], operands[2]);
        return next();
    }

    std::string_view text_;
    Formula &formula_;
    std::size_t at_ = 0;
    std::size_t token_at_ = 0;
    Token token_ = Token::end;
    std::string_view word_;
    int depth_ = 0;
    std::string problem_;
};

std::string_view Formula::shown(Op op) {
    switch (op) {
        case Op::number:
            return "a number";
        case Op::boolean:
            return "a boolean";
        case Op::input:
            return "an input";
        case Op::negate:
        case Op::subtract:
            return "-";
        case Op::add:
            return "+";
        case Op::multiply:
            return "*";
        case Op::divide:
            return "/";
        case Op::less:
            return "<";
        case Op::less_or_equal:
            return "<=";
        case Op::greater:
            return ">";
        case Op::greater_or_equal:
            return ">=";
        case Op::equal:
            return "==";
        case Op::not_equal:
            return "!=";
        case Op::logical_not:
            return "not";
        case Op::logical_and:
            return "and";
        case Op::logical_or:
            return "or";
        case Op::abs:
            return "abs";
        case Op::min:
            return "min";
        case Op::max:
            return "max";
        case Op::exp:
            return "exp";
        case Op::ln:
            return "ln";
        case Op::sqrt:
            return "sqrt";
        case Op::pow:
            return "pow";
        case Op::when:
            return "when";
    }
    return "?";
}

bool Formula::parse(std::string_view text, std::string &problem) {
    nodes_.clear();
    names_.clear();
    if (text.find_first_of("\r\n") != std::string_view::npos) {
        problem = "a formula is one line";
        return false;
    }
    if (text.find_first_not_of(" \t") == std::string_view::npos) {
        problem = "the formula is empty";
        return false;
    }
    Parser parser(text, *this);
    if (!parser.run(problem)) {
        return false;
    }
    scratch_.assign(nodes_.size(), Value{});
    node_used_.assign(nodes_.size(), false);
    used_known_ = false;
    return true;
}

void Formula::connect(std::span<const std::size_t> places) {
    std::size_t most = 0;
    for (Node &node : nodes_) {
        if (node.op == Op::input) {
            node.input = places[node.input];
            most = std::max(most, node.input + 1);
        }
    }
    place_used_.assign(most, false);
}

bool Formula::used(std::size_t place) const {
    if (!used_known_) {
        // From the formula down: a node that was used uses its operands as its rule says. Every node comes
        // after its operands, so one pass from the last to the first reaches each after all that use it.
        std::fill(node_used_.begin(), node_used_.end(), false);
        std::fill(place_used_.begin(), place_used_.end(), false);
        node_used_.back() = true;
        for (std::size_t i = nodes_.size(); i-- > 0;) {
            if (!node_used_[i]) {
                continue;
            }
            const Node &node = nodes_[i];
            const Value &a = scratch_[node.a];
            const Value &b = scratch_[node.b];
            switch (node.op) {
                case Op::number:
                case Op::boolean:
                    break;
                case Op::input:
                    place_used_[node.input] = true;
                    break;
                case Op::negate:
                case Op::abs:
                case Op::exp:
                case Op::ln:
                case Op::sqrt:
                case Op::logical_not:
                    node_used_[node.a] = true;
                    break;
                case Op::logical_and:
                case Op::logical_or: {  // rule 7.1.2
                    const bool deciding = node.op == Op::logical_or;
                    const bool a_decides = a.is_usable() && a.boolean == deciding;
                    const bool b_decides = b.is_usable() && b.boolean == deciding;
                    if (!a_decides && !b_decides) {
                        node_used_[node.a] = node_used_[node.b] = true;  // rule 7.1.1: both
                        break;
                    }
                    // Of those that decide: the good ones, each of which decides by itself, or all of them
                    // where none is good.
                    const bool a_good = a_decides && a.state == State::good;
                    const bool b_good = b_decides && b.state == State::good;
                    const bool any_good = a_good || b_good;
                    node_used_[node.a] = node_used_[node.a] || (any_good ? a_good : a_decides);
                    node_used_[node.b] = node_used_[node.b] || (any_good ? b_good : b_decides);
                    break;
                }
                case Op::when:  // rule 7.1.3: the condition, and the branch it chose
                    node_used_[node.a] = true;
                    if (a.is_usable()) {
                        node_used_[a.boolean ? node.b : node.c] = true;
                    }
                    break;
                default:  // arithmetic, the two-operand functions and the comparisons: both operands
                    node_used_[node.a] = node_used_[node.b] = true;
                    break;
            }
        }
        used_known_ = true;
    }
    return place < place_used_.size() && place_used_[place];
}

bool Formula::type(std::span<const std::optional<Type>> inputs, std::optional<Type> &type, std::string &problem) const {
    std::vector<std::optional<Type>> types(nodes_.size());
    const auto is_not = [&](std::size_t node, Type wanted) {
        return types[node].has_value() && *types[node] != wanted;
    };
    for (std::size_t i = 0; i < nodes_.size(); ++i) {
        const Node &node = nodes_[i];
        switch (node.op) {
            case Op::number:
                types[i] = Type::number;
                break;
            case Op::boolean:
                types[i] = Type::boolean;
                break;
            case Op::input:
                types[i] = inputs[node.input];
                break;
            case Op::negate:
            case Op::abs:
            case Op::exp:
            case Op::ln:
            case Op::sqrt:
                if (is_not(node.a, Type::number)) {
                    problem = std::format("'{}' takes a number, and is given a boolean", shown(node.op));
                    return false;
                }
                types[i] = Type::number;
                break;
            case Op::add:
            case Op::subtract:
            case Op::multiply:
            case Op::divide:
            case Op::min:
            case Op::max:
            case Op::pow:
            case Op::less:
            case Op::less_or_equal:
            case Op::greater:
            case Op::greater_or_equal: {
                if (is_not(node.a, Type::number) || is_not(node.b, Type::number)) {
                    problem = std::format("'{}' takes numbers, and is given a boolean", shown(node.op));
                    return false;
                }
                const bool compares = node.op == Op::less || node.op == Op::less_or_equal || node.op == Op::greater ||
                                      node.op == Op::greater_or_equal;
                types[i] = compares ? Type::boolean : Type::number;
                break;
            }
            case Op::equal:
            case Op::not_equal:
                if (types[node.a].has_value() && types[node.b].has_value() && *types[node.a] != *types[node.b]) {
                    problem =
                        std::format("'{}' takes two of one type, and is given a number and a boolean", shown(node.op));
                    return false;
                }
                types[i] = Type::boolean;
                break;
            case Op::logical_not:
                if (is_not(node.a, Type::boolean)) {
                    problem = "'not' takes a boolean, and is given a number";
                    return false;
                }
                types[i] = Type::boolean;
                break;
            case Op::logical_and:
            case Op::logical_or:
                if (is_not(node.a, Type::boolean) || is_not(node.b, Type::boolean)) {
                    problem = std::format("'{}' takes booleans, and is given a number", shown(node.op));
                    return false;
                }
                types[i] = Type::boolean;
                break;
            case Op::when:
                if (is_not(node.a, Type::boolean)) {
                    problem = "the condition of 'when' is a number, and has to be a boolean";
                    return false;
                }
                if (types[node.b].has_value() && types[node.c].has_value() && *types[node.b] != *types[node.c]) {
                    problem = "the two branches of 'when' are a number and a boolean, and have to be of one type";
                    return false;
                }
                types[i] = types[node.b].has_value() ? types[node.b] : types[node.c];
                break;
        }
    }
    type = types.back();
    return true;
}

namespace {

// Rule 7.1.4: a result that is not finite is `bad`.
Value number_or_bad(double number, State state) {
    return std::isfinite(number) ? Value::of(number, state) : Value::none(State::bad);
}

}  // namespace

Value Formula::evaluate(std::span<const Value> inputs) {
    used_known_ = false;
    for (std::size_t i = 0; i < nodes_.size(); ++i) {
        const Node &node = nodes_[i];
        const Value &a = scratch_[node.a];
        const Value &b = scratch_[node.b];
        Value result;
        switch (node.op) {
            case Op::number:  // rule 7.1.7: a number written in a formula is good
                result = Value::of(node.number);
                break;
            case Op::boolean:
                result = Value::of(node.boolean);
                break;
            case Op::input:
                result = inputs[node.input];
                break;
            case Op::negate:
            case Op::abs:
            case Op::exp:
            case Op::ln:
            case Op::sqrt:
                if (!a.is_usable()) {  // rule 7.1.1
                    result = Value::none(a.state);
                } else if ((node.op == Op::ln || node.op == Op::sqrt) && a.number < 0.0) {  // rule 7.1.4
                    result = Value::none(State::bad);
                } else {
                    double number = 0.0;
                    if (node.op == Op::negate) {
                        number = -a.number;
                    } else if (node.op == Op::abs) {
                        number = std::fabs(a.number);
                    } else if (node.op == Op::exp) {
                        number = std::exp(a.number);
                    } else if (node.op == Op::ln) {
                        number = std::log(a.number);
                    } else {
                        number = std::sqrt(a.number);
                    }
                    result = number_or_bad(number, a.state);
                }
                break;
            case Op::add:
            case Op::subtract:
            case Op::multiply:
            case Op::divide:
            case Op::min:
            case Op::max:
            case Op::pow: {
                const State state = worst(a.state, b.state);
                if (!usable(state)) {
                    result = Value::none(state);
                } else if (node.op == Op::divide && b.number == 0.0) {
                    result = Value::none(State::bad);
                } else {
                    double number = 0.0;
                    if (node.op == Op::add) {
                        number = a.number + b.number;
                    } else if (node.op == Op::subtract) {
                        number = a.number - b.number;
                    } else if (node.op == Op::multiply) {
                        number = a.number * b.number;
                    } else if (node.op == Op::divide) {
                        number = a.number / b.number;
                    } else if (node.op == Op::min) {
                        number = b.number < a.number ? b.number : a.number;
                    } else if (node.op == Op::max) {
                        number = b.number > a.number ? b.number : a.number;
                    } else {
                        number = std::pow(a.number, b.number);  // one with no real value is not a number
                    }
                    result = number_or_bad(number, state);
                }
                break;
            }
            case Op::less:
            case Op::less_or_equal:
            case Op::greater:
            case Op::greater_or_equal: {
                const State state = worst(a.state, b.state);
                if (!usable(state)) {
                    result = Value::none(state, Type::boolean);
                } else if (node.op == Op::less) {
                    result = Value::of(a.number < b.number, state);
                } else if (node.op == Op::less_or_equal) {
                    result = Value::of(a.number <= b.number, state);
                } else if (node.op == Op::greater) {
                    result = Value::of(a.number > b.number, state);
                } else {
                    result = Value::of(a.number >= b.number, state);
                }
                break;
            }
            case Op::equal:
            case Op::not_equal: {  // rule 7.1.6: exactly
                const State state = worst(a.state, b.state);
                if (!usable(state)) {
                    result = Value::none(state, Type::boolean);
                } else {
                    const bool same = a.type == Type::boolean ? a.boolean == b.boolean : a.number == b.number;
                    result = Value::of(node.op == Op::equal ? same : !same, state);
                }
                break;
            }
            case Op::logical_not:
                result = a.is_usable() ? Value::of(!a.boolean, a.state) : Value::none(a.state, Type::boolean);
                break;
            case Op::logical_and:
            case Op::logical_or: {  // rule 7.1.2
                const bool deciding = node.op == Op::logical_or;
                const bool a_decides = a.is_usable() && a.boolean == deciding;
                const bool b_decides = b.is_usable() && b.boolean == deciding;
                const State state = worst(a.state, b.state);
                if (a_decides || b_decides) {
                    const bool good = (a_decides && a.state == State::good) || (b_decides && b.state == State::good);
                    result = Value::of(deciding, good ? State::good : State::uncertain);
                } else if (!usable(state)) {
                    result = Value::none(state, Type::boolean);
                } else {
                    result = Value::of(!deciding, state);
                }
                break;
            }
            case Op::when: {  // rule 7.1.3
                if (!a.is_usable()) {
                    result = Value::none(a.state);
                } else {
                    result = a.boolean ? b : scratch_[node.c];
                    result.state = worst(result.state, a.state);
                }
                break;
            }
        }
        result.timed = false;
        scratch_[i] = result;
    }
    return scratch_.back();
}

}  // namespace fluxgraph::v2::detail

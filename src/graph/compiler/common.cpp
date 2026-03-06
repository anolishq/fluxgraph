#include "common.hpp"
#include "fluxgraph/graph/param_utils.hpp"
#include <algorithm>
#include <cctype>
#include <cmath>
#include <stdexcept>

namespace fluxgraph::compiler_internal {

const ParamValue &require_param(const ParamMap &params, const std::string &name,
                                const std::string &context) {
  auto it = params.find(name);
  if (it == params.end()) {
    throw std::runtime_error("Missing required parameter at " + context + "/" +
                             name);
  }
  return it->second;
}

double as_double(const ParamValue &value, const std::string &path) {
  return param::as_double(value, path);
}

int64_t as_int64(const ParamValue &value, const std::string &path) {
  return param::as_int64(value, path);
}

std::string as_string(const ParamValue &value, const std::string &path) {
  return param::as_string(value, path);
}

void require_finite(const double value, const std::string &path) {
  if (!std::isfinite(value)) {
    throw std::runtime_error("Invalid parameter at " + path +
                             ": expected finite number");
  }
}

void require_finite_positive(const double value, const std::string &path) {
  if (!std::isfinite(value) || value <= 0.0) {
    throw std::runtime_error("Invalid parameter at " + path + ": expected > 0");
  }
}

void require_finite_non_negative(const double value, const std::string &path) {
  if (!std::isfinite(value) || value < 0.0) {
    throw std::runtime_error("Invalid parameter at " + path +
                             ": expected >= 0");
  }
}

std::string format_scalar_constraint_rule(const ScalarConstraint &constraint) {
  switch (constraint.kind) {
  case ScalarConstraint::Kind::finite:
    return "finite number";
  case ScalarConstraint::Kind::greater_than:
    return "> " + std::to_string(constraint.a);
  case ScalarConstraint::Kind::greater_equal:
    return ">= " + std::to_string(constraint.a);
  case ScalarConstraint::Kind::closed_interval:
    return "in [" + std::to_string(constraint.a) + ", " +
           std::to_string(constraint.b) + "]";
  }
  return "finite number";
}

bool satisfies_scalar_constraint(const double value,
                                 const ScalarConstraint &constraint) {
  if (!std::isfinite(value)) {
    return false;
  }

  switch (constraint.kind) {
  case ScalarConstraint::Kind::finite:
    return true;
  case ScalarConstraint::Kind::greater_than:
    return value > constraint.a;
  case ScalarConstraint::Kind::greater_equal:
    return value >= constraint.a;
  case ScalarConstraint::Kind::closed_interval:
    return constraint.a <= constraint.b && value >= constraint.a &&
           value <= constraint.b;
  }
  return false;
}

std::string trim_copy(const std::string &text) {
  auto begin = std::find_if_not(text.begin(), text.end(), [](unsigned char c) {
    return std::isspace(c) != 0;
  });
  auto end = std::find_if_not(text.rbegin(), text.rend(), [](unsigned char c) {
               return std::isspace(c) != 0;
             }).base();

  if (begin >= end) {
    return "";
  }
  return std::string(begin, end);
}

const std::regex &rule_comparator_regex() {
  static const std::regex kComparatorPattern(
      R"(^([A-Za-z0-9_./-]+)\s*(<=|>=|==|!=|<|>)\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)$)");
  return kComparatorPattern;
}

std::function<bool(const SignalStore &)>
compile_condition_expr(const std::string &expr, SignalNamespace &signal_ns,
                       const std::string &rule_id) {
  const std::string trimmed = trim_copy(expr);
  std::smatch match;
  if (!std::regex_match(trimmed, match, rule_comparator_regex())) {
    throw std::runtime_error("Unsupported rule condition syntax for rule '" +
                             rule_id +
                             "'. Supported form: <signal_path> <op> <number>");
  }

  const std::string signal_path = match[1].str();
  const std::string op = match[2].str();
  const double rhs = std::stod(match[3].str());
  const SignalId signal_id = signal_ns.intern(signal_path);

  if (op == "<") {
    return [signal_id, rhs](const SignalStore &store) {
      return store.read_value(signal_id) < rhs;
    };
  }
  if (op == "<=") {
    return [signal_id, rhs](const SignalStore &store) {
      return store.read_value(signal_id) <= rhs;
    };
  }
  if (op == ">") {
    return [signal_id, rhs](const SignalStore &store) {
      return store.read_value(signal_id) > rhs;
    };
  }
  if (op == ">=") {
    return [signal_id, rhs](const SignalStore &store) {
      return store.read_value(signal_id) >= rhs;
    };
  }
  if (op == "==") {
    return [signal_id, rhs](const SignalStore &store) {
      return store.read_value(signal_id) == rhs;
    };
  }

  return [signal_id, rhs](const SignalStore &store) {
    return store.read_value(signal_id) != rhs;
  };
}

} // namespace fluxgraph::compiler_internal

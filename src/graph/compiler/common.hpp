#pragma once

#include "fluxgraph/graph/compiler.hpp"
#include <cstdint>
#include <functional>
#include <map>
#include <regex>
#include <string>

namespace fluxgraph::compiler_internal {

const ParamValue &require_param(const ParamMap &params, const std::string &name,
                                const std::string &context);

double as_double(const ParamValue &value, const std::string &path);
int64_t as_int64(const ParamValue &value, const std::string &path);
std::string as_string(const ParamValue &value, const std::string &path);

void require_finite(double value, const std::string &path);
void require_finite_positive(double value, const std::string &path);
void require_finite_non_negative(double value, const std::string &path);

std::string format_scalar_constraint_rule(const ScalarConstraint &constraint);
bool satisfies_scalar_constraint(double value,
                                 const ScalarConstraint &constraint);

std::string trim_copy(const std::string &text);
const std::regex &rule_comparator_regex();
std::function<bool(const SignalStore &)>
compile_condition_expr(const std::string &expr, SignalNamespace &signal_ns,
                       const std::string &rule_id);

} // namespace fluxgraph::compiler_internal

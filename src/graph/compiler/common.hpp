#pragma once

#include <cstdint>
#include <functional>
#include <map>
#include <regex>
#include <string>

#include "fluxgraph/graph/compiler.hpp"

namespace fluxgraph::compiler_internal {

const ParamValue &require_param(const ParamMap &params, const std::string &name, const std::string &context);

double as_double(const ParamValue &value, const std::string &path);
int64_t as_int64(const ParamValue &value, const std::string &path);
bool as_bool(const ParamValue &value, const std::string &path);
std::string as_string(const ParamValue &value, const std::string &path);
const ParamArray &as_array(const ParamValue &value, const std::string &path);
const ParamObject &as_object(const ParamValue &value, const std::string &path);

void require_finite(double value, const std::string &path);
void require_finite_positive(double value, const std::string &path);
void require_finite_non_negative(double value, const std::string &path);

std::string format_scalar_constraint_rule(const ScalarConstraint &constraint);
bool satisfies_scalar_constraint(double value, const ScalarConstraint &constraint);

std::string trim_copy(const std::string &text);
const std::regex &rule_comparator_regex();
std::function<bool(const SignalStore &)> compile_condition_expr(const std::string &expr, SignalNamespace &signal_ns,
                                                                const std::string &rule_id);

}  // namespace fluxgraph::compiler_internal

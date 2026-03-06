#pragma once

#include "fluxgraph/core/types.hpp"
#include <string>

namespace fluxgraph::param {

std::string type_name(const ParamValue &value);

double as_double(const ParamValue &value, const std::string &path);
int64_t as_int64(const ParamValue &value, const std::string &path);
bool as_bool(const ParamValue &value, const std::string &path);
std::string as_string(const ParamValue &value, const std::string &path);
const ParamArray &as_array(const ParamValue &value, const std::string &path);
const ParamObject &as_object(const ParamValue &value, const std::string &path);

} // namespace fluxgraph::param

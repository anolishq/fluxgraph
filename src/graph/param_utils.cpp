#include "fluxgraph/graph/param_utils.hpp"
#include <stdexcept>

namespace fluxgraph::param {

std::string type_name(const ParamValue &value) {
  if (std::holds_alternative<double>(value)) {
    return "double";
  }
  if (std::holds_alternative<int64_t>(value)) {
    return "int64";
  }
  if (std::holds_alternative<bool>(value)) {
    return "bool";
  }
  if (std::holds_alternative<std::string>(value)) {
    return "string";
  }
  if (std::holds_alternative<ParamArray>(value)) {
    return "array";
  }
  return "object";
}

double as_double(const ParamValue &value, const std::string &path) {
  if (std::holds_alternative<double>(value)) {
    return std::get<double>(value);
  }
  if (std::holds_alternative<int64_t>(value)) {
    return static_cast<double>(std::get<int64_t>(value));
  }
  throw std::runtime_error("Type error at " + path + ": expected number, got " +
                           type_name(value));
}

int64_t as_int64(const ParamValue &value, const std::string &path) {
  if (std::holds_alternative<int64_t>(value)) {
    return std::get<int64_t>(value);
  }
  throw std::runtime_error("Type error at " + path + ": expected int64, got " +
                           type_name(value));
}

bool as_bool(const ParamValue &value, const std::string &path) {
  if (std::holds_alternative<bool>(value)) {
    return std::get<bool>(value);
  }
  throw std::runtime_error("Type error at " + path + ": expected bool, got " +
                           type_name(value));
}

std::string as_string(const ParamValue &value, const std::string &path) {
  if (std::holds_alternative<std::string>(value)) {
    return std::get<std::string>(value);
  }
  throw std::runtime_error("Type error at " + path + ": expected string, got " +
                           type_name(value));
}

const ParamArray &as_array(const ParamValue &value, const std::string &path) {
  if (std::holds_alternative<ParamArray>(value)) {
    return std::get<ParamArray>(value);
  }
  throw std::runtime_error("Type error at " + path + ": expected array, got " +
                           type_name(value));
}

const ParamObject &as_object(const ParamValue &value,
                             const std::string &path) {
  if (std::holds_alternative<ParamObject>(value)) {
    return std::get<ParamObject>(value);
  }
  throw std::runtime_error("Type error at " + path + ": expected object, got " +
                           type_name(value));
}

} // namespace fluxgraph::param

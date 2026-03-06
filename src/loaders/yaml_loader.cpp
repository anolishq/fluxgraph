#ifdef FLUXGRAPH_YAML_ENABLED

#include "fluxgraph/loaders/yaml_loader.hpp"
#include "param_parse_limits.hpp"
#include <cerrno>
#include <cstdlib>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <yaml-cpp/yaml.h>

namespace fluxgraph::loaders {

namespace {

// Helper to format error message with line/column information
std::string format_yaml_error(const std::string &message,
                              const YAML::Mark &mark) {
  return "YAML parse error at line " + std::to_string(mark.line + 1) +
         ", column " + std::to_string(mark.column + 1) + ": " + message;
}

bool parse_int64_strict(const std::string &text, int64_t &out) {
  if (text.empty()) {
    return false;
  }
  errno = 0;
  char *end = nullptr;
  const long long parsed = std::strtoll(text.c_str(), &end, 10);
  if (errno == ERANGE || end != text.c_str() + text.size()) {
    return false;
  }
  if (parsed < std::numeric_limits<int64_t>::min() ||
      parsed > std::numeric_limits<int64_t>::max()) {
    return false;
  }
  out = static_cast<int64_t>(parsed);
  return true;
}

bool parse_double_strict(const std::string &text, double &out) {
  if (text.empty()) {
    return false;
  }
  errno = 0;
  char *end = nullptr;
  const double parsed = std::strtod(text.c_str(), &end);
  if (errno == ERANGE || end != text.c_str() + text.size()) {
    return false;
  }
  out = parsed;
  return true;
}

ParamValue yaml_to_param_value(const YAML::Node &node, const std::string &path,
                               detail::ParamParseBudget &budget,
                               size_t depth = 0) {
  budget.check_depth(depth, path);
  budget.consume_node(path);

  if (node.IsScalar()) {
    const std::string scalar = node.as<std::string>();
    detail::check_string_size(scalar.size(), path);
    if (scalar == "true") {
      return true;
    }
    if (scalar == "false") {
      return false;
    }

    int64_t int_val = 0;
    if (parse_int64_strict(scalar, int_val)) {
      return int_val;
    }

    double double_val = 0.0;
    if (parse_double_strict(scalar, double_val)) {
      return double_val;
    }

    return scalar;
  }

  if (node.IsSequence()) {
    detail::check_array_size(node.size(), path);
    ParamArray arr;
    arr.reserve(node.size());
    for (size_t i = 0; i < node.size(); ++i) {
      arr.push_back(yaml_to_param_value(node[i], path + "/" + std::to_string(i),
                                        budget, depth + 1));
    }
    return arr;
  }

  if (node.IsMap()) {
    detail::check_object_size(node.size(), path);
    ParamObject obj;
    for (auto it = node.begin(); it != node.end(); ++it) {
      const std::string key = it->first.as<std::string>();
      detail::check_string_size(key.size(), path + "/<key>");
      obj.emplace(key, yaml_to_param_value(it->second, path + "/" + key,
                                           budget, depth + 1));
    }
    return obj;
  } else {
    throw std::runtime_error("YAML parse error at " + path +
                             ": Expected scalar/sequence/map value");
  }
}

// Convert YAML node to Variant
Variant yaml_to_variant(const YAML::Node &node, const std::string &path) {
  if (node.IsScalar()) {
    // Try to determine type from the actual content
    try {
      // Try boolean first
      if (node.as<std::string>() == "true" ||
          node.as<std::string>() == "false") {
        return node.as<bool>();
      }
      // Try integer
      if (node.as<std::string>().find('.') == std::string::npos) {
        return node.as<int64_t>();
      }
      // Try double
      return node.as<double>();
    } catch (...) {
      // Fall back to string
      return node.as<std::string>();
    }
  } else {
    throw std::runtime_error(
        "YAML parse error at " + path +
        ": Command args must be scalar (double/int64/bool/string)");
  }
}

// Parse transform specification
TransformSpec parse_transform(const YAML::Node &node, const std::string &base_path,
                              detail::ParamParseBudget &budget) {
  TransformSpec spec;

  std::string path = base_path + "/transform";

  if (!node["type"]) {
    throw std::runtime_error("YAML parse error at " + path +
                             ": Missing required field 'type'");
  }

  spec.type = node["type"].as<std::string>();

  if (node["params"]) {
    if (!node["params"].IsMap()) {
      throw std::runtime_error("YAML parse error at " + path +
                               "/params: Expected map");
    }
    for (auto it = node["params"].begin(); it != node["params"].end(); ++it) {
      std::string key = it->first.as<std::string>();
      std::string param_path = path + "/params/" + key;
      spec.params[key] = yaml_to_param_value(it->second, param_path, budget);
    }
  }

  return spec;
}

// Parse edge specification
EdgeSpec parse_edge(const YAML::Node &node, size_t index,
                    detail::ParamParseBudget &budget) {
  std::string path = "/edges/" + std::to_string(index);
  EdgeSpec spec;

  if (!node["source"]) {
    throw std::runtime_error("YAML parse error at " + path +
                             ": Missing required field 'source'");
  }
  if (!node["target"]) {
    throw std::runtime_error("YAML parse error at " + path +
                             ": Missing required field 'target'");
  }
  if (!node["transform"]) {
    throw std::runtime_error("YAML parse error at " + path +
                             ": Missing required field 'transform'");
  }
  if (!node["transform"].IsMap()) {
    throw std::runtime_error("YAML parse error at " + path +
                             "/transform: Expected map");
  }

  spec.source_path = node["source"].as<std::string>();
  spec.target_path = node["target"].as<std::string>();
  spec.transform = parse_transform(node["transform"], path, budget);

  return spec;
}

SignalSpec parse_signal(const YAML::Node &node, size_t index) {
  const std::string path = "/signals/" + std::to_string(index);
  SignalSpec spec;

  if (!node["path"]) {
    throw std::runtime_error("YAML parse error at " + path +
                             ": Missing required field 'path'");
  }
  if (!node["unit"]) {
    throw std::runtime_error("YAML parse error at " + path +
                             ": Missing required field 'unit'");
  }

  spec.path = node["path"].as<std::string>();
  spec.unit = node["unit"].as<std::string>();
  return spec;
}

// Parse model specification
ModelSpec parse_model(const YAML::Node &node, size_t index,
                      detail::ParamParseBudget &budget) {
  std::string path = "/models/" + std::to_string(index);
  ModelSpec spec;

  if (!node["id"]) {
    throw std::runtime_error("YAML parse error at " + path +
                             ": Missing required field 'id'");
  }
  if (!node["type"]) {
    throw std::runtime_error("YAML parse error at " + path +
                             ": Missing required field 'type'");
  }

  spec.id = node["id"].as<std::string>();
  spec.type = node["type"].as<std::string>();

  if (node["params"]) {
    if (!node["params"].IsMap()) {
      throw std::runtime_error("YAML parse error at " + path +
                               "/params: Expected map");
    }
    for (auto it = node["params"].begin(); it != node["params"].end(); ++it) {
      std::string key = it->first.as<std::string>();
      std::string param_path = path + "/params/" + key;
      spec.params[key] = yaml_to_param_value(it->second, param_path, budget);
    }
  }

  return spec;
}

// Parse rule specification
RuleSpec parse_rule(const YAML::Node &node, size_t index) {
  std::string path = "/rules/" + std::to_string(index);
  RuleSpec spec;

  if (!node["id"]) {
    throw std::runtime_error("YAML parse error at " + path +
                             ": Missing required field 'id'");
  }
  if (!node["condition"]) {
    throw std::runtime_error("YAML parse error at " + path +
                             ": Missing required field 'condition'");
  }

  spec.id = node["id"].as<std::string>();
  spec.condition = node["condition"].as<std::string>();

  // Parse actions array
  if (node["actions"] && node["actions"].IsSequence()) {
    for (size_t i = 0; i < node["actions"].size(); ++i) {
      const YAML::Node &action_node = node["actions"][i];
      std::string action_path = path + "/actions/" + std::to_string(i);

      ActionSpec action;
      if (!action_node["device"]) {
        throw std::runtime_error("YAML parse error at " + action_path +
                                 ": Missing required field 'device'");
      }
      if (!action_node["function"]) {
        throw std::runtime_error("YAML parse error at " + action_path +
                                 ": Missing required field 'function'");
      }

      action.device = action_node["device"].as<std::string>();
      action.function = action_node["function"].as<std::string>();

      if (action_node["args"]) {
        if (!action_node["args"].IsMap()) {
          throw std::runtime_error("YAML parse error at " + action_path +
                                   "/args: Expected map");
        }
        for (auto it = action_node["args"].begin();
             it != action_node["args"].end(); ++it) {
          std::string key = it->first.as<std::string>();
          std::string arg_path = action_path + "/args/" + key;
          action.args[key] = yaml_to_variant(it->second, arg_path);
        }
      }

      spec.actions.push_back(action);
    }
  }

  if (node["on_error"]) {
    spec.on_error = node["on_error"].as<std::string>();
  } else {
    spec.on_error = "log_and_continue";
  }

  return spec;
}

} // anonymous namespace

GraphSpec load_yaml_string(const std::string &yaml_content) {
  GraphSpec spec;
  detail::ParamParseBudget param_budget;

  try {
    YAML::Node root = YAML::Load(yaml_content);

    // Parse signals array
    if (root["signals"] && root["signals"].IsSequence()) {
      size_t index = 0;
      for (const auto &signal_node : root["signals"]) {
        spec.signals.push_back(parse_signal(signal_node, index));
        ++index;
      }
    }

    // Parse edges array
    if (root["edges"] && root["edges"].IsSequence()) {
      size_t index = 0;
      for (const auto &edge_node : root["edges"]) {
        spec.edges.push_back(parse_edge(edge_node, index, param_budget));
        ++index;
      }
    }

    // Parse models array
    if (root["models"] && root["models"].IsSequence()) {
      size_t index = 0;
      for (const auto &model_node : root["models"]) {
        spec.models.push_back(parse_model(model_node, index, param_budget));
        ++index;
      }
    }

    // Parse rules array
    if (root["rules"] && root["rules"].IsSequence()) {
      size_t index = 0;
      for (const auto &rule_node : root["rules"]) {
        spec.rules.push_back(parse_rule(rule_node, index));
        ++index;
      }
    }

  } catch (const YAML::ParserException &e) {
    throw std::runtime_error(format_yaml_error(e.msg, e.mark));
  } catch (const YAML::Exception &e) {
    throw std::runtime_error("YAML error: " + std::string(e.what()));
  }

  return spec;
}

GraphSpec load_yaml_file(const std::string &path) {
  std::ifstream file(path);
  if (!file.is_open()) {
    throw std::runtime_error("Cannot open YAML file: " + path);
  }

  std::stringstream buffer;
  buffer << file.rdbuf();

  try {
    return load_yaml_string(buffer.str());
  } catch (const std::exception &e) {
    throw std::runtime_error("Error loading YAML file '" + path +
                             "': " + e.what());
  }
}

} // namespace fluxgraph::loaders

#endif // FLUXGRAPH_YAML_ENABLED

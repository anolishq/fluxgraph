#ifdef FLUXGRAPH_YAML_ENABLED

#include "fluxgraph/loaders/yaml_loader.hpp"
#include <fstream>
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

ParamValue yaml_to_param_value(const YAML::Node &node, const std::string &path) {
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
    throw std::runtime_error("YAML parse error at " + path +
                             ": Expected scalar value for Variant");
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
    throw std::runtime_error("YAML parse error at " + path +
                             ": Expected scalar value for Variant");
  }
}

// Parse transform specification
TransformSpec parse_transform(const YAML::Node &node,
                              const std::string &base_path) {
  TransformSpec spec;

  std::string path = base_path + "/transform";

  if (!node["type"]) {
    throw std::runtime_error("YAML parse error at " + path +
                             ": Missing required field 'type'");
  }

  spec.type = node["type"].as<std::string>();

  if (node["params"] && node["params"].IsMap()) {
    for (auto it = node["params"].begin(); it != node["params"].end(); ++it) {
      std::string key = it->first.as<std::string>();
      std::string param_path = path + "/params/" + key;
      spec.params[key] = yaml_to_param_value(it->second, param_path);
    }
  }

  return spec;
}

// Parse edge specification
EdgeSpec parse_edge(const YAML::Node &node, size_t index) {
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

  spec.source_path = node["source"].as<std::string>();
  spec.target_path = node["target"].as<std::string>();

  if (node["transform"] && node["transform"].IsMap()) {
    spec.transform = parse_transform(node["transform"], path);
  }

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
ModelSpec parse_model(const YAML::Node &node, size_t index) {
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

  if (node["params"] && node["params"].IsMap()) {
    for (auto it = node["params"].begin(); it != node["params"].end(); ++it) {
      std::string key = it->first.as<std::string>();
      std::string param_path = path + "/params/" + key;
      spec.params[key] = yaml_to_param_value(it->second, param_path);
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

      if (action_node["args"] && action_node["args"].IsMap()) {
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
        spec.edges.push_back(parse_edge(edge_node, index));
        ++index;
      }
    }

    // Parse models array
    if (root["models"] && root["models"].IsSequence()) {
      size_t index = 0;
      for (const auto &model_node : root["models"]) {
        spec.models.push_back(parse_model(model_node, index));
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

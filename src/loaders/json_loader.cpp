#ifdef FLUXGRAPH_JSON_ENABLED

#include "fluxgraph/loaders/json_loader.hpp"
#include <fstream>
#include <nlohmann/json.hpp>
#include <stdexcept>

using json = nlohmann::json;

namespace fluxgraph::loaders {

namespace {

ParamValue json_to_param_value(const json &j, const std::string &path) {
  if (j.is_number_float()) {
    return j.get<double>();
  } else if (j.is_number_integer()) {
    return j.get<int64_t>();
  } else if (j.is_boolean()) {
    return j.get<bool>();
  } else if (j.is_string()) {
    return j.get<std::string>();
  } else {
    throw std::runtime_error("JSON parse error at " + path +
                             ": Unsupported type for Variant");
  }
}

// Convert JSON value to Variant
Variant json_to_variant(const json &j, const std::string &path) {
  if (j.is_number_float()) {
    return j.get<double>();
  } else if (j.is_number_integer()) {
    return j.get<int64_t>();
  } else if (j.is_boolean()) {
    return j.get<bool>();
  } else if (j.is_string()) {
    return j.get<std::string>();
  } else {
    throw std::runtime_error("JSON parse error at " + path +
                             ": Unsupported type for Variant");
  }
}

// Parse transform specification
TransformSpec parse_transform(const json &j, const std::string &base_path) {
  TransformSpec spec;

  std::string path = base_path + "/transform";

  if (!j.contains("type")) {
    throw std::runtime_error("JSON parse error at " + path +
                             ": Missing required field 'type'");
  }

  spec.type = j["type"].get<std::string>();

  if (j.contains("params") && j["params"].is_object()) {
    for (auto &[key, value] : j["params"].items()) {
      std::string param_path = path + "/params/" + key;
      spec.params[key] = json_to_param_value(value, param_path);
    }
  }

  return spec;
}

SignalSpec parse_signal(const json &j, const std::string &base_path,
                        size_t index) {
  const std::string path = base_path + "/" + std::to_string(index);
  SignalSpec spec;

  if (!j.contains("path")) {
    throw std::runtime_error("JSON parse error at " + path +
                             ": Missing required field 'path'");
  }
  if (!j.contains("unit")) {
    throw std::runtime_error("JSON parse error at " + path +
                             ": Missing required field 'unit'");
  }

  spec.path = j["path"].get<std::string>();
  spec.unit = j["unit"].get<std::string>();
  return spec;
}

// Parse edge specification
EdgeSpec parse_edge(const json &j, const std::string &base_path, size_t index) {
  EdgeSpec spec;

  std::string path = base_path + "/" + std::to_string(index);

  if (!j.contains("source")) {
    throw std::runtime_error("JSON parse error at " + path +
                             ": Missing required field 'source'");
  }
  if (!j.contains("target")) {
    throw std::runtime_error("JSON parse error at " + path +
                             ": Missing required field 'target'");
  }
  if (!j.contains("transform")) {
    throw std::runtime_error("JSON parse error at " + path +
                             ": Missing required field 'transform'");
  }

  spec.source_path = j["source"].get<std::string>();
  spec.target_path = j["target"].get<std::string>();
  spec.transform = parse_transform(j["transform"], path);

  return spec;
}

// Parse model specification
ModelSpec parse_model(const json &j, const std::string &base_path,
                      size_t index) {
  ModelSpec spec;

  std::string path = base_path + "/" + std::to_string(index);

  if (!j.contains("id")) {
    throw std::runtime_error("JSON parse error at " + path +
                             ": Missing required field 'id'");
  }
  if (!j.contains("type")) {
    throw std::runtime_error("JSON parse error at " + path +
                             ": Missing required field 'type'");
  }

  spec.id = j["id"].get<std::string>();
  spec.type = j["type"].get<std::string>();

  if (j.contains("params") && j["params"].is_object()) {
    for (auto &[key, value] : j["params"].items()) {
      std::string param_path = path + "/params/" + key;
      spec.params[key] = json_to_param_value(value, param_path);
    }
  }

  return spec;
}

// Parse rule specification
RuleSpec parse_rule(const json &j, const std::string &base_path, size_t index) {
  RuleSpec spec;

  std::string path = base_path + "/" + std::to_string(index);

  if (!j.contains("id")) {
    throw std::runtime_error("JSON parse error at " + path +
                             ": Missing required field 'id'");
  }
  if (!j.contains("condition")) {
    throw std::runtime_error("JSON parse error at " + path +
                             ": Missing required field 'condition'");
  }

  spec.id = j["id"].get<std::string>();
  spec.condition = j["condition"].get<std::string>();

  // Parse actions array
  if (j.contains("actions") && j["actions"].is_array()) {
    for (size_t i = 0; i < j["actions"].size(); ++i) {
      auto &action_json = j["actions"][i];
      std::string action_path = path + "/actions/" + std::to_string(i);

      ActionSpec action;
      if (!action_json.contains("device")) {
        throw std::runtime_error("JSON parse error at " + action_path +
                                 ": Missing required field 'device'");
      }
      if (!action_json.contains("function")) {
        throw std::runtime_error("JSON parse error at " + action_path +
                                 ": Missing required field 'function'");
      }

      action.device = action_json["device"].get<std::string>();
      action.function = action_json["function"].get<std::string>();

      if (action_json.contains("args") && action_json["args"].is_object()) {
        for (auto &[key, value] : action_json["args"].items()) {
          std::string arg_path = action_path + "/args/" + key;
          action.args[key] = json_to_variant(value, arg_path);
        }
      }

      spec.actions.push_back(action);
    }
  }

  if (j.contains("on_error")) {
    spec.on_error = j["on_error"].get<std::string>();
  } else {
    spec.on_error = "log_and_continue";
  }

  return spec;
}

// Parse complete GraphSpec from JSON
GraphSpec parse_json(const json &j) {
  GraphSpec spec;

  // Parse signals (optional)
  if (j.contains("signals") && j["signals"].is_array()) {
    size_t index = 0;
    for (const auto &signal_json : j["signals"]) {
      spec.signals.push_back(parse_signal(signal_json, "/signals", index++));
    }
  }

  // Parse models (optional)
  if (j.contains("models") && j["models"].is_array()) {
    size_t index = 0;
    for (auto &model_json : j["models"]) {
      spec.models.push_back(parse_model(model_json, "/models", index++));
    }
  }

  // Parse edges (optional)
  if (j.contains("edges") && j["edges"].is_array()) {
    size_t index = 0;
    for (auto &edge_json : j["edges"]) {
      spec.edges.push_back(parse_edge(edge_json, "/edges", index++));
    }
  }

  // Parse rules (optional)
  if (j.contains("rules") && j["rules"].is_array()) {
    size_t index = 0;
    for (auto &rule_json : j["rules"]) {
      spec.rules.push_back(parse_rule(rule_json, "/rules", index++));
    }
  }

  return spec;
}

} // anonymous namespace

GraphSpec load_json_file(const std::string &path) {
  std::ifstream file(path);
  if (!file.is_open()) {
    throw std::runtime_error("Failed to open JSON file: " + path);
  }

  json j;
  try {
    file >> j;
  } catch (const json::parse_error &e) {
    throw std::runtime_error("JSON parse error in file " + path + ": " +
                             e.what());
  }

  return parse_json(j);
}

GraphSpec load_json_string(const std::string &json_content) {
  json j;
  try {
    j = json::parse(json_content);
  } catch (const json::parse_error &e) {
    throw std::runtime_error("JSON parse error: " + std::string(e.what()));
  }

  return parse_json(j);
}

} // namespace fluxgraph::loaders

#endif // FLUXGRAPH_JSON_ENABLED

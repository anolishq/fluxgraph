#include "fluxgraph/viz/dot_emitter.hpp"

#include "fluxgraph/core/types.hpp"
#include <algorithm>
#include <array>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <string_view>
#include <tuple>
#include <type_traits>
#include <utility>

namespace fluxgraph::viz {

namespace {

constexpr std::array<std::string_view, 8> kBuiltinTransformTypes = {
    "linear",      "first_order_lag", "delay",       "noise",
    "saturation",  "deadband",        "rate_limiter", "moving_average"};

struct NodeRecord {
  std::string id;
  std::string label;
  std::string shape;
};

struct EdgeRecord {
  std::string source_id;
  std::string target_id;
  std::string transform_type;
  std::string transform_label;
};

bool is_builtin_transform_type(const std::string &transform_type) {
  return std::find(kBuiltinTransformTypes.begin(), kBuiltinTransformTypes.end(),
                   transform_type) != kBuiltinTransformTypes.end();
}

std::string escape_dot_string(const std::string &value) {
  std::string escaped;
  escaped.reserve(value.size() + 8);
  for (char ch : value) {
    switch (ch) {
    case '\\':
      escaped += "\\\\";
      break;
    case '"':
      escaped += "\\\"";
      break;
    case '\n':
      escaped += "\\n";
      break;
    case '\r':
      escaped += "\\r";
      break;
    case '\t':
      escaped += "\\t";
      break;
    default:
      escaped.push_back(ch);
      break;
    }
  }
  return escaped;
}

std::string quote_dot_string(const std::string &value) {
  return "\"" + escape_dot_string(value) + "\"";
}

std::string variant_to_compact_string(const Variant &value) {
  return std::visit(
      [](const auto &item) -> std::string {
        using T = std::decay_t<decltype(item)>;
        if constexpr (std::is_same_v<T, double>) {
          std::ostringstream stream;
          stream << std::setprecision(17) << item;
          return stream.str();
        } else if constexpr (std::is_same_v<T, int64_t>) {
          return std::to_string(item);
        } else if constexpr (std::is_same_v<T, bool>) {
          return item ? "true" : "false";
        } else {
          return "\"" + escape_dot_string(item) + "\"";
        }
      },
      value);
}

std::string format_transform_label(const TransformSpec &transform) {
  std::string label = transform.type.empty() ? "transform" : transform.type;

  if (transform.params.empty()) {
    return label;
  }

  label.push_back('(');
  bool first = true;
  for (const auto &[key, value] : transform.params) {
    if (!first) {
      label += ", ";
    }
    first = false;
    label += key;
    label.push_back('=');
    label += variant_to_compact_string(value);
  }
  label.push_back(')');

  return label;
}

std::string format_action_label(const ActionSpec &action) {
  std::string label = action.device + "." + action.function + "()";
  if (!action.args.empty()) {
    label += " {";
    bool first = true;
    for (const auto &[key, value] : action.args) {
      if (!first) {
        label += ", ";
      }
      first = false;
      label += key;
      label.push_back('=');
      label += variant_to_compact_string(value);
    }
    label.push_back('}');
  }
  return label;
}

std::string format_rule_label(const RuleSpec &rule) {
  std::string label = "rule: " + rule.id;

  if (!rule.condition.empty()) {
    label += "\nif " + rule.condition;
  }

  if (!rule.actions.empty()) {
    label += "\nactions: ";
    bool first = true;
    for (const auto &action : rule.actions) {
      if (!first) {
        label += "; ";
      }
      first = false;
      label += format_action_label(action);
    }
  }

  return label;
}

std::string emit_attributes(const std::map<std::string, std::string> &attributes) {
  if (attributes.empty()) {
    return {};
  }

  std::ostringstream stream;
  stream << " [";

  bool first = true;
  for (const auto &[key, value] : attributes) {
    if (!first) {
      stream << ", ";
    }
    first = false;
    stream << key << "=" << quote_dot_string(value);
  }

  stream << "]";
  return stream.str();
}

} // namespace

std::vector<std::string>
collect_extension_transform_types(const GraphSpec &spec) {
  std::set<std::string> extension_types;
  for (const auto &edge : spec.edges) {
    if (edge.transform.type.empty()) {
      continue;
    }
    if (!is_builtin_transform_type(edge.transform.type)) {
      extension_types.insert(edge.transform.type);
    }
  }

  return {extension_types.begin(), extension_types.end()};
}

std::string emit_dot(const GraphSpec &spec, const DotEmitOptions &options) {
  std::set<std::string> signal_ids;
  std::vector<EdgeRecord> edges;
  edges.reserve(spec.edges.size());

  for (const auto &edge : spec.edges) {
    const std::string source_id = "signal:" + edge.source_path;
    const std::string target_id = "signal:" + edge.target_path;
    signal_ids.insert(source_id);
    signal_ids.insert(target_id);

    edges.push_back(EdgeRecord{
        source_id,
        target_id,
        edge.transform.type,
        format_transform_label(edge.transform),
    });
  }

  std::vector<NodeRecord> nodes;
  nodes.reserve(signal_ids.size() + spec.models.size() + spec.rules.size());

  for (const auto &signal_id : signal_ids) {
    nodes.push_back(
        NodeRecord{signal_id, signal_id.substr(std::string("signal:").size()),
                   "ellipse"});
  }

  if (options.include_models) {
    for (const auto &model : spec.models) {
      std::string label = "model: " + model.id;
      if (!model.type.empty()) {
        label += "\n" + model.type;
      }
      nodes.push_back(NodeRecord{"model:" + model.id, label, "box"});
    }
  }

  if (options.include_rules) {
    for (const auto &rule : spec.rules) {
      nodes.push_back(
          NodeRecord{"rule:" + rule.id, format_rule_label(rule), "note"});
    }
  }

  std::sort(nodes.begin(), nodes.end(),
            [](const NodeRecord &lhs, const NodeRecord &rhs) {
              return lhs.id < rhs.id;
            });

  std::sort(edges.begin(), edges.end(),
            [](const EdgeRecord &lhs, const EdgeRecord &rhs) {
              return std::tie(lhs.source_id, lhs.target_id, lhs.transform_type,
                              lhs.transform_label) <
                     std::tie(rhs.source_id, rhs.target_id, rhs.transform_type,
                              rhs.transform_label);
            });

  std::ostringstream dot;
  dot << "digraph fluxgraph {\n";
  dot << "  rankdir=\"LR\";\n";

  for (const auto &node : nodes) {
    std::map<std::string, std::string> attributes;
    attributes["label"] = node.label;
    attributes["shape"] = node.shape;
    dot << "  " << quote_dot_string(node.id) << emit_attributes(attributes)
        << ";\n";
  }

  for (const auto &edge : edges) {
    std::map<std::string, std::string> attributes;
    attributes["label"] = edge.transform_label;
    attributes["transform_type"] =
        edge.transform_type.empty() ? "transform" : edge.transform_type;

    dot << "  " << quote_dot_string(edge.source_id) << " -> "
        << quote_dot_string(edge.target_id) << emit_attributes(attributes)
        << ";\n";
  }

  dot << "}\n";
  return dot.str();
}

} // namespace fluxgraph::viz


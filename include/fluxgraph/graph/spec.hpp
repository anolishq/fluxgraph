#pragma once

#include "fluxgraph/core/types.hpp"
#include <map>
#include <string>
#include <vector>

namespace fluxgraph {

/// Explicit signal unit contract in graph definition.
struct SignalSpec {
  std::string path;
  std::string unit;
};

/// POD specification for a transform (protocol-agnostic)
struct TransformSpec {
  std::string type; // "linear", "first_order_lag", "delay", etc.
  std::map<std::string, Variant> params;
};

/// POD specification for a signal edge in the graph
struct EdgeSpec {
  std::string source_path; // e.g., "tempctl0/chamber/power"
  std::string target_path; // e.g., "chamber_air/heating_power"
  TransformSpec transform;
};

/// POD specification for a physics model
struct ModelSpec {
  std::string id;   // e.g., "chamber_air"
  std::string type; // "thermal_mass"
  std::map<std::string, Variant> params;
};

/// POD specification for a rule action
struct ActionSpec {
  std::string device;   // e.g., "tempctl0"
  std::string function; // e.g., "set_power"
  std::map<std::string, Variant> args;
};

/// POD specification for a rule
struct RuleSpec {
  std::string id;                  // Required: unique rule identifier
  std::string condition;           // e.g., "chamber_air/temperature > 100.0"
  std::vector<ActionSpec> actions; // actions array
  std::string on_error;            // e.g., "log_and_continue"
};

/// Complete graph specification (protocol-agnostic POD)
struct GraphSpec {
  std::vector<SignalSpec> signals;
  std::vector<ModelSpec> models;
  std::vector<EdgeSpec> edges;
  std::vector<RuleSpec> rules;
};

} // namespace fluxgraph

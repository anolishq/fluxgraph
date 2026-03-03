#pragma once

#include "fluxgraph/graph/spec.hpp"
#include <string>
#include <vector>

namespace fluxgraph::viz {

struct DotEmitOptions {
  bool include_models = true;
  bool include_rules = true;
};

/// Emit deterministic DOT output for a GraphSpec.
std::string emit_dot(const GraphSpec &spec, const DotEmitOptions &options = {});

/// Return sorted transform types that are not part of the built-in set.
std::vector<std::string> collect_extension_transform_types(const GraphSpec &spec);

} // namespace fluxgraph::viz


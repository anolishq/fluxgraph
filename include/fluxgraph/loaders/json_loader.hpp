#pragma once

#ifndef FLUXGRAPH_JSON_ENABLED
#error "JSON loader requested but FLUXGRAPH_JSON_ENABLED not defined. Build with -DFLUXGRAPH_JSON_ENABLED=ON"
#endif

#include <string>

#include "fluxgraph/graph/spec.hpp"

namespace fluxgraph::loaders {

/// Load GraphSpec from JSON file
/// Throws std::runtime_error on parse errors with JSON pointer path
GraphSpec load_json_file(const std::string &path);

/// Load GraphSpec from JSON string
/// Throws std::runtime_error on parse errors with JSON pointer path
GraphSpec load_json_string(const std::string &json_content);

}  // namespace fluxgraph::loaders

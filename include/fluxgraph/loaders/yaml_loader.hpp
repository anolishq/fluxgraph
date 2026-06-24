#pragma once

#ifndef FLUXGRAPH_YAML_ENABLED
#error "YAML loader requested but FLUXGRAPH_YAML_ENABLED not defined. Build with -DFLUXGRAPH_YAML_ENABLED=ON"
#endif

#include <string>

#include "fluxgraph/graph/spec.hpp"

namespace fluxgraph::loaders {

/**
 * Load GraphSpec from YAML file.
 *
 * @param path Path to YAML file
 * @return GraphSpec Parsed graph specification
 * @throws std::runtime_error If file cannot be read or YAML is invalid
 * (includes line numbers)
 */
GraphSpec load_yaml_file(const std::string &path);

/**
 * Load GraphSpec from YAML string.
 *
 * @param yaml_content YAML string content
 * @return GraphSpec Parsed graph specification
 * @throws std::runtime_error If YAML is invalid (includes line numbers)
 */
GraphSpec load_yaml_string(const std::string &yaml_content);

}  // namespace fluxgraph::loaders

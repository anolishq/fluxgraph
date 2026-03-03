#pragma once

#include "fluxgraph/viz/format.hpp"
#include <string>

namespace fluxgraph::viz {

struct GraphvizRenderRequest {
  std::string dot_binary = "dot";
  std::string dot_input_path;
  std::string output_path;
  OutputFormat output_format = OutputFormat::Svg;
};

struct GraphvizRenderResult {
  bool success = false;
  int process_exit_code = -1;
  std::string command;
  std::string message;
};

std::string build_graphviz_command(const GraphvizRenderRequest &request);
GraphvizRenderResult render_with_graphviz(const GraphvizRenderRequest &request);

} // namespace fluxgraph::viz


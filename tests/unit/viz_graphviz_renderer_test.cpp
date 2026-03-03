#include "fluxgraph/viz/graphviz_renderer.hpp"
#include <gtest/gtest.h>

namespace fluxgraph {
namespace {

TEST(GraphvizRenderer, BuildsQuotedCommand) {
  viz::GraphvizRenderRequest request;
  request.dot_binary = "C:/Program Files/Graphviz/bin/dot.exe";
  request.dot_input_path = "C:/tmp/input graph.dot";
  request.output_path = "C:/tmp/output graph.svg";
  request.output_format = viz::OutputFormat::Svg;

  const std::string command = viz::build_graphviz_command(request);

  EXPECT_NE(command.find("\"C:/Program Files/Graphviz/bin/dot.exe\""),
            std::string::npos);
  EXPECT_NE(command.find(" -Tsvg "), std::string::npos);
  EXPECT_NE(command.find("\"C:/tmp/input graph.dot\""), std::string::npos);
  EXPECT_NE(command.find("\"C:/tmp/output graph.svg\""), std::string::npos);
}

TEST(GraphvizRenderer, RejectsDotOutputFormatForRenderer) {
  viz::GraphvizRenderRequest request;
  request.dot_input_path = "input.dot";
  request.output_path = "output.dot";
  request.output_format = viz::OutputFormat::Dot;

  const auto result = viz::render_with_graphviz(request);
  EXPECT_FALSE(result.success);
  EXPECT_TRUE(result.command.empty());
  EXPECT_NE(result.message.find("svg/png"), std::string::npos);
}

} // namespace
} // namespace fluxgraph


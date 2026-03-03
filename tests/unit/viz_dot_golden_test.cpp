#include "fluxgraph/graph/spec.hpp"
#include "fluxgraph/viz/dot_emitter.hpp"
#include <gtest/gtest.h>

#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>

namespace fluxgraph {
namespace {

std::string normalize_newlines(std::string value) {
  std::string normalized;
  normalized.reserve(value.size());

  for (std::size_t i = 0; i < value.size(); ++i) {
    if (value[i] == '\r' && i + 1 < value.size() && value[i + 1] == '\n') {
      continue;
    }
    normalized.push_back(value[i]);
  }

  return normalized;
}

std::string read_text_file(const std::string &path) {
  std::ifstream stream(path, std::ios::binary);
  if (!stream) {
    throw std::runtime_error("Failed to open file: " + path);
  }

  std::ostringstream buffer;
  buffer << stream.rdbuf();
  return buffer.str();
}

TEST(DotEmitter, MatchesGoldenFixtureForSimpleGraph) {
  GraphSpec spec;

  ModelSpec model;
  model.id = "m0";
  model.type = "thermal_mass";
  spec.models.push_back(model);

  RuleSpec rule;
  rule.id = "rule-1";
  rule.condition = "output.signal > 10";
  spec.rules.push_back(rule);

  EdgeSpec edge;
  edge.source_path = "input.signal";
  edge.target_path = "output.signal";
  edge.transform.type = "linear";
  edge.transform.params["offset"] = 1.0;
  edge.transform.params["scale"] = 2.0;
  spec.edges.push_back(edge);

  const std::string emitted = normalize_newlines(viz::emit_dot(spec));
  const std::string golden = normalize_newlines(
      read_text_file(std::string(FLUXGRAPH_SOURCE_DIR) +
                     "/tests/golden/viz_simple_graph.dot"));

  EXPECT_EQ(emitted, golden);
}

} // namespace
} // namespace fluxgraph


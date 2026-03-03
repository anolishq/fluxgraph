#include "fluxgraph/graph/spec.hpp"
#include "fluxgraph/viz/dot_emitter.hpp"
#include <gtest/gtest.h>

#include <string>

namespace fluxgraph {
namespace {

TEST(DotEmitter, EmitsDeterministicNodeAndEdgeOrder) {
  GraphSpec spec;

  EdgeSpec edge_b_to_a;
  edge_b_to_a.source_path = "b/signal";
  edge_b_to_a.target_path = "a/signal";
  edge_b_to_a.transform.type = "custom_ext";
  edge_b_to_a.transform.params["note"] = std::string("value");
  spec.edges.push_back(edge_b_to_a);

  EdgeSpec edge_a_to_c;
  edge_a_to_c.source_path = "a/signal";
  edge_a_to_c.target_path = "c.signal";
  edge_a_to_c.transform.type = "linear";
  edge_a_to_c.transform.params["offset"] = 1.0;
  edge_a_to_c.transform.params["scale"] = 2.0;
  spec.edges.push_back(edge_a_to_c);

  const std::string dot = viz::emit_dot(spec);

  const std::size_t node_a_pos = dot.find("\"signal:a/signal\"");
  const std::size_t node_b_pos = dot.find("\"signal:b/signal\"");
  const std::size_t node_c_pos = dot.find("\"signal:c.signal\"");

  ASSERT_NE(node_a_pos, std::string::npos);
  ASSERT_NE(node_b_pos, std::string::npos);
  ASSERT_NE(node_c_pos, std::string::npos);
  EXPECT_LT(node_a_pos, node_b_pos);
  EXPECT_LT(node_b_pos, node_c_pos);

  const std::size_t edge_a_to_c_pos =
      dot.find("\"signal:a/signal\" -> \"signal:c.signal\"");
  const std::size_t edge_b_to_a_pos =
      dot.find("\"signal:b/signal\" -> \"signal:a/signal\"");

  ASSERT_NE(edge_a_to_c_pos, std::string::npos);
  ASSERT_NE(edge_b_to_a_pos, std::string::npos);
  EXPECT_LT(edge_a_to_c_pos, edge_b_to_a_pos);
}

TEST(DotEmitter, EscapesSpecialCharactersInLabels) {
  GraphSpec spec;

  EdgeSpec edge;
  edge.source_path = "src/with\"quote";
  edge.target_path = "dst\\with\\slash";
  edge.transform.type = "linear";
  edge.transform.params["description"] = std::string("line1\nline2");
  spec.edges.push_back(edge);

  const std::string dot = viz::emit_dot(spec);

  EXPECT_NE(dot.find("\\\"quote"), std::string::npos);
  EXPECT_NE(dot.find("\\\\with\\\\slash"), std::string::npos);
  EXPECT_NE(dot.find("line1\\\\nline2"), std::string::npos);
}

TEST(DotEmitter, ReportsExtensionTransformTypesSortedAndUnique) {
  GraphSpec spec;

  EdgeSpec edge_alpha;
  edge_alpha.source_path = "a";
  edge_alpha.target_path = "b";
  edge_alpha.transform.type = "zeta_transform";
  spec.edges.push_back(edge_alpha);

  EdgeSpec edge_beta;
  edge_beta.source_path = "b";
  edge_beta.target_path = "c";
  edge_beta.transform.type = "alpha_transform";
  spec.edges.push_back(edge_beta);

  EdgeSpec edge_duplicate;
  edge_duplicate.source_path = "c";
  edge_duplicate.target_path = "d";
  edge_duplicate.transform.type = "zeta_transform";
  spec.edges.push_back(edge_duplicate);

  const auto extension_types = viz::collect_extension_transform_types(spec);

  ASSERT_EQ(extension_types.size(), 2U);
  EXPECT_EQ(extension_types[0], "alpha_transform");
  EXPECT_EQ(extension_types[1], "zeta_transform");
}

TEST(DotEmitter, CanExcludeModelAndRuleAnnotationNodes) {
  GraphSpec spec;

  ModelSpec model;
  model.id = "chamber";
  model.type = "thermal_mass";
  spec.models.push_back(model);

  RuleSpec rule;
  rule.id = "r1";
  rule.condition = "a > 1";
  spec.rules.push_back(rule);

  viz::DotEmitOptions options;
  options.include_models = false;
  options.include_rules = false;

  const std::string dot = viz::emit_dot(spec, options);

  EXPECT_EQ(dot.find("\"model:chamber\""), std::string::npos);
  EXPECT_EQ(dot.find("\"rule:r1\""), std::string::npos);
}

} // namespace
} // namespace fluxgraph

#pragma once

#include <memory>
#include <vector>

#include "fluxgraph/graph/compiler.hpp"

namespace fluxgraph::compiler_internal {

void topological_sort_edges(std::vector<CompiledEdge> &edges);
void detect_cycles_in_non_delay_subgraph(const std::vector<CompiledEdge> &edges);
void validate_model_stability_limits(const std::vector<std::unique_ptr<IModel>> &models, double expected_dt);

}  // namespace fluxgraph::compiler_internal

#include "algorithms.hpp"

#include <algorithm>
#include <functional>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>

namespace fluxgraph::compiler_internal {

void topological_sort_edges(std::vector<CompiledEdge> &edges) {
    std::vector<size_t> delay_indices;
    std::vector<size_t> immediate_indices;
    delay_indices.reserve(edges.size());
    immediate_indices.reserve(edges.size());

    for (size_t i = 0; i < edges.size(); ++i) {
        if (edges[i].is_delay) {
            delay_indices.push_back(i);
        } else {
            immediate_indices.push_back(i);
        }
    }

    std::map<SignalId, std::vector<size_t>> outgoing;
    std::map<SignalId, int> in_degree;
    std::set<SignalId> all_signals;

    for (size_t idx : immediate_indices) {
        all_signals.insert(edges[idx].source);
        all_signals.insert(edges[idx].target);
        outgoing[edges[idx].source].push_back(idx);
        in_degree[edges[idx].target]++;
    }

    std::set<SignalId> ready;
    for (SignalId sig : all_signals) {
        if (in_degree[sig] == 0) {
            ready.insert(sig);
        }
    }

    std::vector<size_t> sorted_immediate_indices;
    sorted_immediate_indices.reserve(immediate_indices.size());
    std::set<size_t> processed_edges;

    while (!ready.empty()) {
        SignalId sig = *ready.begin();
        ready.erase(ready.begin());

        auto it = outgoing.find(sig);
        if (it == outgoing.end()) {
            continue;
        }

        for (size_t idx : it->second) {
            if (!processed_edges.insert(idx).second) {
                continue;
            }
            sorted_immediate_indices.push_back(idx);
            if (--in_degree[edges[idx].target] == 0) {
                ready.insert(edges[idx].target);
            }
        }
    }

    if (sorted_immediate_indices.size() != immediate_indices.size()) {
        throw std::runtime_error("GraphCompiler: topological sort failed for non-delay edges.");
    }

    std::vector<CompiledEdge> sorted;
    sorted.reserve(edges.size());

    for (size_t idx : delay_indices) {
        sorted.push_back(std::move(edges[idx]));
    }

    for (size_t idx : sorted_immediate_indices) {
        sorted.push_back(std::move(edges[idx]));
    }

    edges = std::move(sorted);
}

void detect_cycles_in_non_delay_subgraph(const std::vector<CompiledEdge> &edges) {
    std::map<SignalId, std::vector<SignalId>> graph;
    for (const auto &edge : edges) {
        if (edge.is_delay) {
            continue;
        }
        graph[edge.source].push_back(edge.target);
        if (graph.count(edge.target) == 0) {
            graph[edge.target] = {};
        }
    }

    std::map<SignalId, int> state;
    std::vector<SignalId> stack;
    std::vector<SignalId> cycle_path;
    bool found_cycle = false;

    std::function<void(SignalId)> dfs = [&](SignalId node) {
        if (found_cycle) {
            return;
        }

        state[node] = 1;
        stack.push_back(node);

        for (SignalId neighbor : graph[node]) {
            if (state[neighbor] == 0) {
                dfs(neighbor);
                if (found_cycle) {
                    return;
                }
            } else if (state[neighbor] == 1) {
                auto start_it = std::find(stack.begin(), stack.end(), neighbor);
                cycle_path.assign(start_it, stack.end());
                cycle_path.push_back(neighbor);
                found_cycle = true;
                return;
            }
        }

        stack.pop_back();
        state[node] = 2;
    };

    for (const auto &[node, _] : graph) {
        if (state[node] == 0) {
            dfs(node);
        }
        if (found_cycle) {
            break;
        }
    }

    if (found_cycle) {
        std::ostringstream oss;
        oss << "GraphCompiler: Cycle detected in non-delay subgraph: ";
        for (size_t i = 0; i < cycle_path.size(); ++i) {
            if (i > 0) {
                oss << " -> ";
            }
            oss << cycle_path[i];
        }
        oss << ". Add a delay edge in feedback path.";
        throw std::runtime_error(oss.str());
    }
}

void validate_model_stability_limits(const std::vector<std::unique_ptr<IModel>> &models, double expected_dt) {
    for (const auto &model : models) {
        double limit = model->compute_stability_limit();
        if (expected_dt > limit) {
            std::ostringstream oss;
            oss << "Stability violation: " << model->describe() << " requires dt < " << limit
                << "s, but dt = " << expected_dt << "s";
            throw std::runtime_error(oss.str());
        }
    }
}

}  // namespace fluxgraph::compiler_internal

#ifdef FLUXGRAPH_YAML_ENABLED

#include <chrono>
#include <iostream>
#include <sstream>

#include "fluxgraph/loaders/yaml_loader.hpp"

using namespace fluxgraph::loaders;
using namespace std::chrono;

// Generate YAML for a graph with N edges and M models
std::string generate_yaml_graph(int num_edges, int num_models) {
    std::ostringstream oss;

    oss << "models:\n";
    for (int i = 0; i < num_models; ++i) {
        oss << "  - id: model_" << i << "\n";
        oss << "    type: thermal_mass\n";
        oss << "    params:\n";
        oss << "      temp_signal: model_" << i << ".temp\n";
        oss << "      power_signal: model_" << i << ".power\n";
        oss << "      ambient_signal: ambient.temp\n";
        oss << "      thermal_mass: 1000.0\n";
        oss << "      heat_transfer_coeff: 10.0\n";
        oss << "      initial_temp: 25.0\n";
    }

    oss << "edges:\n";
    for (int i = 0; i < num_edges; ++i) {
        oss << "  - source: signal_" << i << ".input\n";
        oss << "    target: signal_" << i << ".output\n";
        oss << "    transform:\n";
        oss << "      type: linear\n";
        oss << "      params:\n";
        oss << "        scale: 1.0\n";
        oss << "        offset: 0.0\n";
    }

    return oss.str();
}

void benchmark_yaml_loader(const std::string &name, const std::string &yaml, int iterations) {
    auto start = high_resolution_clock::now();

    for (int i = 0; i < iterations; ++i) {
        auto spec = load_yaml_string(yaml);
        (void)spec;  // Prevent optimization
    }

    auto end = high_resolution_clock::now();
    auto duration = duration_cast<microseconds>(end - start);

    double avg_us = static_cast<double>(duration.count()) / iterations;
    double avg_ms = avg_us / 1000.0;

    std::cout << name << ":\n";
    std::cout << "  Iterations: " << iterations << "\n";
    std::cout << "  Total time: " << duration.count() << " us\n";
    std::cout << "  Average: " << avg_us << " us (" << avg_ms << " ms)\n\n";
}

int main() {
    std::cout << "=== YAML Loader Benchmarks ===\n\n";

    // Small graph: 10 edges, 2 models
    std::string small_yaml = generate_yaml_graph(10, 2);
    benchmark_yaml_loader("Small graph (10 edges, 2 models)", small_yaml, 10000);

    // Medium graph: 100 edges, 10 models
    std::string medium_yaml = generate_yaml_graph(100, 10);
    benchmark_yaml_loader("Medium graph (100 edges, 10 models)", medium_yaml, 1000);

    // Large graph: 1000 edges, 50 models
    std::string large_yaml = generate_yaml_graph(1000, 50);
    benchmark_yaml_loader("Large graph (1000 edges, 50 models)", large_yaml, 100);

    std::cout << "All YAML loader benchmarks complete.\n";

    return 0;
}

#else

#include <iostream>

int main() {
    std::cout << "YAML loader not enabled. Rebuild with -DFLUXGRAPH_YAML_ENABLED=ON\n";
    return 0;
}

#endif  // FLUXGRAPH_YAML_ENABLED

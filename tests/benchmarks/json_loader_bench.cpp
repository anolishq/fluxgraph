#ifdef FLUXGRAPH_JSON_ENABLED

#include <chrono>
#include <iostream>
#include <sstream>

#include "fluxgraph/loaders/json_loader.hpp"

using namespace fluxgraph::loaders;
using namespace std::chrono;

// Generate JSON for a graph with N edges and M models
std::string generate_json_graph(int num_edges, int num_models) {
    std::ostringstream oss;
    oss << "{\n";
    oss << "  \"models\": [\n";

    for (int i = 0; i < num_models; ++i) {
        oss << "    {\n";
        oss << "      \"id\": \"model_" << i << "\",\n";
        oss << "      \"type\": \"thermal_mass\",\n";
        oss << "      \"params\": {\n";
        oss << "        \"temp_signal\": \"model_" << i << ".temp\",\n";
        oss << "        \"power_signal\": \"model_" << i << ".power\",\n";
        oss << "        \"ambient_signal\": \"ambient.temp\",\n";
        oss << "        \"thermal_mass\": 1000.0,\n";
        oss << "        \"heat_transfer_coeff\": 10.0,\n";
        oss << "        \"initial_temp\": 25.0\n";
        oss << "      }\n";
        oss << "    }";
        if (i < num_models - 1) oss << ",";
        oss << "\n";
    }

    oss << "  ],\n";
    oss << "  \"edges\": [\n";

    for (int i = 0; i < num_edges; ++i) {
        oss << "    {\n";
        oss << "      \"source\": \"signal_" << i << ".input\",\n";
        oss << "      \"target\": \"signal_" << i << ".output\",\n";
        oss << "      \"transform\": {\n";
        oss << "        \"type\": \"linear\",\n";
        oss << "        \"params\": {\n";
        oss << "          \"scale\": 1.0,\n";
        oss << "          \"offset\": 0.0\n";
        oss << "        }\n";
        oss << "      }\n";
        oss << "    }";
        if (i < num_edges - 1) oss << ",";
        oss << "\n";
    }

    oss << "  ]\n";
    oss << "}\n";

    return oss.str();
}

void benchmark_json_loader(const std::string &name, const std::string &json, int iterations) {
    auto start = high_resolution_clock::now();

    for (int i = 0; i < iterations; ++i) {
        auto spec = load_json_string(json);
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
    std::cout << "=== JSON Loader Benchmarks ===\n\n";

    // Small graph: 10 edges, 2 models
    std::string small_json = generate_json_graph(10, 2);
    benchmark_json_loader("Small graph (10 edges, 2 models)", small_json, 10000);

    // Medium graph: 100 edges, 10 models
    std::string medium_json = generate_json_graph(100, 10);
    benchmark_json_loader("Medium graph (100 edges, 10 models)", medium_json, 1000);

    // Large graph: 1000 edges, 50 models
    std::string large_json = generate_json_graph(1000, 50);
    benchmark_json_loader("Large graph (1000 edges, 50 models)", large_json, 100);

    std::cout << "All JSON loader benchmarks complete.\n";

    return 0;
}

#else

#include <iostream>

int main() {
    std::cout << "JSON loader not enabled. Rebuild with -DFLUXGRAPH_JSON_ENABLED=ON\n";
    return 0;
}

#endif  // FLUXGRAPH_JSON_ENABLED

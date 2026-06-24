#include <chrono>
#include <iostream>
#include <string>
#include <vector>

#include "fluxgraph/core/namespace.hpp"

using namespace fluxgraph;
using namespace std::chrono;

void benchmark_namespace_intern() {
    SignalNamespace ns;

    const int num_interns = 10000;
    std::vector<std::string> paths;
    paths.reserve(num_interns);

    // Generate unique paths
    for (int i = 0; i < num_interns; ++i) {
        paths.push_back("device" + std::to_string(i / 100) + ".signal" + std::to_string(i));
    }

    auto start = high_resolution_clock::now();

    for (const auto &path : paths) {
        ns.intern(path);
    }

    auto end = high_resolution_clock::now();
    auto duration_ms = duration_cast<milliseconds>(end - start).count();

    std::cout << "Namespace Intern:\n";
    std::cout << "  Operations: " << num_interns << "\n";
    std::cout << "  Duration:   " << duration_ms << " ms\n";
    std::cout << "  Target:     <5ms\n";
    std::cout << "  Status:     " << (duration_ms < 5 ? "PASS" : "FAIL") << "\n\n";
}

void benchmark_namespace_resolve() {
    SignalNamespace ns;

    const int num_signals = 10000;
    std::vector<std::string> paths;

    // Setup: intern signals
    for (int i = 0; i < num_signals; ++i) {
        std::string path = "device" + std::to_string(i / 100) + ".signal" + std::to_string(i);
        paths.push_back(path);
        ns.intern(path);
    }

    // Benchmark: resolve
    auto start = high_resolution_clock::now();

    SignalId sum = 0;
    for (const auto &path : paths) {
        sum += ns.resolve(path);
    }

    auto end = high_resolution_clock::now();
    auto duration_ms = duration_cast<milliseconds>(end - start).count();

    std::cout << "Namespace Resolve:\n";
    std::cout << "  Operations: " << num_signals << "\n";
    std::cout << "  Duration:   " << duration_ms << " ms\n";
    std::cout << "  Target:     <2ms\n";
    std::cout << "  Status:     " << (duration_ms < 2 ? "PASS" : "FAIL") << "\n";
    std::cout << "  (sum=" << sum << " to prevent optimization)\n\n";
}

int main() {
    std::cout << "FluxGraph Namespace Benchmarks\n";
    std::cout << "===============================\n\n";

    benchmark_namespace_intern();
    benchmark_namespace_resolve();

    return 0;
}

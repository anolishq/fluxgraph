#include <chrono>
#include <iomanip>
#include <iostream>

#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/core/signal_store.hpp"

using namespace fluxgraph;
using namespace std::chrono;

void benchmark_signal_store_reads() {
    SignalStore store;
    SignalNamespace ns;

    // Setup: intern 1000 signals
    std::vector<SignalId> signal_ids;
    for (int i = 0; i < 1000; ++i) {
        std::string path = "device" + std::to_string(i / 10) + ".signal" + std::to_string(i % 10);
        SignalId id = ns.intern(path);
        store.write(id, static_cast<double>(i), "V");
        signal_ids.push_back(id);
    }

    // Benchmark: 1M reads
    const int num_reads = 1000000;
    auto start = high_resolution_clock::now();

    double sum = 0.0;
    for (int i = 0; i < num_reads; ++i) {
        sum += store.read_value(signal_ids[i % 1000]);
    }

    auto end = high_resolution_clock::now();
    auto duration_ms = duration_cast<milliseconds>(end - start).count();

    std::cout << "SignalStore Reads:\n";
    std::cout << "  Operations: " << num_reads << "\n";
    std::cout << "  Duration:   " << duration_ms << " ms\n";
    std::cout << "  Throughput: " << (num_reads / duration_ms) << " kOps/s\n";
    std::cout << "  Target:     <10ms (100 kOps/s)\n";
    std::cout << "  Status:     " << (duration_ms < 10 ? "PASS" : "FAIL") << "\n";
    std::cout << "  (sum=" << sum << " to prevent optimization)\n\n";
}

void benchmark_signal_store_writes() {
    SignalStore store;
    SignalNamespace ns;

    // Setup: intern 1000 signals
    std::vector<SignalId> signal_ids;
    for (int i = 0; i < 1000; ++i) {
        std::string path = "device" + std::to_string(i / 10) + ".signal" + std::to_string(i % 10);
        signal_ids.push_back(ns.intern(path));
    }

    // Benchmark: 1M writes
    const int num_writes = 1000000;
    auto start = high_resolution_clock::now();

    for (int i = 0; i < num_writes; ++i) {
        store.write(signal_ids[i % 1000], static_cast<double>(i), "V");
    }

    auto end = high_resolution_clock::now();
    auto duration_ms = duration_cast<milliseconds>(end - start).count();

    std::cout << "SignalStore Writes:\n";
    std::cout << "  Operations: " << num_writes << "\n";
    std::cout << "  Duration:   " << duration_ms << " ms\n";
    std::cout << "  Throughput: " << (num_writes / duration_ms) << " kOps/s\n";
    std::cout << "  Target:     <15ms (67 kOps/s)\n";
    std::cout << "  Status:     " << (duration_ms < 15 ? "PASS" : "FAIL") << "\n\n";
}

int main() {
    std::cout << "FluxGraph Performance Benchmarks\n";
    std::cout << "=================================\n\n";

    benchmark_signal_store_reads();
    benchmark_signal_store_writes();

    return 0;
}

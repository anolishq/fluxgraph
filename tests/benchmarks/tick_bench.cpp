#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/core/signal_store.hpp"
#include "fluxgraph/engine.hpp"
#include "fluxgraph/graph/compiler.hpp"
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <new>

using namespace fluxgraph;
using namespace std::chrono;

namespace {
std::atomic<bool> g_count_allocations{false};
std::atomic<std::uint64_t> g_allocation_count{0};

class AllocationCountScope {
public:
  AllocationCountScope() {
    g_allocation_count.store(0, std::memory_order_relaxed);
    g_count_allocations.store(true, std::memory_order_relaxed);
  }

  std::uint64_t stop() {
    g_count_allocations.store(false, std::memory_order_relaxed);
    return g_allocation_count.load(std::memory_order_relaxed);
  }
};
} // namespace

void *operator new(std::size_t size) {
  if (size == 0) {
    size = 1;
  }
  if (void *ptr = std::malloc(size)) {
    if (g_count_allocations.load(std::memory_order_relaxed)) {
      g_allocation_count.fetch_add(1, std::memory_order_relaxed);
    }
    return ptr;
  }
  throw std::bad_alloc();
}

void *operator new[](std::size_t size) {
  if (size == 0) {
    size = 1;
  }
  if (void *ptr = std::malloc(size)) {
    if (g_count_allocations.load(std::memory_order_relaxed)) {
      g_allocation_count.fetch_add(1, std::memory_order_relaxed);
    }
    return ptr;
  }
  throw std::bad_alloc();
}

void *operator new(std::size_t size, const std::nothrow_t &) noexcept {
  try {
    return ::operator new(size);
  } catch (...) {
    return nullptr;
  }
}

void *operator new[](std::size_t size, const std::nothrow_t &) noexcept {
  try {
    return ::operator new[](size);
  } catch (...) {
    return nullptr;
  }
}

void operator delete(void *ptr) noexcept { std::free(ptr); }
void operator delete[](void *ptr) noexcept { std::free(ptr); }
void operator delete(void *ptr, std::size_t) noexcept { std::free(ptr); }
void operator delete[](void *ptr, std::size_t) noexcept { std::free(ptr); }

void benchmark_simple_graph() {
  // Simple graph: 10 signals, 5 edges, 1 model
  SignalNamespace sig_ns;
  FunctionNamespace func_ns;
  SignalStore store;

  GraphSpec spec;

  // Add 5 edges with transforms
  for (int i = 0; i < 5; ++i) {
    EdgeSpec edge;
    edge.source_path = "sensor" + std::to_string(i) + ".input";
    edge.target_path = "sensor" + std::to_string(i) + ".output";
    edge.transform.type = "linear";
    edge.transform.params["scale"] = 2.0;
    edge.transform.params["offset"] = 1.0;
    spec.edges.push_back(edge);
  }

  // Add 1 thermal mass model
  ModelSpec model;
  model.id = "thermal1";
  model.type = "thermal_mass";
  model.params["temp_signal"] = std::string("chamber.temperature");
  model.params["power_signal"] = std::string("chamber.power");
  model.params["ambient_signal"] = std::string("chamber.ambient");
  model.params["thermal_mass"] = 1000.0;
  model.params["heat_transfer_coeff"] = 10.0;
  model.params["initial_temp"] = 25.0;
  spec.models.push_back(model);

  GraphCompiler compiler;
  auto program = compiler.compile(spec, sig_ns, func_ns);

  Engine engine;
  engine.load(std::move(program));

  // Initialize signals
  for (int i = 0; i < 5; ++i) {
    auto id = sig_ns.resolve("sensor" + std::to_string(i) + ".input");
    store.write(id, 1.0, "V");
  }
  store.write(sig_ns.resolve("chamber.power"), 100.0, "W");
  store.write(sig_ns.resolve("chamber.ambient"), 20.0, "degC");

  // Warm up
  for (int i = 0; i < 100; ++i) {
    engine.tick(0.1, store);
  }

  // Benchmark: 1000 ticks
  const int num_ticks = 1000;
  AllocationCountScope alloc_scope;
  auto start = high_resolution_clock::now();

  for (int i = 0; i < num_ticks; ++i) {
    engine.tick(0.1, store);
  }

  auto end = high_resolution_clock::now();
  std::uint64_t allocations = alloc_scope.stop();
  auto duration_us = duration_cast<microseconds>(end - start).count();
  double avg_us = static_cast<double>(duration_us) / num_ticks;
  double allocs_per_tick =
      static_cast<double>(allocations) / static_cast<double>(num_ticks);

  std::cout << "Simple Graph (10 signals, 5 edges, 1 model):\n";
  std::cout << "  Ticks:      " << num_ticks << "\n";
  std::cout << "  Duration:   " << duration_us << " us\n";
  std::cout << "  Avg/tick:   " << avg_us << " us\n";
  std::cout << "  Target:     <1000 us (1 ms) [latency]\n";
  std::cout << "  Status:     " << (avg_us < 1000 ? "PASS" : "FAIL") << "\n\n";
  std::cout << "  Allocations: " << allocations << "\n";
  std::cout << "  Alloc/tick:  " << allocs_per_tick << "\n";
  std::cout << "  Target:      0 allocations/tick [memory]\n";
  std::cout << "  Status:      " << (allocations == 0 ? "PASS" : "FAIL")
            << "\n\n";
}

void benchmark_complex_graph() {
  // Complex graph: 1000 signals, 500 edges, 10 models
  SignalNamespace sig_ns;
  FunctionNamespace func_ns;
  SignalStore store;

  GraphSpec spec;

  // Add 500 edges
  for (int i = 0; i < 500; ++i) {
    EdgeSpec edge;
    edge.source_path = "node" + std::to_string(i) + ".output";
    edge.target_path = "node" + std::to_string(i + 500) + ".input";
    edge.transform.type = "linear";
    edge.transform.params["scale"] = 1.0;
    edge.transform.params["offset"] = 0.0;
    spec.edges.push_back(edge);
  }

  // Add 10 thermal mass models
  for (int i = 0; i < 10; ++i) {
    ModelSpec model;
    model.id = "thermal" + std::to_string(i);
    model.type = "thermal_mass";
    model.params["temp_signal"] =
        std::string("chamber" + std::to_string(i) + ".temp");
    model.params["power_signal"] =
        std::string("chamber" + std::to_string(i) + ".power");
    model.params["ambient_signal"] = std::string("ambient");
    model.params["thermal_mass"] = 1000.0;
    model.params["heat_transfer_coeff"] = 10.0;
    model.params["initial_temp"] = 25.0;
    spec.models.push_back(model);
  }

  GraphCompiler compiler;
  auto program = compiler.compile(spec, sig_ns, func_ns);

  Engine engine;
  engine.load(std::move(program));

  // Initialize signals
  for (int i = 0; i < 500; ++i) {
    auto id = sig_ns.resolve("node" + std::to_string(i) + ".output");
    store.write(id, 1.0, "V");
  }
  for (int i = 0; i < 10; ++i) {
    store.write(sig_ns.resolve("chamber" + std::to_string(i) + ".power"), 100.0,
                "W");
  }
  store.write(sig_ns.resolve("ambient"), 20.0, "degC");

  // Warm up
  for (int i = 0; i < 10; ++i) {
    engine.tick(0.1, store);
  }

  // Benchmark: 100 ticks (fewer for complex graph)
  const int num_ticks = 100;
  AllocationCountScope alloc_scope;
  auto start = high_resolution_clock::now();

  for (int i = 0; i < num_ticks; ++i) {
    engine.tick(0.1, store);
  }

  auto end = high_resolution_clock::now();
  std::uint64_t allocations = alloc_scope.stop();
  auto duration_us = duration_cast<microseconds>(end - start).count();
  double avg_us = static_cast<double>(duration_us) / num_ticks;
  double allocs_per_tick =
      static_cast<double>(allocations) / static_cast<double>(num_ticks);

  std::cout << "Complex Graph (1000 signals, 500 edges, 10 models):\n";
  std::cout << "  Ticks:      " << num_ticks << "\n";
  std::cout << "  Duration:   " << duration_us << " us\n";
  std::cout << "  Avg/tick:   " << avg_us << " us\n";
  std::cout << "  Target:     <10000 us (10 ms) [latency]\n";
  std::cout << "  Status:     " << (avg_us < 10000 ? "PASS" : "FAIL") << "\n\n";
  std::cout << "  Allocations: " << allocations << "\n";
  std::cout << "  Alloc/tick:  " << allocs_per_tick << "\n";
  std::cout << "  Target:      0 allocations/tick [memory]\n";
  std::cout << "  Status:      " << (allocations == 0 ? "PASS" : "FAIL")
            << "\n\n";
}

int main() {
  std::cout << "FluxGraph Tick Performance Benchmarks\n";
  std::cout << "======================================\n\n";

  benchmark_simple_graph();
  benchmark_complex_graph();

  return 0;
}

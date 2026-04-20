# Architecture

## Overview

FluxGraph is a deterministic signal processing library designed for real-time simulation. This document explains the key architectural decisions, execution model, and design principles.

## Design Goals

1. **Determinism** - Same inputs always produce same outputs
2. **Performance** - Low overhead for real-time execution (<10ms ticks)
3. **Modularity** - Easy to add transforms/models
4. **Zero Dependencies** - Pure C++17, no external libs
5. **Type Safety** - Strong typing, compile-time checks where possible

## Core Architecture

### Signal-Centric Design

All data flows through signals identified by integer handles (SignalId):

```
[External Input] -> SignalStore -> [Graph Processing] -> SignalStore -> [External Output]
```

**Benefits:**

- Fast lookups (array indexing, not map searches)
- Simple synchronization (snapshot-based)
- Clear data ownership (SignalStore is single source of truth)

### Three-Layer Model

```
+------------------+
|   Application    |  User code sets inputs, reads outputs
+------------------+
         |
+------------------+
|     Engine       |  Orchestrates execution
+------------------+
         |
+------------------+
|   Graph Layer    |  Transforms, Models, Rules
+------------------+
         |
+------------------+
|   SignalStore    |  Central data repository
+------------------+
```

**Layer responsibilities:**

- **Application:** Drives ticks, manages time
- **Engine:** Executes five-stage pipeline, manages execution state
- **Graph:** Implements data flow logic (transforms, physics)
- **SignalStore:** Holds current simulation state

---

## Five-Stage Tick Execution

Each `engine.tick(dt, store)` executes five sequential stages:

### Stage 1: Pre-Tick Snapshot

```cpp
snapshot = store.snapshot();
```

**Purpose:** Create consistent read view of all signals

**Why?** Without snapshot, transforms/models would see partially-updated values during execution, breaking determinism. Example problem:

```
Transform A: output1 = input1 * 2
Transform B: output2 = output1 + 1

Without snapshot:
- Transform A runs, writes output1
- Transform B runs, reads NEW output1 (data race!)

With snapshot:
- Both read from snapshot (old values)
- Both write to store (new values)
- No data races, deterministic order
```

### Stage 2: Model Tick

```cpp
for (auto& model : models) {
    model->tick(dt, store);
}
```

**Purpose:** Update physics models

**Why first?** Models represent "ground truth" physics that other stages observe. Temperature, position, pressure, etc. are physics-driven, not data-flow-driven.

Models write directly to SignalStore with physics_driven=true flag. These signals are owned by models, not computed by transforms.

### Stage 3: Edge Execution

```cpp
for (auto& edge : sorted_edges) {
    double input = snapshot.read(edge.source_id);
    double output = edge.transform->apply(input, dt);
    store.write(edge.target_id, output, edge.unit);
}
```

**Purpose:** Execute transform chains in topological order

**Topological sort ensures:**

- Dependencies execute before dependents
- No signal read before it's written
- Example: If C depends on B depends on A, order is A->B->C

**Why after models?** Transforms process model outputs (e.g., filtering sensor data).

### Stage 4: Rule Evaluation

```cpp
for (auto& rule : rules) {
    if (rule.evaluate(store)) {
        commands.push(rule.emit_command());
    }
}
```

**Purpose:** Evaluate conditions and emit commands

**Why after edges?** Rules operate on processed signals (post-filtering, post-transform).

Example: Emergency stop based on filtered temperature, not raw sensor.

### Stage 5: Post-Tick Write

#### Implicit: all writes already committed to store

**Purpose:** Store now contains new state for next tick

No explicit stage needed - writes happen during stages 2-4.

---

## Topological Sort Algorithm

**Goal:** Order edges so dependencies execute before dependents

### Kahn's Algorithm

```
1. Compute in-degree for each node (count of incoming edges)
2. Start with all nodes that have in-degree 0 (no dependencies)
3. Process queue:
   a. Pop node from queue
   b. Add to sorted list
   c. For each outgoing edge:
      - Decrement target node's in-degree
      - If now zero, add target to queue
4. If sorted list size < node count, graph has cycle
```

**Example:**

```
Input graph:
  A -> B -> C
  A -> C

In-degrees: A=0, B=1, C=2

Step 1: Queue=[A], Sorted=[]
Step 2: Process A, Queue=[B], Sorted=[A]
Step 3: Process B, Queue=[C], Sorted=[A,B]
Step 4: Process C, Queue=[], Sorted=[A,B,C]

Execution order: A, B, C
```

**Complexity:** O(V + E) where V=signals, E=edges

**Implementation:** See `src/compiler.cpp` lines 109-153.

---

## Cycle Detection

**Problem:** Cyclic graphs have no valid topological order

```
A -> B -> C -> A  (cycle)
```

**Detection:** If topological sort produces fewer nodes than graph contains, cycle exists.

**Why prohibit cycles?**

1. No well-defined execution order
2. Bootstrap problem (who computes first value?)
3. Algebraic loops require iterative solvers (out of scope)

**User-facing error:**

```
Error: Cycle detected in signal dependencies
Signals involved: device.sensor1 -> device.filter -> device.sensor1
```

**Future work:** Could support cycles with explicit fixpoint iteration, but adds complexity.

---

## Numerical Stability

### Problem

Physics models use numerical integration. If time step too large, integration diverges.

**Example:** Thermal mass with forward Euler integration:

```
T_{n+1} = T_n + dt * (P - h*(T_n - T_amb)) / C

Stability condition: dt < 2*C/h
```

If violated, temperature oscillates wildly.

### Solution

Models implement `compute_stability_limit()`:

```cpp
double ThermalMassModel::compute_stability_limit() const {
    return 2.0 * m_thermal_mass / m_heat_transfer_coeff;
}
```

GraphCompiler validates during compilation:

```cpp
if (dt > model.compute_stability_limit()) {
    throw std::runtime_error("Time step too large for model stability");
}
```

**User guidance:** If compilation fails, either:

1. Reduce dt (better accuracy anyway)
2. Use implicit integration (future enhancement)

---

## Design Decisions

### Why POD GraphSpec?

**Choice:** GraphSpec is Plain Old Data (vectors of structs)

**Alternatives considered:**

- Builder pattern (e.g., `graph.addEdge(...)`)
- Fluent API (e.g., `graph.edge("A", "B").withTransform(...)`)

**Rationale:**

- POD is serializable (JSON, YAML, Protobuf)
- Clear separation: spec=data, compiler=logic
- Easier to generate programmatically
- Can validate before compilation

### Why Single-Writer SignalStore?

**Choice:** No mutexes, single-writer model

**Alternative:** Thread-safe store with locking

**Rationale:**

- Real-time systems avoid unpredictable lock contention
- Single tick thread is simpler mental model
- Readers can still access safely (read-only)
- Performance: No lock overhead

**Trade-off:** Cannot parallelize edge execution. For now, acceptable (tick <10ms target easily met). Future: Could shard SignalStore by signal ranges.

### Why Integer Signal IDs?

**Choice:** SignalId is uint32_t, not string

**Alternative:** Use std::string paths everywhere

**Rationale:**

- O(1) array lookup vs O(log n) map lookup
- Cache-friendly (contiguous IDs -> contiguous storage)
- Validation at compile time (namespace creation)
- SignalId fits in CPU register

**Trade-off:** Two-step access (intern then use). Mitigated by caching IDs.

### Why No Virtual Functions in Transforms?

**Wait, we DO use virtual functions!** ITransform is interface with virtual methods.

**Decision DID consider:**

- Function pointers (C-style)
- std::function (type erasure)
- Virtual functions (C++ inheritance)

**Chose virtual functions because:**

- Clean interface (ITransform)
- Easy to extend (inherit and implement)
- Compiler can devirtualize in many cases
- Slightly slower than function pointers, but cleaner code

**Performance:** Virtual call ~2-5ns overhead. Transform math dominates (exp, sqrt, etc.)

### Why Snapshot-Based Execution?

**Choice:** Copy all signal values before processing

**Alternatives:**

- Double-buffering (two SignalStores, swap)
- Dependency tracking (only snapshot what's needed)
- Immediate propagation (write-through)

**Rationale:**

- Simplest to reason about (no race conditions)
- Deterministic (execution order doesn't affect output)
- Easy to debug (snapshot is frozen state)

**Trade-off:** O(n) memory copy per tick. For 1000 signals, ~8KB copy (negligible).

**Future optimization:** Lazy snapshot (copy-on-write), but premature optimization for now.

---

## Memory Layout

### SignalStore Internals

```cpp
class SignalStore {
private:
    std::vector<Signal> m_signals;  // Contiguous array
};
```

**Access pattern:**

```
SignalId=5 -> m_signals[5]   (O(1) array index)
```

**Cache implications:**

- Sequential iteration is cache-friendly
- Random access still fast (array, not map)

**Memory:** Approx 24 bytes per signal (value + unit + flags)

### Namespace Internals

Two data structures for O(1) in both directions:

```cpp
class SignalNamespace {
private:
    std::unordered_map<std::string, SignalId> m_path_to_id;
    std::unordered_map<SignalId, std::string> m_id_to_path;
};
```

**intern():** O(1) average (hash map insert)
**resolve():** O(1) average (hash map lookup)
**lookup():** O(1) average (reverse map)

**Memory:** ~32 bytes per signal (two map entries)

---

## Extension Points

### Custom Transforms

Implement ITransform:

```cpp
class MyTransform : public ITransform {
    double apply(double input, double dt) override { ... }
    void reset() override { ... }
    std::unique_ptr<ITransform> clone() const override { ... }
};
```

Register in factory:

```cpp
transform_factory.register_type("my_transform",
    [](const ParamMap& p) { return std::make_unique<MyTransform>(p); });
```

See [EMBEDDING.md](EMBEDDING.md) for details.

### Custom Models

Implement IModel:

```cpp
class MyModel : public IModel {
    void tick(double dt, SignalStore& store) override { ... }
    void reset() override { ... }
    double compute_stability_limit() const override { ... }
    std::string describe() const override { ... }
    std::vector<SignalId> output_signal_ids() const override { ... }
};
```

Register similar to transforms.

### Custom Rules

_(Future feature)_ Implement IRule interface (not yet designed).

---

## Testing Strategy

### Unit Tests

- Test each component in isolation
- Mock dependencies (e.g., FakeSignalStore)
- Focus: Correctness of individual transforms/models

**Location:** tests/unit/

### Analytical Tests

- Validate numerical accuracy against analytical solutions
- Example: FirstOrderLag vs exp(-t/tau)
- Focus: Scientific correctness

**Location:** tests/analytical/

### Integration Tests

- Test full engine execution
- Multi-model interactions
- Determinism validation
- Focus: System behavior

**Location:** tests/integration/

### Benchmarks

- Measure performance (throughput, latency)
- Detect regressions
- Focus: Real-time viability

**Location:** tests/benchmarks/

**Note:** Run benchmarks in Release mode (`-O3`). Debug builds are 10-100x slower.

---

## Performance Characteristics

**Target:** 1000-signal graph in <10ms per tick

### Breakdown (Rough estimates for Release build)

| Operation       | Time       | Notes                       |
| --------------- | ---------- | --------------------------- |
| Snapshot copy   | 10 us      | 1000 signals \* 10ns        |
| Model tick      | 1-5 ms     | Depends on model complexity |
| Edge execution  | 50-500 us  | 1000 edges \* 50ns-500ns    |
| Rule evaluation | 10-100 us  | Simple conditionals         |
| **Total**       | **1-6 ms** | Well under 10ms budget      |

**Bottlenecks:**

1. Model physics (exp, sqrt, etc.)
2. Transform math (less expensive)
3. Memory access (cache misses)

**Not bottlenecks:**

- Virtual function calls (~2ns overhead)
- Namespace lookups (done at compile time)
- Command queue operations (rare)

---

## Future Enhancements

### Parallel Edge Execution

Independent edges could execute concurrently:

```
Level 0: [A, B, C]  (no dependencies, run in parallel)
Level 1: [D, E]     (depend on level 0)
Level 2: [F]        (depends on D, E)
```

**Benefit:** 2-4x speedup for wide graphs
**Challenge:** Thread pool overhead, synchronization

### Implicit Integration

Replace forward Euler with backward Euler or RK4:

**Benefit:** Larger stable time steps
**Challenge:** Iterative solvers (Newton-Raphson)

### YAML/JSON Parsing

Load GraphSpec from file:

```yaml
edges:
  - source: device.sensor
    target: device.filtered
    transform:
      type: first_order_lag
      params:
        tau_s: 1.0
```

**Benefit:** No recompilation for graph changes
**Challenge:** Adds yaml-cpp or nlohmann-json dependency

### GPU Acceleration

Offload transform chains to GPU:

**Benefit:** 10-100x speedup for massively parallel graphs
**Challenge:** GPU synchronization, API complexity

---

## Comparison to Other Frameworks

### vs. Simulink

- **Simulink:** Visual block diagrams, MATLAB integration, expensive
- **FluxGraph:** Code-first, C++17, free, embeddable

### vs. OpenModelica

- **OpenModelica:** Equation-based modeling, DAE solvers, heavy
- **FluxGraph:** Signal-flow, explicit integration, lightweight

### vs. ROS

- **ROS:** Distributed pub/sub, process-based, high latency
- **FluxGraph:** In-process, deterministic, low latency

### vs. Custom C Code

- **Custom:** Fully flexible, hard to maintain, error-prone
- **FluxGraph:** Structured, testable, modular

**FluxGraph niche:** Embedded real-time simulation where determinism and performance matter more than visual design tools.

---

## Code Organization

```
fluxgraph/
├── include/fluxgraph/
│   ├── core/              SignalStore, Namespace, Command
│   ├── transform/         8 built-in transforms + interface
│   ├── model/             ThermalMass + interface
│   ├── graph/             GraphSpec, Compiler
│   └── engine.hpp         Five-stage execution engine
├── src/                   Implementation files
├── tests/
│   ├── unit/              Component tests
│   ├── analytical/        Scientific validation
│   ├── integration/       System tests
│   └── benchmarks/        Performance tests
├── examples/              Usage examples
└── docs/                  Documentation (you are here)
```

**Header-only vs. library:**

- Most code in headers for template flexibility
- Heavy logic (compiler, models) in .cpp for compile time

---

## Build System

CMake 3.20+, C++17 standard:

```cmake
add_subdirectory(fluxgraph)
target_link_libraries(your_app PRIVATE fluxgraph)
```

**Zero external dependencies** (except GoogleTest for tests).

**Platform support:**

- Windows (MSVC 2019+)
- Linux (GCC 9+, Clang 10+)
- macOS (Xcode 12+)

---

## Summary

FluxGraph achieves high-performance deterministic simulation through:

1. **Signal-centric architecture** - Integer IDs, array storage
2. **Five-stage tick model** - Snapshot isolation, ordered execution
3. **Topological sort** - Dependency-aware scheduling
4. **Modular design** - Easy to extend transforms/models
5. **Scientific validation** - Analytical tests for correctness

**Result:** Sub-10ms ticks for 1000-signal graphs with zero dependencies.

**Next:** See [TRANSFORMS.md](TRANSFORMS.md) for transform details, [EMBEDDING.md](EMBEDDING.md) for integration guide.

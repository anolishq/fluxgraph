# Architecture

## Overview

FluxGraph is a deterministic signal processing library designed for real-time simulation. This document explains the key architectural decisions, execution model, and design principles.

## Design Goals

1. **Determinism** - Same inputs always produce same outputs
2. **Performance** - Low overhead for real-time execution (<10ms ticks)
3. **Modularity** - Easy to add transforms/models
4. **Zero Dependencies** - Pure C++20, no external libs
5. **Type Safety** - Strong typing, compile-time checks where possible

## Core Architecture

### Signal-Centric Design

All data flows through signals identified by integer handles (SignalId):

```
[External Input] -> SignalStore -> [Graph Processing] -> SignalStore -> [External Output]
```

**Benefits:**

- Fast lookups (array indexing, not map searches)
- Simple synchronization (single-writer tick, fixed topological order)
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

### Stage 1: Input Boundary Freeze

```cpp
// Stage 1: Input boundary freeze
// (external writes are assumed complete before tick entry)
```

**Purpose:** Application writes made before `tick()` form the input state; the engine takes no snapshot or copy of signal values

**Why?** Edges read and write the live store, so a downstream non-delay edge sees values written earlier in the same tick. Determinism comes from the fixed compiled order. Example:

```
Transform A: output1 = input1 * 2
Transform B: output2 = output1 + 1

In compiled topological order:
- Transform A runs, writes output1
- Transform B runs, reads the output1 that A wrote this tick
- Same inputs and same order give the same outputs
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
for (auto &edge : edges_) {
    const double source_value = store.read_value(edge.source);
    double output = edge.transform->apply(source_value, dt);
    store.write_with_contract_unit(edge.target, output);
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
for (const auto &rule : rules_) {
    if (rule.condition(store)) {
        for (size_t i = 0; i < rule.device_functions.size(); ++i) {
            if (pending_commands_.size() >= pending_commands_.capacity()) {
                throw std::runtime_error(
                    "Engine: command backlog capacity exceeded; call "
                    "drain_commands() more frequently");
            }

            PendingCommand cmd;
            cmd.device = rule.device_functions[i].first;
            cmd.function = rule.device_functions[i].second;
            cmd.args = &rule.args_list[i];
            pending_commands_.push_back(cmd);
        }
    }
}
```

**Purpose:** Evaluate conditions and emit commands

**Why after edges?** Rules operate on processed signals (post-filtering, post-transform).

Example: Emergency stop based on filtered temperature, not raw sensor.

### Stage 5: Post-Tick Write

#### Implicit: all writes already committed to store

**Purpose:** Store now contains new state for next tick

No explicit stage needed - signal writes happen during stages 2-3; rule evaluation queues commands and writes no signals.

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
4. If fewer edges were sorted than there are non-delay edges, the sort fails
   (a backstop: the cycle check below runs first)
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

**Complexity:** O((V + E) log(V + E)) where V=signals, E=edges (ordered `std::map`/`std::set` containers give a deterministic smallest-ID-first order)

**Implementation:** See `topological_sort_edges` in `src/graph/compiler/algorithms.cpp`.

---

## Cycle Detection

**Problem:** Cyclic graphs have no valid topological order

```
A -> B -> C -> A  (cycle)
```

**Detection:** Before the topological sort, a depth-first search over the non-delay edges (`detect_cycles_in_non_delay_subgraph` in `src/graph/compiler/algorithms.cpp`) reports a cycle when it reaches a signal already on the current path.

**Why prohibit cycles of non-delay edges?** A feedback loop that passes through at least one `delay` edge is allowed; delay edges execute first in the edge stage. Cycles made only of non-delay edges are rejected because:

1. No well-defined execution order
2. Bootstrap problem (who computes first value?)
3. Algebraic loops require iterative solvers (out of scope)

**User-facing error:**

```
GraphCompiler: Cycle detected in non-delay subgraph: 0 -> 1 -> 0. Add a delay edge in feedback path.
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
    if (heat_transfer_coeff_ <= 0.0) {
        return std::numeric_limits<double>::infinity();
    }

    const double tau = thermal_mass_ / heat_transfer_coeff_;
    if (integration_method_ == ThermalIntegrationMethod::ForwardEuler) {
        return 2.0 * tau;
    }

    return kRk4NegativeRealAxisStabilityLimit * tau;  // ~2.785 * tau
}
```

GraphCompiler validates during compilation when `compile()` is given an `expected_dt` greater than zero (the default, `-1.0`, skips this check):

```cpp
double limit = model->compute_stability_limit();
if (expected_dt > limit) {
    std::ostringstream oss;
    oss << "Stability violation: " << model->describe() << " requires dt < " << limit
        << "s, but dt = " << expected_dt << "s";
    throw std::runtime_error(oss.str());
}
```

`Engine::tick()` checks every model against the `dt` it is given and throws `Engine: stability violation for model '<describe>' (dt=... exceeds limit=...)`.

**User guidance:** If compilation or a tick fails the stability check, either:

1. Reduce dt (better accuracy anyway)
2. Set `integration_method: rk4` on models that accept it, for a wider limit
3. Use implicit integration (future enhancement)

---

## Design Decisions

### Why POD GraphSpec?

**Choice:** GraphSpec is Plain Old Data (vectors of structs)

**Alternatives considered:**

- Builder pattern (e.g., `graph.addEdge(...)`)
- Fluent API (e.g., `graph.edge("A", "B").withTransform(...)`)

**Rationale:**

- POD maps directly onto JSON and YAML (the optional loaders build a GraphSpec from either)
- Clear separation: spec=data, compiler=logic
- Easier to generate programmatically
- Loaders check structure while parsing; semantic validation (units, signatures, cycles) runs in `GraphCompiler::compile`

### Why Single-Writer SignalStore?

**Choice:** No mutexes, single-writer model

**Alternative:** Thread-safe store with locking

**Rationale:**

- Real-time systems avoid unpredictable lock contention
- Single tick thread is simpler mental model
- Reads are safe only while no write or tick is in progress; concurrent readers need external synchronization (the gRPC server serializes all access with one mutex)
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

### Why Immediate Propagation?

**Choice:** Edges read and write the live store in compiled topological order; no signal values are copied before processing

**Alternatives:**

- Double-buffering (two SignalStores, swap)
- Dependency tracking (only snapshot what's needed)
- Snapshot staging (copy all signal values before processing)

**Rationale:**

- Upstream writes reach downstream non-delay edges in the same tick, so non-delay edges add no delay between each other
- A signal written by a non-delay edge reaches models and delay edges on the next tick, because both run before non-delay edges
- Deterministic (execution order affects values within a tick, and that order is fixed at compile time)

**Trade-off:** The compiler must reject cycles of non-delay edges and keep a stable ordering. See [semantics_spec.md](semantics_spec.md).

---

## Memory Layout

### SignalStore Internals

```cpp
class SignalStore {
private:
    std::vector<Signal> signals_;  // Contiguous array
    std::vector<uint8_t> has_signal_;
    std::vector<uint8_t> physics_driven_;
    std::vector<std::string> declared_units_;
    std::vector<uint8_t> has_declared_unit_;
    size_t signal_count_ = 0;
};
```

**Access pattern:**

```
SignalId=5 -> signals_[5]   (O(1) array index)
```

**Cache implications:**

- Sequential iteration is cache-friendly
- Random access still fast (array, not map)

**Memory:** About 75 bytes per slot on 64-bit libstdc++ (a 40-byte `Signal` holding a `double` and a `std::string` unit, a 32-byte declared-unit `std::string`, and three flag bytes), plus heap storage for unit strings longer than the small-string buffer

### Namespace Internals

Two ordered maps, one per direction, each with O(log n) lookup:

```cpp
class SignalNamespace {
private:
    std::map<std::string, SignalId> path_to_id_;
    std::map<SignalId, std::string> id_to_path_;
    SignalId next_id_ = 0;
};
```

**intern():** O(log n) (map lookup, then two inserts for a new path)
**resolve():** O(log n) (map lookup)
**lookup():** O(log n) (reverse map lookup, returns a copy of the path)

**Memory:** Roughly 150 bytes per signal on 64-bit libstdc++ (two `std::map` nodes, each holding a `std::string` and the ID), plus heap storage for paths longer than the small-string buffer

---

## Extension Points

### Custom Transforms

Implement ITransform:

```cpp
class MyTransform : public ITransform {
    double apply(double input, double dt) override { ... }
    void reset() override { ... }
    ITransform *clone() const override { ... }
};
```

Register in factory:

```cpp
GraphCompiler::register_transform_factory("my_transform",
    [](const TransformSpec &spec) -> std::unique_ptr<ITransform> {
        return std::make_unique<MyTransform>(spec.params);
    });
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
- Use real SignalStore and SignalNamespace instances (no mocks or fakes)
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

### Measured (Release build)

The complex scenario in `tests/benchmarks/tick_bench.cpp` (about 1000 signals, 500 `linear` edges, 10 `thermal_mass` models, no rules) averages 114.67 us per tick with zero allocations per tick in the committed baseline `benchmarks/policy/baselines/ci-hosted.windows-2022.json` (`scenario.tick.complex.v1.avg_tick_us`, Release build on Windows 11). No per-stage breakdown is measured. See [performance-benchmarks.md](performance-benchmarks.md) for how baselines are produced.

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

Add backward Euler alongside the explicit methods (forward Euler is the default; RK4 is selected with `integration_method: rk4`):

**Benefit:** Larger stable time steps
**Challenge:** Iterative solvers (Newton-Raphson)

### YAML/JSON Parsing

Implemented as optional loaders: `load_yaml_file` / `load_json_file` build a GraphSpec from a file when FluxGraph is built with `FLUXGRAPH_YAML_ENABLED` / `FLUXGRAPH_JSON_ENABLED`:

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
**Dependency:** yaml-cpp or nlohmann-json, pulled in only when the matching option is enabled

### GPU Acceleration

Offload transform chains to GPU:

**Benefit:** 10-100x speedup for massively parallel graphs
**Challenge:** GPU synchronization, API complexity

---

## Comparison to Other Frameworks

### vs. Simulink

- **Simulink:** Visual block diagrams, MATLAB integration, expensive
- **FluxGraph:** Code-first, C++20, free, embeddable

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
│   ├── core/              SignalStore, Namespace, types, units
│   ├── transform/         9 built-in transforms + interface
│   ├── model/             7 built-in models + interface, integration methods
│   ├── graph/             GraphSpec, Compiler
│   ├── command.hpp        Command
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

- Built-in transforms and the interfaces are header-only (no templates)
- Heavy logic (compiler, models) in .cpp for compile time

---

## Build System

CMake 3.20+, C++20 standard:

```cmake
add_subdirectory(fluxgraph)
target_link_libraries(your_app PRIVATE fluxgraph)
```

**Zero external dependencies** in the core library. Optional features add GoogleTest (tests), nlohmann-json (JSON loader), yaml-cpp (YAML loader) and gRPC/Protobuf (server).

**Platform support:**

- Windows (MSVC 19.32+ / Visual Studio 2022 17.2+)
- Linux (GCC 13+, Clang 17+ with libc++ 17+ or libstdc++ 13+)
- macOS (Apple Clang with C++20 `std::format`; not built in CI)

CI builds with GCC on Ubuntu 26.04 and MSVC v145 (Visual Studio 2026)
on Windows Server 2025.

---

## Summary

FluxGraph achieves high-performance deterministic simulation through:

1. **Signal-centric architecture** - Integer IDs, array storage
2. **Five-stage tick model** - Immediate propagation in a fixed order
3. **Topological sort** - Dependency-aware scheduling
4. **Modular design** - Easy to extend transforms/models
5. **Scientific validation** - Analytical tests for correctness

**Result:** Sub-10ms ticks for 1000-signal graphs with zero dependencies.

**Next:** See [TRANSFORMS.md](TRANSFORMS.md) for transform details, [EMBEDDING.md](EMBEDDING.md) for integration guide.

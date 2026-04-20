# API Reference

## Overview

FluxGraph is a high-performance C++17 signal processing library for real-time simulations. It provides:

- Type-safe signal storage with units
- Declarative graph-based data flow
- Modular transforms and physics models
- Deterministic execution engine

## Core API

### SignalStore

Central storage for all signal values in your simulation.

```cpp
#include "fluxgraph/core/signal_store.hpp"

fluxgraph::SignalStore store;
```

#### Methods

**void write(SignalId id, double value, const char\* unit)**
Write a signal value with specified unit. First write declares the unit.

```cpp
auto temp_id = namespace.intern("chamber.temp");
store.write(temp_id, 25.0, "degC");
```

**double read_value(SignalId id)**
Read current signal value. Returns 0.0 for invalid or unwritten signals.

```cpp
double temp = store.read_value(temp_id);
```

**Signal read(SignalId id)**
Read full signal including value, unit, and physics-driven flag.

```cpp
auto signal = store.read(sensor_id);
std::cout << "Value: " << signal.value << " " << signal.unit << std::endl;
```

**void declare_unit(SignalId id, const char\* unit)**
Pre-declare expected unit for a signal. Enforces consistency.

```cpp
store.declare_unit(temp_id, "degC");
store.write(temp_id, 25.0, "degF");  // Error: Unit mismatch
```

**void clear()**
Reset all signal values to 0.0. Unit declarations persist.

```cpp
store.clear();  // Values reset, units retained
```

---

### SignalNamespace

Maps human-readable paths to integer SignalId handles for fast lookups.

```cpp
#include "fluxgraph/core/namespace.hpp"

fluxgraph::SignalNamespace namespace;
```

#### Methods

**SignalId intern(const std::string& path)**
Register a signal path and get its unique ID. Idempotent.

```cpp
auto id1 = ns.intern("device.sensor1");  // Creates new ID
auto id2 = ns.intern("device.sensor1");  // Returns same ID
assert(id1 == id2);
```

**SignalId resolve(const std::string& path)**
Lookup existing signal ID. Returns INVALID_SIGNAL_ID if not found.

```cpp
auto id = ns.resolve("device.sensor2");
if (id == fluxgraph::INVALID_SIGNAL_ID) {
    std::cerr << "Signal not found" << std::endl;
}
```

**std::string lookup(SignalId id)**
Reverse lookup SignalId to path. Returns empty string for invalid IDs.

```cpp
std::string path = ns.lookup(signal_id);
```

**size_t size()**
Get total number of interned signals.

**std::vector&lt;std::string&gt; all_paths()**
Get all interned signal paths.

**void clear()**
Remove all signal mappings. Use with caution - invalidates all SignalIds.

---

### FunctionNamespace

Maps device names and function names to integer IDs for command emission.

```cpp
#include "fluxgraph/core/namespace.hpp"

fluxgraph::FunctionNamespace fn_namespace;
```

#### Methods

**DeviceId intern_device(const std::string& device_name)**
Register device name, returns unique DeviceId.

**FunctionId intern_function(const std::string& function_name)**
Register function name, returns unique FunctionId.

Similar resolve/lookup methods as SignalNamespace.

---

### Engine

Executes the simulation graph each tick using five-stage pipeline.

```cpp
#include "fluxgraph/engine.hpp"

fluxgraph::Engine engine;
```

#### Methods

**void load(CompiledProgram program)**
Load compiled graph into engine for execution.

```cpp
GraphCompiler compiler;
auto program = compiler.compile(spec, namespace, fn_namespace);
engine.load(std::move(program));
```

**void tick(double dt, SignalStore& store)**
Execute one simulation step with time delta dt.

```cpp
engine.tick(0.1, store);  // 100ms time step
```

**Five-stage execution:**

1. Pre-tick snapshot (read all signals)
2. Model tick (physics updates)
3. Edge execution (transform chains)
4. Rule evaluation (command emission)
5. Post-tick write (commit changes)

**std::vector&lt;Command&gt; drain_commands()**
Retrieve and clear command queue.

```cpp
auto commands = engine.drain_commands();
for (const auto& cmd : commands) {
    // Execute command
}
```

**void reset()**
Reset all internal state (models, transforms, rules) to initial conditions.

```cpp
engine.reset();
store.clear();
// Ready to run simulation again from t=0
```

---

## Graph Construction

### GraphSpec

Plain Old Data (POD) structure defining the entire simulation graph.

```cpp
#include "fluxgraph/graph/spec.hpp"

fluxgraph::GraphSpec spec;
```

#### Parameter Types

FluxGraph separates graph configuration params from command transport args:

1. `TransformSpec.params` and `ModelSpec.params` use `ParamMap` / `ParamValue`
   (structured values: scalar, array, object).
2. `ActionSpec.args` and runtime `Command` args use scalar `Variant`
   (`double`, `int64_t`, `bool`, `std::string`).

This keeps structured graph configuration decoupled from command/RPC payloads.

#### EdgeSpec

Defines signal transformation edges.

```cpp
fluxgraph::EdgeSpec edge;
edge.source_path = "sensor.raw";
edge.target_path = "sensor.filtered";
edge.transform.type = "first_order_lag";
edge.transform.params["tau_s"] = 1.0;  // 1 second time constant
spec.edges.push_back(edge);
```

**Available transform types:**

- `linear` - Scale and offset: y = scale\*x + offset
- `first_order_lag` - Low-pass filter: tau \* dy/dt + y = x
- `delay` - Time delay: y(t) = x(t - delay_sec)
- `noise` - Add Gaussian noise: y = x + N(0, amplitude)
- `saturation` - Clamp to bounds: y = clamp(x, min, max)
- `deadband` - Zero below threshold: y = (|x| < threshold) ? 0 : x
- `rate_limiter` - Limit rate of change: |dy/dt| <= max_rate
- `moving_average` - Sliding window average

#### ModelSpec

Defines physics models.

```cpp
fluxgraph::ModelSpec model;
model.id = "thermal_chamber";
model.type = "thermal_mass";
model.params["temp_signal"] = std::string("chamber.temp");
model.params["power_signal"] = std::string("chamber.power");
model.params["ambient_signal"] = std::string("ambient.temp");
model.params["thermal_mass"] = 1000.0;  // J/K
model.params["heat_transfer_coeff"] = 10.0;  // W/K
model.params["initial_temp"] = 25.0;  // degC
model.params["integration_method"] = std::string("forward_euler"); // optional: "forward_euler" (default) or "rk4"
spec.models.push_back(model);
```

**Available model types:**

- `thermal_mass` - Heat transfer simulation
- `thermal_rc2` - Two-node thermal RC network (coupled temperatures)
- `first_order_process` - First-order process primitive (PT1)
- `second_order_process` - Second-order process primitive (PT2)
- `state_space_siso_discrete` - Discrete-time SISO state-space model
- `mass_spring_damper` - Translational mass-spring-damper (mechanical)
- `dc_motor` - Armature-controlled DC motor (electromechanical)

Structured state-space example:

```cpp
model.id = "ss";
model.type = "state_space_siso_discrete";
model.params["output_signal"] = std::string("ss.y");
model.params["input_signal"] = std::string("ss.u");
model.params["A_d"] = fluxgraph::ParamArray{
    fluxgraph::ParamArray{0.9, 0.1},
    fluxgraph::ParamArray{0.0, 0.95},
};
model.params["B_d"] = fluxgraph::ParamArray{0.1, 0.05};
model.params["C"] = fluxgraph::ParamArray{1.0, 0.0};
model.params["D"] = 0.0;
model.params["x0"] = fluxgraph::ParamArray{0.0, 0.0};
```

State-space scope notes:

1. This built-in model is discrete-time only.
2. In strict dimensional mode, input/output signal contracts are required.
3. Internal state-unit algebra is not yet modeled.

See [state-space-siso-discrete.md](state-space-siso-discrete.md) for the full
model contract.

#### Migration Note for Custom Factories

Legacy custom factories often used direct `std::get<T>` on scalar-only params.
With `ParamValue`, use typed extractors from `fluxgraph/graph/param_utils.hpp`
for deterministic path-aware errors.

Before:

```cpp
double gain = std::get<double>(spec.params.at("gain"));
std::string output = std::get<std::string>(spec.params.at("output_signal"));
```

After:

```cpp
#include "fluxgraph/graph/param_utils.hpp"

const std::string context = "model[" + spec.id + ":" + spec.type + "]";
double gain = fluxgraph::param::as_double(
    spec.params.at("gain"), context + "/gain");
std::string output = fluxgraph::param::as_string(
    spec.params.at("output_signal"), context + "/output_signal");
```

#### RuleSpec

Defines condition -> command mappings (future feature).

```cpp
fluxgraph::RuleSpec rule;
rule.signal_path = "chamber.temp";
rule.condition_type = "threshold";
rule.threshold = 50.0;
rule.device_name = "controller";
rule.function_name = "emergency_stop";
spec.rules.push_back(rule);
```

---

### GraphCompiler

Compiles GraphSpec into executable form with validation.

```cpp
#include "fluxgraph/graph/compiler.hpp"

fluxgraph::GraphCompiler compiler;
```

#### Methods

**CompiledProgram compile(const GraphSpec& spec, SignalNamespace& ns, FunctionNamespace& fn)**
Compile graph specification into executable program.

**Compilation steps:**

1. Parse transforms, models, rules from spec
2. Resolve all signal paths to IDs via namespace
3. Topological sort to determine execution order
4. Detect cycles (throws exception if found)
5. Validate model stability (checks dt vs dynamics)
6. Package into CompiledProgram

**Throws:**

- std::runtime_error on unknown transform/model types
- std::runtime_error on cyclic dependencies
- std::runtime_error on invalid parameters

```cpp
try {
    auto program = compiler.compile(spec, namespace, fn_namespace);
    engine.load(std::move(program));
} catch (const std::exception& e) {
    std::cerr << "Compilation failed: " << e.what() << std::endl;
}
```

---

## Graph Loaders

Optional loaders for creating `GraphSpec` from JSON or YAML files. These require `-DFLUXGRAPH_JSON_ENABLED=ON` or `-DFLUXGRAPH_YAML_ENABLED=ON` at CMake configure time.

### JSON Loader

Load graphs from JSON files or strings.

```cpp
#include "fluxgraph/loaders/json_loader.hpp"
```

**GraphSpec load_json_file(const std::string& filepath)**
Load graph from JSON file.

```cpp
auto spec = fluxgraph::loaders::load_json_file("graph.json");

fluxgraph::GraphCompiler compiler;
auto program = compiler.compile(spec, signal_ns, func_ns);
engine.load(std::move(program));
```

**GraphSpec load_json_string(const std::string& json_content)**
Parse graph from JSON string.

```cpp
std::string json = R"({
  "edges": [
    {
      "source": "input.x",
      "target": "output.y",
      "transform": {
        "type": "linear",
        "params": {
          "scale": 2.0,
          "offset": 0.0
        }
      }
    }
  ]
})";

auto spec = fluxgraph::loaders::load_json_string(json);
```

**Errors:**

- `std::runtime_error` - JSON parse errors, missing required fields, invalid values
- Error messages include JSON pointer paths (e.g., `/edges/2/transform/type`)

**See also:**

- [JSON_SCHEMA.md](schema-json.md) - Complete schema reference
- [examples/03_json_graph/](https://github.com/anolishq/fluxgraph/tree/main/examples/03_json_graph) - Working example

### YAML Loader

Load graphs from YAML files or strings.

```cpp
#include "fluxgraph/loaders/yaml_loader.hpp"
```

**GraphSpec load_yaml_file(const std::string& filepath)**
Load graph from YAML file.

```cpp
auto spec = fluxgraph::loaders::load_yaml_file("graph.yaml");

fluxgraph::GraphCompiler compiler;
auto program = compiler.compile(spec, signal_ns, func_ns);
engine.load(std::move(program));
```

**GraphSpec load_yaml_string(const std::string& yaml_content)**
Parse graph from YAML string.

```cpp
std::string yaml = R"(
edges:
  - source: input.x
    target: output.y
    transform:
      type: linear
      params:
        scale: 2.0
        offset: 0.0
)";

auto spec = fluxgraph::loaders::load_yaml_string(yaml);
```

**Errors:**

- `std::runtime_error` - YAML parse errors, missing required fields, invalid values
- Error messages include node paths (e.g., `edges[2].transform.type`)

**See also:**

- [YAML_SCHEMA.md](schema-yaml.md) - Complete schema reference
- [examples/04_yaml_graph/](https://github.com/anolishq/fluxgraph/tree/main/examples/04_yaml_graph) - Working example

**Note:** Loaders are completely optional. You can always construct `GraphSpec` programmatically without any file parsing dependencies.

---

## Transforms

### ITransform Interface

All transforms implement this interface.

```cpp
#include "fluxgraph/transform/interface.hpp"

class ITransform {
public:
    virtual double apply(double input, double dt) = 0;
    virtual void reset() = 0;
    virtual std::unique_ptr<ITransform> clone() const = 0;
    virtual ~ITransform() = default;
};
```

**apply(input, dt)** - Process one sample with time step dt
**reset()** - Reset internal state to initial conditions
**clone()** - Create deep copy (for multi-instancing)

### Custom Transforms

Implement ITransform to create custom transforms.

```cpp
class MyTransform : public fluxgraph::ITransform {
private:
    double m_state = 0.0;
public:
    double apply(double input, double dt) override {
        m_state = 0.9 * m_state + 0.1 * input;
        return m_state;
    }

    void reset() override {
        m_state = 0.0;
    }

    std::unique_ptr<ITransform> clone() const override {
        return std::make_unique<MyTransform>(*this);
    }
};
```

Register with factory (see EMBEDDING.md for details).

---

## Models

### IModel Interface

All physics models implement this interface.

```cpp
#include "fluxgraph/model/interface.hpp"

class IModel {
public:
    virtual void tick(double dt, SignalStore& store) = 0;
    virtual void reset() = 0;
    virtual double compute_stability_limit() const = 0;
    virtual std::string describe() const = 0;
    virtual std::vector<SignalId> output_signal_ids() const = 0;
    virtual ~IModel() = default;
};
```

**tick(dt, store)** - Update model by dt seconds using signals from store
**reset()** - Reset to initial state
**compute_stability_limit()** - Return maximum stable dt for numerical integration
**describe()** - Return human-readable description
**output_signal_ids()** - Declare every signal written by tick() for compile-time single-writer validation (must be interned IDs, never `INVALID_SIGNAL`)

### ThermalMassModel

Lumped thermal mass with heat transfer.

Physics equation:

```
C * dT/dt = P - h * (T - T_ambient)
```

Parameters:

- C: thermal_mass (J/degC) - Heat capacity
- h: heat_transfer_coeff (W/degC) - Convection coefficient
- P: power_signal (W) - Heat input
- T_ambient: ambient_signal (degC) - Ambient temperature
- integration_method (optional): `"forward_euler"` (default) or `"rk4"`

**Stability limit:**

- `forward_euler`: dt < 2\*C/h
- `rk4`: dt < 2.785293563\*C/h (negative real-axis stability bound)

Example usage:

```cpp
ModelSpec model;
model.type = "thermal_mass";
model.params["temp_signal"] = std::string("chamber.temp");
model.params["power_signal"] = std::string("power");
model.params["ambient_signal"] = std::string("ambient");
model.params["thermal_mass"] = 1000.0;
model.params["heat_transfer_coeff"] = 10.0;
model.params["initial_temp"] = 25.0;
model.params["integration_method"] = std::string("rk4"); // optional
```

---

## Command

Commands emitted by rules for execution by external systems.

```cpp
#include "fluxgraph/core/command.hpp"

fluxgraph::Command cmd(device_id, function_id);
cmd.add_arg(42.0);              // double
cmd.add_arg(int64_t{100});      // int64_t
cmd.add_arg(true);              // bool
cmd.add_arg(std::string{"OK"}); // string
```

**Access arguments:**

```cpp
if (std::holds_alternative<double>(cmd.args[0])) {
    double value = std::get<double>(cmd.args[0]);
}
```

---

## Thread Safety

**Single-writer model:**

- SignalStore: One writer, multiple readers safe
- Engine: tick() must be called from single thread
- Namespace: intern() not thread-safe, resolve() safe after setup

**Best practice:**
Setup phase (single-threaded):

1. Build namespace (intern all signal paths)
2. Compile graph
3. Load engine

Execution phase (can be threaded):

- Engine tick (single thread)
- Multiple readers can call store.read() concurrently

---

## Error Handling

**Invalid SignalId:**

```cpp
auto id = ns.resolve("nonexistent");
if (id == fluxgraph::INVALID_SIGNAL_ID) {
    // Handle missing signal
}
```

**Compilation errors:**

```cpp
try {
    auto program = compiler.compile(spec, ns, fn);
} catch (const std::runtime_error& e) {
    // e.what() contains error description
}
```

**Unit mismatches:**

```cpp
store.declare_unit(temp_id, "degC");
store.write(temp_id, 77.0, "degF");  // Error logged, write rejected
```

**Invalid tick:**

```cpp
engine.tick(dt, store);  // Throws if no program loaded
```

---

## Performance Tips

1. **Reserve signal IDs upfront:**

```cpp
store.reserve(1000);  // If you know signal count
```

1. **Reuse SignalIds:**

```cpp
// Cache IDs, avoid repeated resolve()
auto temp_id = ns.intern("chamber.temp");
// Use temp_id many times
```

1. **Minimize graph complexity:**

- Fewer edges = faster execution
- Long transform chains = more overhead

1. **Choose appropriate dt:**

- Too small: wasted computation
- Too large: instability
- Use model.compute_stability_limit() as guide

1. **Profile before optimizing:**

- Run benchmarks (see tests/benchmarks/)
- Most time typically in models, not transforms

---

## Minimal Example

```cpp
#include "fluxgraph/core/signal_store.hpp"
#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/graph/compiler.hpp"
#include "fluxgraph/engine.hpp"

int main() {
    using namespace fluxgraph;

    // Setup
    SignalNamespace ns;
    FunctionNamespace fn;
    SignalStore store;
    Engine engine;

    // Build graph
    GraphSpec spec;
    EdgeSpec edge;
    edge.source_path = "input";
    edge.target_path = "output";
    edge.transform.type = "linear";
    edge.transform.params["scale"] = 2.0;
    edge.transform.params["offset"] = 1.0;
    spec.edges.push_back(edge);

    // Compile and load
    GraphCompiler compiler;
    auto program = compiler.compile(spec, ns, fn);
    engine.load(std::move(program));

    // Execute
    auto input_id = ns.resolve("input");
    auto output_id = ns.resolve("output");

    store.write(input_id, 10.0, "");
    engine.tick(0.1, store);

    double result = store.read_value(output_id);
    // result = 2*10 + 1 = 21

    return 0;
}
```

See [examples/](https://github.com/anolishq/fluxgraph/tree/main/examples) for more complete examples.

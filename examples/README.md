# FluxGraph Examples

This directory contains usage examples demonstrating the FluxGraph library API, progressing from simple manual graph composition to more complex physics simulations.

## Building Examples

Examples are built automatically when `FLUXGRAPH_BUILD_EXAMPLES=ON` (default):

```bash
cmake -B build
cmake --build build --config Debug
```

## Example 1: Basic Transform

**Location:** `01_basic_transform/`

Demonstrates the fundamental FluxGraph API pattern:

- Manual `GraphSpec` construction (no YAML)
- Simple signal edge with `LinearTransform` (y = 2x + 1)
- Input/output "ports" as `SignalId` handles
- Basic simulation loop: `write()` -> `tick()` -> `read_value()`

**Run:**

```bash
./build/examples/01_basic_transform/Debug/example_basic_transform.exe
```

**Expected Output:**

```
Simple Transform: y = 2*x + 1
================================
Input: 0V -> Output: 1V
Input: 1V -> Output: 3V
Input: 2V -> Output: 5V
Input: 3V -> Output: 7V
Input: 4V -> Output: 9V
```

**Key API Concepts:**

- `GraphSpec` - Protocol-agnostic POD graph definition
- `GraphCompiler::compile()` - Validates and optimizes graph
- `Engine::load()` - Sets up execution state
- `SignalNamespace::resolve()` - Gets signal IDs from paths
- `SignalStore::write()` and `read_value()` - Signal I/O

## Example 2: Thermal Mass Simulation

**Location:** `02_thermal_mass/`

Shows realistic physics simulation with:

- `ThermalMassModel` - First-order thermal system
- Multiple input ports (heater power, ambient temperature)
- Stateful simulation with noise transform
- Heating and cooling phases

**Run:**

```bash
./build/examples/02_thermal_mass/Debug/example_thermal_mass.exe
```

**Expected Output:**

```
Thermal Mass Simulation
=======================
t= 0.00s  Heater=500.00W  Temp= 25.23 degC  Noisy= 25.15 degC
t= 0.50s  Heater=500.00W  Temp= 25.45 degC  Noisy= 25.38 degC
...
t= 5.00s  Heater=  0.00W  Temp= 27.42 degC  Noisy= 27.48 degC
t= 5.50s  Heater=  0.00W  Temp= 27.38 degC  Noisy= 27.31 degC
...
```

**Physics:**

- Thermal mass: C = 1000 J/K
- Heat transfer: h = 10 W/K
- Time constant: tau = C/h = 100 seconds
- Heating: 500W -> steady-state delta_T = 50 degC above ambient

**Key API Concepts:**

- `ModelSpec` - Physics model configuration
- Model input/output signals (power_in, temperature_out)
- Transform chains (physics -> noise filter)
- Timestep management (dt parameter in `tick()`)

## Example 3: JSON Graph Loader

**Location:** `03_json_graph/` _(requires -DFLUXGRAPH_JSON_ENABLED=ON)_

Demonstrates loading graphs from JSON files:

- External graph definition in `graph.json`
- `load_json_file()` API for file loading
- Same execution model as manual construction
- Thermal chamber simulation with transforms

**Build with JSON support:**

```bash
cmake -B build-json -DFLUXGRAPH_JSON_ENABLED=ON
cmake --build build-json --config Debug
```

**Run:**

```bash
./build-json/examples/03_json_graph/Debug/example_json_graph.exe
```

Use the structured state-space sample file:

```bash
./build-json/examples/03_json_graph/Debug/example_json_graph.exe \
  ./examples/03_json_graph/state_space_siso_discrete.json
```

**Graph structure (graph.json):**

- 1 thermal mass model (chamber)
- 3 signal edges with transforms (saturation, lag, noise)
- heater -> chamber -> sensor -> display pipeline

**Key API Concepts:**

- `load_json_file()` - Parse JSON graph definition
- `load_json_string()` - Parse from string
- Optional dependency (core library still zero-dep)
- Identical runtime API after loading

Additional structured-parameter sample:

- `state_space_siso_discrete.json` demonstrates nested matrix/vector params for
  the discrete state-space model.

## Example 4: YAML Graph Loader

**Location:** `04_yaml_graph/` _(requires -DFLUXGRAPH_YAML_ENABLED=ON)_

Same thermal simulation as Example 3, but using YAML format:

- Human-friendly syntax with comments
- YAML anchors/aliases for reusability
- `load_yaml_file()` API

**Build with YAML support:**

```bash
cmake -B build-yaml -DFLUXGRAPH_YAML_ENABLED=ON
cmake --build build-yaml --config Debug
```

**Run:**

```bash
./build-yaml/examples/04_yaml_graph/Debug/example_yaml_graph.exe
```

Use the structured state-space sample file:

```bash
./build-yaml/examples/04_yaml_graph/Debug/example_yaml_graph.exe \
  ./examples/04_yaml_graph/state_space_siso_discrete.yaml
```

**Graph structure (graph.yaml):**

- Same logical structure as Example 3
- YAML syntax instead of JSON
- Supports comments and multi-line strings

Additional structured-parameter sample:

- `state_space_siso_discrete.yaml` demonstrates nested matrix/vector params for
  the discrete state-space model.

**Key API Concepts:**

- `load_yaml_file()` - Parse YAML graph definition
- `load_yaml_string()` - Parse from string
- Optional dependency (core library still zero-dep)
- Can enable both JSON and YAML simultaneously

## Example 5: Two-Node Thermal RC Simulation

**Location:** `05_thermal_rc2/`

Demonstrates a coupled two-temperature physics model:

- `thermal_rc2` - Two-node thermal RC network (shell/core style)
- Multiple model outputs (`temp_signal_a`, `temp_signal_b`)
- Ambient coupling + inter-node conductance

**Run:**

```bash
./build/examples/05_thermal_rc2/Debug/example_thermal_rc2.exe
```

## Example 6: First-Order Process (PT1)

**Location:** `06_first_order_process/`

Demonstrates a simple first-order process primitive:

- `first_order_process` model with `gain` and `tau_s`
- Dimensionless input/output contracts (`dimensionless`)
- Step input response

**Run:**

```bash
./build/examples/06_first_order_process/Debug/example_first_order_process.exe
```

## Example 7: Second-Order Process (PT2)

**Location:** `07_second_order_process/`

Demonstrates a canonical second-order process primitive:

- `second_order_process` model with `gain`, `zeta`, and `omega_n_rad_s`
- Dimensionless input/output contracts (`dimensionless`)
- Step input response

**Run:**

```bash
./build/examples/07_second_order_process/Debug/example_second_order_process.exe
```

## Example 8: Mass-Spring-Damper (Mechanical)

**Location:** `08_mass_spring_damper/`

Demonstrates a simple translational mechanical model:

- `mass_spring_damper` model with physical parameters (`mass`, `damping_coeff`, `spring_constant`)
- Force input contract (`N`) and position/velocity outputs (`m`, `m/s`)
- Step force response

**Run:**

```bash
./build/examples/08_mass_spring_damper/Debug/example_mass_spring_damper.exe
```

## Example 9: DC Motor (Electromechanical)

**Location:** `09_dc_motor/`

Demonstrates an electromechanical model with coupled electrical + mechanical
dynamics:

- `dc_motor` model with physical parameters (`R`, `L`, `Kt`, `Ke`, `J`, `b`)
- Voltage input (`V`) and load torque input (`N*m`)
- Speed/current/torque outputs (`rad/s`, `A`, `N*m`)

**Run:**

```bash
./build/examples/09_dc_motor/Debug/example_dc_motor.exe
```

## Example 10: State-Space SISO Discrete

**Location:** `10_state_space_siso_discrete/`

Demonstrates structured model parameters for a discrete-time state-space
system:

- `state_space_siso_discrete` model with matrix/vector params (`A_d`, `B_d`,
  `C`, `D`, `x0`)
- Strict dimensional compile mode with declared input/output contracts
- Deterministic difference-equation evolution

**Run:**

```bash
./build/examples/10_state_space_siso_discrete/Debug/example_state_space_siso_discrete.exe
```

## When to Use Each Approach

### Manual GraphSpec (Examples 1 & 2)

**Use when:**

- Embedding FluxGraph in existing code
- Generating graphs programmatically
- No external config file needed
- Dynamic graph construction at runtime

**Benefits:**

- Zero external dependencies (core library only)
- Type-safe at compile time
- Full programmatic control
- No parsing overhead

### JSON Configuration (Example 3)

**Use when:**

- Modern tooling and validation (JSON Schema)
- Exchanging with web APIs or JavaScript
- Strict schema validation needed
- Machine-generated configs

**Benefits:**

- Ubiquitous format (every language supports it)
- Fast parsing with nlohmann/json
- JSON Schema validation available
- Compact syntax

### YAML Configuration (Example 4)

**Use when:**

- Complex graphs with many edges/models
- Non-programmers need to edit configs
- Shared configs across multiple tools

**Benefits:**

- Human-readable/editable
- Declarative syntax with comments
- Anchors/aliases for reuse
- Version control friendly

## Next Steps

After understanding these examples:

1. **Explore transforms** - See `include/fluxgraph/transform/` for all 8 types
2. **Add models** - Implement custom physics models via `IModel` interface
3. **Check tests** - `tests/unit/` and `tests/analytical/` show comprehensive usage
4. **Read docs** - See `docs/` for architecture and design decisions

## API Quick Reference

```cpp
// 1. Setup
SignalNamespace sig_ns;
SignalStore store;
Engine engine;

// 2. Build graph (manual or from YAML)
GraphSpec spec;
spec.edges.push_back({source, target, transform});
spec.models.push_back({id, type, params});

// 3. Compile and load
GraphCompiler compiler;
auto program = compiler.compile(spec, sig_ns, func_ns);
engine.load(std::move(program));

// 4. Get ports
auto input_sig = sig_ns.resolve("device.signal_name");
auto output_sig = sig_ns.resolve("other.output");

// 5. Simulation loop
store.write(input_sig, value, "unit");
engine.tick(dt, store);
double result = store.read_value(output_sig);
```

## Troubleshooting

**"Unknown model type" error:**

- Check ModelSpec `type` field matches an implemented model type (`thermal_mass`, `thermal_rc2`, `first_order_process`, `second_order_process`)
- Ensure all required params are present

**Signals read as 0.0:**

- Verify signal was written before reading
- Check SignalNamespace path spelling
- Confirm `tick()` was called to propagate changes

**Unexpected NaN/Inf values:**

- Check model stability limits (dt too large)
- Verify model parameters satisfy constraints (for example: thermal_mass > 0, heat_transfer_coeff > 0)
- Ensure ambient temperature is initialized

**Compile errors:**

- Use `target_path` not `dest_path` in EdgeSpec
- Use `temp_signal` not `temperature_signal` for ThermalMassModel params
- Include all required headers (engine.hpp, compiler.hpp, etc.)

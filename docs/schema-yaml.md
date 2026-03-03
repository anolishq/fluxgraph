# YAML Graph Schema

FluxGraph YAML files define signal processing graphs with a human-friendly syntax. This document specifies the schema for graph files loaded with `load_yaml_file()` and `load_yaml_string()`.

## YAML Structure

A graph file has four top-level sequences (all optional):

```yaml
signals:
  - path: signal.path
    unit: unit_symbol

models:
  - id: unique_identifier
    type: model_type
    params:
      param_name: value

edges:
  - source: source.signal.path
    target: target.signal.path
    transform:
      type: transform_type
      params:
        param_name: value

rules:
  - id: rule_identifier
    condition: "signal_path > value"
    actions:
      - device: device_id
        function: function_name
        args:
          arg_name: value
```

## Signals

Signals declare explicit unit contracts used by dimensional validation.

```yaml
signals:
  - path: chamber.temp
    unit: degC
```

**Fields:**

- `path` (string, required) - Signal path
- `unit` (string, required) - Unit symbol (`dimensionless`, `W`, `degC`, etc.)

## Models

Models represent physical systems with internal state and differential equations.

### Model Object

```yaml
- id: unique_identifier # Unique model identifier
  type: model_type # Model type (thermal_mass in v1.0)
  params: # Model-specific parameters
    param_name: value
```

### ThermalMass Model

Lumped thermal capacitance with heat transfer: `C * dT/dt = P - h * (T - T_ambient)`

**Parameters:**
| Parameter | Type | Units | Description |
|-----------|------|-------|-------------|
| `temp_signal` | string | - | Output signal path for temperature |
| `power_signal` | string | W | Input signal path for heating power |
| `ambient_signal` | string | degC | Input signal path for ambient temperature |
| `thermal_mass` | number | J/K | Heat capacity (must be > 0) |
| `heat_transfer_coeff` | number | W/K | Heat transfer coefficient (must be > 0) |
| `initial_temp` | number | degC | Initial temperature |

**Example:**

```yaml
models:
  - id: chamber
    type: thermal_mass
    params:
      temp_signal: chamber.temp
      power_signal: chamber.power
      ambient_signal: ambient.temp
      thermal_mass: 1000.0
      heat_transfer_coeff: 10.0
      initial_temp: 25.0
```

**Stability:** Forward Euler integration requires `dt < 2 * thermal_mass / heat_transfer_coeff`

## Edges

Edges connect signals through transforms, defining the dataflow graph.

### Edge Object

```yaml
- source: source.signal.path # Source signal path
  target: target.signal.path # Target signal path
  transform: # Transform specification
    type: transform_type
    params:
      param_name: value
```

## Transforms

All 9 transform types with their parameters:

### 1. Linear Transform

**Type:** `linear`

Scale and offset: `y = scale * x + offset`

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `scale` | number | yes | - | Multiplicative gain |
| `offset` | number | yes | - | Additive offset |
| `clamp_min` | number | no | -infinity | Minimum output value |
| `clamp_max` | number | no | +infinity | Maximum output value |

**Example:**

```yaml
edges:
  - source: sensor.raw
    target: sensor.scaled
    transform:
      type: linear
      params:
        scale: 2.5
        offset: -10.0
        clamp_min: 0.0
        clamp_max: 100.0
```

### 2. First-Order Lag

**Type:** `first_order_lag`

Low-pass filter: `tau * dy/dt + y = x`

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `tau_s` | number | Time constant in seconds (must be > 0) |

**Example:**

```yaml
edges:
  - source: sensor.noisy
    target: sensor.filtered
    transform:
      type: first_order_lag
      params:
        tau_s: 0.5
```

**Frequency Response:** 3dB cutoff at f_c = 1 / (2*pi * tau)

### 3. Delay Transform

**Type:** `delay`

Time-shift signal: `y(t) = x(t - delay_sec)`

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `delay_sec` | number | Delay duration in seconds (must be >= 0) |

**Example:**

```yaml
edges:
  - source: input.signal
    target: delayed.signal
    transform:
      type: delay
      params:
        delay_sec: 0.1
```

**Memory:** Approx `delay_sec / dt * 8` bytes (circular buffer)

### 4. Noise Transform

**Type:** `noise`

Add Gaussian white noise: `y = x + N(0, amplitude)`

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `amplitude` | number | yes | Standard deviation of noise |
| `seed` | integer | no | Random seed for repeatability |

**Example:**

```yaml
edges:
  - source: sensor.ideal
    target: sensor.noisy
    transform:
      type: noise
      params:
        amplitude: 0.5
        seed: 42
```

### 5. Saturation Transform

**Type:** `saturation`

Clamp to bounds: `y = clamp(x, min, max)`

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `min` | number | Minimum output value |
| `max` | number | Maximum output value |

**Example:**

```yaml
edges:
  - source: controller.output
    target: actuator.input
    transform:
      type: saturation
      params:
        min: 0.0
        max: 100.0
```

### 6. Deadband Transform

**Type:** `deadband`

Zero output below threshold: `y = (|x| < threshold) ? 0.0 : x`

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `threshold` | number | Sensitivity threshold (must be >= 0) |

**Example:**

```yaml
edges:
  - source: joystick.raw
    target: joystick.gated
    transform:
      type: deadband
      params:
        threshold: 0.05
```

### 7. Rate Limiter

**Type:** `rate_limiter`

Limit rate of change: `|dy/dt| <= max_rate_per_sec`

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `max_rate_per_sec` | number | Maximum rate in units/second (must be > 0) |

**Example:**

```yaml
edges:
  - source: setpoint.target
    target: setpoint.ramped
    transform:
      type: rate_limiter
      params:
        max_rate_per_sec: 5.0
```

**Settling Time:** Approx `delta_V / max_rate_per_sec` for step change

### 8. Moving Average

**Type:** `moving_average`

Sliding window average (FIR filter): `y = (1/N) * sum(x[n-i])` for i=0 to N-1

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `window_size` | integer | Number of samples to average (must be >= 1) |

**Example:**

```yaml
edges:
  - source: sensor.jittery
    target: sensor.smoothed
    transform:
      type: moving_average
      params:
        window_size: 10
```

**Memory:** `window_size * 8` bytes per instance

### 9. Unit Convert

**Type:** `unit_convert`

Explicit cross-unit conversion transform. Conversion coefficients are derived
from the built-in unit registry.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `to_unit` | string | yes | Target unit symbol |
| `from_unit` | string | no | Optional source-unit assertion |

**Example:**

```yaml
edges:
  - source: sensor.temp_c
    target: sensor.temp_k
    transform:
      type: unit_convert
      params:
        to_unit: K
        from_unit: degC
```

## Rules

Rules trigger device actions when conditions are met.

### Rule Object

```yaml
- id: unique_identifier # Unique rule identifier
  condition: "signal > value" # Simple comparison
  actions: # Array of action objects
    - device: device_id
      function: function_name
      args:
        arg_name: value
  on_error: log_and_continue # Error handling (optional)
```

**Example:**

```yaml
rules:
  - id: heater_on
    condition: "chamber.temp < 20.0"
    actions:
      - device: heater
        function: set_power
        args:
          power: 500.0
```

## Complete Example

```yaml
# Thermal chamber simulation with sensor dynamics

models:
  - id: chamber
    type: thermal_mass
    params:
      temp_signal: chamber.temp
      power_signal: chamber.power
      ambient_signal: ambient.temp
      thermal_mass: 1000.0 # J/K
      heat_transfer_coeff: 10.0 # W/K
      initial_temp: 25.0 # degC

edges:
  # Heater with saturation
  - source: heater.output
    target: chamber.power
    transform:
      type: saturation
      params:
        min: 0.0 # No cooling
        max: 1000.0 # Max 1kW

  # Sensor lag (thermal mass)
  - source: chamber.temp
    target: sensor.reading
    transform:
      type: first_order_lag
      params:
        tau_s: 0.5 # 500ms response

  # Measurement noise
  - source: sensor.reading
    target: display.temp
    transform:
      type: noise
      params:
        amplitude: 0.1 # +/-0.1 degC
        seed: 42 # Repeatable

rules:
  - id: low_temp_alarm
    condition: "chamber.temp < 18.0"
    actions:
      - device: heater
        function: set_power
        args:
          power: 1000.0 # Emergency heat
```

## YAML-Specific Features

### Anchors and Aliases

Reuse configurations with `&anchor` and `*alias`:

```yaml
# Define reusable transform
_noise: &noise_01
  type: noise
  params:
    amplitude: 0.1
    seed: 42

edges:
  - source: sensor1.raw
    target: sensor1.noisy
    transform: *noise_01 # Reuse

  - source: sensor2.raw
    target: sensor2.noisy
    transform: *noise_01 # Same config
```

### Multi-line Strings

Use `|` or `>` for long conditions:

```yaml
rules:
  - id: complex_condition
    condition: |
      chamber.temp > 50.0 &&
      chamber.temp < 100.0
    actions:
      - device: alarm
        function: trigger
```

### Comments

YAML supports inline and full-line comments:

```yaml
models:
  - id: chamber # Main thermal mass
    type: thermal_mass
    params:
      thermal_mass: 1000.0 # Aluminum block
      initial_temp: 25.0 # Room temperature
```

### Compact Collections

Flow style for short lists:

```yaml
edges:
  - source: input.x
    target: output.y
    transform: { type: linear, params: { scale: 2.0, offset: 0.0 } }
```

## Error Messages

The YAML loader provides detailed error messages with node locations:

```
YAML parse error at edges[2].transform: Missing required field 'type'
YAML parse error at models[0].params.thermal_mass: Expected number, got string
YAML parse error in file graph.yaml: [yaml-cpp internal error]
```

## YAML Schema Validation

For tools that support YAML Schema (based on JSON Schema):

```yaml
# yaml-language-server: $schema=https://example.com/fluxgraph-v1.schema.json

models:
  - id: chamber
    # ... VSCode will provide autocomplete and validation
```

Schema file planned for v1.1.

## Usage

### C++ API

```cpp
#include "fluxgraph/loaders/yaml_loader.hpp"

// Load from file
auto spec = fluxgraph::loaders::load_yaml_file("graph.yaml");

// Load from string
std::string yaml_content = R"(
edges:
  - source: a.x
    target: b.y
    transform:
      type: linear
      params:
        scale: 2.0
        offset: 0.0
)";
auto spec2 = fluxgraph::loaders::load_yaml_string(yaml_content);

// Compile and run
fluxgraph::GraphCompiler compiler;
auto program = compiler.compile(spec, signal_ns, func_ns);
engine.load(std::move(program));
```

### Build Configuration

Requires `-DFLUXGRAPH_YAML_ENABLED=ON` at CMake configure time:

```bash
cmake -B build -DFLUXGRAPH_YAML_ENABLED=ON
cmake --build build
```

## JSON vs YAML

Choose based on your use case:

| Format   | When to Use                                                                                                                   |
| -------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **JSON** | - Machine-generated graphs<br>- API payloads<br>- Strict validation required<br>- Minimal dependencies                        |
| **YAML** | - Hand-written configurations<br>- Need comments/documentation<br>- Want anchors/aliases for DRY<br>- Human-readable priority |

**Example:** Use JSON for programmatically generated test cases, YAML for production configurations with extensive documentation.

## See Also

- [JSON_SCHEMA.md](schema-json.md) - JSON equivalent
- [API.md](api-reference.md) - C++ API reference
- [TRANSFORMS.md](transforms.md) - Detailed transform documentation
- [examples/04_yaml_graph/](../examples/04_yaml_graph/) - Working example

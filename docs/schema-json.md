# JSON Graph Schema

FluxGraph JSON files define signal processing graphs using a simple, validated structure. This document specifies the schema for graph files loaded with `load_json_file()` and `load_json_string()`.

## JSON Structure

A graph file has four top-level arrays (all optional):

```json
{
  "signals": [
    /* Signal unit contracts */
  ],
  "models": [
    /* Physics models */
  ],
  "edges": [
    /* Signal edges with transforms */
  ],
  "rules": [
    /* Conditional actions */
  ]
}
```

## Signals

Signals declare explicit unit contracts used by dimensional validation.

```json
{
  "path": "chamber.temp",
  "unit": "degC"
}
```

**Fields:**

- `path` (string, required) - Signal path
- `unit` (string, required) - Unit symbol (`dimensionless`, `W`, `degC`, etc.)

## Models

Models represent physical systems with internal state and differential equations.

### Model Object

```json
{
  "id": "unique_identifier",
  "type": "model_type",
  "params": {
    "param_name": value
  }
}
```

**Fields:**

- `id` (string, required) - Unique model identifier
- `type` (string, required) - Model type (built-in: `"thermal_mass"`, `"thermal_rc2"`, `"first_order_process"`, `"second_order_process"`, `"state_space_siso_discrete"`, `"mass_spring_damper"`, `"dc_motor"`)
- `params` (object, required) - Model-specific parameters (supports nested structured values)

### Parameter Value Types (Models and Transforms)

Model/transform `params` use structured values:

1. scalar: `number`, `integer`, `boolean`, `string`
2. array: JSON array of structured values
3. object: JSON object with structured values

Loader resource limits are enforced to reject abusive payloads:

1. max nesting depth: `32`
2. max total nodes: `250000`
3. max object members: `4096`
4. max array elements: `65536`
5. max string bytes: `1048576`

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
| `integration_method` | string | - | Optional: `"forward_euler"` (default) or `"rk4"` |

**Example:**

```json
{
  "id": "chamber",
  "type": "thermal_mass",
  "params": {
    "temp_signal": "chamber.temp",
    "power_signal": "chamber.power",
    "ambient_signal": "ambient.temp",
    "thermal_mass": 1000.0,
    "heat_transfer_coeff": 10.0,
    "initial_temp": 25.0
  }
}
```

**Stability:** Forward Euler integration requires `dt < 2 * thermal_mass / heat_transfer_coeff`

### ThermalRc2 Model

Two-node thermal RC network with ambient coupling and inter-node conductance.

**Parameters:**
| Parameter | Type | Units | Description |
|-----------|------|-------|-------------|
| `temp_signal_a` | string | - | Output signal path for node A temperature |
| `temp_signal_b` | string | - | Output signal path for node B temperature |
| `power_signal` | string | W | Input signal path for heating power (applied to node A) |
| `ambient_signal` | string | degC | Input signal path for ambient temperature |
| `thermal_mass_a` | number | J/K | Heat capacity of node A (must be > 0) |
| `thermal_mass_b` | number | J/K | Heat capacity of node B (must be > 0) |
| `heat_transfer_coeff_a` | number | W/K | Ambient coupling of node A (must be > 0) |
| `heat_transfer_coeff_b` | number | W/K | Ambient coupling of node B (must be > 0) |
| `coupling_coeff` | number | W/K | Conductance between nodes (must be >= 0) |
| `initial_temp_a` | number | degC | Initial temperature of node A |
| `initial_temp_b` | number | degC | Initial temperature of node B |
| `integration_method` | string | - | Optional: `"forward_euler"` (default) or `"rk4"` |

**Example:**

```json
{
  "id": "chamber_rc",
  "type": "thermal_rc2",
  "params": {
    "temp_signal_a": "chamber.shell_temp",
    "temp_signal_b": "chamber.core_temp",
    "power_signal": "chamber.heater_power",
    "ambient_signal": "ambient.temp",
    "thermal_mass_a": 1000.0,
    "thermal_mass_b": 2000.0,
    "heat_transfer_coeff_a": 10.0,
    "heat_transfer_coeff_b": 8.0,
    "coupling_coeff": 6.0,
    "initial_temp_a": 25.0,
    "initial_temp_b": 25.0,
    "integration_method": "rk4"
  }
}
```

### FirstOrderProcess Model

First-order process primitive: `dy/dt = (gain * u - y) / tau`.

**Parameters:**
| Parameter | Type | Units | Description |
|-----------|------|-------|-------------|
| `output_signal` | string | dimensionless | Output signal path |
| `input_signal` | string | dimensionless | Input signal path |
| `gain` | number | dimensionless | Static gain (finite) |
| `tau_s` | number | s | Time constant (must be > 0) |
| `initial_output` | number | dimensionless | Initial output value |
| `integration_method` | string | - | Optional: `"forward_euler"` (default) or `"rk4"` |

**Example:**

```json
{
  "id": "pt1",
  "type": "first_order_process",
  "params": {
    "output_signal": "pt1.y",
    "input_signal": "pt1.u",
    "gain": 2.0,
    "tau_s": 1.0,
    "initial_output": 0.0
  }
}
```

### SecondOrderProcess Model

Second-order process primitive:
`y'' + 2*zeta*omega_n*y' + omega_n^2*y = omega_n^2 * gain * u`

**Parameters:**
| Parameter | Type | Units | Description |
|-----------|------|-------|-------------|
| `output_signal` | string | dimensionless | Output signal path |
| `input_signal` | string | dimensionless | Input signal path |
| `gain` | number | dimensionless | Static gain (finite) |
| `zeta` | number | dimensionless | Damping ratio (must be >= 0) |
| `omega_n_rad_s` | number | 1/s | Natural frequency (must be > 0) |
| `initial_output` | number | dimensionless | Initial output value |
| `initial_output_rate` | number | 1/s | Initial output rate |
| `integration_method` | string | - | Optional: `"forward_euler"` (default) or `"rk4"` |

**Example:**

```json
{
  "id": "pt2",
  "type": "second_order_process",
  "params": {
    "output_signal": "pt2.y",
    "input_signal": "pt2.u",
    "gain": 2.0,
    "zeta": 0.7,
    "omega_n_rad_s": 4.0,
    "initial_output": 0.0,
    "initial_output_rate": 0.0,
    "integration_method": "rk4"
  }
}
```

### StateSpaceSisoDiscrete Model

Discrete-time SISO state-space model:
`x[k+1] = A_d x[k] + B_d u[k]`, `y[k] = C x[k] + D u[k]`

**Parameters:**
| Parameter | Type | Units | Description |
|-----------|------|-------|-------------|
| `output_signal` | string | user-defined | Output signal path |
| `input_signal` | string | user-defined | Input signal path |
| `A_d` | array of arrays | - | Square matrix (`n x n`) |
| `B_d` | array | - | Input vector (`n`) |
| `C` | array | - | Output vector (`n`) |
| `D` | number | - | Feedthrough scalar |
| `x0` | array | - | Initial state vector (`n`) |

**Validation notes:**

1. `A_d` must be non-empty, rectangular, and square.
2. `B_d`, `C`, and `x0` lengths must match `A_d` dimension.
3. All numeric values must be finite.
4. In strict dimensional mode, `input_signal` and `output_signal` must have
   declared signal contracts.
5. Internal state-unit algebra is currently out of scope.

**Example:**

```json
{
  "id": "ss",
  "type": "state_space_siso_discrete",
  "params": {
    "output_signal": "ss.y",
    "input_signal": "ss.u",
    "A_d": [
      [0.9, 0.1],
      [0.0, 0.95]
    ],
    "B_d": [0.1, 0.05],
    "C": [1.0, 0.0],
    "D": 0.0,
    "x0": [0.0, 0.0]
  }
}
```

### MassSpringDamper Model

Translational single-degree-of-freedom mass-spring-damper:
`m*x'' + c*x' + k*x = F`

**Parameters:**
| Parameter | Type | Units | Description |
|-----------|------|-------|-------------|
| `position_signal` | string | m | Output position signal path |
| `velocity_signal` | string | m/s | Output velocity signal path |
| `force_signal` | string | N | Input force signal path |
| `mass` | number | kg | Mass (must be > 0) |
| `damping_coeff` | number | N*s/m | Damping coefficient (must be >= 0) |
| `spring_constant` | number | N/m | Spring constant (must be >= 0) |
| `initial_position` | number | m | Initial position |
| `initial_velocity` | number | m/s | Initial velocity |
| `integration_method` | string | - | Optional: `"forward_euler"` (default) or `"rk4"` |

**Example:**

```json
{
  "id": "msd",
  "type": "mass_spring_damper",
  "params": {
    "position_signal": "msd.x",
    "velocity_signal": "msd.v",
    "force_signal": "msd.F",
    "mass": 1.0,
    "damping_coeff": 2.0,
    "spring_constant": 20.0,
    "initial_position": 0.0,
    "initial_velocity": 0.0,
    "integration_method": "rk4"
  }
}
```

### DcMotor Model

Armature-controlled DC motor with electrical inductance and viscous friction.

**Parameters:**
| Parameter | Type | Units | Description |
|-----------|------|-------|-------------|
| `speed_signal` | string | rad/s | Output speed signal path |
| `current_signal` | string | A | Output current signal path |
| `torque_signal` | string | N*m | Output electromagnetic torque signal path |
| `voltage_signal` | string | V | Input voltage signal path |
| `load_torque_signal` | string | N*m | Input load torque signal path |
| `resistance_ohm` | number | Ohm | Armature resistance (must be > 0) |
| `inductance_h` | number | H | Armature inductance (must be > 0) |
| `torque_constant` | number | N*m/A | Torque constant (must be > 0) |
| `back_emf_constant` | number | V*s/rad | Back-EMF constant (must be > 0) |
| `inertia` | number | kg*m^2 | Rotor inertia (must be > 0) |
| `viscous_friction` | number | N*m*s/rad | Viscous friction (must be >= 0) |
| `initial_current` | number | A | Initial armature current |
| `initial_speed` | number | rad/s | Initial angular speed |
| `integration_method` | string | - | Optional: `"forward_euler"` (default) or `"rk4"` |

**Example:**

```json
{
  "id": "motor",
  "type": "dc_motor",
  "params": {
    "speed_signal": "motor.omega",
    "current_signal": "motor.i",
    "torque_signal": "motor.tau",
    "voltage_signal": "motor.V",
    "load_torque_signal": "motor.load",
    "resistance_ohm": 2.0,
    "inductance_h": 0.5,
    "torque_constant": 0.1,
    "back_emf_constant": 0.1,
    "inertia": 0.02,
    "viscous_friction": 0.2,
    "initial_current": 0.0,
    "initial_speed": 0.0,
    "integration_method": "rk4"
  }
}
```

## Edges

Edges connect signals through transforms, defining the dataflow graph.

### Edge Object

```json
{
  "source": "source.signal.path",
  "target": "target.signal.path",
  "transform": {
    "type": "transform_type",
    "params": {
      /* transform parameters */
    }
  }
}
```

**Fields:**

- `source` (string, required) - Source signal path
- `target` (string, required) - Target signal path
- `transform` (object, required) - Transform specification

## Transforms

All 9 transform types with their parameters:

### 1. Linear Transform

**Type:** `"linear"`

Scale and offset: `y = scale * x + offset`

**Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `scale` | number | yes | - | Multiplicative gain |
| `offset` | number | yes | - | Additive offset |
| `clamp_min` | number | no | -infinity | Minimum output value |
| `clamp_max` | number | no | +infinity | Maximum output value |

**Example:**

```json
{
  "source": "sensor.raw",
  "target": "sensor.scaled",
  "transform": {
    "type": "linear",
    "params": {
      "scale": 2.5,
      "offset": -10.0,
      "clamp_min": 0.0,
      "clamp_max": 100.0
    }
  }
}
```

### 2. First-Order Lag

**Type:** `"first_order_lag"`

Low-pass filter: `tau * dy/dt + y = x`

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `tau_s` | number | Time constant in seconds (must be > 0) |

**Example:**

```json
{
  "source": "sensor.noisy",
  "target": "sensor.filtered",
  "transform": {
    "type": "first_order_lag",
    "params": {
      "tau_s": 0.5
    }
  }
}
```

**Frequency Response:** `3dB cutoff at f_c = 1 / (2*pi*tau)`

### 3. Delay Transform

**Type:** `"delay"`

Time-shift signal: `y(t) = x(t - delay_sec)`

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `delay_sec` | number | Delay duration in seconds (must be >= 0) |

**Example:**

```json
{
  "source": "input.signal",
  "target": "delayed.signal",
  "transform": {
    "type": "delay",
    "params": {
      "delay_sec": 0.1
    }
  }
}
```

**Memory:** Approx `delay_sec / dt * 8` bytes (circular buffer)

### 4. Noise Transform

**Type:** `"noise"`

Add Gaussian white noise: `y = x + N(0, amplitude)`

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `amplitude` | number | yes | Standard deviation of noise |
| `seed` | integer | no | Random seed for repeatability |

**Example:**

```json
{
  "source": "sensor.ideal",
  "target": "sensor.noisy",
  "transform": {
    "type": "noise",
    "params": {
      "amplitude": 0.5,
      "seed": 42
    }
  }
}
```

### 5. Saturation Transform

**Type:** `"saturation"`

Clamp to bounds: `y = clamp(x, min, max)`

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `min` | number | Minimum output value |
| `max` | number | Maximum output value|

**Example:**

```json
{
  "source": "controller.output",
  "target": "actuator.input",
  "transform": {
    "type": "saturation",
    "params": {
      "min": 0.0,
      "max": 100.0
    }
  }
}
```

### 6. Deadband Transform

**Type:** `"deadband"`

Zero output below threshold: `y = (|x| < threshold) ? 0.0 : x`

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `threshold` | number | Sensitivity threshold (must be >= 0) |

**Example:**

```json
{
  "source": "joystick.raw",
  "target": "joystick.gated",
  "transform": {
    "type": "deadband",
    "params": {
      "threshold": 0.05
    }
  }
}
```

### 7. Rate Limiter

**Type:** `"rate_limiter"`

Limit rate of change: `|dy/dt| <= max_rate_per_sec`

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `max_rate_per_sec` | number | Maximum rate in units/second (must be > 0) |

**Example:**

```json
{
  "source": "setpoint.target",
  "target": "setpoint.ramped",
  "transform": {
    "type": "rate_limiter",
    "params": {
      "max_rate_per_sec": 5.0
    }
  }
}
```

**Settling Time:** Approx `delta_V / max_rate_per_sec` for step change

### 8. Moving Average

**Type:** `"moving_average"`

Sliding window average (FIR filter): `y = (1/N) * sum(x[n-i])` for i=0 to N-1

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `window_size` | integer | Number of samples to average (must be >= 1) |

**Example:**

```json
{
  "source": "sensor.jittery",
  "target": "sensor.smoothed",
  "transform": {
    "type": "moving_average",
    "params": {
      "window_size": 10
    }
  }
}
```

**Memory:** `window_size * 8` bytes per instance

### 9. Unit Convert

**Type:** `"unit_convert"`

Explicit cross-unit conversion transform. Conversion coefficients are derived
from the built-in unit registry.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `to_unit` | string | yes | Target unit symbol |
| `from_unit` | string | no | Optional source-unit assertion |

**Example:**

```json
{
  "source": "sensor.temp_c",
  "target": "sensor.temp_k",
  "transform": {
    "type": "unit_convert",
    "params": {
      "to_unit": "K",
      "from_unit": "degC"
    }
  }
}
```

## Rules

Rules trigger device actions when conditions are met.

### Rule Object

```json
{
  "id": "unique_identifier",
  "condition": "signal_path > value",
  "actions": [
    {
      "device": "device_id",
      "function": "function_name",
      "args": {
        /* function arguments */
      }
    }
  ],
  "on_error": "log_and_continue"
}
```

**Fields:**

- `id` (string, required) - Unique rule identifier
- `condition` (string, required) - Simple comparison (basic parser in v1.0)
- `actions` (array, required) - Array of action objects
- `on_error` (string, optional) - Error handling ("log_and_continue" only in v1.0)

**Action `args` constraint:**

1. command args are scalar-only (`double`, `int64`, `bool`, `string`)
2. nested arrays/objects in `args` are rejected at load time

**Example:**

```json
{
  "id": "heater_on",
  "condition": "chamber.temp < 20.0",
  "actions": [
    {
      "device": "heater",
      "function": "set_power",
      "args": {
        "power": 500.0
      }
    }
  ]
}
```

## Complete Example

```json
{
  "models": [
    {
      "id": "chamber",
      "type": "thermal_mass",
      "params": {
        "temp_signal": "chamber.temp",
        "power_signal": "chamber.power",
        "ambient_signal": "ambient.temp",
        "thermal_mass": 1000.0,
        "heat_transfer_coeff": 10.0,
        "initial_temp": 25.0
      }
    }
  ],
  "edges": [
    {
      "source": "heater.output",
      "target": "chamber.power",
      "transform": {
        "type": "saturation",
        "params": {
          "min": 0.0,
          "max": 1000.0
        }
      }
    },
    {
      "source": "chamber.temp",
      "target": "sensor.reading",
      "transform": {
        "type": "first_order_lag",
        "params": {
          "tau_s": 0.5
        }
      }
    },
    {
      "source": "sensor.reading",
      "target": "display.temp",
      "transform": {
        "type": "noise",
        "params": {
          "amplitude": 0.1,
          "seed": 42
        }
      }
    }
  ],
  "rules": [
    {
      "id": "low_temp_alarm",
      "condition": "chamber.temp < 18.0",
      "actions": [
        {
          "device": "heater",
          "function": "set_power",
          "args": {
            "power": 1000.0
          }
        }
      ]
    }
  ]
}
```

## Error Messages

The JSON loader provides detailed error messages with JSON pointer paths:

```
JSON parse error at /edges/2/transform: Missing required field 'type'
JSON parse error at /rules/0/actions/0/args/payload: Command args must be scalar (double/int64/bool/string)
Parameter parse error at /models/0/params/x: nesting depth exceeds limit (32)
JSON parse error in file graph.json: [nlohmann::json parse error]
```

## JSON Schema Validation

For tools that support JSON Schema, here's a minimal schema excerpt:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "signals": {
      "type": "array",
      "items": { "$ref": "#/definitions/signal" }
    },
    "models": {
      "type": "array",
      "items": { "$ref": "#/definitions/model" }
    },
    "edges": {
      "type": "array",
      "items": { "$ref": "#/definitions/edge" }
    },
    "rules": {
      "type": "array",
      "items": { "$ref": "#/definitions/rule" }
    }
  }
}
```

Full JSON Schema definition: See `schema/fluxgraph-v1.schema.json` (planned for v1.1)

## Usage

### C++ API

```cpp
#include "fluxgraph/loaders/json_loader.hpp"

// Load from file
auto spec = fluxgraph::loaders::load_json_file("graph.json");

// Load from string
std::string json_content = R"({ "edges": [...] })";
auto spec2 = fluxgraph::loaders::load_json_string(json_content);

// Compile and run
fluxgraph::GraphCompiler compiler;
auto program = compiler.compile(spec, signal_ns, func_ns);
engine.load(std::move(program));
```

### Build Configuration

Requires `-DFLUXGRAPH_JSON_ENABLED=ON` at CMake configure time:

```bash
cmake -B build -DFLUXGRAPH_JSON_ENABLED=ON
cmake --build build
```

## See Also

- [YAML_SCHEMA.md](schema-yaml.md) - YAML equivalent (more human-friendly)
- [API.md](api-reference.md) - C++ API reference
- [TRANSFORMS.md](transforms.md) - Detailed transform documentation
- [examples/03_json_graph/](../examples/03_json_graph/) - Working example

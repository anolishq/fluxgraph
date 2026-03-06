# State-Space SISO Discrete Model

## Overview

`state_space_siso_discrete` is FluxGraph's built-in structured-parameter model
for discrete-time linear state-space systems:

1. `x[k+1] = A_d x[k] + B_d u[k]`
2. `y[k] = C x[k] + D u[k]`

This model is discrete by definition and does not use `integration_method`.

## Parameters

| Parameter | Type | Shape | Description |
|-----------|------|-------|-------------|
| `A_d` | array | `n x n` | State transition matrix (square, finite values) |
| `B_d` | array | `n` | Input matrix/vector (finite values) |
| `C` | array | `n` | Output matrix/vector (finite values) |
| `D` | number | scalar | Direct feedthrough term (finite value) |
| `x0` | array | `n` | Initial state (finite values) |
| `input_signal` | string | - | Input signal path |
| `output_signal` | string | - | Output signal path |

Validation is compile-time and path-specific:

1. `A_d` must be non-empty, rectangular, and square.
2. `B_d`, `C`, and `x0` must match `A_d` dimension.
3. Ragged arrays and non-finite numbers are rejected.

## Dimensional Policy

In strict dimensional mode:

1. `input_signal` and `output_signal` must have declared signal contracts.
2. The model does not impose a fixed unit symbol for those signals.

Current limitation:

1. Internal state-unit algebra is currently out of scope.
2. FluxGraph validates signal contracts at model boundaries, not matrix-level
   coefficient units.

## Non-Goals

The following are intentionally out of scope for this model:

1. Continuous-time generic state-space (`x_dot = A x + B u`).
2. MIMO generalized matrices.
3. Structured command argument transport over runtime command APIs.

## C++ Example

```cpp
fluxgraph::ModelSpec model;
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

Runnable example:

1. `examples/10_state_space_siso_discrete/`

Loader-based examples:

1. `examples/03_json_graph/state_space_siso_discrete.json`
2. `examples/04_yaml_graph/state_space_siso_discrete.yaml`

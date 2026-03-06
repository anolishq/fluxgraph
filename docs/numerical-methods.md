# Numerical Methods Policy

## Scope

This document defines the numerical integration policy for FluxGraph models.
It complements `docs/semantics_spec.md` and is authoritative for solver
selection and stability interpretation.
Validation protocol details are documented in `docs/validation-methodology.md`.

## Current Policy

1. For ODE-based models, integration method selection is explicit via model
   parameters.
2. If not specified for ODE models, the deterministic default is
   `forward_euler`.
3. Methods are selected at compile time and remain fixed at runtime.
4. Runtime behavior must be deterministic for identical inputs and `dt`.

## ODE Model Integration Methods

The following built-in models support `integration_method`:

1. `thermal_mass`
2. `thermal_rc2`
3. `first_order_process`
4. `second_order_process`

Discrete-time structured model:

1. `state_space_siso_discrete` does not use `integration_method`.
2. Its update law is natively discrete (`x[k+1] = A_d x[k] + B_d u[k]`).
3. `compute_stability_limit()` returns infinity for this model because no
   continuous-time explicit integration step is performed.

Supported methods:

1. `forward_euler` (default)
2. `rk4` (classic fourth-order Runge-Kutta)

Selection is provided via:

```cpp
model.params["integration_method"] = std::string("forward_euler");
// or
model.params["integration_method"] = std::string("rk4");
```

Unknown method names are compile-time errors.

## Stability Limits

For the linear thermal mass model `dT/dt = (P - h*(T - T_amb)) / C`, with
`k = h/C`, the stability limits are:

1. `forward_euler`: `dt < 2/k = 2*C/h`
2. `rk4`: `dt < 2.785293563/k = 2.785293563*C/h`

If `h <= 0`, the model is treated as unconditionally stable for this criterion.

For the two-node thermal RC model, the system is linear: `dT/dt = A*T + c`.
Let `lambda_min` be the most negative eigenvalue of `A` (largest magnitude on
the negative real axis). The stability limits use:

1. `forward_euler`: `dt < 2/|lambda_min|`
2. `rk4`: `dt < 2.785293563/|lambda_min|`

FluxGraph enforces these via `IModel::compute_stability_limit()`.

For the process primitives:

1. `first_order_process`: equivalent to `lambda = -1/tau_s`, so the same
   negative-real-axis limits apply.
2. `second_order_process`: eigenvalues may be complex; stability is evaluated
   using the selected method's stability function `R(z)` along `z = lambda*dt`,
   requiring `|R(lambda*dt)| <= 1` for each eigenvalue.

## Validation Expectations

Validation runs must report:

1. Error metrics (`L2`, `Linf`) versus analytical references.
2. Convergence behavior as `dt` is refined.
3. Determinism checks for each supported integration method.

## Forward Compatibility

Future methods (for example trapezoidal or implicit schemes) must define:

1. Stability policy and limits.
2. Deterministic selection and defaults.
3. Regression and analytical validation coverage before release.

## Reproducible Validation Run

Use the validation runner to produce validation artifacts:

```bash
python scripts/run_numerical_validation.py --preset dev-release --enforce-order
```

Windows example:

```powershell
python .\scripts\run_numerical_validation.py --preset dev-windows-release --config Release --enforce-order
```

CI evidence runs are produced by:

1. `.github/workflows/numerical-validation-evidence.yml`

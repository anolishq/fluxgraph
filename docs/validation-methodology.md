# Numerical Validation Methodology

## Purpose

This document defines the validation protocol used to support Phase 3
numerical claims for FluxGraph model integration behavior.
Phase-level criteria mapping is documented in `docs/phase3-evidence.md`.

## Systems Under Test

Current validation scope targets `thermal_mass` with two canonical scenarios:

1. `thermal.cooling.v1`
2. `thermal.forced_response.v1`

Each scenario is evaluated with:

1. `forward_euler`
2. `rk4`

## Reference Solution

Validation uses the analytical solution of the first-order linear thermal model:

`dT/dt = (P - h*(T - T_amb)) / C`

Closed-form references are used for both cooling and forced-response settings.

## Error Metrics

For each `(scenario, method, dt)` run:

1. `L2` error over the sampled trajectory
2. `Linf` error over the sampled trajectory
3. Final-time absolute error

## Convergence Estimation

Observed order is estimated by linear regression on log-log scale:

`log(error) = p * log(dt) + b`

`p` is reported as:

1. `observed_order_l2`
2. `observed_order_linf`

## Evidence Thresholds

Current CI-enforced minima (`Linf`):

1. `forward_euler >= 0.9`
2. `rk4 >= 3.5`

These thresholds are conservative guards. They are not intended as publication
claims by themselves; publication claims should cite full artifact sets.

## Reproducibility

Local run:

```bash
python scripts/run_numerical_validation.py --preset dev-release --enforce-order
```

Windows run:

```powershell
python .\scripts\run_numerical_validation.py --preset dev-windows-release --config Release --enforce-order
```

CI run:

1. GitHub Actions workflow: `.github/workflows/numerical-validation-evidence.yml`
2. Output artifact directory: `artifacts/validation/<timestamp_or_runid>_*`

Each evidence run includes:

1. `validation_results.json`
2. `validation_results.csv`
3. `validation_evaluation.json`
4. stdout/stderr and build/configure logs

## Threats to Validity

1. Current suite validates only one model family (`thermal_mass`).
2. Convergence is measured on fixed `dt` sweeps and selected parameter regimes.
3. Floating-point behavior may vary slightly across compilers/architectures.
4. Threshold-based pass/fail does not replace full statistical or multi-platform analysis.

## Next Extensions

1. Add validation scenarios for additional models as they are introduced.
2. Extend to transform stochastic validation (e.g., noise distribution checks).
3. Add publication-grade plotting/notebook pipeline over stored CSV results.

# Performance Benchmarks

## Purpose

This document defines the reproducible benchmark workflow for FluxGraph.

Goals:

1. Provide repeatable measurement artifacts for Phase 2 gates.
2. Separate measured evidence from narrative claims.
3. Keep benchmark runs deterministic enough for regression comparison.

## Scope

Current benchmark executables:

1. `benchmark_signal_store`
2. `benchmark_namespace`
3. `benchmark_tick`
4. `json_loader_bench` (optional, when `FLUXGRAPH_JSON_ENABLED=ON`)
5. `yaml_loader_bench` (optional, when `FLUXGRAPH_YAML_ENABLED=ON`)

## Reproducible Runner

Use the benchmark wrapper scripts.

Linux/macOS:

```bash
bash ./scripts/bench.sh --preset dev-release
```

Windows PowerShell:

```powershell
.\scripts\bench.ps1 -Preset dev-windows-release -Config Release
```

Optional loader benchmarks:

```bash
bash ./scripts/bench.sh --preset dev-release --include-optional
```

Strict status enforcement (for gated runs):

```bash
bash ./scripts/bench.sh --preset dev-release --fail-on-status
```

The wrappers call `scripts/run_benchmarks.py`, which:

1. Configures/builds benchmark targets (unless `--no-build` is set).
2. Runs each benchmark executable.
3. Captures stdout/stderr logs per target.
4. Emits a machine-readable manifest with environment, git metadata, and parsed benchmark metrics.

By default, status failures are reported but do not fail the run; execution failures still fail.
Use `--fail-on-status` when running gate-enforced benchmark checks.

Wrappers then run `scripts/evaluate_benchmarks.py` with a policy profile:

1. `local`: informational for workstation variability.
2. `ci-hosted`: warning-oriented checks for shared CI runners.
3. `ci-dedicated`: strict gate profile for stable hardware evidence.

## Artifact Contract

Artifacts are stored under:

`artifacts/benchmarks/<timestamp>_<preset>/`

Required files:

1. `benchmark_results.json`
2. `benchmark_evaluation.json`
3. `<target>.stdout.log`
4. `<target>.stderr.log`
5. `configure.stdout.log`, `configure.stderr.log` (when build enabled)
6. `build.stdout.log`, `build.stderr.log` (when build enabled)

`benchmark_results.json` contains:

1. Timestamp (UTC)
2. Preset/config/build directory
3. Platform, hostname, Python version
4. Git commit hash and dirty-worktree flag
5. Per-benchmark executable path, command, exit code, duration, parsed PASS/FAIL status lines

Tick benchmark output additionally tracks measured heap allocations during the timed loop (`Allocations`, `Alloc/tick`) so Phase 2 zero-allocation evidence is captured per scenario.

`benchmark_evaluation.json` contains:

1. selected policy profile
2. issue summary (errors/warnings)
3. per-check findings with metric keys and threshold context

## Evidence Rules

For any published performance claim, attach:

1. Commit hash used for the run.
2. Exact benchmark command.
3. Full artifact directory or archived equivalent.
4. Hardware and OS details (captured in manifest + release notes).
5. Comparison baseline (previous artifact manifest).

Claims without linked artifacts are treated as unsupported.

## CI Guidance

Benchmarks are intentionally separated from the default CI correctness lanes.

Recommended:

1. Run benchmark evidence workflow on demand (`workflow_dispatch`) or scheduled lane.
2. Store artifacts as CI build artifacts.
3. Apply `ci-hosted` profile on hosted runners and reserve strict gating for dedicated runners.

## Next Phase 2 Steps

1. Define numeric regression thresholds per workload class.
2. Introduce automated baseline comparison tooling.
3. Add a dedicated perf CI lane with artifact upload and threshold evaluation.

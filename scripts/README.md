# FluxGraph Scripts (Preset-First)

These scripts are thin wrappers around CMake presets.

## Prerequisite

Set `VCPKG_ROOT` so presets can resolve the toolchain:

- Linux/macOS: `export VCPKG_ROOT=/path/to/vcpkg`
- Windows PowerShell: `$env:VCPKG_ROOT = "D:\\Tools\\vcpkg"`

## Build

- Linux/macOS: `bash ./scripts/build.sh --preset dev-release`
- Windows: `.\scripts\build.ps1 -Preset dev-windows-release`

Options:

- `--preset` / `-Preset`: configure+build preset name.
- `--clean-first` / `-CleanFirst`: clean target before build.
- `-j/--jobs` / `-Jobs`: build parallelism.

## Test

- Linux/macOS: `bash ./scripts/test.sh --preset dev-release`
- Windows: `.\scripts\test.ps1 -Preset dev-windows-release`

Options:

- `--preset` / `-Preset`: CTest preset name.
- `--verbose` / `-Verbose`: verbose test output.

## Benchmarks

- Linux/macOS: `bash ./scripts/bench.sh --preset dev-release`
- Windows: `.\scripts\bench.ps1 -Preset dev-windows-release`

Options:

- `--preset` / `-Preset`: configure+build preset.
- `--config` / `-Config`: multi-config build profile (for Visual Studio, usually `Release`).
- `--output-dir` / `-OutputDir`: benchmark artifact directory.
- `--include-optional` / `-IncludeOptional`: include JSON/YAML loader benchmarks.
- `--no-build` / `-NoBuild`: run existing binaries without configure/build.
- `--fail-on-status` / `-FailOnStatus`: return non-zero when benchmark reports `Status: FAIL`.
- `--policy-profile` / `-PolicyProfile`: benchmark policy profile (`local`, `ci-hosted`, `ci-dedicated`).
- `--policy-file` / `-PolicyFile`: policy JSON path (default: `benchmarks/policy/bench_policy.json`).
- `--baseline` / `-Baseline`: optional baseline JSON for latency regression checks.
- `--no-evaluate` / `-NoEvaluate`: skip policy evaluation stage.

Artifacts are written under `artifacts/benchmarks/<timestamp>_<preset>/` with:

- `benchmark_results.json` (manifest + metadata + per-benchmark status)
- `benchmark_evaluation.json` (policy evaluation summary)
- `*.stdout.log` and `*.stderr.log`
- configure/build logs when build is enabled

Promote a run to baseline:

- `python scripts/promote_benchmark_baseline.py --results artifacts/benchmarks/<dir>/benchmark_results.json --policy benchmarks/policy/bench_policy.json --profile ci-hosted --output benchmarks/policy/baselines/ci-hosted.windows-2022.json`

## Common Presets

- `dev-debug`
- `dev-release`
- `dev-windows-debug`
- `dev-windows-release`
- `ci-linux-release`
- `ci-linux-release-json`
- `ci-linux-release-yaml`
- `ci-linux-release-server`
- `ci-windows-release`

## Server + Python gRPC Integration (CI-aligned)

1. Configure/build with `ci-linux-release-server`.
2. Generate Python protobuf bindings:
   - `bash ./scripts/generate_proto_python.sh`
3. Start server binary from `build-server`.
4. Run: `python3 tests/test_grpc_integration.py`

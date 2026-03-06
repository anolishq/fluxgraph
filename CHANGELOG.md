# Changelog

All notable changes to FluxGraph will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Engine tick semantics now follow model-first then edge-propagation execution for immediate within-tick signal flow.
- Edge processing now writes using target signal contracts (or target-local unit state), and no longer copies source unit metadata during propagation.
- Graph compiler supports delay-mediated feedback policy by detecting cycles on the non-delay subgraph.
- Graph compiler topological ordering is deterministic for non-delay edges (stable tie-break by `SignalId`).
- Server `--dt` is now wired into runtime timestep and compile-time stability validation.
- GoogleTest discovery switched to `POST_BUILD` mode for more reliable Visual Studio multi-config test registration.
- Graph schema now supports explicit top-level `signals` unit contracts in JSON/YAML.
- Transform/model registration APIs now include signature-aware strict-mode variants:
  - `register_transform_factory_with_signature(...)`
  - `register_model_factory_with_signature(...)`
- Compiler now supports policy-driven dimensional validation:
  - `DimensionalPolicy::permissive`
  - `DimensionalPolicy::strict`
- Strict-mode rule-threshold validation now requires declared LHS signal unit contracts.
- CI now includes a required strict-dimensional-validation lane with artifact upload.
- Graph configuration params now use structured `ParamValue` trees for model and transform parameters (`ParamMap`), while command/rule args remain scalar `Variant` values.

### Added

- Runtime stability validation in `Engine::tick` (`dt` must be positive and within model stability limits).
- Rule condition execution in compiler for comparator expressions:
  - `<`, `<=`, `>`, `>=`, `==`, `!=`
- Compiler parameter parsing hardening:
  - numeric coercion `int64 -> double` where valid
  - path-precise parameter type/missing-key diagnostics
  - optional `noise.seed` default
  - alias support for `saturation` (`min_value/max_value`) and `rate_limiter` (`max_rate`)
- Single-writer ownership checks across model outputs and edge targets.
- Server write-authority enforcement rejecting writes to protected model-owned and edge-derived signals.
- New/expanded tests covering:
  - immediate chain propagation
  - rule condition emission path
  - delay-mediated cycle acceptance
  - stability validation (compile-time + runtime paths)
  - server protected-write rejection
  - server `--dt` timestep behavior
  - SignalStore unit-declaration behavior
- Benchmark evidence tooling:
  - policy profiles (`local`, `ci-hosted`, `ci-dedicated`)
  - benchmark evaluation script (`scripts/evaluate_benchmarks.py`)
  - benchmark evidence CI workflow with artifact upload (`.github/workflows/benchmark-evidence.yml`)
- Numerical validation framework:
  - `thermal_mass` integration method policy (`forward_euler`, `rk4`)
  - numerical validation runner (`scripts/run_numerical_validation.py`)
  - thermal validation target (`tests/validation/thermal_mass_validation.cpp`)
  - numerical validation CI evidence workflow (`.github/workflows/numerical-validation-evidence.yml`)
  - methodology/evidence docs (`docs/validation-methodology.md`, `docs/numerical-methods.md`)
- Dimensional-analysis core primitives:
  - `UnitKind`, `DimensionVector`, `UnitDef`, `UnitConversion`
  - curated `UnitRegistry` with affine temperature conversions and absolute/delta temperature boundary checks
- New `unit_convert` transform for explicit registry-derived cross-unit conversion (`to_unit`, optional `from_unit` assertion).
- Compiled-program signal contract metadata propagated into runtime preload.
- SignalStore contract/runtime helpers:
  - `write_with_contract_unit(...)`
  - `has_declared_unit(...)`
  - `declared_unit(...)`
- New/expanded unit tests for:
  - unit registry conversions and compatibility checks
  - strict-mode dimensional compiler rejection paths and permissive warning paths
  - target-contract edge write behavior
  - JSON/YAML loader `signals` parsing
  - `unit_convert` transform behavior
- Dimensional validation automation:
  - `scripts/run_dimensional_validation.py` for strict test evidence generation
  - scheduled/dispatch evidence workflow (`.github/workflows/dimensional-validation-evidence.yml`)
- Structured-parameter model support:
  - built-in `state_space_siso_discrete` model (`A_d`, `B_d`, `C`, `D`, `x0`)
  - compile-time structured-parameter validation hook in model signatures
  - unit + analytical tests for shape validation, deterministic trajectory, and reset behavior
- Loader hardening for structured params:
  - centralized parse limits (depth, node count, collection sizes, string size)
  - recursive model/transform param parsing in JSON/YAML loaders
  - scalar-only enforcement for rule action `args`

### Fixed

- Rule execution path was previously non-functional (conditions were hardcoded false).
- Stability validation function existed but was not integrated into active server compile/load path.
- CLI timestep argument was previously parsed but not applied to service runtime behavior.
- Signal unit contract now prevents accidental mismatches while avoiding premature lock-in to `"dimensionless"` defaults.
- Windows test executables no longer link both `gtest_main` and `gmock` runtimes in `fluxgraph_tests`, which could cause zero discovered/registered tests at runtime.

## [0.1.1] - 2024-02-16

### Fixed

- Removed all unicode and emoji characters for maximum terminal compatibility:
  - Degree symbols (°) replaced with "degC" or "deg"
  - Mathematical symbols (≥, ≤, ±, ∞, π, τ, Δ, ∫) replaced with ASCII equivalents (">=", "<=", "+/-", "infinity", "pi", "tau", "delta", "integral")
- Affected files: documentation (JSON_SCHEMA.md, YAML_SCHEMA.md), examples, test files, header comments

## [0.1.0] - 2024-02-16

### Added

**Core Library:**

- `SignalStore` - Type-safe signal storage with unit metadata and physics-driven flags
- `SignalNamespace` - Path-to-ID interning for fast signal lookups
- `FunctionNamespace` - Function registration and lookup
- `DeviceId`, `SignalId` - Type-safe integer handles
- `Variant` - Runtime-typed variant supporting double, string, bool, int64
- `Command` - Typed command structure for device actions

**Transform System:**

- `ITransform` interface for stateful signal transforms
- 8 built-in transforms:
  - `LinearTransform` - Scale, offset, and clamping
  - `FirstOrderLagTransform` - Exponential smoothing with configurable time constant
  - `DelayTransform` - Time-delayed signal with circular buffer
  - `NoiseTransform` - Gaussian white noise with optional seed
  - `SaturationTransform` - Min/max clamping
  - `DeadbandTransform` - Threshold-based zeroing
  - `RateLimiterTransform` - Rate of change limiting
  - `MovingAverageTransform` - Sliding window average (FIR filter)

**Physics Models:**

- `IModel` interface with stability limits
- `ThermalMassModel` - Lumped capacitance heat equation (Forward Euler integration)

**Graph System:**

- `GraphSpec` - Protocol-agnostic POD structure for graph definition
- `GraphCompiler` - Topological sort, cycle detection, stability validation
- `Engine` - Five-stage deterministic tick execution:
  1. Snapshot inputs
  2. Process edges (topological order)
  3. Update models
  4. Commit outputs
  5. Evaluate rules

**Optional Loaders:**

- JSON graph loader (`load_json_file`, `load_json_string`)
  - Requires `-DFLUXGRAPH_JSON_ENABLED=ON`
  - Uses nlohmann/json v3.11.3 (header-only, PRIVATE linkage)
- YAML graph loader (`load_yaml_file`, `load_yaml_string`)
  - Requires `-DFLUXGRAPH_YAML_ENABLED=ON`
  - Uses yaml-cpp master branch (static lib, PRIVATE linkage)

**Testing:**

- 153 tests for core library (zero dependencies)
- 162 tests with JSON or YAML loader enabled
- 171 tests with both loaders enabled
- 19 analytical validation tests:
  - FirstOrderLag vs exp(-t/tau): 1e-3 tolerance
  - ThermalMass vs heat equation: 0.1 degC tolerance
  - Delay: 1e-6 exact time-shift
  - Linear, Saturation, Deadband, RateLimiter, MovingAverage: exact validation

**Examples:**

- `01_basic_transform` - Simple linear transform
- `02_thermal_mass` - Physics simulation with thermal mass model
- `03_json_graph` - Load thermal chamber graph from JSON file
- `04_yaml_graph` - Load thermal chamber graph from YAML file

**Documentation:**

- API reference (`docs/API.md`)
- JSON schema documentation (`docs/JSON_SCHEMA.md`)
- YAML schema documentation (`docs/YAML_SCHEMA.md`)
- Embedding guide (`docs/EMBEDDING.md`)
- Transform reference (`docs/TRANSFORMS.md`)

**Build System:**

- CMake 3.20+ build system
- Conditional compilation for optional loaders
- FetchContent for automatic dependency management
- CMake export configuration (`cmake/fluxgraphConfig.cmake.in`)

### Changed

- N/A (initial release)

### Deprecated

- N/A (initial release)

### Removed

- N/A (initial release)

### Fixed

- N/A (initial release)

### Security

- N/A (initial release)

## Design Philosophy

FluxGraph follows these principles:

1. **Zero-dependency core** - Core library has no external dependencies
2. **Protocol-agnostic** - No assumptions about YAML, gRPC, or protobuf
3. **Single-writer design** - No internal synchronization overhead
4. **Embeddable** - Works in any C++ host application
5. **Scientific rigor** - Dimensional analysis, topological correctness, stability validation
6. **Modern C++** - C++17 with clean, idiomatic API

---

[0.1.1]: https://github.com/FEASTorg/fluxgraph/releases/tag/v0.1.1
[0.1.0]: https://github.com/FEASTorg/fluxgraph/releases/tag/v0.1.0
[unreleased]: https://github.com/FEASTorg/fluxgraph/compare/v0.1.1...HEAD

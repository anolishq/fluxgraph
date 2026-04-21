# Changelog

All notable changes to FluxGraph will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.3] - 2026-04-21

### CI

- Pin org reusable workflow refs from `@main` to `@v1`.
- Add metrics collection to release workflow; `metrics.json` uploaded as release asset on each `v*` tag.

## [1.0.2] - 2026-04-20

### Added

- gRPC server (`fluxgraph-server`): compiles and runs FluxGraph as a network service,
  accepting `LoadGraph`, `Step`, `WriteSignal`, `ReadSignal`, and `Subscribe` RPCs.
  Optional; built via `add_subdirectory(server)`.
- Server write-authority enforcement rejecting writes to protected model-owned and
  edge-derived signals.
- Server `--dt` flag wired into runtime timestep and compile-time stability
  validation.
- `unit_convert` transform: explicit registry-derived cross-unit conversion with
  `to_unit` and optional `from_unit` assertion.
- `state_space_siso_discrete` built-in model: structured `A_d`, `B_d`, `C`, `D`,
  `x0` parameters with compile-time shape validation, analytical tests for
  deterministic trajectory, and reset behavior. SISO example and docs added.
- `dc_motor` model: coupled electrical–mechanical dynamics, curated
  electrical/rotational units, strict compiler signatures, unit and analytical
  tests, Example 9.
- `mass_spring_damper` model: curated mechanical units, compiler signatures, tests,
  example, and docs.
- `PT1` / `PT2` built-in process models: strict `ModelSignature` metadata, minimal
  time units, expanded unit and analytical test coverage.
- `thermal_rc2` two-node thermal model with shared thermal integration utilities,
  docs, tests, and example.
- Dimensional-analysis core: `UnitKind`, `DimensionVector`, `UnitDef`,
  `UnitConversion`; curated `UnitRegistry` with affine temperature conversions and
  absolute/delta boundary checks.
- Compiler dimensional validation policy: `DimensionalPolicy::permissive` and
  `DimensionalPolicy::strict`; strict-mode requires declared LHS signal unit
  contracts.
- Compiled-program signal contract metadata propagated into runtime preload.
- `SignalStore` contract helpers: `write_with_contract_unit`, `has_declared_unit`,
  `declared_unit`.
- Graph schema: explicit top-level `signals` unit contracts in JSON/YAML.
- Structured `ParamValue` / `ParamMap` type for model and transform parameters
  (command/rule args remain scalar `Variant`).
- Centralized parse limits for structured params (depth, node count, collection
  sizes, string size) enforced in JSON/YAML loaders.
- Transform/model registration variants with signature awareness:
  `register_transform_factory_with_signature`, `register_model_factory_with_signature`.
- Rule condition execution: `<`, `<=`, `>`, `>=`, `==`, `!=` comparators (was
  previously hardcoded false).
- Compiler parameter parsing: numeric coercion (`int64 → double`), path-precise
  diagnostics, optional `noise.seed` default, `saturation`/`rate_limiter` aliases.
- Single-writer ownership checks across model outputs and edge targets.
- Runtime stability validation in `Engine::tick` (`dt` must be positive and within
  model stability limits).
- Benchmark evidence tooling: policy profiles (`local`, `ci-hosted`,
  `ci-dedicated`); `scripts/evaluate_benchmarks.py`; CI evidence workflow.
- Numerical validation framework: `thermal_mass` solver strategies
  (`forward_euler`, `rk4`); `scripts/run_numerical_validation.py`; numerical
  validation CI evidence workflow; methodology/evidence docs.
- Dimensional validation automation: `scripts/run_dimensional_validation.py`;
  scheduled/dispatch CI evidence workflow.
- `thermal_mass` integration method policy (`forward_euler`, `rk4`) with
  method-dependent stability, regression, and determinism coverage.
- Expanded test coverage: immediate chain propagation, rule condition emission,
  delay-mediated cycle acceptance, stability validation, server protected-write
  rejection, server `--dt` behavior, `SignalStore` unit-declaration behavior.
- CI: required strict-dimensional-validation lane with artifact upload; Windows
  diagram CI parity; shared docs check workflow.
- Release workflow: on `v*` tag, builds `ci-linux-release-server`, packages
  `fluxgraph-server` binary + source tarball + `manifest.json` + `SHA256SUMS`.

### Changed

- Engine tick semantics: model-first then edge-propagation for immediate
  within-tick signal flow.
- Edge processing writes using target signal contracts (no longer copies source
  unit metadata during propagation).
- Graph compiler: delay-mediated feedback policy detects cycles on the non-delay
  subgraph; topological ordering is deterministic (stable tie-break by `SignalId`).
- Compiler architecture split: built-in transform/model registration is now
  family-scoped.
- Internal helper module and dimensional signature validation extracted to
  dedicated compilation units.
- GoogleTest discovery switched to `POST_BUILD` mode for reliable Visual Studio
  multi-config test registration.
- Org references updated from `feast` / `FEASTorg` to `anolis` / `anolishq`
  throughout.
- Markdownlint config tightened to org canonical ruleset.
- Docs: angle brackets in method signatures escaped for VitePress; case-sensitive
  doc links corrected.

### Fixed

- Rule execution path was non-functional (conditions hardcoded false) — now fully
  wired.
- Stability validation function existed but was not applied during active server
  compile/load path.
- CLI `--dt` was parsed but not applied to service runtime timestep.
- Signal unit contract no longer accidentally locks signals to `"dimensionless"`.
- Windows: `fluxgraph_tests` no longer links both `gtest_main` and `gmock` runtimes
  (was causing zero discovered tests).
- DOT emitter test: match escape-quote form after `TransformSpec::params` typed as
  `ParamValue`.

## [1.0.1] - 2024-02-16

### Fixed

- Removed all Unicode and emoji characters for maximum terminal compatibility:
  degree symbols (`°`) replaced with `degC`/`deg`; mathematical symbols (`≥`, `≤`,
  `±`, `∞`, `π`, `τ`, `Δ`, `∫`) replaced with ASCII equivalents. Affected files:
  documentation, examples, tests, header comments.

## [1.0.0] - 2024-02-16

Initial anolishq release. Core library stable; gRPC server scaffolded.
See `[0.1.1]` and `[0.1.0]` below for historical FEASTorg-era feature inventory.

### Added

- CMake export configuration (`cmake/fluxgraphConfig.cmake.in`).
- v1.0.0 API documentation update.

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

[0.1.1]: https://github.com/anolishq/fluxgraph/releases/tag/v0.1.1
[0.1.0]: https://github.com/anolishq/fluxgraph/releases/tag/v0.1.0
[unreleased]: https://github.com/anolishq/fluxgraph/compare/v0.1.1...HEAD

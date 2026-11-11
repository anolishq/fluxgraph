# Changelog

All notable changes to FluxGraph will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-11-11

1.1.0 is a minor release: it adds `CompiledProgram::model_output_signal_ids()`
and changes a build default for embedding projects. The fixes below refuse some
inputs that used to load or run. Each of those was a bug, a silent misload or
undefined behaviour, never a graph that worked, so they are fixes rather than
breaking changes.

Upgrade notes:

- **A malformed graph file can now fail to load.** A `signals`, `models`,
  `edges` or `rules` key that is not an array, a root that is not an object or
  map, and a rule without `actions` used to load as an empty graph or with
  action-less rules. They now fail with a path-qualified error. Fix the file.
- **A `saturation` or `linear` transform with inverted or NaN bounds** now fails
  to compile, and its constructor throws `std::invalid_argument`.
- **`DelayTransform::apply` throws on a `dt` that is not positive and finite.**
  `Engine::tick` with a NaN or infinite `dt` therefore throws when the graph has
  a delay edge.
- **A delay's tick count can differ by one** where `delay_sec / dt` is meant to
  be a half but its floating-point quotient lands just below it, and after a
  `dt` change the delay now follows `delay_sec`.
- **Through `fluxgraph-server`, a write to any model output** is refused with
  `PERMISSION_DENIED`, not only to `thermal_mass` outputs.
- **An embedding project that relied on fluxgraph's tests or examples being
  built** as a subproject must now set `FLUXGRAPH_BUILD_TESTS` or
  `FLUXGRAPH_BUILD_EXAMPLES` to ON.

### Added

- `CompiledProgram::model_output_signal_ids()` returns every compiled model's
  `output_signal_ids()`, in model order. (#148)

### Changed

- `FLUXGRAPH_BUILD_TESTS` and `FLUXGRAPH_BUILD_EXAMPLES` default to OFF when
  fluxgraph is added with `add_subdirectory` or `FetchContent`, so an embedding
  project no longer needs GTest or builds the examples. They still default to
  ON when fluxgraph is the top-level project. (#119)

### Fixed

- The `saturation` and `linear` transforms rejected nothing about their bounds:
  `min > max` (or `clamp_min > clamp_max`) reached `std::clamp`, which is
  undefined behaviour (every input came out as `max`, or the process aborted
  under `_GLIBCXX_ASSERTIONS`), and a NaN bound silently disabled that side of
  the clamp. Compiling such an edge now fails with
  `Invalid parameter at transform[saturation]/...` (or `transform[linear]/...`),
  and the `SaturationTransform` and `LinearTransform` constructors throw
  `std::invalid_argument`. Equal bounds and the default infinite `linear`
  bounds still work. (#145)

- The JSON and YAML loaders silently skipped a structural field of the wrong
  type, so a malformed file loaded as an empty graph or with action-less rules.
  These inputs loaded before and now fail with a path-qualified error:
  - a top-level `signals`, `models`, `edges` or `rules` key that is present but
    not an array (JSON) / sequence (YAML), including a null value such as a
    bare `rules:`
  - a JSON root that is not an object (an array, a scalar, `null`)
  - a YAML root that is not a map, including a null document: `~`, `null`, a
    bare `---`, or a lone `...` (yaml-cpp reads each as one document with null
    content)
  - a rule whose `actions` is missing or not an array / sequence (`actions` is
    required, and may be empty)

  Input with no document at all (empty, or only whitespace and comments) still
  loads as an empty graph, and every other file that loaded before still loads
  unchanged. (#147)

- The gRPC server protected and marked `physics_driven` only `thermal_mass`
  `temp_signal` outputs. `UpdateSignals` accepted writes to outputs of every
  other model type (`dc_motor`, `mass_spring_damper`, `thermal_rc2`, ...) and
  the next tick overwrote them, and `ReadSignals` reported those outputs as not
  physics-driven after `LoadConfig` or `Reset`. The server now takes the set
  from `CompiledProgram::model_output_signal_ids()`: writes to any model output
  return `PERMISSION_DENIED`, and every model output is physics-driven from
  load and after `Reset`. (#148)

- `DelayTransform` applied the wrong delay after `dt` changed: it kept the
  sample count from the earlier `dt` (a 1 s delay settled at 5 s after `dt` went
  from 0.1 s to 0.5 s) or held one stale value after `dt` shrank. Samples now
  carry their time, and the output is the stored input nearest
  `t - delay_sec`, so the delay follows `delay_sec` across `dt` changes.
  `apply()` with a `dt` that is not positive and finite (`dt <= 0`, NaN,
  ±inf) now throws `std::runtime_error` and leaves the delay's state unchanged,
  instead of computing `llround(inf)` or `llround(NaN)`. `Engine::tick` still
  passes a NaN `dt` (and a +inf `dt` when no model has a finite stability
  limit) to the transforms, so a delay edge makes such a tick throw. By then the
  models and any earlier edges have already run with that `dt`, so a NaN `dt`
  still leaves model outputs such as `thermal_mass` temperatures at NaN for
  good. That is existing `Engine::tick` behaviour, not changed here. The unused
  `time_accumulated_` member is gone. (#146)
- At a constant `dt` the delay's tick count can differ by one from previous
  releases where `delay_sec / dt` is meant to be a half but its floating-point
  quotient lands just below it. The count is now `delay_sec / dt` rounded with
  halves going up (to the older sample), so `0.15 / 0.1` (which evaluates to
  1.4999999999999998) gives 2 ticks where `llround` gave 1. Other ratios keep
  the `max(1, llround(delay_sec / dt))` count, and the count stays fixed over
  long runs. (#146)

### CI

- Build the `linux-x86_64` release binary on `ubuntu-24.04` again (it had moved
  to `ubuntu-26.04`), and fail the release when the packaged `fluxgraph-server`
  needs a `GLIBC_` newer than 2.41, a `GLIBCXX_` newer than 3.4.33 or a
  `CXXABI_` newer than 1.3.15, the versions Debian 13 ships. The check is
  `scripts/check-glibc-floor.sh`, tested in CI by
  `tests/scripts/check-glibc-floor-test.sh`. (#159)
- The weekly dimensional validation evidence workflow restores the vcpkg
  binary cache but no longer saves it. It builds only gtest under the
  x64-linux key the server-enabled lane saves with grpc; finishing first after
  a cache key change, it would leave that lane unable to save and later jobs,
  clang-tidy among them, building grpc from source.

## [1.0.6] - 2026-07-04

Maintenance release — CI, docs, and a one-time source reformat; no library
behavior changes.

### Changed

- Adopt C++20 `std::format` for diagnostics and general clang hygiene. (#66)
- One-time repo-wide clang-format reformat under the shared org config set;
  `.git-blame-ignore-revs` points at the squashed reformat commit. (#55, #56)

### CI

- Promote the clang-tidy diff gate to blocking and fold it into `ok`; lint the
  full C++ surface via the `ci-linux-tidy` preset; pin clang-format /
  clang-tools; standardize on `setup-vcpkg` v2.2+; routine dependency
  maintenance.

### Documentation

- Add `AGENTS.md`; use the public install path; prune completed TODO items;
  reconcile README/CHANGELOG version references. (#67, #72, #76)

## [1.0.5] - 2026-06-16

### Changed

- Bump the vcpkg baseline to the vcpkg `2026.06.01` release: protobuf
  `5.29.5` → `6.33.4`, grpc `1.71.0` → `1.76.0`, abseil and the rest refreshed.
  No source changes required.
- Centralize the vcpkg pin: the shared `setup-vcpkg` action now derives the
  vcpkg commit from `vcpkg-configuration.json`, so the per-workflow
  `VCPKG_COMMIT` env was removed.

### Fixed

- Windows builds broke when GitHub migrated the `windows-2025` runner image
  from Visual Studio 2022 to Visual Studio 2026 (rollout 2026-06-08..06-15),
  removing the `Visual Studio 17 2022` generator. Migrated the MSVC preset to
  generator `Visual Studio 18 2026` with toolset `v145`, renamed the overlay
  triplet `x64-windows-v143` -> `x64-windows-v145`, and updated the `triplet`
  inputs in CI/evidence workflows accordingly.

### CI

- Surface CMake configure/build output in the numerical, benchmark, and
  dimensional evidence workflows: runner scripts now echo captured stdout/stderr
  on failure, and artifact uploads run with `if: always()` (and
  `if-no-files-found: warn`) so partial evidence is retained when a step fails
  early.
- Add CI OK aggregator gate: removed `paths-ignore`, added `dorny/paths-filter`
  to detect code-vs-docs changes, gated all jobs behind the filter, and added a
  final `ok` job as the sole required status check for `main` branch protection.

## [1.0.4] - 2026-04-23

### Fixed

- `include/fluxgraph/version.hpp` and `vcpkg.json` were stale at `0.1.1`; both
  aligned to `1.0.3` to match `CMakeLists.txt`.

### CI

- Version-sync check wired: `version-locations.txt` added tracking `CMakeLists.txt`,
  `include/fluxgraph/version.hpp`, and `vcpkg.json`; CI calls reusable `version-sync`
  workflow from `anolishq/.github`.
- `.anpkg` added to `.gitignore`.

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

[Unreleased]: https://github.com/anolishq/fluxgraph/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/anolishq/fluxgraph/compare/v1.0.6...v1.1.0
[1.0.6]: https://github.com/anolishq/fluxgraph/compare/v1.0.5...v1.0.6
[1.0.5]: https://github.com/anolishq/fluxgraph/compare/v1.0.4...v1.0.5
[1.0.4]: https://github.com/anolishq/fluxgraph/compare/v1.0.3...v1.0.4
[1.0.3]: https://github.com/anolishq/fluxgraph/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/anolishq/fluxgraph/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/anolishq/fluxgraph/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/anolishq/fluxgraph/compare/v0.1.1...v1.0.0
[0.1.1]: https://github.com/anolishq/fluxgraph/releases/tag/v0.1.1
[0.1.0]: https://github.com/anolishq/fluxgraph/releases/tag/v0.1.0

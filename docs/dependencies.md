# Dependency, Build, and CI Governance

This document defines FluxGraph policy for dependency management, preset usage, CI lanes, and versioning.

## vcpkg Policy

1. `vcpkg-configuration.json` is the canonical baseline source.
2. `builtin-baseline` is not used.
3. Lockfile pinning is deferred for now; baseline pinning stays in `vcpkg-configuration.json` (org decision tracked in anolishq/.github#93).

## Dependency Model Policy

- Governed dependencies are resolved via vcpkg + `find_package(...)`.
- Optional loader behavior is controlled by `FLUXGRAPH_JSON_ENABLED` and `FLUXGRAPH_YAML_ENABLED`.
- Dependency transport changes must not regress OFF/ON loader build combinations.

## Python Dependency Policy

1. CI installs Python integration dependencies from `requirements-lock.txt`.
2. `requirements.txt` remains a maintainer-facing range file; lockfile is execution source.
3. Lockfile and range updates must be reviewed together in the same PR.

## Versioning Policy

- FluxGraph follows independent SemVer (`MAJOR.MINOR.PATCH`).
- Public API, schema, or build-surface changes require version-bump decision and changelog note.

## CI Lane Tiers

- **Required**: Linux core build/test lane, Linux diagram-dot lane, Windows core build/test lane, Windows diagram-dot lane, and diagram render smoke lane.
- **Advisory/matrix**: Linux JSON, YAML, and server-enabled lanes.
- **Optional heavy lanes**: extended sanitizer/stress/integration runs.

## Preset Baseline and Exception Policy

Baseline names:

- `dev-debug`, `dev-release`, `ci-linux-release`, `ci-windows-release`
- specialized as supported: `ci-asan`, `ci-ubsan`, `ci-tsan`, `ci-coverage`

Rules:

1. CI should call presets directly.
2. CI-only deviations must be explicit and documented.
3. Repo-specific extension presets are allowed for feature matrices.
4. Every preset must have an active owner/use-case (CI lane, script default, or documented workflow); remove unreferenced presets.

## Dual-Run Policy

During migration of legacy paths:

- run legacy and new paths in parallel,
- minimum 5 consecutive green runs,
- preferred 10 runs before removing legacy paths.

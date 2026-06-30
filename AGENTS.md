# AGENTS.md — fluxgraph

> Per-repo conventions for coding agents (Claude Code, OpenCode, …). The
> canonical cross-repo rules — Conventional Commits, minimal-first/YAGNI, no
> secrets, run checks before asserting success — live in the user's **global**
> `AGENTS.md` and are not repeated here. This file records only what is
> **specific to this repo**: the commands, the gate, and the non-obvious things
> agents get wrong here.

C++20 physics-simulation library used by Anolis providers.

## Build / test

- Configure + build: `cmake --preset ci-linux-release` then
  `cmake --build --preset ci-linux-release`; test with `ctest`.
- Whole-repo clang-tidy uses the `ci-linux-tidy` preset.
- Optional-feature lanes have their own presets (e.g. `ci-linux-release-json`,
  `ci-linux-release-yaml`, `ci-linux-release-server`,
  `ci-linux-release-diagram`).
- The required CI status check is the **`ok`** job (it aggregates the lanes);
  never bypass it, and never merge red.

## Tooling

- **C++ repos:** clang-format / clang-tidy are pinned to **18.1.8** via the
  shared `setup-clang-tools` action (install the same pinned binary locally) — do NOT use
  pip/apt/pre-commit/container versions. Run `clang-format -i` before **every**
  commit (CI fails otherwise).
- Shared `.github` actions/workflows are SHA-pinned with a `# <tag>` comment so
  Renovate can track them — keep that comment when bumping.

## Repo-specific gotchas

- **C++20**, and use **`std::format`** for diagnostics/log messages.
- **The CORE is zero-dependency and must stay that way.** Optional features pull
  deps and are gated behind CMake options (all default `OFF`):
  `FLUXGRAPH_BUILD_SERVER` → gRPC, `FLUXGRAPH_JSON_ENABLED` → nlohmann/json,
  `FLUXGRAPH_YAML_ENABLED` → yaml-cpp, `FLUXGRAPH_BUILD_DIAGRAM_TOOL` → dot.
  Never let a dependency leak into the core target.
- **Embedded-friendly:** the library is host-built in CI but targets embedded
  use — avoid host-only assumptions (no exceptions-required APIs in the core
  path, no heap-only design without need, etc.).
- **`include/fluxgraph/version.hpp` is the canonical version.** It carries split
  macros (`FLUXGRAPH_VERSION_MAJOR/MINOR/PATCH`) *and* the
  `FLUXGRAPH_VERSION` string — keep all four in sync when bumping.

## Backlog

Backlog lives in GitHub issues, not a `TODO.md`.

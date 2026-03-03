# Graph Visualization Contract (Phase 4 Stub)

**Status:** Phase 4 contract; Sprint 4.2 DOT baseline implemented.  
**Purpose:** lock the visualization interface and behavior before coding to prevent drift in tests and CLI behavior.

## 1. Scope

This phase adds an optional graph-diagram toolchain that:

1. takes FluxGraph graph definitions (JSON/YAML via existing loaders, or direct `GraphSpec` in C++),
2. produces deterministic DOT output as the canonical artifact,
3. optionally renders DOT to image formats using external Graphviz CLI tooling.

## 2. Non-Goals (Phase 4)

1. Live runtime graph tracing or time-series overlays.
2. Interactive web UI or editor.
3. Round-trip authoring (diagram back to schema).
4. Core runtime dependency on Graphviz libraries.

## 3. Build and Dependency Contract

1. Feature flag: `FLUXGRAPH_BUILD_DIAGRAM_TOOL` (default `OFF`).
2. No new vcpkg feature is required for the CLI-renderer path in Phase 4.
3. Rendering uses external `dot` process when image output is requested.
4. Core `fluxgraph` library dependency contract remains unchanged.

## 4. Architecture Contract

Planned split:

1. `viz-core`: pure C++ emitter (`GraphSpec -> DOT`), no third-party dependencies.
2. `fluxgraph-diagram` CLI: input parsing/validation, file I/O, optional renderer invocation.

`viz-core` depends on FluxGraph public graph spec types (`GraphSpec`, `ModelSpec`, `EdgeSpec`, `RuleSpec`) and does not depend on runtime engine internals.

## 5. C++ API Sketch (for Direct Integrator Use)

Planned public surface (names may be finalized during implementation, contract intent is stable):

```cpp
#include <fluxgraph/graph/spec.hpp>
#include <string>

namespace fluxgraph::viz {

struct DotEmitOptions {
    bool include_models = true;
    bool include_rules = true;
};

std::string emit_dot(const GraphSpec& spec, const DotEmitOptions& options = {});

} // namespace fluxgraph::viz
```

Contract guarantees:

1. `emit_dot` is deterministic for the same `GraphSpec` and options.
2. Resulting DOT is syntactically valid for Graphviz `dot`.

## 6. DOT Emission Policy (Determinism + Escaping)

## 6.1 Identifier and Label Escaping

1. Emitter always writes node IDs and edge labels as quoted DOT strings.
2. Escape rules:
- `\` -> `\\`
- `"` -> `\"`
- newline -> `\n`
3. Signal paths containing `/`, `.`, spaces, or other punctuation are valid and must be preserved via quoting.

## 6.2 Ordering Rules

1. Node emission order: lexicographic by canonical node ID.
2. Edge emission order: lexicographic by tuple `(source_id, target_id, transform_type, transform_label)`.
3. Attribute key ordering: lexicographic by key name.

No reliance on container insertion order is allowed for canonical DOT output.

## 6.3 Unknown and Extension Types

1. Unknown transform types are rendered (not dropped) using raw `type` text in edge annotation.
2. Unknown transform types do not fail DOT generation unless required fields are structurally invalid.
3. CLI should emit a non-fatal warning for unknown transform types.

## 7. CLI Contract Phasing

Sprint 4.2 baseline:

1. DOT output is supported.
2. If `--format` is supplied with `svg` or `png`, CLI returns explicit unsupported-format error.

Sprint 4.3 extension:

1. Enable `--format svg|png` via Graphviz CLI invocation.
2. If renderer is unavailable or fails, return renderer error with actionable message.

Exit code contract (planned):

1. `0`: success
2. `1`: input/load/validation failure
3. `2`: unsupported option/format for current build
4. `3`: renderer invocation failure

Current implementation status:

1. DOT emission is implemented.
2. Non-DOT `--format` values return unsupported-format errors.
3. Renderer invocation is deferred to Sprint 4.3.

## 8. Evidence and Governance Mapping

Planning source for claim-evidence governance: `working/archive/claim_evidence_matrix.md`.

Visualization claims and expected evidence for this phase:

1. "Deterministic DOT output": unit tests + golden fixtures.
2. "Core isolation": build verification with tool flag OFF.
3. "Optional rendering": advisory CI smoke render lane.

This section must be updated with concrete test references once implementation lands.

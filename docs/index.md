# FluxGraph documentation

FluxGraph is a C++20 library for physics simulation. You describe a system as
a graph of signals, transforms and models, and FluxGraph runs it one tick at a
time with deterministic results. Signals carry units, and an optional strict
compile policy rejects a graph with an undeclared or incompatible unit.
Graphs are built in C++, or loaded from JSON or YAML when the optional loaders
are enabled. An optional gRPC server, `fluxgraph-server`, runs a graph as a
standalone process.

FluxGraph is a standalone library; the Anolis runtime does not depend on it.
In Anolis, the
[simulation provider](https://github.com/anolishq/anolis-provider-sim) uses it
in `sim` mode: built with `ENABLE_FLUXGRAPH=ON`, the provider connects to
`fluxgraph-server` over gRPC and drives its simulated devices from the graph.

## Using FluxGraph

- [Embedding](EMBEDDING.md): add FluxGraph to a CMake project, enable the
  loaders, and register custom transforms and models.
- [API reference](api-reference.md): the C++ classes and functions.
- [JSON schema](schema-json.md): the graph file format read by the JSON
  loader.
- [YAML schema](schema-yaml.md): the same format in YAML.
- [Transforms](TRANSFORMS.md): each built-in transform, its parameters and
  behaviour.
- [State-space SISO discrete model](state-space-siso-discrete.md): parameters
  and validation for the `state_space_siso_discrete` model.
- [Graph visualization](graph-visualization.md): the optional tool that
  writes a graph as Graphviz DOT and renders it to an image.

## Behaviour and design

- [Semantics specification](semantics_spec.md): the normative contract for
  tick ordering, delays, signal ownership and units.
- [Architecture](ARCHITECTURE.md): how the library is built and why.
- [Numerical methods](numerical-methods.md): integration methods for ODE
  models and their stability limits.

## Evidence

- [Validation methodology](validation-methodology.md): how integration
  accuracy is measured against analytical solutions.
- [Performance benchmarks](performance-benchmarks.md): the benchmark
  executables and how to run them reproducibly.

## Development

- [Dependencies](dependencies.md): dependency, preset, CI and versioning
  policy.
- [Developer notes](dev-notes.md): background reading on graph signal
  processing.

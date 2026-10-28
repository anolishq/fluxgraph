# FluxGraph

[![CI](https://github.com/anolishq/fluxgraph/actions/workflows/ci.yml/badge.svg)](https://github.com/anolishq/fluxgraph/actions/workflows/ci.yml)

FluxGraph is a C++20 library for physics simulation, built to be embedded in a
host application. You describe a system as a graph of signals, transforms and
models. FluxGraph compiles the graph into a fixed order and runs it one tick at
a time with deterministic results.

The core library has no external dependencies. Optional loaders read graphs
from JSON or YAML, and an optional gRPC server, `fluxgraph-server`, runs a
graph as a standalone process. The signal store is single-writer and has no
internal locking: one thread calls `engine.tick()`.

FluxGraph does not depend on Anolis, and the Anolis runtime does not depend on
FluxGraph. In Anolis, the
[simulation provider](https://github.com/anolishq/anolis-provider-sim) uses it
in `sim` mode: built with `ENABLE_FLUXGRAPH=ON`, the provider connects to
`fluxgraph-server` over gRPC and drives its simulated devices from the graph.

## Add it to a CMake project

Fetch a release source tarball with `FetchContent` and link the `fluxgraph`
target:

```cmake
include(FetchContent)
FetchContent_Declare(
    fluxgraph
    URL https://github.com/anolishq/fluxgraph/releases/download/v1.0.6/fluxgraph-1.0.6-source.tar.gz
)
set(FLUXGRAPH_BUILD_TESTS OFF)     # v1.0.6 builds tests by default, and tests need GTest
set(FLUXGRAPH_BUILD_EXAMPLES OFF)
FetchContent_MakeAvailable(fluxgraph)
target_link_libraries(your_target PRIVATE fluxgraph)
target_compile_features(your_target PRIVATE cxx_std_20)
```

Replace `v1.0.6` with the
[latest release](https://github.com/anolishq/fluxgraph/releases/latest) tag.
The namespaced target `fluxgraph::fluxgraph` exists only when you use
`find_package(fluxgraph)` against an installed package.

[Embedding](docs/EMBEDDING.md) covers the loaders, custom transforms and
models, and threading.

## Run the server

Each release has a Linux x86_64 build of `fluxgraph-server`:

```bash
VERSION=$(curl -fsSL https://api.github.com/repos/anolishq/fluxgraph/releases/latest | grep '"tag_name"' | sed 's/.*"v\([^"]*\)".*/\1/')
curl -fsSL "https://github.com/anolishq/fluxgraph/releases/download/v${VERSION}/fluxgraph-${VERSION}-linux-x86_64.tar.gz" \
  | tar -xz
./bin/fluxgraph-server --help
```

## Minimal example

This graph has one edge that applies `2x + 1` to a signal:

```cpp
#include <fluxgraph/engine.hpp>
#include <fluxgraph/core/signal_store.hpp>
#include <fluxgraph/core/namespace.hpp>
#include <fluxgraph/graph/compiler.hpp>

int main() {
    // 1. Create namespaces and signal store
    fluxgraph::SignalNamespace sig_ns;
    fluxgraph::FunctionNamespace func_ns;
    fluxgraph::SignalStore store;

    // 2. Build graph specification
    fluxgraph::GraphSpec spec;
    fluxgraph::EdgeSpec edge;
    edge.source_path = "sensor.voltage_in";
    edge.target_path = "sensor.voltage_out";
    edge.transform.type = "linear";
    edge.transform.params["scale"] = 2.0;
    edge.transform.params["offset"] = 1.0;
    spec.edges.push_back(edge);

    // 3. Compile and load
    fluxgraph::GraphCompiler compiler;
    auto program = compiler.compile(spec, sig_ns, func_ns);
    fluxgraph::Engine engine;
    engine.load(std::move(program));

    // 4. Get signal ports
    auto input_sig = sig_ns.resolve("sensor.voltage_in");
    auto output_sig = sig_ns.resolve("sensor.voltage_out");

    // 5. Simulation loop
    store.write(input_sig, 5.0, "V");
    engine.tick(0.1, store);
    double result = store.read_value(output_sig);  // 11.0V (2*5 + 1)

    return 0;
}
```

[`examples/`](examples/) has complete programs:

- [`01_basic_transform`](./examples/01_basic_transform/): signal transform
- [`02_thermal_mass`](./examples/02_thermal_mass/): thermal mass model
- [`03_json_graph`](./examples/03_json_graph/): load a graph from JSON
- [`04_yaml_graph`](./examples/04_yaml_graph/): load a graph from YAML
- [`05_thermal_rc2`](./examples/05_thermal_rc2/): two-node thermal RC model
- [`06_first_order_process`](./examples/06_first_order_process/): first-order
  process (PT1)
- [`07_second_order_process`](./examples/07_second_order_process/):
  second-order process (PT2)
- [`08_mass_spring_damper`](./examples/08_mass_spring_damper/): translational
  mass-spring-damper
- [`09_dc_motor`](./examples/09_dc_motor/): armature-controlled DC motor
- [`10_state_space_siso_discrete`](./examples/10_state_space_siso_discrete/):
  discrete-time state-space model

## Build from source

Requirements:

- CMake 3.20 or later, or 4.2 or later for the Windows presets
- A C++20 compiler with `std::format`: GCC 13+, Clang 17+ with libc++ 17+ or
  libstdc++ 13+, or MSVC 19.32+ (Visual Studio 2022 17.2+)
- vcpkg, with `VCPKG_ROOT` set
- For the Windows presets, Visual Studio 2026: they use the
  `Visual Studio 18 2026` generator with toolset `v145`

On Linux:

```bash
git clone https://github.com/anolishq/fluxgraph.git
cd fluxgraph
export VCPKG_ROOT=/path/to/vcpkg
cmake --preset dev-release
cmake --build --preset dev-release
ctest --preset dev-release
```

On Windows, in PowerShell:

```powershell
$env:VCPKG_ROOT = "D:\Tools\vcpkg"
cmake --preset dev-windows-release
cmake --build --preset dev-windows-release --config Release
ctest --preset dev-windows-release
```

Dependencies come from the vcpkg manifest. [Dependencies](docs/dependencies.md)
covers the vcpkg baseline, presets and CI lanes.

### Build options

| Option | Default | Effect |
| --- | --- | --- |
| `FLUXGRAPH_JSON_ENABLED` | OFF | JSON graph loader (needs nlohmann-json) |
| `FLUXGRAPH_YAML_ENABLED` | OFF | YAML graph loader (needs yaml-cpp) |
| `FLUXGRAPH_BUILD_DIAGRAM_TOOL` | OFF | `fluxgraph-diagram` CLI and DOT emitter |
| `FLUXGRAPH_BUILD_SERVER` | OFF | `fluxgraph-server` gRPC server (needs grpc and protobuf) |
| `FLUXGRAPH_BUILD_TESTS` | ON at top level, OFF as a subproject | Unit tests (needs GTest) |
| `FLUXGRAPH_BUILD_EXAMPLES` | ON at top level, OFF as a subproject | Example programs |

In v1.0.6 and earlier, tests and examples default to ON even as a subproject.
The presets set their own values: the `base` preset, which the others inherit,
turns tests on and examples off, and the `dev-*` presets turn examples on.

### Diagram tool

`fluxgraph-diagram` writes a graph as DOT, or renders it to SVG or PNG. A
`.json` input needs `FLUXGRAPH_JSON_ENABLED=ON`. SVG and PNG output need
Graphviz `dot`, found on `PATH` unless `--dot-bin` is given.

```bash
cmake --preset dev-release -DFLUXGRAPH_BUILD_DIAGRAM_TOOL=ON -DFLUXGRAPH_JSON_ENABLED=ON
cmake --build --preset dev-release
./build/dev-release/tools/fluxgraph-diagram \
  --in ./examples/03_json_graph/graph.json \
  --out ./graph.svg \
  --format svg
```

[Graph visualization](docs/graph-visualization.md) lists every flag.

## License

AGPL-3.0. See [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Changes are recorded in the
[CHANGELOG](CHANGELOG.md).

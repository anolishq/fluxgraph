# FluxGraph

[![CI](https://github.com/anolishq/fluxgraph/actions/workflows/ci.yml/badge.svg)](https://github.com/anolishq/fluxgraph/actions/workflows/ci.yml)

**A protocol-agnostic physics simulation library for embedded systems.**

FluxGraph is a standalone C++ library that provides signal storage, graph compilation,
transforms, models, and deterministic tick execution. FluxGraph enables embeddable
physics simulation in any C++ host application.

## Features

- **Zero dependencies** - Core library has no external dependencies
- **Protocol-agnostic** - No assumptions about YAML, gRPC, or protobuf in core
- **Single-writer design** - No internal synchronization overhead
- **Embeddable** - Works in any C++ host application
- **Scientific rigor** - Dimensional analysis, topological correctness, stability validation
- **C++17** - Modern C++ with clean API

## Quick Start

### Use as a library (recommended)

FluxGraph is a header + compiled library. The easiest way to consume it is via CMake FetchContent
pointing at a tagged release tarball:

```cmake
include(FetchContent)
FetchContent_Declare(
    fluxgraph
    URL https://github.com/anolishq/fluxgraph/releases/download/v1.0.4/fluxgraph-1.0.4-source.tar.gz
)
FetchContent_MakeAvailable(fluxgraph)
target_link_libraries(your_target PRIVATE fluxgraph::fluxgraph)
```

Replace `v1.0.4` with the [latest release](https://github.com/anolishq/fluxgraph/releases/latest) tag.

**FluxGraph server binary** (standalone gRPC simulation server):

```bash
VERSION=$(curl -fsSL https://api.github.com/repos/anolishq/fluxgraph/releases/latest | grep '"tag_name"' | sed 's/.*"v\([^"]*\)".*/\1/')
curl -fsSL "https://github.com/anolishq/fluxgraph/releases/download/v${VERSION}/fluxgraph-${VERSION}-linux-x86_64.tar.gz" \
  | tar -xz
./bin/fluxgraph-server --help
```

### Build from source (contributors)

#### Prerequisites

- CMake 3.20 or later
- C++17 compatible compiler (MSVC 2019+, GCC 9+, Clang 10+)

#### Building

```bash
# Clone
git clone https://github.com/anolishq/fluxgraph.git
cd fluxgraph

# Prerequisite
export VCPKG_ROOT=/path/to/vcpkg

# Configure + build (preset-first)
cmake --preset dev-release
cmake --build --preset dev-release

# Run tests
ctest --preset dev-release
```

```powershell
# Windows (MSVC presets)
$env:VCPKG_ROOT = "D:\\Tools\\vcpkg"
cmake --preset dev-windows-release
cmake --build --preset dev-windows-release --config Release
ctest --preset dev-windows-release
```

### Build Options

Optional graph loaders can be enabled:

| Option                   | Default | Description                                       |
| ------------------------ | ------- | ------------------------------------------------- |
| `FLUXGRAPH_BUILD_DIAGRAM_TOOL` | OFF | Build optional graph diagram CLI + DOT emitter |
| `FLUXGRAPH_JSON_ENABLED` | OFF     | Enable JSON graph loader (requires nlohmann-json) |
| `FLUXGRAPH_YAML_ENABLED` | OFF     | Enable YAML graph loader (requires yaml-cpp)      |

Dependency/build/CI governance: [docs/dependencies.md](docs/dependencies.md).

Dependencies are resolved via vcpkg manifests and `find_package(...)` (no FetchContent drift in CI).

### Diagram Tool (Optional)

With `FLUXGRAPH_BUILD_DIAGRAM_TOOL=ON`, `fluxgraph-diagram` can emit DOT and optional rendered images:

```bash
./build/dev-release/tools/fluxgraph-diagram \
  --in ./examples/03_json_graph/graph.json \
  --out ./graph.svg \
  --format svg
```

See [docs/graph-visualization.md](docs/graph-visualization.md) for full contract and flags.

### Using FluxGraph

See [`examples/`](examples/) for complete usage patterns. Here's a minimal example:

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

**More examples:**

- [`01_basic_transform`](./examples/01_basic_transform/) - Simple signal transformation
- [`02_thermal_mass`](./examples/02_thermal_mass/) - Physics simulation with models
- [`03_json_graph`](./examples/03_json_graph/) - Load graph from JSON file
- [`04_yaml_graph`](./examples/04_yaml_graph/) - Load graph from YAML file
- [`05_thermal_rc2`](./examples/05_thermal_rc2/) - Two-node thermal RC model example
- [`06_first_order_process`](./examples/06_first_order_process/) - First-order process primitive (PT1)
- [`07_second_order_process`](./examples/07_second_order_process/) - Second-order process primitive (PT2)
- [`08_mass_spring_damper`](./examples/08_mass_spring_damper/) - Translational mass-spring-damper model example
- [`09_dc_motor`](./examples/09_dc_motor/) - Armature-controlled DC motor model example
- [`10_state_space_siso_discrete`](./examples/10_state_space_siso_discrete/) - Structured discrete-time state-space model example

## Project Structure

```txt
fluxgraph/
+-- include/fluxgraph/     # Public API headers
|   +-- core/              # Core types, signal storage, namespaces
|   +-- transform/         # Signal transforms
|   +-- model/             # Physics models
+-- src/                   # Implementation
+-- tests/                 # Unit and analytical tests
+-- examples/              # Example applications
+-- docs/                  # Documentation
```

## License

AGPL v3 License - See [LICENSE](LICENSE) for details

## Contributing

This project is part of the Anolis ecosystem. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Related Projects

- [anolis-provider-sim](https://github.com/anolishq/anolis-provider-sim) - Simulation provider which uses FluxGraph for physics simulation
- [anolis](https://github.com/anolishq/anolis) - Machine runtime

## Version

0.1.1 - Current pre-release

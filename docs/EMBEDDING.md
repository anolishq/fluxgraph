# Embedding with your Project

## Overview

This guide shows how to integrate FluxGraph into your C++ application for real-time simulation.

## Prerequisites

- C++17 compatible compiler
  - MSVC 2019+ (Windows)
  - GCC 9+ (Linux)
  - Clang 10+ (macOS/Linux)
- CMake 3.20 or later

---

## Method 1: CMake add_subdirectory (Recommended)

### Step 1: Add FluxGraph to Your Project

```
your_project/
├── CMakeLists.txt
├── external/
│   └── fluxgraph/         <- Clone or submodule here
└── src/
    └── main.cpp
```

Clone FluxGraph:

```bash
cd your_project/external
git clone https://github.com/your-org/fluxgraph.git
```

Or add as submodule:

```bash
git submodule add https://github.com/your-org/fluxgraph.git external/fluxgraph
```

### Step 2: Update CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.20)
project(your_project)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Add FluxGraph library
add_subdirectory(external/fluxgraph)

# Your executable
add_executable(your_app src/main.cpp)
target_link_libraries(your_app PRIVATE fluxgraph)
```

### Step 3: Use in Code

```cpp
#include "fluxgraph/engine.hpp"
#include "fluxgraph/core/signal_store.hpp"
#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/graph/compiler.hpp"

int main() {
    fluxgraph::Engine engine;
    // ... your code ...
}
```

### Step 4: Build

```bash
mkdir build
cd build
cmake ..
cmake --build . --config Release
```

---

## Method 2: CMake FetchContent

Automatically download FluxGraph during configure:

```cmake
cmake_minimum_required(VERSION 3.20)
project(your_project)

set(CMAKE_CXX_STANDARD 17)

include(FetchContent)
FetchContent_Declare(
    fluxgraph
    GIT_REPOSITORY https://github.com/your-org/fluxgraph.git
    GIT_TAG        v0.1.1  # Or main for latest
)
FetchContent_MakeAvailable(fluxgraph)

add_executable(your_app src/main.cpp)
target_link_libraries(your_app PRIVATE fluxgraph)
```

**Pros:**

- No manual download needed
- Easy version pinning
- Clean workspace

**Cons:**

- Slower first configure (downloads every time)
- Requires internet connection

---

## Method 3: Manual Integration (Advanced)

If you can't use CMake or need full control:

### Step 1: Copy Files

```
your_project/
└── fluxgraph/
    ├── include/fluxgraph/      <- Copy all headers
    └── src/                     <- Copy all .cpp files
```

### Step 2: Compile

Add to your build:

- Include path: `your_project/fluxgraph/include`
- Source files:
  - `fluxgraph/src/signal_store.cpp`
  - `fluxgraph/src/namespace.cpp`
  - `fluxgraph/src/compiler.cpp`
  - `fluxgraph/src/engine.cpp`
  - `fluxgraph/src/thermal_mass.cpp`

### Example Makefile

```makefile
CXX = g++
CXXFLAGS = -std=c++17 -O3 -Ifluxgraph/include

SOURCES = src/main.cpp \
          fluxgraph/src/signal_store.cpp \
          fluxgraph/src/namespace.cpp \
          fluxgraph/src/compiler.cpp \
          fluxgraph/src/engine.cpp \
          fluxgraph/src/thermal_mass.cpp

your_app: $(SOURCES)
  $(CXX) $(CXXFLAGS) -o your_app $(SOURCES)
```

---

## Optional Loaders (JSON and YAML)

FluxGraph core has zero dependencies. Optional graph loaders can be enabled at CMake configure time.

### Configuration 1: Core Only (No Loaders)

Zero external dependencies, 153 tests.

```cmake
cmake_minimum_required(VERSION 3.20)
project(your_project)

set(CMAKE_CXX_STANDARD 17)

add_subdirectory(external/fluxgraph)

add_executable(your_app src/main.cpp)
target_link_libraries(your_app PRIVATE fluxgraph)
```

Build graphs programmatically using `GraphSpec`:

```cpp
fluxgraph::GraphSpec spec;
fluxgraph::EdgeSpec edge;
edge.source_path = "input.x";
edge.target_path = "output.y";
edge.transform.type = "linear";
edge.transform.params["scale"] = 2.0;
spec.edges.push_back(edge);
```

### Configuration 2: With JSON Loader

Adds nlohmann/json (header-only), 162 tests.

```cmake
cmake_minimum_required(VERSION 3.20)
project(your_project)

set(CMAKE_CXX_STANDARD 17)

# Enable JSON loader
set(FLUXGRAPH_JSON_ENABLED ON CACHE BOOL "Enable JSON loader")

add_subdirectory(external/fluxgraph)

add_executable(your_app src/main.cpp)
target_link_libraries(your_app PRIVATE fluxgraph)
```

Load graphs from JSON files:

```cpp
#include "fluxgraph/loaders/json_loader.hpp"

auto spec = fluxgraph::loaders::load_json_file("graph.json");

fluxgraph::GraphCompiler compiler;
auto program = compiler.compile(spec, signal_ns, func_ns);
engine.load(std::move(program));
```

### Configuration 3: With YAML Loader

Adds yaml-cpp, 162 tests.

```cmake
cmake_minimum_required(VERSION 3.20)
project(your_project)

set(CMAKE_CXX_STANDARD 17)

# Enable YAML loader
set(FLUXGRAPH_YAML_ENABLED ON CACHE BOOL "Enable YAML loader")

add_subdirectory(external/fluxgraph)

add_executable(your_app src/main.cpp)
target_link_libraries(your_app PRIVATE fluxgraph)
```

Load graphs from YAML files:

```cpp
#include "fluxgraph/loaders/yaml_loader.hpp"

auto spec = fluxgraph::loaders::load_yaml_file("graph.yaml");

fluxgraph::GraphCompiler compiler;
auto program = compiler.compile(spec, signal_ns, func_ns);
engine.load(std::move(program));
```

### Configuration 4: Both Loaders

Supports both JSON and YAML, 171 tests.

```cmake
cmake_minimum_required(VERSION 3.20)
project(your_project)

set(CMAKE_CXX_STANDARD 17)

# Enable both loaders
set(FLUXGRAPH_JSON_ENABLED ON CACHE BOOL "Enable JSON loader")
set(FLUXGRAPH_YAML_ENABLED ON CACHE BOOL "Enable YAML loader")

add_subdirectory(external/fluxgraph)

add_executable(your_app src/main.cpp)
target_link_libraries(your_app PRIVATE fluxgraph)
```

Use either loader as needed:

```cpp
#include "fluxgraph/loaders/json_loader.hpp"
#include "fluxgraph/loaders/yaml_loader.hpp"

// Load JSON
auto spec1 = fluxgraph::loaders::load_json_file("graph.json");

// Or load YAML
auto spec2 = fluxgraph::loaders::load_yaml_file("graph.yaml");
```

### Dependency Details

| Option                   | Dependency            | Linkage              | Size Impact     |
| ------------------------ | --------------------- | -------------------- | --------------- |
| `FLUXGRAPH_JSON_ENABLED` | nlohmann/json v3.11.3 | Header-only, PRIVATE | ~5KB compiled   |
| `FLUXGRAPH_YAML_ENABLED` | yaml-cpp master       | Static lib, PRIVATE  | ~150KB compiled |

**Important:** All dependencies use `PRIVATE` linkage. Your application does not need to find or link these libraries directly.

**See Also:**

- [JSON_SCHEMA.md](schema-json.md) - JSON graph format reference
- [YAML_SCHEMA.md](schema-yaml.md) - YAML graph format reference
- [examples/03_json_graph/](https://github.com/anolishq/fluxgraph/tree/main/examples/03_json_graph) - JSON example
- [examples/04_yaml_graph/](https://github.com/anolishq/fluxgraph/tree/main/examples/04_yaml_graph) - YAML example

---

## Minimal Example

**main.cpp:**

```cpp
#include "fluxgraph/core/signal_store.hpp"
#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/graph/compiler.hpp"
#include "fluxgraph/engine.hpp"
#include <iostream>

int main() {
    using namespace fluxgraph;

    // 1. Setup
    SignalNamespace ns;
    FunctionNamespace fn;
    SignalStore store;
    Engine engine;

    // 2. Build graph: input -> (scale=2, offset=1) -> output
    GraphSpec spec;
    EdgeSpec edge;
    edge.source_path = "input";
    edge.target_path = "output";
    edge.transform.type = "linear";
    edge.transform.params["scale"] = 2.0;
    edge.transform.params["offset"] = 1.0;
    spec.edges.push_back(edge);

    // 3. Compile and load
    GraphCompiler compiler;
    auto program = compiler.compile(spec, ns, fn);
    engine.load(std::move(program));

    // 4. Execute simulation
    auto input_id = ns.resolve("input");
    auto output_id = ns.resolve("output");

    for (int i = 0; i < 10; ++i) {
        store.write(input_id, 10.0 + i, "");
        engine.tick(0.1, store);  // 100ms time step
        double result = store.read_value(output_id);
        std::cout << "Tick " << i << ": output = " << result << std::endl;
        // Expected: 2*(10+i) + 1 = 21, 23, 25, ...
    }

    return 0;
}
```

**Output:**

```
Tick 0: output = 21
Tick 1: output = 23
Tick 2: output = 25
...
```

---

## Realistic Example: Thermal Chamber

**chamber_sim.cpp:**

```cpp
#include "fluxgraph/engine.hpp"
#include "fluxgraph/core/signal_store.hpp"
#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/graph/compiler.hpp"
#include <iostream>
#include <fstream>

int main() {
    using namespace fluxgraph;

    SignalNamespace ns;
    FunctionNamespace fn;
    SignalStore store;
    Engine engine;

    // Build graph
    GraphSpec spec;

    // Thermal mass model
    ModelSpec model;
    model.id = "chamber";
    model.type = "thermal_mass";
    model.params["temp_signal"] = std::string("chamber.temp");
    model.params["power_signal"] = std::string("chamber.power");
    model.params["ambient_signal"] = std::string("ambient.temp");
    model.params["thermal_mass"] = 1000.0;      // 1000 J/degC
    model.params["heat_transfer_coeff"] = 10.0; // 10 W/degC
    model.params["initial_temp"] = 25.0;        // 25 degC
    spec.models.push_back(model);

    // Filter temperature for display
    EdgeSpec edge;
    edge.source_path = "chamber.temp";
    edge.target_path = "chamber.temp_filtered";
    edge.transform.type = "first_order_lag";
    edge.transform.params["tau_s"] = 1.0;  // 1 second filter
    spec.edges.push_back(edge);

    // Compile
    GraphCompiler compiler;
    auto program = compiler.compile(spec, ns, fn);
    engine.load(std::move(program));

    // Get signal IDs
    auto power_id = ns.resolve("chamber.power");
    auto ambient_id = ns.resolve("ambient.temp");
    auto temp_id = ns.resolve("chamber.temp");
    auto filtered_id = ns.resolve("chamber.temp_filtered");

    // Initialize
    store.write(ambient_id, 20.0, "degC");

    // Open log file
    std::ofstream log("chamber_log.csv");
    log << "time,power,temp,temp_filtered" << std::endl;

    // Simulation: 1000 seconds, 0.1s time step
    double time = 0.0;
    for (int tick = 0; tick < 10000; ++tick) {
        // Apply power for first 500 seconds
        double power = (time < 500.0) ? 500.0 : 0.0;
        store.write(power_id, power, "W");

        // Tick engine
        engine.tick(0.1, store);
        time += 0.1;

        // Log every 10 ticks (1 second)
        if (tick % 10 == 0) {
            double temp = store.read_value(temp_id);
            double temp_filt = store.read_value(filtered_id);
            log << time << "," << power << "," << temp << "," << temp_filt << std::endl;
            std::cout << "t=" << time << "s, T=" << temp << " degC" << std::endl;
        }
    }

    log.close();
    std::cout << "Simulation complete. See chamber_log.csv" << std::endl;

    return 0;
}
```

**Build and run:**

```bash
cmake --build build --config Release
./build/chamber_sim
```

**Result:** CSV file with temperature evolution over time.

---

## Thread Safety Considerations

### FluxGraph Threading Model

**Single-writer:** One thread calls `engine.tick()`

**Multi-reader:** Multiple threads can call `store.read()` concurrently

**Namespace:** Thread-safe after setup (intern during init, resolve during execution)

### Safe Pattern

```cpp
// Thread 1: Simulation
void simulation_thread() {
    while (running) {
        engine.tick(dt, store);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
}

// Thread 2: Monitoring
void monitor_thread() {
    while (running) {
        double temp = store.read_value(temp_id);  // Safe concurrent read
        std::cout << "Temp: " << temp << std::endl;
        std::this_thread::sleep_for(std::chrono::seconds(1));
    }
}
```

### Unsafe Pattern (Don't Do This)

```cpp
// BAD: Multiple threads calling tick()
std::thread t1([&]() { engine.tick(dt, store); });
std::thread t2([&]() { engine.tick(dt, store); });  // RACE CONDITION!
```

---

## Performance Optimization

### 1. Build in Release Mode

```bash
cmake -DCMAKE_BUILD_TYPE=Release ..
```

**Impact:** 10-100x faster than Debug. Always benchmark in Release.

### 2. Reserve Signal IDs

If you know signal count upfront:

```cpp
store.reserve(1000);  // Pre-allocate for 1000 signals
```

**Benefit:** Avoids reallocation during simulation.

### 3. Cache Signal IDs

```cpp
// Bad: Repeated resolve
for (int i = 0; i < 1000; ++i) {
    auto id = ns.resolve("chamber.temp");  // Hash lookup every loop!
    double temp = store.read_value(id);
}

// Good: Cache ID
auto temp_id = ns.resolve("chamber.temp");  // Once
for (int i = 0; i < 1000; ++i) {
    double temp = store.read_value(temp_id);  // Fast array index
}
```

### 4. Choose Appropriate dt

```cpp
// Too small: Wasted computation
engine.tick(0.001, store);  // 1000 Hz, likely overkill

// Too large: Instability
engine.tick(1.0, store);    // May violate model stability limits

// Just right: Match physics needs
engine.tick(0.1, store);    // 10 Hz, good for most thermal systems
```

Use `model.compute_stability_limit()` as guide.

### 5. Profile Before Optimizing

```bash
# Linux
perf record ./your_app
perf report

# Windows
# Use Visual Studio Profiler

# macOS
instruments -t "Time Profiler" ./your_app
```

**Common hotspots:**

1. Model physics (exp, sqrt)
2. Transform chains (if very long)
3. Memory access (cache misses)

**Rarely bottleneck:**

- Virtual calls (~2ns)
- Namespace lookups (done at compile)

---

## Custom Transform Registration

### Step 1: Implement ITransform

**my_transform.hpp:**

```cpp
#pragma once
#include "fluxgraph/transform/interface.hpp"
#include <memory>

class MyGainTransform : public fluxgraph::ITransform {
private:
    double m_gain;
public:
    explicit MyGainTransform(double gain) : m_gain(gain) {}

    double apply(double input, double dt) override {
        return input * m_gain;
    }

    void reset() override {
        // Stateless, nothing to reset
    }

    std::unique_ptr<fluxgraph::ITransform> clone() const override {
        return std::make_unique<MyGainTransform>(*this);
    }
};
```

### Step 2: Register with Compiler

**main.cpp:**

```cpp
#include "my_transform.hpp"
#include "fluxgraph/graph/compiler.hpp"

GraphCompiler compiler;

// Register factory function
compiler.register_transform("my_gain",
    [](const fluxgraph::ParamMap& params) -> std::unique_ptr<fluxgraph::ITransform> {
        double gain = std::get<double>(params.at("gain"));
        return std::make_unique<MyGainTransform>(gain);
    }
);

// Now can use in GraphSpec
EdgeSpec edge;
edge.transform.type = "my_gain";
edge.transform.params["gain"] = 5.0;
```

---

## Custom Model Registration

Similar to transforms:

**my_model.hpp:**

```cpp
#pragma once
#include "fluxgraph/model/interface.hpp"

class MyMotorModel : public fluxgraph::IModel {
private:
    fluxgraph::SignalId m_speed_id, m_torque_id;
    double m_inertia;
    double m_speed;
public:
    MyMotorModel(/* params */) { /* ... */ }

    void tick(double dt, fluxgraph::SignalStore& store) override {
        double torque = store.read_value(m_torque_id);
        double accel = torque / m_inertia;
        m_speed += accel * dt;
        store.write(m_speed_id, m_speed, "rpm");
    }

    void reset() override {
        m_speed = 0.0;
    }

    double compute_stability_limit() const override {
        return 0.1;  // Conservative 100ms max
    }

    std::string describe() const override {
        return "Motor model with inertia";
    }

    std::vector<fluxgraph::SignalId> output_signal_ids() const override {
        return {m_speed_id};
    }
};
```

Register:

```cpp
compiler.register_model("motor",
    [](const fluxgraph::ParamMap& params,
       fluxgraph::SignalNamespace& ns) -> std::unique_ptr<fluxgraph::IModel> {
        // Parse params, return model instance
    }
);
```

---

## Debugging Tips

### 1. Enable Logging

```cpp
// Before compile
compiler.set_verbose(true);  // Prints graph structure

// After tick
engine.dump_state(std::cout);  // Print all signals
```

### 2. Validate Graph

```cpp
try {
    auto program = compiler.compile(spec, ns, fn);
} catch (const std::exception& e) {
    std::cerr << "Compile error: " << e.what() << std::endl;
    // e.what() includes cycle details, missing params, etc.
}
```

### 3. Check Signal Units

```cpp
auto signal = store.read(temp_id);
std::cout << "Value: " << signal.value << " "
          << "Unit: " << signal.unit << " "
          << "Physics: " << signal.physics_driven << std::endl;
```

### 4. Compare to Known Good

Run analytical tests:

```bash
cd fluxgraph/build
ctest -R analytical
```

If test passes but your sim doesn't, compare parameters.

---

## Common Pitfalls

### 1. Forgot to Call tick()

```cpp
engine.load(program);
// ... forgot engine.tick(dt, store) ...
double temp = store.read_value(temp_id);  // Still initial value!
```

### 2. Wrong Time Step Units

```cpp
// WRONG: dt in milliseconds, but params expect seconds
engine.tick(100, store);  // Thought this was 100ms, actually 100s!

// RIGHT:
engine.tick(0.1, store);  // 100ms = 0.1 seconds
```

### 3. Reusing Program Across Engines

```cpp
auto program = compiler.compile(spec, ns, fn);
engine1.load(std::move(program));  // OK
engine2.load(std::move(program));  // ERROR: program already moved!

// FIX: Compile twice or clone program
```

### 4. Not Resetting After Re-Run

```cpp
// First run
for (int i = 0; i < 100; ++i) engine.tick(0.1, store);

// Second run (but state still from first run!)
for (int i = 0; i < 100; ++i) engine.tick(0.1, store);  // WRONG

// FIX:
engine.reset();
store.clear();
// Now ready for second run
```

---

## Platform-Specific Notes

### Windows (MSVC)

```bash
cmake -G "Visual Studio 17 2022" -A x64 ..
cmake --build . --config Release
```

### Linux (GCC/Clang)

```bash
cmake -DCMAKE_BUILD_TYPE=Release ..
make -j$(nproc)
```

### macOS (Xcode)

```bash
cmake -G Xcode ..
cmake --build . --config Release
```

---

## Further Reading

- [API.md](api-reference.md) - Complete API reference
- [ARCHITECTURE.md](ARCHITECTURE.md) - Design rationale
- [TRANSFORMS.md](TRANSFORMS.md) - Transform details
- [examples/](https://github.com/anolishq/fluxgraph/tree/main/examples) - Full working examples

---

## Support

**Issues:** <https://github.com/anolishq/fluxgraph/issues>

**Questions:** Post issue with "question" label

**Contributing:** See [CONTRIBUTING.md](https://github.com/anolishq/fluxgraph/blob/main/CONTRIBUTING.md)

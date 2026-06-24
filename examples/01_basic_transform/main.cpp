#include <fluxgraph/core/namespace.hpp>
#include <fluxgraph/core/signal_store.hpp>
#include <fluxgraph/engine.hpp>
#include <fluxgraph/graph/compiler.hpp>
#include <iostream>

int main() {
    // 1. Create namespaces and signal store
    fluxgraph::SignalNamespace sig_ns;
    fluxgraph::FunctionNamespace func_ns;
    fluxgraph::SignalStore store;

    // 2. Build graph specification manually
    fluxgraph::GraphSpec spec;

    // Define edge: voltage_in --[scale=2.0, offset=1.0]--> voltage_out
    fluxgraph::EdgeSpec edge;
    edge.source_path = "sensor.voltage_in";
    edge.target_path = "sensor.voltage_out";
    edge.transform.type = "linear";
    edge.transform.params["scale"] = 2.0;
    edge.transform.params["offset"] = 1.0;
    spec.edges.push_back(edge);

    // 3. Compile graph
    fluxgraph::GraphCompiler compiler;
    auto program = compiler.compile(spec, sig_ns, func_ns);

    // 4. Load into engine
    fluxgraph::Engine engine;
    engine.load(std::move(program));

    // 5. Get signal IDs (these are your input/output "ports")
    auto input_sig = sig_ns.resolve("sensor.voltage_in");
    auto output_sig = sig_ns.resolve("sensor.voltage_out");

    // 6. Simulation loop
    std::cout << "Simple Transform: y = 2*x + 1\n";
    std::cout << "================================\n";
    for (int i = 0; i < 5; ++i) {
        double input_val = i * 1.0;

        // Write to input port
        store.write(input_sig, input_val, "V");

        // Execute graph (dt doesn't affect stateless linear transform)
        engine.tick(0.1, store);

        // Read from output port
        double output_val = store.read_value(output_sig);
        std::cout << "Input: " << input_val << "V -> Output: " << output_val << "V\n";
    }

    return 0;
}

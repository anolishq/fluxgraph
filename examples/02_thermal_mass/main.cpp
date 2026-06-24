#include <fluxgraph/core/namespace.hpp>
#include <fluxgraph/core/signal_store.hpp>
#include <fluxgraph/engine.hpp>
#include <fluxgraph/graph/compiler.hpp>
#include <iomanip>
#include <iostream>

int main() {
    // 1. Setup
    fluxgraph::SignalNamespace sig_ns;
    fluxgraph::FunctionNamespace func_ns;
    fluxgraph::SignalStore store;

    // 2. Build graph with thermal mass model
    fluxgraph::GraphSpec spec;

    // Define thermal mass model
    fluxgraph::ModelSpec model;
    model.id = "chamber_thermal";
    model.type = "thermal_mass";
    model.params["temp_signal"] = std::string("chamber.temperature");
    model.params["power_signal"] = std::string("chamber.heater_power");
    model.params["ambient_signal"] = std::string("chamber.ambient_temp");
    model.params["thermal_mass"] = 1000.0;       // J/K
    model.params["heat_transfer_coeff"] = 10.0;  // W/K
    model.params["initial_temp"] = 25.0;         // degC
    spec.models.push_back(model);

    // Optional: Add noise to temperature reading
    fluxgraph::EdgeSpec noise_edge;
    noise_edge.source_path = "chamber.temperature";
    noise_edge.target_path = "chamber.temperature_noisy";
    noise_edge.transform.type = "noise";
    noise_edge.transform.params["amplitude"] = 0.1;  // +/- 0.1 degC noise
    noise_edge.transform.params["seed"] = static_cast<int64_t>(42);
    spec.edges.push_back(noise_edge);

    // 3. Compile and load
    fluxgraph::GraphCompiler compiler;
    auto program = compiler.compile(spec, sig_ns, func_ns);

    fluxgraph::Engine engine;
    engine.load(std::move(program));

    // 4. Get signal IDs (input/output ports)
    auto heater_sig = sig_ns.resolve("chamber.heater_power");
    auto ambient_sig = sig_ns.resolve("chamber.ambient_temp");
    auto temp_sig = sig_ns.resolve("chamber.temperature");
    auto temp_noisy_sig = sig_ns.resolve("chamber.temperature_noisy");

    // 5. Initialize ambient temperature
    store.write(ambient_sig, 20.0, "degC");

    // 6. Simulation: heat chamber for 5 seconds, then turn off
    std::cout << "Thermal Mass Simulation\n";
    std::cout << "=======================\n";
    std::cout << std::fixed << std::setprecision(2);

    for (double t = 0; t <= 10.0; t += 0.5) {
        // Control heater: on for first 5 seconds, off after
        double heater_power = (t < 5.0) ? 500.0 : 0.0;
        store.write(heater_sig, heater_power, "W");

        // Execute physics
        engine.tick(0.5, store);

        // Read output ports
        double temp = store.read_value(temp_sig);
        double temp_noisy = store.read_value(temp_noisy_sig);

        std::cout << "t=" << std::setw(5) << t << "s  "
                  << "Heater=" << std::setw(5) << heater_power << "W  "
                  << "Temp=" << std::setw(6) << temp << " degC  "
                  << "Noisy=" << std::setw(6) << temp_noisy << " degC\n";
    }

    return 0;
}

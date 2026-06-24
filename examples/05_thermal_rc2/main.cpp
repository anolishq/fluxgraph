#include <fluxgraph/core/namespace.hpp>
#include <fluxgraph/core/signal_store.hpp>
#include <fluxgraph/engine.hpp>
#include <fluxgraph/graph/compiler.hpp>
#include <iomanip>
#include <iostream>

int main() {
    fluxgraph::SignalNamespace sig_ns;
    fluxgraph::FunctionNamespace func_ns;
    fluxgraph::SignalStore store;

    fluxgraph::GraphSpec spec;

    fluxgraph::ModelSpec model;
    model.id = "chamber_rc";
    model.type = "thermal_rc2";
    model.params["temp_signal_a"] = std::string("chamber.shell_temp");
    model.params["temp_signal_b"] = std::string("chamber.core_temp");
    model.params["power_signal"] = std::string("chamber.heater_power");
    model.params["ambient_signal"] = std::string("ambient.temp");
    model.params["thermal_mass_a"] = 1000.0;                  // J/K
    model.params["thermal_mass_b"] = 2000.0;                  // J/K
    model.params["heat_transfer_coeff_a"] = 10.0;             // W/K
    model.params["heat_transfer_coeff_b"] = 8.0;              // W/K
    model.params["coupling_coeff"] = 6.0;                     // W/K
    model.params["initial_temp_a"] = 25.0;                    // degC
    model.params["initial_temp_b"] = 25.0;                    // degC
    model.params["integration_method"] = std::string("rk4");  // optional
    spec.models.push_back(model);

    fluxgraph::GraphCompiler compiler;
    auto program = compiler.compile(spec, sig_ns, func_ns);

    fluxgraph::Engine engine;
    engine.load(std::move(program));

    const auto heater_sig = sig_ns.resolve("chamber.heater_power");
    const auto ambient_sig = sig_ns.resolve("ambient.temp");
    const auto shell_temp_sig = sig_ns.resolve("chamber.shell_temp");
    const auto core_temp_sig = sig_ns.resolve("chamber.core_temp");

    store.write(ambient_sig, 20.0, "degC");

    std::cout << "Thermal RC2 Simulation\n";
    std::cout << "======================\n";
    std::cout << std::fixed << std::setprecision(2);

    for (double t = 0.0; t <= 10.0; t += 0.5) {
        const double heater_power = (t < 5.0) ? 500.0 : 0.0;
        store.write(heater_sig, heater_power, "W");

        engine.tick(0.5, store);

        const double shell_temp = store.read_value(shell_temp_sig);
        const double core_temp = store.read_value(core_temp_sig);

        std::cout << "t=" << std::setw(5) << t << "s  "
                  << "Heater=" << std::setw(6) << heater_power << "W  "
                  << "Shell=" << std::setw(6) << shell_temp << " degC  "
                  << "Core=" << std::setw(6) << core_temp << " degC\n";
    }

    return 0;
}

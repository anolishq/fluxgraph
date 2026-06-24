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
    model.id = "motor";
    model.type = "dc_motor";
    model.params["speed_signal"] = std::string("motor.omega");
    model.params["current_signal"] = std::string("motor.i");
    model.params["torque_signal"] = std::string("motor.tau");
    model.params["voltage_signal"] = std::string("motor.V");
    model.params["load_torque_signal"] = std::string("motor.load");
    model.params["resistance_ohm"] = 2.0;     // Ohm
    model.params["inductance_h"] = 0.5;       // H
    model.params["torque_constant"] = 0.1;    // N*m/A
    model.params["back_emf_constant"] = 0.1;  // V*s/rad
    model.params["inertia"] = 0.02;           // kg*m^2
    model.params["viscous_friction"] = 0.2;   // N*m*s/rad
    model.params["initial_current"] = 0.0;    // A
    model.params["initial_speed"] = 0.0;      // rad/s
    model.params["integration_method"] = std::string("rk4");
    spec.models.push_back(model);

    fluxgraph::GraphCompiler compiler;
    auto program = compiler.compile(spec, sig_ns, func_ns);

    fluxgraph::Engine engine;
    engine.load(std::move(program));

    const auto omega_id = sig_ns.resolve("motor.omega");
    const auto i_id = sig_ns.resolve("motor.i");
    const auto tau_id = sig_ns.resolve("motor.tau");
    const auto v_id = sig_ns.resolve("motor.V");
    const auto load_id = sig_ns.resolve("motor.load");

    std::cout << "DC Motor Step Response\n";
    std::cout << "======================\n";
    std::cout << std::fixed << std::setprecision(4);

    constexpr double dt = 0.01;
    for (double t = 0.0; t <= 5.0; t += dt) {
        const double voltage = (t < 2.5) ? 12.0 : 0.0;
        const double load_torque = 0.1;
        store.write(v_id, voltage, "V");
        store.write(load_id, load_torque, "N*m");

        engine.tick(dt, store);

        if (static_cast<int>(t / dt) % 50 == 0) {
            const double omega = store.read_value(omega_id);
            const double current = store.read_value(i_id);
            const double torque = store.read_value(tau_id);
            std::cout << "t=" << std::setw(5) << t << " s  "
                      << "V=" << std::setw(6) << voltage << " V  "
                      << "load=" << std::setw(6) << load_torque << " N*m  "
                      << "omega=" << std::setw(8) << omega << " rad/s  "
                      << "i=" << std::setw(8) << current << " A  "
                      << "tau=" << std::setw(8) << torque << " N*m\n";
        }
    }

    return 0;
}

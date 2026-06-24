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
    model.id = "msd";
    model.type = "mass_spring_damper";
    model.params["position_signal"] = std::string("msd.position_m");
    model.params["velocity_signal"] = std::string("msd.velocity_m_s");
    model.params["force_signal"] = std::string("msd.force_N");
    model.params["mass"] = 1.0;              // kg
    model.params["damping_coeff"] = 2.0;     // N*s/m
    model.params["spring_constant"] = 20.0;  // N/m
    model.params["initial_position"] = 0.0;  // m
    model.params["initial_velocity"] = 0.0;  // m/s
    model.params["integration_method"] = std::string("rk4");
    spec.models.push_back(model);

    fluxgraph::GraphCompiler compiler;
    auto program = compiler.compile(spec, sig_ns, func_ns);

    fluxgraph::Engine engine;
    engine.load(std::move(program));

    const auto force_id = sig_ns.resolve("msd.force_N");
    const auto position_id = sig_ns.resolve("msd.position_m");
    const auto velocity_id = sig_ns.resolve("msd.velocity_m_s");

    std::cout << "Mass-Spring-Damper Step Response\n";
    std::cout << "================================\n";
    std::cout << std::fixed << std::setprecision(4);

    constexpr double dt = 0.01;
    for (double t = 0.0; t <= 5.0; t += dt) {
        const double force = (t < 2.5) ? 1.0 : 0.0;
        store.write(force_id, force, "N");

        engine.tick(dt, store);

        if (static_cast<int>(t / dt) % 50 == 0) {
            const double x = store.read_value(position_id);
            const double v = store.read_value(velocity_id);
            std::cout << "t=" << std::setw(5) << t << " s  "
                      << "F=" << std::setw(6) << force << " N  "
                      << "x=" << std::setw(8) << x << " m  "
                      << "v=" << std::setw(8) << v << " m/s\n";
        }
    }

    return 0;
}

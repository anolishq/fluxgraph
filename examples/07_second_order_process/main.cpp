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
    spec.signals.push_back({"pt2.u", "dimensionless"});
    spec.signals.push_back({"pt2.y", "dimensionless"});

    fluxgraph::ModelSpec model;
    model.id = "pt2";
    model.type = "second_order_process";
    model.params["output_signal"] = std::string("pt2.y");
    model.params["input_signal"] = std::string("pt2.u");
    model.params["gain"] = 2.0;
    model.params["zeta"] = 0.7;
    model.params["omega_n_rad_s"] = 4.0;
    model.params["initial_output"] = 0.0;
    model.params["initial_output_rate"] = 0.0;
    model.params["integration_method"] = std::string("rk4");  // optional
    spec.models.push_back(model);

    fluxgraph::GraphCompiler compiler;
    auto program = compiler.compile(spec, sig_ns, func_ns);

    fluxgraph::Engine engine;
    engine.load(std::move(program));

    const auto u_sig = sig_ns.resolve("pt2.u");
    const auto y_sig = sig_ns.resolve("pt2.y");

    std::cout << "Second-Order Process Simulation (PT2)\n";
    std::cout << "====================================\n";
    std::cout << std::fixed << std::setprecision(3);

    constexpr double dt = 0.01;
    store.write(u_sig, 0.0, "dimensionless");

    for (double t = 0.0; t <= 5.0; t += dt) {
        const double u = (t >= 1.0) ? 1.0 : 0.0;
        store.write(u_sig, u, "dimensionless");
        engine.tick(dt, store);

        const double y = store.read_value(y_sig);
        if (static_cast<int>(t / dt) % 10 == 0) {
            std::cout << "t=" << std::setw(5) << t << "s  u=" << u << "  y=" << std::setw(8) << y << "\n";
        }
    }

    return 0;
}

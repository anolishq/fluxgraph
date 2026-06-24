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
    spec.signals.push_back({"pt1.u", "dimensionless"});
    spec.signals.push_back({"pt1.y", "dimensionless"});

    fluxgraph::ModelSpec model;
    model.id = "pt1";
    model.type = "first_order_process";
    model.params["output_signal"] = std::string("pt1.y");
    model.params["input_signal"] = std::string("pt1.u");
    model.params["gain"] = 2.0;
    model.params["tau_s"] = 1.0;
    model.params["initial_output"] = 0.0;
    model.params["integration_method"] = std::string("rk4");  // optional
    spec.models.push_back(model);

    fluxgraph::GraphCompiler compiler;
    auto program = compiler.compile(spec, sig_ns, func_ns);

    fluxgraph::Engine engine;
    engine.load(std::move(program));

    const auto u_sig = sig_ns.resolve("pt1.u");
    const auto y_sig = sig_ns.resolve("pt1.y");

    std::cout << "First-Order Process Simulation (PT1)\n";
    std::cout << "===================================\n";
    std::cout << std::fixed << std::setprecision(3);

    constexpr double dt = 0.05;
    store.write(u_sig, 0.0, "dimensionless");

    for (double t = 0.0; t <= 5.0; t += dt) {
        const double u = (t >= 1.0) ? 1.0 : 0.0;
        store.write(u_sig, u, "dimensionless");
        engine.tick(dt, store);

        const double y = store.read_value(y_sig);
        std::cout << "t=" << std::setw(5) << t << "s  u=" << u << "  y=" << std::setw(8) << y << "\n";
    }

    return 0;
}

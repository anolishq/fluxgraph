#ifdef FLUXGRAPH_JSON_ENABLED

#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/core/signal_store.hpp"
#include "fluxgraph/engine.hpp"
#include "fluxgraph/graph/compiler.hpp"
#include "fluxgraph/loaders/json_loader.hpp"
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <stdexcept>

int main(int argc, char *argv[]) {
  // Determine graph file path
  std::string graph_path = "graph.json";
  if (argc > 1) {
    graph_path = argv[1];
  } else if (std::filesystem::exists("examples/03_json_graph/graph.json")) {
    graph_path = "examples/03_json_graph/graph.json";
  }

  std::cout << "=== FluxGraph JSON Loader Example ===\n\n";
  std::cout << "Loading graph from: " << graph_path << "\n\n";

  try {
    // 1. Load graph from JSON file
    auto spec = fluxgraph::loaders::load_json_file(graph_path);

    std::cout << "Graph loaded successfully:\n";
    std::cout << "  Models: " << spec.models.size() << "\n";
    std::cout << "  Edges: " << spec.edges.size() << "\n";
    std::cout << "  Rules: " << spec.rules.size() << "\n\n";

    // 2. Create runtime infrastructure
    fluxgraph::SignalNamespace sig_ns;
    fluxgraph::FunctionNamespace func_ns;
    fluxgraph::SignalStore store;

    // 3. Compile graph
    fluxgraph::GraphCompiler compiler;
    auto program = compiler.compile(spec, sig_ns, func_ns);

    // 4. Load into engine
    fluxgraph::Engine engine;
    engine.load(std::move(program));

    // 5. Run one of the bundled simulation loops based on available signals.
    const auto heater_id = sig_ns.resolve("heater.output");
    const auto ambient_id = sig_ns.resolve("ambient.temp");
    const auto chamber_id = sig_ns.resolve("chamber.temp");
    const auto display_id = sig_ns.resolve("display.temp");

    if (heater_id != fluxgraph::INVALID_SIGNAL &&
        ambient_id != fluxgraph::INVALID_SIGNAL &&
        chamber_id != fluxgraph::INVALID_SIGNAL &&
        display_id != fluxgraph::INVALID_SIGNAL) {
      store.write(ambient_id, 20.0, "degC");
      store.write(heater_id, 500.0, "W");

      std::cout << "Running thermal chamber simulation:\n";
      std::cout << "Time(s)  Heater(W)  Chamber(degC)  Display(degC)\n";
      std::cout << "-------  ---------  -----------  -----------\n";

      const double dt = 0.1;
      for (int i = 0; i <= 100; ++i) {
        engine.tick(dt, store);

        if (i % 10 == 0) {
          const double heater = store.read_value(heater_id);
          const double chamber = store.read_value(chamber_id);
          const double display = store.read_value(display_id);

          std::cout << std::fixed << std::setprecision(1) << std::setw(7)
                    << i * dt << "  " << std::setw(9) << heater << "  "
                    << std::setw(11) << chamber << "  " << std::setw(11)
                    << display << "\n";
        }

        if (i == 50) {
          store.write(heater_id, 0.0, "W");
        }
      }
    } else {
      const auto u_id = sig_ns.resolve("ss.u");
      const auto y_id = sig_ns.resolve("ss.y");
      if (u_id == fluxgraph::INVALID_SIGNAL ||
          y_id == fluxgraph::INVALID_SIGNAL) {
        throw std::runtime_error(
            "Example runner does not recognize graph IO signals");
      }

      std::cout << "Running discrete state-space simulation:\n";
      std::cout << "Time(s)  Input(V)  Output(A)\n";
      std::cout << "-------  --------  ---------\n";

      const double dt = 0.05;
      for (int i = 0; i <= 80; ++i) {
        const double t = i * dt;
        const double u = (t >= 0.5) ? 5.0 : 0.0;
        store.write(u_id, u, "V");
        engine.tick(dt, store);

        if (i % 8 == 0) {
          const double y = store.read_value(y_id);
          std::cout << std::fixed << std::setprecision(2) << std::setw(7) << t
                    << "  " << std::setw(8) << u << "  " << std::setw(9) << y
                    << "\n";
        }
      }
    }

    std::cout << "\nSimulation complete.\n";

  } catch (const std::exception &e) {
    std::cerr << "Error: " << e.what() << "\n";
    return 1;
  }

  return 0;
}

#else

#include <iostream>

int main() {
  std::cout << "This example requires JSON support.\n";
  std::cout << "Rebuild with -DFLUXGRAPH_JSON_ENABLED=ON\n";
  return 1;
}

#endif // FLUXGRAPH_JSON_ENABLED

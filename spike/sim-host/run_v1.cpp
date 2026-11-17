// Runs a FluxGraph 1.x graph on a script from stdin, and prints the signals asked for after each tick.
//
//   run_v1 <graph.yaml> <dt in seconds>
//
// A line of the script is one of:
//
//   out <signal>...         the signals to print after each tick, in this order
//   w <signal> <value>      a write to a signal
//   t                       a tick of dt, and then a line of the `out` signals, with spaces between them
//
// It is the 1.x half of spike/sim-host/compare.py, and decides nothing itself.

#include <cstdio>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/core/signal_store.hpp"
#include "fluxgraph/engine.hpp"
#include "fluxgraph/graph/compiler.hpp"
#include "fluxgraph/loaders/yaml_loader.hpp"

int main(int argc, char *argv[]) {
    if (argc != 3) {
        std::cerr << "usage: run_v1 <graph.yaml> <dt in seconds>\n";
        return 2;
    }
    try {
        const double dt = std::stod(argv[2]);
        auto spec = fluxgraph::loaders::load_yaml_file(argv[1]);
        fluxgraph::SignalNamespace names;
        fluxgraph::FunctionNamespace functions;
        fluxgraph::SignalStore store;
        fluxgraph::GraphCompiler compiler;
        auto program = compiler.compile(spec, names, functions);
        fluxgraph::Engine engine;
        engine.load(std::move(program));

        std::vector<fluxgraph::SignalId> shown;
        std::string line;
        while (std::getline(std::cin, line)) {
            std::istringstream words(line);
            std::string word;
            words >> word;
            if (word == "out") {
                while (words >> word) {
                    const fluxgraph::SignalId id = names.resolve(word);
                    if (id == fluxgraph::INVALID_SIGNAL) {
                        std::cerr << "no signal '" << word << "'\n";
                        return 1;
                    }
                    shown.push_back(id);
                }
            } else if (word == "w") {
                std::string name;
                double value = 0.0;
                words >> name >> value;
                const fluxgraph::SignalId id = names.resolve(name);
                if (id == fluxgraph::INVALID_SIGNAL) {
                    std::cerr << "no signal '" << name << "'\n";
                    return 1;
                }
                store.write(id, value);
            } else if (word == "t") {
                engine.tick(dt, store);
                for (std::size_t i = 0; i < shown.size(); ++i) {
                    std::printf("%s%.17g", i == 0 ? "" : " ", store.read_value(shown[i]));
                }
                std::printf("\n");
            }
        }
    } catch (const std::exception &error) {
        std::cerr << "refused: " << error.what() << "\n";
        return 1;
    }
    return 0;
}

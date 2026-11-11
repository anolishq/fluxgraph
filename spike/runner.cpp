// Spike runner: replay a test vector through FluxGraph's engine and compare
// every published output at every tick, by state and by value.
//
//   spike_runner <vectors dir> [name ...]
//
// With no names, runs every *.graph.tsv in the directory. Exits 1 on any
// difference.

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "blocks.hpp"
#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/core/signal_store.hpp"
#include "fluxgraph/engine.hpp"
#include "fluxgraph/graph/compiler.hpp"

namespace {

using Row = std::vector<std::string>;

std::vector<Row> read_tsv(const std::filesystem::path &path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open " + path.string());
    std::vector<Row> rows;
    std::string line;
    bool header = true;
    while (std::getline(in, line)) {
        if (header) {
            header = false;
            continue;
        }
        Row row;
        std::string cell;
        std::stringstream ss(line);
        while (std::getline(ss, cell, '\t')) row.push_back(cell);
        if (!line.empty() && line.back() == '\t') row.emplace_back();
        rows.push_back(row);
    }
    return rows;
}

int state_of(const std::string &name) {
    if (name == "good") return spike::GOOD;
    if (name == "bad") return spike::BAD;
    return spike::NOT_READY;
}

const char *name_of(int state) { return state == spike::GOOD ? "good" : state == spike::BAD ? "bad" : "not_ready"; }

struct Result {
    size_t ticks = 0;
    size_t outputs = 0;
    size_t compared = 0;
    size_t state_differs = 0;
    size_t value_differs = 0;
    double worst = 0.0;
    std::vector<std::string> first;
};

Result run(const std::filesystem::path &dir, const std::string &name) {
    constexpr double kDt = 2.5;
    constexpr double kTolerance = 1e-9;

    // The graph: one FluxGraph model per block, in the order the file gives.
    // FluxGraph runs models in the order they are declared and does not sort
    // them, so that order has to be a dependency order already (FRICTION 3).
    fluxgraph::GraphSpec spec;
    std::map<std::string, std::string> published;  // signal name -> wire
    for (const Row &row : read_tsv(dir / (name + ".graph.tsv"))) {
        const std::string &block = row.at(0), &type = row.at(1), &field = row.at(2), &key = row.at(3);
        const std::string value = row.size() > 4 ? row[4] : "";
        if (spec.models.empty() || spec.models.back().id != block) {
            fluxgraph::ModelSpec model;
            model.id = block;
            model.type = "blk_" + type;
            spec.models.push_back(model);
        }
        auto &params = spec.models.back().params;
        if (field == "in") {
            params["in." + key] = value;
        } else if (field == "param") {
            params["p." + key] = value;
        } else if (field == "fallback") {
            params["fallback"] = value;
        } else if (field == "out" && !value.empty()) {
            published[value] = block + "." + key;
        }
    }

    fluxgraph::SignalNamespace signals;
    fluxgraph::FunctionNamespace functions;
    fluxgraph::GraphCompiler compiler;
    fluxgraph::Engine engine;
    engine.load(compiler.compile(spec, signals, functions, kDt));
    fluxgraph::SignalStore store;

    std::map<long, std::vector<Row>> inputs, expected;
    for (const Row &row : read_tsv(dir / (name + ".inputs.tsv"))) inputs[std::stol(row.at(0))].push_back(row);
    for (const Row &row : read_tsv(dir / (name + ".expected.tsv"))) expected[std::stol(row.at(0))].push_back(row);

    Result result;
    result.ticks = inputs.size();
    result.outputs = published.size();
    for (const auto &[tick, rows] : inputs) {
        for (const Row &row : rows) {
            const std::string &signal = row.at(2);
            const int state = state_of(row.at(3));
            // An input the graph never reads is not in the namespace; skip it.
            const fluxgraph::SignalId value_id = signals.resolve(signal);
            if (value_id == fluxgraph::INVALID_SIGNAL) continue;
            store.write(value_id, state == spike::GOOD ? std::stod(row.at(4)) : 0.0);
            store.write(signals.resolve(spike::state_path(signal)), static_cast<double>(state));
        }
        engine.tick(kDt, store);
        for (const Row &row : expected[tick]) {
            const std::string &signal = row.at(1);
            const std::string &wire = published.at(signal);
            const int want_state = state_of(row.at(2));
            const int have_state = static_cast<int>(store.read_value(signals.resolve(spike::state_path(wire))));
            ++result.compared;
            std::ostringstream where;
            where << "tick " << tick << " " << signal << ": ";
            if (want_state != have_state) {
                ++result.state_differs;
                if (result.first.size() < 3) {
                    where << "state " << name_of(have_state) << ", expected " << name_of(want_state);
                    result.first.push_back(where.str());
                }
                continue;
            }
            if (want_state != spike::GOOD) continue;
            const double want = std::stod(row.at(3));
            const double have = store.read_value(signals.resolve(wire));
            const double diff = std::fabs(want - have);
            result.worst = std::max(result.worst, diff);
            if (diff > kTolerance * std::max(1.0, std::fabs(want))) {
                ++result.value_differs;
                if (result.first.size() < 3) {
                    where << "value " << have << ", expected " << want;
                    result.first.push_back(where.str());
                }
            }
        }
    }
    return result;
}

}  // namespace

int main(int argc, char **argv) {
    if (argc < 2) {
        std::cerr << "usage: spike_runner <vectors dir> [name ...]\n";
        return 64;
    }
    const std::filesystem::path dir = argv[1];
    std::vector<std::string> names(argv + 2, argv + argc);
    if (names.empty()) {
        for (const auto &entry : std::filesystem::directory_iterator(dir)) {
            const std::string file = entry.path().filename().string();
            const std::string suffix = ".graph.tsv";
            if (file.size() > suffix.size() && file.compare(file.size() - suffix.size(), suffix.size(), suffix) == 0) {
                names.push_back(file.substr(0, file.size() - suffix.size()));
            }
        }
        std::sort(names.begin(), names.end());
    }

    spike::register_blocks();
    bool ok = true;
    std::cout << "vector          ticks outputs compared  state differs  value differs  largest difference\n";
    for (const std::string &name : names) {
        try {
            const Result r = run(dir, name);
            const bool same = r.state_differs == 0 && r.value_differs == 0;
            ok = ok && same;
            std::printf("%-14s %6zu %7zu %8zu %14zu %14zu %19.3g%s\n", name.c_str(), r.ticks, r.outputs, r.compared,
                        r.state_differs, r.value_differs, r.worst, same ? "" : "   DIFFERENT");
            for (const std::string &line : r.first) std::cout << "    " << line << "\n";
        } catch (const std::exception &e) {
            ok = false;
            std::printf("%-14s FAILED: %s\n", name.c_str(), e.what());
        }
    }
    std::cout << (ok ? "ALL THE SAME" : "DIFFERENCES FOUND") << "\n";
    return ok ? 0 : 1;
}

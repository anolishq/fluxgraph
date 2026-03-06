#include <fluxgraph/core/namespace.hpp>
#include <fluxgraph/core/signal_store.hpp>
#include <fluxgraph/engine.hpp>
#include <fluxgraph/graph/compiler.hpp>
#include <iomanip>
#include <iostream>

namespace {

fluxgraph::ParamValue matrix_param(
    std::initializer_list<std::initializer_list<double>> rows) {
  fluxgraph::ParamArray matrix;
  matrix.reserve(rows.size());
  for (const auto &row_values : rows) {
    fluxgraph::ParamArray row;
    row.reserve(row_values.size());
    for (double value : row_values) {
      row.emplace_back(value);
    }
    matrix.emplace_back(row);
  }
  return fluxgraph::ParamValue{matrix};
}

fluxgraph::ParamValue vector_param(std::initializer_list<double> values) {
  fluxgraph::ParamArray out;
  out.reserve(values.size());
  for (double value : values) {
    out.emplace_back(value);
  }
  return fluxgraph::ParamValue{out};
}

} // namespace

int main() {
  fluxgraph::SignalNamespace sig_ns;
  fluxgraph::FunctionNamespace func_ns;
  fluxgraph::SignalStore store;

  fluxgraph::GraphSpec spec;
  spec.signals.push_back({"ss.u", "V"});
  spec.signals.push_back({"ss.y", "A"});

  fluxgraph::ModelSpec model;
  model.id = "ss";
  model.type = "state_space_siso_discrete";
  model.params["output_signal"] = std::string("ss.y");
  model.params["input_signal"] = std::string("ss.u");
  model.params["A_d"] = matrix_param({{0.9, 0.1}, {0.0, 0.95}});
  model.params["B_d"] = vector_param({0.1, 0.05});
  model.params["C"] = vector_param({1.0, 0.0});
  model.params["D"] = 0.0;
  model.params["x0"] = vector_param({0.0, 0.0});
  spec.models.push_back(model);

  fluxgraph::GraphCompiler compiler;
  fluxgraph::CompilationOptions options;
  options.dimensional_policy = fluxgraph::DimensionalPolicy::strict;
  auto program = compiler.compile(spec, sig_ns, func_ns, options);

  fluxgraph::Engine engine;
  engine.load(std::move(program));

  const auto u_id = sig_ns.resolve("ss.u");
  const auto y_id = sig_ns.resolve("ss.y");

  std::cout << "State-Space SISO Discrete Example\n";
  std::cout << "=================================\n";
  std::cout << std::fixed << std::setprecision(4);

  constexpr double dt = 0.05;
  for (int step = 0; step <= 80; ++step) {
    const double t = static_cast<double>(step) * dt;
    const double u = (t >= 0.5) ? 5.0 : 0.0;
    store.write(u_id, u, "V");
    engine.tick(dt, store);

    if (step % 8 == 0) {
      const double y = store.read_value(y_id);
      std::cout << "t=" << std::setw(5) << t << " s  "
                << "u=" << std::setw(7) << u << " V  "
                << "y=" << std::setw(9) << y << " A\n";
    }
  }

  return 0;
}

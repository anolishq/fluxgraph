#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/core/signal_store.hpp"
#include "fluxgraph/model/thermal_mass.hpp"
#include <cmath>
#include <cstddef>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

using namespace fluxgraph;

namespace {

struct Options {
  std::string output_json;
  std::string output_csv;
  double duration_s = 10.0;
  std::vector<double> dt_values = {0.4, 0.2, 0.1, 0.05, 0.025};
};

struct ScenarioConfig {
  std::string id;
  double thermal_mass = 0.0;
  double heat_transfer_coeff = 0.0;
  double initial_temp = 0.0;
  double ambient_temp = 0.0;
  double power = 0.0;
};

struct ValidationPoint {
  double dt = 0.0;
  std::size_t steps = 0;
  double l2_error = 0.0;
  double linf_error = 0.0;
  double final_abs_error = 0.0;
};

struct MethodResult {
  std::string method;
  std::vector<ValidationPoint> points;
  double observed_order_l2 = 0.0;
  double observed_order_linf = 0.0;
};

struct ScenarioResult {
  ScenarioConfig config;
  std::vector<MethodResult> methods;
};

void print_usage() {
  std::cout << "Usage: validation_thermal_mass [options]\n"
               "Options:\n"
               "  --output-json <path>   Write JSON results file\n"
               "  --output-csv <path>    Write CSV results file\n"
               "  --duration-s <value>   Simulation duration in seconds "
               "(default: 10)\n"
               "  --dt-values <list>     Comma-separated dt values (default: "
               "0.4,0.2,0.1,0.05,0.025)\n"
               "  --help                 Show this help\n";
}

std::vector<double> parse_dt_values(const std::string &raw) {
  std::vector<double> out;
  std::stringstream ss(raw);
  std::string token;
  while (std::getline(ss, token, ',')) {
    if (token.empty()) {
      continue;
    }
    const double value = std::stod(token);
    if (value <= 0.0) {
      throw std::runtime_error("dt values must be positive");
    }
    out.push_back(value);
  }
  if (out.empty()) {
    throw std::runtime_error("No valid dt values were provided");
  }
  return out;
}

Options parse_options(int argc, char **argv) {
  Options opts;

  for (int i = 1; i < argc; ++i) {
    const std::string arg = argv[i];
    if (arg == "--help") {
      print_usage();
      throw std::runtime_error("help");
    }
    if (arg == "--output-json") {
      if (i + 1 >= argc) {
        throw std::runtime_error("--output-json requires a path");
      }
      opts.output_json = argv[++i];
      continue;
    }
    if (arg == "--output-csv") {
      if (i + 1 >= argc) {
        throw std::runtime_error("--output-csv requires a path");
      }
      opts.output_csv = argv[++i];
      continue;
    }
    if (arg == "--duration-s") {
      if (i + 1 >= argc) {
        throw std::runtime_error("--duration-s requires a value");
      }
      opts.duration_s = std::stod(argv[++i]);
      if (opts.duration_s <= 0.0) {
        throw std::runtime_error("duration must be positive");
      }
      continue;
    }
    if (arg == "--dt-values") {
      if (i + 1 >= argc) {
        throw std::runtime_error("--dt-values requires a value");
      }
      opts.dt_values = parse_dt_values(argv[++i]);
      continue;
    }

    throw std::runtime_error("Unknown argument: " + arg);
  }

  return opts;
}

double analytical_temperature(const ScenarioConfig &scenario, double t) {
  if (scenario.heat_transfer_coeff <= 0.0) {
    const double slope = scenario.power / scenario.thermal_mass;
    return scenario.initial_temp + slope * t;
  }

  const double k = scenario.heat_transfer_coeff / scenario.thermal_mass;
  const double steady_state =
      scenario.ambient_temp + scenario.power / scenario.heat_transfer_coeff;
  return steady_state +
         (scenario.initial_temp - steady_state) * std::exp(-k * t);
}

ValidationPoint run_point(const ScenarioConfig &scenario,
                          ThermalIntegrationMethod method, double dt,
                          double duration_s) {
  const std::size_t steps =
      static_cast<std::size_t>(std::llround(duration_s / dt));
  if (steps == 0) {
    throw std::runtime_error("duration/dt produced zero steps");
  }

  SignalNamespace ns;
  SignalStore store;

  const std::string prefix = scenario.id + "." + std::string(to_string(method));
  const std::string temp_path = prefix + ".temp";
  const std::string power_path = prefix + ".power";
  const std::string ambient_path = prefix + ".ambient";

  const SignalId temp_id = ns.intern(temp_path);
  const SignalId power_id = ns.intern(power_path);
  const SignalId ambient_id = ns.intern(ambient_path);

  ThermalMassModel model("validation", scenario.thermal_mass,
                         scenario.heat_transfer_coeff, scenario.initial_temp,
                         temp_path, power_path, ambient_path, ns, method);

  double t = 0.0;
  double sum_sq = 0.0;
  double max_abs = 0.0;
  double final_abs = 0.0;

  for (std::size_t step = 0; step < steps; ++step) {
    store.write(power_id, scenario.power, "W");
    store.write(ambient_id, scenario.ambient_temp, "degC");

    model.tick(dt, store);
    t += dt;

    const double actual = store.read_value(temp_id);
    const double expected = analytical_temperature(scenario, t);
    const double abs_error = std::abs(actual - expected);
    sum_sq += abs_error * abs_error;
    if (abs_error > max_abs) {
      max_abs = abs_error;
    }
    final_abs = abs_error;
  }

  ValidationPoint point;
  point.dt = dt;
  point.steps = steps;
  point.l2_error = std::sqrt(sum_sq / static_cast<double>(steps));
  point.linf_error = max_abs;
  point.final_abs_error = final_abs;
  return point;
}

double estimate_order(const std::vector<ValidationPoint> &points, bool use_l2) {
  double n = 0.0;
  double sx = 0.0;
  double sy = 0.0;
  double sxx = 0.0;
  double sxy = 0.0;

  for (const auto &point : points) {
    const double err = use_l2 ? point.l2_error : point.linf_error;
    if (point.dt <= 0.0 || err <= 0.0) {
      continue;
    }
    const double x = std::log(point.dt);
    const double y = std::log(err);
    n += 1.0;
    sx += x;
    sy += y;
    sxx += x * x;
    sxy += x * y;
  }

  if (n < 2.0) {
    return 0.0;
  }

  const double denom = n * sxx - sx * sx;
  if (std::abs(denom) <= std::numeric_limits<double>::epsilon()) {
    return 0.0;
  }
  return (n * sxy - sx * sy) / denom;
}

MethodResult run_method(const ScenarioConfig &scenario,
                        ThermalIntegrationMethod method,
                        const std::vector<double> &dt_values,
                        double duration_s) {
  MethodResult result;
  result.method = to_string(method);

  for (double dt : dt_values) {
    result.points.push_back(run_point(scenario, method, dt, duration_s));
  }

  result.observed_order_l2 = estimate_order(result.points, true);
  result.observed_order_linf = estimate_order(result.points, false);
  return result;
}

std::string json_escape(const std::string &text) {
  std::string out;
  out.reserve(text.size());
  for (char ch : text) {
    switch (ch) {
    case '\\':
      out += "\\\\";
      break;
    case '"':
      out += "\\\"";
      break;
    case '\n':
      out += "\\n";
      break;
    case '\r':
      out += "\\r";
      break;
    case '\t':
      out += "\\t";
      break;
    default:
      out += ch;
      break;
    }
  }
  return out;
}

void write_csv(const std::string &path,
               const std::vector<ScenarioResult> &results) {
  if (path.empty()) {
    return;
  }
  std::ofstream out(path);
  if (!out) {
    throw std::runtime_error("Failed to open CSV output: " + path);
  }

  out << "scenario,method,dt,steps,l2_error,linf_error,final_abs_error\n";
  out << std::setprecision(17);
  for (const auto &scenario : results) {
    for (const auto &method : scenario.methods) {
      for (const auto &point : method.points) {
        out << scenario.config.id << "," << method.method << "," << point.dt
            << "," << point.steps << "," << point.l2_error << ","
            << point.linf_error << "," << point.final_abs_error << "\n";
      }
    }
  }
}

void write_json(const std::string &path, double duration_s,
                const std::vector<double> &dt_values,
                const std::vector<ScenarioResult> &results) {
  std::ostream *out_stream = &std::cout;
  std::ofstream file_out;
  if (!path.empty()) {
    file_out.open(path);
    if (!file_out) {
      throw std::runtime_error("Failed to open JSON output: " + path);
    }
    out_stream = &file_out;
  }
  std::ostream &out = *out_stream;

  double min_euler_order_linf = std::numeric_limits<double>::infinity();
  double min_rk4_order_linf = std::numeric_limits<double>::infinity();

  for (const auto &scenario : results) {
    for (const auto &method : scenario.methods) {
      if (method.method == "forward_euler" &&
          method.observed_order_linf < min_euler_order_linf) {
        min_euler_order_linf = method.observed_order_linf;
      } else if (method.method == "rk4" &&
                 method.observed_order_linf < min_rk4_order_linf) {
        min_rk4_order_linf = method.observed_order_linf;
      }
    }
  }

  out << std::setprecision(17);
  out << "{\n";
  out << "  \"schema_version\": 1,\n";
  out << "  \"duration_s\": " << duration_s << ",\n";
  out << "  \"dt_values\": [";
  for (std::size_t i = 0; i < dt_values.size(); ++i) {
    if (i > 0) {
      out << ", ";
    }
    out << dt_values[i];
  }
  out << "],\n";
  out << "  \"summary\": {\n";
  out << "    \"min_observed_order_linf\": {\n";
  out << "      \"forward_euler\": " << min_euler_order_linf << ",\n";
  out << "      \"rk4\": " << min_rk4_order_linf << "\n";
  out << "    }\n";
  out << "  },\n";
  out << "  \"scenarios\": [\n";

  for (std::size_t si = 0; si < results.size(); ++si) {
    const auto &scenario = results[si];
    out << "    {\n";
    out << "      \"id\": \"" << json_escape(scenario.config.id) << "\",\n";
    out << "      \"parameters\": {\n";
    out << "        \"thermal_mass\": " << scenario.config.thermal_mass
        << ",\n";
    out << "        \"heat_transfer_coeff\": "
        << scenario.config.heat_transfer_coeff << ",\n";
    out << "        \"initial_temp\": " << scenario.config.initial_temp
        << ",\n";
    out << "        \"ambient_temp\": " << scenario.config.ambient_temp
        << ",\n";
    out << "        \"power\": " << scenario.config.power << "\n";
    out << "      },\n";
    out << "      \"methods\": [\n";

    for (std::size_t mi = 0; mi < scenario.methods.size(); ++mi) {
      const auto &method = scenario.methods[mi];
      out << "        {\n";
      out << "          \"name\": \"" << json_escape(method.method) << "\",\n";
      out << "          \"observed_order_l2\": " << method.observed_order_l2
          << ",\n";
      out << "          \"observed_order_linf\": " << method.observed_order_linf
          << ",\n";
      out << "          \"points\": [\n";

      for (std::size_t pi = 0; pi < method.points.size(); ++pi) {
        const auto &point = method.points[pi];
        out << "            {\n";
        out << "              \"dt\": " << point.dt << ",\n";
        out << "              \"steps\": " << point.steps << ",\n";
        out << "              \"l2_error\": " << point.l2_error << ",\n";
        out << "              \"linf_error\": " << point.linf_error << ",\n";
        out << "              \"final_abs_error\": " << point.final_abs_error
            << "\n";
        out << "            }";
        if (pi + 1 < method.points.size()) {
          out << ",";
        }
        out << "\n";
      }

      out << "          ]\n";
      out << "        }";
      if (mi + 1 < scenario.methods.size()) {
        out << ",";
      }
      out << "\n";
    }

    out << "      ]\n";
    out << "    }";
    if (si + 1 < results.size()) {
      out << ",";
    }
    out << "\n";
  }

  out << "  ]\n";
  out << "}\n";
}

} // namespace

int main(int argc, char **argv) {
  Options opts;
  try {
    opts = parse_options(argc, argv);
  } catch (const std::runtime_error &e) {
    if (std::string(e.what()) == "help") {
      return 0;
    }
    std::cerr << "Argument error: " << e.what() << "\n";
    print_usage();
    return 2;
  } catch (const std::exception &e) {
    std::cerr << "Failed to parse options: " << e.what() << "\n";
    return 2;
  }

  const std::vector<ScenarioConfig> scenarios = {
      {
          "thermal.cooling.v1",
          10.0,
          5.0,
          100.0,
          0.0,
          0.0,
      },
      {
          "thermal.forced_response.v1",
          100.0,
          10.0,
          40.0,
          20.0,
          50.0,
      },
  };

  std::vector<ScenarioResult> results;
  results.reserve(scenarios.size());

  for (const auto &scenario : scenarios) {
    ScenarioResult scenario_result;
    scenario_result.config = scenario;
    scenario_result.methods.push_back(
        run_method(scenario, ThermalIntegrationMethod::ForwardEuler,
                   opts.dt_values, opts.duration_s));
    scenario_result.methods.push_back(
        run_method(scenario, ThermalIntegrationMethod::Rk4, opts.dt_values,
                   opts.duration_s));
    results.push_back(std::move(scenario_result));
  }

  try {
    write_csv(opts.output_csv, results);
    write_json(opts.output_json, opts.duration_s, opts.dt_values, results);
  } catch (const std::exception &e) {
    std::cerr << "Failed to write validation artifacts: " << e.what() << "\n";
    return 1;
  }

  return 0;
}

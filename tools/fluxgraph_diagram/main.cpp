#include "fluxgraph/graph/spec.hpp"
#include "fluxgraph/viz/dot_emitter.hpp"
#include "fluxgraph/viz/format.hpp"
#include "fluxgraph/viz/graphviz_renderer.hpp"

#ifdef FLUXGRAPH_JSON_ENABLED
#include "fluxgraph/loaders/json_loader.hpp"
#endif

#ifdef FLUXGRAPH_YAML_ENABLED
#include "fluxgraph/loaders/yaml_loader.hpp"
#endif

#include <algorithm>
#include <cctype>
#include <chrono>
#include <cstdlib>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <system_error>
#include <stdexcept>
#include <string>

namespace {

struct CliArgs {
  std::string input_path;
  std::string output_path;
  fluxgraph::viz::OutputFormat output_format = fluxgraph::viz::OutputFormat::Dot;
  std::string dot_binary = "dot";
  std::string dot_output_path;
};

std::string to_lower(std::string value) {
  std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
    return static_cast<char>(std::tolower(c));
  });
  return value;
}

void print_usage(const char *program) {
  std::cerr << "Usage: " << program
            << " --in <graph.{json|yaml|yml}> --out <output> "
               "[--format dot|svg|png] [--dot-bin <path>] [--dot-out <path>]\n";
}

CliArgs parse_args(int argc, char **argv) {
  CliArgs args;
  std::string format_value = "dot";

  for (int i = 1; i < argc; ++i) {
    const std::string token = argv[i];

    if (token == "--help" || token == "-h") {
      print_usage(argv[0]);
      std::exit(0);
    }

    if (token == "--in" || token == "--out" || token == "--format" ||
        token == "--dot-bin" || token == "--dot-out") {
      if (i + 1 >= argc) {
        throw std::runtime_error("Missing value for argument: " + token);
      }

      const std::string value = argv[++i];
      if (token == "--in") {
        args.input_path = value;
      } else if (token == "--out") {
        args.output_path = value;
      } else if (token == "--format") {
        format_value = value;
      } else if (token == "--dot-bin") {
        args.dot_binary = value;
      } else {
        args.dot_output_path = value;
      }
      continue;
    }

    throw std::runtime_error("Unknown argument: " + token);
  }

  if (args.input_path.empty()) {
    throw std::runtime_error("Missing required argument: --in");
  }

  if (args.output_path.empty()) {
    throw std::runtime_error("Missing required argument: --out");
  }

  const auto parsed_format = fluxgraph::viz::parse_output_format(format_value);
  if (!parsed_format.has_value()) {
    throw std::runtime_error("Unsupported format: " + format_value +
                             ". Valid values: dot, svg, png.");
  }
  args.output_format = parsed_format.value();

  if (args.output_format == fluxgraph::viz::OutputFormat::Dot &&
      !args.dot_output_path.empty() &&
      args.dot_output_path != args.output_path) {
    throw std::runtime_error(
        "For --format dot, --dot-out must match --out when provided.");
  }

  if (args.output_format != fluxgraph::viz::OutputFormat::Dot &&
      !args.dot_output_path.empty() &&
      args.dot_output_path == args.output_path) {
    throw std::runtime_error(
        "For image outputs, --dot-out must differ from --out.");
  }

  return args;
}

fluxgraph::GraphSpec load_graph_spec(const std::string &path) {
  const std::string extension =
      to_lower(std::filesystem::path(path).extension().string());

  if (extension == ".json") {
#ifdef FLUXGRAPH_JSON_ENABLED
    return fluxgraph::loaders::load_json_file(path);
#else
    throw std::runtime_error(
        "JSON input requested, but FLUXGRAPH_JSON_ENABLED is OFF.");
#endif
  }

  if (extension == ".yaml" || extension == ".yml") {
#ifdef FLUXGRAPH_YAML_ENABLED
    return fluxgraph::loaders::load_yaml_file(path);
#else
    throw std::runtime_error(
        "YAML input requested, but FLUXGRAPH_YAML_ENABLED is OFF.");
#endif
  }

  throw std::runtime_error(
      "Unsupported input extension '" + extension +
      "'. Use .json, .yaml, or .yml input files.");
}

void write_text_file(const std::string &path, const std::string &content) {
  const auto output_path = std::filesystem::path(path);
  if (output_path.has_parent_path()) {
    std::error_code ec;
    std::filesystem::create_directories(output_path.parent_path(), ec);
    if (ec) {
      throw std::runtime_error("Failed to create output directory for: " + path);
    }
  }

  std::ofstream stream(path, std::ios::binary);
  if (!stream) {
    throw std::runtime_error("Failed to open output path: " + path);
  }

  stream << content;
  if (!stream) {
    throw std::runtime_error("Failed writing output file: " + path);
  }
}

std::string create_temp_dot_path() {
  std::error_code ec;
  std::filesystem::path temp_dir = std::filesystem::temp_directory_path(ec);
  if (ec) {
    temp_dir = std::filesystem::current_path();
  }

  const auto now_ticks =
      std::chrono::steady_clock::now().time_since_epoch().count();
  for (int attempt = 0; attempt < 64; ++attempt) {
    const std::string filename =
        "fluxgraph-diagram-" + std::to_string(now_ticks) + "-" +
        std::to_string(attempt) + ".dot";
    const auto candidate = temp_dir / filename;
    if (!std::filesystem::exists(candidate)) {
      return candidate.string();
    }
  }

  throw std::runtime_error("Failed to create a temporary DOT path.");
}

} // namespace

int main(int argc, char **argv) {
  CliArgs args;
  try {
    args = parse_args(argc, argv);
  } catch (const std::exception &ex) {
    std::cerr << "error: " << ex.what() << "\n";
    print_usage(argv[0]);
    return 2;
  }

  try {
    const fluxgraph::GraphSpec spec = load_graph_spec(args.input_path);
    const auto extension_types =
        fluxgraph::viz::collect_extension_transform_types(spec);
    for (const auto &type : extension_types) {
      std::cerr << "warning: extension transform type '" << type
                << "' rendered as annotation.\n";
    }

    const std::string dot = fluxgraph::viz::emit_dot(spec);
    if (args.output_format == fluxgraph::viz::OutputFormat::Dot) {
      write_text_file(args.output_path, dot);
      std::cout << "Wrote DOT graph to: " << args.output_path << "\n";
      return 0;
    }

    std::string dot_source_path = args.dot_output_path;
    bool using_temp_dot_path = false;
    if (dot_source_path.empty()) {
      dot_source_path = create_temp_dot_path();
      using_temp_dot_path = true;
    }
    write_text_file(dot_source_path, dot);

    const fluxgraph::viz::GraphvizRenderRequest render_request{
        args.dot_binary,
        dot_source_path,
        args.output_path,
        args.output_format,
    };
    const auto render_result = fluxgraph::viz::render_with_graphviz(render_request);
    if (!render_result.success) {
      std::cerr << "error: " << render_result.message << "\n";
      if (!render_result.command.empty()) {
        std::cerr << "command: " << render_result.command << "\n";
      }
      if (using_temp_dot_path) {
        std::cerr << "DOT source kept at: " << dot_source_path << "\n";
      }
      return 3;
    }

    if (using_temp_dot_path) {
      std::error_code ec;
      std::filesystem::remove(dot_source_path, ec);
    } else {
      std::cout << "Wrote DOT graph to: " << dot_source_path << "\n";
    }

    std::cout << "Wrote " << fluxgraph::viz::output_format_name(args.output_format)
              << " graph to: " << args.output_path << "\n";
    return 0;
  } catch (const std::exception &ex) {
    std::cerr << "error: " << ex.what() << "\n";
    return 1;
  }
}

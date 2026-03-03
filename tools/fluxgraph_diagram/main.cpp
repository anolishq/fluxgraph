#include "fluxgraph/graph/spec.hpp"
#include "fluxgraph/viz/dot_emitter.hpp"

#ifdef FLUXGRAPH_JSON_ENABLED
#include "fluxgraph/loaders/json_loader.hpp"
#endif

#ifdef FLUXGRAPH_YAML_ENABLED
#include "fluxgraph/loaders/yaml_loader.hpp"
#endif

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

struct CliArgs {
  std::string input_path;
  std::string output_path;
  std::string format = "dot";
};

std::string to_lower(std::string value) {
  std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
    return static_cast<char>(std::tolower(c));
  });
  return value;
}

void print_usage(const char *program) {
  std::cerr << "Usage: " << program
            << " --in <graph.{json|yaml|yml}> --out <output.dot> "
               "[--format dot]\n";
}

CliArgs parse_args(int argc, char **argv) {
  CliArgs args;

  for (int i = 1; i < argc; ++i) {
    const std::string token = argv[i];

    if (token == "--help" || token == "-h") {
      print_usage(argv[0]);
      std::exit(0);
    }

    if (token == "--in" || token == "--out" || token == "--format") {
      if (i + 1 >= argc) {
        throw std::runtime_error("Missing value for argument: " + token);
      }

      const std::string value = argv[++i];
      if (token == "--in") {
        args.input_path = value;
      } else if (token == "--out") {
        args.output_path = value;
      } else {
        args.format = to_lower(value);
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
  std::ofstream stream(path, std::ios::binary);
  if (!stream) {
    throw std::runtime_error("Failed to open output path: " + path);
  }

  stream << content;
  if (!stream) {
    throw std::runtime_error("Failed writing output file: " + path);
  }
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

  if (args.format != "dot") {
    std::cerr << "error: Unsupported format '" << args.format
              << "' in this phase. Only '--format dot' is available.\n";
    return 2;
  }

  try {
    const fluxgraph::GraphSpec spec = load_graph_spec(args.input_path);
    const auto extension_types = fluxgraph::viz::collect_extension_transform_types(spec);
    for (const auto &type : extension_types) {
      std::cerr << "warning: extension transform type '" << type
                << "' rendered as annotation.\n";
    }

    const std::string dot = fluxgraph::viz::emit_dot(spec);
    write_text_file(args.output_path, dot);

    std::cout << "Wrote DOT graph to: " << args.output_path << "\n";
    return 0;
  } catch (const std::exception &ex) {
    std::cerr << "error: " << ex.what() << "\n";
    return 1;
  }
}

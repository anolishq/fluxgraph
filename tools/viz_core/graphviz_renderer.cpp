#include "fluxgraph/viz/graphviz_renderer.hpp"

#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <sstream>
#include <string>
#include <vector>

#ifdef _WIN32
#include <process.h>
#endif

namespace fluxgraph::viz {

namespace {

std::string shell_quote(const std::string &value) {
  std::string quoted = "\"";
  quoted.reserve(value.size() + 2U);
  for (char ch : value) {
    if (ch == '"') {
      quoted += "\\\"";
    } else {
      quoted.push_back(ch);
    }
  }
  quoted.push_back('"');
  return quoted;
}

} // namespace

std::string build_graphviz_command(const GraphvizRenderRequest &request) {
  std::ostringstream command;
  command << shell_quote(request.dot_binary) << " -T"
          << output_format_name(request.output_format) << " "
          << shell_quote(request.dot_input_path) << " -o "
          << shell_quote(request.output_path);
  return command.str();
}

GraphvizRenderResult render_with_graphviz(const GraphvizRenderRequest &request) {
  GraphvizRenderResult result;

  if (request.output_format == OutputFormat::Dot) {
    result.message = "Graphviz renderer is only valid for svg/png outputs.";
    return result;
  }

  if (request.dot_input_path.empty()) {
    result.message = "DOT input path is required for Graphviz rendering.";
    return result;
  }

  if (request.output_path.empty()) {
    result.message = "Output path is required for Graphviz rendering.";
    return result;
  }

  result.command = build_graphviz_command(request);

  int exit_code = -1;
#ifdef _WIN32
  // Use direct process invocation on Windows to avoid cmd.exe quoting pitfalls.
  std::vector<std::string> arg_storage;
  arg_storage.reserve(5);
  arg_storage.push_back(request.dot_binary);
  arg_storage.push_back(std::string("-T") + output_format_name(request.output_format));
  arg_storage.push_back(request.dot_input_path);
  arg_storage.push_back("-o");
  arg_storage.push_back(request.output_path);

  std::vector<const char *> argv;
  argv.reserve(arg_storage.size() + 1U);
  for (const auto &value : arg_storage) {
    argv.push_back(value.c_str());
  }
  argv.push_back(nullptr);

  const intptr_t spawn_result =
      _spawnvp(_P_WAIT, request.dot_binary.c_str(), argv.data());
  if (spawn_result == static_cast<intptr_t>(-1)) {
    char error_buffer[128] = {};
    strerror_s(error_buffer, sizeof(error_buffer), errno);
    std::ostringstream message;
    message << "Failed to launch Graphviz renderer '" << request.dot_binary
            << "': " << error_buffer;
    result.message = message.str();
    result.process_exit_code = -1;
    return result;
  }

  if (spawn_result > static_cast<intptr_t>(std::numeric_limits<int>::max())) {
    result.message = "Graphviz renderer returned an out-of-range exit code.";
    result.process_exit_code = -1;
    return result;
  }

  exit_code = static_cast<int>(spawn_result);
#else
  exit_code = std::system(result.command.c_str());
#endif

  result.process_exit_code = exit_code;

  if (exit_code == 0) {
    result.success = true;
    return result;
  }

  std::ostringstream message;
  message << "Graphviz renderer command failed with exit code " << exit_code;
  result.message = message.str();
  return result;
}

} // namespace fluxgraph::viz

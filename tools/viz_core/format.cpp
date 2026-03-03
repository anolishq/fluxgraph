#include "fluxgraph/viz/format.hpp"

#include <algorithm>
#include <cctype>

namespace fluxgraph::viz {

namespace {

std::string to_lower(std::string value) {
  std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
    return static_cast<char>(std::tolower(c));
  });
  return value;
}

} // namespace

std::optional<OutputFormat> parse_output_format(const std::string &value) {
  const std::string normalized = to_lower(value);
  if (normalized == "dot") {
    return OutputFormat::Dot;
  }
  if (normalized == "svg") {
    return OutputFormat::Svg;
  }
  if (normalized == "png") {
    return OutputFormat::Png;
  }
  return std::nullopt;
}

const char *output_format_name(OutputFormat format) {
  switch (format) {
  case OutputFormat::Dot:
    return "dot";
  case OutputFormat::Svg:
    return "svg";
  case OutputFormat::Png:
    return "png";
  }

  return "unknown";
}

} // namespace fluxgraph::viz


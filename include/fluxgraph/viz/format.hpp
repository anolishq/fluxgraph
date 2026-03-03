#pragma once

#include <optional>
#include <string>

namespace fluxgraph::viz {

enum class OutputFormat {
  Dot,
  Svg,
  Png,
};

std::optional<OutputFormat> parse_output_format(const std::string &value);
const char *output_format_name(OutputFormat format);

} // namespace fluxgraph::viz


#pragma once

#include <string_view>

#include "fluxgraph/v2/setting.hpp"
#include "fluxgraph/v2/status.hpp"

namespace fluxgraph::v2 {

/// Reads a graph from the text of a file, for Engine::compile to judge.
///
/// A loader decides as little as it can (rule 9.7). It gives whole numbers, numbers, booleans, text, lists and
/// maps, and what a key or a value may be is the compiler's. It refuses, with Errc::file_refused and a message
/// that says where:
///
/// - text that is not the format;
/// - a key given twice in one map;
/// - a null: JSON's `null`, and YAML's `~`, `null` and a value left empty;
/// - a key that is not text.
///
/// A whole number is one written without a point or an exponent, and a number one written with either
/// (rule 9.4). A whole number 64 bits, signed, do not hold is given as the nearest number.
///
/// Each is in a library of its own, so that the core has no dependency: `fluxgraph_v2_json`, built with
/// FLUXGRAPH_JSON_ENABLED, and `fluxgraph_v2_yaml`, built with FLUXGRAPH_YAML_ENABLED.

/// JSON, as RFC 8259 has it.
Result<Setting> load_json(std::string_view text);

/// YAML, with a value that is not quoted read by the core schema of YAML 1.2:
///
/// - `true`, `True`, `TRUE`, `false`, `False` and `FALSE` are booleans, and nothing else is: `on`, `yes` and `no`
///   are text;
/// - a whole number is digits with a sign or without, or `0o` and octal digits, or `0x` and hexadecimal ones;
/// - a number is digits with a point, an exponent or both, or `.inf` and `.nan` in the three cases YAML gives;
/// - anything else is text: `2.5s`, `none`, a name.
///
/// A value in quotes, or written as a block, is text whatever it holds, and so is one tagged `!!str`. Any other
/// tag is refused. The first document of the text is read.
Result<Setting> load_yaml(std::string_view text);

}  // namespace fluxgraph::v2

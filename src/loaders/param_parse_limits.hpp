#pragma once

#include <cstddef>
#include <stdexcept>
#include <string>

namespace fluxgraph::loaders::detail {

struct ParamParseLimits {
  static constexpr size_t kMaxDepth = 32;
  static constexpr size_t kMaxNodes = 250000;
  static constexpr size_t kMaxObjectMembers = 4096;
  static constexpr size_t kMaxArrayElements = 65536;
  static constexpr size_t kMaxStringBytes = 1 << 20; // 1 MiB
};

struct ParamParseBudget {
  size_t nodes = 0;

  void consume_node(const std::string &path) {
    ++nodes;
    if (nodes > ParamParseLimits::kMaxNodes) {
      throw std::runtime_error("Parameter parse error at " + path +
                               ": node count exceeds limit (" +
                               std::to_string(ParamParseLimits::kMaxNodes) +
                               ")");
    }
  }

  void check_depth(size_t depth, const std::string &path) const {
    if (depth > ParamParseLimits::kMaxDepth) {
      throw std::runtime_error("Parameter parse error at " + path +
                               ": nesting depth exceeds limit (" +
                               std::to_string(ParamParseLimits::kMaxDepth) +
                               ")");
    }
  }
};

inline void check_object_size(size_t size, const std::string &path) {
  if (size > ParamParseLimits::kMaxObjectMembers) {
    throw std::runtime_error("Parameter parse error at " + path +
                             ": object member count exceeds limit (" +
                             std::to_string(ParamParseLimits::kMaxObjectMembers) +
                             ")");
  }
}

inline void check_array_size(size_t size, const std::string &path) {
  if (size > ParamParseLimits::kMaxArrayElements) {
    throw std::runtime_error("Parameter parse error at " + path +
                             ": array length exceeds limit (" +
                             std::to_string(ParamParseLimits::kMaxArrayElements) +
                             ")");
  }
}

inline void check_string_size(size_t size, const std::string &path) {
  if (size > ParamParseLimits::kMaxStringBytes) {
    throw std::runtime_error("Parameter parse error at " + path +
                             ": string length exceeds limit (" +
                             std::to_string(ParamParseLimits::kMaxStringBytes) +
                             " bytes)");
  }
}

} // namespace fluxgraph::loaders::detail

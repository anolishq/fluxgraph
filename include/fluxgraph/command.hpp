#pragma once

#include <map>

#include "fluxgraph/core/types.hpp"

namespace fluxgraph {

/// Represents a command to be routed to a provider
struct Command {
    DeviceId device;
    FunctionId function;
    std::map<std::string, Variant> args;

    Command() : device(INVALID_DEVICE), function(INVALID_FUNCTION) {}

    Command(DeviceId dev, FunctionId func) : device(dev), function(func) {}
};

}  // namespace fluxgraph

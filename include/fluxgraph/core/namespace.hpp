#pragma once

#include <map>
#include <string>
#include <vector>

#include "fluxgraph/core/types.hpp"

namespace fluxgraph {

/// Maps signal paths (e.g., "tempctl0/chamber/temperature") to SignalIds
/// Design: Compile-time (intern) vs runtime (resolve) separation
class SignalNamespace {
public:
    SignalNamespace();
    ~SignalNamespace();

    /// Compile-time: Create a new ID for a path (or return existing)
    /// Used during graph compilation
    SignalId intern(const std::string &path);

    /// Runtime: Resolve an existing path (returns INVALID_SIGNAL if unknown)
    /// Used during command processing
    SignalId resolve(const std::string &path) const;

    /// Reverse lookup: Get path from ID
    std::string lookup(SignalId id) const;

    /// Get total number of interned paths
    size_t size() const;

    /// Get all interned paths
    std::vector<std::string> all_paths() const;

    /// Clear all mappings
    void clear();

private:
    std::map<std::string, SignalId> path_to_id_;
    std::map<SignalId, std::string> id_to_path_;
    SignalId next_id_ = 0;
};

/// Maps device/function names to IDs for command routing
class FunctionNamespace {
public:
    FunctionNamespace();
    ~FunctionNamespace();

    /// Intern a device name (returns existing ID if already interned)
    DeviceId intern_device(const std::string &name);

    /// Intern a function name (returns existing ID if already interned)
    FunctionId intern_function(const std::string &name);

    /// Lookup device name from ID
    std::string lookup_device(DeviceId id) const;

    /// Lookup function name from ID
    std::string lookup_function(FunctionId id) const;

    /// Get device ID (returns INVALID_DEVICE if not found)
    DeviceId resolve_device(const std::string &name) const;

    /// Get function ID (returns INVALID_FUNCTION if not found)
    FunctionId resolve_function(const std::string &name) const;

    /// Clear all mappings
    void clear();

private:
    std::map<std::string, DeviceId> device_map_;
    std::map<DeviceId, std::string> device_reverse_;
    std::map<std::string, FunctionId> function_map_;
    std::map<FunctionId, std::string> function_reverse_;
    DeviceId next_device_id_ = 0;
    FunctionId next_function_id_ = 0;
};

}  // namespace fluxgraph

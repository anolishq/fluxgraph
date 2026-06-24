#include "fluxgraph/core/namespace.hpp"

namespace fluxgraph {

// SignalNamespace implementation

SignalNamespace::SignalNamespace() = default;
SignalNamespace::~SignalNamespace() = default;

SignalId SignalNamespace::intern(const std::string &path) {
    auto it = path_to_id_.find(path);
    if (it != path_to_id_.end()) {
        return it->second;  // Already interned
    }

    SignalId id = next_id_++;
    path_to_id_[path] = id;
    id_to_path_[id] = path;
    return id;
}

SignalId SignalNamespace::resolve(const std::string &path) const {
    auto it = path_to_id_.find(path);
    if (it != path_to_id_.end()) {
        return it->second;
    }
    return INVALID_SIGNAL;
}

std::string SignalNamespace::lookup(SignalId id) const {
    auto it = id_to_path_.find(id);
    if (it != id_to_path_.end()) {
        return it->second;
    }
    return "";  // Return empty string for unknown IDs
}

size_t SignalNamespace::size() const { return path_to_id_.size(); }

std::vector<std::string> SignalNamespace::all_paths() const {
    std::vector<std::string> paths;
    paths.reserve(path_to_id_.size());
    for (const auto &[path, id] : path_to_id_) {
        paths.push_back(path);
    }
    return paths;
}

void SignalNamespace::clear() {
    path_to_id_.clear();
    id_to_path_.clear();
    next_id_ = 0;
}

// FunctionNamespace implementation

FunctionNamespace::FunctionNamespace() = default;
FunctionNamespace::~FunctionNamespace() = default;

DeviceId FunctionNamespace::intern_device(const std::string &name) {
    auto it = device_map_.find(name);
    if (it != device_map_.end()) {
        return it->second;
    }

    DeviceId id = next_device_id_++;
    device_map_[name] = id;
    device_reverse_[id] = name;
    return id;
}

FunctionId FunctionNamespace::intern_function(const std::string &name) {
    auto it = function_map_.find(name);
    if (it != function_map_.end()) {
        return it->second;
    }

    FunctionId id = next_function_id_++;
    function_map_[name] = id;
    function_reverse_[id] = name;
    return id;
}

std::string FunctionNamespace::lookup_device(DeviceId id) const {
    auto it = device_reverse_.find(id);
    if (it != device_reverse_.end()) {
        return it->second;
    }
    return "";
}

std::string FunctionNamespace::lookup_function(FunctionId id) const {
    auto it = function_reverse_.find(id);
    if (it != function_reverse_.end()) {
        return it->second;
    }
    return "";
}

DeviceId FunctionNamespace::resolve_device(const std::string &name) const {
    auto it = device_map_.find(name);
    if (it != device_map_.end()) {
        return it->second;
    }
    return INVALID_DEVICE;
}

FunctionId FunctionNamespace::resolve_function(const std::string &name) const {
    auto it = function_map_.find(name);
    if (it != function_map_.end()) {
        return it->second;
    }
    return INVALID_FUNCTION;
}

void FunctionNamespace::clear() {
    device_map_.clear();
    device_reverse_.clear();
    function_map_.clear();
    function_reverse_.clear();
    next_device_id_ = 0;
    next_function_id_ = 0;
}

}  // namespace fluxgraph

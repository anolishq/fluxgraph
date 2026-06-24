#pragma once

#include <mutex>
#include <string>
#include <unordered_map>

#include "fluxgraph/graph/compiler.hpp"

namespace fluxgraph::compiler_internal {

struct TransformRegistryEntry {
    GraphCompiler::TransformFactory factory;
    bool has_signature = false;
    TransformSignature signature;
};

struct ModelRegistryEntry {
    GraphCompiler::ModelFactory factory;
    bool has_signature = false;
    ModelSignature signature;
};

struct FactoryRegistry {
    std::mutex mutex;
    bool defaults_registered = false;
    std::unordered_map<std::string, TransformRegistryEntry> transform_factories;
    std::unordered_map<std::string, ModelRegistryEntry> model_factories;
};

FactoryRegistry &factory_registry();
void validate_registration_request(const std::string &type, bool has_factory, const std::string &kind);
void ensure_default_factories_registered_locked(FactoryRegistry &registry);

const TransformRegistryEntry &resolve_transform_entry_or_throw(FactoryRegistry &registry, const std::string &type);
const ModelRegistryEntry &resolve_model_entry_or_throw(FactoryRegistry &registry, const std::string &type);

}  // namespace fluxgraph::compiler_internal

#include "registry.hpp"

#include <stdexcept>

#include "common.hpp"
#include "registry_builtins.hpp"

namespace fluxgraph::compiler_internal {

FactoryRegistry &factory_registry() {
    static FactoryRegistry registry;
    return registry;
}

void validate_registration_request(const std::string &type, bool has_factory, const std::string &kind) {
    if (trim_copy(type).empty()) {
        throw std::invalid_argument("GraphCompiler: " + kind + " type must be non-empty");
    }
    if (!has_factory) {
        throw std::invalid_argument("GraphCompiler: " + kind + " factory must be valid");
    }
}

void ensure_default_factories_registered_locked(FactoryRegistry &registry) {
    if (registry.defaults_registered) {
        return;
    }

    register_builtin_transforms(registry);
    register_builtin_models_thermal(registry);
    register_builtin_models_control(registry);
    register_builtin_models_state_space(registry);
    register_builtin_models_mechanical(registry);
    register_builtin_models_electromechanical(registry);

    registry.defaults_registered = true;
}

const TransformRegistryEntry &resolve_transform_entry_or_throw(FactoryRegistry &registry, const std::string &type) {
    auto it = registry.transform_factories.find(type);
    if (it == registry.transform_factories.end()) {
        throw std::runtime_error("Unknown transform type: " + type);
    }
    return it->second;
}

const ModelRegistryEntry &resolve_model_entry_or_throw(FactoryRegistry &registry, const std::string &type) {
    auto it = registry.model_factories.find(type);
    if (it == registry.model_factories.end()) {
        throw std::runtime_error("Unknown model type: " + type);
    }
    return it->second;
}

}  // namespace fluxgraph::compiler_internal

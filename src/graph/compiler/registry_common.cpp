#include <utility>

#include "registry_builtins.hpp"

namespace fluxgraph::compiler_internal {

void register_builtin_transform(FactoryRegistry &registry, const std::string &type,
                                GraphCompiler::TransformFactory factory, TransformSignature::Contract contract) {
    TransformRegistryEntry entry;
    entry.factory = std::move(factory);
    entry.has_signature = true;
    entry.signature.contract = contract;
    registry.transform_factories.emplace(type, std::move(entry));
}

void register_builtin_model(FactoryRegistry &registry, const std::string &type, GraphCompiler::ModelFactory factory,
                            ModelSignature signature) {
    ModelRegistryEntry entry;
    entry.factory = std::move(factory);
    entry.has_signature = true;
    entry.signature = std::move(signature);
    registry.model_factories.emplace(type, std::move(entry));
}

}  // namespace fluxgraph::compiler_internal

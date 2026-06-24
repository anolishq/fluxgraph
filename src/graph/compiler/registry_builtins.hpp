#pragma once

#include <string>

#include "registry.hpp"

namespace fluxgraph::compiler_internal {

void register_builtin_transform(FactoryRegistry &registry, const std::string &type,
                                GraphCompiler::TransformFactory factory,
                                TransformSignature::Contract contract = TransformSignature::Contract::preserve);

void register_builtin_model(FactoryRegistry &registry, const std::string &type, GraphCompiler::ModelFactory factory,
                            ModelSignature signature);

void register_builtin_transforms(FactoryRegistry &registry);
void register_builtin_models_thermal(FactoryRegistry &registry);
void register_builtin_models_control(FactoryRegistry &registry);
void register_builtin_models_state_space(FactoryRegistry &registry);
void register_builtin_models_mechanical(FactoryRegistry &registry);
void register_builtin_models_electromechanical(FactoryRegistry &registry);

}  // namespace fluxgraph::compiler_internal

#pragma once

#include <string>
#include <unordered_map>

#include "fluxgraph/core/units.hpp"
#include "fluxgraph/graph/compiler.hpp"

namespace fluxgraph::compiler_internal {

void emit_warning(const CompilationOptions &options, const std::string &message);

bool is_unit_known(const UnitRegistry &registry, const std::string &unit);
bool has_compatible_dimension_and_kind(const UnitRegistry &registry, const std::string &lhs_unit,
                                       const std::string &rhs_unit);

std::string resolve_signal_contract_or_empty(const std::unordered_map<SignalId, std::string> &signal_contracts,
                                             SignalId id);

void validate_model_signature_contracts(const ModelSpec &model_spec, const ModelSignature &signature,
                                        SignalNamespace &signal_ns,
                                        const std::unordered_map<SignalId, std::string> &signal_contracts,
                                        const UnitRegistry &unit_registry, const CompilationOptions &options,
                                        bool strict);

}  // namespace fluxgraph::compiler_internal

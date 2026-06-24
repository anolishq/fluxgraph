#pragma once

#include <string>
#include <vector>

#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/model/integration.hpp"
#include "fluxgraph/model/interface.hpp"

namespace fluxgraph {

/// First-order (PT1) process model with a single state and one input.
///
/// Dynamics:
///   dy/dt = (gain * u - y) / tau
///
/// Signal contracts:
/// - input_signal: dimensionless
/// - output_signal: dimensionless
class FirstOrderProcessModel : public IModel {
public:
    FirstOrderProcessModel(const std::string &id, double gain, double tau_s, double initial_output,
                           const std::string &output_signal_path, const std::string &input_signal_path,
                           SignalNamespace &ns, IntegrationMethod integration_method = IntegrationMethod::ForwardEuler);

    void tick(double dt, SignalStore &store) override;
    void reset() override;
    double compute_stability_limit() const override;
    std::string describe() const override;
    std::vector<SignalId> output_signal_ids() const override;

private:
    double derivative(double y, double u) const;

    std::string id_;
    SignalId output_signal_;
    SignalId input_signal_;
    double gain_;
    double tau_s_;
    double output_;
    double initial_output_;
    IntegrationMethod integration_method_;
};

}  // namespace fluxgraph

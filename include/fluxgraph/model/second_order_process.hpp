#pragma once

#include <string>
#include <vector>

#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/model/integration.hpp"
#include "fluxgraph/model/interface.hpp"

namespace fluxgraph {

/// Second-order process model (canonical damped oscillator form).
///
/// Dynamics:
///   y'' + 2*zeta*omega_n*y' + omega_n^2*y = omega_n^2 * gain * u
///
/// State:
/// - y (dimensionless)
/// - y_dot (1/s)
///
/// Signal contracts:
/// - input_signal: dimensionless
/// - output_signal: dimensionless
class SecondOrderProcessModel : public IModel {
public:
    SecondOrderProcessModel(const std::string &id, double gain, double zeta, double omega_n_rad_s,
                            double initial_output, double initial_output_rate, const std::string &output_signal_path,
                            const std::string &input_signal_path, SignalNamespace &ns,
                            IntegrationMethod integration_method = IntegrationMethod::ForwardEuler);

    void tick(double dt, SignalStore &store) override;
    void reset() override;
    double compute_stability_limit() const override;
    std::string describe() const override;
    std::vector<SignalId> output_signal_ids() const override;

private:
    struct Derivative {
        double dy = 0.0;
        double dy_dot = 0.0;
    };

    Derivative derivative(double y, double y_dot, double u) const;

    std::string id_;
    SignalId output_signal_;
    SignalId input_signal_;
    double gain_;
    double zeta_;
    double omega_n_rad_s_;
    double y_;
    double y_dot_;
    double initial_output_;
    double initial_output_rate_;
    IntegrationMethod integration_method_;
};

}  // namespace fluxgraph

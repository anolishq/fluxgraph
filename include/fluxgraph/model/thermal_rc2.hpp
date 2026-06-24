#pragma once

#include <string>
#include <vector>

#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/model/interface.hpp"
#include "fluxgraph/model/thermal_integration.hpp"

namespace fluxgraph {

/// Two-node thermal RC model with ambient coupling and inter-node conductance.
///
/// State:
/// - T_a, T_b (degC)
///
/// Inputs:
/// - power_signal (W) applied to node A
/// - ambient_signal (degC) shared ambient temperature
///
/// Parameters:
/// - thermal_mass_a, thermal_mass_b (J/K)
/// - heat_transfer_coeff_a, heat_transfer_coeff_b (W/K)
/// - coupling_coeff (W/K) conductance between nodes
///
/// Dynamics:
///   dT_a/dt = (P - h_a*(T_a - T_amb) - k*(T_a - T_b)) / C_a
///   dT_b/dt = (-h_b*(T_b - T_amb) + k*(T_a - T_b)) / C_b
class ThermalRc2Model : public IModel {
public:
    ThermalRc2Model(const std::string &id, double thermal_mass_a, double thermal_mass_b, double heat_transfer_coeff_a,
                    double heat_transfer_coeff_b, double coupling_coeff, double initial_temp_a, double initial_temp_b,
                    const std::string &temp_signal_a_path, const std::string &temp_signal_b_path,
                    const std::string &power_signal_path, const std::string &ambient_signal_path, SignalNamespace &ns,
                    ThermalIntegrationMethod integration_method = ThermalIntegrationMethod::ForwardEuler);

    void tick(double dt, SignalStore &store) override;
    void reset() override;
    double compute_stability_limit() const override;
    std::string describe() const override;
    std::vector<SignalId> output_signal_ids() const override;

private:
    struct Derivative {
        double dTa = 0.0;
        double dTb = 0.0;
    };

    Derivative derivative(double Ta, double Tb, double power, double ambient) const;

    std::string id_;
    SignalId temp_a_signal_;
    SignalId temp_b_signal_;
    SignalId power_signal_;
    SignalId ambient_signal_;

    double thermal_mass_a_;
    double thermal_mass_b_;
    double heat_transfer_coeff_a_;
    double heat_transfer_coeff_b_;
    double coupling_coeff_;

    double temp_a_;
    double temp_b_;
    double initial_temp_a_;
    double initial_temp_b_;

    ThermalIntegrationMethod integration_method_;
};

}  // namespace fluxgraph

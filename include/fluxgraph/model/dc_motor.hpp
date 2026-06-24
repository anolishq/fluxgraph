#pragma once

#include <string>
#include <vector>

#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/model/integration.hpp"
#include "fluxgraph/model/interface.hpp"

namespace fluxgraph {

/// DC motor model with armature electrical dynamics and viscous friction.
///
/// Dynamics:
///   di/dt     = (V - R*i - K_e*omega) / L
///   domega/dt = (K_t*i - b*omega - tau_load) / J
///
/// State:
/// - i (A)
/// - omega (rad/s)
///
/// Signal contracts:
/// - voltage_signal: V
/// - load_torque_signal: N*m
/// - speed_signal: rad/s
/// - current_signal: A
/// - torque_signal: N*m
class DcMotorModel : public IModel {
public:
    DcMotorModel(const std::string &id, double resistance_ohm, double inductance_h, double torque_constant,
                 double back_emf_constant, double inertia, double viscous_friction, double initial_current,
                 double initial_speed, const std::string &speed_signal_path, const std::string &current_signal_path,
                 const std::string &torque_signal_path, const std::string &voltage_signal_path,
                 const std::string &load_torque_signal_path, SignalNamespace &ns,
                 IntegrationMethod integration_method = IntegrationMethod::ForwardEuler);

    void tick(double dt, SignalStore &store) override;
    void reset() override;
    double compute_stability_limit() const override;
    std::string describe() const override;
    std::vector<SignalId> output_signal_ids() const override;

private:
    struct Derivative {
        double di = 0.0;
        double domega = 0.0;
    };

    Derivative derivative(double i, double omega, double voltage, double load_torque) const;

    std::string id_;
    SignalId speed_signal_;
    SignalId current_signal_;
    SignalId torque_signal_;
    SignalId voltage_signal_;
    SignalId load_torque_signal_;

    double resistance_ohm_;
    double inductance_h_;
    double torque_constant_;
    double back_emf_constant_;
    double inertia_;
    double viscous_friction_;

    double i_;
    double omega_;
    double initial_current_;
    double initial_speed_;

    IntegrationMethod integration_method_;
};

}  // namespace fluxgraph

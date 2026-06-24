#pragma once

#include <string>
#include <vector>

#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/model/integration.hpp"
#include "fluxgraph/model/interface.hpp"

namespace fluxgraph {

/// Translational single-degree-of-freedom mass-spring-damper model.
///
/// Dynamics:
///   m * x'' + c * x' + k * x = F
///
/// State:
/// - x (m)
/// - v = x' (m/s)
///
/// Signal contracts:
/// - force_signal: N
/// - position_signal: m
/// - velocity_signal: m/s
class MassSpringDamperModel : public IModel {
public:
    MassSpringDamperModel(const std::string &id, double mass, double damping_coeff, double spring_constant,
                          double initial_position, double initial_velocity, const std::string &position_signal_path,
                          const std::string &velocity_signal_path, const std::string &force_signal_path,
                          SignalNamespace &ns, IntegrationMethod integration_method = IntegrationMethod::ForwardEuler);

    void tick(double dt, SignalStore &store) override;
    void reset() override;
    double compute_stability_limit() const override;
    std::string describe() const override;
    std::vector<SignalId> output_signal_ids() const override;

private:
    struct Derivative {
        double dx = 0.0;
        double dv = 0.0;
    };

    Derivative derivative(double x, double v, double force) const;

    std::string id_;
    SignalId position_signal_;
    SignalId velocity_signal_;
    SignalId force_signal_;

    double mass_;
    double damping_coeff_;
    double spring_constant_;

    double x_;
    double v_;
    double initial_position_;
    double initial_velocity_;

    IntegrationMethod integration_method_;
};

}  // namespace fluxgraph

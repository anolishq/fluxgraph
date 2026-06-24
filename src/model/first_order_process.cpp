#include "fluxgraph/model/first_order_process.hpp"

#include <cmath>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace fluxgraph {

namespace {

bool is_finite_positive(double value) { return std::isfinite(value) && value > 0.0; }

bool is_finite(double value) { return std::isfinite(value); }

}  // namespace

FirstOrderProcessModel::FirstOrderProcessModel(const std::string &id, double gain, double tau_s, double initial_output,
                                               const std::string &output_signal_path,
                                               const std::string &input_signal_path, SignalNamespace &ns,
                                               IntegrationMethod integration_method)
    : id_(id),
      output_signal_(ns.intern(output_signal_path)),
      input_signal_(ns.intern(input_signal_path)),
      gain_(gain),
      tau_s_(tau_s),
      output_(initial_output),
      initial_output_(initial_output),
      integration_method_(integration_method) {
    if (!is_finite(gain_)) {
        throw std::invalid_argument("FirstOrderProcessModel: gain must be finite");
    }
    if (!is_finite_positive(tau_s_)) {
        throw std::invalid_argument("FirstOrderProcessModel: tau_s must be finite and > 0");
    }
    if (!is_finite(initial_output_)) {
        throw std::invalid_argument("FirstOrderProcessModel: initial_output must be finite");
    }
}

double FirstOrderProcessModel::derivative(double y, double u) const { return (gain_ * u - y) / tau_s_; }

void FirstOrderProcessModel::tick(double dt, SignalStore &store) {
    const double u = store.read_value(input_signal_);

    if (integration_method_ == IntegrationMethod::ForwardEuler) {
        output_ += derivative(output_, u) * dt;
    } else {
        const double k1 = derivative(output_, u);
        const double k2 = derivative(output_ + 0.5 * dt * k1, u);
        const double k3 = derivative(output_ + 0.5 * dt * k2, u);
        const double k4 = derivative(output_ + dt * k3, u);
        output_ += (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4);
    }

    store.write(output_signal_, output_, "dimensionless");
    store.mark_physics_driven(output_signal_, true);
}

void FirstOrderProcessModel::reset() { output_ = initial_output_; }

double FirstOrderProcessModel::compute_stability_limit() const {
    // For dy/dt = -y/tau + ..., lambda = -1/tau.
    const double lambda_mag = 1.0 / tau_s_;
    const double limit = (integration_method_ == IntegrationMethod::Rk4) ? kRk4NegativeRealAxisStabilityLimit : 2.0;
    if (!(lambda_mag > 0.0)) {
        return std::numeric_limits<double>::infinity();
    }
    return limit / lambda_mag;
}

std::string FirstOrderProcessModel::describe() const {
    std::ostringstream oss;
    oss << "FirstOrderProcess(id=" << id_ << ", gain=" << gain_ << ", tau_s=" << tau_s_ << ", y0=" << initial_output_
        << ", method=" << to_string(integration_method_) << ")";
    return oss.str();
}

std::vector<SignalId> FirstOrderProcessModel::output_signal_ids() const { return {output_signal_}; }

}  // namespace fluxgraph

#include "fluxgraph/model/second_order_process.hpp"

#include <algorithm>
#include <cmath>
#include <complex>
#include <limits>
#include <sstream>
#include <stdexcept>

#include "stability_common.hpp"

namespace fluxgraph {

namespace {

bool is_finite_positive(double value) { return std::isfinite(value) && value > 0.0; }

bool is_finite_non_negative(double value) { return std::isfinite(value) && value >= 0.0; }

bool is_finite(double value) { return std::isfinite(value); }

}  // namespace

SecondOrderProcessModel::SecondOrderProcessModel(const std::string &id, double gain, double zeta, double omega_n_rad_s,
                                                 double initial_output, double initial_output_rate,
                                                 const std::string &output_signal_path,
                                                 const std::string &input_signal_path, SignalNamespace &ns,
                                                 IntegrationMethod integration_method)
    : id_(id),
      output_signal_(ns.intern(output_signal_path)),
      input_signal_(ns.intern(input_signal_path)),
      gain_(gain),
      zeta_(zeta),
      omega_n_rad_s_(omega_n_rad_s),
      y_(initial_output),
      y_dot_(initial_output_rate),
      initial_output_(initial_output),
      initial_output_rate_(initial_output_rate),
      integration_method_(integration_method) {
    if (!is_finite(gain_)) {
        throw std::invalid_argument("SecondOrderProcessModel: gain must be finite");
    }
    if (!is_finite_non_negative(zeta_)) {
        throw std::invalid_argument("SecondOrderProcessModel: zeta must be finite and >= 0");
    }
    if (!is_finite_positive(omega_n_rad_s_)) {
        throw std::invalid_argument("SecondOrderProcessModel: omega_n_rad_s must be finite and > 0");
    }
    if (!is_finite(initial_output_)) {
        throw std::invalid_argument("SecondOrderProcessModel: initial_output must be finite");
    }
    if (!is_finite(initial_output_rate_)) {
        throw std::invalid_argument("SecondOrderProcessModel: initial_output_rate must be finite");
    }
}

SecondOrderProcessModel::Derivative SecondOrderProcessModel::derivative(double y, double y_dot, double u) const {
    Derivative out;
    out.dy = y_dot;
    out.dy_dot = omega_n_rad_s_ * omega_n_rad_s_ * (gain_ * u - y) - 2.0 * zeta_ * omega_n_rad_s_ * y_dot;
    return out;
}

void SecondOrderProcessModel::tick(double dt, SignalStore &store) {
    const double u = store.read_value(input_signal_);

    if (integration_method_ == IntegrationMethod::ForwardEuler) {
        const auto k1 = derivative(y_, y_dot_, u);
        y_ += k1.dy * dt;
        y_dot_ += k1.dy_dot * dt;
    } else {
        const auto k1 = derivative(y_, y_dot_, u);
        const auto k2 = derivative(y_ + 0.5 * dt * k1.dy, y_dot_ + 0.5 * dt * k1.dy_dot, u);
        const auto k3 = derivative(y_ + 0.5 * dt * k2.dy, y_dot_ + 0.5 * dt * k2.dy_dot, u);
        const auto k4 = derivative(y_ + dt * k3.dy, y_dot_ + dt * k3.dy_dot, u);

        y_ += (dt / 6.0) * (k1.dy + 2.0 * k2.dy + 2.0 * k3.dy + k4.dy);
        y_dot_ += (dt / 6.0) * (k1.dy_dot + 2.0 * k2.dy_dot + 2.0 * k3.dy_dot + k4.dy_dot);
    }

    store.write(output_signal_, y_, "dimensionless");
    store.mark_physics_driven(output_signal_, true);
}

void SecondOrderProcessModel::reset() {
    y_ = initial_output_;
    y_dot_ = initial_output_rate_;
}

double SecondOrderProcessModel::compute_stability_limit() const {
    // For a linear system x' = A x + b u, stability of explicit methods depends
    // on z = lambda * dt for each eigenvalue lambda of A.
    const double trace = -2.0 * zeta_ * omega_n_rad_s_;
    const double det = omega_n_rad_s_ * omega_n_rad_s_;
    const std::complex<double> disc(trace * trace - 4.0 * det, 0.0);
    const std::complex<double> sqrt_disc = std::sqrt(disc);

    const std::complex<double> lambda1 = 0.5 * (trace + sqrt_disc);
    const std::complex<double> lambda2 = 0.5 * (trace - sqrt_disc);

    const double dt1 = (integration_method_ == IntegrationMethod::ForwardEuler)
                           ? detail::forward_euler_stability_limit(lambda1)
                           : detail::ray_stability_limit(integration_method_, lambda1);
    const double dt2 = (integration_method_ == IntegrationMethod::ForwardEuler)
                           ? detail::forward_euler_stability_limit(lambda2)
                           : detail::ray_stability_limit(integration_method_, lambda2);
    return std::min(dt1, dt2);
}

std::string SecondOrderProcessModel::describe() const {
    std::ostringstream oss;
    oss << "SecondOrderProcess(id=" << id_ << ", gain=" << gain_ << ", zeta=" << zeta_
        << ", omega_n_rad_s=" << omega_n_rad_s_ << ", y0=" << initial_output_ << ", ydot0=" << initial_output_rate_
        << ", method=" << to_string(integration_method_) << ")";
    return oss.str();
}

std::vector<SignalId> SecondOrderProcessModel::output_signal_ids() const { return {output_signal_}; }

}  // namespace fluxgraph

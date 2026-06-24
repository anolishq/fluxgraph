#include "fluxgraph/model/mass_spring_damper.hpp"

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

MassSpringDamperModel::MassSpringDamperModel(const std::string &id, double mass, double damping_coeff,
                                             double spring_constant, double initial_position, double initial_velocity,
                                             const std::string &position_signal_path,
                                             const std::string &velocity_signal_path,
                                             const std::string &force_signal_path, SignalNamespace &ns,
                                             IntegrationMethod integration_method)
    : id_(id),
      position_signal_(ns.intern(position_signal_path)),
      velocity_signal_(ns.intern(velocity_signal_path)),
      force_signal_(ns.intern(force_signal_path)),
      mass_(mass),
      damping_coeff_(damping_coeff),
      spring_constant_(spring_constant),
      x_(initial_position),
      v_(initial_velocity),
      initial_position_(initial_position),
      initial_velocity_(initial_velocity),
      integration_method_(integration_method) {
    if (!is_finite_positive(mass_)) {
        throw std::invalid_argument("MassSpringDamperModel: mass must be finite and > 0");
    }
    if (!is_finite_non_negative(damping_coeff_)) {
        throw std::invalid_argument("MassSpringDamperModel: damping_coeff must be finite and >= 0");
    }
    if (!is_finite_non_negative(spring_constant_)) {
        throw std::invalid_argument("MassSpringDamperModel: spring_constant must be finite and >= 0");
    }
    if (!is_finite(initial_position_)) {
        throw std::invalid_argument("MassSpringDamperModel: initial_position must be finite");
    }
    if (!is_finite(initial_velocity_)) {
        throw std::invalid_argument("MassSpringDamperModel: initial_velocity must be finite");
    }
}

MassSpringDamperModel::Derivative MassSpringDamperModel::derivative(double x, double v, double force) const {
    Derivative out;
    out.dx = v;
    out.dv = (force - damping_coeff_ * v - spring_constant_ * x) / mass_;
    return out;
}

void MassSpringDamperModel::tick(double dt, SignalStore &store) {
    const double force = store.read_value(force_signal_);

    if (integration_method_ == IntegrationMethod::ForwardEuler) {
        const auto k1 = derivative(x_, v_, force);
        x_ += k1.dx * dt;
        v_ += k1.dv * dt;
    } else {
        const auto k1 = derivative(x_, v_, force);
        const auto k2 = derivative(x_ + 0.5 * dt * k1.dx, v_ + 0.5 * dt * k1.dv, force);
        const auto k3 = derivative(x_ + 0.5 * dt * k2.dx, v_ + 0.5 * dt * k2.dv, force);
        const auto k4 = derivative(x_ + dt * k3.dx, v_ + dt * k3.dv, force);

        x_ += (dt / 6.0) * (k1.dx + 2.0 * k2.dx + 2.0 * k3.dx + k4.dx);
        v_ += (dt / 6.0) * (k1.dv + 2.0 * k2.dv + 2.0 * k3.dv + k4.dv);
    }

    store.write(position_signal_, x_, "m");
    store.write(velocity_signal_, v_, "m/s");
    store.mark_physics_driven(position_signal_, true);
    store.mark_physics_driven(velocity_signal_, true);
}

void MassSpringDamperModel::reset() {
    x_ = initial_position_;
    v_ = initial_velocity_;
}

double MassSpringDamperModel::compute_stability_limit() const {
    // Linear state-space:
    //   [x]' = [  0        1 ] [x] + [0] * F
    //   [v]    [ -k/m  -c/m ] [v]   [1/m]
    //
    // Stability of explicit methods depends on z = lambda * dt for each
    // eigenvalue lambda of A.
    const double trace = -damping_coeff_ / mass_;
    const double det = spring_constant_ / mass_;
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

std::string MassSpringDamperModel::describe() const {
    std::ostringstream oss;
    oss << "MassSpringDamper(id=" << id_ << ", mass=" << mass_ << " kg"
        << ", damping_coeff=" << damping_coeff_ << " N*s/m"
        << ", spring_constant=" << spring_constant_ << " N/m"
        << ", x0=" << initial_position_ << " m"
        << ", v0=" << initial_velocity_ << " m/s"
        << ", method=" << to_string(integration_method_) << ")";
    return oss.str();
}

std::vector<SignalId> MassSpringDamperModel::output_signal_ids() const { return {position_signal_, velocity_signal_}; }

}  // namespace fluxgraph

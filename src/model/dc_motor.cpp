#include "fluxgraph/model/dc_motor.hpp"

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

DcMotorModel::DcMotorModel(const std::string &id, double resistance_ohm, double inductance_h, double torque_constant,
                           double back_emf_constant, double inertia, double viscous_friction, double initial_current,
                           double initial_speed, const std::string &speed_signal_path,
                           const std::string &current_signal_path, const std::string &torque_signal_path,
                           const std::string &voltage_signal_path, const std::string &load_torque_signal_path,
                           SignalNamespace &ns, IntegrationMethod integration_method)
    : id_(id),
      speed_signal_(ns.intern(speed_signal_path)),
      current_signal_(ns.intern(current_signal_path)),
      torque_signal_(ns.intern(torque_signal_path)),
      voltage_signal_(ns.intern(voltage_signal_path)),
      load_torque_signal_(ns.intern(load_torque_signal_path)),
      resistance_ohm_(resistance_ohm),
      inductance_h_(inductance_h),
      torque_constant_(torque_constant),
      back_emf_constant_(back_emf_constant),
      inertia_(inertia),
      viscous_friction_(viscous_friction),
      i_(initial_current),
      omega_(initial_speed),
      initial_current_(initial_current),
      initial_speed_(initial_speed),
      integration_method_(integration_method) {
    if (!is_finite_positive(resistance_ohm_)) {
        throw std::invalid_argument("DcMotorModel: resistance_ohm must be finite and > 0");
    }
    if (!is_finite_positive(inductance_h_)) {
        throw std::invalid_argument("DcMotorModel: inductance_h must be finite and > 0");
    }
    if (!is_finite_positive(torque_constant_)) {
        throw std::invalid_argument("DcMotorModel: torque_constant must be finite and > 0");
    }
    if (!is_finite_positive(back_emf_constant_)) {
        throw std::invalid_argument("DcMotorModel: back_emf_constant must be finite and > 0");
    }
    if (!is_finite_positive(inertia_)) {
        throw std::invalid_argument("DcMotorModel: inertia must be finite and > 0");
    }
    if (!is_finite_non_negative(viscous_friction_)) {
        throw std::invalid_argument("DcMotorModel: viscous_friction must be finite and >= 0");
    }
    if (!is_finite(initial_current_)) {
        throw std::invalid_argument("DcMotorModel: initial_current must be finite");
    }
    if (!is_finite(initial_speed_)) {
        throw std::invalid_argument("DcMotorModel: initial_speed must be finite");
    }
}

DcMotorModel::Derivative DcMotorModel::derivative(double i, double omega, double voltage, double load_torque) const {
    Derivative out;
    out.di = (voltage - resistance_ohm_ * i - back_emf_constant_ * omega) / inductance_h_;
    out.domega = (torque_constant_ * i - viscous_friction_ * omega - load_torque) / inertia_;
    return out;
}

void DcMotorModel::tick(double dt, SignalStore &store) {
    const double voltage = store.read_value(voltage_signal_);
    const double load_torque = store.read_value(load_torque_signal_);

    if (integration_method_ == IntegrationMethod::ForwardEuler) {
        const auto k1 = derivative(i_, omega_, voltage, load_torque);
        i_ += k1.di * dt;
        omega_ += k1.domega * dt;
    } else {
        const auto k1 = derivative(i_, omega_, voltage, load_torque);
        const auto k2 = derivative(i_ + 0.5 * dt * k1.di, omega_ + 0.5 * dt * k1.domega, voltage, load_torque);
        const auto k3 = derivative(i_ + 0.5 * dt * k2.di, omega_ + 0.5 * dt * k2.domega, voltage, load_torque);
        const auto k4 = derivative(i_ + dt * k3.di, omega_ + dt * k3.domega, voltage, load_torque);

        i_ += (dt / 6.0) * (k1.di + 2.0 * k2.di + 2.0 * k3.di + k4.di);
        omega_ += (dt / 6.0) * (k1.domega + 2.0 * k2.domega + 2.0 * k3.domega + k4.domega);
    }

    const double torque = torque_constant_ * i_;

    store.write(speed_signal_, omega_, "rad/s");
    store.write(current_signal_, i_, "A");
    store.write(torque_signal_, torque, "N*m");
    store.mark_physics_driven(speed_signal_, true);
    store.mark_physics_driven(current_signal_, true);
    store.mark_physics_driven(torque_signal_, true);
}

void DcMotorModel::reset() {
    i_ = initial_current_;
    omega_ = initial_speed_;
}

double DcMotorModel::compute_stability_limit() const {
    // Linear state-space x' = A x + c, with x = [i, omega]^T.
    const double a11 = -resistance_ohm_ / inductance_h_;
    const double a12 = -back_emf_constant_ / inductance_h_;
    const double a21 = torque_constant_ / inertia_;
    const double a22 = -viscous_friction_ / inertia_;

    const double trace = a11 + a22;
    const double det = a11 * a22 - a12 * a21;
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

std::string DcMotorModel::describe() const {
    std::ostringstream oss;
    oss << "DcMotor(id=" << id_ << ", R=" << resistance_ohm_ << " Ohm"
        << ", L=" << inductance_h_ << " H"
        << ", Kt=" << torque_constant_ << " N*m/A"
        << ", Ke=" << back_emf_constant_ << " V*s/rad"
        << ", J=" << inertia_ << " kg*m^2"
        << ", b=" << viscous_friction_ << " N*m*s/rad"
        << ", i0=" << initial_current_ << " A"
        << ", omega0=" << initial_speed_ << " rad/s"
        << ", method=" << to_string(integration_method_) << ")";
    return oss.str();
}

std::vector<SignalId> DcMotorModel::output_signal_ids() const {
    return {speed_signal_, current_signal_, torque_signal_};
}

}  // namespace fluxgraph

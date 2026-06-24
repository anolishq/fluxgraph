#include "fluxgraph/model/thermal_rc2.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace fluxgraph {

namespace {

bool is_finite_positive(double value) { return std::isfinite(value) && value > 0.0; }

bool is_finite_non_negative(double value) { return std::isfinite(value) && value >= 0.0; }

}  // namespace

ThermalRc2Model::ThermalRc2Model(const std::string &id, double thermal_mass_a, double thermal_mass_b,
                                 double heat_transfer_coeff_a, double heat_transfer_coeff_b, double coupling_coeff,
                                 double initial_temp_a, double initial_temp_b, const std::string &temp_signal_a_path,
                                 const std::string &temp_signal_b_path, const std::string &power_signal_path,
                                 const std::string &ambient_signal_path, SignalNamespace &ns,
                                 ThermalIntegrationMethod integration_method)
    : id_(id),
      temp_a_signal_(ns.intern(temp_signal_a_path)),
      temp_b_signal_(ns.intern(temp_signal_b_path)),
      power_signal_(ns.intern(power_signal_path)),
      ambient_signal_(ns.intern(ambient_signal_path)),
      thermal_mass_a_(thermal_mass_a),
      thermal_mass_b_(thermal_mass_b),
      heat_transfer_coeff_a_(heat_transfer_coeff_a),
      heat_transfer_coeff_b_(heat_transfer_coeff_b),
      coupling_coeff_(coupling_coeff),
      temp_a_(initial_temp_a),
      temp_b_(initial_temp_b),
      initial_temp_a_(initial_temp_a),
      initial_temp_b_(initial_temp_b),
      integration_method_(integration_method) {
    if (!is_finite_positive(thermal_mass_a_)) {
        throw std::invalid_argument("ThermalRc2Model: thermal_mass_a must be finite and > 0");
    }
    if (!is_finite_positive(thermal_mass_b_)) {
        throw std::invalid_argument("ThermalRc2Model: thermal_mass_b must be finite and > 0");
    }
    if (!is_finite_positive(heat_transfer_coeff_a_)) {
        throw std::invalid_argument("ThermalRc2Model: heat_transfer_coeff_a must be finite and > 0");
    }
    if (!is_finite_positive(heat_transfer_coeff_b_)) {
        throw std::invalid_argument("ThermalRc2Model: heat_transfer_coeff_b must be finite and > 0");
    }
    if (!is_finite_non_negative(coupling_coeff_)) {
        throw std::invalid_argument("ThermalRc2Model: coupling_coeff must be finite and >= 0");
    }
    if (!std::isfinite(initial_temp_a_)) {
        throw std::invalid_argument("ThermalRc2Model: initial_temp_a must be finite");
    }
    if (!std::isfinite(initial_temp_b_)) {
        throw std::invalid_argument("ThermalRc2Model: initial_temp_b must be finite");
    }
}

ThermalRc2Model::Derivative ThermalRc2Model::derivative(double Ta, double Tb, double power, double ambient) const {
    Derivative out;

    const double heat_loss_a = heat_transfer_coeff_a_ * (Ta - ambient);
    const double heat_loss_b = heat_transfer_coeff_b_ * (Tb - ambient);
    const double coupling_flow = coupling_coeff_ * (Ta - Tb);

    out.dTa = (power - heat_loss_a - coupling_flow) / thermal_mass_a_;
    out.dTb = (-heat_loss_b + coupling_flow) / thermal_mass_b_;
    return out;
}

void ThermalRc2Model::tick(double dt, SignalStore &store) {
    const double power = store.read_value(power_signal_);
    const double ambient = store.read_value(ambient_signal_);

    if (integration_method_ == ThermalIntegrationMethod::ForwardEuler) {
        const auto k1 = derivative(temp_a_, temp_b_, power, ambient);
        temp_a_ += k1.dTa * dt;
        temp_b_ += k1.dTb * dt;
    } else {
        const auto k1 = derivative(temp_a_, temp_b_, power, ambient);
        const auto k2 = derivative(temp_a_ + 0.5 * dt * k1.dTa, temp_b_ + 0.5 * dt * k1.dTb, power, ambient);
        const auto k3 = derivative(temp_a_ + 0.5 * dt * k2.dTa, temp_b_ + 0.5 * dt * k2.dTb, power, ambient);
        const auto k4 = derivative(temp_a_ + dt * k3.dTa, temp_b_ + dt * k3.dTb, power, ambient);

        temp_a_ += (dt / 6.0) * (k1.dTa + 2.0 * k2.dTa + 2.0 * k3.dTa + k4.dTa);
        temp_b_ += (dt / 6.0) * (k1.dTb + 2.0 * k2.dTb + 2.0 * k3.dTb + k4.dTb);
    }

    store.write(temp_a_signal_, temp_a_, "degC");
    store.write(temp_b_signal_, temp_b_, "degC");
    store.mark_physics_driven(temp_a_signal_, true);
    store.mark_physics_driven(temp_b_signal_, true);
}

void ThermalRc2Model::reset() {
    temp_a_ = initial_temp_a_;
    temp_b_ = initial_temp_b_;
}

double ThermalRc2Model::compute_stability_limit() const {
    // Stability is determined by the eigenvalues of the linear system matrix A.
    // A = -C^{-1} * L, with L symmetric positive definite for h_a,h_b>0 and k>=0.
    const double a11 = -(heat_transfer_coeff_a_ + coupling_coeff_) / thermal_mass_a_;
    const double a22 = -(heat_transfer_coeff_b_ + coupling_coeff_) / thermal_mass_b_;
    const double a12 = coupling_coeff_ / thermal_mass_a_;
    const double a21 = coupling_coeff_ / thermal_mass_b_;

    const double trace = a11 + a22;
    const double det = a11 * a22 - a12 * a21;
    double disc = trace * trace - 4.0 * det;
    disc = std::max(0.0, disc);
    const double sqrt_disc = std::sqrt(disc);

    const double lambda1 = 0.5 * (trace + sqrt_disc);
    const double lambda2 = 0.5 * (trace - sqrt_disc);
    const double most_negative = std::min(lambda1, lambda2);

    if (!(most_negative < 0.0)) {
        return std::numeric_limits<double>::infinity();
    }

    const double limit =
        (integration_method_ == ThermalIntegrationMethod::Rk4) ? kRk4NegativeRealAxisStabilityLimit : 2.0;
    return limit / std::abs(most_negative);
}

std::string ThermalRc2Model::describe() const {
    std::ostringstream oss;
    oss << "ThermalRc2(id=" << id_ << ", Ca=" << thermal_mass_a_ << " J/K"
        << ", Cb=" << thermal_mass_b_ << " J/K"
        << ", ha=" << heat_transfer_coeff_a_ << " W/K"
        << ", hb=" << heat_transfer_coeff_b_ << " W/K"
        << ", k=" << coupling_coeff_ << " W/K"
        << ", Ta0=" << initial_temp_a_ << " degC"
        << ", Tb0=" << initial_temp_b_ << " degC"
        << ", method=" << to_string(integration_method_) << ")";
    return oss.str();
}

std::vector<SignalId> ThermalRc2Model::output_signal_ids() const { return {temp_a_signal_, temp_b_signal_}; }

}  // namespace fluxgraph

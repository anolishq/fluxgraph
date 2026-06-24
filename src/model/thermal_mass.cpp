#include "fluxgraph/model/thermal_mass.hpp"

#include <cmath>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace fluxgraph {

namespace {

bool is_finite_positive(double value) { return std::isfinite(value) && value > 0.0; }

}  // namespace

ThermalMassModel::ThermalMassModel(const std::string &id, double thermal_mass, double heat_transfer_coeff,
                                   double initial_temp, const std::string &temp_signal_path,
                                   const std::string &power_signal_path, const std::string &ambient_signal_path,
                                   SignalNamespace &ns, ThermalIntegrationMethod integration_method)
    : id_(id),
      temp_signal_(ns.intern(temp_signal_path)),
      power_signal_(ns.intern(power_signal_path)),
      ambient_signal_(ns.intern(ambient_signal_path)),
      thermal_mass_(thermal_mass),
      heat_transfer_coeff_(heat_transfer_coeff),
      temperature_(initial_temp),
      initial_temp_(initial_temp),
      integration_method_(integration_method) {
    if (!is_finite_positive(thermal_mass_)) {
        throw std::invalid_argument("ThermalMassModel: thermal_mass must be finite and > 0");
    }
    if (!is_finite_positive(heat_transfer_coeff_)) {
        throw std::invalid_argument("ThermalMassModel: heat_transfer_coeff must be finite and > 0");
    }
    if (!std::isfinite(initial_temp_)) {
        throw std::invalid_argument("ThermalMassModel: initial_temp must be finite");
    }
}

double ThermalMassModel::derivative(double temperature, double net_power, double ambient) const {
    const double heat_loss = heat_transfer_coeff_ * (temperature - ambient);
    return (net_power - heat_loss) / thermal_mass_;
}

void ThermalMassModel::tick(double dt, SignalStore &store) {
    // Read inputs
    double net_power = store.read_value(power_signal_);
    double ambient = store.read_value(ambient_signal_);

    if (integration_method_ == ThermalIntegrationMethod::ForwardEuler) {
        // Forward Euler integration: T += dT/dt * dt
        temperature_ += derivative(temperature_, net_power, ambient) * dt;
    } else {
        // Classic RK4 with fixed inputs over the tick interval.
        const double k1 = derivative(temperature_, net_power, ambient);
        const double k2 = derivative(temperature_ + 0.5 * dt * k1, net_power, ambient);
        const double k3 = derivative(temperature_ + 0.5 * dt * k2, net_power, ambient);
        const double k4 = derivative(temperature_ + dt * k3, net_power, ambient);
        temperature_ += (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4);
    }

    // Write output with unit
    store.write(temp_signal_, temperature_, "degC");
    store.mark_physics_driven(temp_signal_, true);
}

void ThermalMassModel::reset() { temperature_ = initial_temp_; }

double ThermalMassModel::compute_stability_limit() const {
    // Stability for dT/dt = -k*T with k = h/C.
    if (heat_transfer_coeff_ <= 0.0) {
        return std::numeric_limits<double>::infinity();  // No cooling =
                                                         // unconditionally stable
    }

    const double tau = thermal_mass_ / heat_transfer_coeff_;
    if (integration_method_ == ThermalIntegrationMethod::ForwardEuler) {
        return 2.0 * tau;
    }

    return kRk4NegativeRealAxisStabilityLimit * tau;
}

std::string ThermalMassModel::describe() const {
    std::ostringstream oss;
    oss << "ThermalMass(id=" << id_ << ", C=" << thermal_mass_ << " J/K"
        << ", h=" << heat_transfer_coeff_ << " W/K"
        << ", T0=" << initial_temp_ << " degC"
        << ", method=" << to_string(integration_method_) << ")";
    return oss.str();
}

std::vector<SignalId> ThermalMassModel::output_signal_ids() const { return {temp_signal_}; }

}  // namespace fluxgraph

#include "fluxgraph/model/thermal_mass.hpp"
#include <limits>
#include <sstream>

namespace fluxgraph {

ThermalMassModel::ThermalMassModel(const std::string &id, double thermal_mass,
                                   double heat_transfer_coeff,
                                   double initial_temp,
                                   const std::string &temp_signal_path,
                                   const std::string &power_signal_path,
                                   const std::string &ambient_signal_path,
                                   SignalNamespace &ns)
    : id_(id), temp_signal_(ns.intern(temp_signal_path)),
      power_signal_(ns.intern(power_signal_path)),
      ambient_signal_(ns.intern(ambient_signal_path)),
      thermal_mass_(thermal_mass), heat_transfer_coeff_(heat_transfer_coeff),
      temperature_(initial_temp), initial_temp_(initial_temp) {}

void ThermalMassModel::tick(double dt, SignalStore &store) {
  // Read inputs
  double net_power = store.read_value(power_signal_);
  double ambient = store.read_value(ambient_signal_);

  // Compute heat loss to ambient
  double heat_loss = heat_transfer_coeff_ * (temperature_ - ambient);

  // Forward Euler integration: T += dT/dt * dt
  double dT = (net_power - heat_loss) / thermal_mass_ * dt;
  temperature_ += dT;

  // Write output with unit
  store.write(temp_signal_, temperature_, "degC");
  store.mark_physics_driven(temp_signal_, true);
}

void ThermalMassModel::reset() { temperature_ = initial_temp_; }

double ThermalMassModel::compute_stability_limit() const {
  // Forward Euler stability for dT/dt = -k*T: dt < 2/k
  // For this model: k = h/C
  // Therefore: dt < 2*C/h
  if (heat_transfer_coeff_ <= 0.0) {
    return std::numeric_limits<double>::infinity(); // No cooling =
                                                    // unconditionally stable
  }
  return 2.0 * thermal_mass_ / heat_transfer_coeff_;
}

std::string ThermalMassModel::describe() const {
  std::ostringstream oss;
  oss << "ThermalMass(id=" << id_ << ", C=" << thermal_mass_ << " J/K"
      << ", h=" << heat_transfer_coeff_ << " W/K"
      << ", T0=" << initial_temp_ << " degC)";
  return oss.str();
}

std::vector<SignalId> ThermalMassModel::output_signal_ids() const {
  return {temp_signal_};
}

} // namespace fluxgraph

#pragma once

#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/model/interface.hpp"
#include <string>
#include <vector>

namespace fluxgraph {

/// Thermal mass model: simple heat capacity with power input and ambient
/// cooling Physics: dT/dt = (P_in - h*(T - T_amb)) / C Where:
///   T = temperature (degC)
///   P_in = net heating power (W)
///   h = heat transfer coefficient (W/K)
///   T_amb = ambient temperature (degC)
///   C = thermal mass (J/K)
class ThermalMassModel : public IModel {
public:
  /// Construct thermal mass model
  /// @param id Model identifier
  /// @param thermal_mass Heat capacity in J/K
  /// @param heat_transfer_coeff Heat transfer coefficient in W/K
  /// @param initial_temp Initial temperature in degC
  /// @param temp_signal_path Signal path for temperature output (e.g.,
  /// "chamber_air/temperature")
  /// @param power_signal_path Signal path for power input (e.g.,
  /// "chamber_air/heating_power")
  /// @param ambient_signal_path Signal path for ambient temperature (e.g.,
  /// "chamber_air/ambient_temp")
  /// @param ns Signal namespace for path interning
  ThermalMassModel(const std::string &id, double thermal_mass,
                   double heat_transfer_coeff, double initial_temp,
                   const std::string &temp_signal_path,
                   const std::string &power_signal_path,
                   const std::string &ambient_signal_path, SignalNamespace &ns);

  void tick(double dt, SignalStore &store) override;
  void reset() override;

  /// Stability limit for Forward Euler: dt < 2*C/h
  double compute_stability_limit() const override;

  std::string describe() const override;
  std::vector<SignalId> output_signal_ids() const override;

private:
  std::string id_;
  SignalId temp_signal_;
  SignalId power_signal_;
  SignalId ambient_signal_;
  double thermal_mass_;        // C (J/K)
  double heat_transfer_coeff_; // h (W/K)
  double temperature_;         // Current temp (degC)
  double initial_temp_;        // Initial temp for reset (degC)
};

} // namespace fluxgraph

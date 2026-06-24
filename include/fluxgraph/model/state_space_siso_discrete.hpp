#pragma once

#include <cstddef>
#include <string>
#include <vector>

#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/model/interface.hpp"

namespace fluxgraph {

/// Discrete-time SISO state-space model.
///
/// Dynamics:
///   x[k+1] = A_d x[k] + B_d u[k]
///   y[k]   = C x[k] + D u[k]
///
/// Signal contracts:
/// - input_signal: user-defined scalar unit (strict mode requires declaration)
/// - output_signal: user-defined scalar unit (strict mode requires declaration)
class StateSpaceSisoDiscreteModel : public IModel {
public:
    StateSpaceSisoDiscreteModel(const std::string &id, std::vector<std::vector<double>> a_d, std::vector<double> b_d,
                                std::vector<double> c, double d, std::vector<double> x0,
                                const std::string &output_signal_path, const std::string &input_signal_path,
                                SignalNamespace &ns);

    void tick(double dt, SignalStore &store) override;
    void reset() override;
    double compute_stability_limit() const override;
    std::string describe() const override;
    std::vector<SignalId> output_signal_ids() const override;

private:
    static bool is_finite(double value);
    static std::vector<double> flatten_square_matrix(const std::vector<std::vector<double>> &matrix);

    std::string id_;
    SignalId output_signal_ = INVALID_SIGNAL;
    SignalId input_signal_ = INVALID_SIGNAL;
    std::size_t state_dim_ = 0;

    std::vector<double> a_d_;  // row-major n x n
    std::vector<double> b_d_;  // n
    std::vector<double> c_;    // n
    double d_ = 0.0;

    std::vector<double> state_;
    std::vector<double> initial_state_;
    std::vector<double> scratch_state_;
};

}  // namespace fluxgraph

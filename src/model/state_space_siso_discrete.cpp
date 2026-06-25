#include "fluxgraph/model/state_space_siso_discrete.hpp"

#include <cmath>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace fluxgraph {

bool StateSpaceSisoDiscreteModel::is_finite(const double value) { return std::isfinite(value); }

std::vector<double> StateSpaceSisoDiscreteModel::flatten_square_matrix(const std::vector<std::vector<double>> &matrix) {
    const std::size_t n = matrix.size();
    std::vector<double> flat;
    flat.reserve(n * n);

    for (std::size_t i = 0; i < n; ++i) {
        const auto &row = matrix[i];
        if (row.size() != n) {
            throw std::invalid_argument("StateSpaceSisoDiscreteModel: A_d must be square");
        }
        for (double value : row) {
            flat.push_back(value);
        }
    }

    return flat;
}

StateSpaceSisoDiscreteModel::StateSpaceSisoDiscreteModel(const std::string &id,
                                                         const std::vector<std::vector<double>> &a_d,
                                                         std::vector<double> b_d, std::vector<double> c, double d,
                                                         std::vector<double> x0, const std::string &output_signal_path,
                                                         const std::string &input_signal_path, SignalNamespace &ns)
    : id_(id),
      output_signal_(ns.intern(output_signal_path)),
      input_signal_(ns.intern(input_signal_path)),
      state_dim_(a_d.size()),
      a_d_(flatten_square_matrix(a_d)),
      b_d_(std::move(b_d)),
      c_(std::move(c)),
      d_(d),
      state_(std::move(x0)),
      initial_state_(state_),
      scratch_state_(state_dim_, 0.0) {
    if (state_dim_ == 0) {
        throw std::invalid_argument("StateSpaceSisoDiscreteModel: A_d must be non-empty");
    }

    if (b_d_.size() != state_dim_) {
        throw std::invalid_argument("StateSpaceSisoDiscreteModel: B_d size must match A_d dimension");
    }
    if (c_.size() != state_dim_) {
        throw std::invalid_argument("StateSpaceSisoDiscreteModel: C size must match A_d dimension");
    }
    if (state_.size() != state_dim_) {
        throw std::invalid_argument("StateSpaceSisoDiscreteModel: x0 size must match A_d dimension");
    }

    for (double value : a_d_) {
        if (!is_finite(value)) {
            throw std::invalid_argument("StateSpaceSisoDiscreteModel: A_d must contain finite values");
        }
    }
    for (double value : b_d_) {
        if (!is_finite(value)) {
            throw std::invalid_argument("StateSpaceSisoDiscreteModel: B_d must contain finite values");
        }
    }
    for (double value : c_) {
        if (!is_finite(value)) {
            throw std::invalid_argument("StateSpaceSisoDiscreteModel: C must contain finite values");
        }
    }
    if (!is_finite(d_)) {
        throw std::invalid_argument("StateSpaceSisoDiscreteModel: D must be finite");
    }
    for (double value : state_) {
        if (!is_finite(value)) {
            throw std::invalid_argument("StateSpaceSisoDiscreteModel: x0 must contain finite values");
        }
    }
}

void StateSpaceSisoDiscreteModel::tick(double /*dt*/, SignalStore &store) {
    const double input = store.read_value(input_signal_);

    double output = d_ * input;
    for (std::size_t i = 0; i < state_dim_; ++i) {
        output += c_[i] * state_[i];
    }
    store.write_with_contract_unit(output_signal_, output);
    store.mark_physics_driven(output_signal_, true);

    for (std::size_t i = 0; i < state_dim_; ++i) {
        double acc = b_d_[i] * input;
        const std::size_t row_base = i * state_dim_;
        for (std::size_t j = 0; j < state_dim_; ++j) {
            acc += a_d_[row_base + j] * state_[j];
        }
        scratch_state_[i] = acc;
    }
    state_.swap(scratch_state_);
}

void StateSpaceSisoDiscreteModel::reset() { state_ = initial_state_; }

double StateSpaceSisoDiscreteModel::compute_stability_limit() const { return std::numeric_limits<double>::infinity(); }

std::string StateSpaceSisoDiscreteModel::describe() const {
    std::ostringstream oss;
    oss << "StateSpaceSisoDiscrete(id=" << id_ << ", n=" << state_dim_ << ")";
    return oss.str();
}

std::vector<SignalId> StateSpaceSisoDiscreteModel::output_signal_ids() const { return {output_signal_}; }

}  // namespace fluxgraph

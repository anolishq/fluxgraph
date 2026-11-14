#pragma once

// A model (rule 4.9): a state, a rule that steps it over one period given its inputs, and a rule that gives its
// outputs from its state and inputs. Both rules are linear (rule 7.8.7). A model is not a block: a model block
// hosts one (section 7.8), and an estimator hosts one as its predictor (section 7.9).

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

#include "blocks.hpp"

namespace fluxgraph::v2::detail {

struct Model {
    std::size_t states = 0;
    std::size_t inputs = 0;
    std::size_t outputs = 0;
    std::vector<std::string> state_names;  // in the order of A's rows
    std::vector<std::string> input_names;  // in the order of B's columns
    std::vector<std::string> output_names;

    // The step over one period, x' = Ad x + Bd u, and the outputs, y = C x + D u. Each matrix is by rows. `ad`
    // is also the sensitivity of the stepped state to the state it was stepped from (rule 4.9).
    std::vector<double> ad;  // states by states
    std::vector<double> bd;  // states by inputs
    std::vector<double> c;   // outputs by states
    std::vector<double> d;   // outputs by inputs
    std::vector<double> initial;

    /// For each input, whether any output reads it: whether its column of D is not all zero (rule 7.8.2).
    std::vector<bool> direct;

    /// In continuous time, with `a` its matrix, per second and by rows. An estimator's process noise is worked
    /// from it (rule 7.9.2). Not so for `state_space`, which gives Ad and Bd themselves.
    bool continuous = false;
    std::vector<double> a;

    /// A named model whose state decays has a `settle` of its own unless one is given (rule 7.8.6).
    bool has_settle = false;
    std::uint64_t settle = 0;  // in ticks

    /// next = Ad x + Bd u. `next` is not `x`.
    void step(const double *x, const double *u, double *next) const;
    /// y = C x + D u.
    void give(const double *x, const double *u, double *y) const;
};

/// Whether `type` is the type of a model.
bool is_model_type(std::string_view type);

/// Builds the model of `type` from its own settings, read from `settings`, at the reader's period. The step is
/// worked here, once (rule 7.8.7). A fault is left with the reader, and the model is then not to be used.
void build_model(std::string_view type, SettingsReader &settings, Model &model);

}  // namespace fluxgraph::v2::detail

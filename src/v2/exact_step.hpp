#pragma once

// The exact step of a linear model in continuous time (rule 7.8.7): the exponential of its matrix over one period,
// and the integral of that exponential.

#include <cstddef>
#include <vector>

#include "fluxgraph/v2/value.hpp"

namespace fluxgraph::v2::detail {

/// The largest sum of the absolute values along a row of `a`, an n by n matrix by rows, times the period in
/// seconds: the number rule 7.8.7 bounds at 100,000. In double arithmetic, as the rule says.
double stiffness(const std::vector<double> &a, std::size_t n, Time period);

/// For dx/dt = A x + B u with u held: `ad` = exp(A * period), n by n, and `bd` = (the integral of exp(A s) for s
/// from zero to the period) * B, n by m. `a` is per second and by rows, as are `b` and the results. `B` is kept
/// out of the exponential, so the accuracy of `bd` does not depend on its size. An entry that is more than a
/// double holds comes back not finite.
///
/// Worked in arithmetic of twice a double's digits and rounded once at the end, so that what is promised to one
/// part in 10^9 is kept with room to spare up to the bound on stiffness and past it.
void exact_step(const std::vector<double> &a, std::size_t n, const std::vector<double> &b, std::size_t m, Time period,
                std::vector<double> &ad, std::vector<double> &bd);

/// What process noise has added by the end of one period (rule 7.9.2): the integral of exp(A s) Q exp(A' s) for s
/// from zero to the period, n by n, where Q has `q`, a variance per second for each state, on its diagonal and
/// nothing off it. Worked as exact_step() works its matrices, and on the same terms.
void exact_noise(const std::vector<double> &a, std::size_t n, const std::vector<double> &q, Time period,
                 std::vector<double> &noise);

}  // namespace fluxgraph::v2::detail

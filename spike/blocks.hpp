#pragma once

// Spike: the ten signal blocks written against FluxGraph's public interface
// as it stands. See README.md and FRICTION.md. Not part of the library.

#include <map>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include "fluxgraph/core/namespace.hpp"
#include "fluxgraph/core/signal_store.hpp"
#include "fluxgraph/graph/spec.hpp"
#include "fluxgraph/model/interface.hpp"

namespace spike {

// The state of a value on a wire. NOT_READY is 0 on purpose: a signal nobody
// has written reads as 0.0 from the store (FRICTION 2).
enum State : int { NOT_READY = 0, GOOD = 1, BAD = 2 };

struct Val {
    int state = NOT_READY;
    double v = 0.0;
};

inline Val good(double v) { return {GOOD, v}; }

// A wire is two FluxGraph signals, one for the value and one for its state,
// because a FluxGraph signal is a single double (FRICTION 1).
struct Wire {
    fluxgraph::SignalId value = fluxgraph::INVALID_SIGNAL;
    fluxgraph::SignalId state = fluxgraph::INVALID_SIGNAL;
    bool literal = false;
    double number = 0.0;
};

std::string state_path(const std::string &wire);

using Values = std::map<std::string, Val>;

/// A block: named inputs, named outputs, settings, and a step per tick.
/// It is a FluxGraph model because only a model can read several signals.
class Block : public fluxgraph::IModel {
public:
    Block(const fluxgraph::ModelSpec &spec, fluxgraph::SignalNamespace &ns, std::vector<std::string> outputs);

    void tick(double dt, fluxgraph::SignalStore &store) final;
    void reset() override {}
    double compute_stability_limit() const override;
    std::string describe() const override { return id_; }
    std::vector<fluxgraph::SignalId> output_signal_ids() const override;

protected:
    /// t is the time of this tick, counted from 0 at the first one.
    virtual void step(double t, double dt, const Values &in, Values &out) = 0;

    double number(const std::string &key) const;
    std::optional<double> optional_number(const std::string &key) const;
    const std::string &text(const std::string &key) const;

    std::string id_;

private:
    std::map<std::string, Wire> in_;
    std::vector<std::pair<std::string, Wire>> out_;
    std::map<std::string, std::string> settings_;
    std::optional<double> fallback_;
    long ticks_ = 0;
};

/// Register the ten block types with GraphCompiler as "blk_<type>". Once per process.
void register_blocks();

}  // namespace spike

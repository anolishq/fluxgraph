#include "blocks.hpp"

#include <algorithm>
#include <cmath>
#include <deque>
#include <functional>
#include <limits>
#include <memory>
#include <stdexcept>

#include "fluxgraph/graph/compiler.hpp"
#include "fluxgraph/graph/param_utils.hpp"

namespace spike {

using fluxgraph::ModelSpec;
using fluxgraph::SignalNamespace;
using fluxgraph::SignalStore;

std::string state_path(const std::string &wire) { return wire + "#state"; }

namespace {

bool starts_with(const std::string &s, const std::string &prefix) { return s.rfind(prefix, 0) == 0; }

int worst(std::initializer_list<Val> vals) {
    int state = GOOD;
    for (const Val &v : vals) {
        if (v.state == BAD) return BAD;
        if (v.state == NOT_READY) state = NOT_READY;
    }
    return state;
}

Val binary(Val a, Val b, const std::function<double(double, double)> &fn) {
    const int state = worst({a, b});
    return state == GOOD ? good(fn(a.v, b.v)) : Val{state, 0.0};
}

Val sub(Val a, Val b) {
    return binary(a, b, [](double x, double y) { return x - y; });
}
Val add(Val a, Val b) {
    return binary(a, b, [](double x, double y) { return x + y; });
}
Val mul(Val a, Val b) {
    return binary(a, b, [](double x, double y) { return x * y; });
}
Val divide(Val a, Val b) {
    if (worst({a, b}) == GOOD && b.v == 0.0) return {BAD, 0.0};
    return binary(a, b, [](double x, double y) { return x / y; });
}
Val less(Val a, Val b) {
    return binary(a, b, [](double x, double y) { return x < y ? 1.0 : 0.0; });
}
Val greater(Val a, Val b) {
    return binary(a, b, [](double x, double y) { return x > y ? 1.0 : 0.0; });
}
Val absolute(Val a) { return a.state == GOOD ? good(std::fabs(a.v)) : a; }

// Three-valued: one true operand decides an "or", one false operand an "and".
Val logic(const std::vector<Val> &vals, bool decides) {
    int state = GOOD;
    for (const Val &v : vals) {
        if (v.state == GOOD && (v.v != 0.0) == decides) return good(decides ? 1.0 : 0.0);
        if (v.state == BAD) state = BAD;
        if (v.state == NOT_READY && state != BAD) state = NOT_READY;
    }
    return state == GOOD ? good(decides ? 0.0 : 1.0) : Val{state, 0.0};
}

Val when(Val condition, Val a, Val b) {
    if (condition.state != GOOD) return {condition.state, 0.0};
    return condition.v != 0.0 ? a : b;
}

// An expression parser has nothing to do with FluxGraph's design, so each
// formula in the vectors is a function here, keyed by its text.
const std::map<std::string, std::function<Val(const Values &)>> &formulas() {
    static const std::map<std::string, std::function<Val(const Values &)>> table = {
        {"t1 - bias", [](const Values &in) { return sub(in.at("t1"), in.at("bias")); }},
        {"pad - liquid", [](const Values &in) { return sub(in.at("pad"), in.at("liquid")); }},
        {"room + (pad - room) / (1 + k)",
         [](const Values &in) {
             return add(in.at("room"), divide(sub(in.at("pad"), in.at("room")), add(good(1.0), in.at("k"))));
         }},
        {"target + k * (target - room)",
         [](const Values &in) { return add(in.at("target"), mul(in.at("k"), sub(in.at("target"), in.at("room")))); }},
        {"t2 > 70", [](const Values &in) { return greater(in.at("t2"), good(70.0)); }},
        {"t1 > 45", [](const Values &in) { return greater(in.at("t1"), good(45.0)); }},
        {"seen and t2 < t1 - 3",
         [](const Values &in) {
             return logic({in.at("seen"), less(in.at("t2"), sub(in.at("t1"), good(3.0)))}, false);
         }},
        {"a or b or c or d",
         [](const Values &in) { return logic({in.at("a"), in.at("b"), in.at("c"), in.at("d")}, true); }},
        {"abs(slope) < 0.002 and spread < 0.02",
         [](const Values &in) {
             return logic({less(absolute(in.at("slope")), good(0.002)), less(in.at("spread"), good(0.02))}, false);
         }},
        {"duty * watts", [](const Values &in) { return mul(in.at("duty"), in.at("watts")); }},
        {"a / b", [](const Values &in) { return divide(in.at("a"), in.at("b")); }},
        {"when(relay, watts, 0)", [](const Values &in) { return when(in.at("relay"), in.at("watts"), good(0.0)); }},
    };
    return table;
}

}  // namespace

// ---------------------------------------------------------------- Block

Block::Block(const ModelSpec &spec, SignalNamespace &ns, std::vector<std::string> outputs) : id_(spec.id) {
    for (const auto &[key, value] : spec.params) {
        const std::string text = fluxgraph::param::as_string(value, "model[" + spec.id + "]/" + key);
        if (starts_with(key, "in.")) {
            Wire wire;
            if (starts_with(text, "num:")) {
                wire.literal = true;
                wire.number = std::stod(text.substr(4));
            } else {
                const std::string path = text.substr(4);  // after "sig:"
                wire.value = ns.intern(path);
                wire.state = ns.intern(state_path(path));
            }
            in_.emplace(key.substr(3), wire);
        } else if (starts_with(key, "p.")) {
            settings_.emplace(key.substr(2), text);
        } else if (key == "fallback") {
            fallback_ = std::stod(text.substr(4));
        }
    }
    for (const std::string &port : outputs) {
        const std::string path = spec.id + "." + port;
        out_.push_back({port, Wire{ns.intern(path), ns.intern(state_path(path)), false, 0.0}});
    }
}

void Block::tick(double dt, SignalStore &store) {
    Values in;
    for (const auto &[name, wire] : in_) {
        in[name] = wire.literal ? good(wire.number)
                                : Val{static_cast<int>(store.read_value(wire.state)), store.read_value(wire.value)};
    }
    Values out;
    step(static_cast<double>(ticks_) * dt, dt, in, out);
    ++ticks_;
    for (const auto &[port, wire] : out_) {
        Val val = out.count(port) != 0 ? out.at(port) : Val{};
        if (val.state != GOOD && fallback_.has_value()) val = good(*fallback_);
        store.write(wire.value, val.state == GOOD ? val.v : 0.0);
        store.write(wire.state, static_cast<double>(val.state));
    }
}

double Block::compute_stability_limit() const { return std::numeric_limits<double>::infinity(); }

std::vector<fluxgraph::SignalId> Block::output_signal_ids() const {
    std::vector<fluxgraph::SignalId> ids;
    for (const auto &[port, wire] : out_) {
        ids.push_back(wire.value);
        ids.push_back(wire.state);
    }
    return ids;
}

double Block::number(const std::string &key) const { return std::stod(settings_.at(key)); }

std::optional<double> Block::optional_number(const std::string &key) const {
    const auto it = settings_.find(key);
    return it == settings_.end() ? std::nullopt : std::optional<double>(std::stod(it->second));
}

const std::string &Block::text(const std::string &key) const { return settings_.at(key); }

// ---------------------------------------------------------------- the ten blocks

namespace {

class Median : public Block {
public:
    Median(const ModelSpec &s, SignalNamespace &ns) : Block(s, ns, {"y"}), n_(static_cast<size_t>(number("samples"))) {}

protected:
    void step(double, double, const Values &in, Values &out) override {
        const Val &x = in.at("x");
        if (x.state == GOOD) {
            buf_.push_back(x.v);
            if (buf_.size() > n_) buf_.pop_front();
        }
        if (buf_.size() < n_) return;
        std::vector<double> sorted(buf_.begin(), buf_.end());
        std::sort(sorted.begin(), sorted.end());
        const size_t mid = sorted.size() / 2;
        out["y"] = good(sorted.size() % 2 == 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2.0);
    }

private:
    size_t n_;
    std::deque<double> buf_;
};

class Expr : public Block {
public:
    Expr(const ModelSpec &s, SignalNamespace &ns) : Block(s, ns, {"y"}) {
        const auto it = formulas().find(text("formula"));
        if (it == formulas().end())
            throw std::runtime_error("spike: no function for formula '" + text("formula") + "'");
        fn_ = it->second;
    }

protected:
    void step(double, double, const Values &in, Values &out) override { out["y"] = fn_(in); }

private:
    std::function<Val(const Values &)> fn_;
};

class AllGood : public Block {
public:
    AllGood(const ModelSpec &s, SignalNamespace &ns) : Block(s, ns, {"y"}) {}

protected:
    void step(double, double, const Values &in, Values &out) override {
        bool all = true;
        for (const auto &[name, v] : in) all = all && v.state == GOOD;
        out["y"] = good(all ? 1.0 : 0.0);
    }
};

class SinceTrue : public Block {
public:
    SinceTrue(const ModelSpec &s, SignalNamespace &ns) : Block(s, ns, {"y"}), limit_(number("longer_than_s")) {}

protected:
    void step(double t, double, const Values &in, Values &out) override {
        const Val &x = in.at("x");
        if (!last_.has_value() || (x.state == GOOD && x.v != 0.0)) last_ = t;
        out["y"] = good(t - *last_ > limit_ ? 1.0 : 0.0);
    }

private:
    double limit_;
    std::optional<double> last_;
};

class Latch : public Block {
public:
    Latch(const ModelSpec &s, SignalNamespace &ns) : Block(s, ns, {"y"}) {}

protected:
    void step(double, double, const Values &in, Values &out) override {
        const Val &set = in.at("set");
        on_ = on_ || (set.state == GOOD && set.v != 0.0);
        out["y"] = good(on_ ? 1.0 : 0.0);
    }

private:
    bool on_ = false;
};

class HeldFor : public Block {
public:
    HeldFor(const ModelSpec &s, SignalNamespace &ns)
        : Block(s, ns, {"y"}), seconds_(number("seconds")), reset_(text("on_bad") == "reset") {}

protected:
    void step(double t, double, const Values &in, Values &out) override {
        const Val &x = in.at("x");
        if (x.state == GOOD) {
            if (x.v != 0.0) {
                if (!since_.has_value()) since_ = t;
            } else {
                since_.reset();
            }
            out["y"] = good(since_.has_value() && t - *since_ > seconds_ ? 1.0 : 0.0);
            return;
        }
        if (reset_ || !since_.has_value()) {
            since_.reset();
            out["y"] = Val{x.state, 0.0};
            return;
        }
        out["y"] = good(t - *since_ > seconds_ ? 1.0 : 0.0);
    }

private:
    double seconds_;
    bool reset_;
    std::optional<double> since_;
};

class WindowStats : public Block {
public:
    WindowStats(const ModelSpec &s, SignalNamespace &ns)
        : Block(s, ns, {"mean", "slope_per_min", "spread"}),
          window_(number("window")),
          reset_(text("on_bad") == "reset") {}

protected:
    void step(double t, double dt, const Values &in, Values &out) override {
        // The period is not known when a model is built, only at its first tick (FRICTION 5).
        if (n_ == 0) n_ = static_cast<size_t>(std::llround(window_ / dt));
        const Val &x = in.at("x");
        if (x.state == GOOD) {
            buf_.push_back({t, x.v});
            if (buf_.size() > n_) buf_.pop_front();
        } else if (reset_) {
            buf_.clear();
        }
        if (buf_.size() < n_) return;
        const double count = static_cast<double>(buf_.size());
        double sum = 0.0;
        double lo = buf_.front().second;
        double hi = lo;
        for (const auto &[ti, y] : buf_) {
            sum += y;
            lo = std::min(lo, y);
            hi = std::max(hi, y);
        }
        const double my = sum / count;
        out["mean"] = good(my);
        out["spread"] = good(hi - lo);
        const double t0 = buf_.front().first;
        double sx = 0.0;
        for (const auto &[ti, y] : buf_) sx += (ti - t0) / 60.0;
        const double mx = sx / count;
        double den = 0.0;
        for (const auto &[ti, y] : buf_) den += ((ti - t0) / 60.0 - mx) * ((ti - t0) / 60.0 - mx);
        double num = 0.0;
        for (const auto &[ti, y] : buf_) num += ((ti - t0) / 60.0 - mx) * (y - my);
        out["slope_per_min"] = good(num / den);
    }

private:
    double window_;
    bool reset_;
    size_t n_ = 0;
    std::deque<std::pair<double, double>> buf_;
};

class Deadband : public Block {
public:
    Deadband(const ModelSpec &s, SignalNamespace &ns) : Block(s, ns, {"y"}), step_(number("step")) {}

protected:
    void step(double, double, const Values &in, Values &out) override {
        const Val &x = in.at("x");
        if (x.state != GOOD) {
            out["y"] = Val{x.state, 0.0};
            return;
        }
        if (!last_.has_value() || std::fabs(x.v - *last_) >= step_) last_ = x.v;
        out["y"] = good(*last_);
    }

private:
    double step_;
    std::optional<double> last_;
};

class Kalman1 : public Block {
public:
    Kalman1(const ModelSpec &s, SignalNamespace &ns)
        : Block(s, ns, {"x", "sigma"}),
          tau_(number("tau_s")),
          q_(number("q")),
          r_(number("r")),
          var_(optional_number("p0").value_or(4.0)) {}

protected:
    void step(double, double dt, const Values &in, Values &out) override {
        const Val &z = in.at("z");
        const Val &steady = in.at("steady");
        if (!x_.has_value()) {
            if (z.state != GOOD) return;
            x_ = z.v;
            var_ = r_;
        } else {
            if (steady.state == GOOD) {
                const double a = 1.0 - dt / tau_;
                x_ = a * *x_ + (1 - a) * steady.v;
                var_ = a * a * var_ + q_ * dt;
            } else {
                var_ += q_ * dt;
            }
            if (z.state == GOOD) {
                const double k = var_ / (var_ + r_);
                x_ = *x_ + k * (z.v - *x_);
                var_ *= 1 - k;
            }
        }
        out["x"] = good(*x_);
        out["sigma"] = good(std::sqrt(var_));
    }

private:
    double tau_, q_, r_, var_;
    std::optional<double> x_;
};

class Integrate : public Block {
public:
    Integrate(const ModelSpec &s, SignalNamespace &ns) : Block(s, ns, {"y"}), per_(number("per")) {}

protected:
    void step(double, double dt, const Values &in, Values &out) override {
        const Val &x = in.at("x");
        if (x.state == GOOD) total_ += x.v * dt / per_;
        out["y"] = good(total_);
    }

private:
    double per_;
    double total_ = 0.0;
};

template <typename T>
void add_type(const std::string &type) {
    fluxgraph::GraphCompiler::register_model_factory(
        "blk_" + type, [](const ModelSpec &spec, SignalNamespace &ns) -> std::unique_ptr<fluxgraph::IModel> {
            return std::make_unique<T>(spec, ns);
        });
}

}  // namespace

void register_blocks() {
    add_type<Median>("median");
    add_type<Expr>("expr");
    add_type<AllGood>("all_good");
    add_type<SinceTrue>("since_true");
    add_type<Latch>("latch");
    add_type<HeldFor>("held_for");
    add_type<WindowStats>("window_stats");
    add_type<Deadband>("deadband");
    add_type<Kalman1>("kalman1");
    add_type<Integrate>("integrate");
}

}  // namespace spike

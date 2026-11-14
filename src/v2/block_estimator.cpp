// `estimator` (section 7.9): a Kalman filter over a linear model, which it hosts as its predictor.

#include <algorithm>
#include <cmath>
#include <format>
#include <optional>

#include "blocks.hpp"
#include "exact.hpp"
#include "exact_step.hpp"
#include "model.hpp"

namespace fluxgraph::v2::detail {

namespace {

using Kind = Setting::Kind;

constexpr std::int64_t kMaxCount = 2'147'483'647;  // Appendix A: the width of `over` and `max_refused`

// Predictions for the ticks a gap passed over are made one by one up to this many, as ticks that were run would
// have made them. Past it the same result is reached by doubling, to within rounding (rule 7.9.9).
constexpr std::uint64_t kStepsOneByOne = 64;

// One measurement port, as the graph configures it.
struct Port {
    std::string name;
    std::size_t output = 0;  // the model output it is of
    double r = 0.0;
    bool takes_uncertain = false;
    double r_uncertain = 0.0;
};

// What is remembered of one port.
struct PortMemory {
    bool considered = false;  // the sample time last considered on it (rule 7.9.3)
    Time considered_at = 0;
    bool used = false;  // the sample time of the measurement last used (rule 7.9.8)
    Time used_at = 0;
    std::uint64_t refused = 0;  // how many have been refused
    std::uint64_t run = 0;      // how many in a row, of those considered (rule 7.9.5)
    std::uint64_t kept = 0;     // how many of the last `over` normalised innovations squared it holds
    std::size_t oldest = 0;
};

class EstimatorBlock : public Block {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        read_model(setup, settings);
        if (!settings.failed()) {
            read_noise(settings);
        }
        if (!settings.failed()) {
            read_ports(settings);
        }
        if (!settings.failed()) {
            read_tests(settings);
        }
        if (Status status = settings.finish(); !status) {
            return status;
        }
        const std::size_t n = model_.states;
        // Rule 7.9.8: each output has a name of its own.
        for (std::size_t i = 0; i < n; ++i) {
            outputs_.push_back(OutputPort{model_.state_names[i], Type::number, false, std::nullopt});
        }
        for (std::size_t i = 0; i < n; ++i) {
            outputs_.push_back(OutputPort{"sigma_" + model_.state_names[i], Type::number, false, std::nullopt});
        }
        for (const Port &port : ports_) {
            for (const char *stem : {"innovation_", "nis_", "refused_", "since_"}) {
                outputs_.push_back(OutputPort{stem + port.name, Type::number, false, std::nullopt});
            }
        }
        for (std::size_t i = 0; i < outputs_.size(); ++i) {
            for (std::size_t j = 0; j < i; ++j) {
                if (outputs_[i].name == outputs_[j].name) {
                    return graph_error(
                        std::format("block '{}': two of its outputs would be named '{}'", setup.id, outputs_[i].name));
                }
            }
        }
        // Its model inputs are deferred and its measurements direct; a measurement has to carry a sample's time.
        for (const std::string &name : model_.input_names) {
            inputs_.push_back(InputPort{name, Type::number, true, true, false});
        }
        for (const Port &port : ports_) {
            for (const InputPort &other : inputs_) {
                if (other.name == port.name) {
                    return graph_error(
                        std::format("block '{}': two of its inputs would be named '{}'", setup.id, port.name));
                }
            }
            inputs_.push_back(InputPort{port.name, Type::number, true, false, true});
        }
        now_.x.assign(n, 0.0);
        now_.p.assign(n * n, 0.0);
        now_.held.assign(model_.inputs, 0.0);
        now_.has.assign(model_.inputs, false);
        now_.ports.assign(ports_.size(), PortMemory{});
        now_.nis.assign(ports_.size() * over_, 0.0);
        reset();
        next_ = now_;
        for (std::vector<double> *room : {&a_, &b_, &c_, &d_, &e_, &f_}) {
            room->assign(n * n, 0.0);
        }
        gain_.assign(n, 0.0);
        vector_.assign(n, 0.0);
        work_.assign(n, 0.0);
        return {};
    }

    std::span<const InputPort> inputs() const override { return inputs_; }
    std::span<const OutputPort> outputs() const override { return outputs_; }
    Status bind(std::span<const std::optional<Type>> /*input_types*/) override { return {}; }
    LoopRole loop_role() const override { return LoopRole{LoopRole::Kind::estimator, 0, false}; }

    void give(const Tick &tick, std::span<const Value> in, std::span<Value> out) override {
        const std::size_t n = model_.states;
        next_ = now_;  // of one size already: nothing is allocated
        Memory &m = next_;
        bool in_doubt = m.gap_in_doubt;  // rule 7.9.7: this tick is the one a gap ran, unless it passed over none
        m.gap_in_doubt = false;
        // Rule 7.9.2: on every tick after tick 0, one step on the model inputs as they were at the tick before.
        if (m.started) {
            const bool stepped = predict(m);
            in_doubt = in_doubt || m.inputs_in_doubt || !stepped;
        }
        m.started = true;

        // Rule 7.9.3: each measurement, in the order they are declared.
        for (std::size_t k = 0; k < ports_.size(); ++k) {
            const Port &port = ports_[k];
            PortMemory &memory = m.ports[k];
            const Value &z = in[model_.inputs + k];
            const std::size_t first = 2 * n + 4 * k;
            out[first] = out[first + 1] = Value::none(State::not_ready);
            const bool takes = z.state == State::good || (z.state == State::uncertain && port.takes_uncertain);
            if (takes && z.timed && (!memory.considered || z.time > memory.considered_at)) {
                memory.considered = true;
                memory.considered_at = z.time;
                const double variance = z.state == State::good ? port.r : port.r_uncertain;
                const double *c = &model_.c[port.output * n];
                double innovation = z.number;
                for (std::size_t i = 0; i < n; ++i) {
                    innovation -= c[i] * m.x[i];
                }
                double spread = spread_of(m, c, variance);
                const double nis = innovation * innovation / spread;
                bool use = true;
                // Rule 7.9.5: over the gate it is refused, unless that would be one more than `max_refused` in
                // a row: then each state's variance grows by its p0, the spread is worked again, and it is used.
                if (has_gate_ && std::fabs(innovation) > gate_ * std::sqrt(spread)) {
                    in_doubt = true;
                    if (memory.run < max_refused_) {
                        use = false;
                        memory.run += 1;
                        memory.refused += 1;
                    } else {
                        grow(m);
                        spread = spread_of(m, c, variance);
                    }
                }
                if (use) {
                    correct(m, c, innovation, spread, variance);
                    memory.run = 0;
                    memory.used = true;
                    memory.used_at = z.time;
                    m.lost = false;
                    in_doubt = in_doubt || z.state == State::uncertain;
                }
                // Rule 7.9.6: the last `over` of them, refused ones among them.
                if (over_ > 0) {
                    m.nis[k * over_ + memory.oldest] = nis;
                    memory.oldest = (memory.oldest + 1) % over_;
                    memory.kept = std::min<std::uint64_t>(memory.kept + 1, over_);
                }
                out[first] = Value::of(innovation);
                out[first + 1] = Value::of(nis);
            }
            if (over_ > 0 && memory.kept == over_) {
                double sum = 0.0;
                for (std::size_t i = 0; i < over_; ++i) {
                    sum += m.nis[k * over_ + i];
                }
                in_doubt = in_doubt || sum / static_cast<double>(over_) > limit_;  // inconsistent
            }
            out[first + 2] = Value::of(static_cast<double>(memory.refused));
            if (memory.used) {
                // The time from the sample to the tick, however far apart they are, and not less than zero.
                const std::uint64_t since = tick.time > memory.used_at ? span_between(memory.used_at, tick.time) : 0;
                out[first + 3] = Value::of(static_cast<double>(since) / 1e9);
            } else {
                out[first + 3] = Value::none(State::not_ready);
            }
        }
        in_doubt = in_doubt || m.lost;
        for (std::size_t i = 0; i < n; ++i) {
            const double sigma = std::sqrt(m.p[i * n + i]);
            const bool wide = has_sigma_max_[i] && sigma > sigma_max_[i];
            const State state = in_doubt || wide ? State::uncertain : State::good;
            out[i] = Value::of(m.x[i], state);
            out[n + i] = Value::of(sigma, state);
        }
    }

    void update(const Tick & /*tick*/, std::span<const Value> in) override {
        // The model inputs as they are at this tick, for the step to the next (rule 7.9.2).
        next_.inputs_in_doubt = false;
        for (std::size_t i = 0; i < model_.inputs; ++i) {
            if (in[i].is_usable()) {
                next_.held[i] = in[i].number;
                next_.has[i] = true;
            }
            next_.inputs_in_doubt = next_.inputs_in_doubt || in[i].state != State::good;
        }
        now_.swap(next_);
    }

    void gap(const Gap &gap) override {
        Memory &m = now_;
        if (gap.known) {
            predict_many(m, gap.ticks);  // rule 7.9.9: what those ticks would have done
        } else {
            m.lost = true;  // rule 7.9.7: until a measurement is used
        }
        if (gap.rebase) {
            // Rule 7.9.9: each state's variance grows by its p0, once, after the predictions for the ticks passed
            // over and before the one for the tick that runs. Rule 8.5: it has considered and used no sample.
            grow(m);
            for (PortMemory &memory : m.ports) {
                memory.considered = false;
                memory.used = false;
            }
        }
        m.gap_in_doubt = !gap.known || gap.ticks > 0;
    }

    void reset() override {
        const std::size_t n = model_.states;
        now_.x = model_.initial;  // rule 7.9.1: the model's initial state, p0 on each state and nothing between
        std::fill(now_.p.begin(), now_.p.end(), 0.0);
        for (std::size_t i = 0; i < n; ++i) {
            now_.p[i * n + i] = p0_[i];
        }
        std::fill(now_.held.begin(), now_.held.end(), 0.0);
        std::fill(now_.has.begin(), now_.has.end(), false);
        std::fill(now_.ports.begin(), now_.ports.end(), PortMemory{});
        std::fill(now_.nis.begin(), now_.nis.end(), 0.0);
        now_.started = now_.inputs_in_doubt = now_.lost = now_.gap_in_doubt = false;
    }

    void save(StateWriter &writer) const override {
        for (const std::vector<double> *values : {&now_.x, &now_.p, &now_.held, &now_.nis}) {
            for (double value : *values) {
                writer.f64(value);
            }
        }
        for (bool has : now_.has) {
            writer.flag(has);
        }
        for (const PortMemory &memory : now_.ports) {
            writer.flag(memory.considered);
            writer.u64(static_cast<std::uint64_t>(memory.considered_at));
            writer.flag(memory.used);
            writer.u64(static_cast<std::uint64_t>(memory.used_at));
            writer.u64(memory.refused);
            writer.u64(memory.run);
            writer.u64(memory.kept);
            writer.u64(memory.oldest);
        }
        writer.flag(now_.started);
        writer.flag(now_.inputs_in_doubt);
        writer.flag(now_.lost);
    }

    bool restore(StateReader &reader) override {
        for (std::vector<double> *values : {&now_.x, &now_.p, &now_.held, &now_.nis}) {
            for (double &value : *values) {
                if (!reader.f64(value)) {
                    return false;
                }
            }
        }
        for (std::size_t i = 0; i < now_.has.size(); ++i) {
            bool has = false;
            if (!reader.flag(has)) {
                return false;
            }
            now_.has[i] = has;
        }
        for (PortMemory &memory : now_.ports) {
            std::uint64_t considered = 0;
            std::uint64_t used = 0;
            std::uint64_t oldest = 0;
            if (!reader.flag(memory.considered) || !reader.u64(considered) || !reader.flag(memory.used) ||
                !reader.u64(used) || !reader.u64(memory.refused) || !reader.u64(memory.run) ||
                !reader.u64(memory.kept) || !reader.u64(oldest) || memory.kept > over_ ||
                oldest >= std::max<std::size_t>(over_, 1)) {
                return false;
            }
            memory.considered_at = static_cast<Time>(considered);
            memory.used_at = static_cast<Time>(used);
            memory.oldest = static_cast<std::size_t>(oldest);
        }
        now_.gap_in_doubt = false;
        return reader.flag(now_.started) && reader.flag(now_.inputs_in_doubt) && reader.flag(now_.lost);
    }

private:
    struct Memory {
        std::vector<double> x;     // the estimate
        std::vector<double> p;     // its covariance, by rows
        std::vector<double> held;  // each model input's last usable value
        std::vector<bool> has;     // whether it has had one
        std::vector<PortMemory> ports;
        std::vector<double> nis;       // `over` for each port
        bool started = false;          // a tick has run: the next one predicts
        bool inputs_in_doubt = false;  // a model input was uncertain or unusable at the tick before
        bool lost = false;             // a gap of no known length, and no measurement used since
        bool gap_in_doubt = false;     // the next tick is one a gap ran, having passed over a tick or nobody knows

        void swap(Memory &other) {
            x.swap(other.x);
            p.swap(other.p);
            held.swap(other.held);
            has.swap(other.has);
            ports.swap(other.ports);
            nis.swap(other.nis);
            std::swap(started, other.started);
            std::swap(inputs_in_doubt, other.inputs_in_doubt);
            std::swap(lost, other.lost);
            std::swap(gap_in_doubt, other.gap_in_doubt);
        }
    };

    // ---- configuring

    void read_model(const BlockSetup &setup, SettingsReader &settings) {
        const Setting *given = settings.raw("model");
        if (given == nullptr || !given->is(Kind::map)) {
            settings.fail("has to have a 'model': a map with a model's type and its settings");
            return;
        }
        // The model's own settings are read as a block's are, from the map, with `type` among them.
        BlockSetup inner = setup;
        inner.settings = given;
        SettingsReader reader(inner);
        std::string type;
        if (!reader.text("type", type) || !is_model_type(type)) {
            settings.fail("its 'model' has to have a 'type' that is a model's");
            return;
        }
        build_model(type, reader, model_);
        if (Status status = reader.finish(); !status) {
            // The message already names the block; say that it is of the model.
            settings.fail(std::format("in its model: {}", status.error().message.substr(setup.id.size() + 10)));
        }
    }

    // A map from states' names to numbers. Each state has to be there where `all` is set; a name that is not a
    // state's is refused.
    bool by_state(SettingsReader &settings, std::string_view key, bool all, std::vector<double> &values,
                  std::vector<bool> *given_for) {
        const Setting *given = settings.raw(key);
        const std::size_t n = model_.states;
        values.assign(n, 0.0);
        std::vector<bool> seen(n, false);
        if (given == nullptr || !given->is(Kind::map)) {
            if (given != nullptr || all) {
                settings.fail(std::format("setting '{}' has to be a map from each state's name to a number", key));
                return false;
            }
        } else {
            for (std::size_t k = 0; k < given->as_map().keys.size(); ++k) {
                const std::string &name = given->as_map().keys[k];
                const Setting &value = given->as_map().values[k];
                const auto at = std::find(model_.state_names.begin(), model_.state_names.end(), name);
                const bool whole = value.is(Kind::whole);
                if (at == model_.state_names.end()) {
                    settings.fail(std::format("setting '{}' names '{}', which is not a state of the model", key, name));
                    return false;
                }
                if (!whole && !(value.is(Kind::number) && std::isfinite(value.as_number()))) {
                    settings.fail(std::format("setting '{}' gives '{}' {}, and has to give a finite number", key, name,
                                              value.shown()));
                    return false;
                }
                const std::size_t i = static_cast<std::size_t>(at - model_.state_names.begin());
                values[i] = whole ? static_cast<double>(value.as_whole()) : value.as_number();
                seen[i] = true;
            }
            for (std::size_t i = 0; all && i < n; ++i) {
                if (!seen[i]) {
                    settings.fail(
                        std::format("setting '{}' has nothing for the state '{}'", key, model_.state_names[i]));
                    return false;
                }
            }
        }
        if (given_for != nullptr) {
            *given_for = seen;
        }
        return true;
    }

    void read_noise(SettingsReader &settings) {
        const std::size_t n = model_.states;
        std::vector<double> q;
        if (!by_state(settings, "q", true, q, nullptr) || !by_state(settings, "p0", true, p0_, nullptr) ||
            !by_state(settings, "sigma_max", false, sigma_max_, &has_sigma_max_)) {
            return;
        }
        for (std::size_t i = 0; i < n; ++i) {
            if (q[i] < 0.0 || !(p0_[i] > 0.0) || (has_sigma_max_[i] && sigma_max_[i] < 0.0)) {
                settings.fail(
                    std::format("for the state '{}', q and sigma_max are not to be negative and p0 has to be "
                                "more than zero",
                                model_.state_names[i]));
                return;
            }
        }
        // Rule 7.9.2: what process noise has added by the end of one step.
        if (model_.continuous) {
            exact_noise(model_.a, n, q, settings.period(), noise_);
        } else {
            noise_.assign(n * n, 0.0);
            for (std::size_t i = 0; i < n; ++i) {
                noise_[i * n + i] = q[i] * (static_cast<double>(settings.period()) / 1e9);
            }
        }
        for (double entry : noise_) {
            if (!std::isfinite(entry)) {
                settings.fail("the process noise its model adds over one period is more than a double holds");
                return;
            }
        }
    }

    void read_ports(SettingsReader &settings) {
        const Setting *measure = settings.raw("measure");
        if (measure == nullptr || !measure->is(Kind::map) || measure->as_map().keys.empty()) {
            settings.fail("setting 'measure' has to be a map of at least one measurement port");
            return;
        }
        for (std::size_t k = 0; k < measure->as_map().keys.size(); ++k) {
            Port port;
            port.name = measure->as_map().keys[k];
            const Setting &given = measure->as_map().values[k];
            // Rule 9.2: a name a block's settings give to a port is not empty and holds no dot.
            if (port.name.empty() || port.name.find('.') != std::string::npos) {
                settings.fail(std::format("measure names a port '{}', and a port's name is not empty and holds no dot",
                                          port.name));
                return;
            }
            if (!given.is(Kind::map)) {
                settings.fail(std::format("measure: port '{}' has to be a map with 'of' and 'r'", port.name));
                return;
            }
            BlockSetup inner;
            inner.id = settings.id();
            inner.settings = &given;
            inner.period = settings.period();
            SettingsReader reader(inner);
            std::string of;
            if (!reader.text("of", of) && !reader.failed()) {
                reader.fail("has no 'of' setting");
            }
            if (!reader.positive("r", port.r) && !reader.failed()) {
                reader.fail("has no 'r' setting");
            }
            port.takes_uncertain = reader.number("r_uncertain", port.r_uncertain);
            if (!reader.failed() && port.takes_uncertain && port.r_uncertain < port.r) {
                reader.fail(
                    std::format("'r_uncertain' is {}, and is not to be less than 'r', {}", port.r_uncertain, port.r));
            }
            if (Status status = reader.finish(); !status) {
                settings.fail(std::format("measure: port '{}': {}", port.name,
                                          status.error().message.substr(settings.id().size() + 10)));
                return;
            }
            const auto at = std::find(model_.output_names.begin(), model_.output_names.end(), of);
            if (at == model_.output_names.end()) {
                settings.fail(
                    std::format("measure: port '{}' is of '{}', which is not an output of the model", port.name, of));
                return;
            }
            port.output = static_cast<std::size_t>(at - model_.output_names.begin());
            for (std::size_t i = 0; i < model_.inputs; ++i) {
                if (model_.d[port.output * model_.inputs + i] != 0.0) {  // rule 7.9.4
                    settings.fail(std::format("measure: port '{}' is of '{}', which reads the input '{}' directly",
                                              port.name, of, model_.input_names[i]));
                    return;
                }
            }
            ports_.push_back(std::move(port));
        }
    }

    void read_tests(SettingsReader &settings) {
        const Setting *consistency = settings.raw("consistency");
        if (consistency == nullptr) {
            settings.fail("has no 'consistency' setting: none, or a map with 'over' and 'limit'");
            return;
        }
        if (consistency->is(Kind::map)) {
            BlockSetup inner;
            inner.id = settings.id();
            inner.settings = consistency;
            inner.period = settings.period();
            SettingsReader reader(inner);
            std::int64_t over = 0;
            if (!reader.whole("over", 1, kMaxCount, over) && !reader.failed()) {
                reader.fail("has no 'over' setting");
            }
            if (!reader.positive("limit", limit_) && !reader.failed()) {
                reader.fail("has no 'limit' setting");
            }
            if (Status status = reader.finish(); !status) {
                settings.fail(std::format("consistency: {}", status.error().message.substr(settings.id().size() + 10)));
                return;
            }
            if (static_cast<std::uint64_t>(over) > kMaxRememberedTicks) {
                settings.fail(std::format("consistency: 'over' is {}, and this engine remembers no more than {}", over,
                                          kMaxRememberedTicks));
                return;
            }
            over_ = static_cast<std::size_t>(over);
        } else if (!consistency->is(Kind::text) || consistency->as_text() != "none") {
            settings.fail("setting 'consistency' has to be none, or a map with 'over' and 'limit'");
            return;
        }
        has_gate_ = settings.not_negative("gate", gate_);
        std::int64_t most = 0;
        const bool limited = settings.whole("max_refused", 0, kMaxCount, most);
        if (!settings.failed() && limited != has_gate_) {
            settings.fail(has_gate_ ? "'max_refused' has to be given with 'gate'"
                                    : "'max_refused' is given, and is only for an estimator with a 'gate'");
        }
        max_refused_ = static_cast<std::uint64_t>(most);
    }

    // ---- the filter

    // c P c' + v
    double spread_of(const Memory &m, const double *c, double variance) const {
        const std::size_t n = model_.states;
        double spread = variance;
        for (std::size_t i = 0; i < n; ++i) {
            for (std::size_t j = 0; j < n; ++j) {
                spread += c[i] * m.p[i * n + j] * c[j];
            }
        }
        return spread;
    }

    void grow(Memory &m) const {
        for (std::size_t i = 0; i < model_.states; ++i) {
            m.p[i * model_.states + i] += p0_[i];
        }
    }

    // out = a * b, and out = a * b', each n by n and by rows.
    void times(const std::vector<double> &a, const std::vector<double> &b, bool transposed,
               std::vector<double> &out) const {
        const std::size_t n = model_.states;
        for (std::size_t i = 0; i < n; ++i) {
            for (std::size_t j = 0; j < n; ++j) {
                double sum = 0.0;
                for (std::size_t k = 0; k < n; ++k) {
                    sum += a[i * n + k] * (transposed ? b[j * n + k] : b[k * n + j]);
                }
                out[i * n + j] = sum;
            }
        }
    }

    // One step (rule 7.9.2). False where some model input has never been usable: the state stays, and the
    // covariance is P + N.
    bool predict(Memory &m) {
        const std::size_t n = model_.states;
        const bool steps = std::find(m.has.begin(), m.has.end(), false) == m.has.end();
        if (steps) {
            model_.step(m.x.data(), m.held.data(), vector_.data());
            m.x.swap(vector_);
            times(model_.ad, m.p, false, a_);  // Ad P
            times(a_, model_.ad, true, m.p);   // (Ad P) Ad'
        }
        for (std::size_t i = 0; i < n * n; ++i) {
            m.p[i] += noise_[i];
        }
        return steps;
    }

    // `count` steps on the model inputs it last had (rule 7.9.9).
    void predict_many(Memory &m, std::uint64_t count) {
        const std::size_t n = model_.states;
        if (count <= kStepsOneByOne) {
            for (std::uint64_t i = 0; i < count; ++i) {
                predict(m);
            }
            return;
        }
        if (std::find(m.has.begin(), m.has.end(), false) != m.has.end()) {
            for (std::size_t i = 0; i < n * n; ++i) {
                m.p[i] += static_cast<double>(count) * noise_[i];  // the state stays: N, that many times
            }
            return;
        }
        // k steps are x -> M x + v and P -> M P M' + S. Doubling: (M, v, S) twice is (M M, M v + v, M S M' + S);
        // and one such after another likewise. The steps are gathered by the bits of `count`.
        std::vector<double> &power = b_;  // M, v and S of the steps gathered so far
        std::vector<double> &sum = c_;
        std::vector<double> &base = d_;  // M and S of 2^i steps
        std::vector<double> &base_sum = e_;
        std::fill(power.begin(), power.end(), 0.0);
        std::fill(sum.begin(), sum.end(), 0.0);
        for (std::size_t i = 0; i < n; ++i) {
            power[i * n + i] = 1.0;
        }
        base = model_.ad;
        base_sum = noise_;
        std::fill(gain_.begin(), gain_.end(), 0.0);  // v of the steps gathered so far
        for (std::size_t i = 0; i < n; ++i) {        // v of 2^i steps, in vector_
            vector_[i] = 0.0;
            for (std::size_t k = 0; k < model_.inputs; ++k) {
                vector_[i] += model_.bd[i * model_.inputs + k] * m.held[k];
            }
        }
        std::vector<double> &scratch = work_;
        for (; count != 0; count >>= 1) {
            if ((count & 1u) != 0) {
                // The 2^i steps after those gathered: M <- B M, v <- B v + b, S <- B S B' + T.
                times(base, sum, false, a_);
                times(a_, base, true, sum);
                for (std::size_t i = 0; i < n * n; ++i) {
                    sum[i] += base_sum[i];
                }
                for (std::size_t i = 0; i < n; ++i) {
                    scratch[i] = vector_[i];
                    for (std::size_t j = 0; j < n; ++j) {
                        scratch[i] += base[i * n + j] * gain_[j];
                    }
                }
                gain_.swap(scratch);
                times(base, power, false, a_);
                power.swap(a_);
            }
            // 2^i steps twice.
            times(base, base_sum, false, a_);
            times(a_, base, true, f_);
            for (std::size_t i = 0; i < n * n; ++i) {
                base_sum[i] += f_[i];
            }
            for (std::size_t i = 0; i < n; ++i) {
                scratch[i] = vector_[i];
                for (std::size_t j = 0; j < n; ++j) {
                    scratch[i] += base[i * n + j] * vector_[j];
                }
            }
            vector_.swap(scratch);
            times(base, base, false, a_);
            base.swap(a_);
        }
        // x <- M x + v, P <- M P M' + S.
        for (std::size_t i = 0; i < n; ++i) {
            scratch[i] = gain_[i];
            for (std::size_t j = 0; j < n; ++j) {
                scratch[i] += power[i * n + j] * m.x[j];
            }
        }
        m.x = scratch;
        times(power, m.p, false, a_);
        times(a_, power, true, m.p);
        for (std::size_t i = 0; i < n * n; ++i) {
            m.p[i] += sum[i];
        }
    }

    // Rule 7.9.4: x = x + g (z - c x), and P = (1 - g c) P (1 - g c)' + g v g', with g = P c' / s.
    void correct(Memory &m, const double *c, double innovation, double spread, double variance) {
        const std::size_t n = model_.states;
        for (std::size_t i = 0; i < n; ++i) {
            double sum = 0.0;
            for (std::size_t j = 0; j < n; ++j) {
                sum += m.p[i * n + j] * c[j];
            }
            gain_[i] = sum / spread;
        }
        for (std::size_t i = 0; i < n; ++i) {
            m.x[i] += gain_[i] * innovation;
            for (std::size_t j = 0; j < n; ++j) {
                b_[i * n + j] = (i == j ? 1.0 : 0.0) - gain_[i] * c[j];  // 1 - g c
            }
        }
        times(b_, m.p, false, a_);
        times(a_, b_, true, m.p);
        for (std::size_t i = 0; i < n; ++i) {
            for (std::size_t j = 0; j < n; ++j) {
                m.p[i * n + j] += gain_[i] * variance * gain_[j];
            }
        }
    }

    Model model_;
    std::vector<InputPort> inputs_;
    std::vector<OutputPort> outputs_;
    std::vector<Port> ports_;
    std::vector<double> noise_;  // N, by rows
    std::vector<double> p0_;
    std::vector<double> sigma_max_;
    std::vector<bool> has_sigma_max_;
    bool has_gate_ = false;
    double gate_ = 0.0;
    std::uint64_t max_refused_ = 0;
    std::size_t over_ = 0;  // zero where consistency is none
    double limit_ = 0.0;

    Memory now_;
    Memory next_;
    // Room to work in, so that a tick allocates nothing.
    std::vector<double> a_, b_, c_, d_, e_, f_, gain_, vector_, work_;
};

}  // namespace

Result<std::unique_ptr<Block>> make_estimator(const BlockSetup &setup) { return make_block<EstimatorBlock>(setup); }

}  // namespace fluxgraph::v2::detail

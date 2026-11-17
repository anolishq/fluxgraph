// `estimator` (section 7.9): a Kalman filter over a linear model, which it hosts as its predictor.

#include <algorithm>
#include <cmath>
#include <format>
#include <optional>

#include "blocks.hpp"
#include "exact.hpp"
#include "exact_step.hpp"
#include "model.hpp"
#include "remembers.hpp"

namespace fluxgraph::v2::detail {

namespace {

using Kind = Setting::Kind;

constexpr std::int64_t kMaxCount = 2'147'483'647;  // Appendix A: the width of `over` and `max_refused`

// Whole-period steps over a stretch are made one by one up to this many. Past it the same result is reached by
// doubling, to within rounding: what is specified is the result (rule 7.9.2).
constexpr std::uint64_t kStepsOneByOne = 64;

// A place (rule 7.9.2): `part` parts of a period after tick `tick`. For a model in continuous time a period has
// sixteen parts; for one in discrete time it has one, and a place is a tick. No place the state or a model input's
// value has is before tick 0, and none is after the last tick 64 bits can number by more than a period.
struct Place {
    std::uint64_t tick = 0;
    std::uint32_t part = 0;
};

constexpr bool before(Place a, Place b) { return a.tick != b.tick ? a.tick < b.tick : a.part < b.part; }

// How far a sample's place is from the place of the tick it is seen at, in parts of a period: `hi` and `lo` are
// one number of 128 bits. A sample as old as a 64-bit clock allows, at a period of a nanosecond, is 2^68 parts
// behind.
struct Offset {
    bool ahead = false;  // the sample is after the tick; never set with nothing in `hi` and `lo`
    std::uint64_t hi = 0;
    std::uint64_t lo = 0;
};

// Whether the place `a` is from its tick is before the place `b` is from the same tick.
constexpr bool earlier(const Offset &a, const Offset &b) {
    if (a.ahead != b.ahead) {
        return b.ahead;
    }
    const bool less = a.hi != b.hi ? a.hi < b.hi : a.lo < b.lo;
    const bool more = a.hi != b.hi ? a.hi > b.hi : a.lo > b.lo;
    return a.ahead ? less : more;
}

// The whole part of (hi * 2^64 + lo) / by, in 128 bits. `by` is not zero.
constexpr void divide(std::uint64_t &hi, std::uint64_t &lo, std::uint64_t by) {
    std::uint64_t rest = hi % by;
    hi /= by;
    if (rest == 0) {
        lo /= by;
        return;
    }
    std::uint64_t quotient = 0;
    for (int bit = 63; bit >= 0; --bit) {
        // The rest is under `by`, so twice it and one may pass 64 bits by one: `carry` is that bit.
        const bool carry = (rest >> 63) != 0;
        rest = (rest << 1) | ((lo >> bit) & 1u);
        quotient <<= 1;
        if (carry || rest >= by) {
            rest -= by;
            quotient |= 1u;
        }
    }
    lo = quotient;
}

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
    bool seen = false;  // the sample time last considered or passed by on it (rule 7.9.3)
    Time seen_at = 0;
    bool used = false;  // the sample time of the measurement last used (rule 7.9.8)
    Time used_at = 0;
    std::uint64_t refused = 0;  // how many have been refused
    std::uint64_t late = 0;     // how many have been passed by as late
    std::uint64_t run = 0;      // how many refused in a row, of those considered (rule 7.9.5)
    std::uint64_t kept = 0;     // how many of the last `over` normalised innovations squared it holds
    std::size_t oldest = 0;
};

// A value a model input was given, and the place it has it from (rule 7.9.2).
struct Given {
    double value = 0.0;
    Place from;
};

// The model's step over a length of time, and what process noise adds over it (rule 7.9.2). Each is by rows.
struct Step {
    std::vector<double> ad;
    std::vector<double> bd;
    std::vector<double> noise;
};

enum PortOut : std::size_t { kInnovation, kNis, kRefused, kLate, kSince, kPortOuts };

// What the estimator remembers. It is copied at every tick, each vector into one of its own size, so that
// nothing is allocated: the first phase does the estimator's work, and works on the copy (rule 4.4).
struct Memory {
    std::vector<double> x;  // the estimate, where it stands
    std::vector<double> p;  // its covariance, by rows
    Place at;               // the place they stand at
    // Each model input: the value in force at the place the state stands at, if it has had one, and after
    // it the values it has from later places, oldest first, in a ring of the block's `room_`.
    std::vector<double> held;
    std::vector<char> has;
    std::vector<Given> given;
    std::vector<std::size_t> first_given;
    std::vector<std::size_t> count_given;
    std::vector<PortMemory> ports;
    std::vector<double> nis;       // `over` for each port
    bool started = false;          // a tick has run
    bool inputs_in_doubt = false;  // a model input was uncertain or unusable at the tick before
    bool lost = false;             // a gap of no known length, and no measurement used since
    bool gap_in_doubt = false;     // the next tick is one a gap ran, having passed over a tick or nobody knows
    bool first = true;             // no measurement has been due since the start, a reset or a rebase
};

class EstimatorBlock : public Committing<Memory> {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        period_ = static_cast<std::uint64_t>(setup.period);
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
        if (!settings.failed() && settings.counted("lag", lag_) && lag_ > kMaxRememberedTicks) {
            settings.fail(std::format("'lag' is {} periods, and this engine remembers no more than {}", lag_,
                                      kMaxRememberedTicks));
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
            for (const char *stem : {"innovation_", "nis_", "refused_", "late_", "since_"}) {  // as PortOut
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
        // A model input has at most one value from each tick's second phase, and those from before the place the
        // state stands at are not kept: with the state no more than `lag` behind, that is `lag` and one.
        room_ = static_cast<std::size_t>(lag_) + 1;
        reset();
        for (std::vector<double> *room : {&a_, &b_, &c_, &d_, &e_, &f_, &carried_p_}) {
            room->assign(n * n, 0.0);
        }
        for (std::vector<double> *room : {&gain_, &vector_, &work_, &carried_x_}) {
            room->assign(n, 0.0);
        }
        u_.assign(model_.inputs, 0.0);
        has_u_.assign(model_.inputs, 0);
        next_given_.assign(model_.inputs, 0);
        due_.assign(ports_.size(), 0);
        offsets_.assign(ports_.size(), Offset{});
        return {};
    }

    std::span<const InputPort> inputs() const override { return inputs_; }
    std::span<const OutputPort> outputs() const override { return outputs_; }
    Status bind(std::span<const std::optional<Type>> /*input_types*/) override { return {}; }
    LoopRole loop_role() const override { return LoopRole{LoopRole::Kind::estimator, 0, false}; }

protected:
    // The first phase does the estimator's work: it carries the state on, and corrects it by the measurements due.
    // All of it is done to `next`, the copy of what is remembered, and none of it reads `now`.
    void step(const Tick &tick, std::span<const Value> in, std::span<Value> out, const Memory & /*now*/,
              Memory &next) const override {
        const std::size_t n = model_.states;
        Memory &m = next;
        const std::uint64_t number = static_cast<std::uint64_t>(tick.number);  // a tick's number is not negative
        const Place here{number, 0};
        // Rule 7.9.7: a model input was uncertain or not usable at the tick before, or this tick is the one a
        // gap ran, unless the gap passed over none.
        bool in_doubt = m.gap_in_doubt || (m.started && m.inputs_in_doubt);
        m.gap_in_doubt = false;
        m.started = true;

        // Rule 7.9.2, lag: before any measurement, a state that stands more than `lag` behind the tick is
        // carried to `lag` behind it.
        if (number >= lag_) {
            stand_at(m, Place{number - lag_, 0});
        }

        // Rule 7.9.3: the measurements due, in the order of their places, and those of one place as declared.
        std::size_t due = 0;
        for (std::size_t k = 0; k < ports_.size(); ++k) {
            const Value &z = in[model_.inputs + k];
            const std::size_t first = 2 * n + kPortOuts * k;
            out[first + kInnovation] = out[first + kNis] = Value::none(State::not_ready);
            const bool takes = z.state == State::good || (z.state == State::uncertain && ports_[k].takes_uncertain);
            if (takes && z.timed && (!m.ports[k].seen || z.time > m.ports[k].seen_at)) {
                offsets_[k] = offset_of(tick.time, z.time);
                std::size_t at = due++;
                for (; at > 0 && earlier(offsets_[k], offsets_[due_[at - 1]]); --at) {
                    due_[at] = due_[at - 1];
                }
                due_[at] = k;
            }
        }
        for (std::size_t d = 0; d < due; ++d) {
            const std::size_t k = due_[d];
            const Port &port = ports_[k];
            PortMemory &memory = m.ports[k];
            const Value &z = in[model_.inputs + k];
            const std::size_t first = 2 * n + kPortOuts * k;
            memory.seen = true;  // considered or passed by: it is the one last seen on its port either way
            memory.seen_at = z.time;
            Place place;
            const bool late = !place_of(number, offsets_[k], place) || before(place, m.at);
            const bool is_first = m.first;
            m.first = false;
            if (late) {
                in_doubt = true;
                if (!is_first) {
                    memory.late += 1;  // passed by: counted, and not considered
                    continue;
                }
                // The first due after the start, a reset or a rebase is considered where the state stands.
            } else {
                stand_at(m, place);
            }
            const double variance = z.state == State::good ? port.r : port.r_uncertain;
            const double *c = &model_.c[port.output * n];
            double innovation = z.number;
            for (std::size_t i = 0; i < n; ++i) {
                innovation -= c[i] * m.x[i];
            }
            double spread = spread_of(m, c, variance);
            const double nis = innovation * innovation / spread;
            bool use = true;
            // Rule 7.9.5: over the gate it is refused, unless that would be one more than `max_refused` in a
            // row: then each state's variance grows by its p0, the spread is worked again, and it is used.
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
            out[first + kInnovation] = Value::of(innovation);
            out[first + kNis] = Value::of(nis);
        }
        for (std::size_t k = 0; k < ports_.size(); ++k) {
            const PortMemory &memory = m.ports[k];
            const std::size_t first = 2 * n + kPortOuts * k;
            if (over_ > 0 && memory.kept == over_) {
                double sum = 0.0;
                for (std::size_t i = 0; i < over_; ++i) {
                    sum += m.nis[k * over_ + i];
                }
                in_doubt = in_doubt || sum / static_cast<double>(over_) > limit_;  // inconsistent
            }
            out[first + kRefused] = Value::of(static_cast<double>(memory.refused));
            out[first + kLate] = Value::of(static_cast<double>(memory.late));
            if (memory.used) {
                // The time from the sample to the tick, however far apart they are, and not less than zero.
                const std::uint64_t since = tick.time > memory.used_at ? span_between(memory.used_at, tick.time) : 0;
                out[first + kSince] = Value::of(static_cast<double>(since) / 1e9);
            } else {
                out[first + kSince] = Value::none(State::not_ready);
            }
        }
        in_doubt = in_doubt || m.lost;
        // Rule 7.9.8: what is given is carried on from where the state stands to the tick, and what stands is
        // left there. Where it stands after the tick it is given as it stands: nothing is carried back.
        const std::vector<double> *x = &m.x;
        const std::vector<double> *p = &m.p;
        if (before(m.at, here)) {
            carried_x_ = m.x;  // of one size already: nothing is allocated
            carried_p_ = m.p;
            carry(m, carried_x_, carried_p_, m.at, here);
            x = &carried_x_;
            p = &carried_p_;
        }
        for (std::size_t i = 0; i < n; ++i) {
            const double sigma = std::sqrt((*p)[i * n + i]);
            const bool wide = has_sigma_max_[i] && sigma > sigma_max_[i];
            const State state = in_doubt || wide ? State::uncertain : State::good;
            out[i] = Value::of((*x)[i], state);
            out[n + i] = Value::of(sigma, state);
        }
    }

    void take(const Tick &tick, std::span<const Value> in, const Memory & /*now*/, Memory &next) const override {
        Memory &m = next;
        m.inputs_in_doubt = false;
        const std::uint64_t number = static_cast<std::uint64_t>(tick.number);
        for (std::size_t i = 0; i < model_.inputs; ++i) {
            const Value &u = in[i];
            m.inputs_in_doubt = m.inputs_in_doubt || u.state != State::good;
            if (!u.is_usable()) {
                continue;  // it gives nothing, and what it last had stays in force
            }
            Given *last = m.count_given[i] > 0 ? &given(m, i, m.count_given[i] - 1) : nullptr;
            if (last != nullptr ? u.number == last->value : (m.has[i] != 0 && u.number == m.held[i])) {
                continue;  // the value it last had
            }
            // Rule 7.9.2: it has the value from the latest of three places: its sample's, the place the state
            // stands at, and the place its last value is from.
            Place from = m.at;
            Place sampled{number, 0};
            if (u.timed && !place_of(number, offset_of(tick.time, u.time), sampled)) {
                sampled = from;  // before tick 0, and so before where the state stands
            }
            if (before(from, sampled)) {
                from = sampled;
            }
            if (last != nullptr && before(from, last->from)) {
                from = last->from;
            }
            if (!before(m.at, from)) {
                m.held[i] = u.number;  // from where the state stands: it is in force
                m.has[i] = 1;
            } else if (last != nullptr && (!before(last->from, from) || m.count_given[i] == room_)) {
                // From the place its last value is from: that one is never in force. `room_` is never reached
                // by a state this block made, and a state restored from elsewhere loses a value here, no more.
                last->value = u.number;
            } else {
                m.count_given[i] += 1;
                given(m, i, m.count_given[i] - 1) = Given{u.number, from};
            }
        }
    }

    void pass_over(const Gap &gap, Memory &now) const override {
        Memory &m = now;
        // Rule 7.9.9: told that ticks were passed over it does nothing then; rule 7.9.2 carries the state over
        // them when the next tick asks.
        if (!gap.known) {
            m.lost = true;  // rule 7.9.7: until a measurement is used
        }
        if (gap.rebase) {
            // The state is carried to the place of the tick before the one that runs; then each state's variance
            // grows by its p0, once in all. Where it stands after that place, on a sample taken after its tick,
            // it stands there still: nothing is carried back.
            stand_at(m, Place{static_cast<std::uint64_t>(gap.tick) - 1, 0});  // the tick a gap runs is at least 1
            grow(m);
            // No remembered place means anything any more: each model input has the value it last had from
            // where the state stands, the next measurement due is the first, and no sample time is remembered
            // (rule 8.5).
            for (std::size_t i = 0; i < model_.inputs; ++i) {
                if (m.count_given[i] > 0) {
                    m.held[i] = given(m, i, m.count_given[i] - 1).value;
                    m.has[i] = 1;
                    m.count_given[i] = 0;
                }
            }
            m.first = true;
            for (PortMemory &memory : m.ports) {
                memory.seen = false;
                memory.used = false;
            }
        }
        m.gap_in_doubt = !gap.known || gap.ticks > 0;
    }

    // Rule 7.9.1: the model's initial state, p0 on each state and nothing between, at tick 0's place.
    Memory start() const override {
        const std::size_t n = model_.states;
        Memory m;
        m.x = model_.initial;
        m.p.assign(n * n, 0.0);
        for (std::size_t i = 0; i < n; ++i) {
            m.p[i * n + i] = p0_[i];
        }
        m.held.assign(model_.inputs, 0.0);
        m.has.assign(model_.inputs, 0);
        m.given.assign(model_.inputs * room_, Given{});
        m.first_given.assign(model_.inputs, 0);
        m.count_given.assign(model_.inputs, 0);
        m.ports.assign(ports_.size(), PortMemory{});
        m.nis.assign(ports_.size() * over_, 0.0);
        return m;
    }

    // What is saved, in order: the state, its covariance and each port's kept normalised innovations squared; the
    // place the state stands at; for each model input whether it has a value in force, that value, how many it
    // has from later places, and each of those with its place; for each port what PortMemory holds; and four
    // flags. Its length is fixed but for the values from later places, of which a model input has `lag` and one
    // at most. `gap_in_doubt` is not saved: a restore is a gap, and the gap sets it.
    void describe(Fields &fields, Memory &m) const override {
        for (std::vector<double> *values : {&m.x, &m.p, &m.nis}) {
            for (double &value : *values) {
                fields(value);
            }
        }
        const auto place = [&](Place &at) {
            std::uint64_t part = at.part;
            fields(at.tick);
            fields(part);
            if (part >= parts_) {
                fields.fail();
            } else {
                at.part = static_cast<std::uint32_t>(part);
            }
        };
        place(m.at);
        for (std::size_t i = 0; i < model_.inputs; ++i) {
            bool has = m.has[i] != 0;
            std::uint64_t count = m.count_given[i];
            fields(has);
            fields(m.held[i]);
            fields(count);
            if (count > room_) {
                fields.fail();
                return;
            }
            if (fields.reading()) {
                m.has[i] = has ? 1 : 0;
                m.first_given[i] = 0;
                m.count_given[i] = static_cast<std::size_t>(count);
            }
            for (std::size_t j = 0; j < m.count_given[i]; ++j) {
                Given &one = given(m, i, j);
                fields(one.value);
                place(one.from);
            }
        }
        for (PortMemory &memory : m.ports) {
            fields(memory.seen);
            fields(memory.seen_at);
            fields(memory.used);
            fields(memory.used_at);
            fields(memory.refused);
            fields(memory.late);
            fields(memory.run);
            fields(memory.kept);
            if (memory.kept > over_) {
                fields.fail();
            }
            fields.index(memory.oldest, std::max<std::size_t>(over_, 1));
        }
        fields(m.started);
        fields(m.inputs_in_doubt);
        fields(m.lost);
        fields(m.first);
    }

private:
    Given &given(Memory &m, std::size_t input, std::size_t index) const {
        return m.given[input * room_ + (m.first_given[input] + index) % room_];
    }
    const Given &given(const Memory &m, std::size_t input, std::size_t index) const {
        return m.given[input * room_ + (m.first_given[input] + index) % room_];
    }

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
        // Rule 7.9.2: the model's step, and what process noise adds over it, for a whole period, and for a model
        // in continuous time for 8, 4, 2 and 1 sixteenths of one: the period halved that many times, which is
        // exact. For a model in discrete time a place is a tick, and the one step is the model's own.
        parts_ = model_.continuous ? 16 : 1;
        for (unsigned halvings = 0; halvings < (model_.continuous ? 5u : 1u); ++halvings) {
            Step step;
            if (halvings == 0) {
                step.ad = model_.ad;
                step.bd = model_.bd;
            } else {
                exact_step(model_.a, n, model_.b, model_.inputs, settings.period(), step.ad, step.bd, halvings);
            }
            if (model_.continuous) {
                exact_noise(model_.a, n, q, settings.period(), step.noise, halvings);
            } else {
                step.noise.assign(n * n, 0.0);
                for (std::size_t i = 0; i < n; ++i) {
                    step.noise[i * n + i] = q[i] * (static_cast<double>(settings.period()) / 1e9);
                }
            }
            for (const std::vector<double> *matrix : {&step.ad, &step.bd, &step.noise}) {
                for (double entry : *matrix) {
                    if (!std::isfinite(entry)) {
                        settings.fail(
                            "the step of its model, or the process noise it adds, over a period or a part "
                            "of one is more than a double holds");
                        return;
                    }
                }
            }
            steps_.push_back(std::move(step));
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

    // ---- places

    // How far the place of a sample taken at `sample` is from the place of the tick at `tick` that sees it: the
    // time between them in parts of a period, to the nearest whole number, exactly a half going to the later
    // place (rule 7.9.2). Worked in whole numbers of 128 bits: the time between is up to 2^64 nanoseconds, and
    // twice that in sixteenths of a period does not fit in 64.
    Offset offset_of(Time tick, Time sample) const {
        Offset offset;
        const bool ahead = sample > tick;
        const std::uint64_t apart = ahead ? span_between(tick, sample) : span_between(sample, tick);
        // With t the time between in periods and `parts_` parts to a period, the place is floor(parts t + 1/2)
        // after the tick for a sample after it, and ceil(parts t - 1/2) before it for one before: as whole
        // numbers, (2 parts apart + period) / (2 period) and (2 parts apart + period - 1) / (2 period).
        const unsigned shift = parts_ == 16 ? 5 : 1;
        offset.hi = apart >> (64 - shift);
        offset.lo = apart << shift;
        const std::uint64_t half = ahead ? period_ : period_ - 1;
        offset.lo += half;
        offset.hi += offset.lo < half ? 1 : 0;
        divide(offset.hi, offset.lo, 2 * period_);  // a period is under 2^63: twice it fits
        offset.ahead = ahead && (offset.hi != 0 || offset.lo != 0);
        return offset;
    }

    // The place `offset` from the place of tick `number`. False where it is before tick 0: such a place is
    // before any the state stands at. One past what 64 bits number is the last there is.
    bool place_of(std::uint64_t number, const Offset &offset, Place &place) const {
        const bool sixteenths = parts_ == 16;
        const std::uint64_t ticks_hi = sixteenths ? offset.hi >> 4 : offset.hi;
        const std::uint64_t ticks = sixteenths ? (offset.hi << 60) | (offset.lo >> 4) : offset.lo;
        const std::uint32_t rest = sixteenths ? static_cast<std::uint32_t>(offset.lo & 15u) : 0;
        if (offset.ahead) {
            const bool fits = ticks_hi == 0 && ticks <= UINT64_MAX - number;
            place = fits ? Place{number + ticks, rest} : Place{UINT64_MAX, parts_ - 1};
            return true;
        }
        // `ticks` whole periods and `rest` parts before the tick: the tick one more than `ticks` before, and on.
        if (ticks_hi != 0 || ticks > number || (rest != 0 && ticks == number)) {
            return false;
        }
        place = rest != 0 ? Place{number - ticks - 1, parts_ - rest} : Place{number - ticks, 0};
        return true;
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

    // Carries the state to `to` where it stands before it, and it stands there (rule 7.9.2). What a model input
    // had before the place the state stands at is not kept.
    void stand_at(Memory &m, Place to) const {
        if (!before(m.at, to)) {
            return;
        }
        carry(m, m.x, m.p, m.at, to);
        m.at = to;
        for (std::size_t i = 0; i < model_.inputs; ++i) {
            while (m.count_given[i] > 0 && !before(to, given(m, i, 0).from)) {
                m.held[i] = given(m, i, 0).value;
                m.has[i] = 1;
                m.first_given[i] = (m.first_given[i] + 1) % room_;
                m.count_given[i] -= 1;
            }
        }
    }

    // Carries `x` and `p` from the place `at` to the later place `to`, a stretch at a time, a stretch ending
    // wherever a model input has a value from (rule 7.9.2). `at` is where the state stands or after it. The
    // model inputs are read and left as they are.
    void carry(const Memory &m, std::vector<double> &x, std::vector<double> &p, Place at, Place to) const {
        for (std::size_t i = 0; i < model_.inputs; ++i) {
            u_[i] = m.held[i];
            has_u_[i] = m.has[i];
            next_given_[i] = 0;
        }
        while (before(at, to)) {
            Place end = to;
            bool all = true;
            for (std::size_t i = 0; i < model_.inputs; ++i) {
                // The value in force over a stretch is the last one from its first place or an earlier one.
                for (; next_given_[i] < m.count_given[i] && !before(at, given(m, i, next_given_[i]).from);
                     ++next_given_[i]) {
                    u_[i] = given(m, i, next_given_[i]).value;
                    has_u_[i] = 1;
                }
                if (next_given_[i] < m.count_given[i] && before(given(m, i, next_given_[i]).from, end)) {
                    end = given(m, i, next_given_[i]).from;
                }
                all = all && has_u_[i] != 0;
            }
            // Over a stretch: as many whole-period steps as go into it, and then steps of 8, 4, 2 and 1
            // sixteenths, each at most once and in that order, as many as make up the rest.
            std::uint64_t whole = end.tick - at.tick;
            std::uint32_t rest = end.part - at.part;
            if (end.part < at.part) {
                whole -= 1;
                rest += parts_;
            }
            steps(x, p, whole, all);
            for (std::size_t halvings = 1; halvings < steps_.size(); ++halvings) {
                if ((rest & (16u >> halvings)) != 0) {
                    step(steps_[halvings], x, p, all);
                }
            }
            at = end;
        }
    }

    // One step: x = Ad x + Bd u and P = Ad P Ad' + N, with u the model inputs in force, in `u_`. Where some model
    // input has no value, never having been usable, `stepped` is false: the state stays, and the covariance is
    // P + N.
    void step(const Step &over, std::vector<double> &x, std::vector<double> &p, bool stepped) const {
        const std::size_t n = model_.states;
        if (stepped) {
            for (std::size_t i = 0; i < n; ++i) {
                double sum = 0.0;
                for (std::size_t j = 0; j < n; ++j) {
                    sum += over.ad[i * n + j] * x[j];
                }
                for (std::size_t k = 0; k < model_.inputs; ++k) {
                    sum += over.bd[i * model_.inputs + k] * u_[k];
                }
                vector_[i] = sum;
            }
            x.swap(vector_);
            times(over.ad, p, false, a_);  // Ad P
            times(a_, over.ad, true, p);   // (Ad P) Ad'
        }
        for (std::size_t i = 0; i < n * n; ++i) {
            p[i] += over.noise[i];
        }
    }

    // `count` steps of a whole period.
    void steps(std::vector<double> &x, std::vector<double> &p, std::uint64_t count, bool stepped) const {
        const std::size_t n = model_.states;
        const Step &over = steps_[0];
        if (count <= kStepsOneByOne) {
            for (std::uint64_t i = 0; i < count; ++i) {
                step(over, x, p, stepped);
            }
            return;
        }
        if (!stepped) {
            for (std::size_t i = 0; i < n * n; ++i) {
                p[i] += static_cast<double>(count) * over.noise[i];  // the state stays: N, that many times
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
        base = over.ad;
        base_sum = over.noise;
        std::fill(gain_.begin(), gain_.end(), 0.0);  // v of the steps gathered so far
        for (std::size_t i = 0; i < n; ++i) {        // v of 2^i steps, in vector_
            vector_[i] = 0.0;
            for (std::size_t k = 0; k < model_.inputs; ++k) {
                vector_[i] += over.bd[i * model_.inputs + k] * u_[k];
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
                scratch[i] += power[i * n + j] * x[j];
            }
        }
        x = scratch;
        times(power, p, false, a_);
        times(a_, power, true, p);
        for (std::size_t i = 0; i < n * n; ++i) {
            p[i] += sum[i];
        }
    }

    // Rule 7.9.4: x = x + g (z - c x), and P = (1 - g c) P (1 - g c)' + g v g', with g = P c' / s.
    void correct(Memory &m, const double *c, double innovation, double spread, double variance) const {
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
    std::uint64_t period_ = 1;  // in nanoseconds
    std::uint32_t parts_ = 16;  // the parts a period has: 16, or 1 for a model in discrete time
    std::uint64_t lag_ = 2;     // in periods
    std::size_t room_ = 1;      // how many values from later places a model input may have
    std::vector<Step> steps_;   // of a whole period, and for a model in continuous time of 8, 4, 2 and 1 sixteenths
    std::vector<double> p0_;
    std::vector<double> sigma_max_;
    std::vector<bool> has_sigma_max_;
    bool has_gate_ = false;
    double gate_ = 0.0;
    std::uint64_t max_refused_ = 0;
    std::size_t over_ = 0;  // zero where consistency is none
    double limit_ = 0.0;

    // Room to work in, so that a tick allocates nothing. It is not what the block remembers, and a function that
    // may not change that may still work in it: so it is mutable.
    mutable std::vector<double> a_, b_, c_, d_, e_, f_, gain_, vector_, work_;
    mutable std::vector<double> carried_x_, carried_p_;  // what is given at a tick, carried on from where it stands
    mutable std::vector<double> u_;                      // the model inputs in force over a stretch
    mutable std::vector<char> has_u_;
    mutable std::vector<std::size_t> next_given_;
    mutable std::vector<std::size_t> due_;  // the ports with a measurement due, in the order of their places
    mutable std::vector<Offset> offsets_;
};

}  // namespace

Result<std::unique_ptr<Block>> make_estimator(const BlockSetup &setup) { return make_block<EstimatorBlock>(setup); }

}  // namespace fluxgraph::v2::detail

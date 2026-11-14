// The model block (section 7.8): it hosts a model, and its memory is the model's state.

#include <algorithm>
#include <cmath>
#include <format>
#include <optional>

#include "blocks.hpp"
#include "exact.hpp"
#include "model.hpp"

namespace fluxgraph::v2::detail {

namespace {

// Steps a gap passed over are taken one by one up to this many, as ticks that were run would have taken them.
// Past it the same result is reached by squaring the step, to within rounding (rule 7.9.9 says so of the result).
constexpr std::uint64_t kStepsOneByOne = 64;

class ModelBlock : public Block {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        build_model(setup.type, settings, model_);
        settings.counted("ride_through", ride_through_);
        settle_written_ = settings.counted("settle", settle_);
        if (Status status = settings.finish(); !status) {
            return status;
        }
        if (!settle_written_ && model_.has_settle) {
            settle_ = model_.settle;  // rule 7.8.6: a named model's own, unless given
        }
        has_settle_ = settle_written_ || model_.has_settle;
        for (std::size_t i = 0; i < model_.inputs; ++i) {
            // Rule 7.8.2: direct if the model's outputs read it, and deferred if only its step does.
            inputs_.push_back(InputPort{model_.input_names[i], Type::number, true, !model_.direct[i]});
        }
        for (const std::string &name : model_.output_names) {
            outputs_.push_back(OutputPort{name, Type::number, false});
        }
        for (const char *name : {"elapsed", "doubtful", "gaps"}) {
            outputs_.push_back(OutputPort{name, Type::number, false});
        }
        period_seconds_ = static_cast<double>(setup.period) / 1e9;
        const std::size_t n = model_.states;
        const std::size_t wide = (n + 1) * (n + 1);
        x_.assign(n, 0.0);
        next_.assign(n, 0.0);
        u_.assign(model_.inputs, 0.0);
        y_.assign(model_.outputs, 0.0);
        held_.assign(model_.inputs, Held{});
        power_.assign(wide, 0.0);
        square_.assign(wide, 0.0);
        product_.assign(wide, 0.0);
        reset();
        return {};
    }

    std::span<const InputPort> inputs() const override { return inputs_; }
    std::span<const OutputPort> outputs() const override { return outputs_; }
    Status bind(std::span<const std::optional<Type>> /*input_types*/) override { return {}; }

    LoopRole loop_role() const override { return LoopRole{LoopRole::Kind::model, settle_, settle_written_}; }

    void give(const Tick &tick, std::span<const Value> in, std::span<Value> out) override {
        // Rule 7.8.5: a model never gives up its state. Where its outputs read a direct input that is unusable
        // they are worked on its last usable value, or on zero if it has had none, and are uncertain; where
        // they read one that is uncertain, rule D makes them so. The outputs are judged together.
        bool in_doubt = false;
        for (std::size_t i = 0; i < model_.inputs; ++i) {
            if (!model_.direct[i]) {
                u_[i] = 0.0;
            } else if (in[i].is_usable()) {
                u_[i] = in[i].number;
                in_doubt = in_doubt || in[i].state == State::uncertain;
            } else {
                u_[i] = held_[i].has ? held_[i].value : 0.0;
                in_doubt = true;
            }
        }
        // Rule 7.8.6: uncertain for `settle` after its doubt; on a loop, after the loop's in place of its own
        // (rule 7.8.8). A tick is never before a doubt, so the difference is in order.
        if (tick.on_model_loop) {
            in_doubt = in_doubt || tick.loop_settling;
        } else if (has_settle_ && doubted_ && span_between(doubt_, tick.number) <= settle_) {
            in_doubt = true;
        }
        model_.give(x_.data(), u_.data(), y_.data());
        const State state = in_doubt ? State::uncertain : State::good;
        for (std::size_t i = 0; i < model_.outputs; ++i) {
            out[i] = Value::of(y_[i], state);
        }
        // `elapsed` counts this tick; `doubtful` counts the steps of the ticks before it.
        Counters shown = counters_;
        shown.elapsed += 1;
        shown.give(out, model_.outputs, period_seconds_);
    }

    void update(const Tick &tick, std::span<const Value> in) override {
        counters_.elapsed += 1;
        // Rules 7.8.3 and 7.8.4: with an input unusable it steps on that input's last usable value, if that was
        // no more than `ride_through` ago, and otherwise does not step.
        bool steps = true;
        bool in_doubt = false;
        for (std::size_t i = 0; i < model_.inputs; ++i) {
            Held &held = held_[i];
            if (in[i].is_usable()) {
                held = Held{true, false, in[i].number, 0};
                in_doubt = in_doubt || in[i].state == State::uncertain;
            } else {
                held.run += 1;  // a count of ticks: see Counters
                in_doubt = true;
                steps = steps && held.has && !held.lost && held.run <= ride_through_;
            }
            u_[i] = held.value;
        }
        if (steps) {
            model_.step(x_.data(), u_.data(), next_.data());
            x_.swap(next_);
        }
        if (in_doubt) {  // rule 7.8.6: stepped on an uncertain or a held value, or did not step
            doubted_ = true;
            doubt_ = tick.number;
            counters_.doubtful += 1;
        }
    }

    void gap(const Gap &gap) override {
        counters_.gaps += 1;
        if (!gap.known) {
            // It takes no step and does not ride through, until each input is usable again.
            for (Held &held : held_) {
                held.lost = true;
            }
        } else if (gap.ticks > 0) {
            // For each tick passed over, in order, it steps on the last usable value of every input while each
            // is within `ride_through`, and takes no step from the first tick where one is not.
            std::uint64_t steps = gap.ticks;
            for (std::size_t i = 0; i < model_.inputs; ++i) {
                const Held &held = held_[i];
                const bool can = held.has && !held.lost && held.run < ride_through_;
                steps = std::min(steps, can ? ride_through_ - held.run : 0);
                u_[i] = held.value;
            }
            step_many(steps);
            for (Held &held : held_) {
                held.run += gap.ticks;
            }
            counters_.elapsed += gap.ticks;
            counters_.doubtful += gap.ticks;
        }
        if (!gap.known || gap.ticks > 0) {
            doubted_ = true;  // the tick before the one that runs is a doubt
            doubt_ = gap.tick - 1;
        }
    }

    void reset() override {
        x_ = model_.initial;
        std::fill(held_.begin(), held_.end(), Held{});
        counters_ = Counters{};
        doubted_ = false;
        doubt_ = 0;
    }

    void save(StateWriter &writer) const override {
        for (double value : x_) {
            writer.f64(value);
        }
        for (const Held &held : held_) {
            writer.flag(held.has);
            writer.flag(held.lost);
            writer.f64(held.value);
            writer.u64(held.run);
        }
        counters_.save(writer);
        writer.flag(doubted_);
        writer.u64(static_cast<std::uint64_t>(doubt_));
    }

    bool restore(StateReader &reader) override {
        for (double &value : x_) {
            if (!reader.f64(value)) {
                return false;
            }
        }
        for (Held &held : held_) {
            if (!reader.flag(held.has) || !reader.flag(held.lost) || !reader.f64(held.value) || !reader.u64(held.run)) {
                return false;
            }
        }
        std::uint64_t doubt = 0;
        if (!counters_.restore(reader) || !reader.flag(doubted_) || !reader.u64(doubt)) {
            return false;
        }
        doubt_ = static_cast<std::int64_t>(doubt);
        return true;
    }

private:
    // What is kept of one input: its last usable value (rule 7.8.5), and how long ago that was.
    struct Held {
        bool has = false;   // it has had a usable value
        bool lost = false;  // a gap of no known length since: no riding through until it is usable again
        double value = 0.0;
        std::uint64_t run = 0;  // unusable ticks in a row since, ticks a gap passed over among them
    };

    // `steps` steps on the inputs in u_, which are held throughout.
    void step_many(std::uint64_t steps) {
        if (steps <= kStepsOneByOne) {
            for (std::uint64_t i = 0; i < steps; ++i) {
                model_.step(x_.data(), u_.data(), next_.data());
                x_.swap(next_);
            }
            return;
        }
        // One step is the map z -> M z on z = (x, 1), with M = [[Ad, Bd u], [0, 1]]. M to the power `steps`, by
        // squaring, applied to (x, 1).
        const std::size_t n = model_.states;
        const std::size_t w = n + 1;
        std::fill(square_.begin(), square_.end(), 0.0);
        std::fill(power_.begin(), power_.end(), 0.0);
        for (std::size_t i = 0; i < n; ++i) {
            for (std::size_t j = 0; j < n; ++j) {
                square_[i * w + j] = model_.ad[i * n + j];
            }
            for (std::size_t k = 0; k < model_.inputs; ++k) {
                square_[i * w + n] += model_.bd[i * model_.inputs + k] * u_[k];
            }
        }
        square_[n * w + n] = 1.0;
        for (std::size_t i = 0; i < w; ++i) {
            power_[i * w + i] = 1.0;
        }
        const auto multiply = [this, w](const std::vector<double> &a, const std::vector<double> &b) {
            for (std::size_t i = 0; i < w; ++i) {
                for (std::size_t j = 0; j < w; ++j) {
                    double sum = 0.0;
                    for (std::size_t k = 0; k < w; ++k) {
                        sum += a[i * w + k] * b[k * w + j];
                    }
                    product_[i * w + j] = sum;
                }
            }
        };
        for (; steps != 0; steps >>= 1) {
            if ((steps & 1u) != 0) {
                multiply(square_, power_);
                power_.swap(product_);
            }
            multiply(square_, square_);
            square_.swap(product_);
        }
        for (std::size_t i = 0; i < n; ++i) {
            double sum = power_[i * w + n];
            for (std::size_t j = 0; j < n; ++j) {
                sum += power_[i * w + j] * x_[j];
            }
            next_[i] = sum;
        }
        x_.swap(next_);
    }

    Model model_;
    std::vector<InputPort> inputs_;
    std::vector<OutputPort> outputs_;
    std::uint64_t ride_through_ = 0;  // in ticks
    std::uint64_t settle_ = 0;        // in ticks
    bool has_settle_ = false;
    bool settle_written_ = false;
    double period_seconds_ = 1.0;

    std::vector<double> x_;  // the state at the tick being run, and after update() at the next
    std::vector<Held> held_;
    Counters counters_;
    bool doubted_ = false;
    std::int64_t doubt_ = 0;  // the number of the tick of its latest doubt

    // Room to work in, so that a tick allocates nothing.
    std::vector<double> next_;
    std::vector<double> u_;
    std::vector<double> y_;
    std::vector<double> power_;
    std::vector<double> square_;
    std::vector<double> product_;
};

}  // namespace

Result<std::unique_ptr<Block>> make_model(const BlockSetup &setup) { return make_block<ModelBlock>(setup); }

}  // namespace fluxgraph::v2::detail

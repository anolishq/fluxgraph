// The model block (section 7.8): it hosts a model, and its memory is the model's state.

#include <algorithm>
#include <cmath>
#include <format>
#include <optional>

#include "blocks.hpp"
#include "exact.hpp"
#include "model.hpp"
#include "remembers.hpp"

namespace fluxgraph::v2::detail {

namespace {

// Steps a gap passed over are taken one by one up to this many, as ticks that were run would have taken them.
// Past it the same result is reached by squaring the step, to within rounding (rule 7.9.9 says so of the result).
constexpr std::uint64_t kStepsOneByOne = 64;

// What is kept of one input: its last usable value (rule 7.8.5), and how long ago that was.
struct Held {
    bool has = false;   // it has had a usable value
    bool lost = false;  // a gap of no known length since: no riding through until it is usable again
    double value = 0.0;
    std::uint64_t run = 0;  // unusable ticks in a row since, ticks a gap passed over among them
};

struct Memory {
    std::vector<double> x;  // the state at the tick being run, and after the second phase at the next
    std::vector<Held> held;
    Counters counters;
    bool doubted = false;
    std::int64_t doubt = 0;  // the number of the tick of its latest doubt
};

// Room to work in, so that a tick allocates nothing.
struct Work {
    std::vector<double> next;
    std::vector<double> u;
    std::vector<double> y;
    std::vector<double> power;
    std::vector<double> square;
    std::vector<double> product;
};

class ModelBlock : public InPlace<Memory, Work> {
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
        reset();
        return {};
    }

    std::span<const InputPort> inputs() const override { return inputs_; }
    std::span<const OutputPort> outputs() const override { return outputs_; }
    Status bind(std::span<const std::optional<Type>> /*input_types*/) override { return {}; }

    LoopRole loop_role() const override { return LoopRole{LoopRole::Kind::model, settle_, settle_written_}; }

protected:
    void look(const Tick &tick, std::span<const Value> in, std::span<Value> out, const Memory &memory,
              Work &work) const override {
        // Rule 7.8.5: a model never gives up its state. Where its outputs read a direct input that is unusable
        // they are worked on its last usable value, or on zero if it has had none, and are uncertain; where
        // they read one that is uncertain, rule D makes them so. The outputs are judged together.
        bool in_doubt = false;
        for (std::size_t i = 0; i < model_.inputs; ++i) {
            if (!model_.direct[i]) {
                work.u[i] = 0.0;
            } else if (in[i].is_usable()) {
                work.u[i] = in[i].number;
                in_doubt = in_doubt || in[i].state == State::uncertain;
            } else {
                work.u[i] = memory.held[i].has ? memory.held[i].value : 0.0;
                in_doubt = true;
            }
        }
        // Rule 7.8.6: uncertain for `settle` after its doubt; on a loop, after the loop's in place of its own
        // (rule 7.8.8). A tick is never before a doubt, so the difference is in order.
        if (tick.on_model_loop) {
            in_doubt = in_doubt || tick.loop_settling;
        } else if (has_settle_ && memory.doubted && span_between(memory.doubt, tick.number) <= settle_) {
            in_doubt = true;
        }
        model_.give(memory.x.data(), work.u.data(), work.y.data());
        const State state = in_doubt ? State::uncertain : State::good;
        for (std::size_t i = 0; i < model_.outputs; ++i) {
            out[i] = Value::of(work.y[i], state);
        }
        // `elapsed` counts this tick; `doubtful` counts the steps of the ticks before it.
        Counters shown = memory.counters;
        shown.elapsed += 1;
        shown.give(out, model_.outputs, period_seconds_);
    }

    void take(const Tick &tick, std::span<const Value> in, Memory &memory, Work &work) const override {
        memory.counters.elapsed += 1;
        // Rules 7.8.3 and 7.8.4: with an input unusable it steps on that input's last usable value, if that was
        // no more than `ride_through` ago, and otherwise does not step.
        bool steps = true;
        bool in_doubt = false;
        for (std::size_t i = 0; i < model_.inputs; ++i) {
            Held &held = memory.held[i];
            if (in[i].is_usable()) {
                held = Held{true, false, in[i].number, 0};
                in_doubt = in_doubt || in[i].state == State::uncertain;
            } else {
                held.run += 1;  // a count of ticks: see Counters
                in_doubt = true;
                steps = steps && held.has && !held.lost && held.run <= ride_through_;
            }
            work.u[i] = held.value;
        }
        if (steps) {
            model_.step(memory.x.data(), work.u.data(), work.next.data());
            memory.x.swap(work.next);
        }
        if (in_doubt) {  // rule 7.8.6: stepped on an uncertain or a held value, or did not step
            memory.doubted = true;
            memory.doubt = tick.number;
            memory.counters.doubtful += 1;
        }
    }

    void pass_over(const Gap &gap, Memory &memory, Work &work) const override {
        memory.counters.gaps += 1;
        if (!gap.known) {
            // It takes no step and does not ride through, until each input is usable again.
            for (Held &held : memory.held) {
                held.lost = true;
            }
        } else if (gap.ticks > 0) {
            // For each tick passed over, in order, it steps on the last usable value of every input while each
            // is within `ride_through`, and takes no step from the first tick where one is not.
            std::uint64_t steps = gap.ticks;
            for (std::size_t i = 0; i < model_.inputs; ++i) {
                const Held &held = memory.held[i];
                const bool can = held.has && !held.lost && held.run < ride_through_;
                steps = std::min(steps, can ? ride_through_ - held.run : 0);
                work.u[i] = held.value;
            }
            step_many(steps, memory, work);
            for (Held &held : memory.held) {
                held.run += gap.ticks;
            }
            memory.counters.elapsed += gap.ticks;
            memory.counters.doubtful += gap.ticks;
        }
        if (!gap.known || gap.ticks > 0) {
            memory.doubted = true;  // the tick before the one that runs is a doubt
            memory.doubt = gap.tick - 1;
        }
    }

    Memory start() const override {
        return Memory{model_.initial, std::vector<Held>(model_.inputs, Held{}), Counters{}, false, 0};
    }

    Work room() const override {
        const std::size_t n = model_.states;
        const std::size_t wide = (n + 1) * (n + 1);
        return Work{std::vector<double>(n, 0.0),
                    std::vector<double>(model_.inputs, 0.0),
                    std::vector<double>(model_.outputs, 0.0),
                    std::vector<double>(wide, 0.0),
                    std::vector<double>(wide, 0.0),
                    std::vector<double>(wide, 0.0)};
    }

    void describe(Fields &fields, Memory &memory) const override {
        for (double &value : memory.x) {
            fields(value);
        }
        for (Held &held : memory.held) {
            fields(held.has);
            fields(held.lost);
            fields(held.value);
            fields(held.run);
        }
        fields(memory.counters);
        fields(memory.doubted);
        fields(memory.doubt);
    }

private:
    // `steps` steps on the inputs in the work's `u`, which are held throughout.
    void step_many(std::uint64_t steps, Memory &memory, Work &work) const {
        if (steps <= kStepsOneByOne) {
            for (std::uint64_t i = 0; i < steps; ++i) {
                model_.step(memory.x.data(), work.u.data(), work.next.data());
                memory.x.swap(work.next);
            }
            return;
        }
        // One step is the map z -> M z on z = (x, 1), with M = [[Ad, Bd u], [0, 1]]. M to the power `steps`, by
        // squaring, applied to (x, 1).
        const std::size_t n = model_.states;
        const std::size_t w = n + 1;
        std::fill(work.square.begin(), work.square.end(), 0.0);
        std::fill(work.power.begin(), work.power.end(), 0.0);
        for (std::size_t i = 0; i < n; ++i) {
            for (std::size_t j = 0; j < n; ++j) {
                work.square[i * w + j] = model_.ad[i * n + j];
            }
            for (std::size_t k = 0; k < model_.inputs; ++k) {
                work.square[i * w + n] += model_.bd[i * model_.inputs + k] * work.u[k];
            }
        }
        work.square[n * w + n] = 1.0;
        for (std::size_t i = 0; i < w; ++i) {
            work.power[i * w + i] = 1.0;
        }
        const auto multiply = [&work, w](const std::vector<double> &a, const std::vector<double> &b) {
            for (std::size_t i = 0; i < w; ++i) {
                for (std::size_t j = 0; j < w; ++j) {
                    double sum = 0.0;
                    for (std::size_t k = 0; k < w; ++k) {
                        sum += a[i * w + k] * b[k * w + j];
                    }
                    work.product[i * w + j] = sum;
                }
            }
        };
        for (; steps != 0; steps >>= 1) {
            if ((steps & 1u) != 0) {
                multiply(work.square, work.power);
                work.power.swap(work.product);
            }
            multiply(work.square, work.square);
            work.square.swap(work.product);
        }
        for (std::size_t i = 0; i < n; ++i) {
            double sum = work.power[i * w + n];
            for (std::size_t j = 0; j < n; ++j) {
                sum += work.power[i * w + j] * memory.x[j];
            }
            work.next[i] = sum;
        }
        memory.x.swap(work.next);
    }

    Model model_;
    std::vector<InputPort> inputs_;
    std::vector<OutputPort> outputs_;
    std::uint64_t ride_through_ = 0;  // in ticks
    std::uint64_t settle_ = 0;        // in ticks
    bool has_settle_ = false;
    bool settle_written_ = false;
    double period_seconds_ = 1.0;
};

}  // namespace

Result<std::unique_ptr<Block>> make_model(const BlockSetup &setup) { return make_block<ModelBlock>(setup); }

}  // namespace fluxgraph::v2::detail

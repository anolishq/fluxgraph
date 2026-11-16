// `delay` (Appendix A): at tick k its output is its input at tick k - ticks, as a reader of that input saw it then.

#include <algorithm>
#include <array>
#include <format>
#include <optional>

#include "blocks.hpp"

namespace fluxgraph::v2::detail {

namespace {

class DelayBlock : public Block {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        std::int64_t ticks = 1;
        settings.whole("ticks", 1, 2'147'483'647, ticks);
        has_initial_ = settings.constant("initial", initial_);
        if (Status status = settings.finish(); !status) {
            return status;
        }
        if (static_cast<std::uint64_t>(ticks) > kMaxRememberedTicks) {
            return graph_error(
                std::format("block '{}': setting 'ticks' is {}, and this engine remembers no more than {}", setup.id,
                            ticks, kMaxRememberedTicks));
        }
        id_ = setup.id;
        outputs_[0].type = has_initial_ ? std::optional<Type>(initial_.type) : std::nullopt;
        held_.assign(static_cast<std::size_t>(ticks), Value{});
        reset();
        return {};
    }

    std::span<const InputPort> inputs() const override { return inputs_; }
    std::span<const OutputPort> outputs() const override { return outputs_; }

    Status bind(std::span<const std::optional<Type>> input_types) override {
        if (!input_types[0].has_value()) {
            return {};  // not known yet: an initial value has said what the output is, if there is one
        }
        if (has_initial_ && initial_.type != *input_types[0]) {
            return graph_error(std::format("block '{}': its input is a {} and its initial value is a {}", id_,
                                           name_of(*input_types[0]), name_of(initial_.type)));
        }
        outputs_[0].type = input_types[0];
        return {};
    }

    Status on_loop() override {
        if (!has_initial_) {  // rule 5.4
            return graph_error(
                std::format("block '{}': a delay that can reach its own input has to have an initial value", id_));
        }
        return {};
    }

    LoopRole loop_role() const override { return LoopRole{LoopRole::Kind::remembers, held_.size(), false}; }

    void loop_settled() override {
        for (Value &value : held_) {  // rule 7.8.8: every such value it holds, and not only the one it gives next
            if (value.state == State::uncertain) {
                value.state = State::good;
            }
        }
    }

    void give(const Tick & /*tick*/, std::span<const Value> /*in*/, std::span<Value> out) override {
        out[0] = held_[next_];
    }

    void update(const Tick & /*tick*/, std::span<const Value> in) override {
        held_[next_] = in[0];
        next_ = (next_ + 1) % held_.size();
    }

    void gap(const Gap &gap) override {
        if (!gap.known) {
            std::fill(held_.begin(), held_.end(), Value{});  // everything it holds is not_ready
        } else {
            // It moves on that many places, taking in not_ready for each; past its length that is all of it.
            const std::size_t places = static_cast<std::size_t>(std::min<std::uint64_t>(gap.ticks, held_.size()));
            for (std::size_t i = 0; i < places; ++i) {
                held_[next_] = Value{};
                next_ = (next_ + 1) % held_.size();
            }
        }
        if (gap.rebase) {  // rule 8.5: the values it holds lose their sample times
            for (Value &value : held_) {
                value.timed = false;
            }
        }
    }

    void reset() override {
        // Before tick 0 its output is `initial` and good, with no sample time, or not_ready.
        std::fill(held_.begin(), held_.end(), has_initial_ ? initial_ : Value{});
        next_ = 0;
    }

    void save(StateWriter &writer) const override {
        writer.u64(next_);
        for (const Value &value : held_) {
            writer.value(value);
        }
    }

    bool restore(StateReader &reader) override {
        std::uint64_t next = 0;
        if (!reader.u64(next) || next >= held_.size()) {
            return false;
        }
        next_ = static_cast<std::size_t>(next);
        for (Value &value : held_) {
            if (!reader.value(value)) {
                return false;
            }
        }
        return true;
    }

private:
    std::array<InputPort, 1> inputs_ = {{{"x", std::nullopt, true, true}}};
    std::array<OutputPort, 1> outputs_ = {{{"y", std::nullopt, true, 0}}};
    std::string id_;
    bool has_initial_ = false;
    Value initial_;
    std::vector<Value> held_;  // the last `ticks` inputs; the oldest, which is what it gives next, is at next_
    std::size_t next_ = 0;
};

}  // namespace

Result<std::unique_ptr<Block>> make_delay(const BlockSetup &setup) { return make_block<DelayBlock>(setup); }

}  // namespace fluxgraph::v2::detail

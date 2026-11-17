// `delay` (Appendix A): at tick k its output is its input at tick k - ticks, as a reader of that input saw it then.

#include <algorithm>
#include <array>
#include <format>
#include <optional>

#include "blocks.hpp"
#include "remembers.hpp"

namespace fluxgraph::v2::detail {

namespace {

// The last `ticks` inputs. The oldest, which is what the block gives next, is at `next`.
struct Memory {
    std::vector<Value> held;
    std::size_t next = 0;
};

class DelayBlock : public InPlace<Memory> {
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
        ticks_ = static_cast<std::size_t>(ticks);
        reset();
        return {};
    }

    std::span<const InputPort> inputs() const override { return inputs_; }
    std::span<const OutputPort> outputs() const override { return outputs_; }

    Status bind(std::span<const std::optional<Type>> input_types) override {
        const std::optional<Type> &input = input_types[0];
        if (!input.has_value()) {
            return {};  // not known yet: an initial value has said what the output is, if there is one
        }
        if (has_initial_ && initial_.type != *input) {
            return graph_error(std::format("block '{}': its input is a {} and its initial value is a {}", id_,
                                           name_of(*input), name_of(initial_.type)));
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

    LoopRole loop_role() const override { return LoopRole{LoopRole::Kind::remembers, ticks_, false}; }

protected:
    void settle(Memory &memory) const override {
        for (Value &value : memory.held) {  // rule 7.8.8: every such value it holds, and not only the one it gives next
            if (value.state == State::uncertain) {
                value.state = State::good;
            }
        }
    }

    void look(const Tick & /*tick*/, std::span<const Value> /*in*/, std::span<Value> out, const Memory &memory,
              NoWork & /*work*/) const override {
        out[0] = memory.held[memory.next];
    }

    void take(const Tick & /*tick*/, std::span<const Value> in, Memory &memory,
              const NoWork & /*work*/) const override {
        memory.held[memory.next] = in[0];
        memory.next = (memory.next + 1) % memory.held.size();
    }

    void pass_over(const Gap &gap, Memory &memory) const override {
        if (!gap.known) {
            std::fill(memory.held.begin(), memory.held.end(), Value{});  // everything it holds is not_ready
        } else {
            // It moves on that many places, taking in not_ready for each; past its length that is all of it.
            const std::size_t places = static_cast<std::size_t>(std::min<std::uint64_t>(gap.ticks, memory.held.size()));
            for (std::size_t i = 0; i < places; ++i) {
                memory.held[memory.next] = Value{};
                memory.next = (memory.next + 1) % memory.held.size();
            }
        }
        if (gap.rebase) {  // rule 8.5: the values it holds lose their sample times
            for (Value &value : memory.held) {
                value.timed = false;
            }
        }
    }

    // Before tick 0 its output is `initial` and good, with no sample time, or not_ready.
    Memory start() const override { return Memory{std::vector<Value>(ticks_, has_initial_ ? initial_ : Value{}), 0}; }

    void describe(Fields &fields, Memory &memory) const override {
        fields.index(memory.next, memory.held.size());
        for (Value &value : memory.held) {
            fields(value);
        }
    }

private:
    std::array<InputPort, 1> inputs_ = {{{"x", std::nullopt, true, true}}};
    std::array<OutputPort, 1> outputs_ = {{{"y", std::nullopt, true, 0}}};
    std::string id_;
    bool has_initial_ = false;
    Value initial_;
    std::size_t ticks_ = 1;
};

}  // namespace

Result<std::unique_ptr<Block>> make_delay(const BlockSetup &setup) { return make_block<DelayBlock>(setup); }

}  // namespace fluxgraph::v2::detail

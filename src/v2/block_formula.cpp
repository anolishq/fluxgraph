// `formula` and `all_good`: the two block types with no memory, and with inputs under names the graph chooses.

#include <format>
#include <optional>

#include "blocks.hpp"
#include "formula.hpp"

namespace fluxgraph::v2::detail {

namespace {

class StatelessBlock : public Block {
public:
    std::span<const InputPort> inputs() const override { return inputs_; }
    std::span<const OutputPort> outputs() const override { return outputs_; }
    void update(const Tick & /*tick*/, std::span<const Value> /*in*/) override {}
    void gap(const Gap & /*gap*/) override {}  // rule 8.6: nothing, no memory
    void reset() override {}
    void save(StateWriter & /*writer*/) const override {}
    bool restore(StateReader & /*reader*/) override { return true; }

protected:
    std::vector<InputPort> inputs_;
    std::vector<OutputPort> outputs_;
};

class FormulaBlock : public StatelessBlock {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        std::string text;
        std::string sample_of;
        if (!settings.text("expr", text) && !settings.failed()) {
            settings.fail("has no 'expr' setting");
        }
        const bool named = settings.text("sample_of", sample_of);
        if (Status status = settings.finish(); !status) {
            return status;
        }
        if (setup.connections.empty()) {
            return graph_error(std::format("block '{}': a formula takes one or more inputs", setup.id));
        }
        std::size_t signals = 0;
        std::optional<std::size_t> named_place;
        for (std::size_t i = 0; i < setup.connections.size(); ++i) {
            const Connection &connection = setup.connections[i];
            if (!Formula::is_input_name(connection.port)) {
                return graph_error(std::format("block '{}': '{}' is not a name a formula can give an input", setup.id,
                                               connection.port));
            }
            inputs_.push_back(InputPort{std::string(connection.port), std::nullopt, true, false});
            if (!connection.constant) {
                ++signals;
                sample_ = i;  // of use only where it is the one signal
            }
            if (named && connection.port == sample_of) {
                if (connection.constant) {
                    return graph_error(std::format(
                        "block '{}': sample_of names '{}', which is a constant and not a signal", setup.id, sample_of));
                }
                named_place = i;
            }
        }
        if (named && !named_place.has_value()) {
            return graph_error(
                std::format("block '{}': sample_of names '{}', which is not one of its inputs", setup.id, sample_of));
        }
        if (named) {
            sample_ = named_place;
        } else if (signals != 1) {
            sample_.reset();  // rule 3.7: the time of the tick
        }

        std::string problem;
        if (!formula_.parse(text, problem)) {
            return graph_error(std::format("block '{}': formula '{}': {}", setup.id, text, problem));
        }
        std::vector<std::size_t> places;
        std::vector<bool> used(inputs_.size(), false);
        for (const std::string &name : formula_.names()) {
            std::size_t place = inputs_.size();
            for (std::size_t i = 0; i < inputs_.size(); ++i) {
                if (inputs_[i].name == name) {
                    place = i;
                }
            }
            if (place == inputs_.size()) {
                return graph_error(std::format("block '{}': formula '{}' uses '{}', which is not one of its inputs",
                                               setup.id, text, name));
            }
            used[place] = true;
            places.push_back(place);
        }
        for (std::size_t i = 0; i < inputs_.size(); ++i) {
            if (!used[i]) {
                return graph_error(std::format("block '{}': formula '{}' does not use its input '{}'", setup.id, text,
                                               inputs_[i].name));
            }
        }
        formula_.connect(places);
        id_ = setup.id;
        text_ = text;
        outputs_.push_back(OutputPort{"y", std::nullopt, true});
        return {};
    }

    Status bind(std::span<const std::optional<Type>> input_types) override {
        std::string problem;
        if (!formula_.type(input_types, outputs_[0].type, problem)) {
            return graph_error(std::format("block '{}': formula '{}': {}", id_, text_, problem));
        }
        return {};
    }

    bool used(std::size_t input) const override { return formula_.used(input); }

    void give(const Tick &tick, std::span<const Value> in, std::span<Value> out) override {
        Value y = formula_.evaluate(in);
        if (y.is_usable()) {  // rule 3.7
            if (sample_.has_value()) {
                y.timed = in[*sample_].timed;
                y.time = in[*sample_].time;
            } else {
                y.timed = true;
                y.time = tick.time;
            }
        }
        out[0] = y;
    }

private:
    Formula formula_;
    std::string id_;
    std::string text_;
    std::optional<std::size_t> sample_;  // the input whose sample time `y` carries, if it carries one
};

class AllGoodBlock : public StatelessBlock {
public:
    Status configure(const BlockSetup &setup) {
        SettingsReader settings(setup);
        if (Status status = settings.finish(); !status) {
            return status;
        }
        if (setup.connections.empty()) {
            return graph_error(std::format("block '{}': all_good takes one or more inputs", setup.id));
        }
        for (const Connection &connection : setup.connections) {
            inputs_.push_back(InputPort{std::string(connection.port), std::nullopt, true, false});
        }
        outputs_.push_back(OutputPort{"y", Type::boolean, false});
        return {};
    }

    Status bind(std::span<const std::optional<Type>> /*input_types*/) override { return {}; }

    void give(const Tick & /*tick*/, std::span<const Value> in, std::span<Value> out) override {
        bool all = true;
        for (const Value &value : in) {
            all = all && value.state == State::good;
        }
        out[0] = Value::of(all);  // it reads states and not values, and is always good (rule D)
    }
};

}  // namespace

Result<std::unique_ptr<Block>> make_formula(const BlockSetup &setup) { return make_block<FormulaBlock>(setup); }
Result<std::unique_ptr<Block>> make_all_good(const BlockSetup &setup) { return make_block<AllGoodBlock>(setup); }

}  // namespace fluxgraph::v2::detail

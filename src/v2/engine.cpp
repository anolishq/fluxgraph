// The engine: time and the host (section 6), inputs from outside (section 7.2), the two phases of a tick
// (rule 4.4), and reset, save, restore and gaps (section 8).
//
// Times are 64 bits wide, signed, and the host may pass any of them, so no sum, difference or product of times
// here is taken for granted. Each is one of: a comparison, which cannot wrap; a difference of two times known to
// be in order, taken unsigned by span_between(), where it always fits; or a sum checked by add_span(). Where one
// rests on something shown earlier, the comment beside it says what.

#include "fluxgraph/v2/engine.hpp"

#include <algorithm>
#include <cmath>
#include <format>
#include <map>
#include <string>

#include "exact.hpp"
#include "fluxgraph/v2/block.hpp"
#include "program.hpp"

namespace fluxgraph::v2 {

namespace {

using detail::add_span;
using detail::after_by_more_than;
using detail::kTimeMax;
using detail::span_between;

constexpr std::uint64_t kStateMagic = 0x3376'4746'5846'4c46ULL;  // a state this engine wrote, in this layout

// A write that waits, or stands (rule 6.8).
struct Written {
    Time at = 0;
    State state = State::not_ready;
    bool boolean = false;
    double number = 0.0;
};

struct InputState {
    bool stands = false;
    Written standing;
    std::vector<Written> waiting;  // in the order they were written
};

// What is kept of a loop that holds a model block (rule 7.8.8): its doubt, the latest tick at which a block in it
// used a value that was not good, read from outside the loop, or gave an output that was not usable to the loop.
struct LoopState {
    bool doubted = false;
    std::int64_t doubt = 0;
};

// A rebase the host has asked for and no call has yet followed (rule 8.5).
struct PendingRebase {
    bool active = false;
    bool known = false;     // the host said how long the graph was away
    std::uint64_t due = 0;  // the ticks that would have been due in that time, where known
};

}  // namespace

struct Engine::Impl {
    detail::Program program;
    std::map<std::string, std::size_t, std::less<>> input_index;
    std::vector<InputState> inputs;
    std::vector<Value> slots;  // every signal as it is at the tick being run
    std::vector<Value> in;     // room for one block's inputs and outputs
    std::vector<Value> out;
    std::vector<bool> gave_unusable;  // for each slot: what its block gave at this tick, before any fallback
    std::vector<LoopState> loops;
    std::vector<bool> settling;  // for each loop: within `settle` of its doubt at the tick being run
    std::vector<Output> outputs;

    std::uint64_t thrown = 0;  // since the last call that ran a tick
    bool has_last_now = false;
    Time last_now = 0;
    std::int64_t last_tick = -1;  // the number of the last tick run, or -1 before any
    // Tick `anchor_tick` is at `anchor_time`, and the ticks after it at whole periods from that: tick 0 as the
    // first call gave it, or the tick of the last rebase (rule 6.5).
    std::int64_t anchor_tick = 0;
    Time anchor_time = 0;
    bool initial_stands_in = true;  // no rebase since the engine was made or last reset (rule 7.2.1)
    PendingRebase rebase;

    Status write(std::string_view input, State state, const Value *value, Time at);
    void forget_writes();
    void run_tick(std::int64_t number, Time time, Time limit);
    Value read_input(const detail::InputSpec &spec, const InputState &state, Time time) const;
    void save(StateWriter &writer) const;
    bool load(StateReader &reader);
};

// ---- writes (rules 6.7, 6.8 and 6.11)

Status Engine::Impl::write(std::string_view input, State state, const Value *value, Time at) {
    const auto found = input_index.find(input);
    if (found == input_index.end()) {
        return Error{Errc::write_refused, std::format("'{}' is not an input of the graph", input)};
    }
    const detail::InputSpec &spec = program.inputs[found->second];
    if (static_cast<unsigned>(state) > static_cast<unsigned>(State::good)) {
        return Error{Errc::write_refused, std::format("input '{}': a write has one of the four states", input)};
    }
    Written written;
    written.at = at;
    written.state = state;
    if (usable(state)) {
        if (value == nullptr) {
            return Error{Errc::write_refused,
                         std::format("input '{}': a {} write has to have a value", input, name_of(state))};
        }
        if (value->type != spec.type) {
            return Error{Errc::write_refused, std::format("input '{}' is a {}, and the write is of a {}", input,
                                                          name_of(spec.type), name_of(value->type))};
        }
        written.boolean = value->boolean;
        written.number = value->number;
    }
    InputState &held = inputs[found->second];
    if (held.stands && at < held.standing.at) {
        ++thrown;  // it can never stand, and is thrown away as it is made
        return {};
    }
    held.waiting.push_back(written);
    if (held.waiting.size() > program.max_waiting) {
        // The earliest goes, and of two with one time the earlier written: min_element gives the first of equals.
        held.waiting.erase(std::min_element(held.waiting.begin(), held.waiting.end(),
                                            [](const Written &a, const Written &b) { return a.at < b.at; }));
        ++thrown;
    }
    return {};
}

// Nothing stands, and nothing waits; none of it counts as thrown away (rules 8.1 and 8.5).
void Engine::Impl::forget_writes() {
    for (InputState &held : inputs) {
        held.stands = false;
        held.waiting.clear();
    }
}

// ---- one tick

// Section 7.2: what an input is at a tick whose time is `time`.
Value Engine::Impl::read_input(const detail::InputSpec &spec, const InputState &held, Time time) const {
    Value value = Value::none(State::not_ready, spec.type);
    if (!held.stands) {
        // The graph has run since tick 0 or the last rebase's tick, whose time is the anchor's: a tick is never
        // before the anchor, so the difference is in order.
        const std::uint64_t run = span_between(anchor_time, time);
        const bool too_long = spec.has_max_age && run > static_cast<std::uint64_t>(spec.max_age);
        if (spec.has_initial && !too_long && initial_stands_in) {
            value = spec.initial;  // no sample time: it is not a sample of anything
            value.state = State::uncertain;
        } else if (too_long) {
            value.state = State::bad;
        }
        return value;
    }
    const Written &standing = held.standing;
    if (!usable(standing.state)) {
        value.state = standing.state;
        return value;
    }
    if (spec.type == Type::number && !std::isfinite(standing.number)) {
        value.state = State::bad;
        return value;
    }
    // Its age is the tick's time less its own, however far apart they are, and below zero for a sample stamped
    // after the tick, which is not more than any maximum.
    if (spec.has_max_age && after_by_more_than(time, standing.at, spec.max_age)) {
        value.state = State::bad;
        return value;
    }
    value.state = standing.state;
    value.boolean = standing.boolean;
    value.number = standing.number;
    value.timed = true;
    value.time = standing.at;
    return value;
}

// Runs tick `number`, whose time is `time`. It may see a write whose time is not after `limit` (rule 6.8).
void Engine::Impl::run_tick(std::int64_t number, Time time, Time limit) {
    for (std::size_t i = 0; i < inputs.size(); ++i) {
        InputState &held = inputs[i];
        std::size_t kept = 0;
        for (const Written &written : held.waiting) {
            if (written.at > limit) {
                held.waiting[kept++] = written;
            } else if (!held.stands || written.at >= held.standing.at) {
                // The latest time stands, and of two with one time the one written later.
                held.standing = written;
                held.stands = true;
            }
        }
        held.waiting.resize(kept);
        slots[i] = read_input(program.inputs[i], held, time);
    }

    // Rule 7.8.8: a loop is judged at a tick by its latest doubt before it. Where it is not within `settle` of
    // that, what its delays, windows and low-passes took in as uncertain at an earlier tick becomes good.
    for (std::size_t i = 0; i < loops.size(); ++i) {
        const detail::LoopSpec &loop = program.loops[i];
        settling[i] = loops[i].doubted && span_between(loops[i].doubt, number) <= loop.settle;  // doubt < number
        if (!settling[i]) {
            for (std::size_t member : loop.blocks) {
                program.blocks[member].block->loop_settled();
            }
        }
    }

    Tick tick{number, time};
    const auto gather = [this](const detail::BlockSpec &spec, bool second_phase) {
        for (std::size_t port = 0; port < spec.sources.size(); ++port) {
            const detail::Source &source = spec.sources[port];
            if (source.kind == detail::Source::Kind::constant) {
                in[port] = source.constant;
            } else if (source.kind == detail::Source::Kind::signal && (second_phase || !source.deferred)) {
                in[port] = slots[source.slot];
            } else {
                in[port] = Value{};
            }
        }
    };
    // The first phase: every block gives its outputs, in the one order.
    for (detail::BlockSpec &spec : program.blocks) {
        gather(spec, false);
        const std::size_t count = spec.outputs.size();
        std::fill_n(out.begin(), count, Value{});
        tick.on_model_loop = spec.loop >= 0;
        tick.loop_settling = spec.loop >= 0 && settling[static_cast<std::size_t>(spec.loop)];
        spec.block->give(tick, std::span<const Value>(in.data(), spec.sources.size()),
                         std::span<Value>(out.data(), count));
        for (std::size_t port = 0; port < count; ++port) {
            const detail::OutputSpec &output = spec.outputs[port];
            Value value = out[port];
            value.type = output.type;
            if (value.is_usable() && output.type == Type::number && !std::isfinite(value.number)) {
                value.state = State::bad;  // rule 3.6, whatever the block
            }
            gave_unusable[spec.first_slot + port] = !value.is_usable();
            if (!value.is_usable()) {
                if (output.has_fallback) {
                    value = output.fallback;  // section 7.10: uncertain, and no sample time
                } else {
                    value = Value::none(value.state, output.type);
                }
            } else if (!output.own_sample_time) {
                value.timed = true;  // rule 3.7: the time of the tick
                value.time = time;
            }
            slots[spec.first_slot + port] = value;
        }
    }
    // Rule 7.8.8: what starts a loop's doubt at this tick. It is seen from the next tick.
    for (std::size_t i = 0; i < loops.size(); ++i) {
        const detail::LoopSpec &loop = program.loops[i];
        // An output that was not usable, on a port a block of the loop is connected to, fallback or not.
        bool doubt = false;
        for (std::size_t slot : loop.watched) {
            doubt = doubt || gave_unusable[slot];
        }
        // A value that was not good, read from outside the loop and used.
        for (std::size_t member : loop.blocks) {
            const detail::BlockSpec &spec = program.blocks[member];
            for (std::size_t port = 0; port < spec.sources.size() && !doubt; ++port) {
                const detail::Source &source = spec.sources[port];
                doubt = source.outside_loop && slots[source.slot].state != State::good && spec.block->used(port);
            }
        }
        if (doubt) {
            loops[i] = LoopState{true, number};
        }
    }
    // The second phase: every block updates its state.
    for (detail::BlockSpec &spec : program.blocks) {
        gather(spec, true);
        tick.on_model_loop = spec.loop >= 0;
        tick.loop_settling = spec.loop >= 0 && settling[static_cast<std::size_t>(spec.loop)];
        spec.block->update(tick, std::span<const Value>(in.data(), spec.sources.size()));
    }
}

// ---- the public interface

Engine::Engine(std::unique_ptr<Impl> impl) : impl_(std::move(impl)) {}
Engine::Engine(Engine &&) noexcept = default;
Engine &Engine::operator=(Engine &&) noexcept = default;
Engine::~Engine() = default;

Result<Engine> Engine::compile(const Setting &graph) {
    Result<detail::Program> compiled = detail::compile_graph(graph);
    if (!compiled) {
        return compiled.error();
    }
    auto impl = std::make_unique<Impl>();
    impl->program = std::move(compiled.value());
    const detail::Program &program = impl->program;
    impl->inputs.resize(program.inputs.size());
    for (std::size_t i = 0; i < program.inputs.size(); ++i) {
        impl->input_index.emplace(program.inputs[i].name, i);
    }
    for (Type type : program.slot_types) {
        impl->slots.push_back(Value::none(State::not_ready, type));
    }
    std::size_t most_inputs = 0;
    std::size_t most_outputs = 0;
    for (const detail::BlockSpec &spec : program.blocks) {
        most_inputs = std::max(most_inputs, spec.sources.size());
        most_outputs = std::max(most_outputs, spec.outputs.size());
    }
    impl->gave_unusable.assign(program.slot_types.size(), false);
    impl->loops.assign(program.loops.size(), LoopState{});
    impl->settling.assign(program.loops.size(), false);
    impl->in.resize(most_inputs);
    impl->out.resize(most_outputs);
    for (const detail::Published &published : program.published) {
        impl->outputs.push_back(Output{published.name, impl->slots[published.slot]});
    }
    return Engine(std::move(impl));
}

Time Engine::period() const { return impl_->program.period; }

Status Engine::write(std::string_view input, State state, double value, Time at) {
    const Value given = Value::of(value);
    return impl_->write(input, state, &given, at);
}

Status Engine::write(std::string_view input, State state, bool value, Time at) {
    const Value given = Value::of(value);
    return impl_->write(input, state, &given, at);
}

Status Engine::write(std::string_view input, State state, Time at) { return impl_->write(input, state, nullptr, at); }

Result<TickReport> Engine::tick(Time now) {
    Impl &s = *impl_;
    if (s.has_last_now && now < s.last_now) {
        return Error{Errc::call_refused,
                     std::format("the call's time, {}, is earlier than that of the call before, {}", now, s.last_now)};
    }
    const std::uint64_t period = static_cast<std::uint64_t>(s.program.period);  // more than zero

    // What the call would run. Nothing is changed until it is known that the call is not refused.
    std::uint64_t due = 0;         // how many ticks it runs
    std::int64_t last_number = 0;  // the last of them
    Time last_time = now;
    bool gap = false;
    bool skipped_known = true;
    std::uint64_t skipped = 0;
    const bool first = s.last_tick < 0;
    const bool rebased = !first && s.rebase.active;
    if (first) {
        due = 1;  // rule 6.5: tick 0, at this `now`
    } else if (rebased) {
        // Rule 8.5: of the ticks that would have been due the last runs, and if none would the next tick does.
        const std::uint64_t advance = s.rebase.known && s.rebase.due > 1 ? s.rebase.due : 1;
        if (advance > span_between(s.last_tick, kTimeMax)) {
            return Error{Errc::call_refused,
                         "the tick this call would run has a number that does not fit in 64 bits: rebase again with "
                         "a length that does"};
        }
        // Shown just above to fit signed, so the unsigned sum read back signed is the true one.
        last_number = static_cast<std::int64_t>(static_cast<std::uint64_t>(s.last_tick) + advance);
        due = 1;
        gap = true;
        skipped_known = s.rebase.known;
        skipped = s.rebase.known ? advance - 1 : 0;
    } else if (now >= s.anchor_time) {
        // No accepted call is earlier than the one that set the anchor, so this always holds; were it not to,
        // no tick would be due.
        //
        // Rule 6.6: tick `anchor_tick + j` is due when j periods are no more than half a period past `now`,
        // that is when j <= (elapsed + period / 2) / period in true arithmetic. With elapsed = whole * period +
        // rest, the largest such j is `whole`, and one more when twice `rest` is at least a period.
        const std::uint64_t elapsed = span_between(s.anchor_time, now);
        const std::uint64_t whole = elapsed / period;
        const std::uint64_t rest = elapsed % period;
        const bool half = rest >= period - rest;  // rest < period, so neither side wraps
        // `half` needs a period of 2 or more, and then `whole` is at most 2^63 - 1: the sum cannot wrap.
        const std::uint64_t reach = whole + (half ? 1 : 0);
        const std::uint64_t run = span_between(s.anchor_tick, s.last_tick);  // the last tick run is not before it
        if (reach > run) {
            if (reach > span_between(s.anchor_tick, kTimeMax)) {
                return Error{Errc::call_refused,
                             "the call would run a tick whose number does not fit in 64 bits (rule 6.11)"};
            }
            last_number = static_cast<std::int64_t>(static_cast<std::uint64_t>(s.anchor_tick) + reach);
            // Its time is the anchor's and `reach` periods. whole * period is elapsed - rest, which fits; the
            // period added for `half` may not, and the sum with the anchor may not.
            std::uint64_t offset = elapsed - rest;
            const bool offset_fits = !half || period <= UINT64_MAX - offset;
            if (half && offset_fits) {
                offset += period;
            }
            if (!offset_fits || !add_span(s.anchor_time, offset, last_time)) {
                return Error{Errc::call_refused,
                             "the call would run a tick whose time does not fit in 64 bits (rule 6.11)"};
            }
            due = reach - run;
            if (due > s.program.max_catch_up) {  // rules 6.9 and 8.4: a stall
                gap = true;
                skipped = due - 1;
                due = 1;
            }
        }
    }

    // The call is accepted.
    s.has_last_now = true;
    s.last_now = now;
    for (std::size_t i = 0; i < s.inputs.size(); ++i) {  // rule 6.8: stamped ahead
        std::vector<Written> &waiting = s.inputs[i].waiting;
        const Time max_ahead = s.program.inputs[i].max_ahead;
        const auto ahead = [&](const Written &written) { return after_by_more_than(written.at, now, max_ahead); };
        const auto kept = std::remove_if(waiting.begin(), waiting.end(), ahead);
        s.thrown += static_cast<std::uint64_t>(waiting.end() - kept);
        waiting.erase(kept, waiting.end());
    }
    TickReport report;
    if (due == 0) {
        return report;  // rule 6.6: it says so, and gives nothing else
    }
    if (first || rebased) {
        s.anchor_tick = last_number;
        s.anchor_time = now;
    }
    if (rebased) {
        s.rebase.active = false;
        s.initial_stands_in = false;
    }
    if (gap) {  // rule 8.6: before the tick runs, every block is told
        // The number of the tick that runs is at least 1: the first tick is never a gap.
        const std::int64_t first_run = static_cast<std::int64_t>(static_cast<std::uint64_t>(last_number) - (due - 1));
        const Gap told{skipped_known, skipped, rebased, first_run};
        for (detail::BlockSpec &spec : s.program.blocks) {
            spec.block->gap(told);
        }
        if (!skipped_known || skipped > 0) {
            // The tick before the one that runs is a doubt of a model block, and its loop's if it is on one.
            for (LoopState &loop : s.loops) {
                loop = LoopState{true, first_run - 1};
            }
        }
    }
    for (std::uint64_t i = 0; i < due; ++i) {
        const std::uint64_t before_last = due - 1 - i;
        // No later than the last, whose number was shown to fit, and after the last tick run.
        const std::int64_t number = static_cast<std::int64_t>(static_cast<std::uint64_t>(last_number) - before_last);
        Time time = last_time;
        if (before_last != 0) {
            // A catch-up tick: no later than the last, so both the product and the sum are within those shown
            // to fit for it.
            add_span(s.anchor_time, span_between(s.anchor_tick, number) * period, time);
        }
        // Rule 6.8: the last tick of a call sees up to the later of its own time and the call's.
        s.run_tick(number, time, before_last == 0 ? std::max(time, now) : time);
    }
    s.last_tick = last_number;
    for (std::size_t i = 0; i < s.outputs.size(); ++i) {
        s.outputs[i].value = s.slots[s.program.published[i].slot];
    }

    report.ran = static_cast<std::uint32_t>(due);  // at most max_catch_up, which is under 2^31
    report.gap = gap;
    report.skipped_known = skipped_known;
    report.skipped = static_cast<std::int64_t>(skipped);  // fewer than the ticks the last tick's number counts
    report.tick = last_number;
    report.time = last_time;
    report.thrown = s.thrown;
    s.thrown = 0;
    for (const InputState &held : s.inputs) {
        report.waiting += held.waiting.size();
    }
    return report;
}

std::span<const Output> Engine::outputs() const { return impl_->outputs; }

void Engine::rebase() {
    Impl &s = *impl_;
    s.forget_writes();
    if (s.last_tick < 0) {
        return;  // before any tick: the writes waiting are done with, and nothing else
    }
    s.rebase = PendingRebase{true, false, 0};
    s.has_last_now = false;
}

Status Engine::rebase(Time away) {
    Impl &s = *impl_;
    if (away < 0) {
        return Error{Errc::rebase_refused,
                     std::format("the length of a rebase is {}, and is not less than zero", away)};
    }
    s.forget_writes();
    if (s.last_tick < 0) {
        return {};
    }
    // Rule 8.5: the length over the period, to the nearest whole number, a half rounding up. As in tick().
    const std::uint64_t length = static_cast<std::uint64_t>(away);
    const std::uint64_t period = static_cast<std::uint64_t>(s.program.period);
    const std::uint64_t rest = length % period;
    s.rebase = PendingRebase{true, true, length / period + (rest >= period - rest ? 1 : 0)};
    s.has_last_now = false;
    return {};
}

void Engine::reset() {
    Impl &s = *impl_;
    for (detail::BlockSpec &spec : s.program.blocks) {
        spec.block->reset();
    }
    std::fill(s.loops.begin(), s.loops.end(), LoopState{});
    s.forget_writes();
    s.thrown = 0;
    s.has_last_now = false;
    s.last_tick = -1;
    s.initial_stands_in = true;
    s.rebase = PendingRebase{};
    for (std::size_t i = 0; i < s.outputs.size(); ++i) {
        s.outputs[i].value = Value::none(State::not_ready, s.program.slot_types[s.program.published[i].slot]);
    }
}

// Rule 8.2: what the blocks remember, their counters, each loop's doubt and the number of the last tick run. Not
// what stands, what waits, the clock, a rebase not yet followed by its call, or the count of writes thrown away.
void Engine::Impl::save(StateWriter &writer) const {
    writer.u64(kStateMagic);
    writer.u64(program.fingerprint);
    writer.u64(static_cast<std::uint64_t>(last_tick));
    for (const LoopState &loop : loops) {
        writer.flag(loop.doubted);
        writer.u64(static_cast<std::uint64_t>(loop.doubt));
    }
    for (const detail::BlockSpec &spec : program.blocks) {
        spec.block->save(writer);
    }
}

// Takes back what save() wrote after its first two words. False where the state is not whole, and the engine
// is then in no state to run.
bool Engine::Impl::load(StateReader &reader) {
    std::uint64_t last = 0;
    if (!reader.u64(last) ||
        (last != static_cast<std::uint64_t>(std::int64_t{-1}) && last > detail::kTimeMaxUnsigned)) {
        return false;
    }
    for (LoopState &loop : loops) {
        std::uint64_t doubt = 0;
        if (!reader.flag(loop.doubted) || !reader.u64(doubt)) {
            return false;
        }
        loop.doubt = static_cast<std::int64_t>(doubt);
    }
    for (detail::BlockSpec &spec : program.blocks) {
        if (!spec.block->restore(reader)) {
            return false;
        }
    }
    if (!reader.at_end()) {
        return false;
    }
    last_tick = static_cast<std::int64_t>(last);
    return true;
}

SavedState Engine::save() const {
    StateWriter writer;
    impl_->save(writer);
    return SavedState{std::move(writer.bytes())};
}

Status Engine::restore(const SavedState &state) {
    Impl &s = *impl_;
    StateReader reader(state.bytes);
    std::uint64_t magic = 0;
    std::uint64_t fingerprint = 0;
    if (!reader.u64(magic) || magic != kStateMagic || !reader.u64(fingerprint) ||
        fingerprint != s.program.fingerprint) {
        return Error{Errc::state_refused, "the state was not saved from this graph"};
    }
    StateWriter held;
    s.save(held);  // to put back, should the state turn out not to be whole
    if (!s.load(reader)) {
        StateReader back(held.bytes());
        std::uint64_t unused = 0;
        back.u64(unused);
        back.u64(unused);
        s.load(back);
        return Error{Errc::state_refused, "the state is not one this engine wrote"};
    }
    if (s.last_tick < 0) {
        reset();  // rule 8.3: restoring a state saved before any tick had run is a reset
        return {};
    }
    s.forget_writes();
    s.rebase = PendingRebase{true, false, 0};  // rule 8.5: a restore puts back "nobody knows"
    s.has_last_now = false;
    return {};
}

}  // namespace fluxgraph::v2

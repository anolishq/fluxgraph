#pragma once

// A block that remembers: what it is configured as is apart from what it remembers, and the two phases of a tick
// (rule 4.4) are kept apart by what each is allowed to change.
//
// A block's memory is one struct, `Memory`. The block says once which of its fields a saved state holds
// (`describe`), and reset, save and restore follow from that. Every function a block writes for a tick is const:
// what it is configured as cannot change once the graph is compiled, and what it remembers reaches it as an
// argument, read-only wherever the phase may not change it.

#include <cstdint>
#include <span>

#include "blocks.hpp"

namespace fluxgraph::v2::detail {

/// The fields of a block's memory that a saved state holds, in order. Made over a writer it saves each field it
/// is given, and over a reader it reads each one back.
class Fields {
public:
    explicit Fields(StateWriter &writer) : writer_(&writer) {}
    explicit Fields(StateReader &reader) : reader_(&reader) {}

    void operator()(bool &field) {
        if (writer_ != nullptr) {
            writer_->flag(field);
        } else {
            ok_ = ok_ && reader_->flag(field);
        }
    }
    void operator()(double &field) {
        if (writer_ != nullptr) {
            writer_->f64(field);
        } else {
            ok_ = ok_ && reader_->f64(field);
        }
    }
    void operator()(std::uint64_t &field) {
        if (writer_ != nullptr) {
            writer_->u64(field);
        } else {
            ok_ = ok_ && reader_->u64(field);
        }
    }
    void operator()(std::int64_t &field) {
        std::uint64_t bits = static_cast<std::uint64_t>(field);
        (*this)(bits);
        field = static_cast<std::int64_t>(bits);
    }
    void operator()(Counters &field) {
        (*this)(field.elapsed);
        (*this)(field.doubtful);
        (*this)(field.gaps);
    }

    /// False once a field could not be read back.
    bool ok() const { return ok_; }

private:
    StateWriter *writer_ = nullptr;
    StateReader *reader_ = nullptr;
    bool ok_ = true;
};

/// A block that works out what it will remember in the first phase and takes it up in the second.
///
/// `step` is the first phase. It is given what the block remembers, which it cannot change, and a copy of it to
/// leave as the tick leaves it. The copy becomes what the block remembers in the second phase, after `take`, which
/// is for a block that has to see a deferred input before it does.
template <typename Memory>
class Committing : public Block {
public:
    void give(const Tick &tick, std::span<const Value> in, std::span<Value> out) final {
        next_ = now_;
        step(tick, in, out, now_, next_);
    }

    void update(const Tick &tick, std::span<const Value> in) final {
        take(tick, in, now_, next_);
        now_ = next_;
    }

    void gap(const Gap &gap) final { pass_over(gap, now_); }
    void loop_settled() final { settle(now_); }
    void reset() final { now_ = start(); }

    void save(StateWriter &writer) const final {
        Memory held = now_;
        Fields fields(writer);
        describe(fields, held);
    }

    bool restore(StateReader &reader) final {
        Memory read = start();  // a field a saved state does not hold is as the block was made
        Fields fields(reader);
        describe(fields, read);
        if (!fields.ok()) {
            return false;
        }
        now_ = read;
        return true;
    }

protected:
    /// The first phase (see Block::give): the outputs, and `next`, which starts as a copy of `now`.
    virtual void step(const Tick &tick, std::span<const Value> in, std::span<Value> out, const Memory &now,
                      Memory &next) const = 0;
    /// The second phase, for a block that reads a deferred input: what `step` left in `next` may be changed.
    virtual void take(const Tick & /*tick*/, std::span<const Value> /*in*/, const Memory & /*now*/,
                      Memory & /*next*/) const {}
    /// Before the tick a gap runs (see Block::gap).
    virtual void pass_over(const Gap &gap, Memory &now) const = 0;
    /// See Block::loop_settled.
    virtual void settle(Memory & /*now*/) const {}
    /// What the block remembers as it is made, and after a reset.
    virtual Memory start() const { return Memory{}; }
    /// Gives `fields` each field of `memory` that a saved state holds, in the order it holds them.
    virtual void describe(Fields &fields, Memory &memory) const = 0;

private:
    Memory now_{};   // as the last tick left it
    Memory next_{};  // as this tick leaves it, from the first phase until the second takes it
};

}  // namespace fluxgraph::v2::detail

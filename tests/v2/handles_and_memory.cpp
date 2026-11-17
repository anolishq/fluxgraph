// What include/fluxgraph/v2/engine.hpp says of input handles and of memory, checked against the core.
//
// Every allocation in the process is counted, by replacing the global operator new. The program prints one line
// for each thing it checks and returns 1 if any does not hold.

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <new>
#include <string>
#include <string_view>

#include "fluxgraph/v2/engine.hpp"

namespace {

std::uint64_t allocations = 0;  // NOLINT(cppcoreguidelines-avoid-non-const-global-variables)

}  // namespace

// NOLINTBEGIN(cppcoreguidelines-no-malloc,cppcoreguidelines-owning-memory)
void *operator new(std::size_t size) {
    ++allocations;
    if (void *memory = std::malloc(size != 0 ? size : 1)) {
        return memory;
    }
    std::abort();  // the core does nothing about memory that cannot be had, and neither does this
}

void operator delete(void *memory) noexcept { std::free(memory); }
void operator delete(void *memory, std::size_t /*size*/) noexcept { std::free(memory); }
// NOLINTEND(cppcoreguidelines-no-malloc,cppcoreguidelines-owning-memory)

namespace {

using fluxgraph::v2::Engine;
using fluxgraph::v2::Errc;
using fluxgraph::v2::InputHandle;
using fluxgraph::v2::Result;
using fluxgraph::v2::Setting;
using fluxgraph::v2::State;
using fluxgraph::v2::Status;
using fluxgraph::v2::Time;

constexpr Time kSecond = 1'000'000'000;
constexpr std::uint64_t kRoom = 1024;  // the writes an input has room for from the start, as engine.hpp says

bool all_held = true;  // NOLINT(cppcoreguidelines-avoid-non-const-global-variables)

void check(bool holds, std::string_view what) {
    std::cout << (holds ? "holds  " : "FAILS  ") << what << '\n';
    all_held = all_held && holds;
}

// A low-pass and a total of one input, with `max_waiting` as given, or the graph's own where it is zero.
Setting graph(std::int64_t max_waiting, std::string_view tau) {
    Setting lowpass;
    lowpass.set("id", Setting::text("f"))
        .set("type", Setting::text("lowpass"))
        .set("in", Setting::map().set("x", Setting::text("x")))
        .set("settings", Setting::map().set("tau", Setting::text(std::string(tau))))
        .set("out", Setting::map().set("y", Setting::text("y")));
    Setting total;
    total.set("id", Setting::text("i"))
        .set("type", Setting::text("integrate"))
        .set("in", Setting::map().set("x", Setting::text("x")))
        .set("out", Setting::map().set("y", Setting::text("total")));
    Setting made;
    made.set("period", Setting::text("1s"));
    if (max_waiting != 0) {
        made.set("max_waiting", Setting::whole(max_waiting));
    }
    made.set("inputs", Setting::map().set("x", Setting::map().set("max_age", Setting::text("none"))))
        .set("blocks", Setting::list().add(std::move(lowpass)).add(std::move(total)));
    return made;
}

bool refused_as_a_write(const Status &status) { return !status && status.error().code == Errc::write_refused; }

void handles() {
    Result<Engine> first = Engine::compile(graph(0, "3s"));
    Result<Engine> twin = Engine::compile(graph(0, "3s"));
    Result<Engine> other = Engine::compile(graph(0, "4s"));
    if (!first || !twin || !other) {
        check(false, "the graphs compile");
        return;
    }
    const Result<InputHandle> x = first->input("x");
    check(x.ok(), "an input's name gives a handle");
    const Result<InputHandle> none = first->input("nope");
    check(!none && none.error().code == Errc::write_refused, "a name that is not an input gives none");
    if (!x) {
        return;
    }
    check(first->write(x.value(), State::good, 2.0, 0).ok(), "a write by handle is taken");
    check(twin->write(x.value(), State::good, 2.0, 0).ok(), "and by an engine of the same graph");
    check(refused_as_a_write(other->write(x.value(), State::good, 2.0, 0)), "and refused by one of another graph");
    check(refused_as_a_write(first->write(InputHandle(), State::good, 2.0, 0)), "a handle nobody gave is refused");
    check(refused_as_a_write(first->write(x.value(), State::good, true, 0)), "a value of the wrong type is refused");
    check(refused_as_a_write(first->write(x.value(), State::good, 0)), "a usable write with no value is refused");
    check(first->write(x.value(), State::bad, kSecond).ok(), "a write with no value and no usable state is taken");
}

void memory() {
    Result<Engine> made = Engine::compile(graph(0, "3s"));
    if (!made) {
        check(false, "the graph compiles");
        return;
    }
    Engine &engine = made.value();
    const InputHandle x = engine.input("x").value();

    std::uint64_t before = allocations;
    bool taken = true;
    for (std::int64_t k = 0; k < 2000; ++k) {
        taken = engine.write(x, State::good, static_cast<double>(k), k * kSecond).ok() && taken;
        taken = engine.tick(k * kSecond).ok() && taken;
    }
    check(taken, "2,000 writes by handle and 2,000 calls are taken");
    check(allocations == before, "and allocate nothing");

    before = allocations;
    taken = true;
    for (std::int64_t k = 2000; k < 4000; ++k) {
        taken = engine.write("x", State::good, static_cast<double>(k), k * kSecond).ok() && taken;
        taken = engine.tick(k * kSecond).ok() && taken;
    }
    check(taken && allocations == before, "nor do 2,000 writes by name, each with its call");

    // No call between them: the writes wait, and past `max_waiting` the earliest is thrown away at each.
    before = allocations;
    taken = true;
    for (std::uint64_t k = 0; k < 2 * kRoom; ++k) {
        taken = engine.write(x, State::good, 1.0, 5000 * kSecond + static_cast<Time>(k)).ok() && taken;
    }
    check(taken && allocations == before, "nor do 2,048 writes with no call between them");

    // Where the graph lets more wait than there is room for from the start, the room is what is promised.
    Result<Engine> wide = Engine::compile(graph(4096, "3s"));
    if (!wide) {
        check(false, "a graph with a max_waiting of 4096 compiles");
        return;
    }
    const InputHandle wide_x = wide->input("x").value();
    before = allocations;
    for (std::uint64_t k = 0; k < kRoom; ++k) {
        taken = wide->write(wide_x, State::good, 1.0, static_cast<Time>(k)).ok() && taken;
    }
    check(taken && allocations == before, "with a max_waiting of 4096, the first 1,024 waiting allocate nothing");
}

}  // namespace

int main() {
    handles();
    memory();
    std::cout << (all_held ? "ALL HOLD" : "SOMETHING FAILS") << '\n';
    return all_held ? 0 : 1;
}

#!/usr/bin/env python3
"""Run the reference and the second implementation side by side on random inputs.

The vectors pin down the cases someone thought of. This looks for the ones
nobody did. Each graph below is run at periods of 1 s and 100 ms, with the
host's clock starting near 100 s and near 1.7e9 s: ten seeded runs of 250
calls at each. Before a call each input is written once, several times or
not at all, in any of the four states, finite or not, with a time that is
the call's, earlier, or ahead, and sometimes a time it has carried before.
Calls come on time, early, late, twice, after a stall of several periods,
and after one long enough to be a gap. Among the calls the engines are
saved, restored, rebased and reset, and after a restore or a rebase the
clock may start again from a low value. What is compared after every call:
how many ticks it ran, what it says of itself, and the state and value of
every published output.

  python3 conformance/compare.py

Exits 1 on any difference. Stdlib only.

This is a comparison of two readings, and a fault they share passes it.
"""

from __future__ import annotations

import math
import random
import sys

import reference
from second import adapter as second

NUM, BOOL = "number", "boolean"


def graphs(d, tau):
    """d(n): the length of n periods, as the graph file writes it. tau(x): x periods, likewise."""

    def formula(bid, expr, ins, out=None, **more):
        spec = {"id": bid, "type": "formula", "in": ins, "settings": {"expr": expr, **more}}
        if out:
            spec["out"] = {"y": out}
        return spec

    def block(kind, ins, out, bid=None, **settings):
        spec = {"id": bid or kind, "type": kind, "in": ins, "out": out}
        if settings:
            spec["settings"] = settings
        return spec

    plant = {"A": [[0.5, 0.1], [0.0, 0.8]], "B": [0.5, 0.2], "C": [1.0, 0.0]}
    thermal = {"thermal_mass": 4.0 * float(tau(1)[:-2]) / 1000.0, "heat_transfer": 1.0, "initial": 3.0}
    return {
        "formula arithmetic": (
            {"a": NUM, "b": NUM},
            [formula("f", "(a + b) * 2 - a / b + pow(a, 2)", {"a": "a", "b": "b"}, "y")],
        ),
        "formula functions": (
            {"a": NUM, "b": NUM},
            [formula("f", "sqrt(a) + ln(b) + exp(a / 4) + min(a, b) - max(a, abs(b))", {"a": "a", "b": "b"}, "y")],
        ),
        "formula logic": (
            {"p": BOOL, "q": BOOL, "r": BOOL},
            [
                formula("f", "(p or q) and not r", {"p": "p", "q": "q", "r": "r"}, "y"),
                formula("g", "p and q or r == p", {"p": "p", "q": "q", "r": "r"}, "z"),
            ],
        ),
        "formula choice": (
            {"p": BOOL, "a": NUM, "b": NUM},
            [formula("f", "when(p and a > 0, max(a, b), -b)", {"p": "p", "a": "a", "b": "b"}, "y")],
        ),
        "all_good": ({"a": NUM, "p": BOOL}, [block("all_good", {"a": "a", "p": "p"}, {"y": "y"})]),
        "delay": (
            {"a": NUM, "p": BOOL},
            [
                {
                    "id": "d",
                    "type": "delay",
                    "in": {"x": "a"},
                    "settings": {"ticks": 3, "initial": 7},
                    "out": {"y": "y"},
                },
                {"id": "e", "type": "delay", "in": {"x": "p"}, "out": {"y": "z"}},
            ],
        ),
        "window, every sample required": (
            {"a": NUM},
            [
                block(
                    "window",
                    {"x": "a"},
                    {
                        "mean": "mean",
                        "median": "median",
                        "min": "lo",
                        "max": "hi",
                        "spread": "sp",
                        "slope": "sl",
                        "count": "n",
                    },
                    window=d(5),
                )
            ],
        ),
        "window, half required": (
            {"a": NUM},
            [
                block(
                    "window",
                    {"x": "a"},
                    {"mean": "mean", "median": "median", "slope": "sl", "count": "n"},
                    window=d(6),
                    min_good=0.5,
                )
            ],
        ),
        "window, new samples only": (
            {"a": NUM},
            [
                block(
                    "window",
                    {"x": "a"},
                    {"mean": "mean", "slope": "sl", "count": "n"},
                    window=d(6),
                    min_good=0.3,
                    only_new=True,
                )
            ],
        ),
        "sample times through a formula and a delay": (
            {"a": NUM, "b": NUM},
            [
                formula("f", "a - b", {"a": "a", "b": "b"}, sample_of="a"),
                {"id": "d", "type": "delay", "in": {"x": "f.y"}, "settings": {"ticks": 2}},
                block("window", {"x": "d.y"}, {"mean": "mean", "count": "n"}, window=d(5), min_good=0.2, only_new=True),
            ],
        ),
        "a formula of two signals, with no sample_of": (
            {"a": NUM, "b": NUM},
            [
                formula("f", "a - b", {"a": "a", "b": "b"}),
                block("window", {"x": "f.y"}, {"count": "n"}, window=d(5), min_good=0.2, only_new=True),
            ],
        ),
        "a model that overflows": (
            {"a": NUM},
            [block("state_space", {"u": "a"}, {"y": "y"}, A=[[1e200]], B=[1e200], C=[1.0])],
        ),
        "deadband": ({"a": NUM}, [block("deadband", {"x": "a"}, {"y": "y"}, step=1.5, ride_through=d(2))]),
        "lowpass": (
            {"a": NUM},
            [
                block("lowpass", {"x": "a"}, {"y": "y"}, tau=tau(2.5), ride_through=d(1)),
                block("lowpass", {"x": "lowpass.y"}, {"y": "z"}, bid="again", tau=tau(1.5), settle=d(4)),
            ],
        ),
        "hysteresis": (
            {"a": NUM},
            [
                block("hysteresis", {"x": "a"}, {"y": "y"}, rise=2, fall=-1),
                block("hysteresis", {"x": "a"}, {"y": "z"}, bid="started", rise=2, fall=-1, initial=True),
            ],
        ),
        "held_for, reset": ({"p": BOOL}, [block("held_for", {"x": "p"}, {"y": "y"}, time=d(3), on_bad="reset")]),
        "held_for, hold": (
            {"p": BOOL},
            [block("held_for", {"x": "p"}, {"y": "y"}, time=d(3), on_bad="hold", hold_limit=d(2))],
        ),
        "since_true, assume_false": (
            {"p": BOOL},
            [block("since_true", {"x": "p"}, {"y": "y"}, time=d(4), on_bad="assume_false")],
        ),
        "since_true, unknown": (
            {"p": BOOL},
            [block("since_true", {"x": "p"}, {"y": "y"}, time=d(4), on_bad="unknown")],
        ),
        "latch": (
            {"p": BOOL, "q": BOOL},
            [
                block("latch", {"set": "p", "reset": "q"}, {"y": "y"}),
                block("latch", {"set": "p"}, {"y": "z"}, bid="once"),
            ],
        ),
        "integrate": (
            {"a": NUM, "p": BOOL},
            [
                block("integrate", {"x": "a", "reset": "p"}, {"y": "y", "missed": "missed"}, per="1m", tolerance=0.2),
                block("integrate", {"x": "a"}, {"y": "z"}, bid="strict", max_missed=d(20)),
            ],
        ),
        "thermal mass": (
            {"a": NUM, "b": NUM},
            [
                block(
                    "thermal_mass",
                    {"power": "a", "ambient": "b"},
                    {"temp": "y"},
                    ride_through=d(1),
                    substeps=2,
                    **thermal,
                )
            ],
        ),
        "state space, input deferred": (
            {"a": NUM},
            [block("state_space", {"u": "a"}, {"y": "y"}, settle=d(4), **plant)],
        ),
        "state space, input direct": (
            {"a": NUM},
            [block("state_space", {"u": "a"}, {"y": "y"}, D=0.5, ride_through=d(2), **plant)],
        ),
        "a model in a loop with a formula": (
            {"a": NUM},
            [
                block("state_space", {"u": "e"}, {"y": "y"}, bid="plant", settle=d(3), **plant),
                formula("ctl", "0.6 * (a - y)", {"a": "a", "y": "plant.y"}, "e"),
            ],
        ),
        "two masses, each the other's ambient": (
            {"a": NUM, "b": NUM},
            [
                block("thermal_mass", {"power": "a", "ambient": "right.temp"}, {"temp": "y"}, bid="left", **thermal),
                block("thermal_mass", {"power": "b", "ambient": "left.temp"}, {"temp": "z"}, bid="right", **thermal),
            ],
        ),
        "estimator": (
            {"a": NUM, "b": NUM, "c": NUM},
            [
                block(
                    "estimator",
                    {"u": "a", "z": "b", "w": "c"},
                    {
                        "x0": "x0",
                        "sigma_x0": "s0",
                        "x1": "x1",
                        "sigma_x1": "s1",
                        "innovation_z": "iz",
                        "refused_z": "rz",
                        "since_w": "sw",
                    },
                    model={"type": "state_space", **plant},
                    q={"x0": 0.01, "x1": 0.02},
                    p0={"x0": 1.0, "x1": 2.0},
                    measure={"z": {"of": "x0", "r": 0.25}, "w": {"of": "x1", "r": 0.5}},
                    gate=3,
                    sigma_max={"x0": 0.6},
                )
            ],
        ),
        "estimator over a thermal mass": (
            {"a": NUM, "b": NUM, "c": NUM},
            [
                block(
                    "estimator",
                    {"power": "a", "ambient": "b", "z": "c"},
                    {"temp": "t", "sigma_temp": "s", "innovation_z": "iz", "since_z": "sz"},
                    model={"type": "thermal_mass", **thermal},
                    q={"temp": 0.05},
                    p0={"temp": 4.0},
                    measure={"z": {"of": "temp", "r": 1.0}},
                    use_uncertain=True,
                    substeps=2,
                )
            ],
        ),
        "a fallback read inside the graph": (
            {"a": NUM},
            [
                {"id": "w", "type": "window", "in": {"x": "a"}, "settings": {"window": d(3)}, "fallback": {"mean": -1}},
                formula("f", "m * 2", {"m": "w.mean"}, "y"),
                {
                    "id": "h",
                    "type": "hysteresis",
                    "in": {"x": "a"},
                    "settings": {"rise": 2, "fall": 0},
                    "fallback": {"y": False},
                    "out": {"y": "z"},
                },
            ],
        ),
        "a loop through a delay": (
            {"a": NUM},
            [
                {"id": "prev", "type": "delay", "in": {"x": "acc"}, "settings": {"initial": 0}},
                formula("sum", "when(a > 4, 0, p * 0.5 + a)", {"p": "prev.y", "a": "a"}, "acc"),
                {"id": "db", "type": "deadband", "in": {"x": "acc"}, "settings": {"step": 0.75}, "out": {"y": "held"}},
            ],
        ),
        "a chain of detectors, declared last first": (
            {"a": NUM},
            [
                {"id": "la", "type": "latch", "in": {"set": "hf.y"}, "out": {"y": "latched"}},
                {
                    "id": "hf",
                    "type": "held_for",
                    "in": {"x": "hy.y"},
                    "settings": {"time": d(2), "on_bad": "hold", "hold_limit": d(2)},
                    "out": {"y": "held"},
                },
                {"id": "hy", "type": "hysteresis", "in": {"x": "lp.y"}, "settings": {"rise": 1, "fall": 0}},
                {"id": "lp", "type": "lowpass", "in": {"x": "a"}, "settings": {"tau": tau(3), "ride_through": d(1)}},
            ],
        ),
        "inputs with initial values": (
            {"a": NUM, "p": BOOL},
            [formula("f", "when(p, a, 0 - a)", {"p": "p", "a": "a"}, "y")],
        ),
    }


RUNS, CALLS = 10, 250
INITIAL = {"inputs with initial values": {"a": 20, "p": True}}
SECOND = 10**9


def write_random(rng, engines, last, name, kind, now, period, quiet):
    """Write the input no times, once, or a few times, each write with a state, a value and a time."""
    r = rng.random()
    if r < quiet:
        return  # not written before this call: what stands goes on standing
    for _ in range(rng.choice([1, 1, 1, 1, 2, 3])):
        r = rng.random()
        if r < 0.08 and name in last:  # the same sample, written again
            state, value, at = last[name]
        else:
            # now, a little or a lot earlier, or ahead: in tenths of a period
            at = now - period * rng.choice([0, 0, 0, 4, 10, 25, 40, -6, -15, -300]) // 10
            value = None
            if r < 0.18:
                state = "bad"
            elif r < 0.25:
                state = "not_ready"
            else:
                state = "uncertain" if rng.random() < 0.15 else "good"
                if kind == BOOL:
                    value = rng.random() < 0.6
                elif rng.random() < 0.03:
                    value = rng.choice([math.inf, math.nan, -math.inf])
                else:
                    value = rng.choice([round(rng.uniform(-5, 5), 2), float(rng.randint(-3, 6)), 0.0])
            last[name] = (state, value, at)
        for engine in engines:
            engine.write(name, state, value, at)


def same(a, b):
    if a.state != b.state:
        return False
    if a.v is None or b.v is None:
        return a.v is None and b.v is None
    if isinstance(a.v, bool) or isinstance(b.v, bool):
        return isinstance(a.v, bool) and isinstance(b.v, bool) and a.v == b.v
    return abs(a.v - b.v) <= 1e-9 * max(1.0, abs(a.v))


def main():
    total = differences = 0
    print(f"{'graph':42s} {'period':>6s} {'clock':>6s} {'compared':>9s}  differences")
    for base, origin in ((1000, 100), (100, 100), (1000, 1_700_000_000), (100, 1_700_000_000)):
        period = base * 10**6  # nanoseconds
        catalogue = graphs(lambda n, base=base: f"{n * base}ms", lambda x, base=base: f"{round(x * base)}ms")
        for index, (label, (inputs, blocks)) in enumerate(catalogue.items()):
            declared = {}
            for name, kind in inputs.items():
                declared[name] = {"type": kind, "max_age": f"{3 * base}ms" if name != "c" else "none"}
                if name in INITIAL.get(label, {}):
                    declared[name]["initial"] = INITIAL[label][name]
            graph = {"period": f"{base}ms", "max_catch_up": 20, "inputs": declared, "blocks": blocks}
            compared = found = 0
            first = None
            for run in range(RUNS):
                rng = random.Random(1000 * index + run + base + origin)
                quiet = rng.choice([0.1, 0.1, 0.5])  # how often an input is left unwritten
                engines = [reference.Engine(graph), second.Engine(graph)]
                start, tick, last_now, saved, last = origin * SECOND, 0, None, None, {}
                for call in range(CALLS):
                    op = rng.random()
                    if call and op < 0.01:
                        saved = [engine.save() for engine in engines]
                    elif saved and op < 0.02:
                        for engine, state in zip(engines, saved, strict=True):
                            engine.restore(state)
                        last_now, start = None, rng.choice([start, 5 * SECOND])  # the clock may start again
                    elif call and op < 0.03:
                        for engine in engines:
                            engine.rebase()
                        last_now, start = None, rng.choice([start, 5 * SECOND])
                    elif call and op < 0.035:
                        for engine in engines:
                            engine.reset()
                        last_now = None
                    # On time, early or late within half a period, a second call, a stall, or a gap.
                    tick += rng.choice([1, 1, 1, 1, 1, 1, 1, 1, 0, 2, 4, 30]) if call else 0
                    jitter = rng.choice([0, 0, 2, -2, 3, -3, 5]) if call else 0  # tenths of a period
                    now = start + period * tick + period * jitter // 10
                    now = now if last_now is None else max(now, last_now)
                    last_now = now
                    for name, kind in inputs.items():
                        write_random(rng, engines, last, name, kind, now, period, quiet)
                    (ran_a, a), (ran_b, b) = engines[0].tick(now), engines[1].tick(now)
                    compared += 1
                    if ran_a != ran_b or (a is None) != (b is None) or (ran_a and engines[0].info != engines[1].info):
                        found += 1
                        first = first or f"run {run} call {call} now {now}: ran {ran_a} and {ran_b}"
                        continue
                    for signal in a or {}:
                        compared += 1
                        if not same(a[signal], b[signal]):
                            found += 1
                            first = first or (
                                f"run {run} call {call} now {now} {signal}: {tuple(a[signal])[:2]}, {tuple(b[signal])}"
                            )
            total += compared
            differences += found
            print(f"{label:42s} {base / 1000:5g}s {origin:6.1e} {compared:9d}  {found}")
            if first:
                print(f"    first: {first}")
    print(f"\n{total} comparisons, {differences} differences")
    sys.exit(1 if differences else 0)


if __name__ == "__main__":
    main()

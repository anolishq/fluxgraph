#!/usr/bin/env python3
"""Run the reference and the second implementation side by side on random inputs.

The vectors pin down the cases someone thought of. This looks for the ones
nobody did: seventeen graphs, forty seeded runs of 250 ticks each, with
inputs that are written or not, good, bad, not ready, not finite, and of
various ages. Every published output is compared at every tick, by state
and by value.

  python3 conformance/compare.py

Exits 1 on any difference. Stdlib only.
"""

from __future__ import annotations

import math
import random
import sys

import reference
from second import adapter as second


def formula(expr, inputs, **more):
    return {"id": "f", "type": "formula", "in": {n: n for n in inputs}, "settings": {"expr": expr}, **more}


def gate(expr):
    """A condition on input a, read by the block under test as c.y."""
    return {"id": "c", "type": "formula", "in": {"a": "a"}, "settings": {"expr": expr}}


GRAPHS = {
    "formula arithmetic": (["a", "b"], [formula("(a + b) * 2 - a / b", "ab", out={"y": "y"})]),
    "formula logic": (["a", "b", "c"], [formula("(a > 0 or b > 0) and not (c > 0)", "abc", out={"y": "y"})]),
    "formula choice": (["a", "b", "c"], [formula("when(c > 0, max(a, b), min(a, abs(b)))", "abc", out={"y": "y"})]),
    "all_good": (["a", "b"], [{"id": "g", "type": "all_good", "in": {"a": "a", "b": "b"}, "out": {"y": "y"}}]),
    "delay of three ticks": (
        ["a"],
        [{"id": "d", "type": "delay", "in": {"x": "a"}, "settings": {"ticks": 3, "initial": 7}, "out": {"y": "y"}}],
    ),
    "window, every sample required": (
        ["a"],
        [
            {
                "id": "w",
                "type": "window",
                "in": {"x": "a"},
                "settings": {"window": "5s"},
                "out": {"mean": "mean", "median": "median", "min": "lo", "max": "hi", "spread": "sp", "slope": "sl"},
            }
        ],
    ),
    "window, half required": (
        ["a"],
        [
            {
                "id": "w",
                "type": "window",
                "in": {"x": "a"},
                "settings": {"window": "6s", "min_good": 0.5},
                "out": {"mean": "mean", "median": "median", "spread": "sp", "slope": "sl"},
            }
        ],
    ),
    "window, one sample enough": (
        ["a"],
        [
            {
                "id": "w",
                "type": "window",
                "in": {"x": "a"},
                "settings": {"window": "4s", "min_good": 0.25},
                "out": {"mean": "mean", "slope": "sl"},
            }
        ],
    ),
    "deadband with ride-through": (
        ["a"],
        [
            {
                "id": "d",
                "type": "deadband",
                "in": {"x": "a"},
                "settings": {"step": 1.5, "ride_through": "2s"},
                "out": {"y": "y"},
            }
        ],
    ),
    "held_for, reset": (
        ["a"],
        [
            gate("a > 0"),
            {
                "id": "h",
                "type": "held_for",
                "in": {"x": "c.y"},
                "settings": {"time": "3s", "on_bad": "reset"},
                "out": {"y": "y"},
            },
        ],
    ),
    "held_for, hold": (
        ["a"],
        [
            gate("a > 0"),
            {
                "id": "h",
                "type": "held_for",
                "in": {"x": "c.y"},
                "settings": {"time": "3s", "on_bad": "hold"},
                "out": {"y": "y"},
            },
        ],
    ),
    "since_true": (
        ["a"],
        [
            gate("a > 2"),
            {"id": "s", "type": "since_true", "in": {"x": "c.y"}, "settings": {"time": "4s"}, "out": {"y": "y"}},
        ],
    ),
    "latch": (["a"], [gate("a > 4"), {"id": "l", "type": "latch", "in": {"set": "c.y"}, "out": {"y": "y"}}]),
    "total": (
        ["a"],
        [
            {
                "id": "t",
                "type": "total",
                "in": {"x": "a"},
                "settings": {"per": "1m"},
                "out": {"y": "y", "missed": "missed"},
            }
        ],
    ),
    "kalman1": (
        ["a", "b"],
        [
            {
                "id": "k",
                "type": "kalman1",
                "in": {"z": "a", "model": "b"},
                "settings": {"tau": "8s", "q": 0.01, "r": 0.25},
                "out": {"x": "x", "sigma": "sigma"},
            }
        ],
    ),
    "a fallback read inside the graph": (
        ["a"],
        [
            {"id": "w", "type": "window", "in": {"x": "a"}, "settings": {"window": "3s"}, "fallback": {"mean": -1}},
            {"id": "f", "type": "formula", "in": {"m": "w.mean"}, "settings": {"expr": "m * 2"}, "out": {"y": "y"}},
        ],
    ),
    "a loop through a delay": (
        ["a"],
        [
            {"id": "prev", "type": "delay", "in": {"x": "acc"}, "settings": {"initial": 0}},
            {
                "id": "sum",
                "type": "formula",
                "in": {"p": "prev.y", "a": "a"},
                "settings": {"expr": "p * 0.5 + a"},
                "out": {"y": "acc"},
            },
            {"id": "db", "type": "deadband", "in": {"x": "acc"}, "settings": {"step": 0.75}, "out": {"y": "held"}},
        ],
    ),
}

RUNS, TICKS = 40, 250


def write_random(rng, engines, name):
    r = rng.random()
    if r < 0.12:
        return  # not written this tick: the last value stands and ages
    if r < 0.24:
        state, value, age = "bad", None, 0.0
    elif r < 0.32:
        state, value, age = "not_ready", None, 0.0
    elif r < 0.35:
        state, value, age = "good", rng.choice([math.inf, math.nan, -math.inf]), 0.0
    else:
        value = rng.choice([round(rng.uniform(-5, 5), 2), float(rng.randint(-3, 6)), 0.0])
        state, age = "good", rng.choice([0.0, 0.0, 0.0, 1.0, 2.5, 4.0])
    for engine in engines:
        engine.write(name, state, value, age)


def same(a, b):
    if a.state != b.state:
        return False
    return a.state != "good" or abs(a.v - b.v) <= 1e-9 * max(1.0, abs(a.v))


def main():
    total = differences = 0
    print(f"{'graph':34s} {'compared':>9s}  differences")
    for index, (label, (inputs, blocks)) in enumerate(GRAPHS.items()):
        graph = {"period": "1s", "inputs": {n: {"max_age": "3s"} for n in inputs}, "blocks": blocks}
        compared = found = 0
        first = None
        for run in range(RUNS):
            rng = random.Random(1000 * index + run)
            engines = [reference.Engine(graph), second.Engine(graph)]
            for tick in range(TICKS):
                for name in inputs:
                    write_random(rng, engines, name)
                a, b = engines[0].tick(), engines[1].tick()
                for signal in a:
                    compared += 1
                    if not same(a[signal], b[signal]):
                        found += 1
                        first = first or f"run {run} tick {tick} {signal}: {tuple(a[signal])} and {tuple(b[signal])}"
        total += compared
        differences += found
        print(f"{label:34s} {compared:9d}  {found}")
        if first:
            print(f"    first: {first}")
    print(f"\n{total} comparisons, {differences} differences")
    sys.exit(1 if differences else 0)


if __name__ == "__main__":
    main()

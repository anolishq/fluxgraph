#!/usr/bin/env python3
"""Run the reference and the second implementation side by side on random inputs.

The vectors pin down the cases someone thought of. This looks for the ones
nobody did. Each graph below gets forty seeded runs of 250 calls. Inputs are
written or not, in any of the four states, finite or not, sampled now,
earlier or ahead. Calls come on time, early, late, twice, or after a stall
of several periods. What is compared after every call: how many ticks it
ran, and the state and value of every published output.

  python3 conformance/compare.py

Exits 1 on any difference. Stdlib only.
"""

from __future__ import annotations

import math
import random
import sys

import reference
from second import adapter as second

NUM, BOOL = "number", "boolean"
TAU = "1.4426950408889634s"  # one period over ln 2


def block(kind, ins, out, **settings):
    spec = {"id": kind, "type": kind, "in": ins, "out": out}
    if settings:
        spec["settings"] = settings
    return spec


def formula(bid, expr, ins, out=None):
    spec = {"id": bid, "type": "formula", "in": ins, "settings": {"expr": expr}}
    if out:
        spec["out"] = {"y": out}
    return spec


GRAPHS = {
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
            {"id": "d", "type": "delay", "in": {"x": "a"}, "settings": {"ticks": 3, "initial": 7}, "out": {"y": "y"}},
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
                window="5s",
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
                window="6s",
                min_good=0.5,
            )
        ],
    ),
    "window, one sample enough": (
        {"a": NUM},
        [block("window", {"x": "a"}, {"mean": "mean", "slope": "sl"}, window="4s", min_good=0.25)],
    ),
    "deadband": ({"a": NUM}, [block("deadband", {"x": "a"}, {"y": "y"}, step=1.5, ride_through="2s")]),
    "lowpass": ({"a": NUM}, [block("lowpass", {"x": "a"}, {"y": "y"}, tau="2.5s", ride_through="1s")]),
    "hysteresis": ({"a": NUM}, [block("hysteresis", {"x": "a"}, {"y": "y"}, rise=2, fall=-1)]),
    "held_for, reset": ({"p": BOOL}, [block("held_for", {"x": "p"}, {"y": "y"}, time="3s", on_bad="reset")]),
    "held_for, hold": (
        {"p": BOOL},
        [block("held_for", {"x": "p"}, {"y": "y"}, time="3s", on_bad="hold", hold_limit="2s")],
    ),
    "since_true, assume_false": (
        {"p": BOOL},
        [block("since_true", {"x": "p"}, {"y": "y"}, time="4s", on_bad="assume_false")],
    ),
    "since_true, unknown": ({"p": BOOL}, [block("since_true", {"x": "p"}, {"y": "y"}, time="4s", on_bad="unknown")]),
    "latch": ({"p": BOOL, "q": BOOL}, [block("latch", {"set": "p", "reset": "q"}, {"y": "y"})]),
    "integrate": (
        {"a": NUM, "p": BOOL},
        [
            block("integrate", {"x": "a", "reset": "p"}, {"y": "y", "missed": "missed"}, per="1m"),
            {"id": "j", "type": "integrate", "in": {"x": "a"}, "settings": {"max_missed": "20s"}, "out": {"y": "z"}},
        ],
    ),
    "kalman1": (
        {"a": NUM, "b": NUM},
        [
            block(
                "kalman1",
                {"z": "a", "model": "b"},
                {"x": "x", "sigma": "sigma"},
                tau=TAU,
                q=0.01,
                r=0.25,
                max_coast="3s",
            )
        ],
    ),
    "kalman1 behind a delay": (
        {"a": NUM},
        [
            {"id": "d", "type": "delay", "in": {"x": "a"}, "settings": {"ticks": 2}},
            block(
                "kalman1",
                {"z": "d.y", "model": 0},
                {"x": "x", "sigma": "sigma"},
                tau=TAU,
                q=0.01,
                r=0.25,
                max_coast="3s",
            ),
        ],
    ),
    "a fallback read inside the graph": (
        {"a": NUM},
        [
            {"id": "w", "type": "window", "in": {"x": "a"}, "settings": {"window": "3s"}, "fallback": {"mean": -1}},
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
    "a chain of detectors": (
        {"a": NUM},
        [
            {"id": "lp", "type": "lowpass", "in": {"x": "a"}, "settings": {"tau": "3s", "ride_through": "1s"}},
            {"id": "hy", "type": "hysteresis", "in": {"x": "lp.y"}, "settings": {"rise": 1, "fall": 0}},
            {
                "id": "hf",
                "type": "held_for",
                "in": {"x": "hy.y"},
                "settings": {"time": "2s", "on_bad": "hold", "hold_limit": "2s"},
                "out": {"y": "held"},
            },
            {"id": "la", "type": "latch", "in": {"set": "hf.y"}, "out": {"y": "latched"}},
        ],
    ),
    "an input with an initial value": (
        {"a": NUM, "p": BOOL},
        [formula("f", "when(p, a, 0 - a)", {"p": "p", "a": "a"}, "y")],
    ),
}

RUNS, CALLS = 40, 250
INITIAL = {"an input with an initial value": {"a": 20, "p": True}}


def write_random(rng, engines, name, kind, now, quiet):
    r = rng.random()
    if r < quiet:
        return  # not written before this call: the last value stands and ages
    sampled = now - rng.choice([0.0, 0.0, 0.0, 0.4, 1.0, 2.5, 4.0, -0.6, -1.5])
    value = None
    if r < quiet + 0.1:
        state = "bad"
    elif r < quiet + 0.17:
        state = "not_ready"
    else:
        state = "uncertain" if rng.random() < 0.15 else "good"
        if kind == BOOL:
            value = rng.random() < 0.6
        elif rng.random() < 0.03:
            value = rng.choice([math.inf, math.nan, -math.inf])
        else:
            value = rng.choice([round(rng.uniform(-5, 5), 2), float(rng.randint(-3, 6)), 0.0])
    for engine in engines:
        engine.write(name, state, value, sampled)


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
    print(f"{'graph':34s} {'compared':>9s}  differences")
    for index, (label, (inputs, blocks)) in enumerate(GRAPHS.items()):
        declared = {}
        for name, kind in inputs.items():
            declared[name] = {"type": kind, "max_age": "3s"}
            if name in INITIAL.get(label, {}):
                declared[name]["initial"] = INITIAL[label][name]
        if "chain" in label:
            blocks = blocks[::-1]  # declared last block first: the order has to come from the wiring
        graph = {"period": "1s", "inputs": declared, "blocks": blocks}
        compared = found = 0
        first = None
        for run in range(RUNS):
            rng = random.Random(1000 * index + run)
            quiet = rng.choice([0.1, 0.1, 0.5])  # how often an input is left unwritten
            engines = [reference.Engine(graph), second.Engine(graph)]
            tick = 0
            for call in range(CALLS):
                # On time, early or late within half a period, a second call, or a stall.
                tick += rng.choice([1, 1, 1, 1, 1, 1, 1, 0, 2, 4]) if call else 0
                now = 100.0 + tick + (rng.choice([0.0, 0.0, 0.2, -0.2, 0.3, -0.3]) if call else 0.0)
                now = max(now, engines[0].last_now or now)
                for name, kind in inputs.items():
                    write_random(rng, engines, name, kind, now, quiet)
                (ran_a, a), (ran_b, b) = engines[0].tick(now), engines[1].tick(now)
                compared += 1
                if ran_a != ran_b or (a is None) != (b is None):
                    found += 1
                    first = first or f"run {run} call {call} now {now}: ran {ran_a} and {ran_b}"
                    continue
                for signal in a or {}:
                    compared += 1
                    if not same(a[signal], b[signal]):
                        found += 1
                        first = first or (
                            f"run {run} call {call} now {now} {signal}: {tuple(a[signal])[:2]} and {tuple(b[signal])}"
                        )
        total += compared
        differences += found
        print(f"{label:34s} {compared:9d}  {found}")
        if first:
            print(f"    first: {first}")
    print(f"\n{total} comparisons, {differences} differences")
    sys.exit(1 if differences else 0)


if __name__ == "__main__":
    main()

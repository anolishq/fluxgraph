#!/usr/bin/env python3
"""Run the reference and the second implementation side by side on random inputs.

The vectors pin down the cases someone thought of. This looks for the ones
nobody did. Each graph below is run at periods of 1 s, 100 ms and 37 ms,
with the host's clock starting near 100 s and near 1.7e9 s: ten seeded runs
of 250 calls at each. Before a call each input is written once, several times or
not at all, in any of the four states, finite or not, with a time that is
the call's, earlier, or ahead, and sometimes a time it has carried before.
Calls come on time, early, late, twice, after a stall of several periods,
and after one long enough to be a gap, at times on a grid of tenths of a
period or at any nanosecond. Some calls and some writes are ones that must
be refused. Among the calls the engines are saved, restored, rebased once
or twice and reset, and after a restore or a rebase the clock may start
again from a low value. What is compared after every call:
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
    pt = float(tau(1)[:-2]) / 1000.0  # one period, in seconds
    thermal = {"thermal_mass": 4.0 * pt, "heat_transfer": 1.0, "initial": 3.0}
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
                block(
                    "hysteresis",
                    {"x": "a"},
                    {"y": "y", "elapsed": "el", "doubtful": "db", "gaps": "gp"},
                    rise=2,
                    fall=-1,
                ),
                block("hysteresis", {"x": "a"}, {"y": "z"}, bid="started", rise=2, fall=-1, initial=True),
            ],
        ),
        "held_for, reset": (
            {"p": BOOL},
            [
                block(
                    "held_for",
                    {"x": "p"},
                    {"y": "y", "elapsed": "el", "doubtful": "db", "gaps": "gp"},
                    time=d(3),
                    on_bad="reset",
                )
            ],
        ),
        "held_for, hold": (
            {"p": BOOL},
            [
                block(
                    "held_for",
                    {"x": "p"},
                    {"y": "y", "elapsed": "el", "doubtful": "db", "gaps": "gp"},
                    time=d(3),
                    on_bad="hold",
                    hold_limit=d(2),
                )
            ],
        ),
        "since_true, assume_false": (
            {"p": BOOL},
            [
                block(
                    "since_true",
                    {"x": "p"},
                    {"y": "y", "elapsed": "el", "doubtful": "db", "gaps": "gp"},
                    time=d(4),
                    on_bad="assume_false",
                )
            ],
        ),
        "since_true, unknown": (
            {"p": BOOL},
            [
                block(
                    "since_true",
                    {"x": "p"},
                    {"y": "y", "elapsed": "el", "doubtful": "db", "gaps": "gp"},
                    time=d(4),
                    on_bad="unknown",
                )
            ],
        ),
        "latch": (
            {"p": BOOL, "q": BOOL},
            [
                block("latch", {"set": "p", "reset": "q"}, {"y": "y", "elapsed": "el", "doubtful": "db", "gaps": "gp"}),
                block("latch", {"set": "p"}, {"y": "z"}, bid="once"),
            ],
        ),
        "integrate": (
            {"a": NUM, "p": BOOL},
            [
                block(
                    "integrate",
                    {"x": "a", "reset": "p"},
                    {"y": "y", "missed": "missed", "doubtful": "db", "elapsed": "el", "gaps": "gaps"},
                    per="1m",
                ),
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
                    **thermal,
                )
            ],
        ),
        "state space, input deferred": (
            {"a": NUM},
            [
                block(
                    "state_space",
                    {"u": "a"},
                    {"y": "y", "elapsed": "el", "doubtful": "db", "gaps": "gp"},
                    settle=d(4),
                    **plant,
                )
            ],
        ),
        "state space, input direct": (
            {"a": NUM},
            [
                block(
                    "state_space",
                    {"u": "a"},
                    {"y": "y", "elapsed": "el", "doubtful": "db", "gaps": "gp"},
                    D=0.5,
                    ride_through=d(2),
                    **plant,
                )
            ],
        ),
        "a model in a loop with a formula": (
            {"a": NUM},
            [
                block("state_space", {"u": "e"}, {"y": "y"}, bid="plant", settle=d(3), **plant),
                formula("ctl", "0.6 * (a - y)", {"a": "a", "y": "plant.y"}, "e"),
            ],
        ),
        "two masses joined, as one block": (
            {"a": NUM, "b": NUM},
            [
                block(
                    "thermal_rc2",
                    {"power": "a", "ambient": "b"},
                    {"temp_a": "y", "temp_b": "z", "doubtful": "db"},
                    thermal_mass_a=thermal["thermal_mass"],
                    thermal_mass_b=2.5 * thermal["thermal_mass"],
                    heat_transfer_a=1.0,
                    heat_transfer_b=0.0,
                    coupling=3.0,
                    initial_a=3.0,
                    initial_b=-1.0,
                    ride_through=d(1),
                )
            ],
        ),
        "first and second order processes": (
            {"a": NUM},
            [
                block("first_order_process", {"u": "a"}, {"y": "y"}, tau=tau(0.3), gain=2.5, initial=1.0),
                block(
                    "second_order_process",
                    {"u": "a"},
                    {"y": "z", "rate": "zr"},
                    omega_n=2.0 / (float(tau(1)[:-2]) / 1000.0),
                    zeta=0.2,
                    gain=0.5,
                    initial_rate=1.0,
                    settle=d(4),
                ),
            ],
        ),
        "a spring, damped and not, and a motor": (
            {"a": NUM, "b": NUM},
            [
                block(
                    "mass_spring_damper",
                    {"force": "a"},
                    {"position": "x", "velocity": "v"},
                    mass=2.0,
                    damping=0.0,
                    stiffness=3.0 / (float(tau(1)[:-2]) / 1000.0) ** 2,
                    initial_position=0.5,
                ),
                block(
                    "dc_motor",
                    {"voltage": "a", "load_torque": "b"},
                    {"speed": "w", "current": "i", "torque": "tq", "gaps": "gp"},
                    resistance=2.0,
                    inductance=0.5 * float(tau(1)[:-2]) / 1000.0,
                    back_emf=0.1,
                    torque_constant=0.3,
                    inertia=0.2 * float(tau(1)[:-2]) / 1000.0,
                    friction=0.05,
                ),
            ],
        ),
        "a linear model of three states, two inputs and a direct output": (
            {"a": NUM, "b": NUM},
            [
                block(
                    "linear",
                    {"p": "a", "q": "b"},
                    {"first": "y", "mix": "z", "elapsed": "el"},
                    A=[[-0.4 / pt, 0.1 / pt, 0.0], [0.2 / pt, -0.3 / pt, 0.05 / pt], [0.0, 1.0 / pt, 0.0]],
                    B=[[1.0 / pt, 0.0], [0.0, 0.5 / pt], [0.0, 0.0]],
                    C=[[1.0, 0.0, 0.0], [0.5, -1.0, 0.25]],
                    D=[[0.0, 0.0], [0.0, 2.0]],
                    initial=[1.0, 0.0, -1.0],
                    inputs=["p", "q"],
                    outputs=["first", "mix"],
                    settle=d(3),
                    ride_through=d(2),
                )
            ],
        ),
        "a linear model that grows": (
            {"a": NUM},
            [block("linear", {"u": "a"}, {"y": "y"}, A=[[0.3 / pt]], B=[[1.0 / pt]], C=[[1.0]])],
        ),
        "a model in a loop with a delay": (
            {"a": NUM},
            [
                block("state_space", {"u": "i"}, {"y": "y"}, bid="plant", settle=d(4), **plant),
                {
                    "id": "acc",
                    "type": "delay",
                    "in": {"x": "i"},
                    "settings": {"ticks": 2, "initial": 0},
                    "out": {"y": "p"},
                },
                formula("ctl", "0.5 * p + 0.3 * (a - y)", {"p": "acc.y", "a": "a", "y": "plant.y"}, "i"),
            ],
        ),
        "a model in a loop that reads a choice": (
            {"a": NUM, "b": NUM, "p": BOOL, "q": BOOL},
            [
                block("state_space", {"u": "e"}, {"y": "y"}, bid="plant", settle=d(2), **plant),
                formula(
                    "ctl",
                    "when(p or q, 0.6 * (a - y), b)",
                    {"a": "a", "b": "b", "p": "p", "q": "q", "y": "plant.y"},
                    "e",
                ),
            ],
        ),
        "a model in a loop with a fallback and a hold": (
            {"a": NUM},
            [
                block("state_space", {"u": "held"}, {"y": "y"}, bid="plant", settle=d(3), ride_through=d(1), **plant),
                {
                    "id": "ctl",
                    "type": "formula",
                    "in": {"a": "a", "y": "plant.y"},
                    "settings": {"expr": "a / (y - 1)"},
                    "fallback": {"y": 0.5},
                    "out": {"y": "e"},
                },
                {
                    "id": "db",
                    "type": "deadband",
                    "in": {"x": "ctl.y"},
                    "settings": {"step": 0.5, "ride_through": d(2)},
                    "out": {"y": "held"},
                },
            ],
        ),
        "a model in a loop with a window and a low-pass": (
            {"a": NUM},
            [
                block("state_space", {"u": "e"}, {"y": "y", "gaps": "gp"}, bid="plant", settle=d(5), **plant),
                block("window", {"x": "plant.y"}, {"mean": "m", "slope": "sl"}, bid="w", window=d(3), min_good=0.6),
                block("lowpass", {"x": "w.mean"}, {"y": "s"}, bid="f", tau=tau(0.6), settle=d(2)),
                formula("ctl", "0.6 * (a - s) + 0 * k", {"a": "a", "s": "f.y", "k": "w.slope"}, "e"),
            ],
        ),
        "slopes of windows with few good samples": (
            {"a": NUM},
            [block("window", {"x": "a"}, {"slope": "sl", "mean": "mean"}, window=d(4), min_good=0.25)],
        ),
        "a window whose min_good rounds to nothing": (
            {"a": NUM},
            [block("window", {"x": "a"}, {"mean": "mean", "max": "hi", "count": "n"}, window=d(5), min_good=0.01)],
        ),
        "a formula of one signal into new samples only": (
            {"a": NUM},
            [
                formula("f", "a * 2", {"a": "a"}),
                block("window", {"x": "f.y"}, {"mean": "mean", "count": "n"}, window=d(4), min_good=0.5, only_new=True),
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
                        "nis_z": "nz",
                        "since_w": "sw",
                    },
                    model={
                        "type": "linear",
                        "A": [[-0.5 / pt, 0.1 / pt], [0.0, -0.2 / pt]],
                        "B": [[0.5 / pt], [0.2 / pt]],
                        "C": [[1.0, 0.0], [0.5, 1.0]],
                        "outputs": ["first", "both"],
                    },
                    q={"x0": 0.01 / pt, "x1": 0.02 / pt},
                    p0={"x0": 1.0, "x1": 2.0},
                    measure={"z": {"of": "first", "r": 0.25, "r_uncertain": 1.0}, "w": {"of": "both", "r": 0.5}},
                    consistency={"over": 4, "limit": 2.5},
                    gate=2,
                    max_refused=2,
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
                    {"temp": "t", "sigma_temp": "s", "innovation_z": "iz", "nis_z": "nz", "since_z": "sz"},
                    model={"type": "thermal_mass", **thermal},
                    q={"temp": 0.05 / pt},
                    p0={"temp": 4.0},
                    measure={"z": {"of": "temp", "r": 1.0, "r_uncertain": 3.0}},
                    consistency="none",
                )
            ],
        ),
        "an estimator over a discrete model, in a loop": (
            {"b": NUM},
            [
                block(
                    "estimator",
                    {"u": "back.y", "z": "b"},
                    {"x0": "x0", "sigma_x0": "s0", "refused_z": "rz"},
                    model={"type": "state_space", "A": [[0.9]], "B": [0.3], "C": [1.0]},
                    q={"x0": 0.05},
                    p0={"x0": 1.0},
                    measure={"z": {"of": "y", "r": 0.5}},
                    consistency={"over": 3, "limit": 3},
                    gate=2.5,
                    max_refused=0,
                ),
                formula("back", "0 - x", {"x": "estimator.x0"}),
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
        "rate limit": (
            {"a": NUM},
            [
                block("rate_limit", {"x": "a"}, {"y": "y", "limited": "l"}, up=1.5 / pt, ride_through=d(2)),
                block("rate_limit", {"x": "a"}, {"y": "z", "limited": "m"}, bid="other", up=0.0, down=40.0 / pt),
            ],
        ),
        "pid": (
            {"a": NUM, "b": NUM, "p": BOOL},
            [
                block(
                    "pid",
                    {"setpoint": "a", "measurement": "b", "reset": "p"},
                    {"y": "y", "integral": "i", "limited": "l", "elapsed": "e", "doubtful": "d", "gaps": "g"},
                    kp=1.5,
                    ki=0.7 / pt,
                    kd=0.3 * pt,
                    filter=tau(2),
                    min=-30.0,
                    max=40.0,
                ),
                block(
                    "pid",
                    {"setpoint": "a", "measurement": "b", "applied": "b"},
                    {"y": "z", "integral": "j"},
                    bid="pi",
                    kp=-0.5,
                    ki=0.2 / pt,
                ),
            ],
        ),
        "a pid on a loop with a process, through a rate limit": (
            {"a": NUM},
            [
                {
                    "id": "c",
                    "type": "pid",
                    "in": {"setpoint": "a", "measurement": "plant.y", "applied": "slew.y"},
                    "settings": {
                        "kp": 0.8,
                        "ki": 0.3 / pt,
                        "kd": 0.1 * pt,
                        "filter": tau(1),
                        "min": -50.0,
                        "max": 50.0,
                        "applied_within": 0.25,
                    },
                    "out": {"y": "u", "limited": "l", "integral": "i", "doubtful": "d"},
                    "fallback": {"y": 0.0},
                },
                block("rate_limit", {"x": "c.y"}, {"y": "v"}, bid="slew", up=20.0 / pt, ride_through=d(1), initial=0.0),
                block("first_order_process", {"u": "slew.y"}, {"y": "x"}, bid="plant", tau=tau(2), settle=d(6)),
            ],
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
            # now, a little or a lot earlier, or ahead: in tenths of a period, or at any nanosecond
            at = now - period * rng.choice([0, 0, 0, 4, 10, 25, 40, -6, -15, -300]) // 10
            if rng.random() < 0.3:
                at = now - rng.randint(-2 * period, 4 * period)
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
    for base, origin in ((1000, 100), (100, 100), (37, 100), (1000, 1_700_000_000), (100, 1_700_000_000)):
        period = base * 10**6  # nanoseconds
        catalogue = graphs(lambda n, base=base: f"{n * base}ms", lambda x, base=base: f"{round(x * base)}ms")
        for index, (label, (inputs, blocks)) in enumerate(catalogue.items()):
            declared = {}
            for name, kind in inputs.items():
                declared[name] = {"type": kind, "max_age": f"{3 * base}ms" if name != "c" else "none"}
                if name == "b":
                    declared[name]["max_ahead"] = f"{2 * base}ms"
                if name in INITIAL.get(label, {}):
                    declared[name]["initial"] = INITIAL[label][name]
            graph = {"period": f"{base}ms", "max_catch_up": 20, "max_waiting": 3, "inputs": declared, "blocks": blocks}
            compared = found = 0
            first = None
            for run in range(RUNS):
                rng = random.Random(1000 * index + run + base + origin)
                quiet = rng.choice([0.1, 0.1, 0.5])  # how often an input is left unwritten
                engines = [reference.Engine(graph), second.Engine(graph)]
                start, tick, last_now, saved, last = origin * SECOND, 0, None, None, {}
                fresh = [engine.save() for engine in engines]  # a state saved before any tick
                for call in range(CALLS):
                    op = rng.random()
                    if call and op < 0.01:
                        saved = [engine.save() for engine in engines]
                    elif saved and op < 0.02:
                        for engine, state in zip(engines, saved, strict=True):
                            engine.restore(state)
                        last_now, start = None, rng.choice([start, 5 * SECOND])  # the clock may start again
                    elif call and op < 0.03:
                        # the host may say how long it was away: under half a period, a few, or a great many
                        away = rng.choice([None, None, 0, period // 3, period * 3 // 2, period * 7, period * 400])
                        if away is not None and rng.random() < 0.3:
                            away = rng.randint(0, 9 * period)
                        for engine in engines:
                            engine.rebase(away)
                        if rng.random() < 0.3:  # written, and then a second rebase
                            for name, kind in inputs.items():
                                write_random(rng, engines, last, name, kind, start, period, 0.0)
                            away = rng.choice([None, period * 5 // 2])
                            for engine in engines:
                                engine.rebase(away)
                        last_now, start = None, rng.choice([start, 5 * SECOND])
                    elif call and op < 0.033:
                        for engine, state in zip(engines, fresh, strict=True):
                            engine.restore(state)
                        last_now = None
                    elif call and op < 0.035:
                        for engine in engines:
                            engine.reset()
                        last_now = None
                    # On time, early or late within half a period, a second call, a stall, or a gap.
                    tick += rng.choice([1, 1, 1, 1, 1, 1, 1, 1, 0, 2, 4, 30]) if call else 0
                    jitter = rng.choice([0, 0, 2, -2, 3, -3, 5]) if call else 0  # tenths of a period
                    now = start + period * tick + period * jitter // 10
                    if call and rng.random() < 0.3:  # or at any nanosecond within half a period
                        now = start + period * tick + rng.randint(-period // 2, period // 2)
                    now = now if last_now is None else max(now, last_now)
                    called, last_now = last_now, now  # the time of the call before this one
                    for name, kind in inputs.items():
                        write_random(rng, engines, last, name, kind, now, period, quiet)
                    if called is not None and rng.random() < 0.02:  # what must be refused, by both
                        compared += 1
                        refusals = 0
                        for engine in engines:
                            for attempt in (
                                lambda e=engine: e.tick(called - 1),
                                lambda e=engine: e.write(next(iter(inputs)), "good", "text", now),
                                lambda e=engine: e.write("not an input", "good", 1.0, now),
                                lambda e=engine: e.rebase(-1),
                            ):
                                try:
                                    attempt()
                                except Exception:  # noqa: BLE001 - any refusal will do
                                    refusals += 1
                        if refusals != 8:
                            found += 1
                            first = first or f"run {run} call {call} now {now}: {refusals} of 8 refusals"
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

#!/usr/bin/env python3
"""Run the simulation provider's extrusion graph on FluxGraph 1.x and on the version 2 core, as a host that
simulates would, and set both against the equations integrated finely.

  python3 spike/sim-host/compare.py <run_v1> <fluxgraph_v2_driver>

`run_v1` is spike/sim-host/run_v1.cpp built against the 1.x library, and the driver is of a build with the YAML
loader. The README beside this has the commands.

The graph is four thermal masses: two halves of a chamber, a hotend in the top half, and material leaving the
hotend. A relay heats the top half for the first 20 s and the hotend from 5 s to 40 s; the ambient is 22 degC.
It is run for 60 s at three periods. At each tick the four temperatures a provider would hand on as readings
are taken from each engine, and from the equations stepped by RK4 at a thousandth of the period with the relays
switching where the ticks do.

The version 2 core runs two graphs: one with a block for each mass, as the 1.x graph has a model for each, and
one with the three masses that act on one another joined in one linear model.

An engine's k-th line is set against the truth at tick k and at tick k + 1, since the two engines differ in
which they mean (rule 7.8.1), and the better is kept. Printed: for each period and each engine, which it means,
and its worst error on each of the four temperatures, over the whole run and over the run after its first 5 s.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "conformance"))

SIGNALS = ["tempctl0/tc1_temp", "tempctl0/tc2_temp", "tempctl1/tc1_temp", "tempctl1/tc2_temp"]
AMBIENT = 22.0
SECONDS = 60.0


def relays(t):
    """-> the top half's relay and the hotend's, at time t."""
    return (1.0 if t < 20.0 else 0.0), (1.0 if 5.0 <= t < 40.0 else 0.0)


def writes(t):
    top, hotend = relays(t)
    return {
        "environment/ambient_temp": AMBIENT,
        "tempctl0/relay1_state": top,
        "tempctl0/relay2_state": 0.0,
        "tempctl1/relay1_state": hotend,
        "tempctl1/relay2_state": 0.0,
        "motorctl0/motor1_duty": 0.0,
        "motorctl0/motor2_duty": 0.0,
    }


def rates(x, t):
    """The equations of extrusion.v1.yaml: d/dt of top, bottom, hotend and material."""
    top, bottom, hotend, material = x
    r_top, r_hotend = relays(t)
    return (
        (900.0 * r_top - 15.0 * (top - AMBIENT)) / 500.0,
        (0.0 - 15.0 * (bottom - AMBIENT)) / 500.0,
        (1800.0 * r_hotend - 8.0 * (hotend - top)) / 50.0,
        ((3.0 * hotend + 100.0) - 25.0 * (material - top)) / 10.0,
    )


def truth(dt, ticks):
    """-> the four temperatures at each tick's time, from 0 to `ticks`, by RK4 at dt / 1000."""
    x = (22.0, 22.0, 22.0, 22.0)
    rows = [x]
    h = dt / 1000.0
    for k in range(ticks):
        t_in = k * dt  # the relays are as they are at the tick, for all of the period
        for _ in range(1000):
            k1 = rates(x, t_in)
            k2 = rates(tuple(a + 0.5 * h * b for a, b in zip(x, k1)), t_in)
            k3 = rates(tuple(a + 0.5 * h * b for a, b in zip(x, k2)), t_in)
            k4 = rates(tuple(a + h * b for a, b in zip(x, k3)), t_in)
            x = tuple(a + h / 6.0 * (b + 2 * c + 2 * d + e) for a, b, c, d, e in zip(x, k1, k2, k3, k4))
        rows.append(x)
    return rows


def run_v1(binary, dt, ticks):
    """-> the four temperatures after each tick, or the reason 1.x gave for refusing."""
    script = ["out " + " ".join(SIGNALS)]
    for k in range(ticks):
        script += [f"w {name} {value!r}" for name, value in writes(k * dt).items()]
        script.append("t")
    done = subprocess.run(
        [binary, str(HERE / "extrusion.v1.yaml"), repr(dt)],
        input="\n".join(script) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        return done.stderr.strip().splitlines()[-1]
    return [tuple(float(v) for v in line.split()) for line in done.stdout.splitlines()]


def run_v2(graph, dt, ticks):
    """-> the four temperatures at each tick, or the reason the core gave for refusing."""
    from cpp import adapter, loaders

    text = (HERE / graph).read_text().replace("period: 100ms", f"period: {round(dt * 1000)}ms")
    try:
        engine = adapter.Engine(loaders.load("yaml", text))
    except adapter.CompileError as refused:
        return str(refused)
    period = round(dt * 1e9)
    rows = []
    for k in range(ticks):
        for name, value in writes(k * dt).items():
            engine.write(name, "good", value, k * period)
        ran, out = engine.tick(k * period)
        assert ran == 1
        assert all(out[name].state == "good" for name in SIGNALS), out
        rows.append(tuple(out[name].v for name in SIGNALS))
    return rows


def worst(rows, exact, shift):
    """-> the worst error on each signal, a line k of `rows` set against the truth at tick k + shift."""
    return [max(abs(row[i] - exact[k + shift][i]) for k, row in enumerate(rows)) for i in range(len(SIGNALS))]


def main():
    binary, driver = sys.argv[1], sys.argv[2]
    os.environ["FLUXGRAPH_V2_DRIVER"] = driver
    print(f"{'period':>7s}  {'engine':10s}  {'a line is the state':22s}  " + "  ".join(f"{s:>18s}" for s in SIGNALS))
    for dt in (0.1, 0.5, 1.0):
        ticks = round(SECONDS / dt)
        exact = truth(dt, ticks)
        for name, rows in (
            ("1.x", run_v1(binary, dt, ticks)),
            ("2.0", run_v2("extrusion.v2.yaml", dt, ticks)),
            ("2.0 joined", run_v2("extrusion-joined.v2.yaml", dt, ticks)),
        ):
            if isinstance(rows, str):
                print(f"{dt:6.1f}s  {name:10s}  refused: {rows}")
                continue
            errors = {shift: worst(rows, exact, shift) for shift in (0, 1)}
            shift = min(errors, key=lambda s: max(errors[s]))
            means = "at the tick" if shift == 0 else "a period after it"
            print(f"{dt:6.1f}s  {name:10s}  {means:22s}  " + "  ".join(f"{e:18.3g}" for e in errors[shift]))
            late = worst(rows[round(5.0 / dt) :], exact[round(5.0 / dt) :], shift)
            print(f"{'':7s}  {'':10s}  {'  and after 5 s':22s}  " + "  ".join(f"{e:18.3g}" for e in late))
    first = run_v1(binary, 0.1, 2)
    print(f"1.x, after its first tick at 0.1 s: {first[0]}, where every mass began at 22")


if __name__ == "__main__":
    main()

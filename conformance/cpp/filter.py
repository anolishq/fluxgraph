#!/usr/bin/env python3
"""Check the C++ core's estimator as a filter, against statistics and not against another implementation.

Where the data are drawn from the estimator's own model, with the process noise and the measurement noise it was
told of, a Kalman filter's errors are as large as it says they are: the estimation error of each state, squared
and over its variance, averages 1, and so does the innovation squared over its spread (rule 7.9.6 says as much:
"an estimator whose model and noise are right has a mean of 1"). A filter with its prediction, its noise or its
correction wrong fails one or the other.

  FLUXGRAPH_V2_DRIVER=build/v2/tools/fluxgraph_v2_driver/fluxgraph_v2_driver python3 conformance/cpp/filter.py

For a thermal mass and a second-order process, each at a period far shorter than its time constant and at one
far longer, the truth is stepped by the exact step with noise drawn from the exact `N` (both worked in decimal
by steps.py, and not by the core), measured with noise of variance `r`, and given to the estimator tick by tick.
Each case is 1,000 runs of 40 ticks from a state drawn about the estimator's initial state with variance `p0`,
with a seeded generator. Printed for each: the mean normalised innovation squared over every tick, and for each
state the mean normalised estimation error squared over every tick and at the last tick alone, which the runs
make independent. Exits 1 if a mean is further from 1 than chance allows: 0.05 for the innovations (40,000 of
them, a standard deviation of 0.007) and 0.15 for the last tick's errors (1,000, a standard deviation of 0.045).
"""

from __future__ import annotations

import math
import os
import random
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import steps  # noqa: E402
from cpp import adapter  # noqa: E402

RUNS, TICKS = 1000, 40


def cases():
    for period in ("2s", "500s"):  # a time constant of 100 s
        settings = {"thermal_mass": 100.0, "heat_transfer": 1.0, "initial": 20.0}
        a, b = [[-1.0 / 100.0]], [[1.0 / 100.0, 1.0 / 100.0]]
        yield {
            "name": f"thermal mass, period {period}",
            "period": period,
            "model": {"type": "thermal_mass", **settings},
            "a": a,
            "b": b,
            "c": [1.0],
            "inputs": {"power": 60.0, "ambient": 20.0},
            "states": ["temp"],
            "of": "temp",
            "q": [0.01],
            "p0": [4.0],
            "r": 0.25,
            "initial": [20.0],
        }
    for period in ("50ms", "10s"):  # a natural period of about 6 s
        omega, zeta, gain = 1.0, 0.5, 2.0
        yield {
            "name": f"second-order process, period {period}",
            "period": period,
            "model": {"type": "second_order_process", "omega_n": omega, "zeta": zeta, "gain": gain},
            "a": [[0.0, 1.0], [-omega * omega, -2.0 * zeta * omega]],
            "b": [[0.0], [omega * omega * gain]],
            "c": [1.0, 0.0],
            "inputs": {"u": 1.0},
            "states": ["y", "rate"],
            "of": "y",
            "q": [0.02, 0.3],
            "p0": [1.0, 0.5],
            "r": 0.04,
            "initial": [0.0, 0.0],
        }


def cholesky(matrix):
    n = len(matrix)
    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            rest = matrix[i][j] - sum(lower[i][k] * lower[j][k] for k in range(j))
            lower[i][j] = math.sqrt(rest) if i == j else rest / lower[j][j]
    return lower


def run(case, rng):
    n = len(case["states"])
    period = round(adapter.seconds(case["period"]) * 10**9)
    seconds = Decimal(period) / 10**9
    ad, bd = steps.exact_step(case["a"], case["b"], seconds)
    ad, bd = [[float(v) for v in row] for row in ad], [[float(v) for v in row] for row in bd]
    noise = [[float(v) for v in row] for row in steps.exact_noise(case["a"], case["q"], seconds)]
    root = cholesky(noise)
    u = list(case["inputs"].values())
    drive = [sum(bd[i][k] * u[k] for k in range(len(u))) for i in range(n)]

    settings = {"model": case["model"], "consistency": "none"}
    settings["q"] = dict(zip(case["states"], case["q"]))
    settings["p0"] = dict(zip(case["states"], case["p0"]))
    settings["measure"] = {"z": {"of": case["of"], "r": case["r"]}}
    out = {"nis_z": "nis"}
    out.update({name: name for name in case["states"]})
    out.update({f"sigma_{name}": f"sigma_{name}" for name in case["states"]})
    block = {"id": "k", "type": "estimator", "in": {**case["inputs"], "z": "z"}, "settings": settings, "out": out}
    engine = adapter.Engine({"period": case["period"], "inputs": {"z": {"max_age": "none"}}, "blocks": [block]})

    nis, errors, last = [], [[] for _ in range(n)], [[] for _ in range(n)]
    for _ in range(RUNS):
        engine.reset()
        x = [case["initial"][i] + math.sqrt(case["p0"][i]) * rng.gauss(0.0, 1.0) for i in range(n)]
        for tick in range(TICKS):
            if tick:
                draw = [rng.gauss(0.0, 1.0) for _ in range(n)]
                x = [
                    sum(ad[i][j] * x[j] for j in range(n)) + drive[i] + sum(root[i][j] * draw[j] for j in range(i + 1))
                    for i in range(n)
                ]
            z = sum(case["c"][i] * x[i] for i in range(n)) + math.sqrt(case["r"]) * rng.gauss(0.0, 1.0)
            engine.write("z", adapter.GOOD, z, tick * period)
            gave = engine.tick(tick * period)[1]
            if any(gave[name].state != adapter.GOOD for name in case["states"]) or gave["nis"].v is None:
                print(f"FAILS: {case['name']}: not good at tick {tick}: {gave}")
                sys.exit(1)
            nis.append(gave["nis"].v)
            for i, name in enumerate(case["states"]):
                squared = ((x[i] - gave[name].v) / gave[f"sigma_{name}"].v) ** 2
                errors[i].append(squared)
                if tick == TICKS - 1:
                    last[i].append(squared)
    return sum(nis) / len(nis), [sum(e) / len(e) for e in errors], [sum(e) / len(e) for e in last]


def main():
    adapter.start()
    rng = random.Random(7_9)
    ok = True
    print(f"{'case':38s} {'innovations':>11s}  errors of each state: over every tick, and at the last")
    for case in cases():
        nis, errors, last = run(case, rng)
        shown = ", ".join(f"{name} {e:.3f} and {final:.3f}" for name, e, final in zip(case["states"], errors, last))
        print(f"{case['name']:38s} {nis:11.3f}  {shown}")
        ok = ok and abs(nis - 1) <= 0.05 and all(abs(final - 1) <= 0.15 for final in last)
    print(
        f"{RUNS} runs of {TICKS} ticks each: "
        + ("EVERY MEAN IS 1, AS FAR AS CHANCE ALLOWS" if ok else "A MEAN IS NOT 1")
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

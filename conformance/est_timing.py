"""An estimator whose model is exactly right, under ordinary host timing (amendment 13).

A soft sensor: a core of 200 J/K heated by a 60 W square wave, joined at 4 W/K to a surface of 50 J/K that loses
1 W/K. The surface is measured about once a second with noise of 0.05; the core is what is wanted. The plant is
stepped exactly at 10 ms, and a host loop calls the reference engine at its own interval.

    python3 conformance/est_timing.py [seed] [call]

prints, for each kind of host, how many ticks were `uncertain`, how many measurements were refused, the mean
normalised innovation squared, and the rms error of the core after the first 300 s: for the reference as it is,
for it with a `lag` of 4 s, and for two filters written here that work between samples, one on a grid of a
sixteenth of a period. With a second argument the error is against the truth at the later of the call and the
tick, and not at the tick. With BEFORE set to a directory holding reference.py and formula.py as they were at
commit b705419, the first line of each is the estimator before the amendment.

It draws noise: it is a measurement, and no part of the checks.
"""

import math
import random
import sys
from fractions import Fraction

import os

OLD = bool(os.environ.get("BEFORE"))  # the estimator as it was before amendment 13
sys.path.insert(0, os.environ.get("BEFORE") or os.path.dirname(os.path.abspath(__file__)))
import reference as R  # noqa: E402

NS = 1_000_000_000
A = [[-0.02, 0.02], [0.08, -0.1]]
B = [[0.005], [0.0]]
Q = [1e-4, 1e-4]
RV = 0.05**2
P0 = [1.0, 1.0]
GATE, MAX_REFUSED, OVER, LIMIT = 3.0, 5, 20, 2.0
FINE = Fraction(1, 100)  # the truth is stepped exactly at 10 ms
SECONDS = 2400
AT_CALL = len(sys.argv) > 2  # set the core against the truth at the later of the call and the tick, and not the tick

_steps = {}


def step_for(dt_ns):
    """(Ad, Bd, N) for a step of dt_ns, exactly, as the reference works a period."""
    if dt_ns not in _steps:
        dt = Fraction(dt_ns, NS)
        ad, bd = R.discretise(A, B, dt)
        _steps[dt_ns] = (ad, bd, R.discretise_noise(A, Q, dt))
    return _steps[dt_ns]


def mat(a, b):
    return [[sum(a[i][m] * b[m][j] for m in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]


def truth(switch_offset, seed):
    """The plant at every 10 ms: [(core, surface)], and the heater's power at each of those times."""
    rng = random.Random(seed)
    ad, bd, n = step_for(int(FINE * NS))
    l00 = math.sqrt(n[0][0])  # a draw of the step's process noise, by its Cholesky factor
    l10 = n[1][0] / l00
    l11 = math.sqrt(n[1][1] - l10 * l10)
    x, xs, us = [0.0, 0.0], [], []
    for i in range(int(SECONDS / FINE) + 400):
        t = i * float(FINE)
        u = 60.0 if ((t - switch_offset) // 300) % 2 == 0 and t >= switch_offset else 0.0
        xs.append(tuple(x))
        us.append(u)
        a, b = rng.gauss(0, 1), rng.gauss(0, 1)
        x = [
            ad[0][0] * x[0] + ad[0][1] * x[1] + bd[0][0] * u + l00 * a,
            ad[1][0] * x[0] + ad[1][1] * x[1] + bd[1][0] * u + l10 * a + l11 * b,
        ]
    return xs, us


def host(xs, us, interval, latency, seed):
    """What a host loop hands over at each call: (call time ns, z, z's sample time ns, u)."""
    rng = random.Random(seed + 1)
    out, j = [], 0
    while (tc := round(j * interval * 100)) * 10_000_000 <= SECONDS * NS:  # call times on the 10 ms grid
        ts = tc - round(latency * 100)
        if ts >= 0:
            out.append((tc * 10_000_000, xs[ts][1] + rng.gauss(0, 0.05), ts * 10_000_000, us[tc]))
        j += 1
    return out


class Port:
    """Rules 7.9.5 and 7.9.6 for one port."""

    def __init__(self):
        self.run, self.refused, self.kept = 0, 0, []

    def consider(self, innovation, s):
        """-> 'used', 'refused' or 'given in'."""
        self.kept = (self.kept + [innovation * innovation / s])[-OVER:]
        if abs(innovation) > GATE * math.sqrt(s):
            if self.run < MAX_REFUSED:
                self.run, self.refused = self.run + 1, self.refused + 1
                return "refused"
            self.run = 0
            return "given in"
        self.run = 0
        return "used"

    def inconsistent(self):
        return len(self.kept) == OVER and sum(self.kept) / OVER > LIMIT


def as_written(calls, xs, lag=None):
    """The reference engine, rule 7.9 as it stands. -> (uncertain ticks, ticks, refused, mean nis, core rms)."""
    graph = {
        "period": "1s",
        "inputs": {"u": {"max_age": "none"}, "z": {"max_age": "none"}},
        "blocks": [
            {
                "id": "k",
                "type": "estimator",
                "in": {"u": "u", "z": "z"},
                "settings": {
                    "model": {"type": "linear", "A": A, "B": B, "C": [[1, 0], [0, 1]]},
                    "q": {"x0": Q[0], "x1": Q[1]},
                    "p0": {"x0": P0[0], "x1": P0[1]},
                    "measure": {"z": {"of": "y1", "r": RV}},
                    "gate": GATE,
                    "max_refused": MAX_REFUSED,
                    "consistency": {"over": OVER, "limit": LIMIT},
                }
                | ({} if lag is None else {"lag": lag}),
                "out": {"x0": "core", "nis_z": "nis", "refused_z": "refused"} | ({} if OLD else {"late_z": "late"}),
            }
        ],
    }
    e = R.Engine(graph)
    uncertain = ticks = 0
    nis, err, refused, late = [], [], 0, 0
    for tc, z, ts, u in calls:
        e.write("z", R.GOOD, z, ts)
        e.write("u", R.GOOD, u, tc)
        ran, out = e.tick(tc)
        if not ran:
            continue
        tick_time = e.info["time"]  # of the last tick the call ran: the nearest to the call
        ticks += ran
        uncertain += out["core"].state != R.GOOD
        if out["nis"].state == R.GOOD:
            nis.append(out["nis"].v)
        refused, late = out["refused"].v, 0 if OLD else out["late"].v
        if tick_time >= 300 * NS:
            err.append(out["core"].v - xs[(max(tc, tick_time) if AT_CALL else tick_time) // 10_000_000][0])
    rms = math.sqrt(sum(d * d for d in err) / len(err))
    return uncertain, len(err) + 300, int(refused), sum(nis) / max(len(nis), 1), rms, int(late)


def between_samples(calls, xs, grid_ns=None):
    """A filter whose state stands at the time of the measurement last considered. Each measurement is met by a
    prediction to its own sample time, on the model inputs as they were written, each from its own time; what is
    given at a call is a prediction on from there. With grid_ns, every time is first rounded to that grid."""
    snap = (lambda t: round(t / grid_ns) * grid_ns) if grid_ns else (lambda t: t)
    x, p, t = [0.0, 0.0], [[P0[0], 0.0], [0.0, P0[1]]], 0
    changes = [(0, 0.0)]  # the model input: (from when, value), in order of time
    port, uncertain, nis, err, late = Port(), 0, [], [], 0

    def carry(x, p, t0, t1, keep_p=True):
        """From t0 to t1, across each change of the input between them."""
        at, i = t0, max(k for k, (when, _) in enumerate(changes) if when <= t0)
        while at < t1:
            until = min(t1, changes[i + 1][0]) if i + 1 < len(changes) else t1
            if until > at:
                ad, bd, n = step_for(until - at)
                u = changes[i][1]
                x = [ad[r][0] * x[0] + ad[r][1] * x[1] + bd[r][0] * u for r in range(2)]
                if keep_p:
                    f = mat(mat(ad, p), [[ad[0][0], ad[1][0]], [ad[0][1], ad[1][1]]])
                    p = [[f[r][c] + n[r][c] for c in range(2)] for r in range(2)]
                at = until
            i += 1
        return x, p

    for tc, z, ts, u in calls:
        tc_s, ts_s = snap(tc), snap(ts)
        if u != changes[-1][1]:
            changes.append((max(tc_s, changes[-1][0]), u))
        flagged = False
        if ts_s < t:
            late += 1  # older than what it has: taken as of now
            ts_s = t
        x, p = carry(x, p, t, ts_s)
        t = ts_s
        innovation, s = z - x[1], p[1][1] + RV
        nis.append(innovation * innovation / s)
        what = port.consider(innovation, s)
        if what == "given in":
            p = [[p[0][0] + P0[0], p[0][1]], [p[1][0], p[1][1] + P0[1]]]
            s = p[1][1] + RV
        if what != "refused":
            g = [p[0][1] / s, p[1][1] / s]
            x = [x[0] + g[0] * innovation, x[1] + g[1] * innovation]
            ikc = [[1.0, -g[0]], [0.0, 1.0 - g[1]]]
            f = mat(mat(ikc, p), [[ikc[0][0], ikc[1][0]], [ikc[0][1], ikc[1][1]]])
            p = [[f[r][c] + g[r] * RV * g[c] for c in range(2)] for r in range(2)]
        flagged = what != "used" or port.inconsistent()
        uncertain += flagged
        ahead, _ = carry(x, p, t, max(tc_s, t), keep_p=False)
        if tc >= 300 * NS:
            err.append(ahead[0] - xs[tc // 10_000_000][0])
        while len(changes) > 1 and changes[1][0] <= t:
            changes.pop(0)
    rms = math.sqrt(sum(d * d for d in err) / len(err))
    return uncertain, len(calls), port.refused, sum(nis) / len(nis), rms, late


CASES = [
    ("host on time, heater switches on a tick", 1.0, 0.0, 0.0),
    ("host 3% slow", 1.03, 0.0, 0.0),
    ("host 3% fast", 0.97, 0.0, 0.0),
    ("host on time, heater switches 0.4 s after a tick", 1.0, 0.0, 0.4),
    ("samples 3 s old", 1.0, 3.0, 0.0),
    ("host 3% slow, samples 3 s old, switch 0.4 s after", 1.03, 3.0, 0.4),
]

if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    print(f"seed {seed}; each: uncertain of calls or ticks, refused, mean NIS, rms error of the core after 300 s")
    for name, interval, latency, offset in CASES:
        xs, us = truth(offset, seed)
        calls = host(xs, us, interval, latency, seed)
        a = as_written(calls, xs)
        a4 = a if OLD else as_written(calls, xs, lag="4s")
        b = between_samples(calls, xs)
        c = between_samples(calls, xs, grid_ns=NS // 16)
        print(name)
        row = "{:5d} of {:5d}  refused {:4d}  nis {:6.2f}  rms {:.3f}  late {}"
        print("  the reference    " + row.format(*a))
        print("  with lag of 4 s  " + row.format(*a4))
        print(f"  between samples  {b[0]:5d} of {b[1]:5d}  refused {b[2]:4d}  nis {b[3]:6.2f}  rms {b[4]:.3f}")
        print(f"  on a 1/16 grid   {c[0]:5d} of {c[1]:5d}  refused {c[2]:4d}  nis {c[3]:6.2f}  rms {c[4]:.3f}")

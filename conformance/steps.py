#!/usr/bin/env python3
"""Check an implementation's exact step (rule 7.8.7) against arithmetic of many more digits.

A model in continuous time is stepped by `Ad = exp(A * period)` and `Bd`, the integral of `exp(A s)` over the
period times `B`, worked when the graph is compiled and promised to one part in 10^9 up to the bound on
stiffness: the largest sum of absolute values along a row of `A`, times the period, at most 100,000. Two
implementations that agree on a step show that they are alike and not that either is right: the reference here
worked its steps in doubles, was out by 2.8e-9 at the bound, and agreed with every vector. This works `Ad` and
`Bd` in decimal arithmetic of 150 digits, by a route of its own, checks that route against closed forms where
there are any, and then sets an implementation against it at, near and far inside the bound.

  python3 conformance/steps.py            the reference
  python3 conformance/steps.py --second   the second implementation

`Ad` and `Bd` are read off the implementation through a `linear` block whose outputs are its states: started from
one unit state with inputs of zero it gives a column of `Ad` at tick 1, and from zero with one input at one, a column of
`Bd`.

What is checked:

1. The decimal route against closed forms: one state; two states with two real rates, by the formula for a
   triangular matrix; a rotation, by sines and cosines summed from their series.
2. The implementation against the decimal route on families of matrices (thermal networks, rotations with a little
   damping, triangular ones with rates many orders apart and large entries off the diagonal, ones that grow), from
   1 to 6 states, with the row sum times the period from 10^-8 to just under 100,000, at periods of 1 s, 37 ms
   and 2.5 s, and with `B` up to 10^150.
3. A matrix just past the bound is refused, and one whose step is past what a double holds.
4. A named model's default `settle` (rule 7.8.6), against the eigenvalues worked in decimal.

The error of an entry is its difference from the decimal value over the larger of that value and 1, as rule 11.5
compares. Prints the worst of each family, and exits 1 if any is over 10^-9. Stdlib only.
"""

from __future__ import annotations

import math
import random
import sys
from decimal import Decimal, getcontext

import reference

adapter = reference  # the implementation under test; --second swaps it

getcontext().prec = 150
PROMISED = 1e-9
BOUND = 100000


# ---- arithmetic of many digits


def identity(n):
    return [[Decimal(int(i == j)) for j in range(n)] for i in range(n)]


def times(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]


def exponential(m):
    """exp(m) for a square matrix of Decimals: the series, on m over a power of two, then squared back."""
    n = len(m)
    size = max(sum(abs(v) for v in row) for row in m)
    halvings = max(0, size.adjusted() * 4 + 16) if size else 0  # 10^k is under 2^(4k): the scaled size is under 2^-8
    x = [[v / (Decimal(2) ** halvings) for v in row] for row in m]
    total, term = identity(n), identity(n)
    for k in range(1, 60):
        term = [[v / k for v in row] for row in times(term, x)]
        total = [[total[i][j] + term[i][j] for j in range(n)] for i in range(n)]
    for _ in range(halvings):
        total = times(total, total)
    return total


def exact_step(a, b, seconds):
    """-> (Ad, Bd), from the exponential of [[A, I], [0, 0]] times the period, whose corner is the integral."""
    n = len(a)
    wide = [
        [Decimal(a[i][j]) * seconds for j in range(n)] + [seconds * int(i == j) for j in range(n)] for i in range(n)
    ]
    wide += [[Decimal(0)] * (2 * n) for _ in range(n)]
    e = exponential(wide)
    ad = [row[:n] for row in e[:n]]
    integral = [row[n:] for row in e[:n]]
    return ad, times(integral, [[Decimal(v) for v in row] for row in b])


def pi():
    def arctan_inverse(x):  # arctan(1 / x), by its series
        total, term, k = Decimal(0), Decimal(1) / x, 0
        while abs(term) > Decimal(10) ** -170:
            total += term / (2 * k + 1) * (-1) ** k
            term, k = term / (x * x), k + 1
        return total

    getcontext().prec += 30
    value = 16 * arctan_inverse(Decimal(5)) - 4 * arctan_inverse(Decimal(239))  # Machin
    getcontext().prec -= 30
    return +value


def sine_cosine(angle, pi_value):
    turns = (angle / (2 * pi_value)).to_integral_value()
    x = angle - turns * 2 * pi_value
    sine, cosine, term, k = Decimal(0), Decimal(0), Decimal(1), 0
    while abs(term) > Decimal(10) ** -160:
        if k % 2 == 0:
            cosine += term * (-1) ** (k // 2)
        else:
            sine += term * (-1) ** (k // 2)
        k += 1
        term = term * x / k
    return sine, cosine


def worst(have, want):
    """-> (the largest error over the entries, as rule 11.5 measures it, where it is)."""
    most = (0.0, None)
    for i, row in enumerate(want):
        for j, exact in enumerate(row):
            error = float(abs(Decimal(have[i][j]) - exact) / max(Decimal(1), abs(exact)))
            if not error <= most[0]:
                most = (error, (i, j, have[i][j], float(exact)))
    return most


def closed_forms():
    """1: the decimal route is itself right, where a closed form says what right is."""
    most, pi_value = 0.0, pi()
    for rate in ("-100000", "-709", "-1", "-0.000000001", "0", "0.25", "700"):
        ad, bd = exact_step([[Decimal(rate)]], [[Decimal(1)]], Decimal(1))
        want = Decimal(rate).exp()
        integral = Decimal(1) if rate == "0" else (want - 1) / Decimal(rate)
        most = max(most, float(abs(ad[0][0] - want) / max(1, want)), float(abs(bd[0][0] - integral) / max(1, integral)))
    for fast, slow in (("100000", "0.001"), ("99999", "50000"), ("3", "2.999999")):
        a, b = Decimal(fast), Decimal(slow)  # [[-a, 1], [0, -b]]: exp is [[e^-a, (e^-b - e^-a) / (a - b)], [0, e^-b]]
        ad, _ = exact_step([[-a, Decimal(1)], [Decimal(0), -b]], [[Decimal(0)], [Decimal(1)]], Decimal(1))
        want = [[(-a).exp(), ((-b).exp() - (-a).exp()) / (a - b)], [Decimal(0), (-b).exp()]]
        most = max(most, max(float(abs(ad[i][j] - want[i][j])) for i in range(2) for j in range(2)))
    for speed in ("99999.5", "316.2", "1", "0.0001"):
        w = Decimal(speed)  # [[0, w], [-w, 0]]: a rotation by w
        ad, bd = exact_step([[Decimal(0), w], [-w, Decimal(0)]], [[Decimal(1)], [Decimal(0)]], Decimal(1))
        sine, cosine = sine_cosine(w, pi_value)
        want = [[cosine, sine], [-sine, cosine]]
        most = max(most, max(float(abs(ad[i][j] - want[i][j])) for i in range(2) for j in range(2)))
        most = max(most, float(abs(bd[0][0] - sine / w)), float(abs(bd[1][0] - (cosine - 1) / w)))
    if most > 1e-100:
        print(f"FAILS: the decimal route is out from a closed form by {most:.3g}")
        sys.exit(1)
    return most


# ---- the core


def core_step(a, b, period):
    """-> (Ad, Bd) as the core works them, or None where it refuses the graph."""
    n, m = len(a), len(b[0])
    outputs = [f"y{i}" for i in range(n)]
    settings = {"A": a, "B": b, "C": [[float(i == j) for j in range(n)] for i in range(n)]}
    settings.update(inputs=[f"u{k}" for k in range(m)], outputs=outputs)
    columns = []
    for column in range(n + m):
        initial = [float(i == column) for i in range(n)]
        ins = {f"u{k}": float(n + k == column) for k in range(m)}
        block = {"id": "m", "type": "linear", "in": ins, "settings": dict(settings, initial=initial)}
        block["out"] = {name: name for name in outputs}
        try:
            engine = adapter.Engine({"period": f"{period}ns", "blocks": [block]})
        except adapter.CompileError:
            return None
        engine.tick(0)
        out = engine.tick(period)[1]
        if any(out[name].v is None for name in outputs):
            return None
        columns.append([out[name].v for name in outputs])
    ad = [[columns[j][i] for j in range(n)] for i in range(n)]
    bd = [[columns[n + k][i] for k in range(m)] for i in range(n)]
    return ad, bd


def scaled(matrix, size, seconds):
    """The matrix times what makes its largest row sum, times the period, `size`: as the doubles the core is given."""
    if not any(any(row) for row in matrix):  # a family can come out all zero in one state: a plain decay then
        matrix = [[-1.0 * (i == j) for j in range(len(matrix))] for i in range(len(matrix))]
    most = max(sum(abs(v) for v in row) for row in matrix)
    return [[float(v * size / (most * seconds)) for v in row] for row in matrix]


def families(rng, n):
    network = [[rng.uniform(0, 1) if i < j else 0.0 for j in range(n)] for i in range(n)]
    network = [[network[min(i, j)][max(i, j)] for j in range(n)] for i in range(n)]
    for i in range(n):
        network[i][i] = -(sum(network[i]) + rng.choice([0.0, 1e-6, 0.3]))
    yield "a thermal network", network
    spin = [[rng.uniform(-1, 1) if i < j else 0.0 for j in range(n)] for i in range(n)]
    spin = [[spin[i][j] - spin[j][i] for j in range(n)] for i in range(n)]
    for i in range(n):
        spin[i][i] = -rng.choice([0.0, 1e-9, 1e-3])
    yield "rotations, little damped", spin
    ladder = [[rng.uniform(-1, 1) if i < j else 0.0 for j in range(n)] for i in range(n)]
    for i in range(n):
        ladder[i][i] = -(10.0 ** rng.uniform(-9, 0))
    yield "triangular, rates far apart", ladder


def against_the_core(rng):
    """2: the core against the decimal route."""
    tried, table = 0, {}
    for period in (10**9, 37 * 10**6, 2_500_000_000):
        seconds = Decimal(period) / 10**9
        for n in range(1, 7):
            for size in (1e-8, 1e-3, 1.0, 50.0, 1e3, 3e4, 99999.9):
                for family, matrix in families(rng, n):
                    a = scaled(matrix, size, float(seconds))
                    m = rng.randint(1, 3)
                    b = [[rng.uniform(-1, 1) * rng.choice([1.0, 1.0, 1e-9, 1e150]) for _ in range(m)] for _ in range(n)]
                    have = core_step(a, b, period)
                    if have is None:
                        print(f"FAILS: the core refused {family}, {n} states, size {size:g}, period {period} ns")
                        sys.exit(1)
                    want = exact_step(a, b, seconds)
                    tried += 1
                    for which, h, w in (("Ad", have[0], want[0]), ("Bd", have[1], want[1])):
                        error, where = worst(h, w)
                        key = (family, which)
                        if error >= table.get(key, (-1.0,))[0]:
                            table[key] = (error, n, size, period, where)
    # ones that grow: any matrix, of a size that keeps exp within a double
    for n in range(1, 7):
        for size in (1.0, 30.0, 300.0):
            matrix = [[rng.uniform(-1, 1) for _ in range(n)] for _ in range(n)]
            a = scaled(matrix, size, 1.0)
            b = [[rng.uniform(-1, 1)] for _ in range(n)]
            have, want = core_step(a, b, 10**9), exact_step(a, b, Decimal(1))
            tried += 1
            for which, h, w in (("Ad", have[0], want[0]), ("Bd", have[1], want[1])):
                error, where = worst(h, w)
                key = ("any matrix, growing", which)
                if error >= table.get(key, (-1.0,))[0]:
                    table[key] = (error, n, size, 10**9, where)
    return tried, table


def refusals():
    """3: just past the bound, and past what a double holds."""
    wanted = [
        ("a row sum of 100000.001 at 1 s", [[-100000.001]], 10**9, True),
        ("a row sum of 100000 at 1 s", [[-100000.0]], 10**9, False),
        ("a row sum of 40000.0004 at 2.5 s", [[-40000.0004]], 2_500_000_000, True),
        ("a row sum of 40000 at 2.5 s", [[-20000.0, 20000.0], [0.0, -1.0]], 2_500_000_000, False),
        ("a state that grows past a double in one period", [[710.0]], 10**9, True),
        ("a state that grows to just under it", [[709.0]], 10**9, False),
    ]
    for what, a, period, refused in wanted:
        have = core_step(a, [[1.0]] * len(a), period)
        if (have is None) != refused:
            print(f"FAILS: {what} was {'accepted' if refused else 'refused'}")
            sys.exit(1)
    return len(wanted)


def default_settles():
    """4: three of a named model's slowest time constant, rounded up to whole ticks, by the ticks it is uncertain
    for after one uncertain input."""
    cases = []
    for mass, loss in ((4.0, 1.0), (10.0, 3.0), (1.0, 8.0), (0.5, 0.75)):
        cases.append(("thermal_mass", {"thermal_mass": mass, "heat_transfer": loss, "initial": 0.0}, [[-loss / mass]]))
    for ma, mb, ha, hb, k in ((1.0, 2.0, 1.0, 0.5, 3.0), (0.001, 5.0, 0.2, 1.0, 40.0), (2.0, 2.0, 0.0, 1.0, 0.25)):
        s = {"thermal_mass_a": ma, "thermal_mass_b": mb, "heat_transfer_a": ha, "heat_transfer_b": hb, "coupling": k}
        s.update(initial_a=0.0, initial_b=0.0)
        cases.append(("thermal_rc2", s, [[-(ha + k) / ma, k / ma], [k / mb, -(hb + k) / mb]]))
    for omega, zeta in ((2.0, 0.2), (1.0, 1.0), (0.5, 3.0), (30.0, 40.0)):
        s = {"omega_n": omega, "zeta": zeta}
        cases.append(("second_order_process", s, [[0.0, 1.0], [-omega * omega, -2 * zeta * omega]]))
    for mass, damping, stiff in ((2.0, 1.0, 3.0), (1.0, 50.0, 1.0)):
        s = {"mass": mass, "damping": damping, "stiffness": stiff}
        cases.append(("mass_spring_damper", s, [[0.0, 1.0], [-stiff / mass, -damping / mass]]))
    # A first-order process whose r is a whole number, and in doubles comes out a little over it: 6, 12 and 33.
    quick = [
        ("first_order_process", {"tau": tau}, [[-1 / float(tau[:-1])]], "100ms") for tau in ("0.2s", "0.4s", "1.1s")
    ]
    cases = [(*case, "1s") for case in cases] + quick
    ports = {"thermal_mass": ("power", "ambient"), "thermal_rc2": ("power", "ambient"), "second_order_process": ("u",)}
    ports["mass_spring_damper"], ports["first_order_process"] = ("force",), ("u",)
    state = {
        "thermal_mass": "temp",
        "thermal_rc2": "temp_a",
        "second_order_process": "y",
        "mass_spring_damper": "position",
        "first_order_process": "y",
    }
    for kind, settings, a, period in cases:
        step = round(adapter.seconds(period) * 10**9)
        if kind == "first_order_process":
            rate = -1 / Decimal(settings["tau"][:-1])
        elif len(a) == 1:
            rate = Decimal(a[0][0])
        else:  # the larger root of x^2 - trace x + determinant, or the real part where they are a pair
            half = (Decimal(a[0][0]) + Decimal(a[1][1])) / 2
            det = Decimal(a[0][0]) * Decimal(a[1][1]) - Decimal(a[0][1]) * Decimal(a[1][0])
            rate = half if half * half <= det else half + (half * half - det).sqrt()
        r = 3 / -rate * 10**9 / step
        want = math.ceil(r - Decimal("1e-9"))
        if abs(r - Decimal("1e-9") - round(r)) < Decimal("1e-12"):
            continue  # within rounding of where it turns: a graph may be taken either way
        ins = {port: ("x" if i == 0 else 0.0) for i, port in enumerate(ports[kind])}
        block = {"id": "m", "type": kind, "in": ins, "settings": settings, "out": {state[kind]: "s"}}
        engine = adapter.Engine({"period": period, "inputs": {"x": {"max_age": "none"}}, "blocks": [block]})
        engine.write("x", adapter.UNCERTAIN, 1.0, 0)  # stepped on at tick 0: a doubt, seen for `settle` ticks after
        if engine.tick(0)[1]["s"].state != adapter.GOOD:
            print(f"FAILS: a {kind} is not good at tick 0")
            sys.exit(1)
        engine.write("x", adapter.GOOD, 1.0, step)
        first = next(k for k in range(1, want + 3) if engine.tick(k * step)[1]["s"].state == adapter.GOOD)
        if first != want + 1:
            print(f"FAILS: the default settle of a {kind} {settings}: {first - 1} ticks, and the text gives {want}")
            sys.exit(1)
    return len(cases)


def main():
    global adapter
    if sys.argv[1:] == ["--second"]:
        from second import adapter as second

        adapter = second
    rng = random.Random(7_8_7)
    print(f"the decimal route against closed forms: out by at most {closed_forms():.1g}")
    tried, table = against_the_core(rng)
    most = 0.0
    print(f"{'family':30s} {'':3s} {'worst error':>11s}  where")
    for (family, which), (error, n, size, period, where) in sorted(table.items()):
        most = max(most, error)
        at = f"{n} states, size {size:g}, period {period / 1e9:g} s"
        print(f"{family:30s} {which:3s} {error:11.3g}  {at}, entry {where}")
    tried += refusals() + default_settles()
    if not most <= PROMISED:
        print(f"FAILS: the worst error, {most:.3g}, is over what is promised, {PROMISED:g}")
        sys.exit(1)
    print(f"{tried} checks: ALL HOLD; the worst error of the step is {most:.3g}, against {PROMISED:g} promised")


if __name__ == "__main__":
    main()

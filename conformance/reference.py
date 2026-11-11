#!/usr/bin/env python3
"""A reference for the version 2 semantics proposal (docs/semantics_spec_v2.md), third revision.

Small, slow and written to be read beside the proposal. It is not the
library and shares no code with it. Its job is to be a second opinion: the
vectors in vectors/ state what each rule should give, worked out by hand,
and this has to agree with them.

Stdlib only. The formula language is in formula.py. run.py loads the
vectors (it needs PyYAML) and drives this.
"""

from __future__ import annotations

import collections
import copy
import math
import re
import statistics
from fractions import Fraction

from formula import BAD, BOOLEAN, GOOD, NOT_READY, NUMBER, UNCERTAIN, CompileError, Formula, Val, usable, worst

STATES = (GOOD, UNCERTAIN, NOT_READY, BAD)
_DURATION = re.compile(r"^([0-9]+(?:\.[0-9]+)?)(ns|us|ms|s|m|h)$")
_UNIT = {
    "ns": Fraction(1, 10**9),
    "us": Fraction(1, 10**6),
    "ms": Fraction(1, 1000),
    "s": Fraction(1),
    "m": Fraction(60),
    "h": Fraction(3600),
}
NS = 10**9


def length(text, whole=True):
    """Section 9 rule 3: a length of time, exactly, in seconds. It is a whole number of nanoseconds."""
    m = _DURATION.match(text) if isinstance(text, str) else None
    if not m:
        raise CompileError(f"{text!r} is not a length of time (use 500ms, 3s, 2m, 1h)")
    seconds_ = Fraction(m.group(1)) * _UNIT[m.group(2)]
    if whole and (seconds_ * NS).denominator != 1:  # 6 rule 2
        raise CompileError(f"{text!r} is not a whole number of nanoseconds")
    return seconds_


def nanoseconds(text):
    return int(length(text) * NS)


def seconds(text):
    return float(length(text))


def round_up(x):
    """Section 6 rule 3: up to a whole number, a value within 1e-9 of one being that one."""
    return math.ceil(x - 1e-9)


def latest(*ticks):
    ticks = [t for t in ticks if t is not None]
    return max(ticks) if ticks else None


# ---------------------------------------------------------------- settings


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def read_settings(where, spec, raw, period):
    """spec: name -> (kind, required, default). -> the settings, checked for type (section 9 rule 5)."""
    if not isinstance(raw, dict):
        raise CompileError(f"{where}: settings are a map")
    if set(raw) - set(spec):
        raise CompileError(f"{where}: unknown setting(s) {sorted(set(raw) - set(spec))}")
    out = {}
    for name, (kind, required, default) in spec.items():
        if name not in raw:
            if required:
                raise CompileError(f"{where}: missing setting {name!r}")
            out[name] = default
            continue
        value, what = raw[name], f"{where}: setting {name!r}"
        try:
            if kind in ("ticks", "ticks1"):  # a counted length: a whole number of periods (6 rule 3)
                n = length(value) / period
                if n.denominator != 1:
                    raise CompileError(f"is {value}, which is not a whole number of periods")
                if n < (1 if kind == "ticks1" else 0):
                    raise CompileError("is at least one period")
                value = int(n)
            elif kind == "seconds":  # it scales a value, and is no time the engine keeps (6 rule 3)
                value = length(value, whole=False)
            elif kind == "number":
                if not is_number(value):
                    raise CompileError("is a finite number")
            elif kind == "int":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise CompileError("is a whole number, written without a point")
            elif kind == "bool":
                if not isinstance(value, bool):
                    raise CompileError("is true or false")
            elif kind == "const":
                if not isinstance(value, bool) and not is_number(value):
                    raise CompileError("is a finite number, or true or false")
            elif kind == "choice":
                if value not in default:
                    raise CompileError(f"is one of {list(default)}")
            elif kind == "str":
                if not isinstance(value, str):
                    raise CompileError("is text")
            elif kind == "numbers":
                if not isinstance(value, list) or not value or not all(is_number(v) for v in value):
                    raise CompileError("is a list of finite numbers")
            elif kind == "matrix":
                rows = value if isinstance(value, list) else []
                if not rows or not all(
                    isinstance(r, list) and len(r) == len(rows) and all(map(is_number, r)) for r in rows
                ):
                    raise CompileError("is a square list of rows of finite numbers")
            elif kind == "map" and not isinstance(value, dict):
                raise CompileError("is a map")
        except CompileError as exc:
            raise CompileError(f"{what} {exc}") from exc
        out[name] = value
    return out


# ---------------------------------------------------------------- blocks


class Block:
    """A block as configured. `ports`: input -> (type or None for any, required, direct); None: any inputs."""

    settings: dict = {}
    ports: dict | None = {}
    outputs: dict = {"y": NUMBER}
    typed_late = False  # its output types wait on its inputs' types
    own_at = False  # it gives its outputs their sample time itself (3 rule 7)
    loop_settle = None  # on a loop that holds a model: the loop's settle, in ticks (7.8 rule 8)
    loop_doubt = None  # and the loop's doubt, a tick, given by the engine before each tick

    def __init__(self, s, period):
        self.s, self.period = s, float(period)

    def bind(self, in_types):
        """Told its inputs' types, once they are known."""

    def output(self, k, t, ins):
        """First phase: the outputs at tick k, whose time is t, from the state and the direct inputs."""
        raise NotImplementedError

    def update(self, k, ins):
        """Second phase: the state, from every input."""

    def used(self, ins):
        """Rule D: the inputs it used. Every block but a formula uses every input it has."""
        return set(ins)

    def loop_settled(self, k):
        """7.8 rule 8: it is on a loop that holds a model, and the loop is not within settle of its doubt."""
        d = self.loop_doubt
        return self.loop_settle is not None and (d is None or not d < k <= d + self.loop_settle)

    def gap(self, k):
        """Section 8 rule 6: time went by unseen; k is the gap's tick."""

    def forget_times(self):
        """Section 8 rule 5: a rebase. The clock may be another clock: forget every sample time."""


class FormulaBlock(Block):
    settings = {"expr": ("str", True, None), "sample_of": ("str", False, None)}
    ports = None
    typed_late = True
    own_at = True

    def bind(self, in_types):
        self.formula = Formula(self.s["expr"], in_types)
        self.outputs = {"y": self.formula.type}

    def wired(self, signals):
        """Told which of its inputs are signals: which one y takes its sample time from."""
        named = self.s["sample_of"]
        if named is not None and named not in signals:
            raise CompileError(f"sample_of names {named!r}, which is not an input of the block that is a signal")
        self.sample_of = named if named is not None else signals[0] if len(signals) == 1 else None

    def output(self, k, t, ins):
        out = self.formula.eval(ins)
        return {"y": Val(out.state, out.v, ins[self.sample_of].at if self.sample_of else t)}

    def used(self, ins):
        return self.formula.uses(ins)


class AllGood(Block):
    ports = None
    outputs = {"y": BOOLEAN}

    def output(self, k, t, ins):
        return {"y": Val(GOOD, all(v.state == GOOD for v in ins.values()))}


class Delay(Block):
    settings = {"ticks": ("int", False, 1), "initial": ("const", False, None)}
    ports = {"x": (None, True, False)}
    typed_late = True
    own_at = True

    def __init__(self, *a):
        super().__init__(*a)
        if self.s["ticks"] < 1:
            raise CompileError("ticks is at least 1")
        self.past = collections.deque()

    def bind(self, in_types):
        initial = self.s["initial"]
        kind = None if initial is None else BOOLEAN if isinstance(initial, bool) else NUMBER
        if kind is not None and "x" in in_types and in_types["x"] != kind:
            raise CompileError("its initial value is not of its input's type")
        self.outputs = {"y": in_types.get("x", kind)}

    def output(self, k, t, ins):
        if len(self.past) < self.s["ticks"]:
            initial = self.s["initial"]
            if initial is None:
                return {"y": Val(NOT_READY)}
            return {"y": Val(GOOD, initial if isinstance(initial, bool) else float(initial))}
        if self.loop_settled(k):  # 7.8 rule 8: what it took in as uncertain becomes good
            self.past = collections.deque(Val(GOOD, v.v, v.at) if v.state == UNCERTAIN else v for v in self.past)
        return {"y": self.past[0]}

    def update(self, k, ins):
        self.past.append(ins["x"])
        if len(self.past) > self.s["ticks"]:
            self.past.popleft()

    def gap(self, k):
        self.past = collections.deque(Val(UNCERTAIN, v.v, v.at) if v.state == GOOD else v for v in self.past)

    def forget_times(self):
        self.past = collections.deque(Val(v.state, v.v) for v in self.past)


class Window(Block):
    """Section 7.3."""

    settings = {
        "window": ("ticks1", True, None),
        "min_good": ("number", False, None),
        "only_new": ("bool", False, False),
    }
    ports = {"x": (NUMBER, True, True)}
    outputs = dict.fromkeys(("mean", "median", "min", "max", "spread", "slope", "count"), NUMBER)

    def __init__(self, *a):
        super().__init__(*a)
        self.n = self.s["window"]
        if self.s["min_good"] is None:
            if self.s["only_new"]:
                raise CompileError("min_good is given with only_new: true")  # rule 8
            self.s["min_good"] = 1.0
        if not 0.0 < self.s["min_good"] <= 1.0:
            raise CompileError("min_good is more than 0 and at most 1")
        self.need = max(1, round_up(self.s["min_good"] * self.n))
        self.buf, self.last_at = collections.deque(maxlen=self.n), None

    def output(self, k, t, ins):
        x = ins["x"]
        if self.s["only_new"] and usable(x):  # rule 8
            if x.at is None or (self.last_at is not None and x.at <= self.last_at):
                x = Val(NOT_READY)
            else:
                self.last_at = x.at
        if self.loop_settled(k):  # 7.8 rule 8: what it took in as uncertain counts as good
            took = (Val(GOOD, v.v, v.at) if v.state == UNCERTAIN else v for v in self.buf)
            self.buf = collections.deque(took, maxlen=self.n)
        self.buf.append(x)
        first = self.n - len(self.buf)  # the ticks of the window from before the start, or a gap
        held = [(first + i, v) for i, v in enumerate(self.buf) if usable(v)]
        good = [(i, v) for i, v in held if v.state == GOOD]
        out = {"count": Val(GOOD, float(len(held)))}
        names = [name for name in self.outputs if name != "count"]
        if len(held) < self.need:  # rule 3
            missing = [v.state for v in self.buf if not usable(v)] + [NOT_READY] * first
            return out | dict.fromkeys(names, Val(worst(missing)))
        state, of = (GOOD, good) if len(good) >= self.need else (UNCERTAIN, held)  # rules 5 and 4
        ys = [v.v for _, v in of]
        out |= {
            "mean": Val(state, sum(ys) / len(ys)),
            "median": Val(state, statistics.median(ys)),
            "min": Val(state, min(ys)),
            "max": Val(state, max(ys)),
            "spread": Val(state, max(ys) - min(ys)),
        }
        if len(good) < 2 <= len(held):  # rule 6: no two good samples, so the slope is of the usable ones
            state, of = UNCERTAIN, held
            ys = [v.v for _, v in of]
        ts = [i * self.period for i, _ in of]
        mt, my = sum(ts) / len(ts), sum(ys) / len(ys)
        den = sum((ti - mt) ** 2 for ti in ts)
        if len(of) < 2 or den == 0.0:
            out["slope"] = Val(BAD)
        else:
            out["slope"] = Val(state, sum((ti - mt) * (y - my) for ti, y in zip(ts, ys, strict=True)) / den)
        return out

    def gap(self, k):
        self.buf.clear()

    def forget_times(self):
        self.last_at = None


class Deadband(Block):
    """Section 7.4 rules 1 to 4."""

    settings = {"step": ("number", True, None), "ride_through": ("ticks", False, 0)}
    ports = {"x": (NUMBER, True, True)}

    def __init__(self, *a):
        super().__init__(*a)
        if self.s["step"] < 0:
            raise CompileError("step is not negative")
        self.held, self.seen = None, None  # the value it holds; the tick of its last usable input

    def output(self, k, t, ins):
        x = ins["x"]
        if usable(x):
            if self.held is None or abs(x.v - self.held) >= self.s["step"]:
                self.held = x.v
            self.seen = k
            return {"y": Val(x.state, self.held)}  # rule 2: the state of the input at this tick
        if self.held is not None and k - self.seen <= self.s["ride_through"]:
            return {"y": Val(UNCERTAIN, self.held)}
        self.held = None
        return {"y": Val(x.state)}

    def gap(self, k):
        self.held = None


class Lowpass(Block):
    """Section 7.4 rules 5 to 8."""

    settings = {"tau": ("seconds", True, None), "ride_through": ("ticks", False, 0), "settle": ("ticks", False, None)}
    ports = {"x": (NUMBER, True, True)}

    def __init__(self, *a):
        super().__init__(*a)
        if self.s["tau"] <= 0:
            raise CompileError("tau is more than zero")
        self.a = math.exp(-self.period / float(self.s["tau"]))
        if self.s["settle"] is None:
            self.s["settle"] = round_up(3 * float(self.s["tau"]) / self.period)
        self.y, self.seen, self.doubt = None, None, None

    def output(self, k, t, ins):
        x = ins["x"]
        if self.loop_settled(k):  # 7.8 rule 8: what it took in as uncertain counts as good
            self.doubt = None
        if not usable(x):
            if self.y is not None and k - self.seen <= self.s["ride_through"]:
                return {"y": Val(UNCERTAIN, self.y)}
            self.y, self.doubt = None, None  # rule 4, and rule 7: forgetting clears the doubt
            return {"y": Val(x.state)}
        if self.y is None:
            self.y = x.v
        else:
            m = k - self.seen  # riding through is no doubt: the ticks it missed decay too
            self.y = self.a**m * self.y + (1 - self.a**m) * x.v
        self.seen = k
        settling = self.doubt is not None and k - self.doubt <= self.s["settle"]  # the settle ticks after it
        if x.state == UNCERTAIN:
            self.doubt = k
        return {"y": Val(UNCERTAIN if x.state == UNCERTAIN or settling else GOOD, self.y)}

    def gap(self, k):
        self.y, self.doubt = None, None


class Counted(Block):
    """A block whose memory has no end: it gives `elapsed`, `doubtful` and `gaps` (section 7, Counters)."""

    def __init__(self, *a):
        super().__init__(*a)
        self.since, self.doubtful = None, 0  # the tick the count is from; the ticks of it not good
        self.gaps, self.gap_at = 0, None  # the gaps at or after that tick; the tick of the last gap

    def count_from(self, k):
        self.since, self.doubtful = k, 0
        self.gaps = int(self.gap_at == k)

    def counters(self, k, not_good):
        if self.since is None:
            return {"elapsed": Val(GOOD, 0.0), "doubtful": Val(GOOD, 0.0), "gaps": Val(GOOD, 0.0)}
        self.doubtful += bool(not_good)
        return {
            "elapsed": Val(GOOD, (k - self.since + 1) * self.period),
            "doubtful": Val(GOOD, self.doubtful * self.period),
            "gaps": Val(GOOD, float(self.gaps)),
        }

    def gap(self, k):
        self.gaps, self.gap_at = self.gaps + 1, k


COUNTERS = {"elapsed": NUMBER, "doubtful": NUMBER, "gaps": NUMBER}


class Hysteresis(Counted):
    """Section 7.5."""

    settings = {"rise": ("number", True, None), "fall": ("number", True, None), "initial": ("bool", False, None)}
    ports = {"x": (NUMBER, True, True)}
    outputs = {"y": BOOLEAN} | COUNTERS

    def __init__(self, *a):
        super().__init__(*a)
        if not self.s["rise"] > self.s["fall"]:
            raise CompileError("rise is more than fall")
        self.on = self.s["initial"]

    def output(self, k, t, ins):
        x = ins["x"]
        was = self.on
        if usable(x) and (x.v >= self.s["rise"] or x.v <= self.s["fall"]):
            self.on = x.v >= self.s["rise"]
        if self.since is None or self.on != was:  # rule 4: from the tick its value last changed
            self.count_from(k)
        if not usable(x):
            y = Val(x.state)
        else:
            y = Val(NOT_READY) if self.on is None else Val(x.state, self.on)
        return {"y": y} | self.counters(k, x.state != GOOD)


class HeldFor(Counted):
    """Section 7.6 rule 1."""

    settings = {
        "time": ("ticks", True, None),
        "on_bad": ("choice", True, ("reset", "hold")),
        "hold_limit": ("ticks", False, None),
    }
    ports = {"x": (BOOLEAN, True, True)}
    outputs = {"y": BOOLEAN} | COUNTERS

    def __init__(self, *a):
        super().__init__(*a)
        if (self.s["on_bad"] == "hold") != (self.s["hold_limit"] is not None):
            raise CompileError("hold_limit is given with on_bad: hold, and only then")
        self.stretch = 0

    def output(self, k, t, ins):
        x = ins["x"]
        if usable(x):
            self.stretch = 0
            if not x.v:
                self.since = None
                y = Val(x.state, False)
            else:
                if self.since is None:
                    self.count_from(k)
                y = Val(x.state, k - self.since > self.s["time"])
        else:
            self.stretch += 1
            if self.s["on_bad"] == "reset" or self.since is None or self.stretch > self.s["hold_limit"]:
                self.since = None
                y = Val(x.state)
            else:
                y = Val(UNCERTAIN, k - self.since > self.s["time"])
        return {"y": y} | self.counters(k, x.state != GOOD)

    def gap(self, k):
        super().gap(k)
        self.since, self.stretch = None, 0


class SinceTrue(Counted):
    """Section 7.6 rule 2."""

    settings = {"time": ("ticks", True, None), "on_bad": ("choice", True, ("assume_false", "unknown"))}
    ports = {"x": (BOOLEAN, True, True)}
    outputs = {"y": BOOLEAN} | COUNTERS

    def output(self, k, t, ins):
        x = ins["x"]
        if self.since is None or (usable(x) and x.v):
            self.count_from(k)  # the clock is set
        late = k - self.since > self.s["time"]
        if usable(x):
            y = Val(x.state, late)
        else:
            y = Val(UNCERTAIN, late) if self.s["on_bad"] == "assume_false" else Val(x.state)
        return {"y": y} | self.counters(k, x.state != GOOD)

    def gap(self, k):
        super().gap(k)
        self.since = None  # the clock is set to the gap's tick, when it runs


class Latch(Counted):
    """Section 7.6 rule 3."""

    ports = {"set": (BOOLEAN, True, True), "reset": (BOOLEAN, False, True)}
    outputs = {"y": BOOLEAN} | COUNTERS

    def __init__(self, *a):
        super().__init__(*a)
        self.on = False

    def output(self, k, t, ins):
        s, r = ins["set"], ins.get("reset")
        was = self.on
        if self.since is None:
            self.count_from(k)
        if r is not None and usable(r) and r.v:
            self.on = False
            self.count_from(k)
            y = Val(r.state, False)
        elif self.on:
            y = Val(GOOD, True)
        elif usable(s) and s.v:
            self.on = True
            y = Val(s.state, True)
        elif usable(s):
            y = Val(s.state, False)
        else:
            y = Val(s.state)
        return {"y": y} | self.counters(k, not was and s.state != GOOD)


class Integrate(Block):
    """Section 7.7."""

    settings = {"per": ("seconds", False, Fraction(1)), "max_missed": ("ticks", False, None)}
    ports = {"x": (NUMBER, True, True), "reset": (BOOLEAN, False, True)}
    outputs = dict.fromkeys(("y", "missed", "doubtful", "elapsed", "gaps"), NUMBER)

    def __init__(self, *a):
        super().__init__(*a)
        if self.s["per"] <= 0:
            raise CompileError("per is more than zero")
        self.total, self.ran, self.missed, self.doubtful, self.gaps = 0.0, 0, 0, 0, 0
        self.gap_at = None  # the tick of the last gap

    def output(self, k, t, ins):
        x, r = ins["x"], ins.get("reset")
        resetting = r is not None and usable(r) and r.v
        if resetting:
            self.total, self.ran, self.missed, self.doubtful = 0.0, 0, 0, 0
            self.gaps = int(self.gap_at == k)  # a gap at the tick it counts from is counted
        self.ran += 1
        if usable(x):
            self.total += x.v * self.period / float(self.s["per"])
            self.doubtful += x.state == UNCERTAIN
        else:
            self.missed += 1
        limit = self.s["max_missed"]
        if limit is not None and self.missed > limit:  # rule 2
            y = Val(BAD)
        elif x.state == UNCERTAIN or (resetting and r.state == UNCERTAIN):
            y = Val(UNCERTAIN, self.total)
        else:
            y = Val(GOOD, self.total)
        return {
            "y": y,
            "missed": Val(GOOD, self.missed * self.period),
            "doubtful": Val(GOOD, self.doubtful * self.period),
            "elapsed": Val(GOOD, self.ran * self.period),
            "gaps": Val(GOOD, float(self.gaps)),
        }

    def gap(self, k):
        self.gaps, self.gap_at = self.gaps + 1, k


# ---------------------------------------------------------------- models (4 rule 9)


class Model:
    """A state, a step over one period, and outputs from the state and the inputs."""

    params: dict = {}
    inputs: tuple = ()
    states: tuple = ()
    outputs: tuple = ()
    reads_now: frozenset = frozenset()  # the inputs its outputs read: those are direct
    tau = None  # its slowest time constant, in seconds, if its memory fades
    limit = math.inf  # the longest step it is stable at

    def initial(self):
        raise NotImplementedError

    def step(self, x, u, dt):
        raise NotImplementedError

    def give(self, x, u):
        return dict(zip(self.outputs, x, strict=True))

    def sensitivity(self, x, u, dt):
        """How the stepped state moves with the state it was stepped from: rows by stepped state."""
        raise NotImplementedError


class ThermalMass(Model):
    params = {
        "thermal_mass": ("number", True, None),
        "heat_transfer": ("number", True, None),
        "initial": ("number", True, None),
    }
    inputs, states, outputs = ("power", "ambient"), ("temp",), ("temp",)

    def __init__(self, p):
        self.c, self.h, self.t0 = float(p["thermal_mass"]), float(p["heat_transfer"]), float(p["initial"])
        if self.c <= 0 or self.h <= 0:
            raise CompileError("thermal_mass and heat_transfer are more than zero")
        self.tau = self.c / self.h
        self.limit = 2.785 * self.tau

    def initial(self):
        return [self.t0]

    def step(self, x, u, dt):  # classical fourth-order Runge-Kutta, inputs held
        def rate(temp):
            return (u["power"] - self.h * (temp - u["ambient"])) / self.c

        k1 = rate(x[0])
        k2 = rate(x[0] + dt / 2 * k1)
        k3 = rate(x[0] + dt / 2 * k2)
        k4 = rate(x[0] + dt * k3)
        return [x[0] + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)]

    def sensitivity(self, x, u, dt):
        z = -dt * self.h / self.c
        return [[1 + z + z**2 / 2 + z**3 / 6 + z**4 / 24]]


class StateSpace(Model):
    params = {
        "A": ("matrix", True, None),
        "B": ("numbers", True, None),
        "C": ("numbers", True, None),
        "D": ("number", False, 0.0),
        "initial": ("numbers", False, None),
    }
    inputs, outputs = ("u",), ("y",)

    def __init__(self, p):
        n = len(p["B"])
        self.a, self.b, self.c, self.d = p["A"], p["B"], p["C"], float(p["D"])
        self.x0 = [float(v) for v in (p["initial"] or [0.0] * n)]
        if len(self.a) != n or len(self.c) != n or len(self.x0) != n:
            raise CompileError("A, B, C and initial are of one size")
        self.states = tuple(f"x{i}" for i in range(n))
        self.reads_now = frozenset({"u"}) if self.d != 0.0 else frozenset()

    def initial(self):
        return list(self.x0)

    def step(self, x, u, dt):
        return [
            sum(a * xi for a, xi in zip(row, x, strict=True)) + b * u["u"]
            for row, b in zip(self.a, self.b, strict=True)
        ]

    def give(self, x, u):
        return {"y": sum(c * xi for c, xi in zip(self.c, x, strict=True)) + (self.d * u["u"] if self.d else 0.0)}

    def sensitivity(self, x, u, dt):
        return [list(row) for row in self.a]


MODELS = {"thermal_mass": ThermalMass, "state_space": StateSpace}


def stepped(model, x, u, period, substeps):
    for _ in range(substeps):
        x = model.step(x, u, period / substeps)
    return x


MODEL_SETTINGS = {"ride_through": ("ticks", False, 0), "settle": ("ticks", False, None), "substeps": ("int", False, 1)}


class ModelBlock(Block):
    """Section 7.8."""

    model_type = None

    def __init__(self, *a):
        super().__init__(*a)
        self.model = MODELS[self.model_type]({name: self.s[name] for name in MODELS[self.model_type].params})
        if self.s["substeps"] < 1:
            raise CompileError("substeps is at least 1")
        if self.period / self.s["substeps"] > self.model.limit:  # rule 7
            raise CompileError(
                f"a step of {self.period / self.s['substeps']:g} s is longer than this model is stable at "
                f"({self.model.limit:g} s): raise substeps"
            )
        self.settle_given = self.s["settle"] is not None  # rule 8 needs the author's, on a loop
        if self.s["settle"] is None and self.model.tau is not None:
            self.s["settle"] = round_up(3 * self.model.tau / self.period)
        self.ports = {name: (NUMBER, True, name in self.model.reads_now) for name in self.model.inputs}
        self.outputs = dict.fromkeys(self.model.outputs, NUMBER) | COUNTERS
        self.x = self.model.initial()
        self.last = {}  # input -> (its last usable value, the tick of it)
        self.doubt = None  # rule 6: its own. On a loop the engine gives it the loop's before each tick
        self.doubtful, self.gaps = 0, 0
        self.on_loop = False

    def output(self, k, t, ins):
        u, state = {}, GOOD
        for name in self.model.reads_now:  # rule 5
            v = ins[name]
            if usable(v):
                u[name] = v.v
                if v.state == UNCERTAIN:
                    state = UNCERTAIN  # rule D
            else:
                u[name] = self.last[name][0] if name in self.last else 0.0
                state = UNCERTAIN
        settle = self.s["settle"]
        if settle is not None and self.doubt is not None and self.doubt < k <= self.doubt + settle:  # rule 6
            state = UNCERTAIN
        out = {name: Val(state, value) for name, value in self.model.give(self.x, u).items()}
        out["elapsed"] = Val(GOOD, (k + 1) * self.period)
        out["doubtful"] = Val(GOOD, self.doubtful * self.period)  # of the steps before this tick
        out["gaps"] = Val(GOOD, float(self.gaps))
        return out

    def update(self, k, ins):
        u, held, uncertain = {}, False, False
        for name in self.model.inputs:
            v = ins[name]
            if usable(v):
                u[name], self.last[name] = v.v, (v.v, k)
                uncertain = uncertain or v.state == UNCERTAIN
            elif name in self.last and k - self.last[name][1] <= self.s["ride_through"]:  # rule 4
                u[name], held = self.last[name][0], True
        stepped = len(u) == len(self.model.inputs)
        if stepped:
            self.x = self.model_step(u)
        failed = held or not stepped
        if failed or uncertain:
            self.doubtful += 1
            if not self.on_loop:
                self.doubt = k

    def model_step(self, u):
        return stepped(self.model, self.x, u, self.period, self.s["substeps"])

    def gap(self, k):
        self.doubt = k - 1  # uncertain from the gap's tick
        self.gaps += 1
        return True


class ThermalMassBlock(ModelBlock):
    model_type = "thermal_mass"
    outputs = {"temp": NUMBER} | COUNTERS
    settings = ThermalMass.params | MODEL_SETTINGS


class StateSpaceBlock(ModelBlock):
    model_type = "state_space"
    outputs = {"y": NUMBER} | COUNTERS
    settings = StateSpace.params | MODEL_SETTINGS


# ---------------------------------------------------------------- the estimator


class Estimator(Block):
    """Section 7.9."""

    settings = {
        "model": ("map", True, None),
        "q": ("map", True, None),
        "p0": ("map", True, None),
        "measure": ("map", True, None),
        "gate": ("number", False, None),
        "sigma_max": ("map", False, None),
        "use_uncertain": ("bool", False, False),
        "substeps": ("int", False, 1),
    }

    def __init__(self, *a):
        super().__init__(*a)
        spec = dict(self.s["model"])
        kind = spec.pop("type", None)
        if kind not in MODELS:
            raise CompileError(f"model type {kind!r} is not a model")
        self.model = MODELS[kind](read_settings("model", MODELS[kind].params, spec, None))
        if self.s["substeps"] < 1 or self.period / self.s["substeps"] > self.model.limit:
            raise CompileError("the step is longer than the model is stable at: raise substeps")
        self.names = list(self.model.states)
        n = len(self.names)

        def per_state(setting, least, strict, required=True):
            given = self.s[setting] or {}
            if set(given) - set(self.names) or (required and set(given) != set(self.names)):
                raise CompileError(f"{setting} names each state: {self.names}")
            for name, value in given.items():
                if not is_number(value) or value < least or (strict and value == least):
                    raise CompileError(f"{setting} for {name!r} is out of range")
            return given

        q, p0 = per_state("q", 0, False), per_state("p0", 0, True)
        self.limits = per_state("sigma_max", 0, False, required=False)
        if self.s["gate"] is not None and self.s["gate"] < 0:
            raise CompileError("gate is not negative")
        self.q = [float(q[name]) * self.period for name in self.names]
        self.p0 = [float(p0[name]) for name in self.names]
        self.meas = {}
        for port, m in self.s["measure"].items():
            if (
                not isinstance(port, str)
                or port in self.model.inputs
                or not isinstance(m, dict)
                or set(m) != {"of", "r"}
            ):
                raise CompileError(f"measure {port!r} is a port of its own, with `of` and `r`")
            if m["of"] not in self.names or not is_number(m["r"]) or m["r"] <= 0:
                raise CompileError(f"measure {port!r}: `of` is a state and `r` is more than zero")
            self.meas[port] = (self.names.index(m["of"]), float(m["r"]))
        if not self.meas:
            raise CompileError("measure names at least one measurement")
        self.ports = {name: (NUMBER, True, True) for name in (*self.model.inputs, *self.meas)}
        self.outputs = dict.fromkeys(self.names, NUMBER)
        self.outputs |= {f"sigma_{name}": NUMBER for name in self.names}
        for port in self.meas:
            self.outputs |= {f"innovation_{port}": NUMBER, f"refused_{port}": NUMBER, f"since_{port}": NUMBER}
        self.x = self.model.initial()
        self.p = [[self.p0[i] if i == j else 0.0 for j in range(n)] for i in range(n)]
        self.considered = dict.fromkeys(self.meas)  # the sample time last considered, per port
        self.used_at = dict.fromkeys(self.meas)  # the sample time last used, per port
        self.refused = dict.fromkeys(self.meas, 0)
        self.last_u = {}

    def _predict(self, u):
        n, sub = len(self.x), self.s["substeps"]
        for _ in range(sub):  # the state and its covariance, a sub-step at a time
            f = self.model.sensitivity(self.x, u, self.period / sub)
            fp = [[sum(f[i][m] * self.p[m][j] for m in range(n)) for j in range(n)] for i in range(n)]
            self.p = [[sum(fp[i][m] * f[j][m] for m in range(n)) for j in range(n)] for i in range(n)]
            self.x = self.model.step(self.x, u, self.period / sub)

    def output(self, k, t, ins):
        n = len(self.names)
        if k > 0:  # rule 2: from the tick before to this one, on the inputs as they were then
            if len(self.last_u) == len(self.model.inputs):
                self._predict(dict(self.last_u))
            for i in range(n):
                self.p[i][i] += self.q[i]
        coasting = False
        for name in self.model.inputs:
            if usable(ins[name]):
                self.last_u[name] = ins[name].v
            else:
                coasting = True
        out = {}
        for port, (i, r) in self.meas.items():  # rules 3 and 4
            z = ins[port]
            out[f"innovation_{port}"] = Val(NOT_READY)
            takes = z.state == GOOD or (z.state == UNCERTAIN and self.s["use_uncertain"])
            if takes and z.at is not None and (self.considered[port] is None or z.at > self.considered[port]):
                self.considered[port] = z.at
                innovation, s = z.v - self.x[i], self.p[i][i] + r
                out[f"innovation_{port}"] = Val(GOOD, innovation)
                if self.s["gate"] is not None and abs(innovation) > self.s["gate"] * math.sqrt(s):
                    self.refused[port] += 1
                else:
                    g = [self.p[j][i] / s for j in range(n)]
                    row = list(self.p[i])
                    self.x = [xj + gj * innovation for xj, gj in zip(self.x, g, strict=True)]
                    self.p = [[self.p[a][b] - g[a] * row[b] for b in range(n)] for a in range(n)]
                    self.used_at[port] = z.at
            out[f"refused_{port}"] = Val(GOOD, float(self.refused[port]))
            out[f"since_{port}"] = (
                Val(NOT_READY) if self.used_at[port] is None else Val(GOOD, max(0, t - self.used_at[port]) / NS)
            )
        for i, name in enumerate(self.names):  # rule 5
            sigma = math.sqrt(max(self.p[i][i], 0.0))
            wide = name in self.limits and sigma > self.limits[name]
            state = UNCERTAIN if coasting or wide else GOOD
            out[name], out[f"sigma_{name}"] = Val(state, self.x[i]), Val(state, sigma)
        return out

    def gap(self, k):
        for i in range(len(self.names)):
            self.p[i][i] += self.p0[i]

    def forget_times(self):
        self.considered = dict.fromkeys(self.meas)
        self.used_at = dict.fromkeys(self.meas)


CATALOGUE = {
    "formula": FormulaBlock,
    "all_good": AllGood,
    "delay": Delay,
    "window": Window,
    "deadband": Deadband,
    "lowpass": Lowpass,
    "hysteresis": Hysteresis,
    "held_for": HeldFor,
    "since_true": SinceTrue,
    "latch": Latch,
    "integrate": Integrate,
    "thermal_mass": ThermalMassBlock,
    "state_space": StateSpaceBlock,
    "estimator": Estimator,
}

_GRAPH_KEYS = {"period", "max_catch_up", "max_waiting", "inputs", "blocks"}
_BLOCK_KEYS = {"id", "type", "in", "settings", "out", "fallback"}
_INPUT_KEYS = {"type", "unit", "max_age", "max_ahead", "initial"}


def _type_of(constant):
    return BOOLEAN if isinstance(constant, bool) else NUMBER


def _is_constant(value):
    return isinstance(value, bool) or is_number(value)


# ---------------------------------------------------------------- the engine


class Engine:
    def __init__(self, graph):
        if not isinstance(graph, dict) or set(graph) - _GRAPH_KEYS:
            raise CompileError(f"unknown key(s) in the graph: {sorted(set(graph) - _GRAPH_KEYS)}")
        if "period" not in graph:
            raise CompileError("a graph states its period")
        period = length(graph["period"])
        if period <= 0:
            raise CompileError("the period is more than zero")
        self.period = nanoseconds(graph["period"])  # every time in the engine is whole nanoseconds (6 rule 2)
        self.max_catch_up = graph.get("max_catch_up", 100)
        if isinstance(self.max_catch_up, bool) or not isinstance(self.max_catch_up, int) or self.max_catch_up < 1:
            raise CompileError("max_catch_up is a whole number, at least 1")
        self.max_waiting = graph.get("max_waiting", 1024)  # 6 rule 8
        if isinstance(self.max_waiting, bool) or not isinstance(self.max_waiting, int) or self.max_waiting < 1:
            raise CompileError("max_waiting is a whole number, at least 1")

        self.inputs = {}
        for name, spec in (graph.get("inputs") or {}).items():
            where, spec = f"input {name}", spec or {}
            if not isinstance(name, str) or not name:
                raise CompileError(f"{where}: its name is text")
            if set(spec) - _INPUT_KEYS:
                raise CompileError(f"{where}: unknown key(s) {sorted(set(spec) - _INPUT_KEYS)}")
            kind = spec.get("type", NUMBER)
            if kind not in (NUMBER, BOOLEAN):
                raise CompileError(f"{where}: type is number or boolean")
            if "max_age" not in spec:
                raise CompileError(f"{where}: max_age is required: a length of time, or none")
            try:
                max_age = math.inf if spec["max_age"] == "none" else nanoseconds(spec["max_age"])
            except CompileError as exc:
                raise CompileError(f"{where}: max_age: {exc}") from exc
            initial = spec.get("initial")
            if initial is not None and (not _is_constant(initial) or _type_of(initial) != kind):
                raise CompileError(f"{where}: its initial value is a finite {kind}")
            try:
                max_ahead = nanoseconds(spec["max_ahead"]) if "max_ahead" in spec else self.period
            except CompileError as exc:
                raise CompileError(f"{where}: max_ahead: {exc}") from exc
            if 2 * max_age < self.period or 2 * max_ahead < self.period:  # 7.2, and 6 rule 8
                raise CompileError(f"{where}: max_age and max_ahead are not less than half a period")
            self.inputs[name] = {"type": kind, "max_age": max_age, "max_ahead": max_ahead, "initial": initial}

        specs = graph.get("blocks") or []
        ids = [b.get("id") if isinstance(b, dict) else None for b in specs]
        if not all(isinstance(i, str) and i for i in ids) or len(set(ids)) != len(ids):
            raise CompileError("every block has an id of its own, which is text")
        by_id = {b["id"]: b for b in specs}

        # The blocks as configured, and what each publishes.
        self.blocks, writer = {}, {}
        for b in specs:
            where = f"block {b['id']}"
            if set(b) - _BLOCK_KEYS:
                raise CompileError(f"{where}: unknown key(s) {sorted(set(b) - _BLOCK_KEYS)}")
            if b.get("type") not in CATALOGUE:
                raise CompileError(f"{where}: unknown type {b.get('type')!r}")
            cls = CATALOGUE[b["type"]]
            try:
                block = cls(read_settings(where, cls.settings, b.get("settings") or {}, period), period)  # in seconds
            except CompileError as exc:
                raise CompileError(str(exc) if str(exc).startswith(where) else f"{where}: {exc}") from exc
            self.blocks[b["id"]] = block
            for port, signal in (b.get("out") or {}).items():
                if port not in block.outputs:
                    raise CompileError(f"{where}: no output {port!r}")
                if not isinstance(signal, str) or not signal:
                    raise CompileError(f"{where}: output {port!r} needs a signal name")
                if signal in writer or signal in self.inputs:
                    raise CompileError(f"{where}: {signal} already has a writer")
                writer[signal] = (b["id"], port)
        self.published = dict(writer)
        dotted = {f"{bid}.{port}": (bid, port) for bid, block in self.blocks.items() for port in block.outputs}
        for name in (*self.inputs, *self.published):  # 9 rule 2
            if name in dotted:
                raise CompileError(
                    f"{name} is the name of an output of block {dotted[name][0]}, and cannot name anything else"
                )
        writer |= dotted

        # Wiring, and which inputs are direct.
        self.wiring, direct, every = {}, {}, {}
        for b in specs:
            bid, where, block, given = b["id"], f"block {b['id']}", self.blocks[b["id"]], b.get("in") or {}
            if block.ports is None:
                if not given:
                    raise CompileError(f"{where}: needs at least one input")
            else:
                if set(given) - set(block.ports):
                    raise CompileError(f"{where}: unknown input(s) {sorted(set(given) - set(block.ports))}")
                missing = [p for p, (_, required, _) in block.ports.items() if required and p not in given]
                if missing:
                    raise CompileError(f"{where}: missing input(s) {missing}")
            wires, direct[bid], every[bid] = {}, set(), set()
            for port, ref in given.items():
                is_direct = True if block.ports is None else block.ports[port][2]
                if isinstance(ref, bool) or isinstance(ref, (int, float)):
                    if not _is_constant(ref):
                        raise CompileError(f"{where}: the constant on {port!r} is not finite")
                    wires[port] = ("const", ref if isinstance(ref, bool) else float(ref))
                elif isinstance(ref, str) and ref in self.inputs:
                    wires[port] = ("input", ref)
                elif isinstance(ref, str) and ref in writer:
                    wires[port] = ("block", writer[ref], is_direct)
                    every[bid].add(writer[ref][0])
                    if is_direct:
                        direct[bid].add(writer[ref][0])
                else:
                    raise CompileError(f"{where}: {ref!r} on {port!r} is neither an input nor a block's output")
            self.wiring[bid] = wires
            if isinstance(block, FormulaBlock):
                try:
                    block.wired([port for port, src in wires.items() if src[0] != "const"])
                except CompileError as exc:
                    raise CompileError(f"{where}: {exc}") from exc

        self.order = self._order(direct)
        self._loops(every)

        # Types, in an order where they are known.
        self.types = {
            (bid, port): kind
            for bid, blk in self.blocks.items()
            if not blk.typed_late
            for port, kind in blk.outputs.items()
        }
        pending = list(by_id)
        while pending:
            progressed = False
            for bid in list(pending):
                block, where = self.blocks[bid], f"block {bid}"
                in_types, ready = {}, True
                for port, src in self.wiring[bid].items():
                    if src[0] == "const":
                        in_types[port] = _type_of(src[1])
                    elif src[0] == "input":
                        in_types[port] = self.inputs[src[1]]["type"]
                    elif src[1] in self.types:
                        in_types[port] = self.types[src[1]]
                    elif isinstance(block, Delay) and block.s["initial"] is not None:
                        continue  # a delay on a loop takes its type from its initial value
                    else:
                        ready = False
                if not ready:
                    continue
                for port, kind in in_types.items():
                    want = block.ports[port][0] if block.ports is not None else None
                    if want is not None and kind != want:
                        raise CompileError(f"{where}: input {port!r} takes a {want}, and was given a {kind}")
                try:
                    block.bind(in_types)
                except CompileError as exc:
                    raise CompileError(f"{where}: {exc}") from exc
                for port, kind in block.outputs.items():
                    self.types[(bid, port)] = kind
                pending.remove(bid)
                progressed = True
            if not progressed:
                raise CompileError(f"the types of blocks {sorted(pending)} cannot be worked out")
        self.fallback = {}
        for bid, block in self.blocks.items():
            where = f"block {bid}"
            for port, src in self.wiring[bid].items():
                if isinstance(block, Delay) and src[0] == "block" and self.types[src[1]] != self.types[(bid, "y")]:
                    raise CompileError(f"{where}: its initial value is not of its input's type")
            if isinstance(block, Delay) and block.s["initial"] is None and self._reaches(every, bid, bid):
                raise CompileError(f"{where}: a delay on a loop needs an initial value")  # 5 rule 4
            self.fallback[bid] = dict(by_id[bid].get("fallback") or {})
            for port, value in self.fallback[bid].items():
                if port not in block.outputs:
                    raise CompileError(f"{where}: fallback names no output {port!r}")
                if not _is_constant(value) or _type_of(value) != block.outputs[port]:
                    raise CompileError(f"{where}: the fallback for {port!r} is a finite {block.outputs[port]}")

        self.initial_blocks = copy.deepcopy(self.blocks)
        self.fingerprint = repr(graph)
        self.reset()

    @staticmethod
    def _reaches(edges, start, goal):
        seen, todo = set(), list(edges[start])
        while todo:
            node = todo.pop()
            if node == goal:
                return True
            if node not in seen:
                seen.add(node)
                todo.extend(edges[node])
        return False

    def _loops(self, every):
        """7.8 rule 8: the blocks that each reach every other are a loop; one that holds a model is one block."""
        self.loop_of, self.outside, self.loop_settle = {}, {}, {}
        self.read_in_loop = set()  # the outputs a block of the same loop reads
        for bid in self.blocks:
            if bid in self.loop_of or not self._reaches(every, bid, bid):
                continue
            members = frozenset(
                b for b in self.blocks if b == bid or (self._reaches(every, bid, b) and self._reaches(every, b, bid))
            )
            models = [b for b in sorted(members) if isinstance(self.blocks[b], ModelBlock)]
            if not models:
                continue  # 5 rule 6: no memory that fades, and no rule
            where = f"the loop of blocks {sorted(members)}"
            if not all(self.blocks[b].settle_given for b in models):
                raise CompileError(f"{where}: every model on a loop is given settle")
            settles = {self.blocks[b].s["settle"] for b in models}
            if len(settles) != 1:
                raise CompileError(f"{where}: the models on a loop are all given the same settle")
            settle = settles.pop()
            if any(isinstance(self.blocks[b], Estimator) for b in members):
                raise CompileError(f"{where}: an estimator is not put on a loop that holds a model block")
            memory = {Delay: lambda d: d.s["ticks"], Window: lambda w: w.n, Lowpass: lambda f: f.s["settle"]}
            remembers = [b for b in sorted(members) if type(self.blocks[b]) in memory]
            if sum(memory[type(self.blocks[b])](self.blocks[b]) for b in remembers) > settle:
                raise CompileError(f"{where}: its delays, windows and low-passes add up to more than settle")
            self.loop_settle[members] = settle
            for b in members:
                self.loop_of[b] = members
                self.outside[b] = {
                    port
                    for port, src in self.wiring[b].items()
                    if src[0] == "input" or (src[0] == "block" and src[1][0] not in members)
                }
                self.read_in_loop |= {
                    src[1] for src in self.wiring[b].values() if src[0] == "block" and src[1][0] in members
                }
                if isinstance(self.blocks[b], ModelBlock):
                    self.blocks[b].on_loop = True
                self.blocks[b].loop_settle = settle

    @staticmethod
    def _order(deps):
        """Section 5: one order from the direct inputs, ties by id, loops refused by name."""
        done, out = set(), []
        while len(out) < len(deps):
            ready = sorted(n for n in deps if n not in done and deps[n] <= done)
            if not ready:
                raise CompileError(f"loop of direct inputs among blocks {sorted(set(deps) - done)}")
            out.append(ready[0])
            done.add(ready[0])
        return out

    # ---- state (section 8)

    def reset(self):
        self.blocks = copy.deepcopy(self.initial_blocks)
        self.k = 0  # the next tick to run
        self.zero = None  # the time tick 0 is at, or would be at, in nanoseconds
        self.since = None  # the time the graph has run since: tick 0's, or the last rebase's
        self.last_now = None
        self.standing = {}  # input -> (state, value, time): the write last taken up
        self.pending = {name: [] for name in self.inputs}  # the writes not yet taken up, as made
        self.rebasing = False
        self.thrown = 0  # writes thrown away since the last call that ran a tick
        self.loop_doubt = dict.fromkeys(self.loop_settle)  # 7.8 rule 8: each loop's doubt, a tick
        self.info = None  # what the last call that ran a tick has to say (6 rule 10)

    def save(self):
        return self.fingerprint, copy.deepcopy((self.blocks, self.k, self.loop_doubt))

    def restore(self, saved):
        fingerprint, state = saved
        if fingerprint != self.fingerprint:
            raise ValueError("this state was saved from a different graph")
        if state[1] == 0:  # saved before any tick: a reset, not a gap (8 rule 3)
            return self.reset()
        self.blocks, self.k, self.loop_doubt = copy.deepcopy(state)
        self.rebase()

    def rebase(self):
        """The host's clock has stepped, or a state was restored: the next call is a gap, at any time."""
        self.pending = {name: [] for name in self.inputs}  # 8 rule 5: what was written before is done with
        self.standing = {}  # and nothing stands, from now: a write on the new clock is not judged by the old
        if self.zero is None and self.k == 0:
            return  # nothing has run: the next call runs tick 0, and is no gap
        self.last_now, self.rebasing = None, True

    def write(self, name, state, value=None, at=None):
        """The host writes an input: a state, a value, and a time (6 rule 7). Refusals are rule 11."""
        if name not in self.inputs:
            raise KeyError(f"{name} is not an input of this graph")
        if state not in STATES:
            raise ValueError(f"{state!r} is not a state")
        if isinstance(at, bool) or not isinstance(at, int):
            raise ValueError("a write carries a time, a whole number of nanoseconds")
        if isinstance(at, int) and not -(2**63) <= at < 2**63:
            raise ValueError("a time fits in 64 bits")
        if state in (GOOD, UNCERTAIN):
            if self.inputs[name]["type"] == BOOLEAN and not isinstance(value, bool):
                raise ValueError(f"{name} is a boolean")
            if self.inputs[name]["type"] == NUMBER:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"{name} is a number")
                value = float(value)
        else:
            value = None
        stands = self.standing.get(name)
        if stands is not None and at < stands[2]:  # it can never stand: thrown away as it is made
            self.thrown += 1
            return
        waiting = self.pending[name]
        waiting.append((state, value, at))
        if len(waiting) > self.max_waiting:  # the earliest goes, the earlier written of two with one time
            del waiting[min(range(len(waiting)), key=lambda i: (waiting[i][2], i))]
            self.thrown += 1

    def _take_up(self, t, last):
        """6 rule 8: the writes this tick may see are done with, and the one with the latest time stands."""
        limit = max(t, self.last_now) if last else t  # the last tick of a call sees what the host has in hand
        for name, writes in self.pending.items():
            for write in [w for w in writes if w[2] <= limit]:
                stands = self.standing.get(name)
                if stands is None or write[2] >= stands[2]:  # of two with one time, the later written
                    self.standing[name] = write
            self.pending[name] = [w for w in writes if w[2] > limit]

    def _input(self, name, k, t):
        """Section 7.2."""
        spec = self.inputs[name]
        if name not in self.standing:
            ran = t - self.since
            if spec["initial"] is not None and ran <= spec["max_age"]:
                value = spec["initial"]
                return Val(UNCERTAIN, value if isinstance(value, bool) else float(value))
            return Val(BAD) if ran > spec["max_age"] else Val(NOT_READY)
        state, value, at = self.standing[name]
        if state in (NOT_READY, BAD):
            return Val(state)
        if spec["type"] == NUMBER and not math.isfinite(value):
            return Val(BAD)
        if t - at > spec["max_age"]:
            return Val(BAD)
        return Val(state, value, at)

    # ---- time (section 6)

    def tick(self, now):
        """Run every tick that is due. -> (ticks run, the outputs of the last, or None)."""
        if isinstance(now, bool) or not isinstance(now, int) or not -(2**63) <= now < 2**63:
            raise ValueError("the time passed to tick is a whole number of nanoseconds that fits in 64 bits")
        if self.last_now is not None and now < self.last_now:
            raise ValueError("the time passed to tick does not go backwards")
        self.last_now = now
        for name, writes in self.pending.items():  # rule 8: stamped too far ahead
            self.pending[name] = [w for w in writes if w[2] - now <= self.inputs[name]["max_ahead"]]
            self.thrown += len(writes) - len(self.pending[name])
        if self.zero is None:  # rule 5
            self.zero = self.since = now
        gap = False
        if self.rebasing:  # 8 rule 5: one tick, at the call's time, on what may be another clock
            self.rebasing, gap, due = False, True, 1
            self.zero, self.since = now - self.k * self.period, now
            for block in self.blocks.values():
                block.forget_times()
        else:
            # rule 6: the ticks whose time is no more than half a period after now
            ahead = 2 * now + self.period - 2 * (self.zero + self.k * self.period)
            due = ahead // (2 * self.period) + 1 if ahead >= 0 else 0
            if due == 0:
                self.info = None
                return 0, None
            if due > self.max_catch_up:  # 8 rule 4: a stall. One tick, the last that was due
                gap = True
                self.zero += (due - 1) * self.period
                due = 1
        if gap:
            for bid, block in self.blocks.items():  # 8 rule 6
                if block.gap(self.k) and bid in self.loop_of:  # a model's doubt is its loop's
                    self.loop_doubt[self.loop_of[bid]] = self.k - 1
        out = None
        for i in range(due):
            out = self._run(last=i == due - 1)
        self.info = {
            "gap": gap,
            "tick": self.k - 1,
            "time": self.zero + (self.k - 1) * self.period,
            "thrown": self.thrown,  # since the last call that ran a tick
            "waiting": sum(len(writes) for writes in self.pending.values()),
        }
        self.thrown = 0
        return due, out

    def _run(self, last):
        k, t = self.k, self.zero + self.k * self.period
        self._take_up(t, last)
        inputs = {name: self._input(name, k, t) for name in self.inputs}
        now = {}

        def read(bid, phase_one):
            ins = {}
            for port, src in self.wiring[bid].items():
                if src[0] == "const":
                    ins[port] = Val(GOOD, src[1])
                elif src[0] == "input":
                    ins[port] = inputs[src[1]]
                elif src[2] or not phase_one:
                    ins[port] = now[src[1]]
            return ins

        doubts = set()  # the loops something not good came into at this tick (7.8 rule 8)

        def from_outside(bid, ins, ports):
            if any(ins[port].state != GOOD for port in ports if port in ins and port in self.outside[bid]):
                doubts.add(self.loop_of[bid])

        for bid in self.order:  # first phase
            block, ins = self.blocks[bid], read(bid, True)
            if bid in self.loop_of:
                doubt = self.loop_doubt[self.loop_of[bid]]
                block.loop_doubt = doubt
                if isinstance(block, ModelBlock):
                    block.doubt = doubt
            given = block.output(k, t, ins)
            if bid in self.loop_of:
                from_outside(bid, ins, block.used(ins))
            for port, val in given.items():
                if usable(val) and isinstance(val.v, float) and not math.isfinite(val.v):
                    val = Val(BAD)  # 3 rule 6
                substituted = False
                if not usable(val):
                    val = Val(val.state)
                    if (bid, port) in self.read_in_loop:  # 7.8 rule 8: whatever stands in for it
                        doubts.add(self.loop_of[bid])
                    if port in self.fallback[bid]:  # 7.10
                        substituted = True
                        value = self.fallback[bid][port]
                        val = Val(UNCERTAIN, value if isinstance(value, bool) else float(value))
                keeps = block.own_at and usable(val) and not substituted  # 3 rule 7
                now[(bid, port)] = Val(val.state, val.v, val.at if keeps else t)
        for bid in self.order:  # second phase
            block, ins = self.blocks[bid], read(bid, False)
            block.update(k, ins)
            if bid in self.loop_of:
                from_outside(bid, ins, {p for p in ins if block.ports is not None and not block.ports[p][2]})
        for loop in doubts:
            self.loop_doubt[loop] = k
        self.k = k + 1
        return {sig: now[w] for sig, w in self.published.items()}

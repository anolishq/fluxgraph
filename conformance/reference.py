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
import sys
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
    if whole and seconds_ * NS >= 2**63:
        raise CompileError(f"{text!r} does not fit in 64 bits, in nanoseconds")
    return seconds_


def nanoseconds(text):
    return int(length(text) * NS)


def seconds(text):
    return float(length(text))


MOST = 2**31 - 1  # Appendix A: the most a count the author gives may be


def round_up(x):
    """7.8 rule 6: a named model's settle, which is not exact: the least whole number not less than x - 1e-9."""
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
                if value > MOST:
                    raise CompileError(f"is at most {MOST}")
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
            elif kind == "rows":
                rows = value if isinstance(value, list) else []
                if not rows or not all(
                    isinstance(r, list) and r and len(r) == len(rows[0]) and all(map(is_number, r)) for r in rows
                ):
                    raise CompileError("is a list of rows of finite numbers, each as long as the others")
            elif kind == "names":
                if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
                    raise CompileError("is a list of names")
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

    def gap(self, k, n):
        """Section 8 rule 6: ticks went by unseen. k is the tick about to run; n how many did not, or None if
        nobody knows, which is more than anything a block counts."""

    def forget_times(self):
        """Section 8 rule 5: a rebase. The clock may be another clock: forget every sample time."""


class FormulaBlock(Block):
    settings = {"expr": ("str", True, None), "sample_of": ("str", False, None)}
    ports = None
    typed_late = True
    own_at = True

    def bind(self, in_types):
        limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(limit, 10000))  # Appendix A: a formula nested 100 deep is read
        try:
            self.formula = Formula(self.s["expr"], in_types)
        except RecursionError:  # and an engine may refuse one nested deeper than it can read
            raise CompileError("the formula is nested too deep") from None
        finally:
            sys.setrecursionlimit(limit)
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

    def gap(self, k, n):
        for _ in range(self.s["ticks"] if n is None else min(n, self.s["ticks"])):
            self.update(k, {"x": Val(NOT_READY)})

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
        # 6 rule 3: exactly, from the decimal as it is written
        self.need = max(1, math.ceil(Fraction(str(self.s["min_good"])) * self.n))
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

    def gap(self, k, n):
        for _ in range(self.n if n is None else min(n, self.n)):
            self.buf.append(Val(NOT_READY))

    def forget_times(self):
        self.last_at = None
        if self.s["only_new"]:  # it cannot tell a sample from before the rebase from one written again after
            self.buf.clear()


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

    def gap(self, k, n):
        if self.held is not None and (n is None or k - 1 - self.seen > self.s["ride_through"]):
            self.held = None


class RateLimit(Deadband):
    """Section 7.4 rules 9 to 11. What it holds, and when it forgets, are a deadband's."""

    settings = {
        "up": ("number", True, None),
        "down": ("number", False, None),
        "ride_through": ("ticks", False, 0),
        "initial": ("number", False, None),
    }
    outputs = {"y": NUMBER, "limited": BOOLEAN}

    def __init__(self, *a):
        Block.__init__(self, *a)
        if self.s["down"] is None:
            self.s["down"] = self.s["up"]
        if self.s["up"] < 0 or self.s["down"] < 0:
            raise CompileError("up and down are not negative")
        self.start = None if self.s["initial"] is None else float(self.s["initial"])
        self.held, self.seen = self.start, None  # rule 9: it holds `initial` from the start

    def output(self, k, t, ins):
        x = ins["x"]
        if usable(x):
            if self.held is not None:
                reach = (self.s["up"] if x.v > self.held else self.s["down"]) * self.period
                if abs(x.v - self.held) > reach:  # rule 9: one period's worth, whatever went before
                    x = Val(x.state, self.held + math.copysign(reach, x.v - self.held))
            limited = Val(x.state, x.v != ins["x"].v)
            self.held, self.seen = x.v, k
            return {"y": Val(x.state, self.held), "limited": limited}
        riding = self.seen is not None and k - self.seen <= self.s["ride_through"]
        if riding:
            return {"y": Val(UNCERTAIN, self.held), "limited": Val(x.state)}
        self.held, self.seen = self.start, None  # rule 11: forgotten, it holds `initial` again, if it has one
        return {"y": Val(x.state), "limited": Val(x.state)}

    def gap(self, k, n):
        if self.seen is not None and (n is None or k - 1 - self.seen > self.s["ride_through"]):
            self.held, self.seen = self.start, None


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
            self.s["settle"] = math.ceil(3 * self.s["tau"] / a[1])  # 6 rule 3: exactly
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

    def gap(self, k, n):
        if self.y is not None and (n is None or k - 1 - self.seen > self.s["ride_through"]):
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

    def gap(self, k, n):
        self.gaps, self.gap_at = self.gaps + 1, k
        if n and self.since is not None and self.unseen():
            self.doubtful += n  # on a tick nobody saw, no input was good

    def unseen(self):
        """Whether a tick with its input not good would have been counted as doubtful."""
        return True


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

    def gap(self, k, n):
        if n != 0:  # a gap that passed over no tick does nothing to it
            self.stretch = self.stretch + n if n is not None and self.s["on_bad"] == "hold" else None
            if self.stretch is None or self.stretch > self.s["hold_limit"]:
                self.since, self.stretch = None, 0  # the timer stops, as on an unusable input
        super().gap(k, n)


class SinceTrue(Counted):
    """Section 7.6 rule 2."""

    settings = {"time": ("ticks", True, None), "on_bad": ("choice", True, ("assume_false", "unknown"))}
    ports = {"x": (BOOLEAN, True, True)}
    outputs = {"y": BOOLEAN} | COUNTERS

    long_ago = False  # after a gap of no known length: the input was last true longer ago than `time`

    def output(self, k, t, ins):
        x = ins["x"]
        if usable(x) and x.v:
            self.long_ago = False
        if self.since is None or (usable(x) and x.v):
            self.count_from(k)  # the clock is set
        late = self.long_ago or k - self.since > self.s["time"]
        if usable(x):
            y = Val(x.state, late)
        else:
            y = Val(UNCERTAIN, late) if self.s["on_bad"] == "assume_false" else Val(x.state)
        return {"y": y} | self.counters(k, x.state != GOOD)

    def gap(self, k, n):
        super().gap(k, n)
        if n is None:
            self.since, self.long_ago = None, True  # the counts start again at the gap's tick


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

    def unseen(self):
        return not self.on


class Integrate(Block):
    """Section 7.7."""

    settings = {"per": ("seconds", False, Fraction(1)), "max_missed": ("ticks", False, None)}
    ports = {"x": (NUMBER, True, True), "reset": (BOOLEAN, False, True)}
    outputs = dict.fromkeys(("y", "missed", "doubtful", "elapsed", "gaps"), NUMBER)

    def __init__(self, *a):
        super().__init__(*a)
        if self.s["per"] <= 0:
            raise CompileError("per is more than zero")
        self.ratio = float(a[1] / self.s["per"])  # Appendix A: worked once, exactly
        self.total, self.ran, self.missed, self.doubtful, self.gaps = 0.0, 0, 0, 0, 0
        self.gap_at = None  # the tick of the last gap
        self.lost = False  # it has missed nobody knows how much: more than max_missed, if that is given

    def output(self, k, t, ins):
        x, r = ins["x"], ins.get("reset")
        resetting = r is not None and usable(r) and r.v
        if resetting:
            self.total, self.ran, self.missed, self.doubtful, self.lost = 0.0, 0, 0, 0, False
            self.gaps = int(self.gap_at == k)  # a gap at the tick it counts from is counted
        self.ran += 1
        if usable(x):
            self.total += x.v * self.ratio
            self.doubtful += x.state == UNCERTAIN
        else:
            self.missed += 1
        limit = self.s["max_missed"]
        if limit is not None and (self.missed > limit or self.lost):  # rule 2
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

    def gap(self, k, n):
        self.gaps, self.gap_at = self.gaps + 1, k
        if n:
            self.ran, self.missed = self.ran + n, self.missed + n
        self.lost = self.lost or n is None


class Pid(Counted):
    """Section 7.7 rules 5 to 11."""

    settings = {
        "kp": ("number", True, None),
        "ki": ("number", False, 0.0),
        "kd": ("number", False, 0.0),
        "filter": ("seconds", False, None),
        "min": ("number", False, None),
        "max": ("number", False, None),
        "applied_within": ("number", False, 0.0),
    }
    ports = {
        "setpoint": (NUMBER, True, True),
        "measurement": (NUMBER, True, True),
        "reset": (BOOLEAN, False, True),
        "applied": (NUMBER, False, False),  # deferred: rule 12
    }
    outputs = {"y": NUMBER, "integral": NUMBER, "limited": BOOLEAN} | COUNTERS

    def __init__(self, *a):
        super().__init__(*a)
        if (self.s["kd"] != 0) != (self.s["filter"] is not None):
            raise CompileError("filter is given when kd is not zero, and only then")
        if self.s["filter"] is not None and self.s["filter"] <= 0:
            raise CompileError("filter is more than zero")
        if self.s["min"] is not None and self.s["max"] is not None and self.s["min"] >= self.s["max"]:
            raise CompileError("min is less than max")
        if self.s["applied_within"] < 0:
            raise CompileError("applied_within is not negative")
        self.a = math.exp(-self.period / float(self.s["filter"])) if self.s["filter"] is not None else 0.0
        self.integral, self.before, self.f = 0.0, None, 0.0  # before: the measurement of the tick before
        self.added = None  # this tick's addition: (the integral before it, the addition, y)

    def output(self, k, t, ins):
        sp, pv, r = ins["setpoint"], ins["measurement"], ins.get("reset")
        resetting = bool(r is not None and usable(r) and r.v)
        if resetting or self.since is None:
            self.count_from(k)
        if resetting:  # rule 10: before this tick's addition
            self.integral, self.before, self.f = 0.0, None, 0.0
        counts = self.counters(k, sp.state != GOOD or pv.state != GOOD)
        state = worst((sp.state, pv.state))
        self.added = None
        if not (usable(sp) and usable(pv)):  # rule 8: no value, and the integral is kept
            self.before, self.f = None, 0.0
            doubted = UNCERTAIN if resetting and r.state == UNCERTAIN else GOOD  # rule 9
            return {"y": Val(state), "limited": Val(state), "integral": Val(doubted, self.integral)} | counts
        if resetting and r.state == UNCERTAIN:
            state = UNCERTAIN
        error = sp.v - pv.v
        if self.before is None:  # rule 7: there is no tick before
            self.f = 0.0
        else:
            self.f = self.a * self.f + (1.0 - self.a) * (pv.v - self.before) / self.period
        self.before = pv.v
        rest = self.s["kp"] * error - self.s["kd"] * self.f
        low, high, add = self.s["min"], self.s["max"], self.s["ki"] * error * self.period
        with_it, cut, was = rest + self.integral + add, False, self.integral
        if high is not None and add > 0 and with_it > high:  # rule 6: cut short at the limit
            self.integral, cut = max(self.integral, high - rest), True
        elif low is not None and add < 0 and with_it < low:
            self.integral, cut = min(self.integral, low - rest), True
        else:
            self.integral += add
        y, limited = rest + self.integral, False
        if high is not None and (y > high or (cut and add > 0)):  # cut short, y is the limit itself
            y, limited = float(high), True
        elif low is not None and (y < low or (cut and add < 0)):
            y, limited = float(low), True
        self.added = (was, add, y)
        return {"y": Val(state, y), "limited": Val(state, limited), "integral": Val(state, self.integral)} | counts

    def update(self, k, ins):
        got = ins.get("applied")
        if self.added is None or got is None or not usable(got):
            return
        was, add, y = self.added
        within = self.s["applied_within"]
        if (add > 0 and y - got.v > within) or (add < 0 and got.v - y > within):  # rule 12: it fell short
            self.integral = was

    def gap(self, k, n):
        super().gap(k, n)
        if n != 0:  # 8 rule 6: the derivative starts again, unless no tick was passed over
            self.before, self.f = None, 0.0


# ---------------------------------------------------------------- models (4 rule 9)


def matmul(a, b):
    return [[sum(a[i][m] * b[m][j] for m in range(len(b))) for j in range(len(b[0]))] for i in range(len(a))]


def expm(m):
    """e to a matrix, by scaling, a Taylor series and squaring. Any way to the same number will do (7.8 rule 7).

    Each squaring doubles the rounding error, so it is scaled no further than to a row sum of 2, where the series
    still loses nothing.
    """
    n = len(m)
    norm = max(sum(abs(v) for v in row) for row in m)
    squarings = max(0, math.ceil(math.log2(norm)) - 1) if norm > 0 else 0
    scaled = [[v / 2**squarings for v in row] for row in m]
    out = [[float(i == j) for j in range(n)] for i in range(n)]
    term = [row[:] for row in out]
    for order in range(1, 40):
        term = [[v / order for v in row] for row in matmul(term, scaled)]
        out = [[out[i][j] + term[i][j] for j in range(n)] for i in range(n)]
    for _ in range(squarings):
        out = matmul(out, out)
    return out


def discretise(a, b, dt):
    """dx/dt = Ax + Bu with u held over dt -> x' = Ad x + Bd u, exactly.

    One exponential, of [[A, I], [0, 0]] dt, gives Ad and the integral of exp(A s) over the period; Bd is that
    integral times B. B is kept out of the exponential, so that its size costs Ad nothing.
    """
    n = len(a)
    big = [[v * dt for v in a[i]] + [dt * (i == j) for j in range(n)] for i in range(n)] + [[0.0] * (2 * n)] * n
    e = expm(big)
    return [row[:n] for row in e[:n]], matmul([row[n:] for row in e[:n]], b)


STIFFEST = 100_000.0  # 7.8 rule 7: the most a row of A, summed, times the period, may be


def transpose(m):
    return [list(col) for col in zip(*m, strict=True)]


def discretise_noise(a, q, dt):
    """The integral of exp(A s) Q exp(A' s) over dt, Q the diagonal q: what white noise of those intensities on
    each state has done to the covariance by the end of a step (7.9 rule 2).

    Over a short step h it is a series in h, whose terms are M0 = Q and M(k+1) = A Mk + Mk A', each over
    (k+1)!; and the step is doubled back up: N(2h) = N(h) + F N(h) F', with F = exp(A h).
    """
    n = len(a)
    norm = max(sum(abs(v) for v in row) for row in a) * dt
    doublings = max(0, math.ceil(math.log2(norm))) if norm > 0 else 0
    h = dt / 2**doublings
    term = [[q[i] * h if i == j else 0.0 for j in range(n)] for i in range(n)]
    noise = [row[:] for row in term]
    at = transpose(a)
    for order in range(1, 40):
        left, right = matmul(a, term), matmul(term, at)
        term = [[(left[i][j] + right[i][j]) * h / (order + 1) for j in range(n)] for i in range(n)]
        noise = [[noise[i][j] + term[i][j] for j in range(n)] for i in range(n)]
    f = expm([[v * h for v in row] for row in a])
    for _ in range(doublings):
        carried = matmul(matmul(f, noise), transpose(f))
        noise = [[noise[i][j] + carried[i][j] for j in range(n)] for i in range(n)]
        f = matmul(f, f)
    return noise


def compose(second, first):
    """Two steps as one: each is (F, G, N) for x' = F x + G u and P' = F P F' + N."""
    (f2, g2, n2), (f1, g1, n1) = second, first
    size = len(f1)
    pushed, carried = matmul(f2, g1), matmul(matmul(f2, n1), transpose(f2))
    return (
        matmul(f2, f1),
        [[pushed[i][j] + g2[i][j] for j in range(len(g1[0]))] for i in range(size)],
        [[carried[i][j] + n2[i][j] for j in range(size)] for i in range(size)],
    )


class Model:
    """A linear model (4 rule 9): x' = Ad x + Bd u over one period, and y = C x + D u.

    A subclass says what it is in `build`: its matrices, its initial state and the names of its inputs, states
    and outputs. In continuous time the step over the period is worked out here, exactly, with the inputs held.
    """

    params: dict = {}
    continuous = True
    default_settle = False  # whether `settle` is three of its slowest time constant unless given

    def __init__(self, p, period):
        made = self.build(p)
        self.inputs, self.states, self.outputs = (tuple(made[key]) for key in ("inputs", "states", "outputs"))
        a, b, self.c, self.d = ([[float(v) for v in row] for row in made[key]] for key in "ABCD")
        self.x0 = [float(v) for v in made["initial"]]
        n, m, p_out = len(self.states), len(self.inputs), len(self.outputs)
        sizes = len(a) == n and all(len(row) == n for row in a) and len(b) == n and all(len(row) == m for row in b)
        sizes = sizes and len(self.c) == p_out and all(len(row) == n for row in self.c)
        sizes = sizes and len(self.d) == p_out and all(len(row) == m for row in self.d) and len(self.x0) == n
        if not sizes:  # each list has something in it already: the kinds of the settings see to that
            raise CompileError(
                "A is square, B has a row per state and a column per input, C a row per output "
                "and a column per state, D a row per output and a column per input, and initial "
                "a number per state"
            )
        for names in (self.inputs, self.states, self.outputs):
            if len(set(names)) != len(names) or not all(isinstance(name, str) and name for name in names):
                raise CompileError("the names of a model's inputs, of its states and of its outputs are each distinct")
            if any("." in name for name in names):  # 9 rule 2
                raise CompileError("a name of a model's input, state or output holds no dot")
        if set(self.outputs) & set(COUNTERS):
            raise CompileError(f"a model's output is not named one of {sorted(COUNTERS)}")
        # an input is direct if an output reads it (7.8 rule 2)
        self.reads_now = frozenset(name for j, name in enumerate(self.inputs) if any(row[j] != 0.0 for row in self.d))
        if self.continuous:  # rule 7: how fast it is against the period, by the largest row of A
            stiff = max(sum(abs(v) for v in row) for row in a) * period
            if not stiff <= STIFFEST:
                raise CompileError(
                    f"the model is too fast for this period: the largest sum along a row of A, times the period, "
                    f"is {stiff:g}, and may be {STIFFEST:g} at most. Leave out the state that has settled long "
                    f"before a tick, or put the states in units nearer each other"
                )
        self.ad, self.bd = discretise(a, b, period) if self.continuous else (a, b)
        if not all(math.isfinite(v) for row in (*self.ad, *self.bd) for v in row):
            raise CompileError("the model's step over this period is not finite: it grows too fast for the period")
        self.tau = self.slowest(a, made.get("det")) if self.continuous and self.default_settle else None
        self.a, self.period = a, period

    def noise(self, q):
        """7.9 rule 2: what process noise of intensities q adds to the covariance over one period."""
        if self.continuous:
            return discretise_noise(self.a, q, self.period)
        return [[q[i] * self.period if i == j else 0.0 for j in range(len(q))] for i in range(len(q))]

    def build(self, p):
        raise NotImplementedError

    @staticmethod
    def slowest(a, det):
        """The slowest time constant of one or two states, in seconds, or None if a mode does not decay.

        `det` is A's determinant as the model's own settings give it, with no subtraction to lose a slow rate in.
        """
        if len(a) == 1:
            top = a[0][0]
        else:
            half = (a[0][0] + a[1][1]) / 2
            if half * half <= det:
                top = half  # a pair that swings, or one rate twice
            elif half < 0:
                top = det / (half - math.sqrt(half * half - det))  # the product over the faster: nothing cancels
            else:
                top = half + math.sqrt(half * half - det)
        return -1.0 / top if top < 0 else None

    def initial(self):
        return list(self.x0)

    def step(self, x, u):
        """One period on, with the inputs held."""
        held = [u[name] for name in self.inputs]
        return [
            sum(f * xi for f, xi in zip(row, x, strict=True)) + sum(g * ui for g, ui in zip(gain, held, strict=True))
            for row, gain in zip(self.ad, self.bd, strict=True)
        ]

    def give(self, x, u):
        out = {}
        for name, row, direct in zip(self.outputs, self.c, self.d, strict=True):
            out[name] = sum(c * xi for c, xi in zip(row, x, strict=True))
            out[name] += sum(d * u[port] for d, port in zip(direct, self.inputs, strict=True) if d != 0.0)
        return out


def _positive(p, *names):
    for name in names:
        if not p[name] > 0:
            raise CompileError(f"{name} is more than zero")


def _not_negative(p, *names):
    for name in names:
        if p[name] < 0:
            raise CompileError(f"{name} is not negative")


class Linear(Model):
    params = {
        "A": ("matrix", True, None),
        "B": ("rows", True, None),
        "C": ("rows", True, None),
        "D": ("rows", False, None),
        "initial": ("numbers", False, None),
        "inputs": ("names", False, None),
        "states": ("names", False, None),
        "outputs": ("names", False, None),
    }

    def build(self, p):
        n, m, outs = len(p["A"]), len(p["B"][0]), len(p["C"])

        def names(given, one, many, count):
            return given if given is not None else [one] if count == 1 else [f"{many}{i}" for i in range(count)]

        return {
            "A": p["A"],
            "B": p["B"],
            "C": p["C"],
            "D": p["D"] if p["D"] is not None else [[0.0] * m for _ in range(outs)],
            "initial": p["initial"] if p["initial"] is not None else [0.0] * n,
            "inputs": names(p["inputs"], "u", "u", m),
            "states": names(p["states"], "x0", "x", n),
            "outputs": names(p["outputs"], "y", "y", outs),
        }


class ThermalMass(Model):
    params = {
        "thermal_mass": ("number", True, None),
        "heat_transfer": ("number", True, None),
        "initial": ("number", True, None),
    }
    default_settle = True

    def build(self, p):
        _positive(p, "thermal_mass", "heat_transfer")
        c, h = p["thermal_mass"], p["heat_transfer"]
        return {
            "A": [[-h / c]],
            "B": [[1 / c, h / c]],
            "C": [[1.0]],
            "D": [[0.0, 0.0]],
            "initial": [p["initial"]],
            "inputs": ["power", "ambient"],
            "states": ["temp"],
            "outputs": ["temp"],
        }


class ThermalRc2(Model):
    params = {
        "thermal_mass_a": ("number", True, None),
        "thermal_mass_b": ("number", True, None),
        "heat_transfer_a": ("number", True, None),
        "heat_transfer_b": ("number", True, None),
        "coupling": ("number", True, None),
        "initial_a": ("number", True, None),
        "initial_b": ("number", True, None),
    }
    default_settle = True

    def build(self, p):
        _positive(p, "thermal_mass_a", "thermal_mass_b")
        _not_negative(p, "heat_transfer_a", "heat_transfer_b", "coupling")
        ca, cb, ha, hb, k = (
            p[key] for key in ("thermal_mass_a", "thermal_mass_b", "heat_transfer_a", "heat_transfer_b", "coupling")
        )
        return {
            "A": [[-(ha + k) / ca, k / ca], [k / cb, -(hb + k) / cb]],
            "det": (ha * hb + k * (ha + hb)) / (ca * cb),
            "B": [[1 / ca, ha / ca], [0.0, hb / cb]],
            "C": [[1.0, 0.0], [0.0, 1.0]],
            "D": [[0.0, 0.0], [0.0, 0.0]],
            "initial": [p["initial_a"], p["initial_b"]],
            "inputs": ["power", "ambient"],
            "states": ["temp_a", "temp_b"],
            "outputs": ["temp_a", "temp_b"],
        }


class FirstOrderProcess(Model):
    params = {"tau": ("seconds", True, None), "gain": ("number", False, 1.0), "initial": ("number", False, 0.0)}
    default_settle = True

    def build(self, p):
        _positive(p, "tau")
        tau = float(p["tau"])
        return {
            "A": [[-1 / tau]],
            "B": [[p["gain"] / tau]],
            "C": [[1.0]],
            "D": [[0.0]],
            "initial": [p["initial"]],
            "inputs": ["u"],
            "states": ["y"],
            "outputs": ["y"],
        }


class SecondOrderProcess(Model):
    params = {
        "omega_n": ("number", True, None),
        "zeta": ("number", True, None),
        "gain": ("number", False, 1.0),
        "initial": ("number", False, 0.0),
        "initial_rate": ("number", False, 0.0),
    }
    default_settle = True

    def build(self, p):
        _positive(p, "omega_n")
        _not_negative(p, "zeta")
        w, z = p["omega_n"], p["zeta"]
        return {
            "A": [[0.0, 1.0], [-w * w, -2 * z * w]],
            "det": w * w,
            "B": [[0.0], [w * w * p["gain"]]],
            "C": [[1.0, 0.0], [0.0, 1.0]],
            "D": [[0.0], [0.0]],
            "initial": [p["initial"], p["initial_rate"]],
            "inputs": ["u"],
            "states": ["y", "rate"],
            "outputs": ["y", "rate"],
        }


class MassSpringDamper(Model):
    params = {
        "mass": ("number", True, None),
        "damping": ("number", True, None),
        "stiffness": ("number", True, None),
        "initial_position": ("number", False, 0.0),
        "initial_velocity": ("number", False, 0.0),
    }
    default_settle = True

    def build(self, p):
        _positive(p, "mass")
        _not_negative(p, "damping", "stiffness")
        m, c, k = p["mass"], p["damping"], p["stiffness"]
        return {
            "A": [[0.0, 1.0], [-k / m, -c / m]],
            "det": k / m,
            "B": [[0.0], [1 / m]],
            "C": [[1.0, 0.0], [0.0, 1.0]],
            "D": [[0.0], [0.0]],
            "initial": [p["initial_position"], p["initial_velocity"]],
            "inputs": ["force"],
            "states": ["position", "velocity"],
            "outputs": ["position", "velocity"],
        }


class DcMotor(Model):
    params = {
        "resistance": ("number", True, None),
        "inductance": ("number", True, None),
        "back_emf": ("number", True, None),
        "torque_constant": ("number", True, None),
        "inertia": ("number", True, None),
        "friction": ("number", True, None),
        "initial_current": ("number", False, 0.0),
        "initial_speed": ("number", False, 0.0),
    }
    default_settle = True

    def build(self, p):
        _positive(p, "inductance", "inertia")
        _not_negative(p, "resistance", "friction", "back_emf", "torque_constant")
        r, ind, ke, kt, j, b = (
            p[key] for key in ("resistance", "inductance", "back_emf", "torque_constant", "inertia", "friction")
        )
        return {
            "A": [[-r / ind, -ke / ind], [kt / j, -b / j]],
            "det": (r * b + ke * kt) / (ind * j),
            "B": [[1 / ind, 0.0], [0.0, -1 / j]],
            "C": [[0.0, 1.0], [1.0, 0.0], [kt, 0.0]],
            "D": [[0.0, 0.0]] * 3,
            "initial": [p["initial_current"], p["initial_speed"]],
            "inputs": ["voltage", "load_torque"],
            "states": ["current", "speed"],
            "outputs": ["speed", "current", "torque"],
        }


class StateSpace(Model):
    """Discrete, one input and one output, as 1.x has it: its matrices are the step itself, at whatever period."""

    params = {
        "A": ("matrix", True, None),
        "B": ("numbers", True, None),
        "C": ("numbers", True, None),
        "D": ("number", False, 0.0),
        "initial": ("numbers", False, None),
    }
    continuous = False

    def build(self, p):
        n = len(p["B"])
        return {
            "A": p["A"],
            "B": [[v] for v in p["B"]],
            "C": [p["C"]],
            "D": [[p["D"]]],
            "initial": p["initial"] if p["initial"] is not None else [0.0] * n,
            "inputs": ["u"],
            "states": [f"x{i}" for i in range(n)],
            "outputs": ["y"],
        }


MODELS = {
    "linear": Linear,
    "thermal_mass": ThermalMass,
    "thermal_rc2": ThermalRc2,
    "first_order_process": FirstOrderProcess,
    "second_order_process": SecondOrderProcess,
    "mass_spring_damper": MassSpringDamper,
    "dc_motor": DcMotor,
    "state_space": StateSpace,
}
MODEL_SETTINGS = {"ride_through": ("ticks", False, 0), "settle": ("ticks", False, None)}


class ModelBlock(Block):
    """Section 7.8."""

    model_type = None

    def __init__(self, *a):
        super().__init__(*a)
        params = {name: self.s[name] for name in MODELS[self.model_type].params}
        self.model = MODELS[self.model_type](params, self.period)
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
            elif name in self.last and k - self.last[name][1] <= self.s["ride_through"]:  # rule 4, by tick number
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
        return self.model.step(self.x, u)

    def gap(self, k, n):
        self.gaps += 1
        if n == 0:
            return False  # no tick was passed over, and no step was missed
        self.doubt = k - 1  # uncertain from the gap's tick
        if n is None:  # nobody knows how long: too long to ride through
            self.last = {name: (value, -math.inf) for name, (value, _) in self.last.items()}
            return True
        self.doubtful += n  # each a step on a held value, or one not taken
        for j in range(k - n, k):  # rule 4, for the ticks nobody saw: a held step while every input is within reach
            held = [
                name
                for name in self.model.inputs
                if name in self.last and j - self.last[name][1] <= self.s["ride_through"]
            ]
            if len(held) < len(self.model.inputs):
                break
            self.x = self.model_step({name: self.last[name][0] for name in held})
        return True


MODEL_BLOCKS = {
    kind: type(f"{model.__name__}Block", (ModelBlock,), {"model_type": kind, "settings": model.params | MODEL_SETTINGS})
    for kind, model in MODELS.items()
}


# ---------------------------------------------------------------- the estimator


class Estimator(Block):
    """Section 7.9."""

    settings = {
        "model": ("map", True, None),
        "q": ("map", True, None),
        "p0": ("map", True, None),
        "measure": ("map", True, None),
        "consistency": ("any", True, None),
        "gate": ("number", False, None),
        "max_refused": ("int", False, None),
        "sigma_max": ("map", False, None),
    }

    def __init__(self, *a):
        super().__init__(*a)
        spec = dict(self.s["model"])
        kind = spec.pop("type", None)
        if kind not in MODELS:
            raise CompileError(f"model type {kind!r} is not a model")
        self.model = MODELS[kind](read_settings("model", MODELS[kind].params, spec, None), self.period)
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
        gate, most = self.s["gate"], self.s["max_refused"]
        if gate is not None and gate < 0:
            raise CompileError("gate is not negative")
        if (gate is None) != (most is None) or (most is not None and most < 0):
            raise CompileError("max_refused is given with gate, and only then, and is not negative")
        test = self.s["consistency"]  # rule 7: stated, or said to be none
        if test != "none":
            fits = isinstance(test, dict) and set(test) == {"over", "limit"}
            fits = fits and isinstance(test["over"], int) and not isinstance(test["over"], bool)
            fits = fits and 1 <= test["over"] <= MOST
            if not fits or not is_number(test["limit"]) or test["limit"] <= 0:
                raise CompileError("consistency is `none`, or `over`, a whole number of measurements, and `limit`")
        self.over, self.limit = (None, None) if test == "none" else (test["over"], float(test["limit"]))
        self.qd = self.model.noise([float(q[name]) for name in self.names])
        if not all(math.isfinite(v) for row in self.qd for v in row):
            raise CompileError("the model's process noise over this period is not finite")
        self.p0 = [float(p0[name]) for name in self.names]
        self.meas = {}
        for port, m in self.s["measure"].items():
            fits = isinstance(port, str) and port not in self.model.inputs and isinstance(m, dict)
            fits = fits and port != "" and "." not in port  # 9 rule 2
            if not fits or not {"of", "r"} <= set(m) or set(m) - {"of", "r", "r_uncertain"}:
                raise CompileError(f"measure {port!r} is a port of its own, with `of`, `r` and perhaps `r_uncertain`")
            wide = m.get("r_uncertain")
            if m["of"] not in self.model.outputs or not is_number(m["r"]) or m["r"] <= 0:
                raise CompileError(f"measure {port!r}: `of` is an output of the model and `r` is more than zero")
            if wide is not None and (not is_number(wide) or wide < m["r"]):
                raise CompileError(f"measure {port!r}: `r_uncertain` is not less than `r`")
            row = self.model.outputs.index(m["of"])
            if any(v != 0.0 for v in self.model.d[row]):
                raise CompileError(f"measure {port!r}: the output {m['of']!r} reads an input directly")
            self.meas[port] = (self.model.c[row], float(m["r"]), None if wide is None else float(wide))
        if not self.meas:
            raise CompileError("measure names at least one measurement")
        self.ports = {name: (NUMBER, True, False) for name in self.model.inputs}  # deferred: rule 2
        self.ports |= {port: (NUMBER, True, True) for port in self.meas}
        named = [*self.names, *(f"sigma_{name}" for name in self.names)]
        for port in self.meas:
            named += [f"innovation_{port}", f"nis_{port}", f"refused_{port}", f"since_{port}"]
        if len(set(named)) != len(named):  # rule 8
            twice = sorted({name for name in named if named.count(name) > 1})
            raise CompileError(f"two outputs would be named {twice[0]!r}")
        self.outputs = dict.fromkeys(named, NUMBER)
        self.x = self.model.initial()
        self.p = [[self.p0[i] if i == j else 0.0 for j in range(n)] for i in range(n)]
        self.considered = dict.fromkeys(self.meas)  # the sample time last considered, per port
        self.used_at = dict.fromkeys(self.meas)  # the sample time last used, per port
        self.refused = dict.fromkeys(self.meas, 0)  # how many, in all
        self.run = dict.fromkeys(self.meas, 0)  # how many in a row
        self.recent = {
            port: collections.deque(maxlen=self.over) for port in self.meas
        }  # normalised innovations squared
        self.last_u = {}  # each model input's last usable value
        self.stepping = False  # the second phase of a tick has run: a step to the next is due
        self.held = False  # that step is on a value that was held, or was uncertain, or is not taken
        self.rebased = False
        self.lost = False  # a gap of no known length has gone by, and no measurement has been used since

    def _advance(self, times):
        """`times` steps on the model inputs it has (rule 2): the state if it has them all, and the covariance."""
        n = len(self.names)
        if len(self.last_u) < len(self.model.inputs):  # some model input has never been usable: the state
            self.p = [[self.p[i][j] + times * self.qd[i][j] for j in range(n)] for i in range(n)]  # stays, and
            return  # its covariance is P + N for each step
        f = [[float(i == j) for j in range(n)] for i in range(n)]
        g = [[0.0] * len(self.model.inputs) for _ in range(n)]
        noise = [[0.0] * n for _ in range(n)]
        step = (self.model.ad, self.model.bd, self.qd)
        while times:  # by doubling: after a long gap this is still few products
            if times & 1:
                f, g, noise = compose(step, (f, g, noise))
            step = compose(step, step)
            times >>= 1
        u = [[self.last_u[name]] for name in self.model.inputs]
        moved, pushed = matmul(f, [[v] for v in self.x]), matmul(g, u)
        self.x = [moved[i][0] + pushed[i][0] for i in range(n)]
        spread = matmul(matmul(f, self.p), transpose(f))
        self.p = [[spread[i][j] + noise[i][j] for j in range(n)] for i in range(n)]

    def output(self, k, t, ins):
        n = len(self.names)
        doubt = False
        if self.stepping:  # rule 2: from the tick before to this one, on the inputs as they were then
            self._advance(1)
            doubt, self.stepping, self.held = self.held, False, False
        out = {}
        for port, (row, r, wide) in self.meas.items():  # rules 3 and 4
            z = ins[port]
            out[f"innovation_{port}"] = out[f"nis_{port}"] = Val(NOT_READY)
            variance = r if z.state == GOOD else wide if z.state == UNCERTAIN else None
            if (
                variance is not None
                and z.at is not None
                and (self.considered[port] is None or z.at > self.considered[port])
            ):
                self.considered[port] = z.at
                innovation = z.v - sum(c * xi for c, xi in zip(row, self.x, strict=True))
                reach = [sum(self.p[i][j] * row[j] for j in range(n)) for i in range(n)]  # P times the row
                s = sum(c * v for c, v in zip(row, reach, strict=True)) + variance
                out[f"innovation_{port}"] = Val(GOOD, innovation)
                out[f"nis_{port}"] = Val(GOOD, innovation * innovation / s)
                self.recent[port].append(innovation * innovation / s)
                take = True
                if self.s["gate"] is not None and abs(innovation) > self.s["gate"] * math.sqrt(s):
                    self.run[port] += 1
                    if self.run[port] > self.s["max_refused"]:  # too many in a row to be outliers: widen, and take it
                        for i in range(n):
                            self.p[i][i] += self.p0[i]
                        reach = [sum(self.p[i][j] * row[j] for j in range(n)) for i in range(n)]
                        s = sum(c * v for c, v in zip(row, reach, strict=True)) + variance
                        doubt = True  # it has given in to what it was refusing, and cannot tell why
                    else:
                        take, doubt = False, True
                        self.refused[port] += 1
                if take:
                    self.run[port] = 0
                    gain = [v / s for v in reach]
                    self.x = [xi + gi * innovation for xi, gi in zip(self.x, gain, strict=True)]
                    # rule 4: (1 - g c) P (1 - g c)' + g v g', which a wide p0 beside a small r cannot round to nothing
                    keep = [[float(a == b) - gain[a] * row[b] for b in range(n)] for a in range(n)]
                    kept = matmul(matmul(keep, self.p), transpose(keep))
                    self.p = [[kept[a][b] + gain[a] * variance * gain[b] for b in range(n)] for a in range(n)]
                    self.used_at[port] = z.at
                    self.lost = False
                    doubt = doubt or z.state == UNCERTAIN  # rule D
            out[f"refused_{port}"] = Val(GOOD, float(self.refused[port]))
            out[f"since_{port}"] = (
                Val(NOT_READY) if self.used_at[port] is None else Val(GOOD, max(0, t - self.used_at[port]) / NS)
            )
            if self.over is not None and len(self.recent[port]) == self.over:  # rule 7
                doubt = doubt or sum(self.recent[port]) / self.over > self.limit
        for i, name in enumerate(self.names):  # rule 5
            sigma = math.sqrt(max(self.p[i][i], 0.0))
            wide = name in self.limits and sigma > self.limits[name]
            state = UNCERTAIN if doubt or wide or self.lost else GOOD
            out[name], out[f"sigma_{name}"] = Val(state, self.x[i]), Val(state, sigma)
        return out

    def update(self, k, ins):
        """Second phase: the model inputs of this tick, for the step to the next."""
        self.stepping = True
        for name in self.model.inputs:
            if usable(ins[name]):
                self.last_u[name] = ins[name].v
                self.held = self.held or ins[name].state == UNCERTAIN
            else:
                self.held = True

    def gap(self, k, n):
        if n:  # the ticks nobody saw: as many steps on what it last had
            self._advance(n)
        if n is None or self.rebased:  # nobody knows how long, or it cannot tell an old sample from a new one
            for i in range(len(self.names)):
                self.p[i][i] += self.p0[i]
        if n != 0:
            self.held = True  # the step to the tick that runs is on values nobody saw
        self.lost = self.lost or n is None
        self.rebased = False

    def forget_times(self):
        self.considered = dict.fromkeys(self.meas)
        self.used_at = dict.fromkeys(self.meas)
        self.rebased = True


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
    "rate_limit": RateLimit,
    "pid": Pid,
    **MODEL_BLOCKS,
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
        if isinstance(self.max_catch_up, bool) or not isinstance(self.max_catch_up, int):
            raise CompileError("max_catch_up is a whole number, at least 1")
        if not 1 <= self.max_catch_up <= MOST:
            raise CompileError(f"max_catch_up is a whole number, at least 1 and at most {MOST}")
        self.max_waiting = graph.get("max_waiting", 1024)  # 6 rule 8
        if isinstance(self.max_waiting, bool) or not isinstance(self.max_waiting, int):
            raise CompileError("max_waiting is a whole number, at least 1")
        if not 1 <= self.max_waiting <= MOST:
            raise CompileError(f"max_waiting is a whole number, at least 1 and at most {MOST}")

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
        if any("." in i for i in ids):  # 9 rule 2
            raise CompileError("a block id holds no dot")
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
        for bid, block in self.blocks.items():  # 7.9 rule 3: a measurement carries the time of a sample
            for port in block.meas if isinstance(block, Estimator) else ():
                if not self._carries(self.wiring[bid][port], set()):
                    raise CompileError(
                        f"block {bid}: the measurement {port!r} is read from a block that gives it the tick's time, "
                        f"so every tick would count as a new sample: read it from an input, a delay, or a formula "
                        f"that takes its sample time from one"
                    )

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

    def _carries(self, src, seen):
        """Whether a signal carries the sample time of an input, and not the time of the tick (3 rule 7)."""
        if src[0] != "block":
            return src[0] == "input"
        bid = src[1][0]
        if bid in seen:
            return False
        block = self.blocks[bid]
        through = "x" if isinstance(block, Delay) else getattr(block, "sample_of", None)
        return through is not None and self._carries(self.wiring[bid][through], seen | {bid})

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
            if len(models) > 1:
                raise CompileError(
                    f"{where}: model blocks {models} read each other, a tick apart: write them as one linear model"
                )
            if not self.blocks[models[0]].settle_given:
                raise CompileError(f"{where}: a model on a loop is given settle")
            settle = self.blocks[models[0]].s["settle"]
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
        self.rebased = False  # whether there has been a rebase since the engine was made or reset (7.2 rule 1)
        self.last_now = None
        self.standing = {}  # input -> (state, value, time): the write last taken up
        self.pending = {name: [] for name in self.inputs}  # the writes not yet taken up, as made
        self.rebasing, self.away = False, None
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

    def rebase(self, away=None):
        """The host's clock has stepped, or a state was restored: the next call is a gap, at any time.

        `away`: how long the graph did not run, in nanoseconds from the time of the last tick it ran, if the
        host knows (8 rule 5).
        """
        if away is not None and (isinstance(away, bool) or not isinstance(away, int) or not 0 <= away < 2**63):
            raise ValueError("the length of a rebase is a whole number of nanoseconds, not negative")
        self.pending = {name: [] for name in self.inputs}  # 8 rule 5: what was written before is done with
        self.standing = {}  # and nothing stands, from now: a write on the new clock is not judged by the old
        if self.zero is None and self.k == 0:
            return  # nothing has run: the next call runs tick 0, and is no gap
        self.last_now, self.rebasing, self.away = None, True, away

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
            if spec["initial"] is not None and ran <= spec["max_age"] and not self.rebased:
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
        # 6 rule 11: the last tick this call would run has a number and a time that fit in 64 bits
        if self.rebasing:
            number, at = self.k + (self.away is not None and self._over()), now
        else:
            zero = now if self.zero is None else self.zero
            number = (2 * (now - zero) + self.period) // (2 * self.period)
            at = zero + number * self.period
        if number >= 2**63 or at >= 2**63:
            raise ValueError("the tick this call would run does not fit in 64 bits")
        self.last_now = now
        for name, writes in self.pending.items():  # rule 8: stamped too far ahead
            self.pending[name] = [w for w in writes if w[2] - now <= self.inputs[name]["max_ahead"]]
            self.thrown += len(writes) - len(self.pending[name])
        if self.zero is None:  # rule 5
            self.zero = self.since = now
        gap, skipped = False, 0
        if self.rebasing:  # 8 rule 5: one tick, at the call's time, on what may be another clock
            self.rebasing, gap, due = False, True, 1
            skipped = None  # nobody knows, unless the host said how long it was away
            if self.away is not None:  # the ticks that were due in that time, less the one that now runs
                skipped = self._over()
                self.k += skipped
            self.zero, self.since, self.rebased = now - self.k * self.period, now, True
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
                gap, skipped = True, due - 1
                self.k += skipped  # the ticks before it were not run, and keep their numbers
                due = 1
        if gap:
            for bid, block in self.blocks.items():  # 8 rule 6
                if block.gap(self.k, skipped) and bid in self.loop_of:  # a model's doubt is its loop's
                    self.loop_doubt[self.loop_of[bid]] = self.k - 1
        out = None
        for i in range(due):
            out = self._run(last=i == due - 1)
        self.info = {
            "gap": gap,
            "skipped": skipped,  # the ticks a gap passed over, or None if nobody knows
            "tick": self.k - 1,
            "time": self.zero + (self.k - 1) * self.period,
            "thrown": self.thrown,  # since the last call that ran a tick
            "waiting": sum(len(writes) for writes in self.pending.values()),
        }
        self.thrown = 0
        return due, out

    def _over(self):
        """8 rule 5: the ticks due in the time a rebase was told of, less the one that runs."""
        return max(0, (2 * self.away + self.period) // (2 * self.period) - 1)

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
                keeps = block.own_at and usable(val)  # 3 rule 7
                now[(bid, port)] = Val(val.state, val.v, None if substituted else val.at if keeps else t)
        for bid in self.order:  # second phase
            block, ins = self.blocks[bid], read(bid, False)
            block.update(k, ins)
            if bid in self.loop_of:
                from_outside(bid, ins, {p for p in ins if block.ports is not None and not block.ports[p][2]})
        for loop in doubts:
            self.loop_doubt[loop] = k
        self.k = k + 1
        return {sig: now[w] for sig, w in self.published.items()}

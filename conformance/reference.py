#!/usr/bin/env python3
"""A reference for the version 2 semantics proposal (docs/semantics_spec_v2.md).

Small, slow and written to be read beside the proposal. It is not the
library and shares no code with it. Its job is to be a second opinion: the
vectors in vectors/ state what each rule should give, worked out by hand,
and this has to agree with them.

Stdlib only. run.py loads the vectors (it needs PyYAML) and drives this.
"""

from __future__ import annotations

import collections
import copy
import math
import re
import statistics

GOOD, UNCERTAIN, NOT_READY, BAD = "good", "uncertain", "not_ready", "bad"
_WORST_FIRST = (BAD, NOT_READY, UNCERTAIN, GOOD)  # section 3 rule 3
NUMBER, BOOLEAN = "number", "boolean"

Val = collections.namedtuple("Val", "state v new", defaults=(None, False))
_DURATION = re.compile(r"^([0-9]+(?:\.[0-9]+)?)(ms|s|m|h)$")
_UNIT = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


class CompileError(Exception):
    """The graph is refused. Raised when a graph is built, never while it runs."""


def usable(val):
    return val.state in (GOOD, UNCERTAIN)


def worst(states):
    states = set(states)
    return next((s for s in _WORST_FIRST if s in states), GOOD)


def seconds(text):
    m = _DURATION.match(text) if isinstance(text, str) else None
    if not m:
        raise CompileError(f"{text!r} is not a length of time (use 500ms, 3s, 2m, 1h)")
    return float(m.group(1)) * _UNIT[m.group(2)]


def ticks_of(duration, period, what, least=0):
    """Section 6 rule 2: a counted length of time is a whole number of periods."""
    n = duration / period
    if abs(n - round(n)) > 1e-9:
        raise CompileError(f"{what} is {duration} s, which is not a whole number of periods of {period} s")
    if round(n) < least:
        raise CompileError(f"{what} is at least {least} period(s)")
    return round(n)


# ---------------------------------------------------------------- formulas

_NUMBER = r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
_TOKEN = re.compile(rf"[ \t]*(?:({_NUMBER})|([A-Za-z_][A-Za-z0-9_]*)|(<=|>=|==|!=|[-+*/<>(),]))")
_COMPARE = {"<", "<=", ">", ">=", "==", "!="}
_FUNCTIONS = {"abs": 1, "min": 2, "max": 2, "exp": 1, "ln": 1, "sqrt": 1, "pow": 2, "when": 3}
_RESERVED = {"and", "or", "not", "true", "false", *_FUNCTIONS}


class Formula:
    """Appendix A: the grammar, the types, and section 7.1's states."""

    def __init__(self, text, types):
        self.tokens, pos = [], 0
        text = str(text)
        if "\n" in text:
            raise CompileError("a formula is one line")
        while pos < len(text.rstrip(" \t")):
            m = _TOKEN.match(text, pos)
            if not m:
                raise CompileError(f"formula: cannot read {text[pos:].strip()[:12]!r}")
            kind = "num" if m.group(1) else "name" if m.group(2) else "op"
            self.tokens.append((kind, m.group(m.lastindex)))
            pos = m.end()
        self.i, self.types, self.used = 0, types, set()
        bad = set(types) & _RESERVED
        if bad:
            raise CompileError(f"{sorted(bad)} cannot be the name of an input")
        self.tree = self._or()
        if self.i != len(self.tokens):
            raise CompileError(f"formula: unexpected {self.tokens[self.i][1]!r}")
        unused = set(types) - self.used
        if unused:
            raise CompileError(f"the formula does not use its input(s) {sorted(unused)}")
        self.type = self.tree[1]

    # A node is (kind, type, ...).
    def _peek(self):
        return self.tokens[self.i] if self.i < len(self.tokens) else (None, None)

    def _take(self, value=None):
        tok = self._peek()
        if tok[0] is None or (value is not None and tok[1] != value):
            raise CompileError(f"formula: expected {value or 'more'}, found {tok[1]!r}")
        self.i += 1
        return tok

    def _need(self, node, want, what):
        if node[1] != want:
            raise CompileError(f"formula: {what} takes a {want}, and was given a {node[1]}")

    def _logic(self, word, lower):
        node = lower()
        while self._peek() == ("name", word):
            self._take()
            right = lower()
            self._need(node, BOOLEAN, word)
            self._need(right, BOOLEAN, word)
            node = (word, BOOLEAN, node, right)
        return node

    def _or(self):
        return self._logic("or", self._and)

    def _and(self):
        return self._logic("and", self._not)

    def _not(self):
        if self._peek() == ("name", "not"):
            self._take()
            node = self._not()
            self._need(node, BOOLEAN, "not")
            return ("not", BOOLEAN, node)
        return self._compare()

    def _compare(self):
        node = self._add()
        if self._peek()[0] == "op" and self._peek()[1] in _COMPARE:
            op = self._take()[1]
            right = self._add()
            if op in ("==", "!="):
                if node[1] != right[1]:
                    raise CompileError(f"formula: {op} takes two of one type")
            else:
                self._need(node, NUMBER, op)
                self._need(right, NUMBER, op)
            node = ("cmp", BOOLEAN, op, node, right)
            if self._peek()[0] == "op" and self._peek()[1] in _COMPARE:
                raise CompileError("comparisons do not chain: write (a < b) and (b < c)")
        return node

    def _binary(self, ops, lower):
        node = lower()
        while self._peek()[0] == "op" and self._peek()[1] in ops:
            op = self._take()[1]
            right = lower()
            self._need(node, NUMBER, op)
            self._need(right, NUMBER, op)
            node = ("arith", NUMBER, op, node, right)
        return node

    def _add(self):
        return self._binary("+-", self._mul)

    def _mul(self):
        return self._binary("*/", self._unary)

    def _unary(self):
        if self._peek() == ("op", "-"):
            self._take()
            node = self._unary()
            self._need(node, NUMBER, "unary minus")
            return ("neg", NUMBER, node)
        return self._primary()

    def _primary(self):
        kind, text = self._take()
        if kind == "num":
            if not math.isfinite(float(text)):
                raise CompileError(f"formula: {text} is too large for a number")
            return ("const", NUMBER, float(text))
        if kind == "op" and text == "(":
            node = self._or()
            self._take(")")
            return node
        if kind != "name":
            raise CompileError(f"formula: unexpected {text!r}")
        if text in ("true", "false"):
            return ("const", BOOLEAN, text == "true")
        if text in _FUNCTIONS:
            self._take("(")
            args = [self._or()]
            while self._peek() == ("op", ","):
                self._take()
                args.append(self._or())
            self._take(")")
            if len(args) != _FUNCTIONS[text]:
                raise CompileError(f"formula: {text} takes {_FUNCTIONS[text]} argument(s)")
            if text == "when":
                self._need(args[0], BOOLEAN, "the condition of when")
                if args[1][1] != args[2][1]:
                    raise CompileError("formula: the two branches of when are of one type")
                return ("when", args[1][1], *args)
            for a in args:
                self._need(a, NUMBER, text)
            return ("call", NUMBER, text, args)
        if text in ("and", "or", "not"):
            raise CompileError(f"formula: unexpected {text!r}")
        if text not in self.types:
            raise CompileError(f"formula uses {text!r}, which is not one of the block's inputs")
        self.used.add(text)
        return ("name", self.types[text], text)

    def eval(self, env):
        out = self._eval(self.tree, env)
        return Val(out.state, out.v if usable(out) else None)

    def _eval(self, node, env):
        kind = node[0]
        if kind == "const":
            return Val(GOOD, node[2])
        if kind == "name":
            return env[node[2]]
        if kind in ("or", "and"):  # 7.1 rule 2
            decides = kind == "or"
            vals = [self._eval(node[2], env), self._eval(node[3], env)]
            deciders = [v for v in vals if usable(v) and bool(v.v) == decides]
            if deciders:
                return Val(GOOD if any(v.state == GOOD for v in deciders) else UNCERTAIN, decides)
            state = worst(v.state for v in vals)
            return Val(state, (not decides) if state in (GOOD, UNCERTAIN) else None)
        if kind == "when":  # 7.1 rule 3
            cond = self._eval(node[2], env)
            if not usable(cond):
                return Val(cond.state, None)
            branch = self._eval(node[3] if cond.v else node[4], env)
            state = worst((cond.state, branch.state))
            return Val(state, branch.v if state in (GOOD, UNCERTAIN) else None)
        if kind == "not":
            vals, fn = [self._eval(node[2], env)], (lambda a: not a)
        elif kind == "neg":
            vals, fn = [self._eval(node[2], env)], (lambda a: -a)
        elif kind == "cmp":
            vals = [self._eval(node[3], env), self._eval(node[4], env)]
            fn = {
                "<": lambda a, b: a < b,
                "<=": lambda a, b: a <= b,
                ">": lambda a, b: a > b,
                ">=": lambda a, b: a >= b,
                "==": lambda a, b: a == b,
                "!=": lambda a, b: a != b,
            }[node[2]]
        elif kind == "arith":
            vals = [self._eval(node[3], env), self._eval(node[4], env)]
            fn = {
                "+": lambda a, b: a + b,
                "-": lambda a, b: a - b,
                "*": lambda a, b: a * b,
                "/": lambda a, b: a / b,
            }[node[2]]
        else:
            vals = [self._eval(a, env) for a in node[3]]
            fn = {
                "abs": abs,
                "min": min,
                "max": max,
                "exp": math.exp,
                "ln": math.log,
                "sqrt": math.sqrt,
                "pow": math.pow,
            }[node[2]]
        state = worst(v.state for v in vals)  # 7.1 rule 1
        if state not in (GOOD, UNCERTAIN):
            return Val(state, None)
        try:
            value = fn(*(v.v for v in vals))
        except (ZeroDivisionError, ValueError, OverflowError):  # 7.1 rule 4
            return Val(BAD, None)
        if isinstance(value, float) and not math.isfinite(value):
            return Val(BAD, None)
        return Val(state, value)


# ---------------------------------------------------------------- blocks


class Block:
    """A block type. `ports` maps an input to (type or None for any, required, direct)."""

    ports: dict | None = {}
    settings: dict = {}  # name -> (kind, required, default)
    outputs: dict = {"y": NUMBER}
    own_new = False

    def __init__(self, settings, period, in_types):
        self.s, self.period = settings, period

    def out_types(self, in_types):
        return dict(self.outputs)

    def output(self, k, ins):
        """First phase: the outputs, from the state and the direct inputs."""
        raise NotImplementedError

    def update(self, k, ins):
        """Second phase: the state, from every input. Most blocks need none."""


class FormulaBlock(Block):
    ports = None
    settings = {"expr": ("str", True, None)}

    def __init__(self, settings, period, in_types):
        super().__init__(settings, period, in_types)
        self.formula = Formula(settings["expr"], in_types)

    def out_types(self, in_types):
        return {"y": self.formula.type}

    def output(self, k, ins):
        return {"y": self.formula.eval(ins)}


class AllGood(Block):
    ports = None
    outputs = {"y": BOOLEAN}

    def output(self, k, ins):
        return {"y": Val(GOOD, all(v.state == GOOD for v in ins.values()))}


class Delay(Block):
    ports = {"x": (None, True, False)}
    own_new = True  # its output is new when the input it gives was new
    settings = {"ticks": ("int", False, 1), "initial": ("const", False, None)}

    def __init__(self, *a):
        super().__init__(*a)
        if self.s["ticks"] < 1:
            raise CompileError("ticks is at least 1")
        initial = self.s["initial"]
        if initial is not None and "x" in a[2] and _type_of(initial) != a[2]["x"]:
            raise CompileError("its initial value is not of its input's type")
        if initial is not None and not isinstance(initial, bool):
            self.s["initial"] = float(initial)
        self.past = collections.deque()

    def out_types(self, in_types):
        if "x" in in_types:
            return {"y": in_types["x"]}
        return {"y": BOOLEAN if isinstance(self.s["initial"], bool) else NUMBER}

    def output(self, k, ins):
        if len(self.past) < self.s["ticks"]:
            initial = self.s["initial"]
            return {"y": Val(GOOD, initial) if initial is not None else Val(NOT_READY)}
        return {"y": self.past[0]}

    def update(self, k, ins):
        self.past.append(ins["x"])
        if len(self.past) > self.s["ticks"]:
            self.past.popleft()


class Window(Block):
    """Section 7.3."""

    ports = {"x": (NUMBER, True, True)}
    settings = {"window": ("ticks1", True, None), "min_good": ("number", False, 1.0)}
    outputs = dict.fromkeys(("mean", "median", "min", "max", "spread", "slope", "count"), NUMBER)

    def __init__(self, *a):
        super().__init__(*a)
        self.n = self.s["window"]
        if not 0.0 < self.s["min_good"] <= 1.0:
            raise CompileError("min_good is a fraction above 0 and at most 1")
        self.buf = collections.deque(maxlen=self.n)

    def output(self, k, ins):
        self.buf.append(ins["x"])
        # The sample's place in the window, counted from its oldest tick.
        first = self.n - len(self.buf)
        held = [(first + i, v) for i, v in enumerate(self.buf) if usable(v)]
        out = {"count": Val(GOOD, float(len(held)))}
        names = [name for name in self.outputs if name != "count"]
        if len(held) < math.ceil(self.s["min_good"] * self.n - 1e-9):  # 7.3 rule 2
            missing = [v.state for v in self.buf if not usable(v)] + [NOT_READY] * first
            return out | dict.fromkeys(names, Val(worst(missing)))
        whole = len(self.buf) == self.n and all(v.state == GOOD for v in self.buf)
        state = GOOD if whole else UNCERTAIN
        ys = [v.v for _, v in held]
        out |= {
            "mean": Val(state, sum(ys) / len(ys)),
            "median": Val(state, statistics.median(ys)),
            "min": Val(state, min(ys)),
            "max": Val(state, max(ys)),
            "spread": Val(state, max(ys) - min(ys)),
        }
        ts = [i * self.period for i, _ in held]
        mt, my = sum(ts) / len(ts), sum(ys) / len(ys)
        den = sum((t - mt) ** 2 for t in ts)
        if len(held) < 2 or den == 0.0:
            out["slope"] = Val(BAD)
        else:
            out["slope"] = Val(state, sum((t - mt) * (y - my) for t, y in zip(ts, ys, strict=True)) / den)
        return out


class Holder(Block):
    """Section 7.4: a block that keeps one value. Subclasses say how it moves."""

    ports = {"x": (NUMBER, True, True)}

    def __init__(self, *a):
        super().__init__(*a)
        self.held, self.seen = None, None

    def move(self, x):
        raise NotImplementedError

    def output(self, k, ins):
        x = ins["x"]
        if usable(x):
            self.held = x.v if self.held is None else self.move(x.v)
            self.seen = k
            return {"y": Val(x.state, self.held)}
        if self.held is not None and k - self.seen <= self.s["ride_through"]:
            return {"y": Val(UNCERTAIN, self.held)}
        return {"y": Val(x.state)}


class Deadband(Holder):
    settings = {"step": ("number", True, None), "ride_through": ("ticks", False, 0)}

    def __init__(self, *a):
        super().__init__(*a)
        if self.s["step"] < 0:
            raise CompileError("step is not negative")

    def move(self, x):
        return x if abs(x - self.held) >= self.s["step"] else self.held


class Lowpass(Holder):
    settings = {"tau": ("seconds", True, None), "ride_through": ("ticks", False, 0)}

    def __init__(self, *a):
        super().__init__(*a)
        if self.s["tau"] <= 0:
            raise CompileError("tau is more than zero")
        self.a = math.exp(-self.period / self.s["tau"])

    def move(self, x):
        return self.a * self.held + (1 - self.a) * x


class Hysteresis(Block):
    """Section 7.5."""

    ports = {"x": (NUMBER, True, True)}
    settings = {"rise": ("number", True, None), "fall": ("number", True, None)}
    outputs = {"y": BOOLEAN}

    def __init__(self, *a):
        super().__init__(*a)
        if not self.s["rise"] > self.s["fall"]:
            raise CompileError("rise is more than fall")
        self.on = None

    def output(self, k, ins):
        x = ins["x"]
        if not usable(x):
            return {"y": Val(x.state)}
        if x.v >= self.s["rise"]:
            self.on = True
        elif x.v <= self.s["fall"]:
            self.on = False
        return {"y": Val(NOT_READY) if self.on is None else Val(x.state, self.on)}


class HeldFor(Block):
    """Section 7.6 rule 1."""

    ports = {"x": (BOOLEAN, True, True)}
    settings = {
        "time": ("ticks", True, None),
        "on_bad": ("choice", True, ("reset", "hold")),
        "hold_limit": ("ticks", False, None),
    }
    outputs = {"y": BOOLEAN}

    def __init__(self, *a):
        super().__init__(*a)
        if (self.s["on_bad"] == "hold") != (self.s["hold_limit"] is not None):
            raise CompileError("hold_limit is given with on_bad: hold, and only then")
        self.since, self.degraded, self.gap = None, False, 0

    def output(self, k, ins):
        x = ins["x"]
        if usable(x):
            self.gap = 0
            if not x.v:
                self.since, self.degraded = None, False
                return {"y": Val(x.state, False)}
            if self.since is None:
                self.since, self.degraded = k, False
            self.degraded = self.degraded or x.state == UNCERTAIN
            return {"y": Val(UNCERTAIN if self.degraded else GOOD, k - self.since > self.s["time"])}
        self.gap += 1
        if self.s["on_bad"] == "reset" or self.since is None or self.gap > self.s["hold_limit"]:
            self.since, self.degraded = None, False
            return {"y": Val(x.state)}
        self.degraded = True
        return {"y": Val(UNCERTAIN, k - self.since > self.s["time"])}


class SinceTrue(Block):
    """Section 7.6 rule 2."""

    ports = {"x": (BOOLEAN, True, True)}
    settings = {"time": ("ticks", True, None), "on_bad": ("choice", True, ("assume_false", "unknown"))}
    outputs = {"y": BOOLEAN}

    def __init__(self, *a):
        super().__init__(*a)
        self.last = None

    def output(self, k, ins):
        x = ins["x"]
        if self.last is None or (usable(x) and x.v):
            self.last = k
        late = k - self.last > self.s["time"]
        if usable(x):
            return {"y": Val(x.state, late)}
        return {"y": Val(UNCERTAIN, late) if self.s["on_bad"] == "assume_false" else Val(x.state)}


class Latch(Block):
    """Section 7.6 rule 3."""

    ports = {"set": (BOOLEAN, True, True), "reset": (BOOLEAN, False, True)}
    outputs = {"y": BOOLEAN}

    def __init__(self, *a):
        super().__init__(*a)
        self.on = False

    def output(self, k, ins):
        s, r = ins["set"], ins.get("reset")
        if r is not None and usable(r) and r.v:
            self.on = False
        elif usable(s) and s.v:
            self.on = True
        if self.on:
            return {"y": Val(GOOD, True)}
        return {"y": Val(s.state, False) if usable(s) else Val(s.state)}


class Integrate(Block):
    """Section 7.7."""

    ports = {"x": (NUMBER, True, True), "reset": (BOOLEAN, False, True)}
    settings = {"per": ("seconds", False, 1.0), "max_missed": ("ticks", False, None)}
    outputs = {"y": NUMBER, "missed": NUMBER}

    def __init__(self, *a):
        super().__init__(*a)
        if self.s["per"] <= 0:
            raise CompileError("per is more than zero")
        self.total, self.missed, self.degraded = 0.0, 0, False

    def output(self, k, ins):
        x, r = ins["x"], ins.get("reset")
        if r is not None and usable(r) and r.v:
            self.total, self.missed, self.degraded = 0.0, 0, False
        if usable(x):
            self.total += x.v * self.period / self.s["per"]
            self.degraded = self.degraded or x.state == UNCERTAIN
        else:
            self.missed += 1
        limit = self.s["max_missed"]
        if limit is not None and self.missed > limit:
            y = Val(BAD)
        else:
            y = Val(UNCERTAIN if self.missed or self.degraded else GOOD, self.total)
        return {"y": y, "missed": Val(GOOD, self.missed * self.period)}


class Kalman1(Block):
    """Appendix B: a fixture for section 7.9, not a filter to use."""

    ports = {"z": (NUMBER, True, True), "model": (NUMBER, True, True)}
    settings = {
        "tau": ("seconds", True, None),
        "q": ("number", True, None),
        "r": ("number", True, None),
        "max_coast": ("ticks", True, None),
    }
    outputs = {"x": NUMBER, "sigma": NUMBER}

    def __init__(self, *a):
        super().__init__(*a)
        if self.s["tau"] <= 0 or self.s["r"] <= 0 or self.s["q"] < 0:
            raise CompileError("tau and r are more than zero, and q is not negative")
        self.a = math.exp(-self.period / self.s["tau"])
        self.x, self.var, self.corrected, self.on_uncertain = None, None, None, False

    def output(self, k, ins):
        z, model = ins["z"], ins["model"]
        fresh = usable(z) and z.new
        if self.x is None:
            if not fresh:
                return dict.fromkeys(self.outputs, Val(NOT_READY))
            self.x, self.var = z.v, self.s["r"]
        else:
            if usable(model):
                self.x = self.a * self.x + (1 - self.a) * model.v
                self.var = self.a * self.a * self.var + self.s["q"] * self.period
            else:
                self.var += self.s["q"] * self.period
            if fresh:
                gain = self.var / (self.var + self.s["r"])
                self.x += gain * (z.v - self.x)
                self.var *= 1 - gain
        if fresh:
            self.corrected, self.on_uncertain = k, z.state == UNCERTAIN
        coasting = k - self.corrected > self.s["max_coast"]
        state = UNCERTAIN if coasting or self.on_uncertain else GOOD
        return {"x": Val(state, self.x), "sigma": Val(state, math.sqrt(self.var))}


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
    "kalman1": Kalman1,
}

_GRAPH_KEYS = {"period", "inputs", "blocks"}
_BLOCK_KEYS = {"id", "type", "in", "settings", "out", "fallback"}
_INPUT_KEYS = {"type", "unit", "max_age", "initial"}


def _type_of(constant):
    return BOOLEAN if isinstance(constant, bool) else NUMBER


def _is_constant(value):
    return isinstance(value, (bool, int, float))


# ---------------------------------------------------------------- the engine


class Engine:
    def __init__(self, graph):
        if not isinstance(graph, dict) or set(graph) - _GRAPH_KEYS:
            raise CompileError(f"unknown key(s) in the graph: {sorted(set(graph) - _GRAPH_KEYS)}")
        if "period" not in graph:
            raise CompileError("a graph states its period")
        self.period = seconds(graph["period"])
        if self.period <= 0:
            raise CompileError("the period is positive")

        self.inputs = {}
        for name, spec in (graph.get("inputs") or {}).items():
            spec = spec or {}
            if set(spec) - _INPUT_KEYS:
                raise CompileError(f"input {name}: unknown key(s) {sorted(set(spec) - _INPUT_KEYS)}")
            kind = spec.get("type", NUMBER)
            if kind not in (NUMBER, BOOLEAN):
                raise CompileError(f"input {name}: type is number or boolean")
            initial = spec.get("initial")
            if initial is not None and (not _is_constant(initial) or _type_of(initial) != kind):
                raise CompileError(f"input {name}: its initial value is a {kind}")
            if initial is not None and kind == NUMBER and not math.isfinite(initial):
                raise CompileError(f"input {name}: its initial value is finite")
            max_age = seconds(spec["max_age"]) if "max_age" in spec else math.inf
            if max_age < 0:
                raise CompileError(f"input {name}: max_age is not negative")
            self.inputs[name] = {"type": kind, "max_age": max_age, "initial": initial}
        self.max_age = {name: spec["max_age"] for name, spec in self.inputs.items()}

        specs = graph.get("blocks") or []
        ids = [b.get("id") if isinstance(b, dict) else None for b in specs]
        if len(set(ids)) != len(ids) or None in ids:
            raise CompileError("every block has an id of its own")
        by_id = {b["id"]: b for b in specs}

        writer = {}  # signal -> (block, port)
        for b in specs:
            where = f"block {b['id']}"
            if set(b) - _BLOCK_KEYS:
                raise CompileError(f"{where}: unknown key(s) {sorted(set(b) - _BLOCK_KEYS)}")
            if b.get("type") not in CATALOGUE:
                raise CompileError(f"{where}: unknown type {b.get('type')!r}")
            cls = CATALOGUE[b["type"]]
            for port, signal in (b.get("out") or {}).items():
                if port not in cls.outputs:
                    raise CompileError(f"{where}: no output {port!r}")
                if not isinstance(signal, str) or not signal:
                    raise CompileError(f"{where}: output {port!r} needs a signal name")
                if signal in writer or signal in self.inputs:
                    raise CompileError(f"{where}: {signal} already has a writer")
                writer[signal] = (b["id"], port)
        self.published = dict(writer)
        for b in specs:
            for port in CATALOGUE[b["type"]].outputs:
                writer.setdefault(f"{b['id']}.{port}", (b["id"], port))

        # Wiring, and which inputs are direct.
        self.wiring, direct, every = {}, {}, {}
        for b in specs:
            where = f"block {b['id']}"
            cls, given = CATALOGUE[b["type"]], b.get("in") or {}
            if cls.ports is None:
                if not given:
                    raise CompileError(f"{where}: needs at least one input")
            else:
                if set(given) - set(cls.ports):
                    raise CompileError(f"{where}: unknown input(s) {sorted(set(given) - set(cls.ports))}")
                missing = [p for p, (_, required, _) in cls.ports.items() if required and p not in given]
                if missing:
                    raise CompileError(f"{where}: missing input(s) {missing}")
            wires, direct[b["id"]], every[b["id"]] = {}, set(), set()
            for port, ref in given.items():
                is_direct = True if cls.ports is None else cls.ports[port][2]
                if _is_constant(ref):
                    if not isinstance(ref, bool) and not math.isfinite(ref):
                        raise CompileError(f"{where}: the constant on {port!r} is not finite")
                    wires[port] = ("const", ref if isinstance(ref, bool) else float(ref))
                elif ref in self.inputs:
                    wires[port] = ("input", ref)
                elif ref in writer:
                    wires[port] = ("block", writer[ref], is_direct)
                    every[b["id"]].add(writer[ref][0])
                    if is_direct:
                        direct[b["id"]].add(writer[ref][0])
                else:
                    raise CompileError(f"{where}: {ref} is neither an input nor a block's output")
            self.wiring[b["id"]] = wires

        self.order = self._order(direct)

        # Settings, types and the blocks themselves, in an order where types are known.
        self.blocks, self.types, self.fallback = {}, {}, {}
        for b in specs:  # every type but these two fixes the types of its outputs
            if CATALOGUE[b["type"]] not in (FormulaBlock, Delay):
                self.types.update({(b["id"], port): kind for port, kind in CATALOGUE[b["type"]].outputs.items()})
        pending = list(by_id)
        while pending:
            progressed = False
            for bid in list(pending):
                b = by_id[bid]
                where, cls = f"block {bid}", CATALOGUE[b["type"]]
                in_types, ready = {}, True
                for port, src in self.wiring[bid].items():
                    if src[0] == "const":
                        in_types[port] = _type_of(src[1])
                    elif src[0] == "input":
                        in_types[port] = self.inputs[src[1]]["type"]
                    elif src[1] in self.types:
                        in_types[port] = self.types[src[1]]
                    elif cls is Delay and (b.get("settings") or {}).get("initial") is not None:
                        continue  # a delay on a loop takes its type from its initial value
                    else:
                        ready = False
                if not ready:
                    continue
                for port, kind in in_types.items():
                    want = cls.ports[port][0] if cls.ports is not None else None
                    if want is not None and kind != want:
                        raise CompileError(f"{where}: input {port!r} takes a {want}, and was given a {kind}")
                try:
                    block = cls(self._settings(where, cls, b.get("settings") or {}), self.period, in_types)
                except CompileError as exc:
                    raise CompileError(f"{where}: {exc}") from exc
                out_types = block.out_types(in_types)
                for port, kind in out_types.items():
                    self.types[(bid, port)] = kind
                fallback = dict(b.get("fallback") or {})
                for port, value in fallback.items():
                    if port not in cls.outputs:
                        raise CompileError(f"{where}: fallback names no output {port!r}")
                    if not _is_constant(value) or _type_of(value) != out_types[port]:
                        raise CompileError(f"{where}: the fallback for {port!r} is a {out_types[port]}")
                    if out_types[port] == NUMBER and not math.isfinite(value):
                        raise CompileError(f"{where}: the fallback for {port!r} is finite")
                self.blocks[bid], self.fallback[bid] = block, fallback
                pending.remove(bid)
                progressed = True
            if not progressed:
                raise CompileError(f"the types of blocks {sorted(pending)} cannot be worked out")
        for bid, wires in self.wiring.items():
            cls = CATALOGUE[by_id[bid]["type"]]
            for port, src in wires.items():
                if src[0] == "block" and cls is Delay and self.types[src[1]] != self.types[(bid, "y")]:
                    raise CompileError(f"block {bid}: its initial value is not of its input's type")

        # Section 5 rule 4: a delay on a loop has an initial value.
        for bid, block in self.blocks.items():
            if isinstance(block, Delay) and block.s["initial"] is None and self._reaches(every, bid, bid):
                raise CompileError(f"block {bid}: a delay on a loop needs an initial value")

        self.signal_types = {sig: self.types[w] for sig, w in self.published.items()}
        self.initial_blocks = copy.deepcopy(self.blocks)
        self.fingerprint = repr((self.period, sorted(self.inputs.items()), specs))
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

    def _settings(self, where, cls, raw):
        if set(raw) - set(cls.settings):
            raise CompileError(f"{where}: unknown setting(s) {sorted(set(raw) - set(cls.settings))}")

        def length(name, value):
            try:
                return seconds(value)
            except CompileError as exc:
                raise CompileError(f"{where}: setting {name!r}: {exc}") from exc

        out = {}
        for name, (kind, required, default) in cls.settings.items():
            if name not in raw:
                if required:
                    raise CompileError(f"{where}: missing setting {name!r}")
                out[name] = default
                continue
            value = raw[name]
            if kind == "choice":
                if value not in default:
                    raise CompileError(f"{where}: setting {name!r} is one of {list(default)}")
            elif kind in ("ticks", "ticks1"):
                span = length(name, value)
                if span < 0:
                    raise CompileError(f"{where}: setting {name!r} is not negative")
                value = ticks_of(span, self.period, f"setting {name!r}", least=1 if kind == "ticks1" else 0)
            elif kind == "seconds":
                value = length(name, value)
            elif kind == "const":
                if not _is_constant(value) or (not isinstance(value, bool) and not math.isfinite(value)):
                    raise CompileError(f"{where}: setting {name!r} is a finite number, or true or false")
            elif kind == "int":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise CompileError(f"{where}: setting {name!r} must be a whole number")
            elif kind == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise CompileError(f"{where}: setting {name!r} must be a finite number")
            elif not isinstance(value, str):
                raise CompileError(f"{where}: setting {name!r} must be text")
            out[name] = value
        return out

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

    # ---- state

    def reset(self):
        self.blocks = copy.deepcopy(self.initial_blocks)
        self.k = 0  # the next tick to run
        self.zero = None  # the time of tick 0
        self.last_now = None
        self.written = {}  # input -> (state, value, sample time, serial)
        self.serial = 0
        self.seen = 0  # the serial of the latest write the last tick saw

    def save(self):
        state = (self.blocks, self.k, self.written, self.serial, self.seen)
        return self.fingerprint, copy.deepcopy(state)

    def restore(self, saved):
        fingerprint, state = saved
        if fingerprint != self.fingerprint:
            raise ValueError("this state was saved from a different graph")  # 8 rule 3
        self.blocks, self.k, self.written, self.serial, self.seen = copy.deepcopy(state)
        self.zero, self.last_now = None, None  # 8 rule 4: time did not pass

    def write(self, name, state, value=None, sampled=None):
        """The host writes an input: a state, a value, and the time it was sampled."""
        if name not in self.inputs:
            raise KeyError(f"{name} is not an input of this graph")
        if state not in _WORST_FIRST:
            raise ValueError(f"{state!r} is not a state")
        if state in (GOOD, UNCERTAIN):
            if _type_of(value) != self.inputs[name]["type"] and not (
                self.inputs[name]["type"] == NUMBER and isinstance(value, (int, float))
            ):
                raise ValueError(f"{name} is a {self.inputs[name]['type']}")
            if self.inputs[name]["type"] == NUMBER:
                value = float(value)
        self.serial += 1
        self.written[name] = (state, value, sampled, self.serial)

    def _input(self, name, k, t, missed):
        """Section 7.2."""
        spec = self.inputs[name]
        if missed:
            return Val(BAD)
        if name not in self.written:
            if spec["initial"] is not None:
                value = spec["initial"]
                return Val(UNCERTAIN, value if isinstance(value, bool) else float(value))
            return Val(BAD) if k * self.period > spec["max_age"] else Val(NOT_READY)
        state, value, sampled, serial = self.written[name]
        new = serial > self.seen
        if state in (NOT_READY, BAD):
            return Val(state, None, new)
        age = 0.0 if sampled is None else max(0.0, t - sampled)
        ahead = sampled is not None and sampled - t > self.period
        if (spec["type"] == NUMBER and not math.isfinite(value)) or age > spec["max_age"] or ahead:
            return Val(BAD, None, new)
        return Val(state, value, new)

    # ---- time

    def tick(self, now):
        """Section 6: run every tick that is due. Returns (ticks run, outputs of the last)."""
        if self.last_now is not None and now < self.last_now:
            raise ValueError("the time passed to tick does not go backwards")
        self.last_now = now
        if self.zero is None:
            self.zero = now - self.k * self.period
        due = []
        while self.zero + (self.k + len(due)) * self.period <= now + self.period / 2:  # 6 rule 4
            due.append(self.k + len(due))
        out = None
        for k in due:
            out = self._run(k, missed=k != due[-1])
        return len(due), out

    def _run(self, k, missed):
        t = self.zero + k * self.period
        inputs = {name: self._input(name, k, t, missed) for name in self.inputs}
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

        for bid in self.order:  # first phase
            block, ins = self.blocks[bid], read(bid, True)
            signals = [v for port, v in ins.items() if self.wiring[bid][port][0] != "const"]
            new = not signals or any(v.new for v in signals)
            for port, val in block.output(k, ins).items():
                if usable(val) and isinstance(val.v, float) and not math.isfinite(val.v):
                    val = Val(BAD)  # section 3 rule 6
                if not usable(val):
                    val = Val(val.state, None, val.new)
                    if port in self.fallback[bid]:  # 7.10
                        value = self.fallback[bid][port]
                        val = Val(UNCERTAIN, value if isinstance(value, bool) else float(value))
                now[(bid, port)] = Val(val.state, val.v, val.new if block.own_new else new)
        for bid in self.order:  # second phase
            self.blocks[bid].update(k, read(bid, False))
        if not missed:
            self.seen = self.serial
        self.k = k + 1
        return {sig: now[w] for sig, w in self.published.items()}

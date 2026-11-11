#!/usr/bin/env python3
"""A reference for the version 2 semantics proposal (docs/semantics_spec_v2.md).

Small, slow and written to be read beside the proposal. It is not the
library and shares no code with it. Its job is to be a second opinion: the
vectors in vectors/ state what each rule should give, worked out by hand,
and this has to agree with them.

Stdlib only. run.py loads the vectors (it needs PyYAML) and drives this.
"""

from __future__ import annotations

import ast
import collections
import copy
import math
import re
import statistics

GOOD, NOT_READY, BAD = "good", "not_ready", "bad"
Val = collections.namedtuple("Val", "state v")
NOT_READY_VAL = Val(NOT_READY, None)
BAD_VAL = Val(BAD, None)
_DURATION = re.compile(r"^(\d+(?:\.\d+)?)(ms|s|m|h)$")
_UNIT = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


class CompileError(Exception):
    """The graph is refused. Raised when a graph is built, never while it runs."""


def good(v):
    return Val(GOOD, float(v))


def worst(vals):
    """Section 7.1 rule 1: bad over not_ready over good."""
    states = {v.state for v in vals}
    return BAD if BAD in states else NOT_READY if NOT_READY in states else GOOD


def seconds(text):
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    m = _DURATION.match(str(text))
    if not m:
        raise CompileError(f"{text!r} is not a length of time (use 500ms, 3s, 2m, 1h)")
    return float(m.group(1)) * _UNIT[m.group(2)]


def whole_ticks(duration, period, what):
    n = duration / period
    if abs(n - round(n)) > 1e-9 or round(n) < 1:
        raise CompileError(f"{what} is {duration} s, which is not a whole number of periods of {period} s")
    return round(n)


# ---------------------------------------------------------------- formulas

_BIN = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b}
_CMP = {
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
}
_FUNCS = {"abs": (abs, 1), "min": (min, 2), "max": (max, 2)}


class Formula:
    """Arithmetic, comparison, three-valued logic and when(condition, a, b)."""

    def __init__(self, text, names):
        try:
            self.tree = ast.parse(str(text), mode="eval").body
        except SyntaxError as exc:
            raise CompileError(f"formula {text!r} does not parse: {exc.msg}") from exc
        self._check(self.tree, set(names))

    def _check(self, node, names):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, bool)):
            return
        if isinstance(node, ast.Name):
            if node.id not in names:
                raise CompileError(f"formula uses {node.id!r}, which is not one of the block's inputs")
            return
        if isinstance(node, ast.BinOp) and (type(node.op) in _BIN or isinstance(node.op, ast.Div)):
            children = [node.left, node.right]
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.Not)):
            children = [node.operand]
        elif isinstance(node, ast.BoolOp):
            children = node.values
        elif isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMP:
            children = [node.left, node.comparators[0]]
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            name, n = node.func.id, len(node.args)
            if name != "when" and name not in _FUNCS:
                raise CompileError(f"formula calls unknown function {name!r}")
            if n != (3 if name == "when" else _FUNCS[name][1]):
                raise CompileError(f"formula calls {name} with {n} argument(s)")
            children = node.args
        else:
            raise CompileError(f"formula uses unsupported syntax ({type(node).__name__})")
        for child in children:
            self._check(child, names)

    def eval(self, env):
        return self._eval(self.tree, env)

    def _eval(self, node, env):
        if isinstance(node, ast.Constant):
            return good(node.value)
        if isinstance(node, ast.Name):
            return env[node.id]
        if isinstance(node, ast.BoolOp):  # 7.1 rule 2
            vals = [self._eval(v, env) for v in node.values]
            decides = isinstance(node.op, ast.Or)
            if any(v.state == GOOD and bool(v.v) == decides for v in vals):
                return good(decides)
            state = worst(vals)
            return good(not decides) if state == GOOD else Val(state, None)
        if isinstance(node, ast.Call) and node.func.id == "when":  # 7.1 rule 3
            cond = self._eval(node.args[0], env)
            if cond.state != GOOD:
                return Val(cond.state, None)
            return self._eval(node.args[1] if cond.v else node.args[2], env)
        if isinstance(node, ast.UnaryOp):
            vals = [self._eval(node.operand, env)]
            fn = (lambda a: not a) if isinstance(node.op, ast.Not) else (lambda a: -a)
        elif isinstance(node, ast.BinOp):
            vals = [self._eval(node.left, env), self._eval(node.right, env)]
            fn = (lambda a, b: a / b) if isinstance(node.op, ast.Div) else _BIN[type(node.op)]
        elif isinstance(node, ast.Compare):
            vals = [self._eval(node.left, env), self._eval(node.comparators[0], env)]
            fn = _CMP[type(node.ops[0])]
        else:
            vals = [self._eval(a, env) for a in node.args]
            fn = _FUNCS[node.func.id][0]
        state = worst(vals)
        if state != GOOD:
            return Val(state, None)
        try:
            return good(fn(*(v.v for v in vals)))
        except ZeroDivisionError:  # 7.1 rule 4
            return BAD_VAL


# ---------------------------------------------------------------- blocks


class Block:
    inputs: dict | None = {}  # port -> required; None means any names
    settings: dict = {}  # name -> (kind, required, default)
    outputs: tuple = ("y",)
    previous: frozenset = frozenset()  # input ports read from the previous tick (section 5)

    def __init__(self, settings, period, in_names):
        self.s, self.period = settings, period

    def step(self, t, ins):
        raise NotImplementedError


class FormulaBlock(Block):
    inputs = None
    settings = {"expr": ("str", True, None)}

    def __init__(self, settings, period, in_names):
        super().__init__(settings, period, in_names)
        self.formula = Formula(settings["expr"], in_names)

    def step(self, t, ins):
        return {"y": self.formula.eval(ins)}


class AllGood(Block):
    """True when every input is good. Always good itself."""

    inputs = None

    def step(self, t, ins):
        return {"y": good(all(v.state == GOOD for v in ins.values()))}


class Delay(Block):
    """Its input from `ticks` ticks ago; `initial`, if given, until then."""

    inputs = {"x": True}
    settings = {"ticks": ("int", False, 1), "initial": ("number", False, None)}
    previous = frozenset({"x"})

    def __init__(self, *a):
        super().__init__(*a)
        if self.s["ticks"] < 1:
            raise CompileError("a delay is at least one tick")
        self.past = collections.deque()
        self.count = 0

    def step(self, t, ins):
        # The engine hands this port last tick's value, so past[0] is the
        # input from `ticks` ticks ago once that many ticks have run.
        self.past.append(ins["x"])
        if len(self.past) > self.s["ticks"]:
            self.past.popleft()
        self.count += 1
        if self.count <= self.s["ticks"]:
            initial = self.s["initial"]
            return {"y": good(initial) if initial is not None else NOT_READY_VAL}
        return {"y": self.past[0]}


class Window(Block):
    """Statistics of the usable samples in the last `window` (section 7.2)."""

    inputs = {"x": True}
    settings = {"window": ("duration", True, None), "min_good": ("number", False, 1.0)}
    outputs = ("mean", "median", "min", "max", "spread", "slope")

    def __init__(self, *a):
        super().__init__(*a)
        self.n = whole_ticks(self.s["window"], self.period, "a window")
        if not 0.0 < self.s["min_good"] <= 1.0:
            raise CompileError("min_good is a fraction above 0 and at most 1")
        self.need = math.ceil(self.s["min_good"] * self.n - 1e-9)
        self.buf = collections.deque(maxlen=self.n)

    def step(self, t, ins):
        self.buf.append((t, ins["x"]))
        usable = [(ti, v.v) for ti, v in self.buf if v.state == GOOD]
        if len(usable) < self.need:
            # Ticks before the graph started count as not ready.
            missing = [v for _, v in self.buf if v.state != GOOD]
            missing += [NOT_READY_VAL] * (self.n - len(self.buf))
            return dict.fromkeys(self.outputs, Val(worst(missing), None))
        ys = [y for _, y in usable]
        out = {
            "mean": good(sum(ys) / len(ys)),
            "median": good(statistics.median(ys)),
            "min": good(min(ys)),
            "max": good(max(ys)),
            "spread": good(max(ys) - min(ys)),
        }
        mt = sum(ti for ti, _ in usable) / len(usable)
        den = sum((ti - mt) ** 2 for ti, _ in usable)
        if den == 0.0:
            out["slope"] = BAD_VAL  # one sample has no slope
        else:
            my = sum(ys) / len(ys)
            out["slope"] = good(sum((ti - mt) * (y - my) for ti, y in usable) / den)
        return out


class Deadband(Block):
    """Holds its output until the input has moved by `step` or more (section 7.2)."""

    inputs = {"x": True}
    settings = {"step": ("number", True, None), "ride_through": ("duration", False, 0.0)}

    def __init__(self, *a):
        super().__init__(*a)
        self.held, self.seen = None, None

    def step(self, t, ins):
        x = ins["x"]
        if x.state == GOOD:
            if self.held is None or abs(x.v - self.held) >= self.s["step"]:
                self.held = x.v
            self.seen = t
            return {"y": good(self.held)}
        if self.held is not None and t - self.seen <= self.s["ride_through"] + 1e-9:
            return {"y": good(self.held)}
        return {"y": Val(x.state, None)}


class HeldFor(Block):
    """True once the input has been true for longer than `time` (section 7.3 rule 1)."""

    inputs = {"x": True}
    settings = {"time": ("duration", True, None), "on_bad": ("choice", True, ("reset", "hold"))}

    def __init__(self, *a):
        super().__init__(*a)
        self.since = None

    def step(self, t, ins):
        x = ins["x"]
        if x.state == GOOD:
            self.since = (self.since if self.since is not None else t) if x.v else None
            return {"y": good(self.since is not None and t - self.since > self.s["time"] + 1e-9)}
        if self.s["on_bad"] == "reset" or self.since is None:
            self.since = None
            return {"y": Val(x.state, None)}
        return {"y": good(t - self.since > self.s["time"] + 1e-9)}


class SinceTrue(Block):
    """True when the input has not been true for longer than `time` (section 7.3 rule 2)."""

    inputs = {"x": True}
    settings = {"time": ("duration", True, None)}

    def __init__(self, *a):
        super().__init__(*a)
        self.last = None

    def step(self, t, ins):
        x = ins["x"]
        if self.last is None or (x.state == GOOD and x.v):
            self.last = t
        return {"y": good(t - self.last > self.s["time"] + 1e-9)}


class Latch(Block):
    """False until the input is first true, then true (section 7.3 rule 3)."""

    inputs = {"set": True}

    def __init__(self, *a):
        super().__init__(*a)
        self.on = False

    def step(self, t, ins):
        self.on = self.on or (ins["set"].state == GOOD and bool(ins["set"].v))
        return {"y": good(self.on)}


class Total(Block):
    """A running total of the input over time, and the time it missed (section 7.4)."""

    inputs = {"x": True}
    settings = {"per": ("duration", False, 1.0)}
    outputs = ("y", "missed")

    def __init__(self, *a):
        super().__init__(*a)
        self.total, self.missed = 0.0, 0.0

    def step(self, t, ins):
        if ins["x"].state == GOOD:
            self.total += ins["x"].v * self.period / self.s["per"]
        else:
            self.missed += self.period
        return {"y": good(self.total), "missed": good(self.missed)}


class Kalman1(Block):
    """One state relaxing toward `model` with time constant `tau`, corrected by `z` (section 7.5)."""

    inputs = {"z": True, "model": True}
    settings = {"tau": ("duration", True, None), "q": ("number", True, None), "r": ("number", True, None)}
    outputs = ("x", "sigma")

    def __init__(self, *a):
        super().__init__(*a)
        self.x, self.var = None, None

    def step(self, t, ins):
        z, model = ins["z"], ins["model"]
        if self.x is None:
            if z.state != GOOD:
                return dict.fromkeys(self.outputs, NOT_READY_VAL)
            self.x, self.var = z.v, self.s["r"]
            return {"x": good(self.x), "sigma": good(math.sqrt(self.var))}
        if model.state == GOOD:
            a = 1.0 - self.period / self.s["tau"]
            self.x = a * self.x + (1 - a) * model.v
            self.var = a * a * self.var + self.s["q"] * self.period
        else:
            self.var += self.s["q"] * self.period
        if z.state == GOOD:
            k = self.var / (self.var + self.s["r"])
            self.x += k * (z.v - self.x)
            self.var *= 1 - k
        return {"x": good(self.x), "sigma": good(math.sqrt(self.var))}


CATALOGUE = {
    "formula": FormulaBlock,
    "all_good": AllGood,
    "delay": Delay,
    "window": Window,
    "deadband": Deadband,
    "held_for": HeldFor,
    "since_true": SinceTrue,
    "latch": Latch,
    "total": Total,
    "kalman1": Kalman1,
}

_GRAPH_KEYS = {"period", "inputs", "blocks"}
_BLOCK_KEYS = {"id", "type", "in", "settings", "out", "fallback"}
_INPUT_KEYS = {"max_age", "unit"}


def _setting(where, name, kind, value):
    if kind == "duration":
        return seconds(value)
    ok = {
        "int": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "str": isinstance(value, str),
    }
    if isinstance(kind, str) and kind in ok:
        if not ok[kind]:
            raise CompileError(f"{where}: setting {name!r} must be a {kind}")
        return value
    raise CompileError(f"{where}: setting {name!r} has no known kind")


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

        self.max_age = {}
        for name, spec in (graph.get("inputs") or {}).items():
            spec = spec or {}
            if set(spec) - _INPUT_KEYS:
                raise CompileError(f"input {name}: unknown key(s) {sorted(set(spec) - _INPUT_KEYS)}")
            self.max_age[name] = seconds(spec["max_age"]) if "max_age" in spec else math.inf

        specs = graph.get("blocks") or []
        ids = [b.get("id") for b in specs]
        if len(set(ids)) != len(ids) or None in ids:
            raise CompileError("every block has an id of its own")

        # Every signal a block may read: an input, a published output, or id.port.
        writer = {}
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
                if signal in writer or signal in self.max_age:
                    raise CompileError(f"{where}: {signal} already has a writer")
                writer[signal] = (b["id"], port)
            for port in cls.outputs:
                writer.setdefault(f"{b['id']}.{port}", (b["id"], port))

        self.blocks, self.wiring, self.fallback, deps = {}, {}, {}, {}
        for b in specs:
            where = f"block {b['id']}"
            cls = CATALOGUE[b["type"]]
            given = b.get("in") or {}
            if cls.inputs is not None:
                if set(given) - set(cls.inputs):
                    raise CompileError(f"{where}: unknown input(s) {sorted(set(given) - set(cls.inputs))}")
                missing = [n for n, required in cls.inputs.items() if required and n not in given]
                if missing:
                    raise CompileError(f"{where}: missing input(s) {missing}")
            wires, reads = {}, set()
            for port, ref in given.items():
                if isinstance(ref, (int, float)):
                    wires[port] = ("const", float(ref))
                elif ref in self.max_age:
                    wires[port] = ("input", ref)
                elif ref in writer:
                    wires[port] = ("block", writer[ref])
                    if port not in cls.previous:
                        reads.add(writer[ref][0])
                else:
                    raise CompileError(f"{where}: {ref} is neither an input nor a block's output")
            raw = b.get("settings") or {}
            if set(raw) - set(cls.settings):
                raise CompileError(f"{where}: unknown setting(s) {sorted(set(raw) - set(cls.settings))}")
            settings = {}
            for name, (kind, required, default) in cls.settings.items():
                if name not in raw:
                    if required:
                        raise CompileError(f"{where}: missing setting {name!r}")
                    settings[name] = default
                elif kind == "choice":
                    if raw[name] not in default:
                        raise CompileError(f"{where}: setting {name!r} is one of {list(default)}")
                    settings[name] = raw[name]
                else:
                    settings[name] = _setting(where, name, kind, raw[name])
            for port in b.get("fallback") or {}:
                if port not in cls.outputs:
                    raise CompileError(f"{where}: fallback names no output {port!r}")
            try:
                self.blocks[b["id"]] = cls(settings, self.period, list(given))
            except CompileError as exc:
                raise CompileError(f"{where}: {exc}") from exc
            self.wiring[b["id"]] = wires
            self.fallback[b["id"]] = dict(b.get("fallback") or {})
            deps[b["id"]] = reads

        self.order = self._order(deps)
        self.published = {sig: w for sig, w in writer.items() if "." not in sig or sig.split(".")[0] not in self.blocks}
        self.initial = copy.deepcopy(self.blocks)
        self.reset()

    @staticmethod
    def _order(deps):
        """Section 5: one order, ties by id, loops refused by name."""
        done, out = set(), []
        while len(out) < len(deps):
            ready = sorted(n for n in deps if n not in done and deps[n] <= done)
            if not ready:
                raise CompileError(f"dependency loop among blocks {sorted(set(deps) - done)}")
            out.append(ready[0])
            done.add(ready[0])
        return out

    def reset(self):
        self.blocks = copy.deepcopy(self.initial)
        self.k = 0
        self.written = {}  # input -> (state, value, sample time)
        self.last = {}  # (block, port) -> Val, from the previous tick
        self.last_inputs = {}  # input -> Val, as the previous tick saw it

    def save(self):
        return copy.deepcopy((self.blocks, self.k, self.written, self.last, self.last_inputs))

    def restore(self, saved):
        self.blocks, self.k, self.written, self.last, self.last_inputs = copy.deepcopy(saved)

    def write(self, name, state, value=None, age=0.0):
        """The host writes an input, sampled `age` seconds before the next tick."""
        if name not in self.max_age:
            raise KeyError(f"{name} is not an input of this graph")
        self.written[name] = (state, value, self.k * self.period - age)

    def _input(self, name, t):
        """Section 7.7."""
        if name not in self.written:
            return NOT_READY_VAL
        state, value, sampled = self.written[name]
        if state != GOOD:
            return Val(state, None)
        if not math.isfinite(value) or t - sampled > self.max_age[name] + 1e-9:
            return BAD_VAL
        return good(value)

    def tick(self):
        t = self.k * self.period
        now = {}
        inputs = {name: self._input(name, t) for name in self.max_age}
        for bid in self.order:
            block, ins = self.blocks[bid], {}
            for port, src in self.wiring[bid].items():
                if src[0] == "const":
                    ins[port] = good(src[1])
                elif src[0] == "input":
                    source = self.last_inputs if port in block.previous else inputs
                    ins[port] = source.get(src[1], NOT_READY_VAL)
                elif port in block.previous:
                    ins[port] = self.last.get(src[1], NOT_READY_VAL)
                else:
                    ins[port] = now[src[1]]
            for port, val in block.step(t, ins).items():
                if val.state == GOOD and not math.isfinite(val.v):
                    val = BAD_VAL
                if val.state != GOOD and port in self.fallback[bid]:
                    val = good(self.fallback[bid][port])  # 7.6
                now[(bid, port)] = val
        self.last, self.last_inputs = now, inputs
        self.k += 1
        return {sig: now[w] for sig, w in self.published.items()}

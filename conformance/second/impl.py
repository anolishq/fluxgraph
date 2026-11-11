"""Second implementation of FluxGraph semantics v2 (proposal), from the text alone.

Standard library only. See ASSUMPTIONS.md for every guess made here.
"""

import copy
import heapq
import json
import math
import re
from fractions import Fraction

GOOD, NOT_READY, BAD = "good", "not_ready", "bad"
_RANK = {GOOD: 0, NOT_READY: 1, BAD: 2}
_STATES = (GOOD, NOT_READY, BAD)


class CompileError(Exception):
    pass


class RestoreError(ValueError):
    pass


def _worst(states):
    w = GOOD
    for s in states:
        if _RANK[s] > _RANK[w]:
            w = s
    return w


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _norm(sv):
    """A good value must be finite; anything else carries no number."""
    s, v = sv
    if s != GOOD:
        return (s, None)
    v = float(v)
    if not math.isfinite(v):
        return (BAD, None)
    return (GOOD, v)


# ---------------------------------------------------------------- durations

_DUR = re.compile(r"^\s*((?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)\s*(ms|s|m|h)\s*$")
_UNIT = {"ms": Fraction(1, 1000), "s": Fraction(1), "m": Fraction(60), "h": Fraction(3600)}


def _frac(v, what):
    if not _is_num(v):
        raise CompileError("%s: expected a number, got %r" % (what, v))
    if isinstance(v, float):
        if not math.isfinite(v):
            raise CompileError("%s: %r is not finite" % (what, v))
        return Fraction(repr(v))
    return Fraction(v)


def _duration(v, what):
    """A length of time as an exact Fraction of seconds."""
    if isinstance(v, str):
        m = _DUR.match(v)
        if not m:
            raise CompileError("%s: %r is not a length of time" % (what, v))
        return Fraction(m.group(1)) * _UNIT[m.group(2)]
    if _is_num(v):
        return _frac(v, what)
    raise CompileError("%s: %r is not a length of time" % (what, v))


# ------------------------------------------------------------------ formula

_TOK = re.compile(
    r"\s*(?:(?P<num>(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)"
    r"|(?P<id>[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<op><=|>=|==|!=|<|>|\+|-|\*|/|\(|\)|,))"
)
_RESERVED = {"and", "or", "not", "abs", "min", "max", "when"}
_FUNCS = {"abs": 1, "min": 2, "max": 2, "when": 3}
_CMP = {"<", "<=", ">", ">=", "==", "!="}


class _Parser:
    def __init__(self, text, where):
        self.where = where
        self.toks = []
        self.names = set()
        pos = 0
        text = text.rstrip()
        while pos < len(text):
            m = _TOK.match(text, pos)
            if not m:
                self.fail("cannot read %r" % text[pos:].strip()[:20])
            if m.group("num") is not None:
                self.toks.append(("num", float(m.group("num"))))
            elif m.group("id") is not None:
                self.toks.append(("id", m.group("id")))
            else:
                self.toks.append(("op", m.group("op")))
            pos = m.end()
        self.i = 0

    def fail(self, msg):
        raise CompileError("%s: formula: %s" % (self.where, msg))

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else ("end", None)

    def take(self):
        t = self.peek()
        self.i += 1
        return t

    def accept(self, kind, val):
        if self.peek() == (kind, val):
            self.i += 1
            return True
        return False

    def expect(self, val):
        if not self.accept("op", val):
            self.fail("expected %r, found %r" % (val, self.peek()[1]))

    def parse(self):
        if not self.toks:
            self.fail("empty expression")
        node = self.p_or()
        if self.peek()[0] != "end":
            self.fail("unexpected %r" % (self.peek()[1],))
        return node

    def p_or(self):
        n = self.p_and()
        while self.accept("id", "or"):
            n = ("or", n, self.p_and())
        return n

    def p_and(self):
        n = self.p_not()
        while self.accept("id", "and"):
            n = ("and", n, self.p_not())
        return n

    def p_not(self):
        if self.accept("id", "not"):
            return ("not", self.p_not())
        return self.p_cmp()

    def p_cmp(self):
        n = self.p_add()
        if self.peek()[0] == "op" and self.peek()[1] in _CMP:
            op = self.take()[1]
            n = ("cmp", op, n, self.p_add())
            if self.peek()[0] == "op" and self.peek()[1] in _CMP:
                raise CompileError("comparisons do not chain: write (a < b) and (b < c)")
        return n

    def p_add(self):
        n = self.p_mul()
        while self.peek() in (("op", "+"), ("op", "-")):
            op = self.take()[1]
            n = ("arith", op, n, self.p_mul())
        return n

    def p_mul(self):
        n = self.p_unary()
        while self.peek() in (("op", "*"), ("op", "/")):
            op = self.take()[1]
            n = ("arith", op, n, self.p_unary())
        return n

    def p_unary(self):
        if self.accept("op", "-"):
            return ("neg", self.p_unary())
        return self.p_primary()

    def p_primary(self):
        kind, val = self.take()
        if kind == "num":
            return ("num", val)
        if kind == "op" and val == "(":
            n = self.p_or()
            self.expect(")")
            return n
        if kind == "id":
            if val in _FUNCS:
                self.expect("(")
                args = [self.p_or()]
                while self.accept("op", ","):
                    args.append(self.p_or())
                self.expect(")")
                if len(args) != _FUNCS[val]:
                    self.fail("%s takes %d argument(s), got %d" % (val, _FUNCS[val], len(args)))
                return ("call", val, args)
            if val in _RESERVED:
                self.fail("unexpected %r" % val)
            self.names.add(val)
            return ("var", val)
        self.fail("unexpected %r" % (val if kind != "end" else "end of expression"))


def _eval(node, env):
    kind = node[0]
    if kind == "num":
        return (GOOD, node[1])
    if kind == "var":
        return env[node[1]]
    if kind == "neg":
        s, v = _eval(node[1], env)
        return (GOOD, -v) if s == GOOD else (s, None)
    if kind == "not":
        s, v = _eval(node[1], env)
        return (GOOD, 0.0 if v != 0 else 1.0) if s == GOOD else (s, None)
    if kind in ("and", "or"):
        a = _eval(node[1], env)
        b = _eval(node[2], env)
        decides = (lambda v: v == 0) if kind == "and" else (lambda v: v != 0)
        decided = 0.0 if kind == "and" else 1.0
        for s, v in (a, b):
            if s == GOOD and decides(v):
                return (GOOD, decided)
        w = _worst((a[0], b[0]))
        if w != GOOD:
            return (w, None)
        return (GOOD, 1.0 - decided)
    if kind in ("arith", "cmp"):
        op = node[1]
        a = _eval(node[2], env)
        b = _eval(node[3], env)
        w = _worst((a[0], b[0]))
        if w != GOOD:
            return (w, None)
        x, y = a[1], b[1]
        if kind == "cmp":
            r = {"<": x < y, "<=": x <= y, ">": x > y, ">=": x >= y, "==": x == y, "!=": x != y}[op]
            return (GOOD, 1.0 if r else 0.0)
        if op == "/":
            if y == 0:
                return (BAD, None)
            r = x / y
        elif op == "+":
            r = x + y
        elif op == "-":
            r = x - y
        else:
            r = x * y
        return _norm((GOOD, r))
    if kind == "call":
        name, args = node[1], node[2]
        if name == "when":
            c = _eval(args[0], env)
            if c[0] != GOOD:
                return (c[0], None)
            return _eval(args[1] if c[1] != 0 else args[2], env)
        vals = [_eval(a, env) for a in args]
        w = _worst(s for s, _ in vals)
        if w != GOOD:
            return (w, None)
        if name == "abs":
            return (GOOD, abs(vals[0][1]))
        if name == "min":
            return (GOOD, min(vals[0][1], vals[1][1]))
        return (GOOD, max(vals[0][1], vals[1][1]))
    raise AssertionError(kind)


# -------------------------------------------------------------- block types
# settings: name -> (kind, required, default)
# inputs:   None for "any", else {port: required}

_TYPES = {
    "formula": {"inputs": None, "outputs": ["y"], "settings": {"expr": ("str", True, None)}},
    "all_good": {"inputs": None, "outputs": ["y"], "settings": {}},
    "delay": {
        "inputs": {"x": True},
        "outputs": ["y"],
        "prev": {"x"},
        "settings": {"ticks": ("int", False, 1), "initial": ("num", False, None)},
    },
    "window": {
        "inputs": {"x": True},
        "outputs": ["mean", "median", "min", "max", "spread", "slope"],
        "settings": {"window": ("dur", True, None), "min_good": ("num", False, 1)},
    },
    "deadband": {
        "inputs": {"x": True},
        "outputs": ["y"],
        "settings": {"step": ("num", True, None), "ride_through": ("dur", False, 0)},
    },
    "held_for": {
        "inputs": {"x": True},
        "outputs": ["y"],
        "settings": {"time": ("dur", True, None), "on_bad": ("str", True, None)},
    },
    "since_true": {"inputs": {"x": True}, "outputs": ["y"], "settings": {"time": ("dur", True, None)}},
    "latch": {"inputs": {"set": True}, "outputs": ["y"], "settings": {}},
    "total": {"inputs": {"x": True}, "outputs": ["y", "missed"], "settings": {"per": ("dur", False, 1)}},
    "kalman1": {
        "inputs": {"z": True, "model": True},
        "outputs": ["x", "sigma"],
        "settings": {"tau": ("dur", True, None), "q": ("num", True, None), "r": ("num", True, None)},
    },
}

_BLOCK_KEYS = {"id", "type", "in", "settings", "out", "fallback"}
_TOP_KEYS = {"period", "inputs", "blocks"}
_INPUT_KEYS = {"max_age", "unit", "signal"}


class _Block:
    pass


def _initial_state(b):
    t = b.type
    if t == "delay":
        return {"buf": []}
    if t == "window":
        return {"buf": []}
    if t == "deadband":
        return {"held": None, "last": None}
    if t == "held_for":
        return {"start": None}
    if t == "since_true":
        return {"clock": None}
    if t == "latch":
        return {"on": False}
    if t == "total":
        return {"y": 0.0, "missed": 0}
    if t == "kalman1":
        return {"x": None, "var": None}
    return {}


def _step(b, k, ins, period):
    """Evaluate block b at tick k. ins: port -> (state, value). Returns port -> (state, value)."""
    t, st, cfg = b.type, b.state, b.cfg
    if t == "formula":
        return {"y": _eval(b.ast, ins)}

    if t == "all_good":
        return {"y": (GOOD, 1.0 if all(s == GOOD for s, _ in ins.values()) else 0.0)}

    if t == "delay":
        n = cfg["ticks"]
        if len(st["buf"]) >= n:
            return {"y": st["buf"][0]}
        if cfg["initial"] is None:
            return {"y": (NOT_READY, None)}
        return {"y": (GOOD, cfg["initial"])}

    if t == "window":
        n = cfg["n"]
        s, v = ins["x"]
        st["buf"].append((s, v, k))
        del st["buf"][:-n]
        usable = [(kk, vv) for ss, vv, kk in st["buf"] if ss == GOOD]
        if len(usable) < cfg["min_good"] * n:
            states = [ss for ss, _, _ in st["buf"] if ss != GOOD]
            if len(st["buf"]) < n:
                states.append(NOT_READY)
            w = _worst(states)
            return {p: (w, None) for p in b.ports}
        vals = sorted(vv for _, vv in usable)
        m = len(vals)
        mean = math.fsum(vals) / m
        median = vals[m // 2] if m % 2 else (vals[m // 2 - 1] + vals[m // 2]) / 2.0
        out = {
            "mean": (GOOD, mean),
            "median": (GOOD, median),
            "min": (GOOD, vals[0]),
            "max": (GOOD, vals[-1]),
            "spread": (GOOD, vals[-1] - vals[0]),
        }
        if m < 2:
            out["slope"] = (BAD, None)
        else:
            k0 = usable[0][0]
            ts = [float((kk - k0) * period) for kk, _ in usable]
            tm = math.fsum(ts) / m
            num = math.fsum((tt - tm) * (vv - mean) for tt, (_, vv) in zip(ts, usable))
            den = math.fsum((tt - tm) ** 2 for tt in ts)
            out["slope"] = (GOOD, num / den) if den > 0 else (BAD, None)
        return out

    if t == "deadband":
        s, v = ins["x"]
        if s == GOOD:
            if st["held"] is None or abs(v - st["held"]) >= cfg["step"]:
                st["held"] = v
            st["last"] = k
            return {"y": (GOOD, st["held"])}
        if st["held"] is not None and (k - st["last"]) * period <= cfg["ride_through"]:
            return {"y": (GOOD, st["held"])}
        return {"y": (s, None)}

    if t == "held_for":
        s, v = ins["x"]
        if s == GOOD:
            if v != 0:
                if st["start"] is None:
                    st["start"] = k
                return {"y": (GOOD, 1.0 if (k - st["start"]) * period > cfg["time"] else 0.0)}
            st["start"] = None
            return {"y": (GOOD, 0.0)}
        if cfg["on_bad"] == "reset":
            st["start"] = None
            return {"y": (s, None)}
        if st["start"] is not None:
            return {"y": (GOOD, 1.0 if (k - st["start"]) * period > cfg["time"] else 0.0)}
        return {"y": (s, None)}

    if t == "since_true":
        s, v = ins["x"]
        if st["clock"] is None or (s == GOOD and v != 0):
            st["clock"] = k
        return {"y": (GOOD, 1.0 if (k - st["clock"]) * period > cfg["time"] else 0.0)}

    if t == "latch":
        s, v = ins["set"]
        if s == GOOD and v != 0:
            st["on"] = True
        return {"y": (GOOD, 1.0 if st["on"] else 0.0)}

    if t == "total":
        s, v = ins["x"]
        if s == GOOD:
            st["y"] += v * cfg["period_f"] / cfg["per_f"]
        else:
            st["missed"] += 1
        return {"y": (GOOD, st["y"]), "missed": (GOOD, float(st["missed"] * period))}

    if t == "kalman1":
        zs, z = ins["z"]
        ms, mv = ins.get("model", (NOT_READY, None))
        a, qp, r = cfg["a"], cfg["q"] * cfg["period_f"], cfg["r"]
        if st["x"] is None:
            if zs != GOOD:
                return {"x": (NOT_READY, None), "sigma": (NOT_READY, None)}
            st["x"], st["var"] = z, r
        else:
            if ms == GOOD:
                st["x"] = a * st["x"] + (1 - a) * mv
                st["var"] = a * a * st["var"] + qp
            else:
                st["var"] = st["var"] + qp
            if zs == GOOD:
                g = st["var"] / (st["var"] + r)
                st["x"] = st["x"] + g * (z - st["x"])
                st["var"] = st["var"] * (1 - g)
        return {"x": (GOOD, st["x"]), "sigma": (GOOD, math.sqrt(st["var"]))}

    raise AssertionError(t)


# ------------------------------------------------------------------ compile


def _setting(bid, name, kind, raw):
    what = "block %r: setting %r" % (bid, name)
    if kind == "dur":
        return _duration(raw, what)
    if kind == "num":
        _frac(raw, what)
        return raw
    if kind == "int":
        if not isinstance(raw, int) or isinstance(raw, bool):
            raise CompileError("%s: expected a whole number, got %r" % (what, raw))
        return raw
    if kind == "str":
        if not isinstance(raw, str):
            raise CompileError("%s: expected text, got %r" % (what, raw))
        return raw
    raise AssertionError(kind)


def _compile_block(raw, period, seen_ids):
    if not isinstance(raw, dict):
        raise CompileError("a block must be a mapping, got %r" % (raw,))
    if "id" not in raw:
        raise CompileError("a block has no id: %r" % (raw,))
    bid = raw["id"]
    if not isinstance(bid, str) or not bid:
        raise CompileError("block id %r is not a non-empty string" % (bid,))
    if bid in seen_ids:
        raise CompileError("duplicate block id %r" % bid)
    for key in raw:
        if key not in _BLOCK_KEYS:
            raise CompileError("block %r: unknown key %r" % (bid, key))
    if "type" not in raw:
        raise CompileError("block %r: no type" % bid)
    btype = raw["type"]
    if not isinstance(btype, str) or btype not in _TYPES:
        raise CompileError("block %r: unknown type %r" % (bid, btype))
    spec = _TYPES[btype]

    b = _Block()
    b.id, b.type, b.ports = bid, btype, list(spec["outputs"])
    b.prev = spec.get("prev", set())
    b.ast = None

    # settings
    given = raw.get("settings", {})
    if given is None:
        given = {}
    if not isinstance(given, dict):
        raise CompileError("block %r: settings must be a mapping" % bid)
    for name in given:
        if name not in spec["settings"]:
            raise CompileError("block %r: unknown setting %r" % (bid, name))
    s = {}
    for name, (kind, required, default) in spec["settings"].items():
        if name in given:
            s[name] = _setting(bid, name, kind, given[name])
        elif required:
            raise CompileError("block %r: missing required setting %r" % (bid, name))
        else:
            s[name] = None if default is None else _setting(bid, name, kind, default)

    def rng(name, ok, must):
        if not ok:
            raise CompileError("block %r: setting %r out of range: %r (%s)" % (bid, name, given.get(name), must))

    cfg = {"period_f": float(period)}
    if btype == "formula":
        p = _Parser(s["expr"], "block %r" % bid)
        b.ast = p.parse()
        b.names = p.names
    elif btype == "delay":
        rng("ticks", s["ticks"] >= 1, "must be 1 or more")
        cfg["ticks"] = s["ticks"]
        cfg["initial"] = None if s["initial"] is None else float(s["initial"])
    elif btype == "window":
        rng("window", s["window"] > 0, "must be longer than zero")
        n = s["window"] / period
        if n.denominator != 1:
            raise CompileError(
                "block %r: setting 'window' (%r) is not a whole number of periods" % (bid, given["window"])
            )
        mg = _frac(s["min_good"], "min_good")
        rng("min_good", 0 < mg <= 1, "must be more than 0 and at most 1")
        cfg["n"], cfg["min_good"] = int(n), mg
    elif btype == "deadband":
        rng("step", s["step"] >= 0, "must not be negative")
        rng("ride_through", s["ride_through"] >= 0, "must not be negative")
        cfg["step"], cfg["ride_through"] = float(s["step"]), s["ride_through"]
    elif btype == "held_for":
        rng("time", s["time"] >= 0, "must not be negative")
        rng("on_bad", s["on_bad"] in ("reset", "hold"), "must be 'reset' or 'hold'")
        cfg["time"], cfg["on_bad"] = s["time"], s["on_bad"]
    elif btype == "since_true":
        rng("time", s["time"] >= 0, "must not be negative")
        cfg["time"] = s["time"]
    elif btype == "total":
        rng("per", s["per"] > 0, "must be longer than zero")
        cfg["per_f"] = float(s["per"])
    elif btype == "kalman1":
        rng("tau", s["tau"] > 0, "must be longer than zero")
        rng("q", s["q"] >= 0, "must not be negative")
        rng("r", s["r"] > 0, "must be more than zero")
        if period > s["tau"]:
            raise CompileError("block %r: setting 'tau' (%r) is shorter than the period" % (bid, given["tau"]))
        cfg["a"] = float(1 - period / s["tau"])
        cfg["q"], cfg["r"] = float(s["q"]), float(s["r"])
    b.cfg = cfg
    b.norm_settings = {k: (str(v) if isinstance(v, Fraction) else v) for k, v in s.items()}

    # inputs
    ins = raw.get("in", {})
    if ins is None:
        ins = {}
    if not isinstance(ins, dict):
        raise CompileError("block %r: 'in' must be a mapping" % bid)
    b.raw_in = {}
    for port, src in ins.items():
        if not isinstance(port, str):
            raise CompileError("block %r: input port %r is not a name" % (bid, port))
        if btype == "formula":
            if port in _RESERVED:
                raise CompileError("block %r: input port %r is a reserved word" % (bid, port))
            if port not in b.names:
                raise CompileError("block %r: input port %r is not named in the formula" % (bid, port))
        elif spec["inputs"] is not None and port not in spec["inputs"]:
            raise CompileError("block %r: unknown input port %r" % (bid, port))
        if _is_num(src):
            if not math.isfinite(src):
                raise CompileError("block %r: input %r: constant %r is not finite" % (bid, port, src))
            b.raw_in[port] = ("const", float(src))
        elif isinstance(src, str):
            b.raw_in[port] = ("sig", src)
        else:
            raise CompileError("block %r: input %r must be a signal name or a number, got %r" % (bid, port, src))
    if btype == "formula":
        for name in sorted(b.names):
            if name not in b.raw_in:
                raise CompileError("block %r: formula names %r, which is not one of its inputs" % (bid, name))
    elif spec["inputs"] is not None:
        for port, required in spec["inputs"].items():
            if required and port not in b.raw_in:
                raise CompileError("block %r: missing required input %r" % (bid, port))

    # outputs and fallbacks
    out = raw.get("out", {})
    if out is None:
        out = {}
    if not isinstance(out, dict):
        raise CompileError("block %r: 'out' must be a mapping" % bid)
    for port, name in out.items():
        if port not in b.ports:
            raise CompileError("block %r: unknown output port %r" % (bid, port))
        if not isinstance(name, str) or not name:
            raise CompileError("block %r: output %r must be published under a signal name, got %r" % (bid, port, name))
    b.out = dict(out)
    fb = raw.get("fallback", {})
    if fb is None:
        fb = {}
    if not isinstance(fb, dict):
        raise CompileError("block %r: 'fallback' must be a mapping" % bid)
    b.fallback = {}
    for port, v in fb.items():
        if port not in b.ports:
            raise CompileError("block %r: fallback names unknown output port %r" % (bid, port))
        if not _is_num(v) or not math.isfinite(v):
            raise CompileError("block %r: fallback for %r must be a finite number, got %r" % (bid, port, v))
        b.fallback[port] = float(v)
    return b


def _loops(blocks, deps):
    """Strongly connected components that are loops, each a sorted list of ids."""
    index, low, on, stack, out = {}, {}, set(), [], []
    counter = [0]

    def visit(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in sorted(deps[v]):
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1 or v in deps[v]:
                out.append(sorted(comp))

    for v in sorted(blocks):
        if v not in index:
            visit(v)
    return sorted(out)


class Engine:
    def __init__(self, graph):
        if not isinstance(graph, dict):
            raise CompileError("a graph must be a mapping")
        for key in graph:
            if key not in _TOP_KEYS:
                raise CompileError("unknown top-level key %r" % (key,))
        if "period" not in graph:
            raise CompileError("the graph has no period")
        period = _duration(graph["period"], "period")
        if period <= 0:
            raise CompileError("period %r must be longer than zero" % (graph["period"],))
        self._period = period

        # external inputs
        raw_inputs = graph.get("inputs") or {}
        if isinstance(raw_inputs, list):
            as_dict = {}
            for item in raw_inputs:
                if not isinstance(item, dict) or "signal" not in item:
                    raise CompileError("an input needs a 'signal' name: %r" % (item,))
                if item["signal"] in as_dict:
                    raise CompileError("duplicate signal %r: declared as an input twice" % (item["signal"],))
                as_dict[item["signal"]] = item
            raw_inputs = as_dict
        if not isinstance(raw_inputs, dict):
            raise CompileError("'inputs' must be a mapping of signal name to its declaration")
        self.max_age = {}
        self._max_age = {}
        for name, decl in raw_inputs.items():
            if not isinstance(name, str) or not name:
                raise CompileError("input name %r is not a non-empty string" % (name,))
            if decl is None:
                decl = {}
            if not isinstance(decl, dict):
                raise CompileError("input %r: declaration must be a mapping" % name)
            for key in decl:
                if key not in _INPUT_KEYS:
                    raise CompileError("input %r: unknown key %r" % (name, key))
            if decl.get("max_age") is None:
                self._max_age[name] = None
                self.max_age[name] = math.inf
            else:
                age = _duration(decl["max_age"], "input %r: max_age" % name)
                if age < 0:
                    raise CompileError(
                        "input %r: max_age %r out of range: must not be negative" % (name, decl["max_age"])
                    )
                self._max_age[name] = age
                self.max_age[name] = float(age)

        # blocks
        raw_blocks = graph.get("blocks") or []
        if not isinstance(raw_blocks, list):
            raise CompileError("'blocks' must be a list")
        self._blocks = {}
        for raw in raw_blocks:
            b = _compile_block(raw, period, self._blocks)
            self._blocks[b.id] = b

        # every signal has exactly one writer
        writers = {name: "an input from outside" for name in self._max_age}
        table = {name: ("in", name) for name in self._max_age}
        for b in self._blocks.values():
            for port, name in b.out.items():
                if name in writers:
                    raise CompileError(
                        "duplicate signal %r: written by %s and by block %r (port %r)"
                        % (name, writers[name], b.id, port)
                    )
                writers[name] = "block %r (port %r)" % (b.id, port)
                table[name] = ("blk", b.id, port)
        for b in self._blocks.values():
            for port in b.ports:
                name = "%s.%s" % (b.id, port)
                ref = ("blk", b.id, port)
                if name in table and table[name] != ref:
                    raise CompileError(
                        "duplicate signal %r: it is both %s and the unpublished name of "
                        "block %r (port %r)" % (name, writers.get(name, "another block's port"), b.id, port)
                    )
                table[name] = ref
                writers.setdefault(name, "block %r (port %r)" % (b.id, port))

        # resolve reads
        deps = {bid: set() for bid in self._blocks}
        for b in self._blocks.values():
            b.src = {}
            for port, (kind, v) in b.raw_in.items():
                if kind == "const":
                    b.src[port] = ("const", v)
                    continue
                if v not in table:
                    raise CompileError(
                        "block %r: input %r reads signal %r, which is neither an input "
                        "nor a block's output" % (b.id, port, v)
                    )
                b.src[port] = table[v]
                if table[v][0] == "blk" and port not in b.prev:
                    deps[b.id].add(table[v][1])

        # one evaluation order, ties broken by block id
        loops = _loops(self._blocks, deps)
        if loops:
            raise CompileError("dependency loop through blocks: " + "; ".join(", ".join(loop) for loop in loops))
        waiting = {bid: len(d) for bid, d in deps.items()}
        readers = {bid: [] for bid in deps}
        for bid, d in deps.items():
            for dep in d:
                readers[dep].append(bid)
        ready = [bid for bid, n in waiting.items() if n == 0]
        heapq.heapify(ready)
        self._order = []
        while ready:
            bid = heapq.heappop(ready)
            self._order.append(self._blocks[bid])
            for r in readers[bid]:
                waiting[r] -= 1
                if waiting[r] == 0:
                    heapq.heappush(ready, r)
        self.order = [b.id for b in self._order]

        self._published = []
        for b in self._blocks.values():
            for port, name in b.out.items():
                self._published.append((name, ("blk", b.id, port)))

        self._fingerprint = json.dumps(
            {
                "period": str(period),
                "inputs": {n: (None if a is None else str(a)) for n, a in self._max_age.items()},
                "blocks": {
                    b.id: {
                        "type": b.type,
                        "settings": b.norm_settings,
                        "in": {p: list(v) for p, v in b.raw_in.items()},
                        "out": b.out,
                        "fallback": b.fallback,
                    }
                    for b in self._blocks.values()
                },
            },
            sort_keys=True,
        )
        self.reset()

    # -------------------------------------------------------------- running

    def reset(self):
        self._k = 0
        self._written = {}
        for b in self._blocks.values():
            b.state = _initial_state(b)

    def write(self, name, state, value=None, age=0.0):
        if name not in self._max_age:
            raise KeyError("%r is not an input of this graph" % (name,))
        if state not in _STATES:
            raise ValueError("state must be one of %r, got %r" % (_STATES, state))
        if state == GOOD:
            if not _is_num(value):
                raise ValueError("a good value must be a number, got %r" % (value,))
            value = float(value)
        else:
            value = None
        age = float(age)
        if math.isnan(age):
            raise ValueError("age must be a number")
        self._written[name] = (state, value, age, self._k)

    def _input(self, name, k):
        rec = self._written.get(name)
        if rec is None:
            return (NOT_READY, None)
        state, value, age, k_written = rec
        if state != GOOD:
            return (state, None)
        if not math.isfinite(value):
            return (BAD, None)
        limit = self._max_age[name]
        if limit is not None:
            now = age + float((k - k_written) * self._period)
            lim = float(limit)
            if now > lim + 1e-9 * max(1.0, abs(lim)):
                return (BAD, None)
        return (GOOD, value)

    def tick(self):
        k = self._k
        vals = {}
        for name in self._max_age:
            vals[("in", name)] = self._input(name, k)

        def read(src):
            return (GOOD, src[1]) if src[0] == "const" else vals[src]

        for b in self._order:
            ins = {p: read(s) for p, s in b.src.items() if p not in b.prev}
            outs = _step(b, k, ins, self._period)
            for port in b.ports:
                sv = _norm(outs[port])
                if sv[0] != GOOD and port in b.fallback:
                    sv = (GOOD, b.fallback[port])
                vals[("blk", b.id, port)] = sv
        for b in self._order:
            if b.type == "delay":
                b.state["buf"].append(read(b.src["x"]))
                del b.state["buf"][: -b.cfg["ticks"]]
        self._k = k + 1
        return {name: vals[src] for name, src in self._published}

    # -------------------------------------------------------- save / restore

    def save(self):
        return copy.deepcopy(
            {
                "graph": self._fingerprint,
                "k": self._k,
                "written": self._written,
                "blocks": {bid: b.state for bid, b in self._blocks.items()},
            }
        )

    def restore(self, snapshot):
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("graph") != self._fingerprint
            or set(snapshot.get("blocks", {})) != set(self._blocks)
        ):
            raise RestoreError("this state was not saved from the same graph")
        snap = copy.deepcopy(snapshot)
        self._k = snap["k"]
        self._written = snap["written"]
        for bid, b in self._blocks.items():
            b.state = snap["blocks"][bid]

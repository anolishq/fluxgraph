"""An independent reading of "FluxGraph semantics, version 2 (proposal)".

Sections 3 to 9, Appendix A and Appendix B. Standard library only.
Choices the text does not settle are listed in ASSUMPTIONS.md.
"""

import copy
import json
import math
import re
from fractions import Fraction

GOOD = "good"
UNCERTAIN = "uncertain"
NOT_READY = "not_ready"
BAD = "bad"

_RANK = {BAD: 0, NOT_READY: 1, UNCERTAIN: 2, GOOD: 3}

NUMBER = "number"
BOOLEAN = "boolean"


class CompileError(Exception):
    pass


def usable(state):
    return state == GOOD or state == UNCERTAIN


def worst(states):
    return min(states, key=_RANK.__getitem__)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _const_type(v):
    if isinstance(v, bool):
        return BOOLEAN
    if _is_num(v):
        return NUMBER
    return None


# ---------------------------------------------------------------- time

_TIME_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)(ms|s|m|h)")
_UNIT = {"ms": Fraction(1, 1000), "s": Fraction(1), "m": Fraction(60), "h": Fraction(3600)}


def parse_time(text):
    """A length of time as an exact Fraction of seconds, or None."""
    if not isinstance(text, str):
        return None
    m = _TIME_RE.fullmatch(text)
    if not m:
        return None
    return Fraction(m.group(1)) * _UNIT[m.group(2)]


# ------------------------------------------------------------- formula

_FUNCS = {"abs": 1, "min": 2, "max": 2, "exp": 1, "ln": 1, "sqrt": 1, "pow": 2, "when": 3}
_RESERVED = {"and", "or", "not", "true", "false"} | set(_FUNCS)
_NUM_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NAME_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"


class _FormulaError(Exception):
    pass


def _tokenize(text):
    toks = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == " " or c == "\t":
            i += 1
        elif c in "0123456789":
            m = _NUM_RE.match(text, i)
            i = m.end()
            if i < len(text) and (text[i] in _NAME_CHARS or text[i] == "."):
                raise _FormulaError("malformed number at column %d" % (m.start() + 1))
            v = float(m.group(0))
            if not math.isfinite(v):
                raise _FormulaError("number %s is not finite" % m.group(0))
            toks.append(("num", v))
        elif c in _NAME_CHARS:
            m = _NAME_RE.match(text, i)
            i = m.end()
            toks.append(("name", m.group(0)))
        elif text[i : i + 2] in ("<=", ">=", "==", "!="):
            toks.append(("op", text[i : i + 2]))
            i += 2
        elif c in "<>+-*/(),":
            toks.append(("op", c))
            i += 1
        else:
            raise _FormulaError("unexpected character %r at column %d" % (c, i + 1))
    toks.append(("end", None))
    return toks


class _Parser:
    def __init__(self, text):
        self.toks = _tokenize(text)
        self.i = 0

    def peek(self):
        return self.toks[self.i]

    def take(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def at(self, kind, val):
        return self.toks[self.i] == (kind, val)

    def expect_op(self, val):
        if not self.at("op", val):
            raise _FormulaError("expected %r, found %r" % (val, self.peek()[1]))
        self.i += 1

    def parse(self):
        node = self.p_or()
        if self.peek()[0] != "end":
            raise _FormulaError("unexpected %r" % (self.peek()[1],))
        return node

    def p_or(self):
        node = self.p_and()
        while self.at("name", "or"):
            self.take()
            node = ("bin", "or", node, self.p_and())
        return node

    def p_and(self):
        node = self.p_not()
        while self.at("name", "and"):
            self.take()
            node = ("bin", "and", node, self.p_not())
        return node

    def p_not(self):
        if self.at("name", "not"):
            self.take()
            return ("un", "not", self.p_not())
        return self.p_cmp()

    def p_cmp(self):
        node = self.p_add()
        t = self.peek()
        if t[0] == "op" and t[1] in ("<", "<=", ">", ">=", "==", "!="):
            self.take()
            node = ("bin", t[1], node, self.p_add())
            t = self.peek()
            if t[0] == "op" and t[1] in ("<", "<=", ">", ">=", "==", "!="):
                raise _FormulaError("comparisons do not chain")
        return node

    def p_add(self):
        node = self.p_mul()
        while self.at("op", "+") or self.at("op", "-"):
            op = self.take()[1]
            node = ("bin", op, node, self.p_mul())
        return node

    def p_mul(self):
        node = self.p_unary()
        while self.at("op", "*") or self.at("op", "/"):
            op = self.take()[1]
            node = ("bin", op, node, self.p_unary())
        return node

    def p_unary(self):
        if self.at("op", "-"):
            self.take()
            return ("un", "neg", self.p_unary())
        return self.p_primary()

    def p_primary(self):
        kind, val = self.take()
        if kind == "num":
            return ("num", val)
        if kind == "op" and val == "(":
            node = self.p_or()
            self.expect_op(")")
            return node
        if kind == "name":
            if val == "true":
                return ("bool", True)
            if val == "false":
                return ("bool", False)
            if val in _FUNCS:
                self.expect_op("(")
                args = [self.p_or()]
                while self.at("op", ","):
                    self.take()
                    args.append(self.p_or())
                self.expect_op(")")
                if len(args) != _FUNCS[val]:
                    raise _FormulaError("%s takes %d argument(s)" % (val, _FUNCS[val]))
                return ("call", val, args)
            if val in _RESERVED:
                raise _FormulaError("unexpected %r" % val)
            if self.at("op", "("):
                raise _FormulaError("unknown function %r" % val)
            return ("name", val)
        if kind == "end":
            raise _FormulaError("unexpected end of formula")
        raise _FormulaError("unexpected %r" % (val,))


def _names_used(node, acc):
    k = node[0]
    if k == "name":
        acc.add(node[1])
    elif k == "un":
        _names_used(node[2], acc)
    elif k == "bin":
        _names_used(node[2], acc)
        _names_used(node[3], acc)
    elif k == "call":
        for a in node[2]:
            _names_used(a, acc)
    return acc


def _type_of(node, types):
    k = node[0]
    if k == "num":
        return NUMBER
    if k == "bool":
        return BOOLEAN
    if k == "name":
        return types[node[1]]
    if k == "un":
        t = _type_of(node[2], types)
        if node[1] == "neg":
            if t != NUMBER:
                raise _FormulaError("unary minus takes a number")
            return NUMBER
        if t != BOOLEAN:
            raise _FormulaError("'not' takes a boolean")
        return BOOLEAN
    if k == "bin":
        op = node[1]
        ta = _type_of(node[2], types)
        tb = _type_of(node[3], types)
        if op in ("+", "-", "*", "/"):
            if ta != NUMBER or tb != NUMBER:
                raise _FormulaError("%r takes numbers" % op)
            return NUMBER
        if op in ("<", "<=", ">", ">="):
            if ta != NUMBER or tb != NUMBER:
                raise _FormulaError("%r takes numbers" % op)
            return BOOLEAN
        if op in ("==", "!="):
            if ta != tb:
                raise _FormulaError("%r takes two of one type" % op)
            return BOOLEAN
        if ta != BOOLEAN or tb != BOOLEAN:
            raise _FormulaError("%r takes booleans" % op)
        return BOOLEAN
    fn, args = node[1], node[2]
    ts = [_type_of(a, types) for a in args]
    if fn == "when":
        if ts[0] != BOOLEAN:
            raise _FormulaError("the condition of 'when' is a boolean")
        if ts[1] != ts[2]:
            raise _FormulaError("the branches of 'when' are of one type")
        return ts[1]
    if any(t != NUMBER for t in ts):
        raise _FormulaError("%s takes numbers" % fn)
    return NUMBER


def _num_result(r):
    if r is None or not math.isfinite(r):
        return (BAD, None)
    return r


def _eval(node, env):
    """Returns (state, value); value is None when the state is not usable."""
    k = node[0]
    if k == "num" or k == "bool":
        return (GOOD, node[1])
    if k == "name":
        return env[node[1]]
    if k == "un":
        s, v = _eval(node[2], env)
        if not usable(s):
            return (s, None)
        return (s, (not v) if node[1] == "not" else -v)
    if k == "bin":
        op = node[1]
        sa, va = _eval(node[2], env)
        sb, vb = _eval(node[3], env)
        if op in ("and", "or"):
            decides = op == "or"
            deciders = [s for s, v in ((sa, va), (sb, vb)) if usable(s) and v is decides]
            if deciders:
                return (GOOD if GOOD in deciders else UNCERTAIN, decides)
            s = worst([sa, sb])
            if not usable(s):
                return (s, None)
            return (s, (va or vb) if op == "or" else (va and vb))
        s = worst([sa, sb])
        if not usable(s):
            return (s, None)
        if op == "<":
            return (s, va < vb)
        if op == "<=":
            return (s, va <= vb)
        if op == ">":
            return (s, va > vb)
        if op == ">=":
            return (s, va >= vb)
        if op == "==":
            return (s, va == vb)
        if op == "!=":
            return (s, va != vb)
        if op == "+":
            r = va + vb
        elif op == "-":
            r = va - vb
        elif op == "*":
            r = va * vb
        else:
            if vb == 0:
                return (BAD, None)
            r = va / vb
        if not math.isfinite(r):
            return (BAD, None)
        return (s, r)
    fn, args = node[1], node[2]
    if fn == "when":
        sc, vc = _eval(args[0], env)
        if not usable(sc):
            return (sc, None)
        sx, vx = _eval(args[1] if vc else args[2], env)
        s = worst([sc, sx])
        return (s, vx if usable(s) else None)
    vals = [_eval(a, env) for a in args]
    s = worst([x[0] for x in vals])
    if not usable(s):
        return (s, None)
    a = vals[0][1]
    b = vals[1][1] if len(vals) > 1 else None
    try:
        if fn == "abs":
            r = abs(a)
        elif fn == "min":
            r = min(a, b)
        elif fn == "max":
            r = max(a, b)
        elif fn == "exp":
            r = math.exp(a)
        elif fn == "ln":
            r = math.log(a) if a > 0 else None
        elif fn == "sqrt":
            r = math.sqrt(a) if a >= 0 else None
        else:
            r = math.pow(a, b)
    except (ValueError, OverflowError, ZeroDivisionError):
        r = None
    if r is None or not math.isfinite(r):
        return (BAD, None)
    return (s, r)


# ------------------------------------------------------ block catalogue

_REQ = object()

# port -> (type or None for any, required, direct)
_INPUTS = {
    "delay": {"x": (None, True, False)},
    "window": {"x": (NUMBER, True, True)},
    "deadband": {"x": (NUMBER, True, True)},
    "lowpass": {"x": (NUMBER, True, True)},
    "hysteresis": {"x": (NUMBER, True, True)},
    "held_for": {"x": (BOOLEAN, True, True)},
    "since_true": {"x": (BOOLEAN, True, True)},
    "latch": {"set": (BOOLEAN, True, True), "reset": (BOOLEAN, False, True)},
    "integrate": {"x": (NUMBER, True, True), "reset": (BOOLEAN, False, True)},
    "kalman1": {"z": (NUMBER, True, True), "model": (NUMBER, True, True)},
}

# port -> type (None: decided per block)
_OUTPUTS = {
    "formula": {"y": None},
    "all_good": {"y": BOOLEAN},
    "delay": {"y": None},
    "window": {p: NUMBER for p in ("mean", "median", "min", "max", "spread", "slope", "count")},
    "deadband": {"y": NUMBER},
    "lowpass": {"y": NUMBER},
    "hysteresis": {"y": BOOLEAN},
    "held_for": {"y": BOOLEAN},
    "since_true": {"y": BOOLEAN},
    "latch": {"y": BOOLEAN},
    "integrate": {"y": NUMBER, "missed": NUMBER},
    "kalman1": {"x": NUMBER, "sigma": NUMBER},
}

# setting -> (kind, default or _REQ[, choices])
# kinds: str, num, whole, const, counted (a time that is whole periods, kept
# as ticks), anytime (a time of any length, kept as seconds), choice
_SETTINGS = {
    "formula": {"expr": ("str", _REQ)},
    "all_good": {},
    "delay": {"ticks": ("whole", 1), "initial": ("const", None)},
    "window": {"window": ("counted", _REQ), "min_good": ("num", 1.0)},
    "deadband": {"step": ("num", _REQ), "ride_through": ("counted", 0)},
    "lowpass": {"tau": ("anytime", _REQ), "ride_through": ("counted", 0)},
    "hysteresis": {"rise": ("num", _REQ), "fall": ("num", _REQ)},
    "held_for": {
        "time": ("counted", _REQ),
        "on_bad": ("choice", _REQ, ("reset", "hold")),
        "hold_limit": ("counted", None),
    },
    "since_true": {"time": ("counted", _REQ), "on_bad": ("choice", _REQ, ("assume_false", "unknown"))},
    "latch": {},
    "integrate": {"per": ("anytime", 1.0), "max_missed": ("counted", None)},
    "kalman1": {"tau": ("anytime", _REQ), "q": ("num", _REQ), "r": ("num", _REQ), "max_coast": ("counted", _REQ)},
}


class _Block:
    def __init__(self, bid, btype):
        self.id = bid
        self.type = btype
        self.ins = {}  # port -> ("const", value) | ("in", name) | ("blk", id, port)
        self.direct = {}  # port -> bool
        self.set = {}  # parsed settings
        self.out_types = {}
        self.fallback = {}  # port -> value
        self.ast = None
        self.has_signal_inputs = False


# Each block type: init(b) -> state; out(b, st, k, ins) -> {port: (state, value)}
# where ins maps port -> (state, value, new). For blocks whose inputs are all
# direct, out() also updates the state: the update uses only this tick's own
# inputs, so doing it in the first phase gives the same result as the second.


def _init_none(b):
    return {}


def _out_formula(b, st, k, ins):
    env = {p: (s, v) for p, (s, v, _) in ins.items()}
    return {"y": _eval(b.ast, env)}


def _out_all_good(b, st, k, ins):
    return {"y": (GOOD, all(s == GOOD for s, _, _ in ins.values()))}


def _init_delay(b):
    return {"buf": []}


def _init_window(b):
    return {"buf": []}


def _out_window(b, st, k, ins):
    n = b.set["window"]
    s, v, _ = ins["x"]
    buf = st["buf"]
    buf.append((s, v))
    del buf[:-n]
    slots = [(NOT_READY, None)] * (n - len(buf)) + buf
    us = [(i, sv[1]) for i, sv in enumerate(slots) if usable(sv[0])]
    vals = [x for _, x in us]
    out = {"count": (GOOD, float(len(us)))}
    names = ("mean", "median", "min", "max", "spread", "slope")
    if len(us) < math.ceil(b.set["min_good"] * n - 1e-9):
        hole = worst([sv[0] for sv in slots if not usable(sv[0])])
        for p in names:
            out[p] = (hole, None)
        return out
    state = GOOD if all(sv[0] == GOOD for sv in slots) else UNCERTAIN
    m = len(vals)
    srt = sorted(vals)
    out["mean"] = (state, sum(vals) / m)
    if m % 2:
        out["median"] = (state, srt[m // 2])
    else:
        out["median"] = (state, (srt[m // 2 - 1] + srt[m // 2]) / 2)
    out["min"] = (state, srt[0])
    out["max"] = (state, srt[-1])
    out["spread"] = (state, srt[-1] - srt[0])
    if m < 2:
        out["slope"] = (BAD, None)
    else:
        ts = [i * b.period for i, _ in us]
        tm = sum(ts) / m
        vm = sum(vals) / m
        num = sum((t - tm) * (x - vm) for t, x in zip(ts, vals))
        den = sum((t - tm) * (t - tm) for t in ts)
        out["slope"] = (state, num / den)
    return out


def _init_hold(b):
    return {"held": None, "last": None}


def _out_hold(b, st, k, ins):
    s, x, _ = ins["x"]
    if usable(s):
        h = st["held"]
        if h is None:
            h = x
        elif b.type == "deadband":
            if abs(x - h) >= b.set["step"]:
                h = x
        else:
            a = b.a
            h = a * h + (1 - a) * x
        st["held"] = h
        st["last"] = k
        return {"y": (s, h)}
    if st["held"] is not None and k - st["last"] <= b.set["ride_through"]:
        return {"y": (UNCERTAIN, st["held"])}
    return {"y": (s, None)}


def _init_hyst(b):
    return {"q": None}


def _out_hyst(b, st, k, ins):
    s, x, _ = ins["x"]
    if usable(s):
        if x >= b.set["rise"]:
            st["q"] = True
        elif x <= b.set["fall"]:
            st["q"] = False
    if not usable(s):
        return {"y": (s, None)}
    if st["q"] is None:
        return {"y": (NOT_READY, None)}
    return {"y": (s, st["q"])}


def _init_held_for(b):
    return {"start": None, "allgood": True, "gap": 0}


def _out_held_for(b, st, k, ins):
    s, x, _ = ins["x"]
    n = b.set["time"]
    if usable(s):
        st["gap"] = 0
        if not x:
            st["start"] = None
            return {"y": (s, False)}
        if st["start"] is None:
            st["start"] = k
            st["allgood"] = True
        if s != GOOD:
            st["allgood"] = False
        return {"y": (GOOD if st["allgood"] else UNCERTAIN, k - st["start"] > n)}
    if b.set["on_bad"] == "hold" and st["start"] is not None:
        st["gap"] += 1
        if st["gap"] <= b.set["hold_limit"]:
            st["allgood"] = False
            return {"y": (UNCERTAIN, k - st["start"] > n)}
    st["start"] = None
    st["gap"] = 0
    return {"y": (s, None)}


def _init_since_true(b):
    return {"last": 0}


def _out_since_true(b, st, k, ins):
    s, x, _ = ins["x"]
    if usable(s):
        if x:
            st["last"] = k
        return {"y": (s, k - st["last"] > b.set["time"])}
    if b.set["on_bad"] == "assume_false":
        return {"y": (UNCERTAIN, k - st["last"] > b.set["time"])}
    return {"y": (s, None)}


def _init_latch(b):
    return {"q": False}


def _out_latch(b, st, k, ins):
    s, x, _ = ins["set"]
    r = ins.get("reset")
    if r is not None and usable(r[0]) and r[1]:
        st["q"] = False
    elif usable(s) and x:
        st["q"] = True
    if st["q"]:
        return {"y": (GOOD, True)}
    if usable(s):
        return {"y": (s, False)}
    return {"y": (s, None)}


def _init_integrate(b):
    return {"total": 0.0, "missed": 0, "allgood": True}


def _out_integrate(b, st, k, ins):
    s, x, _ = ins["x"]
    r = ins.get("reset")
    if r is not None and usable(r[0]) and r[1]:
        st["total"] = 0.0
        st["missed"] = 0
        st["allgood"] = True
    if usable(s):
        st["total"] += x * b.period / b.set["per"]
        if s != GOOD:
            st["allgood"] = False
    else:
        st["missed"] += 1
    out = {"missed": (GOOD, st["missed"] * b.period)}
    mm = b.set["max_missed"]
    if mm is not None and st["missed"] > mm:
        out["y"] = (BAD, None)
    elif st["missed"] == 0 and st["allgood"]:
        out["y"] = (GOOD, st["total"])
    else:
        out["y"] = (UNCERTAIN, st["total"])
    return out


def _init_kalman1(b):
    return {"started": False, "x": None, "var": None, "last": None, "last_unc": False}


def _out_kalman1(b, st, k, ins):
    zs, z, znew = ins["z"]
    ms, model, _ = ins["model"]
    fresh = usable(zs) and znew
    if not st["started"]:
        if not fresh:
            return {"x": (NOT_READY, None), "sigma": (NOT_READY, None)}
        st["started"] = True
        st["x"] = z
        st["var"] = b.set["r"]
        st["last"] = k
        st["last_unc"] = zs == UNCERTAIN
    else:
        a = b.a
        if usable(ms):
            st["x"] = a * st["x"] + (1 - a) * model
            st["var"] = a * a * st["var"] + b.set["q"] * b.period
        else:
            st["var"] = st["var"] + b.set["q"] * b.period
        if fresh:
            g = st["var"] / (st["var"] + b.set["r"])
            st["x"] = st["x"] + g * (z - st["x"])
            st["var"] = st["var"] * (1 - g)
            st["last"] = k
            st["last_unc"] = zs == UNCERTAIN
    if k - st["last"] > b.set["max_coast"] or st["last_unc"]:
        state = UNCERTAIN
    else:
        state = GOOD
    return {"x": (state, st["x"]), "sigma": (state, math.sqrt(st["var"]))}


_BEHAVIOUR = {
    "formula": (_init_none, _out_formula),
    "all_good": (_init_none, _out_all_good),
    "delay": (_init_delay, None),
    "window": (_init_window, _out_window),
    "deadband": (_init_hold, _out_hold),
    "lowpass": (_init_hold, _out_hold),
    "hysteresis": (_init_hyst, _out_hyst),
    "held_for": (_init_held_for, _out_held_for),
    "since_true": (_init_since_true, _out_since_true),
    "latch": (_init_latch, _out_latch),
    "integrate": (_init_integrate, _out_integrate),
    "kalman1": (_init_kalman1, _out_kalman1),
}


# -------------------------------------------------------------- compile


def _compile(graph):
    if not isinstance(graph, dict):
        raise CompileError("graph: not a mapping")
    for key in graph:
        if key not in ("period", "inputs", "blocks"):
            raise CompileError("graph: unknown key %r" % (key,))
    if "period" not in graph:
        raise CompileError("graph: period is missing")
    period = parse_time(graph["period"])
    if period is None or period <= 0:
        raise CompileError("graph: period %r is not a length of time more than zero" % (graph["period"],))

    # inputs
    inputs = {}
    raw_inputs = graph.get("inputs")
    if raw_inputs is None:
        raw_inputs = {}
    if not isinstance(raw_inputs, dict):
        raise CompileError("graph: inputs is not a mapping")
    for name, spec in raw_inputs.items():
        if not isinstance(name, str) or name == "":
            raise CompileError("input %r: its name is not a non-empty string" % (name,))
        if spec is None:
            spec = {}
        if not isinstance(spec, dict):
            raise CompileError("input %r: not a mapping" % name)
        for key in spec:
            if key not in ("type", "unit", "max_age", "initial"):
                raise CompileError("input %r: unknown key %r" % (name, key))
        typ = spec.get("type", NUMBER)
        if typ not in (NUMBER, BOOLEAN):
            raise CompileError("input %r: type %r is not number or boolean" % (name, typ))
        max_age = None
        max_age_exact = None
        if "max_age" in spec:
            max_age_exact = parse_time(spec["max_age"])
            if max_age_exact is None:
                raise CompileError("input %r: max_age %r is not a length of time" % (name, spec["max_age"]))
            max_age = float(max_age_exact)
        initial = None
        if "initial" in spec:
            initial = spec["initial"]
            if _const_type(initial) != typ:
                raise CompileError("input %r: initial %r is not a %s" % (name, initial, typ))
            if typ == NUMBER:
                initial = float(initial)
                if not math.isfinite(initial):
                    raise CompileError("input %r: initial is not finite" % name)
        inputs[name] = {"type": typ, "max_age": max_age, "max_age_exact": max_age_exact, "initial": initial}

    # blocks: shape
    raw_blocks = graph.get("blocks")
    if raw_blocks is None:
        raw_blocks = []
    if not isinstance(raw_blocks, list):
        raise CompileError("graph: blocks is not a list")
    blocks = {}
    raw_by_id = {}
    for pos, rb in enumerate(raw_blocks):
        if not isinstance(rb, dict):
            raise CompileError("block at position %d: not a mapping" % pos)
        if "id" not in rb:
            raise CompileError("block at position %d: has no id" % pos)
        bid = rb["id"]
        if not isinstance(bid, str) or bid == "":
            raise CompileError("block at position %d: id %r is not a non-empty string" % (pos, bid))
        if bid in blocks:
            raise CompileError("block %r: another block has this id" % bid)
        for key in rb:
            if key not in ("id", "type", "in", "settings", "out", "fallback"):
                raise CompileError("block %r: unknown key %r" % (bid, key))
        btype = rb.get("type")
        if not isinstance(btype, str) or btype not in _BEHAVIOUR:
            raise CompileError("block %r: unknown block type %r" % (bid, btype))
        for key in ("in", "settings", "out", "fallback"):
            if rb.get(key) is not None and not isinstance(rb[key], dict):
                raise CompileError("block %r: %r is not a mapping" % (bid, key))
        blocks[bid] = _Block(bid, btype)
        raw_by_id[bid] = rb

    # signal names and their writers
    names = {}

    def add_name(name, src, who):
        if name in names and names[name] != src:
            raise CompileError("%s: signal %r has two writers" % (who, name))
        names[name] = src

    for name in inputs:
        add_name(name, ("in", name), "input %r" % name)
    for bid, b in blocks.items():
        for port in _OUTPUTS[b.type]:
            add_name("%s.%s" % (bid, port), ("blk", bid, port), "block %r" % bid)
    published = {}
    for bid, b in blocks.items():
        out = raw_by_id[bid].get("out") or {}
        for port, name in out.items():
            if port not in _OUTPUTS[b.type]:
                raise CompileError("block %r: unknown port %r in out" % (bid, port))
            if not isinstance(name, str) or name == "":
                raise CompileError("block %r: out port %r is not given a signal name" % (bid, port))
            if name in published:
                raise CompileError("block %r: signal %r has two writers" % (bid, name))
            add_name(name, ("blk", bid, port), "block %r" % bid)
            published[name] = (bid, port)

    # connections
    for bid, b in blocks.items():
        raw_in = raw_by_id[bid].get("in") or {}
        if b.type in ("formula", "all_good"):
            if not raw_in:
                raise CompileError("block %r: a %s takes one or more inputs" % (bid, b.type))
            ports = {p: (None, True, True) for p in raw_in}
        else:
            ports = _INPUTS[b.type]
        for port, ref in raw_in.items():
            if port not in ports:
                raise CompileError("block %r: unknown port %r in in" % (bid, port))
            if isinstance(ref, str):
                if ref not in names:
                    raise CompileError(
                        "block %r: port %r reads signal %r, which is neither an input "
                        "nor a block's output" % (bid, port, ref)
                    )
                b.ins[port] = names[ref]
                b.has_signal_inputs = True
            elif _const_type(ref) is not None:
                if _const_type(ref) == NUMBER:
                    ref = float(ref)
                    if not math.isfinite(ref):
                        raise CompileError("block %r: the constant on port %r is not finite" % (bid, port))
                b.ins[port] = ("const", ref)
            else:
                raise CompileError(
                    "block %r: port %r is given %r, which is neither a signal nor a constant" % (bid, port, ref)
                )
            b.direct[port] = ports[port][2]
        for port, (_, required, _) in ports.items():
            if required and port not in b.ins:
                raise CompileError("block %r: required input %r is left unconnected" % (bid, port))

    # settings
    for bid, b in blocks.items():
        _compile_settings(b, raw_by_id[bid].get("settings") or {}, period)

    # order: direct inputs only, ties by block id
    deps = {bid: set() for bid in blocks}  # direct
    all_deps = {bid: set() for bid in blocks}  # direct and deferred
    for bid, b in blocks.items():
        for port, src in b.ins.items():
            if src[0] == "blk":
                all_deps[bid].add(src[1])
                if b.direct[port]:
                    deps[bid].add(src[1])
    order = []
    done = set()
    remaining = set(blocks)
    while remaining:
        ready = sorted(bid for bid in remaining if deps[bid] <= done)
        if not ready:
            raise CompileError("a loop of direct inputs through blocks: %s" % ", ".join(_find_cycle(deps, remaining)))
        order.append(ready[0])
        done.add(ready[0])
        remaining.discard(ready[0])

    # a delay on a loop has an initial value
    for bid, b in blocks.items():
        if b.type == "delay" and b.set["initial"] is None and _reaches(all_deps, bid, bid):
            raise CompileError("block %r: a delay on a loop has no setting 'initial'" % bid)

    # types
    memo = {}

    def src_type(src):
        if src[0] == "const":
            return _const_type(src[1])
        if src[0] == "in":
            return inputs[src[1]]["type"]
        return out_type(src[1], src[2])

    def out_type(bid, port):
        key = (bid, port)
        if key in memo:
            return memo[key]
        b = blocks[bid]
        t = _OUTPUTS[b.type][port]
        if b.type == "delay":
            if b.set["initial"] is not None:
                t = _const_type(b.set["initial"])
            else:
                t = src_type(b.ins["x"])
        elif b.type == "formula":
            types = {p: src_type(s) for p, s in b.ins.items()}
            try:
                t = _type_of(b.ast, types)
            except _FormulaError as e:
                raise CompileError("block %r: setting 'expr': %s" % (bid, e))
        memo[key] = t
        return t

    for bid in order:
        b = blocks[bid]
        for port in _OUTPUTS[b.type]:
            b.out_types[port] = out_type(bid, port)
    for bid, b in blocks.items():
        for port, src in b.ins.items():
            if b.type in ("formula", "all_good"):
                continue
            want = _INPUTS[b.type][port][0]
            if b.type == "delay":
                want = b.out_types["y"]
            got = src_type(src)
            if got != want:
                what = "a constant" if src[0] == "const" else "a signal"
                if b.type == "delay" and b.set["initial"] is not None:
                    raise CompileError(
                        "block %r: setting 'initial' is a %s and port 'x' is given %s "
                        "that is a %s" % (bid, want, what, got)
                    )
                raise CompileError(
                    "block %r: port %r is a %s and is given %s that is a %s" % (bid, port, want, what, got)
                )

    # fallbacks
    for bid, b in blocks.items():
        fb = raw_by_id[bid].get("fallback") or {}
        for port, val in fb.items():
            if port not in _OUTPUTS[b.type]:
                raise CompileError("block %r: unknown port %r in fallback" % (bid, port))
            if _const_type(val) != b.out_types[port]:
                raise CompileError(
                    "block %r: fallback for port %r is not a constant of type %s" % (bid, port, b.out_types[port])
                )
            if b.out_types[port] == NUMBER:
                val = float(val)
                if not math.isfinite(val):
                    raise CompileError("block %r: fallback for port %r is not finite" % (bid, port))
            b.fallback[port] = val

    return period, inputs, blocks, order, published


def _find_cycle(deps, remaining):
    start = sorted(remaining)[0]
    path = [start]
    seen = {start: 0}
    while True:
        nxt = sorted(d for d in deps[path[-1]] if d in remaining)[0]
        if nxt in seen:
            return path[seen[nxt] :]
        seen[nxt] = len(path)
        path.append(nxt)


def _reaches(deps, start, target):
    """True if target is among the blocks start depends on, at any remove."""
    stack = list(deps[start])
    seen = set()
    while stack:
        x = stack.pop()
        if x == target:
            return True
        if x not in seen:
            seen.add(x)
            stack.extend(deps[x])
    return False


def _compile_settings(b, raw, period):
    bid = b.id
    spec = _SETTINGS[b.type]
    for name in raw:
        if name not in spec:
            raise CompileError("block %r: unknown setting %r" % (bid, name))
    for name, sp in spec.items():
        kind, default = sp[0], sp[1]
        if name not in raw:
            if default is _REQ:
                raise CompileError("block %r: required setting %r is missing" % (bid, name))
            b.set[name] = default
            continue
        val = raw[name]

        def wrong(what):
            raise CompileError("block %r: setting %r is %r, which is not %s" % (bid, name, val, what))

        if kind == "str":
            if not isinstance(val, str):
                wrong("a string")
        elif kind == "num":
            if not _is_num(val) or not math.isfinite(val):
                wrong("a finite number")
            val = float(val)
        elif kind == "whole":
            if not _is_num(val) or not math.isfinite(val) or val != int(val):
                wrong("a whole number")
            val = int(val)
        elif kind == "const":
            if _const_type(val) is None:
                wrong("a number or a boolean")
            if _is_num(val):
                val = float(val)
                if not math.isfinite(val):
                    wrong("finite")
        elif kind == "choice":
            if not isinstance(val, str) or val not in sp[2]:
                wrong("one of " + ", ".join(sp[2]))
        else:
            t = parse_time(val)
            if t is None:
                wrong("a length of time")
            if kind == "counted":
                ticks = t / period
                if ticks.denominator != 1:
                    wrong("a whole number of periods")
                val = int(ticks)
            else:
                val = float(t)
        b.set[name] = val

    def out_of_range(name, what):
        raise CompileError("block %r: setting %r is out of range: it must be %s" % (bid, name, what))

    s = b.set
    b.period = float(period)
    if b.type == "formula":
        try:
            b.ast = _Parser(s["expr"]).parse()
        except _FormulaError as e:
            raise CompileError("block %r: setting 'expr': %s" % (bid, e))
        used = _names_used(b.ast, set())
        for name in sorted(used):
            if name not in b.ins:
                raise CompileError(
                    "block %r: the formula uses %r, which is not one of the block's inputs" % (bid, name)
                )
        for port in b.ins:
            if port not in used:
                raise CompileError("block %r: input %r is not used by the formula" % (bid, port))
    elif b.type == "delay":
        if s["ticks"] < 1:
            out_of_range("ticks", "at least 1")
    elif b.type == "window":
        if s["window"] < 1:
            out_of_range("window", "at least one period")
        if not (0 < s["min_good"] <= 1):
            out_of_range("min_good", "more than 0 and at most 1")
    elif b.type == "deadband":
        if s["step"] < 0:
            out_of_range("step", "not negative")
    elif b.type == "lowpass":
        if s["tau"] <= 0:
            out_of_range("tau", "more than zero")
        b.a = math.exp(-b.period / s["tau"])
    elif b.type == "hysteresis":
        if not s["rise"] > s["fall"]:
            out_of_range("rise", "more than fall")
    elif b.type == "held_for":
        if s["on_bad"] == "hold" and s["hold_limit"] is None:
            raise CompileError("block %r: required setting 'hold_limit' is missing (on_bad is hold)" % bid)
        if s["on_bad"] != "hold" and s["hold_limit"] is not None:
            raise CompileError("block %r: setting 'hold_limit' is given without on_bad: hold" % bid)
    elif b.type == "integrate":
        if s["per"] <= 0:
            out_of_range("per", "more than zero")
    elif b.type == "kalman1":
        if s["tau"] <= 0:
            out_of_range("tau", "more than zero")
        if s["r"] <= 0:
            out_of_range("r", "more than zero")
        if s["q"] < 0:
            out_of_range("q", "not negative")
        b.a = math.exp(-b.period / s["tau"])


# --------------------------------------------------------------- engine


class Engine:
    def __init__(self, graph):
        period, inputs, blocks, order, published = _compile(graph)
        self._signature = json.dumps(graph, sort_keys=True, default=repr)
        self._period_exact = period
        self._period = float(period)
        self.inputs = inputs
        self._blocks = blocks
        self._order = order
        self._published = published
        self.reset()

    # -- state

    def reset(self):
        self._next = 0  # index of the next tick to run
        self._t0 = None  # time of tick 0, set by the next call
        self._last_now = None
        self._writes = {}  # name -> (state, value, sampled)
        self._fresh = set()  # inputs written since the last tick that was not missed
        self._states = {bid: _BEHAVIOUR[b.type][0](b) for bid, b in self._blocks.items()}

    def save(self):
        return {
            "fluxgraph2": self._signature,
            "next": self._next,
            "writes": dict(self._writes),
            "fresh": set(self._fresh),
            "states": copy.deepcopy(self._states),
        }

    def restore(self, saved):
        if not isinstance(saved, dict) or saved.get("fluxgraph2") != self._signature:
            raise ValueError("this state was not saved from the same graph")
        self._next = saved["next"]
        self._t0 = None
        self._last_now = None
        self._writes = dict(saved["writes"])
        self._fresh = set(saved["fresh"])
        self._states = copy.deepcopy(saved["states"])

    # -- host side

    def write(self, name, state, value, sampled):
        if name not in self.inputs:
            raise KeyError("no external input named %r" % (name,))
        if state not in _RANK:
            raise ValueError("unknown state %r" % (state,))
        if usable(state):
            typ = self.inputs[name]["type"]
            if typ == BOOLEAN:
                if not isinstance(value, bool):
                    raise TypeError("input %r is a boolean" % name)
            else:
                if not _is_num(value):
                    raise TypeError("input %r is a number" % name)
                value = float(value)
            if not _is_num(sampled) or math.isnan(sampled):
                raise ValueError("a usable write needs a sample time")
            sampled = float(sampled)
        else:
            value = None
            sampled = None
        self._writes[name] = (state, value, sampled)
        self._fresh.add(name)

    def tick(self, now):
        if not _is_num(now) or not math.isfinite(now):
            raise ValueError("now is not a finite number")
        if self._last_now is not None and now < self._last_now:
            raise ValueError("now is earlier than the last call's")
        self._last_now = now
        if self._t0 is None:
            self._t0 = now - self._next * self._period
        due = 0
        while self._t0 + (self._next + due) * self._period <= now + self._period / 2:
            due += 1
        outputs = None
        for i in range(due):
            outputs = self._run(missed=(i < due - 1))
        return (due, outputs)

    # -- one tick

    def _input_at(self, name, k, time, missed):
        spec = self.inputs[name]
        if missed:
            return (BAD, None, False)
        new = name in self._fresh
        if name not in self._writes:
            if spec["initial"] is not None:
                return (UNCERTAIN, spec["initial"], new)
            if spec["max_age_exact"] is not None and k * self._period_exact > spec["max_age_exact"]:
                return (BAD, None, new)
            return (NOT_READY, None, new)
        state, value, sampled = self._writes[name]
        if not usable(state):
            return (state, None, new)
        if spec["type"] == NUMBER and not math.isfinite(value):
            return (BAD, None, new)
        age = max(time - sampled, 0.0)
        if spec["max_age"] is not None and age > spec["max_age"]:
            return (BAD, None, new)
        if sampled > time + self._period:
            return (BAD, None, new)
        return (state, value, new)

    def _run(self, missed):
        k = self._next
        time = self._t0 + k * self._period
        sig = {}
        for name in self.inputs:
            sig[("in", name)] = self._input_at(name, k, time, missed)

        def read(src):
            if src[0] == "const":
                return (GOOD, src[1], False)
            return sig[src]

        # first phase: every block gives its outputs
        for bid in self._order:
            b = self._blocks[bid]
            st = self._states[bid]
            if b.type == "delay":
                buf = st["buf"]
                if len(buf) == b.set["ticks"]:
                    s, v, new = buf[0]
                elif b.set["initial"] is not None:
                    s, v, new = GOOD, b.set["initial"], False
                else:
                    s, v, new = NOT_READY, None, False
                outs = {"y": (s, v)}
            else:
                ins = {port: read(src) for port, src in b.ins.items()}
                outs = _BEHAVIOUR[b.type][1](b, st, k, ins)
                new = (not b.has_signal_inputs) or any(x[2] for x in ins.values())
            for port, (s, v) in outs.items():
                if usable(s) and b.out_types[port] == NUMBER and not math.isfinite(v):
                    s = BAD
                if not usable(s):
                    v = None
                    if port in b.fallback:
                        s, v = UNCERTAIN, b.fallback[port]
                sig[("blk", bid, port)] = (s, v, new)

        # second phase: every block updates its state (only a delay has
        # anything left to do)
        for bid in self._order:
            b = self._blocks[bid]
            if b.type == "delay":
                buf = self._states[bid]["buf"]
                buf.append(read(b.ins["x"]))
                del buf[: -b.set["ticks"]]

        if not missed:
            self._fresh.clear()
        self._next = k + 1

        result = {}
        for name, (bid, port) in self._published.items():
            s, v, _ = sig[("blk", bid, port)]
            if usable(s) and self._blocks[bid].out_types[port] == NUMBER:
                v = float(v)
            result[name] = (s, v)
        return result

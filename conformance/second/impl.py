"""An independent reading of "FluxGraph semantics, version 2 (proposal)".

Sections 3 to 9 and every block type of Appendix A. Units are ignored.
Standard library only. Choices the text does not settle are listed in
ASSUMPTIONS.md.
"""

import copy
import json
import math
import re
from fractions import Fraction


class CompileError(Exception):
    pass


GOOD = "good"
UNC = "uncertain"
NR = "not_ready"
BAD = "bad"
_RANK = {BAD: 0, NR: 1, UNC: 2, GOOD: 3}
NUMBER = "number"
BOOLEAN = "boolean"

TICK = object()  # "the sample time is the time of the tick"
REQ = object()  # "this setting is required"


def usable(state):
    return state == GOOD or state == UNC


def worst(states):
    return min(states, key=lambda s: _RANK[s])


def _later(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _finite(v):
    """The value as a finite float, or None."""
    if not _is_num(v):
        return None
    try:
        f = float(v)
    except OverflowError:
        return None
    return f if math.isfinite(f) else None


def ceil_tol(v):
    """Round up to a whole number; within 1e-9 of a whole number is it."""
    r = round(v)
    if abs(v - r) <= 1e-9:
        return int(r)
    return int(math.ceil(v))


_DUR_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)(ms|s|m|h)")
_UNITS = {"ms": Fraction(1, 1000), "s": Fraction(1), "m": Fraction(60), "h": Fraction(3600)}


def parse_duration(what, v):
    if not isinstance(v, str):
        raise CompileError("%s: a length of time is a number and a unit, got %r" % (what, v))
    m = _DUR_RE.fullmatch(v)
    if not m:
        raise CompileError("%s: %r is not a length of time" % (what, v))
    return Fraction(m.group(1)) * _UNITS[m.group(2)]


# ---------------------------------------------------------------- settings


def s_num(b, st, key, default=REQ):
    if key not in st:
        if default is REQ:
            raise b.err("missing required setting %r" % key)
        return default
    f = _finite(st[key])
    if f is None:
        raise b.err("setting %r must be a finite number" % key)
    return f


def s_whole(b, st, key, default=REQ):
    if key not in st:
        if default is REQ:
            raise b.err("missing required setting %r" % key)
        return default
    v = st[key]
    if not isinstance(v, int) or isinstance(v, bool):
        raise b.err("setting %r must be a whole number" % key)
    return v


def s_bool(b, st, key, default=REQ):
    if key not in st:
        if default is REQ:
            raise b.err("missing required setting %r" % key)
        return default
    if not isinstance(st[key], bool):
        raise b.err("setting %r must be true or false" % key)
    return st[key]


def s_counted(b, st, key, default=REQ):
    """A counted length of time, as a whole number of ticks."""
    if key not in st:
        if default is REQ:
            raise b.err("missing required setting %r" % key)
        return default
    d = parse_duration("block %r setting %r" % (b.id, key), st[key])
    q = d / b.ctx.period_fr
    if q.denominator != 1:
        raise b.err("setting %r (%s) is not a whole number of periods" % (key, st[key]))
    return int(q)


def s_length(b, st, key, default=REQ):
    """A length of time that is not counted, in seconds."""
    if key not in st:
        if default is REQ:
            raise b.err("missing required setting %r" % key)
        return default
    return float(parse_duration("block %r setting %r" % (b.id, key), st[key]))


def s_choice(b, st, key, choices):
    if key not in st:
        raise b.err("missing required setting %r" % key)
    if not isinstance(st[key], str) or st[key] not in choices:
        raise b.err("setting %r must be one of %s" % (key, ", ".join(choices)))
    return st[key]


# ----------------------------------------------------------------- formula

_DIGITS = "0123456789"
_LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_"
_FUNCS = {"abs": 1, "min": 2, "max": 2, "exp": 1, "ln": 1, "sqrt": 1, "pow": 2, "when": 3}
_KEYWORDS = ("and", "or", "not", "true", "false")


class _FormulaError(Exception):
    pass


def _tokenize(src):
    toks = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c == " " or c == "\t":
            i += 1
        elif c in _DIGITS:
            j = i
            while j < n and src[j] in _DIGITS:
                j += 1
            if j < n and src[j] == ".":
                if j + 1 < n and src[j + 1] in _DIGITS:
                    j += 1
                    while j < n and src[j] in _DIGITS:
                        j += 1
                else:
                    raise _FormulaError("a point must be followed by digits")
            if j < n and src[j] in "eE":
                k = j + 1
                if k < n and src[k] in "+-":
                    k += 1
                if k < n and src[k] in _DIGITS:
                    while k < n and src[k] in _DIGITS:
                        k += 1
                    j = k
            if j < n and (src[j] in _LETTERS or src[j] == "."):
                raise _FormulaError("bad number at %r" % src[i : j + 1])
            v = float(src[i:j])
            if math.isinf(v):
                raise _FormulaError("number %s is too large" % src[i:j])
            toks.append(("num", v))
            i = j
        elif c in _LETTERS:
            j = i
            while j < n and (src[j] in _LETTERS or src[j] in _DIGITS):
                j += 1
            w = src[i:j]
            if w in _KEYWORDS:
                toks.append(("kw", w))
            elif w in _FUNCS:
                toks.append(("func", w))
            else:
                toks.append(("name", w))
            i = j
        elif src[i : i + 2] in ("<=", ">=", "==", "!="):
            toks.append(("op", src[i : i + 2]))
            i += 2
        elif c in "<>+-*/(),":
            toks.append(("op", c))
            i += 1
        else:
            raise _FormulaError("unexpected character %r" % c)
    toks.append(("end", None))
    return toks


class _Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    def peek(self):
        return self.toks[self.i]

    def take(self):
        t = self.toks[self.i]
        self.i += 1
        return t

    def is_(self, kind, val):
        return self.toks[self.i] == (kind, val)

    def expect(self, kind, val):
        if not self.is_(kind, val):
            raise _FormulaError("expected %r, found %r" % (val, self.peek()[1]))
        self.i += 1

    def parse(self):
        node = self.p_or()
        if self.peek()[0] != "end":
            raise _FormulaError("unexpected %r" % (self.peek()[1],))
        return node

    def p_or(self):
        node = self.p_and()
        while self.is_("kw", "or"):
            self.take()
            node = ("or", node, self.p_and())
        return node

    def p_and(self):
        node = self.p_not()
        while self.is_("kw", "and"):
            self.take()
            node = ("and", node, self.p_not())
        return node

    def p_not(self):
        if self.is_("kw", "not"):
            self.take()
            return ("not", self.p_not())
        return self.p_compare()

    def p_compare(self):
        node = self.p_sum()
        t = self.peek()
        if t[0] == "op" and t[1] in ("<", "<=", ">", ">=", "==", "!="):
            self.take()
            node = ("cmp", t[1], node, self.p_sum())
            t = self.peek()
            if t[0] == "op" and t[1] in ("<", "<=", ">", ">=", "==", "!="):
                raise _FormulaError("comparisons do not chain")
        return node

    def p_sum(self):
        node = self.p_product()
        while self.is_("op", "+") or self.is_("op", "-"):
            op = self.take()[1]
            node = ("arith", op, node, self.p_product())
        return node

    def p_product(self):
        node = self.p_unary()
        while self.is_("op", "*") or self.is_("op", "/"):
            op = self.take()[1]
            node = ("arith", op, node, self.p_unary())
        return node

    def p_unary(self):
        if self.is_("op", "-"):
            self.take()
            return ("neg", self.p_unary())
        return self.p_primary()

    def p_primary(self):
        kind, val = self.take()
        if kind == "num":
            return ("num", val)
        if kind == "kw" and val in ("true", "false"):
            return ("bool", val == "true")
        if kind == "name":
            return ("name", val)
        if kind == "op" and val == "(":
            node = self.p_or()
            self.expect("op", ")")
            return node
        if kind == "func":
            self.expect("op", "(")
            args = [self.p_or()]
            while self.is_("op", ","):
                self.take()
                args.append(self.p_or())
            self.expect("op", ")")
            if len(args) != _FUNCS[val]:
                raise _FormulaError("%s takes %d argument(s)" % (val, _FUNCS[val]))
            return ("call", val, args)
        raise _FormulaError("unexpected %r" % (val,))


def _names(node, acc):
    if node[0] == "name":
        acc.add(node[1])
    elif node[0] in ("neg", "not"):
        _names(node[1], acc)
    elif node[0] in ("or", "and"):
        _names(node[1], acc)
        _names(node[2], acc)
    elif node[0] in ("arith", "cmp"):
        _names(node[2], acc)
        _names(node[3], acc)
    elif node[0] == "call":
        for a in node[2]:
            _names(a, acc)
    return acc


def _ftype(node, types):
    k = node[0]
    if k == "num":
        return NUMBER
    if k == "bool":
        return BOOLEAN
    if k == "name":
        return types[node[1]]
    if k == "neg":
        if _ftype(node[1], types) != NUMBER:
            raise _FormulaError("unary minus takes a number")
        return NUMBER
    if k == "not":
        if _ftype(node[1], types) != BOOLEAN:
            raise _FormulaError("'not' takes a boolean")
        return BOOLEAN
    if k in ("or", "and"):
        if _ftype(node[1], types) != BOOLEAN or _ftype(node[2], types) != BOOLEAN:
            raise _FormulaError("%r takes booleans" % k)
        return BOOLEAN
    if k == "arith":
        if _ftype(node[2], types) != NUMBER or _ftype(node[3], types) != NUMBER:
            raise _FormulaError("%r takes numbers" % node[1])
        return NUMBER
    if k == "cmp":
        a = _ftype(node[2], types)
        b = _ftype(node[3], types)
        if node[1] in ("==", "!="):
            if a != b:
                raise _FormulaError("%r takes two of one type" % node[1])
        elif a != NUMBER or b != NUMBER:
            raise _FormulaError("%r takes numbers" % node[1])
        return BOOLEAN
    # call
    f, args = node[1], node[2]
    ts = [_ftype(a, types) for a in args]
    if f == "when":
        if ts[0] != BOOLEAN:
            raise _FormulaError("the condition of when() is a boolean")
        if ts[1] != ts[2]:
            raise _FormulaError("the branches of when() are of one type")
        return ts[1]
    for t in ts:
        if t != NUMBER:
            raise _FormulaError("%s() takes numbers" % f)
    return NUMBER


def _feval(node, env):
    """Returns (state, value); value is None when the state is not usable."""
    k = node[0]
    if k == "num" or k == "bool":
        return (GOOD, node[1])
    if k == "name":
        return env[node[1]]
    if k == "neg":
        st, v = _feval(node[1], env)
        return (st, -v) if usable(st) else (st, None)
    if k == "not":
        st, v = _feval(node[1], env)
        return (st, not v) if usable(st) else (st, None)
    if k == "or" or k == "and":
        a = _feval(node[1], env)
        b = _feval(node[2], env)
        decides = k == "or"
        deciders = [o for o in (a, b) if usable(o[0]) and o[1] is decides]
        if deciders:
            st = GOOD if any(o[0] == GOOD for o in deciders) else UNC
            return (st, decides)
        st = worst([a[0], b[0]])
        return (st, not decides) if usable(st) else (st, None)
    if k == "arith":
        a = _feval(node[2], env)
        b = _feval(node[3], env)
        st = worst([a[0], b[0]])
        if not usable(st):
            return (st, None)
        op = node[1]
        x, y = a[1], b[1]
        if op == "+":
            r = x + y
        elif op == "-":
            r = x - y
        elif op == "*":
            r = x * y
        else:
            if y == 0:
                return (BAD, None)
            r = x / y
        if not math.isfinite(r):
            return (BAD, None)
        return (st, r)
    if k == "cmp":
        a = _feval(node[2], env)
        b = _feval(node[3], env)
        st = worst([a[0], b[0]])
        if not usable(st):
            return (st, None)
        op = node[1]
        x, y = a[1], b[1]
        if op == "<":
            r = x < y
        elif op == "<=":
            r = x <= y
        elif op == ">":
            r = x > y
        elif op == ">=":
            r = x >= y
        elif op == "==":
            r = x == y
        else:
            r = x != y
        return (st, r)
    # call
    f, args = node[1], node[2]
    if f == "when":
        c = _feval(args[0], env)
        if not usable(c[0]):
            return (c[0], None)
        br = _feval(args[1] if c[1] else args[2], env)
        st = worst([br[0], c[0]])
        return (st, br[1]) if usable(st) else (st, None)
    vals = [_feval(a, env) for a in args]
    st = worst([v[0] for v in vals])
    if not usable(st):
        return (st, None)
    xs = [v[1] for v in vals]
    try:
        if f == "abs":
            r = abs(xs[0])
        elif f == "min":
            r = min(xs[0], xs[1])
        elif f == "max":
            r = max(xs[0], xs[1])
        elif f == "exp":
            r = math.exp(xs[0])
        elif f == "ln":
            r = math.log(xs[0])
        elif f == "sqrt":
            r = math.sqrt(xs[0])
        else:
            r = math.pow(xs[0], xs[1])
    except (ValueError, OverflowError, ZeroDivisionError):
        return (BAD, None)
    if not math.isfinite(r):
        return (BAD, None)
    return (st, float(r))


# ------------------------------------------------------------------ blocks
#
# A signal is a tuple (state, value, sample_time, cause).
# A block's output() returns {port: (state, value, sample_time, cause)},
# where sample_time may be TICK and cause may be None ("the default of rule
# 3.8"). The engine applies rule 3.6, the fallback and the defaults.


def out(state, value=None, cause=None):
    return (state, value, TICK, cause)


class Block:
    SETTINGS = ()
    has_update = False

    def __init__(self, bid, settings, in_map, ctx):
        self.id = bid
        self.ctx = ctx
        self.st = settings
        for key in settings:
            if key not in self.SETTINGS:
                raise self.err("unknown setting %r" % (key,))
        self.in_ports = {}  # port -> (type or None, required, direct)
        self.out_ports = {}  # port -> type or None
        self.configure(in_map)
        self.reset()

    def err(self, msg):
        return CompileError("block %r: %s" % (self.id, msg))

    def configure(self, in_map):
        pass

    def reset(self):
        self.s = {}

    def gap(self, g):
        pass

    def output(self, k, t, ins):
        raise NotImplementedError

    def update(self, k, t, ins):
        pass


class Formula(Block):
    SETTINGS = ("expr", "sample_of")

    def configure(self, in_map):
        if not in_map:
            raise self.err("a formula takes one or more inputs")
        for port in in_map:
            self.in_ports[port] = (None, True, True)
        self.out_ports["y"] = None
        if "expr" not in self.st:
            raise self.err("missing required setting 'expr'")
        expr = self.st["expr"]
        if not isinstance(expr, str):
            raise self.err("setting 'expr' must be text")
        try:
            toks = _tokenize(expr)
            if len(toks) == 1:
                raise _FormulaError("the formula is empty")
            self.ast = _Parser(toks).parse()
        except _FormulaError as e:
            raise self.err("setting 'expr': %s" % e)
        used = _names(self.ast, set())
        for name in sorted(used):
            if name not in in_map:
                raise self.err("setting 'expr' uses %r, which is not an input of the block" % name)
        for port in in_map:
            if port not in used:
                raise self.err("input %r is not used by the formula" % (port,))
        signal_ports = [p for p, v in in_map.items() if isinstance(v, str)]
        self.sample_port = None
        if "sample_of" in self.st:
            so = self.st["sample_of"]
            if not isinstance(so, str) or so not in signal_ports:
                raise self.err("setting 'sample_of' must name an input of the block that is a signal, got %r" % (so,))
            self.sample_port = so
        elif len(signal_ports) == 1:
            self.sample_port = signal_ports[0]

    def typecheck(self, types):
        try:
            return _ftype(self.ast, types)
        except _FormulaError as e:
            raise self.err("setting 'expr': %s" % e)

    def output(self, k, t, ins):
        env = {p: (s[0], s[1]) for p, s in ins.items()}
        st, v = _feval(self.ast, env)
        stime = TICK
        if self.sample_port is not None:
            stime = ins[self.sample_port][2]
        return {"y": (st, v, stime, None)}


class AllGood(Block):
    def configure(self, in_map):
        if not in_map:
            raise self.err("all_good takes one or more inputs")
        for port in in_map:
            self.in_ports[port] = (None, True, True)
        self.out_ports["y"] = BOOLEAN

    def output(self, k, t, ins):
        return {"y": out(GOOD, all(s[0] == GOOD for s in ins.values()))}


class Delay(Block):
    SETTINGS = ("ticks", "initial")
    has_update = True

    def configure(self, in_map):
        self.in_ports["x"] = (None, True, False)
        self.out_ports["y"] = None
        self.ticks = s_whole(self, self.st, "ticks", 1)
        if self.ticks < 1:
            raise self.err("setting 'ticks' must be at least 1")
        self.initial = None
        self.initial_type = None
        if "initial" in self.st:
            v = self.st["initial"]
            if isinstance(v, bool):
                self.initial, self.initial_type = v, BOOLEAN
            elif _finite(v) is not None:
                self.initial, self.initial_type = float(v), NUMBER
            else:
                raise self.err("setting 'initial' must be a finite number or true or false")

    def reset(self):
        if self.initial is None:
            first = (NR, None, None, None)
        else:
            first = (GOOD, self.initial, None, None)
        self.first = first
        self.s = {"buf": [first] * self.ticks}

    def gap(self, g):
        self.s["buf"] = [(UNC, e[1], e[2], g) if e[0] == GOOD and e is not self.first else e for e in self.s["buf"]]

    def output(self, k, t, ins):
        return {"y": self.s["buf"][0]}

    def update(self, k, t, ins):
        buf = self.s["buf"]
        buf.pop(0)
        buf.append(ins["x"])


class Window(Block):
    SETTINGS = ("window", "min_good", "only_new")
    STATS = ("mean", "median", "min", "max", "spread", "slope")

    def configure(self, in_map):
        self.in_ports["x"] = (NUMBER, True, True)
        for p in self.STATS + ("count",):
            self.out_ports[p] = NUMBER
        self.n = s_counted(self, self.st, "window")
        if self.n < 1:
            raise self.err("setting 'window' must be at least one period")
        mg = s_num(self, self.st, "min_good", 1.0)
        if not (mg > 0 and mg <= 1):
            raise self.err("setting 'min_good' must be more than 0 and at most 1")
        self.need = max(1, ceil_tol(mg * self.n))
        self.only_new = s_bool(self, self.st, "only_new", False)

    def reset(self):
        # buf: the last (up to n) ticks, oldest first. An entry is
        # (True, value, state) for a sample, (False, None, state) for none.
        self.s = {"buf": [], "last": None}

    def gap(self, g):
        self.s["buf"] = []

    def output(self, k, t, ins):
        s = self.s
        x = ins["x"]
        if not usable(x[0]):
            entry = (False, None, x[0])
        elif not self.only_new:
            entry = (True, x[1], x[0])
        elif x[2] is not None and (s["last"] is None or x[2] > s["last"]):
            entry = (True, x[1], x[0])
            s["last"] = x[2]
        else:
            entry = (False, None, NR)
        buf = s["buf"]
        buf.append(entry)
        if len(buf) > self.n:
            buf.pop(0)
        offset = self.n - len(buf)  # ticks of the window from before the start
        samples = [(offset + i, e[1], e[2]) for i, e in enumerate(buf) if e[0]]
        cnt = len(samples)
        res = {"count": out(GOOD, float(cnt))}
        if cnt < self.need:
            none_states = [e[2] for e in buf if not e[0]]
            if offset > 0:
                none_states.append(NR)
            st = worst(none_states)
            for p in self.STATS:
                res[p] = out(st)
            return res
        all_good = all(sm[2] == GOOD for sm in samples)
        if self.only_new:
            st = GOOD if (all_good and offset == 0) else UNC
        else:
            st = GOOD if (all_good and cnt == self.n) else UNC
        vals = [sm[1] for sm in samples]
        total = 0.0
        for v in vals:
            total += v
        mean = total / cnt
        srt = sorted(vals)
        if cnt % 2:
            median = srt[cnt // 2]
        else:
            median = (srt[cnt // 2 - 1] + srt[cnt // 2]) / 2
        lo, hi = srt[0], srt[-1]
        res["mean"] = out(st, mean)
        res["median"] = out(st, median)
        res["min"] = out(st, lo)
        res["max"] = out(st, hi)
        res["spread"] = out(st, hi - lo)
        if cnt < 2:
            res["slope"] = out(BAD)
        else:
            times = [sm[0] * self.ctx.period for sm in samples]
            tm = 0.0
            for tt in times:
                tm += tt
            tm /= cnt
            num = 0.0
            den = 0.0
            for tt, v in zip(times, vals):
                num += (tt - tm) * (v - mean)
                den += (tt - tm) * (tt - tm)
            res["slope"] = out(st, num / den)
        return res


class Deadband(Block):
    SETTINGS = ("step", "ride_through")

    def configure(self, in_map):
        self.in_ports["x"] = (NUMBER, True, True)
        self.out_ports["y"] = NUMBER
        self.step = s_num(self, self.st, "step")
        if self.step < 0:
            raise self.err("setting 'step' must not be negative")
        self.rt = s_counted(self, self.st, "ride_through", 0)

    def reset(self):
        self.s = {"held": None, "m": 0}  # held: (value, state, cause)

    def gap(self, g):
        self.s["held"] = None
        self.s["m"] = 0

    def output(self, k, t, ins):
        s = self.s
        x = ins["x"]
        if usable(x[0]):
            s["m"] = 0
            h = s["held"]
            if h is None or abs(x[1] - h[0]) >= self.step:
                h = s["held"] = (x[1], x[0], x[3])
            if h[1] == GOOD and x[0] == GOOD:
                return {"y": out(GOOD, h[0])}
            cause = None
            if h[1] == UNC:
                cause = _later(cause, h[2])
            if x[0] == UNC:
                cause = _later(cause, x[3])
            return {"y": out(UNC, h[0], cause)}
        if s["held"] is not None:
            s["m"] += 1
            if s["m"] <= self.rt:
                return {"y": out(UNC, s["held"][0], k)}
            s["held"] = None
        return {"y": out(x[0])}


class Lowpass(Block):
    SETTINGS = ("tau", "ride_through", "settle")

    def configure(self, in_map):
        self.in_ports["x"] = (NUMBER, True, True)
        self.out_ports["y"] = NUMBER
        self.tau = s_length(self, self.st, "tau")
        if not self.tau > 0:
            raise self.err("setting 'tau' must be more than zero")
        self.rt = s_counted(self, self.st, "ride_through", 0)
        self.settle = s_counted(self, self.st, "settle", None)
        if self.settle is None:
            self.settle = ceil_tol(3.0 * self.tau / self.ctx.period)
        self.a = math.exp(-self.ctx.period / self.tau)

    def reset(self):
        self.s = {"y": None, "m": 0, "doubt": None}

    def gap(self, g):
        self.s["y"] = None
        self.s["m"] = 0

    def output(self, k, t, ins):
        s = self.s
        x = ins["x"]
        if usable(x[0]):
            if s["y"] is None:
                s["y"] = x[1]
                s["doubt"] = None
            else:
                m = s["m"] + 1
                am = self.a**m
                s["y"] = am * s["y"] + (1 - am) * x[1]
                if m > 1:
                    s["doubt"] = _later(s["doubt"], k)
            s["m"] = 0
            if x[0] == UNC:
                s["doubt"] = _later(s["doubt"], x[3])
            d = s["doubt"]
            if d is not None and k - d < self.settle:
                return {"y": out(UNC, s["y"], d)}
            return {"y": out(GOOD, s["y"])}
        if s["y"] is not None:
            s["m"] += 1
            if s["m"] <= self.rt:
                return {"y": out(UNC, s["y"], k)}
            s["y"] = None
            s["m"] = 0
        return {"y": out(x[0])}


class Hysteresis(Block):
    SETTINGS = ("rise", "fall", "initial")

    def configure(self, in_map):
        self.in_ports["x"] = (NUMBER, True, True)
        self.out_ports["y"] = BOOLEAN
        self.rise = s_num(self, self.st, "rise")
        self.fall = s_num(self, self.st, "fall")
        if not self.rise > self.fall:
            raise self.err("setting 'rise' must be more than 'fall'")
        self.initial = s_bool(self, self.st, "initial", None)

    def reset(self):
        self.s = {"on": self.initial, "sure": True}

    def gap(self, g):
        self.s["sure"] = False

    def output(self, k, t, ins):
        s = self.s
        x = ins["x"]
        if not usable(x[0]):
            s["sure"] = False
            return {"y": out(x[0])}
        if x[1] >= self.rise:
            s["on"] = True
            s["sure"] = x[0] == GOOD
        elif x[1] <= self.fall:
            s["on"] = False
            s["sure"] = x[0] == GOOD
        if s["on"] is None:
            return {"y": out(NR)}
        st = GOOD if (s["sure"] and x[0] == GOOD) else UNC
        return {"y": out(st, s["on"])}


class HeldFor(Block):
    SETTINGS = ("time", "on_bad", "hold_limit")

    def configure(self, in_map):
        self.in_ports["x"] = (BOOLEAN, True, True)
        self.out_ports["y"] = BOOLEAN
        self.n = s_counted(self, self.st, "time")
        self.on_bad = s_choice(self, self.st, "on_bad", ("reset", "hold"))
        if self.on_bad == "hold":
            self.limit = s_counted(self, self.st, "hold_limit")
        elif "hold_limit" in self.st:
            raise self.err("setting 'hold_limit' is refused without on_bad: hold")

    def reset(self):
        self.s = {"start": None, "all_good": True, "m": 0}

    def gap(self, g):
        self.s["start"] = None
        self.s["m"] = 0

    def output(self, k, t, ins):
        s = self.s
        x = ins["x"]
        if usable(x[0]):
            s["m"] = 0
            if not x[1]:
                s["start"] = None
                return {"y": out(x[0], False)}
            if s["start"] is None:
                s["start"] = k
                s["all_good"] = True
            if x[0] != GOOD:
                s["all_good"] = False
            st = GOOD if s["all_good"] else UNC
            return {"y": out(st, k - s["start"] > self.n)}
        if self.on_bad == "hold" and s["start"] is not None:
            s["m"] += 1
            if s["m"] <= self.limit:
                s["all_good"] = False
                return {"y": out(UNC, k - s["start"] > self.n)}
        s["start"] = None
        s["m"] = 0
        return {"y": out(x[0])}


class SinceTrue(Block):
    SETTINGS = ("time", "on_bad")

    def configure(self, in_map):
        self.in_ports["x"] = (BOOLEAN, True, True)
        self.out_ports["y"] = BOOLEAN
        self.n = s_counted(self, self.st, "time")
        self.on_bad = s_choice(self, self.st, "on_bad", ("assume_false", "unknown"))

    def reset(self):
        self.s = {"clock": None, "not_good": None}

    def gap(self, g):
        self.s["clock"] = g
        self.s["not_good"] = g

    def output(self, k, t, ins):
        s = self.s
        x = ins["x"]
        if s["clock"] is None:
            s["clock"] = k
        if x[0] != GOOD:
            s["not_good"] = k
        if usable(x[0]) and x[1]:
            s["clock"] = k
        if not usable(x[0]) and self.on_bad == "unknown":
            return {"y": out(x[0])}
        value = (k - s["clock"]) > self.n
        since = max(s["clock"], k - self.n)
        doubt = s["not_good"] is not None and s["not_good"] >= since
        return {"y": out(UNC if doubt else GOOD, value)}


class Latch(Block):
    def configure(self, in_map):
        self.in_ports["set"] = (BOOLEAN, True, True)
        self.in_ports["reset"] = (BOOLEAN, False, True)
        self.out_ports["y"] = BOOLEAN

    def reset(self):
        self.s = {"set": False, "sure": True}

    def gap(self, g):
        if not self.s["set"]:
            self.s["sure"] = False

    def output(self, k, t, ins):
        s = self.s
        st_ = ins["set"]
        rs = ins.get("reset")
        if rs is not None and usable(rs[0]) and rs[1]:
            s["set"] = False
            s["sure"] = rs[0] == GOOD
        elif usable(st_[0]) and st_[1]:
            was = s["set"]
            s["set"] = True
            if (not was) or st_[0] == GOOD:
                s["sure"] = st_[0] == GOOD
        elif (not s["set"]) and st_[0] != GOOD:
            s["sure"] = False
        if s["set"]:
            return {"y": out(GOOD if s["sure"] else UNC, True)}
        if not usable(st_[0]):
            return {"y": out(st_[0])}
        return {"y": out(GOOD if s["sure"] else UNC, False)}


class Integrate(Block):
    SETTINGS = ("per", "max_missed", "tolerance")

    def configure(self, in_map):
        self.in_ports["x"] = (NUMBER, True, True)
        self.in_ports["reset"] = (BOOLEAN, False, True)
        self.out_ports["y"] = NUMBER
        self.out_ports["missed"] = NUMBER
        self.per = s_length(self, self.st, "per", 1.0)
        if not self.per > 0:
            raise self.err("setting 'per' must be more than zero")
        self.max_missed = s_counted(self, self.st, "max_missed", None)
        self.tol = s_num(self, self.st, "tolerance", 0.0)
        if self.tol < 0:
            raise self.err("setting 'tolerance' must not be negative")

    def reset(self):
        self.s = {"total": 0.0, "run": 0, "missed": 0, "unc": 0, "gap": False}

    def gap(self, g):
        self.s["gap"] = True

    def output(self, k, t, ins):
        s = self.s
        x = ins["x"]
        rs = ins.get("reset")
        if rs is not None and usable(rs[0]) and rs[1]:
            self.reset()
            s = self.s
        s["run"] += 1
        if usable(x[0]):
            s["total"] += x[1] * self.ctx.period / self.per
            if x[0] == UNC:
                s["unc"] += 1
        else:
            s["missed"] += 1
        if self.max_missed is not None and s["missed"] > self.max_missed:
            st = BAD
        elif s["gap"] or s["missed"] + s["unc"] > self.tol * s["run"]:
            st = UNC
        else:
            st = GOOD
        return {"y": out(st, s["total"]), "missed": out(GOOD, s["missed"] * self.ctx.period)}


# ------------------------------------------------------------------ models


class ThermalMassModel:
    KEYS = ("thermal_mass", "heat_transfer", "initial")
    inputs = ("power", "ambient")
    outputs = ("temp",)

    def __init__(self, b, st):
        self.c = s_num(b, st, "thermal_mass")
        self.h = s_num(b, st, "heat_transfer")
        if not self.c > 0:
            raise b.err("setting 'thermal_mass' must be more than zero")
        if not self.h > 0:
            raise b.err("setting 'heat_transfer' must be more than zero")
        self.t0 = s_num(b, st, "initial")
        self.states = ("temp",)
        self.direct = set()
        self.tau = self.c / self.h
        self.max_step = 2.785 * self.tau

    def initial(self):
        return [self.t0]

    def step(self, x, u, d):
        p, amb = u["power"], u["ambient"]

        def f(temp):
            return (p - self.h * (temp - amb)) / self.c

        k1 = f(x[0])
        k2 = f(x[0] + d / 2 * k1)
        k3 = f(x[0] + d / 2 * k2)
        k4 = f(x[0] + d * k3)
        return [x[0] + d / 6 * (k1 + 2 * k2 + 2 * k3 + k4)]

    def out(self, x, u):
        return {"temp": x[0]}

    def sens(self, d, n):
        z = -d * self.h / self.c
        return [[(1 + z + z**2 / 2 + z**3 / 6 + z**4 / 24) ** n]]


class StateSpaceModel:
    KEYS = ("A", "B", "C", "D", "initial")
    inputs = ("u",)
    outputs = ("y",)

    def __init__(self, b, st):
        def vec(key, n, default=REQ):
            if key not in st:
                if default is REQ:
                    raise b.err("missing required setting %r" % key)
                return default
            v = st[key]
            if not isinstance(v, list) or (n is not None and len(v) != n):
                raise b.err("setting %r must be a list of %s numbers" % (key, "n" if n is None else n))
            res = []
            for e in v:
                f = _finite(e)
                if f is None:
                    raise b.err("setting %r must hold finite numbers" % key)
                res.append(f)
            return res

        if "A" not in st:
            raise b.err("missing required setting 'A'")
        a = st["A"]
        if not isinstance(a, list) or not a:
            raise b.err("setting 'A' must be a list of n rows of n numbers")
        n = len(a)
        self.a = []
        for row in a:
            if not isinstance(row, list) or len(row) != n:
                raise b.err("setting 'A' must be a list of n rows of n numbers")
            r = []
            for e in row:
                f = _finite(e)
                if f is None:
                    raise b.err("setting 'A' must hold finite numbers")
                r.append(f)
            self.a.append(r)
        self.n = n
        self.b = vec("B", n)
        self.c = vec("C", n)
        self.d = s_num(b, st, "D", 0.0)
        self.x0 = vec("initial", n, [0.0] * n)
        self.states = tuple("x%d" % i for i in range(n))
        self.direct = {"u"} if self.d != 0 else set()
        self.tau = None
        self.max_step = None

    def initial(self):
        return list(self.x0)

    def step(self, x, u, d):
        uu = u["u"]
        res = []
        for i in range(self.n):
            acc = 0.0
            for j in range(self.n):
                acc += self.a[i][j] * x[j]
            res.append(acc + self.b[i] * uu)
        return res

    def out(self, x, u):
        acc = 0.0
        for i in range(self.n):
            acc += self.c[i] * x[i]
        if self.d != 0:
            acc += self.d * u["u"]
        return {"y": acc}

    def sens(self, d, n):
        return [list(r) for r in self.a]


MODELS = {"thermal_mass": ThermalMassModel, "state_space": StateSpaceModel}


def _check_stable(b, model, substeps):
    if model.max_step is not None:
        if b.ctx.period / substeps > model.max_step:
            raise b.err(
                "the period over setting 'substeps' is longer than "
                "the longest step the model is stable at (%r s)" % model.max_step
            )


def _model_steps(model, substeps):
    """How many steps per tick, and how long each."""
    return substeps if model.max_step is not None or model.tau is not None else 1


class ModelBlock(Block):
    MODEL = None
    has_update = True

    def configure(self, in_map):
        mst = {k: v for k, v in self.st.items() if k in self.MODEL.KEYS}
        self.model = self.MODEL(self, mst)
        self.rt = s_counted(self, self.st, "ride_through", 0)
        self.substeps = s_whole(self, self.st, "substeps", 1)
        if self.substeps < 1:
            raise self.err("setting 'substeps' must be at least 1")
        self.settle = s_counted(self, self.st, "settle", None)
        if self.settle is None and self.model.tau is not None:
            self.settle = ceil_tol(3.0 * self.model.tau / self.ctx.period)
        _check_stable(self, self.model, self.substeps)
        self.nsteps = _model_steps(self.model, self.substeps)
        for name in self.model.inputs:
            self.in_ports[name] = (NUMBER, True, name in self.model.direct)
        for name in self.model.outputs:
            self.out_ports[name] = NUMBER

    def reset(self):
        self.s = {
            "x": self.model.initial(),
            "last": {n: None for n in self.model.inputs},
            "m": {n: 0 for n in self.model.inputs},
            "doubt": None,
        }

    def gap(self, g):
        self.s["doubt"] = _later(self.s["doubt"], g)

    def output(self, k, t, ins):
        s = self.s
        u = {}
        unusable_direct = False
        cause = None
        for name in self.model.direct:
            sg = ins[name]
            if usable(sg[0]):
                u[name] = sg[1]
                if sg[0] == UNC:
                    cause = _later(cause, sg[3])
            else:
                unusable_direct = True
                last = s["last"][name]
                u[name] = 0.0 if last is None else last
        vals = self.model.out(s["x"], u)
        d = s["doubt"]
        if unusable_direct:
            st, c = UNC, k
        elif cause is not None:
            st, c = UNC, cause
        elif d is not None and (self.settle is None or k - d < self.settle):
            st, c = UNC, d
        else:
            st, c = GOOD, None
        return {p: out(st, v, c) for p, v in vals.items()}

    def update(self, k, t, ins):
        s = self.s
        u = {}
        can_step = True
        held = False
        causes = None
        for name in self.model.inputs:
            sg = ins[name]
            if usable(sg[0]):
                u[name] = sg[1]
                s["last"][name] = sg[1]
                s["m"][name] = 0
                if sg[0] == UNC:
                    causes = _later(causes, sg[3])
            else:
                s["m"][name] += 1
                if s["last"][name] is not None and s["m"][name] <= self.rt:
                    u[name] = s["last"][name]
                    held = True
                else:
                    can_step = False
        if not can_step:
            s["doubt"] = _later(s["doubt"], k)
            return
        d = self.ctx.period / self.nsteps
        x = s["x"]
        for _ in range(self.nsteps):
            x = self.model.step(x, u, d)
        s["x"] = x
        s["doubt"] = _later(s["doubt"], causes)
        if held:
            s["doubt"] = _later(s["doubt"], k)


class ThermalMassBlock(ModelBlock):
    MODEL = ThermalMassModel
    SETTINGS = ThermalMassModel.KEYS + ("ride_through", "settle", "substeps")


class StateSpaceBlock(ModelBlock):
    MODEL = StateSpaceModel
    SETTINGS = StateSpaceModel.KEYS + ("ride_through", "settle", "substeps")


class Estimator(Block):
    SETTINGS = ("model", "q", "p0", "measure", "gate", "sigma_max", "use_uncertain", "substeps")

    def _state_map(self, key, required):
        if key not in self.st:
            if required:
                raise self.err("missing required setting %r" % key)
            return {}
        m = self.st[key]
        if not isinstance(m, dict):
            raise self.err("setting %r must be a map from states' names to numbers" % key)
        res = {}
        for name, v in m.items():
            if name not in self.model.states:
                raise self.err("setting %r names %r, which is not a state of the model" % (key, name))
            f = _finite(v)
            if f is None:
                raise self.err("setting %r: the value for %r must be a finite number" % (key, name))
            res[name] = f
        if required:
            for name in self.model.states:
                if name not in res:
                    raise self.err("setting %r has no value for state %r" % (key, name))
        return res

    def configure(self, in_map):
        if "model" not in self.st:
            raise self.err("missing required setting 'model'")
        m = self.st["model"]
        if not isinstance(m, dict) or "type" not in m:
            raise self.err("setting 'model' must be a map with a 'type'")
        if not isinstance(m["type"], str) or m["type"] not in MODELS:
            raise self.err("setting 'model': unknown model type %r" % (m["type"],))
        cls = MODELS[m["type"]]
        mst = {}
        for key, v in m.items():
            if key == "type":
                continue
            if key not in cls.KEYS:
                raise self.err("setting 'model': unknown setting %r" % (key,))
            mst[key] = v
        self.model = cls(self, mst)
        self.substeps = s_whole(self, self.st, "substeps", 1)
        if self.substeps < 1:
            raise self.err("setting 'substeps' must be at least 1")
        _check_stable(self, self.model, self.substeps)
        self.nsteps = _model_steps(self.model, self.substeps)
        states = self.model.states
        q = self._state_map("q", True)
        p0 = self._state_map("p0", True)
        for name in states:
            if q[name] < 0:
                raise self.err("setting 'q' for %r must not be negative" % name)
            if not p0[name] > 0:
                raise self.err("setting 'p0' for %r must be more than zero" % name)
        self.q = [q[n] for n in states]
        self.p0 = [p0[n] for n in states]
        smax = self._state_map("sigma_max", False)
        self.sigma_max = [smax.get(n) for n in states]
        self.gate = s_num(self, self.st, "gate", None)
        if self.gate is not None and self.gate < 0:
            raise self.err("setting 'gate' must not be negative")
        self.use_uncertain = s_bool(self, self.st, "use_uncertain", False)
        if "measure" not in self.st:
            raise self.err("missing required setting 'measure'")
        meas = self.st["measure"]
        if not isinstance(meas, dict):
            raise self.err("setting 'measure' must be a map")
        for name in self.model.inputs:
            self.in_ports[name] = (NUMBER, True, True)
        for name in states:
            self.out_ports[name] = NUMBER
        for name in states:
            self._add_out("sigma_" + name)
        self.measures = []  # (port, state index, r)
        for port, spec in meas.items():
            if not isinstance(port, str):
                raise self.err("setting 'measure': a port's name is text, got %r" % (port,))
            if port in self.in_ports:
                raise self.err("setting 'measure': port %r is named twice or is one of the model's inputs" % port)
            if not isinstance(spec, dict):
                raise self.err("setting 'measure': port %r needs 'of' and 'r'" % port)
            for key in spec:
                if key not in ("of", "r"):
                    raise self.err("setting 'measure': port %r has an unknown key %r" % (port, key))
            if "of" not in spec or spec["of"] not in states:
                raise self.err("setting 'measure': port %r must name a state of the model in 'of'" % port)
            r = _finite(spec.get("r"))
            if r is None or not r > 0:
                raise self.err("setting 'measure': port %r needs an 'r' more than zero" % port)
            self.in_ports[port] = (NUMBER, True, True)
            self.measures.append((port, states.index(spec["of"]), r))
        for port, _i, _r in self.measures:
            self._add_out("innovation_" + port)
            self._add_out("refused_" + port)
            self._add_out("since_" + port)

    def _add_out(self, name):
        if name in self.out_ports:
            raise self.err("two outputs would be named %r" % name)
        self.out_ports[name] = NUMBER

    def reset(self):
        n = len(self.model.states)
        self.s = {
            "x": self.model.initial(),
            "p": [[self.p0[i] if i == j else 0.0 for j in range(n)] for i in range(n)],
            "last": {nm: None for nm in self.model.inputs},
            "considered": {m[0]: None for m in self.measures},
            "refused": {m[0]: 0 for m in self.measures},
            "used": {m[0]: None for m in self.measures},
        }

    def gap(self, g):
        for i in range(len(self.p0)):
            self.s["p"][i][i] += self.p0[i]

    def output(self, k, t, ins):
        s = self.s
        n = len(self.model.states)
        period = self.ctx.period
        # predict, on the model inputs as they were at the tick before
        if k != 0:
            p = s["p"]
            if all(v is not None for v in s["last"].values()):
                d = period / self.nsteps
                f = self.model.sens(d, self.nsteps)
                x = s["x"]
                for _ in range(self.nsteps):
                    x = self.model.step(x, s["last"], d)
                s["x"] = x
                fp = [[sum(f[i][m] * p[m][j] for m in range(n)) for j in range(n)] for i in range(n)]
                p = [[sum(fp[i][m] * f[j][m] for m in range(n)) for j in range(n)] for i in range(n)]
                s["p"] = p
            for i in range(n):
                p[i][i] += self.q[i] * period
        any_unusable = False
        for name in self.model.inputs:
            sg = ins[name]
            if usable(sg[0]):
                s["last"][name] = sg[1]
            else:
                any_unusable = True
        # correct
        res = {}
        x = s["x"]
        p = s["p"]
        for port, i, r in self.measures:
            sg = ins[port]
            ok = sg[0] == GOOD or (self.use_uncertain and sg[0] == UNC)
            last = s["considered"][port]
            if ok and sg[2] is not None and (last is None or sg[2] > last):
                s["considered"][port] = sg[2]
                innovation = sg[1] - x[i]
                spread = p[i][i] + r
                root = math.sqrt(spread) if spread >= 0 else float("nan")
                if self.gate is not None and abs(innovation) > self.gate * root:
                    s["refused"][port] += 1
                else:
                    g = [p[j][i] / spread for j in range(n)]
                    row = list(p[i])
                    for j in range(n):
                        x[j] += g[j] * innovation
                        for l in range(n):  # noqa: E741
                            p[j][l] -= g[j] * row[l]
                    s["used"][port] = sg[2]
                res["innovation_" + port] = out(GOOD, innovation)
            else:
                res["innovation_" + port] = out(NR)
            res["refused_" + port] = out(GOOD, float(s["refused"][port]))
            if s["used"][port] is None:
                res["since_" + port] = out(NR)
            else:
                res["since_" + port] = out(GOOD, t - s["used"][port])
        for i, name in enumerate(self.model.states):
            var = p[i][i]
            sigma = math.sqrt(var) if var >= 0 else float("nan")
            st = GOOD
            if any_unusable:
                st = UNC
            elif self.sigma_max[i] is not None and sigma > self.sigma_max[i]:
                st = UNC
            res[name] = out(st, x[i])
            res["sigma_" + name] = out(st, sigma)
        return res


BLOCK_TYPES = {
    "formula": Formula,
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


# ------------------------------------------------------------------ engine


class _Ctx:
    def __init__(self, period_fr):
        self.period_fr = period_fr
        self.period = float(period_fr)


class _Input:
    def __init__(self, type_, max_age, max_ahead, has_initial, initial):
        self.type = type_
        self.max_age = max_age  # seconds, or None for `none`
        self.max_ahead = max_ahead  # seconds
        self.has_initial = has_initial
        self.initial = initial


def _const_type(v):
    return BOOLEAN if isinstance(v, bool) else NUMBER


class Engine:
    def __init__(self, graph):
        if not isinstance(graph, dict):
            raise CompileError("the graph must be a map")
        for key in graph:
            if key not in ("period", "max_catch_up", "inputs", "blocks"):
                raise CompileError("unknown key %r at the top of the graph" % (key,))
        if "period" not in graph:
            raise CompileError("the graph has no 'period'")
        period_fr = parse_duration("period", graph["period"])
        if period_fr <= 0:
            raise CompileError("period: must be more than zero")
        self._ctx = _Ctx(period_fr)
        self._period = self._ctx.period
        self._max_catch_up = graph.get("max_catch_up", 100)
        if not isinstance(self._max_catch_up, int) or isinstance(self._max_catch_up, bool) or self._max_catch_up < 1:
            raise CompileError("max_catch_up: must be a whole number, at least 1")
        self._compile_inputs(graph.get("inputs"))
        self._compile_blocks(graph.get("blocks"))
        self._graph_key = json.dumps(graph, default=repr)
        self.reset()

    # ----------------------------------------------------------- compiling

    def _compile_inputs(self, decls):
        self.inputs = {}
        if decls is None:
            decls = {}
        if not isinstance(decls, dict):
            raise CompileError("inputs: must be a map")
        for name, d in decls.items():
            what = "input %r" % (name,)
            if not isinstance(name, str):
                raise CompileError("%s: an input's name is text" % what)
            if d is None:
                d = {}
            if not isinstance(d, dict):
                raise CompileError("%s: must be a map" % what)
            for key in d:
                if key not in ("type", "unit", "max_age", "max_ahead", "initial"):
                    raise CompileError("%s: unknown key %r" % (what, key))
            type_ = d.get("type", NUMBER)
            if type_ not in (NUMBER, BOOLEAN):
                raise CompileError("%s: unknown type %r" % (what, type_))
            if "max_age" not in d:
                raise CompileError("%s: no max_age" % what)
            if d["max_age"] == "none" and isinstance(d["max_age"], str):
                max_age = None
            else:
                max_age = float(parse_duration(what + " max_age", d["max_age"]))
            if "max_ahead" in d:
                max_ahead = float(parse_duration(what + " max_ahead", d["max_ahead"]))
            else:
                max_ahead = self._period
            has_initial = "initial" in d
            initial = None
            if has_initial:
                v = d["initial"]
                if type_ == BOOLEAN:
                    if not isinstance(v, bool):
                        raise CompileError("%s: initial must be true or false" % what)
                    initial = v
                else:
                    initial = _finite(v)
                    if initial is None:
                        raise CompileError("%s: initial must be a finite number" % what)
            self.inputs[name] = _Input(type_, max_age, max_ahead, has_initial, initial)

    def _compile_blocks(self, specs):
        if specs is None:
            specs = []
        if not isinstance(specs, list):
            raise CompileError("blocks: must be a list")
        self._blocks = {}
        in_maps = {}
        out_maps = {}
        fallbacks = {}
        for spec in specs:
            if not isinstance(spec, dict):
                raise CompileError("blocks: every block must be a map")
            if "id" not in spec:
                raise CompileError("a block has no id: %r" % (spec,))
            bid = spec["id"]
            if not isinstance(bid, str):
                raise CompileError("block id %r is not text" % (bid,))
            if bid in self._blocks:
                raise CompileError("block %r: two blocks have this id" % bid)
            for key in spec:
                if key not in ("id", "type", "in", "settings", "out", "fallback"):
                    raise CompileError("block %r: unknown key %r" % (bid, key))
            btype = spec.get("type")
            if not isinstance(btype, str) or btype not in BLOCK_TYPES:
                raise CompileError("block %r: unknown block type %r" % (bid, btype))
            maps = []
            for key in ("in", "settings", "out", "fallback"):
                m = spec.get(key)
                if m is None:
                    m = {}
                if not isinstance(m, dict):
                    raise CompileError("block %r: %r must be a map" % (bid, key))
                for name in m:
                    if not isinstance(name, str):
                        raise CompileError("block %r: %r in %r is not text" % (bid, name, key))
                maps.append(m)
            in_map, settings, out_map, fallback = maps
            for port, v in in_map.items():
                if isinstance(v, str) or isinstance(v, bool):
                    continue
                if _finite(v) is None:
                    raise CompileError(
                        "block %r: input port %r must be given a signal's "
                        "name, a finite number, or true or false, got %r" % (bid, port, v)
                    )
            b = BLOCK_TYPES[btype](bid, settings, in_map, self._ctx)
            for port in in_map:
                if port not in b.in_ports:
                    raise b.err("unknown input port %r" % port)
            for port, (_t, required, _d) in b.in_ports.items():
                if required and port not in in_map:
                    raise b.err("required input port %r is not connected" % port)
            for port, name in out_map.items():
                if port not in b.out_ports:
                    raise b.err("unknown output port %r in 'out'" % port)
                if not isinstance(name, str):
                    raise b.err("output port %r: a signal's name is text, got %r" % (port, name))
            for port in fallback:
                if port not in b.out_ports:
                    raise b.err("unknown output port %r in 'fallback'" % port)
            self._blocks[bid] = b
            in_maps[bid] = in_map
            out_maps[bid] = out_map
            fallbacks[bid] = fallback

        # names
        dotted = {}
        for bid, b in self._blocks.items():
            for port in b.out_ports:
                name = bid + "." + port
                if name in dotted:
                    raise CompileError(
                        "block %r: %r could also mean port %r of block %r"
                        % (bid, name, dotted[name][2], dotted[name][1])
                    )
                dotted[name] = ("blk", bid, port)
        for name in self.inputs:
            if name in dotted:
                raise CompileError("input %r has a name of the form <block id>.<port>" % name)
        self._published = {}
        for bid, out_map in out_maps.items():
            for port, name in out_map.items():
                if name in dotted:
                    raise CompileError(
                        "block %r: output port %r is published as %r, a "
                        "name of the form <block id>.<port>" % (bid, port, name)
                    )
                if name in self.inputs:
                    raise CompileError(
                        "block %r: output port %r writes signal %r, which is an input from outside" % (bid, port, name)
                    )
                if name in self._published:
                    raise CompileError(
                        "block %r: output port %r writes signal %r, which has another writer" % (bid, port, name)
                    )
                self._published[name] = ("blk", bid, port)

        # connections
        for bid, b in self._blocks.items():
            b.conns = {}
            for port, v in in_maps[bid].items():
                if isinstance(v, bool):
                    b.conns[port] = ("const", v)
                elif not isinstance(v, str):
                    b.conns[port] = ("const", float(v))
                elif v in self.inputs:
                    b.conns[port] = ("in", v)
                elif v in self._published:
                    b.conns[port] = self._published[v]
                elif v in dotted:
                    b.conns[port] = dotted[v]
                else:
                    raise b.err(
                        "input port %r reads signal %r, which is neither an input nor a block's output" % (port, v)
                    )

        # loops (rules 5.3, 5.4) and the order (rules 5.1, 5.2)
        self._order = self._sort()
        self._check_delays()

        # types
        self._types = {}
        self._typing = set()
        for bid, b in self._blocks.items():
            for port in b.out_ports:
                self._out_type(b, port)
            for port, conn in b.conns.items():
                want = b.in_ports[port][0]
                got = self._conn_type(conn)
                if isinstance(b, Delay):
                    want = b.initial_type
                if want is not None and got != want:
                    raise b.err("input port %r is a %s and is connected to a %s" % (port, want, got))
            b.fallback = {}
            for port, v in fallbacks[bid].items():
                ptype = self._types[(bid, port)]
                if ptype == BOOLEAN:
                    if not isinstance(v, bool):
                        raise b.err("fallback for %r must be true or false" % port)
                    b.fallback[port] = v
                else:
                    f = _finite(v)
                    if f is None:
                        raise b.err("fallback for %r must be a finite number" % port)
                    b.fallback[port] = f

    def _conn_type(self, conn):
        if conn[0] == "const":
            return _const_type(conn[1])
        if conn[0] == "in":
            return self.inputs[conn[1]].type
        return self._out_type(self._blocks[conn[1]], conn[2])

    def _out_type(self, b, port):
        key = (b.id, port)
        if key in self._types:
            return self._types[key]
        if key in self._typing:
            raise b.err("the type of output %r depends on itself" % port)
        self._typing.add(key)
        t = b.out_ports[port]
        if t is None:
            if isinstance(b, Delay):
                if b.initial_type is not None:
                    t = b.initial_type
                else:
                    t = self._conn_type(b.conns["x"])
            else:
                t = b.typecheck({p: self._conn_type(c) for p, c in b.conns.items()})
        self._typing.discard(key)
        self._types[key] = t
        return t

    def _sort(self):
        deps = {bid: set() for bid in self._blocks}
        for bid, b in self._blocks.items():
            for port, conn in b.conns.items():
                if conn[0] == "blk" and b.in_ports[port][2]:
                    deps[bid].add(conn[1])
        order = []
        done = set()
        remaining = set(self._blocks)
        while remaining:
            ready = sorted(bid for bid in remaining if deps[bid] <= done)
            if not ready:
                on_loop = self._on_loop(deps, remaining)
                raise CompileError("a loop of direct inputs through blocks " + ", ".join(repr(x) for x in on_loop))
            bid = ready[0]
            order.append(self._blocks[bid])
            done.add(bid)
            remaining.discard(bid)
        return order

    @staticmethod
    def _reach(deps, start):
        seen = set()
        stack = list(deps[start])
        while stack:
            x = stack.pop()
            if x not in seen:
                seen.add(x)
                stack.extend(deps[x])
        return seen

    def _on_loop(self, deps, remaining):
        return sorted(bid for bid in remaining if bid in self._reach(deps, bid))

    def _check_delays(self):
        deps = {bid: set() for bid in self._blocks}
        for bid, b in self._blocks.items():
            for conn in b.conns.values():
                if conn[0] == "blk":
                    deps[bid].add(conn[1])
        for bid, b in self._blocks.items():
            if isinstance(b, Delay) and b.initial is None:
                if bid in self._reach(deps, bid):
                    raise b.err("setting 'initial' is missing, and the delay can reach its own input")

    # ------------------------------------------------------------- running

    def reset(self):
        self._last_k = None  # number of the last tick run
        self._anchor_k = 0  # a tick whose time is known ...
        self._anchor_t = 0.0  # ... and its time
        self._origin_t = 0.0  # time of tick 0, or of the last gap's tick
        self._last_now = None
        self._restored = False
        self._standing = {}  # name -> (state, value, sampled, refused)
        self._pending = {}  # name -> (state, value, sampled)
        for b in self._blocks.values():
            b.reset()

    def save(self):
        return {
            "graph": self._graph_key,
            "engine": copy.deepcopy(
                (self._last_k, self._anchor_k, self._anchor_t, self._origin_t, self._last_now, self._standing)
            ),
            "blocks": {bid: copy.deepcopy(b.s) for bid, b in self._blocks.items()},
        }

    def restore(self, saved):
        if not isinstance(saved, dict) or saved.get("graph") != self._graph_key:
            raise ValueError("this state was not saved from the same graph")
        (self._last_k, self._anchor_k, self._anchor_t, self._origin_t, self._last_now, self._standing) = copy.deepcopy(
            saved["engine"]
        )
        for bid, b in self._blocks.items():
            b.s = copy.deepcopy(saved["blocks"][bid])
        self._pending = {}
        self._restored = True

    def write(self, name, state, value, sampled):
        if name not in self.inputs:
            raise KeyError("no input named %r" % (name,))
        if state not in _RANK:
            raise ValueError("unknown state %r" % (state,))
        if not usable(state):
            self._pending[name] = (state, None, None)
            return
        if self.inputs[name].type == BOOLEAN:
            if not isinstance(value, bool):
                raise ValueError("input %r takes a boolean" % name)
        else:
            if not _is_num(value):
                raise ValueError("input %r takes a number" % name)
            value = float(value)
        if not _is_num(sampled) or not math.isfinite(sampled):
            raise ValueError("a usable value needs a finite sample time")
        self._pending[name] = (state, value, float(sampled))

    def _time(self, k):
        return self._anchor_t + (k - self._anchor_k) * self._period

    def tick(self, now):
        if not _is_num(now) or not math.isfinite(now):
            raise ValueError("now must be a finite number")
        now = float(now)
        gap = False
        if self._last_k is None:
            ticks = [(0, now)]
            self._anchor_k, self._anchor_t = 0, now
            self._origin_t = now
        elif self._restored:
            gap = True
        else:
            if now < self._last_now:
                raise ValueError("now is earlier than the last call's")
            ticks = []
            k = self._last_k + 1
            while len(ticks) <= self._max_catch_up:
                t = self._time(k)
                if t <= now + 0.5 * self._period + self._period * 1e-6:
                    ticks.append((k, t))
                    k += 1
                else:
                    break
            if not ticks:
                self._last_now = now
                return (0, None)
            if len(ticks) > self._max_catch_up:
                gap = True
        self._restored = False
        if gap:
            g = self._last_k + 1
            self._anchor_k, self._anchor_t = g, now
            self._origin_t = now
            self._standing = {}
            for b in self._blocks.values():
                b.gap(g)
            ticks = [(g, now)]
        sig = None
        for i, (k, t) in enumerate(ticks):
            if i == len(ticks) - 1:
                self._take_up(t)
            sig = self._run_tick(k, t)
            self._last_k = k
        self._last_now = now
        outputs = {}
        for name, key in self._published.items():
            s = sig[key]
            outputs[name] = (s[0], s[1])
        return (len(ticks), outputs)

    def _take_up(self, t):
        slack = self._period * 1e-6
        for name, (state, value, sampled) in self._pending.items():
            refused = False
            if usable(state):
                refused = sampled - t > self.inputs[name].max_ahead + slack
            self._standing[name] = (state, value, sampled, refused)
        self._pending = {}

    def _input_signal(self, name, k, t):
        d = self.inputs[name]
        slack = self._period * 1e-6
        standing = self._standing.get(name)
        if standing is None:
            too_long = d.max_age is not None and t - self._origin_t > d.max_age + slack
            if not too_long:
                if d.has_initial:
                    return (UNC, d.initial, None, k)
                return (NR, None, None, None)
            return (BAD, None, None, None)
        state, value, sampled, refused = standing
        if not usable(state):
            return (state, None, None, None)
        if d.type == NUMBER and not math.isfinite(value):
            return (BAD, None, None, None)
        if refused:
            return (BAD, None, None, None)
        if d.max_age is not None and t - sampled > d.max_age + slack:
            return (BAD, None, None, None)
        return (state, value, sampled, k if state == UNC else None)

    @staticmethod
    def _get(conn, sig):
        if conn[0] == "const":
            return (GOOD, conn[1], None, None)
        return sig[conn]

    def _run_tick(self, k, t):
        sig = {}
        for name in self.inputs:
            sig[("in", name)] = self._input_signal(name, k, t)
        # first phase: every block gives its outputs
        for b in self._order:
            ins = {port: self._get(conn, sig) for port, conn in b.conns.items() if b.in_ports[port][2]}
            outs = b.output(k, t, ins)
            for port in b.out_ports:
                state, value, stime, cause = outs[port]
                ptype = self._types[(b.id, port)]
                if usable(state) and ptype == NUMBER:
                    value = float(value)
                    if not math.isfinite(value):
                        state = BAD
                if not usable(state):
                    if port in b.fallback:
                        res = (UNC, b.fallback[port], t, k)
                    else:
                        res = (state, None, None, None)
                else:
                    if stime is TICK:
                        stime = t
                    if state == UNC:
                        if cause is None:
                            causes = [s[3] for s in ins.values() if s[0] == UNC and s[3] is not None]
                            cause = max(causes) if causes else k
                    else:
                        cause = None
                    res = (state, value, stime, cause)
                sig[("blk", b.id, port)] = res
        # second phase: every block updates its state
        for b in self._order:
            if b.has_update:
                ins = {port: self._get(conn, sig) for port, conn in b.conns.items()}
                b.update(k, t, ins)
        return sig

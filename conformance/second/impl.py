"""An independent reading of "FluxGraph semantics, version 2 (proposal)".

Sections 3 to 9 and every block type of Appendix A. Units are ignored.
Standard library only. Choices the text does not settle are listed in
ASSUMPTIONS.md, for Amendment 1 (time and the host interface) in
ASSUMPTIONS-amendment-1.md, for Amendment 2 (doubt through memory) in
ASSUMPTIONS-amendment-2.md, for Amendment 3 (gaps) in
ASSUMPTIONS-amendment-3.md, for Amendment 4 (models) in
ASSUMPTIONS-amendment-4.md, for Amendment 5 (the estimator) in
ASSUMPTIONS-amendment-5.md, and for Amendment 6 (the whole text, read cold)
in ASSUMPTIONS-amendment-6.md, and for Amendment 7 (a rate limit and a PID)
in ASSUMPTIONS-amendment-7.md.

Every time is a whole number of nanoseconds, held as an int (rule 6.2).
"""

import copy
import decimal
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


_INT32_MAX = 2147483647  # the most `ticks`, `over`, `max_refused`, `max_catch_up` and `max_waiting` may be


def ceil_exact(v):
    """A fraction rounded up to a whole number, exactly: no tolerance
    (rule 6.3)."""
    return -((-v.numerator) // v.denominator)


def as_written(v):
    """A number of the graph file as the decimal it is written as (rule
    6.3): a double is taken for the shortest decimal that reads back as
    it, which is what was written unless that had more digits than a
    double keeps."""
    if isinstance(v, int):
        return Fraction(v)
    return Fraction(decimal.Decimal(repr(float(v))))


def settle_of(tau, period):
    """A named model's `settle`, three of its slowest time constant in
    ticks (rule 7.8.6): in double arithmetic, the least whole number not
    less than r - 1e-9."""
    return int(math.ceil(3.0 * tau / period - 1e-9))


def _is_time(v):
    """A time the host gives: a whole number (of nanoseconds)."""
    return isinstance(v, int) and not isinstance(v, bool) and -(2**63) <= v < 2**63


_NS = 10**9
_DUR_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)(ns|us|ms|s|m|h)")
_UNITS = {"ns": 1, "us": 10**3, "ms": 10**6, "s": _NS, "m": 60 * _NS, "h": 3600 * _NS}


def parse_length(what, v):
    """A length as written, in nanoseconds, exactly (it need not be whole)."""
    if not isinstance(v, str):
        raise CompileError("%s: a length of time is a number and a unit, got %r" % (what, v))
    m = _DUR_RE.fullmatch(v)
    if not m:
        raise CompileError("%s: %r is not a length of time" % (what, v))
    return Fraction(m.group(1)) * _UNITS[m.group(2)]


def parse_duration(what, v):
    """A length of time the engine keeps: a whole number of nanoseconds."""
    d = parse_length(what, v)
    if d.denominator != 1:
        raise CompileError("%s: %r is not a whole number of nanoseconds" % (what, v))
    if d >= 2**63:
        raise CompileError("%s: %r does not fit in 64 bits, signed" % (what, v))
    return int(d)


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
    if v > _INT32_MAX:
        raise b.err("setting %r must be at most %d" % (key, _INT32_MAX))
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
    if d % b.ctx.period_ns:
        raise b.err("setting %r (%s) is not a whole number of periods" % (key, st[key]))
    return d // b.ctx.period_ns


def s_length(b, st, key, default=REQ):
    """A length that only scales a value: any length at all, in seconds."""
    if key not in st:
        if default is REQ:
            raise b.err("missing required setting %r" % key)
        return default
    return float(parse_length("block %r setting %r" % (b.id, key), st[key]) / _NS)


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


def _fuses(node, env, acc):
    """The names a formula uses at a tick (rule D): not an operand that did
    not decide, and not a branch it did not take."""
    k = node[0]
    if k == "name":
        acc.add(node[1])
    elif k in ("neg", "not"):
        _fuses(node[1], env, acc)
    elif k in ("or", "and"):
        decides = k == "or"
        ops = [(o, _feval(o, env)) for o in (node[1], node[2])]
        deciders = [(o, r) for o, r in ops if usable(r[0]) and r[1] is decides]
        if any(r[0] == GOOD for o, r in deciders):
            deciders = [(o, r) for o, r in deciders if r[0] == GOOD]
        for o, _r in deciders or ops:
            _fuses(o, env, acc)
    elif k in ("arith", "cmp"):
        _fuses(node[2], env, acc)
        _fuses(node[3], env, acc)
    elif k == "call":
        args = node[2]
        if node[1] == "when":
            _fuses(args[0], env, acc)
            c = _feval(args[0], env)
            if usable(c[0]):
                _fuses(args[1] if c[1] else args[2], env, acc)
        else:
            for a in args:
                _fuses(a, env, acc)
    return acc


# ------------------------------------------------------------------ blocks
#
# A signal is a tuple (state, value, sample_time).
# A block's output() returns {port: (state, value, sample_time)}, where
# sample_time may be TICK. The engine applies rule 3.6 and the fallback.


def out(state, value=None):
    return (state, value, TICK)


class _Loop:
    """A loop that holds a model, treated as one block (rule 7.8.8)."""

    def __init__(self, ids, settle):
        self.ids = ids
        self.settle = settle
        self.read = set()  # (block id, port): outputs a block of the loop reads
        self.reset()

    def reset(self):
        # doubt: the latest tick of a doubt; prev: the latest before this tick
        self.s = {"doubt": None, "prev": None}

    def within(self, k):
        """Whether tick k is one of the `settle` ticks after a doubt."""
        d = self.s["prev"]
        return d is not None and k - d <= self.settle


class Block:
    SETTINGS = ()
    has_update = False
    loop = None  # the loop that holds a model the block is on, if any

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

    def gap(self, g, n):
        """Before tick g runs at a gap: n ticks were passed over, or n is
        None and nobody knows how many (rule 8.6)."""

    def rebase(self):
        """Forget every sample time the block remembers (rule 8.5)."""

    def uses(self, ins):
        """The inputs, of those given, the block uses at this tick."""
        return set(ins)

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

    def uses(self, ins):
        return _fuses(self.ast, {p: (s[0], s[1]) for p, s in ins.items()}, set())

    def output(self, k, t, ins):
        env = {p: (s[0], s[1]) for p, s in ins.items()}
        st, v = _feval(self.ast, env)
        stime = TICK
        if self.sample_port is not None:
            stime = ins[self.sample_port][2]
        return {"y": (st, v, stime)}


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
            first = (NR, None, None)
        else:
            first = (GOOD, self.initial, None)
        self.s = {"buf": [first] * self.ticks}

    def gap(self, g, n):
        # it moves on, taking in not_ready for each tick nobody saw; where
        # nobody knows how many, that is everything it holds
        n = self.ticks if n is None else min(n, self.ticks)
        self.s["buf"] = self.s["buf"][n:] + [(NR, None, None)] * n

    def rebase(self):
        # the values it holds carry no sample time from then on (rule 8.5)
        self.s["buf"] = [e if e[2] is None else (e[0], e[1], None) for e in self.s["buf"]]

    def output(self, k, t, ins):
        if self.loop is not None and not self.loop.within(k):
            # the loop has settled: what it took in as uncertain becomes
            # good, and stays so (rule 7.8.8)
            self.s["buf"] = [(GOOD, e[1], e[2]) if e[0] == UNC else e for e in self.s["buf"]]
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
        # worked exactly, from the decimal as it is written (rule 6.3)
        self.need = max(1, ceil_exact(as_written(self.st.get("min_good", 1)) * self.n))
        self.only_new = s_bool(self, self.st, "only_new", False)
        if self.only_new and "min_good" not in self.st:
            raise self.err("setting 'min_good' is required with only_new: true")

    def reset(self):
        # buf: the last (up to n) ticks, oldest first. An entry is
        # (True, value, state) for a sample, (False, None, state) for none.
        self.s = {"buf": [], "last": None}

    def gap(self, g, n):
        if n is None:
            self.s["buf"] = []  # none of its ticks holds a sample
        else:
            # the ticks passed over hold no sample, and count as not_ready
            self.s["buf"] = (self.s["buf"] + [(False, None, NR)] * min(n, self.n))[-self.n :]

    def rebase(self):
        self.s["last"] = None
        if self.only_new:
            # it cannot tell a sample from before the rebase from the same
            # one written again after it: it keeps none (rule 8.5)
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
        if self.loop is not None and not self.loop.within(k):
            # the loop has settled: a sample taken in as uncertain at an
            # earlier tick is held as a good one from then on (rule 7.8.8)
            s["buf"] = [(e[0], e[1], GOOD) if e[0] and e[2] == UNC else e for e in s["buf"]]
        buf = s["buf"]
        buf.append(entry)
        if len(buf) > self.n:
            buf.pop(0)
        offset = self.n - len(buf)  # ticks of the window from before the start
        samples = [(offset + i, e[1], e[2]) for i, e in enumerate(buf) if e[0]]
        usable_samples = samples
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
        good = [sm for sm in samples if sm[2] == GOOD]
        if len(good) >= self.need:
            # the statistics are of the good samples alone (rule 7.3.5)
            st = GOOD
            samples = good
            cnt = len(samples)
        else:
            st = UNC
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
        if cnt < 2 and len(usable_samples) >= 2:
            # fewer than two good samples: of its usable ones (rule 7.3.6)
            st = UNC
            samples = usable_samples
            cnt = len(samples)
            vals = [sm[1] for sm in samples]
            total = 0.0
            for v in vals:
                total += v
            mean = total / cnt
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
        self.s = {"held": None, "m": 0}  # held: the value, or None

    def gap(self, g, n):
        s = self.s
        if s["held"] is None:
            return
        if n is not None and s["m"] + n <= self.rt:
            s["m"] += n  # it rides through the ticks passed over
        else:
            s["held"] = None
            s["m"] = 0

    def output(self, k, t, ins):
        s = self.s
        x = ins["x"]
        if usable(x[0]):
            s["m"] = 0
            if s["held"] is None or abs(x[1] - s["held"]) >= self.step:
                s["held"] = x[1]
            return {"y": out(x[0], s["held"])}
        if s["held"] is not None:
            s["m"] += 1
            if s["m"] <= self.rt:
                return {"y": out(UNC, s["held"])}
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
            # three time constants, rounded up exactly (rule 6.3)
            tau_ns = parse_length("block %r setting 'tau'" % self.id, self.st["tau"])
            self.settle = ceil_exact(3 * tau_ns / self.ctx.period_ns)
        self.a = math.exp(-self.ctx.period / self.tau)

    def reset(self):
        self.s = {"y": None, "m": 0, "doubt": None}

    def gap(self, g, n):
        s = self.s
        if s["y"] is None:
            return
        if n is not None and s["m"] + n <= self.rt:
            s["m"] += n  # it rides through, and decays over them later (rule 7.4.5)
        else:
            s["y"] = None
            s["m"] = 0
            s["doubt"] = None

    def output(self, k, t, ins):
        s = self.s
        x = ins["x"]
        if self.loop is not None and not self.loop.within(k):
            s["doubt"] = None  # the loop has settled: its doubt is cleared (rule 7.8.8)
        if usable(x[0]):
            if s["y"] is None:
                s["y"] = x[1]
            else:
                am = self.a ** (s["m"] + 1)
                s["y"] = am * s["y"] + (1 - am) * x[1]
            s["m"] = 0
            d = s["doubt"]
            if x[0] == UNC:
                s["doubt"] = k
                return {"y": out(UNC, s["y"])}
            if d is not None and k - d <= self.settle:
                return {"y": out(UNC, s["y"])}
            return {"y": out(GOOD, s["y"])}
        if s["y"] is not None:
            s["m"] += 1
            if s["m"] <= self.rt:
                return {"y": out(UNC, s["y"])}
            s["y"] = None
            s["m"] = 0
            s["doubt"] = None
        return {"y": out(x[0])}


class RateLimit(Block):
    SETTINGS = ("up", "down", "ride_through", "initial")

    def configure(self, in_map):
        self.in_ports["x"] = (NUMBER, True, True)
        self.out_ports["y"] = NUMBER
        self.out_ports["limited"] = BOOLEAN
        self.up = s_num(self, self.st, "up")
        if self.up < 0:
            raise self.err("setting 'up' must not be negative")
        self.down = s_num(self, self.st, "down", self.up)
        if self.down < 0:
            raise self.err("setting 'down' must not be negative")
        self.rt = s_counted(self, self.st, "ride_through", 0)
        self.initial = s_num(self, self.st, "initial", None)

    def reset(self):
        # held: the value it holds, or None; given: it holds a value it
        # gave, and not `initial` alone
        self.s = {"held": self.initial, "m": 0, "given": False}

    def _forget(self):
        # having forgotten, it holds `initial` again if it was given one
        self.s["held"] = self.initial
        self.s["m"] = 0
        self.s["given"] = False

    def gap(self, g, n):
        s = self.s
        if not s["given"]:
            return
        if n is not None and s["m"] + n <= self.rt:
            s["m"] += n  # it rides through the ticks passed over
        else:
            self._forget()

    def output(self, k, t, ins):
        s = self.s
        x = ins["x"]
        if usable(x[0]):
            s["m"] = 0
            h = s["held"]
            if h is None:
                h = x[1]  # a first input is taken as it is
            elif x[1] > h:
                reach = self.up * self.ctx.period
                h = x[1] if x[1] - h <= reach else h + reach
            elif x[1] < h:
                reach = self.down * self.ctx.period
                h = x[1] if h - x[1] <= reach else h - reach
            s["held"] = h
            s["given"] = True
            return {"y": out(x[0], h), "limited": out(x[0], h != x[1])}
        # holding `initial` and nothing else it does not ride through
        if s["given"]:
            s["m"] += 1
            if s["m"] <= self.rt:
                return {"y": out(UNC, s["held"]), "limited": out(x[0])}
            self._forget()
        return {"y": out(x[0]), "limited": out(x[0])}


class Hysteresis(Block):
    SETTINGS = ("rise", "fall", "initial")

    def configure(self, in_map):
        self.in_ports["x"] = (NUMBER, True, True)
        self.out_ports["y"] = BOOLEAN
        self.out_ports["elapsed"] = NUMBER
        self.out_ports["doubtful"] = NUMBER
        self.rise = s_num(self, self.st, "rise")
        self.fall = s_num(self, self.st, "fall")
        if not self.rise > self.fall:
            raise self.err("setting 'rise' must be more than 'fall'")
        self.initial = s_bool(self, self.st, "initial", None)
        self.out_ports["gaps"] = NUMBER

    def reset(self):
        # run, doubtful, gaps: counted since its value last changed
        self.s = {"on": self.initial, "run": 0, "doubtful": 0, "gaps": 0, "gap_at": None}

    def gap(self, g, n):
        self.s["gaps"] += 1
        self.s["gap_at"] = g
        if n is not None:
            self.s["run"] += n
            self.s["doubtful"] += n

    def output(self, k, t, ins):
        s = self.s
        x = ins["x"]
        if usable(x[0]):
            was = s["on"]
            if x[1] >= self.rise:
                s["on"] = True
            elif x[1] <= self.fall:
                s["on"] = False
            if s["on"] is not was:
                s["run"] = 0
                s["doubtful"] = 0
                s["gaps"] = 1 if s["gap_at"] == k else 0
        s["run"] += 1
        if x[0] != GOOD:
            s["doubtful"] += 1
        if not usable(x[0]):
            y = out(x[0])
        elif s["on"] is None:
            y = out(NR)
        else:
            y = out(x[0], s["on"])
        period = self.ctx.period
        return {
            "y": y,
            "elapsed": out(GOOD, s["run"] * period),
            "doubtful": out(GOOD, s["doubtful"] * period),
            "gaps": out(GOOD, float(s["gaps"])),
        }


class HeldFor(Block):
    SETTINGS = ("time", "on_bad", "hold_limit")

    def configure(self, in_map):
        self.in_ports["x"] = (BOOLEAN, True, True)
        self.out_ports["y"] = BOOLEAN
        self.out_ports["elapsed"] = NUMBER
        self.out_ports["doubtful"] = NUMBER
        self.out_ports["gaps"] = NUMBER
        self.n = s_counted(self, self.st, "time")
        self.on_bad = s_choice(self, self.st, "on_bad", ("reset", "hold"))
        if self.on_bad == "hold":
            self.limit = s_counted(self, self.st, "hold_limit")
        elif "hold_limit" in self.st:
            raise self.err("setting 'hold_limit' is refused without on_bad: hold")

    def reset(self):
        # doubtful: ticks since the timer started on which x was not good
        self.s = {"start": None, "m": 0, "doubtful": 0, "gaps": 0, "gap_at": None}

    def gap(self, g, n):
        s = self.s
        s["gap_at"] = g
        if s["start"] is None:
            return
        if n == 0:
            s["gaps"] += 1  # none passed over: nothing but one to gaps
            return
        if n is not None and self.on_bad == "hold" and s["m"] + n <= self.limit:
            # the unusable stretch grows by n, and the timer runs on
            s["m"] += n
            s["doubtful"] += n
            s["gaps"] += 1
            return
        s["start"] = None
        s["m"] = 0
        s["doubtful"] = 0

    def _counters(self, k, res):
        s = self.s
        period = self.ctx.period
        run = 0 if s["start"] is None else k - s["start"] + 1
        res["elapsed"] = out(GOOD, run * period)
        res["doubtful"] = out(GOOD, s["doubtful"] * period)
        res["gaps"] = out(GOOD, 0.0 if s["start"] is None else float(s["gaps"]))
        return res

    def output(self, k, t, ins):
        s = self.s
        x = ins["x"]
        if usable(x[0]):
            s["m"] = 0
            if not x[1]:
                s["start"] = None
                s["doubtful"] = 0
                return self._counters(k, {"y": out(x[0], False)})
            if s["start"] is None:
                s["start"] = k
                s["doubtful"] = 0
                s["gaps"] = 1 if s["gap_at"] == k else 0
            if x[0] != GOOD:
                s["doubtful"] += 1
            return self._counters(k, {"y": out(x[0], k - s["start"] > self.n)})
        if self.on_bad == "hold" and s["start"] is not None:
            s["m"] += 1
            if s["m"] <= self.limit:
                s["doubtful"] += 1
                return self._counters(k, {"y": out(UNC, k - s["start"] > self.n)})
        s["start"] = None
        s["m"] = 0
        s["doubtful"] = 0
        return self._counters(k, {"y": out(x[0])})


class SinceTrue(Block):
    SETTINGS = ("time", "on_bad")

    def configure(self, in_map):
        self.in_ports["x"] = (BOOLEAN, True, True)
        self.out_ports["y"] = BOOLEAN
        self.out_ports["elapsed"] = NUMBER
        self.out_ports["doubtful"] = NUMBER
        self.out_ports["gaps"] = NUMBER
        self.n = s_counted(self, self.st, "time")
        self.on_bad = s_choice(self, self.st, "on_bad", ("assume_false", "unknown"))

    def reset(self):
        # doubtful, gaps: counted since the clock was set
        # old: after a gap of no known length, the input was last true
        # longer ago than `time`, until the clock is next set
        self.s = {"clock": None, "doubtful": 0, "gaps": 0, "gap_at": None, "old": False}

    def gap(self, g, n):
        s = self.s
        s["gap_at"] = g
        if n is None:
            s["old"] = True
            s["clock"] = g  # its counts start again at the gap's tick
            s["doubtful"] = 0
            s["gaps"] = 1
        else:
            s["doubtful"] += n  # the clock is not set
            s["gaps"] += 1

    def output(self, k, t, ins):
        s = self.s
        x = ins["x"]
        if s["clock"] is None:
            s["clock"] = k
        if usable(x[0]) and x[1]:
            s["clock"] = k
            s["old"] = False
            s["doubtful"] = 0
            s["gaps"] = 1 if s["gap_at"] == k else 0
        if x[0] != GOOD:
            s["doubtful"] += 1
        period = self.ctx.period
        res = {
            "elapsed": out(GOOD, (k - s["clock"] + 1) * period),
            "doubtful": out(GOOD, s["doubtful"] * period),
            "gaps": out(GOOD, float(s["gaps"])),
        }
        value = s["old"] or (k - s["clock"]) > self.n
        if usable(x[0]):
            res["y"] = out(x[0], value)
        elif self.on_bad == "unknown":
            res["y"] = out(x[0])
        else:
            res["y"] = out(UNC, value)
        return res


class Latch(Block):
    def configure(self, in_map):
        self.in_ports["set"] = (BOOLEAN, True, True)
        self.in_ports["reset"] = (BOOLEAN, False, True)
        self.out_ports["y"] = BOOLEAN
        self.out_ports["elapsed"] = NUMBER
        self.out_ports["doubtful"] = NUMBER
        self.out_ports["gaps"] = NUMBER

    def reset(self):
        # run, doubtful, gaps: counted since it was last cleared
        self.s = {"set": False, "run": 0, "doubtful": 0, "gaps": 0, "gap_at": None}

    def gap(self, g, n):
        self.s["gaps"] += 1
        self.s["gap_at"] = g
        if n is not None:
            self.s["run"] += n
            if not self.s["set"]:
                self.s["doubtful"] += n

    def output(self, k, t, ins):
        s = self.s
        st_ = ins["set"]
        rs = ins.get("reset")
        was = s["set"]
        if rs is not None and usable(rs[0]) and rs[1]:
            s["set"] = False
            s["run"] = 0
            s["doubtful"] = 0
            s["gaps"] = 1 if s["gap_at"] == k else 0
            y = out(rs[0], False)
        elif s["set"]:
            y = out(GOOD, True)
        elif usable(st_[0]) and st_[1]:
            s["set"] = True
            y = out(st_[0], True)
        elif usable(st_[0]):
            y = out(st_[0], False)
        else:
            y = out(st_[0])
        s["run"] += 1
        if not was and st_[0] != GOOD:
            s["doubtful"] += 1
        period = self.ctx.period
        return {
            "y": y,
            "elapsed": out(GOOD, s["run"] * period),
            "doubtful": out(GOOD, s["doubtful"] * period),
            "gaps": out(GOOD, float(s["gaps"])),
        }


class Integrate(Block):
    SETTINGS = ("per", "max_missed")

    def configure(self, in_map):
        self.in_ports["x"] = (NUMBER, True, True)
        self.in_ports["reset"] = (BOOLEAN, False, True)
        for p in ("y", "missed", "doubtful", "elapsed", "gaps"):
            self.out_ports[p] = NUMBER
        self.per = s_length(self, self.st, "per", 1.0)
        if not self.per > 0:
            raise self.err("setting 'per' must be more than zero")
        self.max_missed = s_counted(self, self.st, "max_missed", None)

    def reset(self):
        # over: a gap of no known length, which is more than any max_missed
        self.s = {"total": 0.0, "run": 0, "missed": 0, "unc": 0, "gaps": 0, "gap_at": None, "over": False}

    def gap(self, g, n):
        self.s["gaps"] += 1
        self.s["gap_at"] = g
        if n is not None:
            self.s["run"] += n
            self.s["missed"] += n
        elif self.max_missed is not None:
            self.s["over"] = True

    def output(self, k, t, ins):
        s = self.s
        x = ins["x"]
        rs = ins.get("reset")
        reset_unc = False
        if rs is not None and usable(rs[0]) and rs[1]:
            gap_at = s["gap_at"]
            self.reset()
            s = self.s
            s["gap_at"] = gap_at
            s["gaps"] = 1 if gap_at == k else 0
            reset_unc = rs[0] == UNC
        s["run"] += 1
        if usable(x[0]):
            s["total"] += x[1] * self.ctx.period / self.per
            if x[0] == UNC:
                s["unc"] += 1
        else:
            s["missed"] += 1
        if s["over"] or (self.max_missed is not None and s["missed"] > self.max_missed):
            st = BAD
        elif x[0] == UNC or reset_unc:
            st = UNC
        else:
            st = GOOD
        period = self.ctx.period
        return {
            "y": out(st, s["total"]),
            "missed": out(GOOD, s["missed"] * period),
            "doubtful": out(GOOD, s["unc"] * period),
            "elapsed": out(GOOD, s["run"] * period),
            "gaps": out(GOOD, float(s["gaps"])),
        }


class Pid(Block):
    SETTINGS = ("kp", "ki", "kd", "filter", "min", "max", "applied_within")
    has_update = True

    def configure(self, in_map):
        self.in_ports["setpoint"] = (NUMBER, True, True)
        self.in_ports["measurement"] = (NUMBER, True, True)
        self.in_ports["reset"] = (BOOLEAN, False, True)
        self.in_ports["applied"] = (NUMBER, False, False)  # deferred
        self.out_ports["y"] = NUMBER
        self.out_ports["integral"] = NUMBER
        self.out_ports["limited"] = BOOLEAN
        for p in ("elapsed", "doubtful", "gaps"):
            self.out_ports[p] = NUMBER
        self.kp = s_num(self, self.st, "kp")
        self.ki = s_num(self, self.st, "ki", 0.0)
        self.kd = s_num(self, self.st, "kd", 0.0)
        if self.kd != 0:
            filt = s_length(self, self.st, "filter")
            if not filt > 0:
                raise self.err("setting 'filter' must be more than zero")
            self.a = math.exp(-self.ctx.period / filt)
        elif "filter" in self.st:
            raise self.err("setting 'filter' is refused without a 'kd' that is not zero")
        self.lo = s_num(self, self.st, "min", None)
        self.hi = s_num(self, self.st, "max", None)
        if self.lo is not None and self.hi is not None and not self.lo < self.hi:
            raise self.err("setting 'min' must be less than 'max'")
        self.within = s_num(self, self.st, "applied_within", 0.0)
        if self.within < 0:
            raise self.err("setting 'applied_within' must not be negative")

    def reset(self):
        # prev: the measurement of the tick before, or None where the
        # derivative is at its start; run, doubtful, gaps: since its last reset
        # made: this tick's addition, for `applied` in the second phase:
        # (the integral before it, the addition, y), or None
        self.s = {
            "integral": 0.0,
            "f": 0.0,
            "prev": None,
            "run": 0,
            "doubtful": 0,
            "gaps": 0,
            "gap_at": None,
            "made": None,
        }

    def gap(self, g, n):
        s = self.s
        s["gaps"] += 1
        s["gap_at"] = g
        if n == 0:
            return  # none passed over: nothing but one to gaps (rule 8.6)
        s["prev"] = None  # the derivative starts again (rule 7.7.7)
        if n is not None:
            s["run"] += n
            s["doubtful"] += n

    def output(self, k, t, ins):
        s = self.s
        sp = ins["setpoint"]
        me = ins["measurement"]
        rs = ins.get("reset")
        reset_unc = False
        if rs is not None and usable(rs[0]) and rs[1]:
            gap_at = s["gap_at"]
            self.reset()
            s = self.s
            s["gap_at"] = gap_at
            s["gaps"] = 1 if gap_at == k else 0
            reset_unc = rs[0] == UNC
        s["run"] += 1
        s["made"] = None
        if sp[0] != GOOD or me[0] != GOOD:
            s["doubtful"] += 1
        period = self.ctx.period
        res = {
            "elapsed": out(GOOD, s["run"] * period),
            "doubtful": out(GOOD, s["doubtful"] * period),
            "gaps": out(GOOD, float(s["gaps"])),
        }
        st = worst([sp[0], me[0]])
        if not usable(st):
            # a controller does not drive on a value it did not see. The
            # integral is kept, and the derivative starts again
            s["prev"] = None
            res["y"] = out(st)
            res["limited"] = out(st)
            res["integral"] = out(UNC if reset_unc else GOOD, s["integral"])
            return res
        error = sp[1] - me[1]
        # the derivative, of the measurement, through its filter
        derivative = 0.0
        if self.kd != 0:
            if s["prev"] is None:
                s["f"] = 0.0  # there is no tick before
            else:
                slope = (me[1] - s["prev"]) / period
                s["f"] = self.a * s["f"] + (1 - self.a) * slope
            derivative = -self.kd * s["f"]
        s["prev"] = me[1]
        # the integral: an addition that would put the output before
        # limiting past a limit is cut short (rule 7.7.6)
        add = self.ki * error * period
        before = s["integral"]
        raw = self.kp * error + (s["integral"] + add) + derivative
        cut = False
        if self.hi is not None and add > 0 and raw > self.hi:
            # what puts that output at max, or as it is if that is less;
            # and y is max
            cut = True
            at = self.hi - self.kp * error - derivative
            if at > s["integral"]:
                s["integral"] = at
            raw = self.hi
        elif self.lo is not None and add < 0 and raw < self.lo:
            cut = True
            at = self.lo - self.kp * error - derivative
            if at < s["integral"]:
                s["integral"] = at
            raw = self.lo
        else:
            s["integral"] += add
            raw = self.kp * error + s["integral"] + derivative
        y = raw
        limited = cut
        if self.hi is not None and raw > self.hi:
            y, limited = self.hi, True
        if self.lo is not None and raw < self.lo:
            y, limited = self.lo, True
        if reset_unc:
            st = UNC
        res["y"] = out(st, y)
        res["limited"] = out(st, limited)
        res["integral"] = out(st, s["integral"])
        s["made"] = (before, add, y)
        return res

    def update(self, k, t, ins):
        # what was applied (rule 7.7.12): where it fell short of y the way
        # the addition went, the addition is taken back
        s = self.s
        made = s["made"]
        s["made"] = None
        ap = ins.get("applied")
        if made is None or ap is None or not usable(ap[0]):
            return
        before, add, y = made
        if not math.isfinite(y):
            return
        # less than y, or more, by more than `applied_within`
        if (add > 0 and y - ap[1] > self.within) or (add < 0 and ap[1] - y > self.within):
            s["integral"] = before


# ------------------------------------------------------------------ models
#
# Every model is linear and is stepped exactly (rule 7.8.7):
# x' = Ad.x + Bd.u, y = C.x + D.u. For a model in continuous time Ad and Bd
# are worked out here, once, when the graph is compiled.

_EXP_DIGITS = 100  # decimal digits carried while a matrix exponential is worked out
_DOUBLE_MAX = 1.7976931348623157e308  # the largest double
_FASTEST = 100000  # the most a row of A, summed, times the period may be


def _expm(m):
    """exp(m) for a square matrix of Decimals: the series for m / 2**s,
    with s such that the scaled matrix is small, squared s times."""
    n = len(m)
    zero = decimal.Decimal(0)

    def mul(p, q):
        return [[sum((p[i][k] * q[k][j] for k in range(n)), zero) for j in range(n)] for i in range(n)]

    norm = max(sum((abs(v) for v in row), zero) for row in m)
    s = 0
    while norm > decimal.Decimal("0.5"):
        norm /= 2
        s += 1
    scaled = [[v / (2**s) for v in row] for row in m]
    res = [[decimal.Decimal(int(i == j)) for j in range(n)] for i in range(n)]
    term = [list(row) for row in res]
    tiny = decimal.Decimal(10) ** -(_EXP_DIGITS + 5)
    k = 0
    while True:
        k += 1
        term = [[v / k for v in row] for row in mul(term, scaled)]
        res = [[res[i][j] + term[i][j] for j in range(n)] for i in range(n)]
        if max(abs(v) for row in term for v in row) < tiny:
            break
    for _ in range(s):
        res = mul(res, res)
    return res


def _discretize(a, b, period_ns):
    """Ad = exp(A.period), and Bd, the integral of exp(A.s) for s from
    zero to the period, times B, as floats. With T the period, the
    exponential of [[A.T, 1], [0, 0]] is [[Ad, G], [0, 1]], where G is the
    integral of exp(A.T.s) for s from zero to one; Bd is T.G.B. B is kept
    out of the exponential, so that its size does not touch Ad."""
    n = len(a)
    m = len(b[0]) if b else 0
    zero = decimal.Decimal(0)
    with decimal.localcontext() as ctx:
        ctx.prec = _EXP_DIGITS
        period = decimal.Decimal(period_ns) / decimal.Decimal(_NS)
        big = []
        for i in range(n):
            big.append([decimal.Decimal(v) * period for v in a[i]] + [decimal.Decimal(int(i == j)) for j in range(n)])
        for _ in range(n):
            big.append([zero] * (2 * n))
        e = _expm(big)
        ad = [[e[i][j] for j in range(n)] for i in range(n)]
        bd = [
            [period * sum((e[i][n + k] * decimal.Decimal(b[k][j]) for k in range(n)), zero) for j in range(m)]
            for i in range(n)
        ]
        # an entry that is more than a double holds (rule 7.8.7)
        most = decimal.Decimal(_DOUBLE_MAX)
        if any(abs(v) > most for row in ad + bd for v in row):
            return None, None
        ad = [[float(v) for v in row] for row in ad]
        bd = [[float(v) for v in row] for row in bd]
    return ad, bd


def _fastness(a, period):
    """The largest sum of the absolute values along a row of A, times the
    period in seconds, in double arithmetic (rule 7.8.7): each row summed
    from its first entry to its last."""
    most = 0.0
    for row in a:
        acc = 0.0
        for v in row:
            acc += abs(v)
        most = max(most, acc)
    return most * period


def _slowest(a, det):
    """The slowest time constant of a model of one or two states: minus
    one over the largest real part among the eigenvalues of A, or None
    where a state does not decay. det is A's determinant for two states,
    as the model's entry gives it from its settings (rule 7.8.6)."""
    if len(a) == 1:
        top = a[0][0]
    else:
        # h, half the sum of the diagonal
        half = (a[0][0] + a[1][1]) / 2
        if half * half <= det:
            top = half  # a pair of complex eigenvalues, or two the same
        elif half < 0:
            # that way round, so that a slow rate beside a fast one is not
            # lost in the subtraction
            top = det / (half - math.sqrt(half * half - det))
        else:
            top = half + math.sqrt(half * half - det)  # not less than zero
    if not top < 0:
        return None
    return -1.0 / top


class Model:
    """A state, a step over one period and the outputs (rule 4.9)."""

    def __init__(self, inputs, states, outputs, ad, bd, c, d, x0, tau):
        self.inputs = tuple(inputs)
        self.states = tuple(states)
        self.outputs = tuple(outputs)
        self.ad = ad  # also the sensitivity of the stepped state (rule 4.9)
        self.bd = bd
        self.c = c
        self.d = d
        self.x0 = x0
        self.tau = tau  # the slowest time constant, in seconds, or None
        self.a = None  # A, for a model in continuous time
        # an input is direct if any output reads it (rule 7.8.2)
        self.direct = set(name for j, name in enumerate(self.inputs) if any(row[j] != 0 for row in d))

    def initial(self):
        return list(self.x0)

    def step(self, x, u):
        res = []
        for i in range(len(x)):
            acc = 0.0
            for j in range(len(x)):
                acc += self.ad[i][j] * x[j]
            for j, name in enumerate(self.inputs):
                acc += self.bd[i][j] * u[name]
            res.append(acc)
        return res

    def out(self, x, u):
        res = {}
        for i, port in enumerate(self.outputs):
            acc = 0.0
            for j in range(len(x)):
                acc += self.c[i][j] * x[j]
            for j, name in enumerate(self.inputs):
                if name in self.direct:
                    acc += self.d[i][j] * u[name]
            res[port] = acc
        return res


def _continuous(b, inputs, states, outputs, a, bm, c, x0, d=None, named=True, det=None):
    """A model in continuous time: dx/dt = A.x + B.u, y = C.x + D.u."""
    if d is None:
        d = [[0.0] * len(inputs) for _ in outputs]
    if _fastness(a, b.ctx.period) > _FASTEST:
        raise b.err(
            "the model is too fast for the period: the largest sum of the absolute values along "
            "a row of A, times the period, is more than %d" % _FASTEST
        )
    ad, bd = _discretize(a, bm, b.ctx.period_ns)
    if ad is None:
        # it grows too fast for the graph's period (rule 7.8.7)
        raise b.err("the model grows so fast that its step over one period is more than a double holds")
    model = Model(inputs, states, outputs, ad, bd, c, d, x0, _slowest(a, det) if named else None)
    model.a = a
    return model


def s_matrix(b, st, key, rows, cols, default=REQ):
    """A list of rows of finite numbers. rows or cols may be None: any."""
    if key not in st:
        if default is REQ:
            raise b.err("missing required setting %r" % key)
        return default
    v = st[key]
    if not isinstance(v, list) or (rows is not None and len(v) != rows):
        raise b.err("setting %r must be a list of %s rows" % (key, "its" if rows is None else rows))
    res = []
    for row in v:
        if not isinstance(row, list):
            raise b.err("setting %r must be a list of rows of numbers" % key)
        if cols is None:
            cols = len(row)
        if len(row) != cols:
            raise b.err("setting %r: a row must hold %d numbers" % (key, cols))
        r = []
        for e in row:
            f = _finite(e)
            if f is None:
                raise b.err("setting %r must hold finite numbers" % key)
            r.append(f)
        res.append(r)
    return res


def s_vector(b, st, key, n, default=REQ):
    if key not in st:
        if default is REQ:
            raise b.err("missing required setting %r" % key)
        return default
    v = st[key]
    if not isinstance(v, list) or len(v) != n:
        raise b.err("setting %r must be a list of %d numbers" % (key, n))
    res = []
    for e in v:
        f = _finite(e)
        if f is None:
            raise b.err("setting %r must hold finite numbers" % key)
        res.append(f)
    return res


def s_names(b, st, key, n, stem, single):
    """A list of n distinct names; left out, `single` for one and
    stem0, stem1 and so on for several."""
    if key not in st:
        return [single] if n == 1 else ["%s%d" % (stem, i) for i in range(n)]
    v = st[key]
    if not isinstance(v, list) or len(v) != n or not all(isinstance(e, str) for e in v):
        raise b.err("setting %r must be a list of %d names" % (key, n))
    if len(set(v)) != n:
        raise b.err("setting %r: the names must be distinct" % key)
    for e in v:
        if e == "" or "." in e:
            raise b.err("setting %r: a name is not empty and holds no dot, got %r" % (key, e))
    return list(v)


def s_range(b, st, key, default=REQ, positive=False, not_negative=False):
    v = s_num(b, st, key, default)
    if positive and not v > 0:
        raise b.err("setting %r must be more than zero" % key)
    if not_negative and v < 0:
        raise b.err("setting %r must not be negative" % key)
    return v


_MODEL_OUTPUTS = ("elapsed", "doubtful", "gaps")


def _linear(b, st):
    a = s_matrix(b, st, "A", None, None)
    n = len(a)
    if n < 1 or any(len(row) != n for row in a):
        raise b.err("setting 'A' must be a list of n rows of n numbers")
    bm = s_matrix(b, st, "B", n, None)
    m = len(bm[0])
    c = s_matrix(b, st, "C", None, n)
    p = len(c)
    if m < 1 or p < 1:
        raise b.err("a linear model has at least one input and one output")
    d = s_matrix(b, st, "D", p, m, [[0.0] * m for _ in range(p)])
    x0 = s_vector(b, st, "initial", n, [0.0] * n)
    inputs = s_names(b, st, "inputs", m, "u", "u")
    states = s_names(b, st, "states", n, "x", "x0")
    outputs = s_names(b, st, "outputs", p, "y", "y")
    for name in outputs:
        if name in _MODEL_OUTPUTS:
            raise b.err("setting 'outputs': %r is the name of a model output" % name)
    return _continuous(b, inputs, states, outputs, a, bm, c, x0, d, named=False)


def _thermal_mass(b, st):
    cap = s_range(b, st, "thermal_mass", positive=True)
    h = s_range(b, st, "heat_transfer", positive=True)
    t0 = s_num(b, st, "initial")
    return _continuous(b, ("power", "ambient"), ("temp",), ("temp",), [[-h / cap]], [[1 / cap, h / cap]], [[1.0]], [t0])


def _thermal_rc2(b, st):
    ca = s_range(b, st, "thermal_mass_a", positive=True)
    cb = s_range(b, st, "thermal_mass_b", positive=True)
    ha = s_range(b, st, "heat_transfer_a", not_negative=True)
    hb = s_range(b, st, "heat_transfer_b", not_negative=True)
    k = s_range(b, st, "coupling", not_negative=True)
    x0 = [s_num(b, st, "initial_a"), s_num(b, st, "initial_b")]
    a = [[-(ha + k) / ca, k / ca], [k / cb, -(hb + k) / cb]]
    bm = [[1 / ca, ha / ca], [0.0, hb / cb]]
    names = ("temp_a", "temp_b")
    det = (ha * hb + k * (ha + hb)) / (ca * cb)
    return _continuous(b, ("power", "ambient"), names, names, a, bm, [[1.0, 0.0], [0.0, 1.0]], x0, det=det)


def _first_order_process(b, st):
    tau = s_length(b, st, "tau")
    if not tau > 0:
        raise b.err("setting 'tau' must be more than zero")
    gain = s_num(b, st, "gain", 1.0)
    y0 = s_num(b, st, "initial", 0.0)
    return _continuous(b, ("u",), ("y",), ("y",), [[-1 / tau]], [[gain / tau]], [[1.0]], [y0])


def _second_order_process(b, st):
    wn = s_range(b, st, "omega_n", positive=True)
    zeta = s_range(b, st, "zeta", not_negative=True)
    gain = s_num(b, st, "gain", 1.0)
    x0 = [s_num(b, st, "initial", 0.0), s_num(b, st, "initial_rate", 0.0)]
    a = [[0.0, 1.0], [-wn * wn, -2 * zeta * wn]]
    names = ("y", "rate")
    return _continuous(b, ("u",), names, names, a, [[0.0], [wn * wn * gain]], [[1.0, 0.0], [0.0, 1.0]], x0, det=wn * wn)


def _mass_spring_damper(b, st):
    mass = s_range(b, st, "mass", positive=True)
    damping = s_range(b, st, "damping", not_negative=True)
    stiffness = s_range(b, st, "stiffness", not_negative=True)
    x0 = [s_num(b, st, "initial_position", 0.0), s_num(b, st, "initial_velocity", 0.0)]
    a = [[0.0, 1.0], [-stiffness / mass, -damping / mass]]
    names = ("position", "velocity")
    return _continuous(
        b, ("force",), names, names, a, [[0.0], [1 / mass]], [[1.0, 0.0], [0.0, 1.0]], x0, det=stiffness / mass
    )


def _dc_motor(b, st):
    r = s_range(b, st, "resistance", not_negative=True)
    ind = s_range(b, st, "inductance", positive=True)
    # not negative, so that nothing in the determinant is subtracted
    ke = s_range(b, st, "back_emf", not_negative=True)
    kt = s_range(b, st, "torque_constant", not_negative=True)
    inertia = s_range(b, st, "inertia", positive=True)
    friction = s_range(b, st, "friction", not_negative=True)
    x0 = [s_num(b, st, "initial_current", 0.0), s_num(b, st, "initial_speed", 0.0)]
    a = [[-r / ind, -ke / ind], [kt / inertia, -friction / inertia]]
    bm = [[1 / ind, 0.0], [0.0, -1 / inertia]]
    c = [[0.0, 1.0], [1.0, 0.0], [kt, 0.0]]
    det = (r * friction + ke * kt) / (ind * inertia)
    return _continuous(
        b, ("voltage", "load_torque"), ("current", "speed"), ("speed", "current", "torque"), a, bm, c, x0, det=det
    )


def _state_space(b, st):
    """In discrete time: Ad and Bd themselves, at whatever period."""
    a = s_matrix(b, st, "A", None, None)
    n = len(a)
    if n < 1 or any(len(row) != n for row in a):
        raise b.err("setting 'A' must be a list of n rows of n numbers")
    bd = [[v] for v in s_vector(b, st, "B", n)]
    c = [s_vector(b, st, "C", n)]
    d = [[s_num(b, st, "D", 0.0)]]
    x0 = s_vector(b, st, "initial", n, [0.0] * n)
    return Model(("u",), ["x%d" % i for i in range(n)], ("y",), a, bd, c, d, x0, None)


# type -> (the model's own settings, what builds it)
MODELS = {
    "linear": (("A", "B", "C", "D", "initial", "inputs", "states", "outputs"), _linear),
    "thermal_mass": (("thermal_mass", "heat_transfer", "initial"), _thermal_mass),
    "thermal_rc2": (
        (
            "thermal_mass_a",
            "thermal_mass_b",
            "heat_transfer_a",
            "heat_transfer_b",
            "coupling",
            "initial_a",
            "initial_b",
        ),
        _thermal_rc2,
    ),
    "first_order_process": (("tau", "gain", "initial"), _first_order_process),
    "second_order_process": (("omega_n", "zeta", "gain", "initial", "initial_rate"), _second_order_process),
    "mass_spring_damper": (
        ("mass", "damping", "stiffness", "initial_position", "initial_velocity"),
        _mass_spring_damper,
    ),
    "dc_motor": (
        (
            "resistance",
            "inductance",
            "back_emf",
            "torque_constant",
            "inertia",
            "friction",
            "initial_current",
            "initial_speed",
        ),
        _dc_motor,
    ),
    "state_space": (("A", "B", "C", "D", "initial"), _state_space),
}


class ModelBlock(Block):
    MODEL = None  # the model's type
    has_update = True

    def configure(self, in_map):
        keys, build = MODELS[self.MODEL]
        self.model = build(self, {k: v for k, v in self.st.items() if k in keys})
        self.rt = s_counted(self, self.st, "ride_through", 0)
        self.settle = s_counted(self, self.st, "settle", None)
        if self.settle is None and self.model.tau is not None:
            # three of its slowest time constant (rule 7.8.6)
            self.settle = settle_of(self.model.tau, self.ctx.period)
        for name in self.model.inputs:
            self.in_ports[name] = (NUMBER, True, name in self.model.direct)
        for name in self.model.outputs:
            self.out_ports[name] = NUMBER
        self.out_ports["elapsed"] = NUMBER
        self.out_ports["doubtful"] = NUMBER
        self.out_ports["gaps"] = NUMBER

    def reset(self):
        self.s = {
            "gaps": 0,
            "x": self.model.initial(),
            "last": {n: None for n in self.model.inputs},
            "m": {n: 0 for n in self.model.inputs},
            "doubt": None,
            "run": 0,  # ticks since the first, the present one counted
            "doubtful": 0,  # ticks whose step was a doubt
        }

    def gap(self, g, n):
        s = self.s
        s["gaps"] += 1
        if n == 0:
            return  # none passed over: nothing but one to gaps
        # the tick before the one that runs is a doubt (rule 8.6)
        s["doubt"] = _later(s["doubt"], g - 1)
        if n is None:
            for name in self.model.inputs:
                s["m"][name] = self.rt + 1  # it does not ride through (rule 7.8.4)
            return
        # for each tick passed over, in order: a step on the last usable
        # value of every input while each is within ride_through, and no
        # step from the first tick where one is not (rule 8.6)
        # (the result of those steps, and not that each tick is gone through)
        steps = 0
        if all(v is not None for v in s["last"].values()):
            steps = max(0, min(n, self.rt - max(s["m"].values())))
        for _ in range(steps):
            self._step(s["last"])
        for name in self.model.inputs:
            s["m"][name] += n
        s["run"] += n
        s["doubtful"] += n

    def _step(self, u):
        self.s["x"] = self.model.step(self.s["x"], u)

    def output(self, k, t, ins):
        s = self.s
        u = {}
        doubtful_direct = False
        for name in self.model.direct:
            sg = ins[name]
            if usable(sg[0]):
                u[name] = sg[1]
                if sg[0] == UNC:
                    doubtful_direct = True
            else:
                doubtful_direct = True
                last = s["last"][name]
                u[name] = 0.0 if last is None else last
        vals = self.model.out(s["x"], u)
        if self.loop is not None:
            # the loop's doubt, in place of its own (rule 7.8.8)
            within = self.loop.within(k)
        else:
            d = s["doubt"]
            within = self.settle is not None and d is not None and k - d <= self.settle
        st = UNC if (doubtful_direct or within) else GOOD
        res = {p: out(st, v) for p, v in vals.items()}
        s["run"] += 1
        res["elapsed"] = out(GOOD, s["run"] * self.ctx.period)
        res["doubtful"] = out(GOOD, s["doubtful"] * self.ctx.period)
        res["gaps"] = out(GOOD, float(s["gaps"]))
        return res

    def update(self, k, t, ins):
        s = self.s
        u = {}
        can_step = True
        doubt = False  # it steps on an uncertain or a held value
        for name in self.model.inputs:
            sg = ins[name]
            if usable(sg[0]):
                u[name] = sg[1]
                s["last"][name] = sg[1]
                s["m"][name] = 0
                if sg[0] == UNC:
                    doubt = True
            else:
                s["m"][name] += 1
                if s["last"][name] is not None and s["m"][name] <= self.rt:
                    u[name] = s["last"][name]
                    doubt = True
                else:
                    can_step = False
        if can_step:
            self._step(u)
        if doubt or not can_step:
            s["doubt"] = k
            s["doubtful"] += 1


def _model_block(model_type):
    """The block type that hosts one type of model."""
    return type(
        "ModelBlock_" + model_type,
        (ModelBlock,),
        {"MODEL": model_type, "SETTINGS": MODELS[model_type][0] + ("ride_through", "settle")},
    )


def _noise(a, q, period_ns):
    """What process noise has added by the end of one step (rule 7.9.2):
    the integral of exp(A.s).Q.exp(A'.s) for s from zero to the period,
    with Q the q's on its diagonal, as floats; or None where an entry is
    more than a double holds.

    N(t), that integral up to t, obeys dN/dt = A.N + N.A' + Q from N = 0.
    With N's entries in one column, row by row, that is a linear model
    dv/dt = K.v + (Q's entries) with K = A (x) 1 + 1 (x) A, and it is
    stepped exactly as a model is (_discretize): the integral of exp(K.s)
    over the period, times Q's entries."""
    n = len(a)
    k = [[0.0] * (n * n) for _ in range(n * n)]
    for i in range(n):
        for j in range(n):
            for m in range(n):
                k[i * n + j][m * n + j] += a[i][m]  # A.N
                k[i * n + j][i * n + m] += a[j][m]  # N.A'
    forcing = [[q[i] if i == j else 0.0] for i in range(n) for j in range(n)]
    _kd, nd = _discretize(k, forcing, period_ns)
    if nd is None:
        return None
    res = [[nd[i * n + j][0] for j in range(n)] for i in range(n)]
    # it is symmetric: let rounding not say otherwise
    for i in range(n):
        for j in range(i):
            res[i][j] = res[j][i] = (res[i][j] + res[j][i]) / 2
    return res


class Estimator(Block):
    SETTINGS = ("model", "q", "p0", "measure", "consistency", "gate", "max_refused", "sigma_max")
    has_update = True

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
        keys, build = MODELS[m["type"]]
        mst = {}
        for key, v in m.items():
            if key == "type":
                continue
            if key not in keys:
                raise self.err("setting 'model': unknown setting %r" % (key,))
            mst[key] = v
        self.model = build(self, mst)
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
        # N, what process noise adds over one step (rule 7.9.2)
        if self.model.a is None:
            # in discrete time: q times the period on each state's own variance
            period = self.ctx.period
            self.noise = [
                [self.q[i] * period if i == j else 0.0 for j in range(len(states))] for i in range(len(states))
            ]
        else:
            self.noise = _noise(self.model.a, self.q, self.ctx.period_ns)
            if self.noise is None:
                raise self.err(
                    "the model grows so fast that its process noise over one period is more than a double holds"
                )
        smax = self._state_map("sigma_max", False)
        for name, v in smax.items():
            if v < 0:
                raise self.err("setting 'sigma_max' for %r must not be negative" % name)
        self.sigma_max = [smax.get(n) for n in states]
        self.gate = s_num(self, self.st, "gate", None)
        if self.gate is not None and self.gate < 0:
            raise self.err("setting 'gate' must not be negative")
        if self.gate is None:
            if "max_refused" in self.st:
                raise self.err("setting 'max_refused' is refused without 'gate'")
            self.max_refused = None
        else:
            self.max_refused = s_whole(self, self.st, "max_refused")
            if self.max_refused < 0:
                raise self.err("setting 'max_refused' must not be negative")
        if "consistency" not in self.st:
            raise self.err("missing required setting 'consistency'")
        cons = self.st["consistency"]
        if isinstance(cons, str) and cons == "none":
            self.over = None
            self.limit = None
        elif isinstance(cons, dict):
            for key in cons:
                if key not in ("over", "limit"):
                    raise self.err("setting 'consistency' has an unknown key %r" % (key,))
            self.over = s_whole(self, cons, "over")
            if self.over < 1:
                raise self.err("setting 'consistency': 'over' must be at least 1")
            self.limit = s_num(self, cons, "limit")
            if not self.limit > 0:
                raise self.err("setting 'consistency': 'limit' must be more than zero")
        else:
            raise self.err("setting 'consistency' must be none, or a map with 'over' and 'limit'")
        if "measure" not in self.st:
            raise self.err("missing required setting 'measure'")
        meas = self.st["measure"]
        if not isinstance(meas, dict):
            raise self.err("setting 'measure' must be a map")
        if not meas:
            raise self.err("setting 'measure' must have at least one port")
        for name in self.model.inputs:
            self.in_ports[name] = (NUMBER, True, False)  # deferred
        for name in states:
            self.out_ports[name] = NUMBER
        for name in states:
            self._add_out("sigma_" + name)
        self.measures = []  # (port, the output's row of C, r, r_uncertain or None)
        for port, spec in meas.items():
            if not isinstance(port, str):
                raise self.err("setting 'measure': a port's name is text, got %r" % (port,))
            if port == "" or "." in port:
                raise self.err("setting 'measure': a port's name is not empty and holds no dot, got %r" % (port,))
            if port in self.in_ports:
                raise self.err("setting 'measure': port %r is named twice or is one of the model's inputs" % port)
            if not isinstance(spec, dict):
                raise self.err("setting 'measure': port %r needs 'of' and 'r'" % port)
            for key in spec:
                if key not in ("of", "r", "r_uncertain"):
                    raise self.err("setting 'measure': port %r has an unknown key %r" % (port, key))
            if "of" not in spec or spec["of"] not in self.model.outputs:
                raise self.err("setting 'measure': port %r must name an output of the model in 'of'" % port)
            row = self.model.outputs.index(spec["of"])
            if any(v != 0 for v in self.model.d[row]):
                raise self.err("setting 'measure': port %r is of an output that reads an input directly" % port)
            r = _finite(spec.get("r"))
            if r is None or not r > 0:
                raise self.err("setting 'measure': port %r needs an 'r' more than zero" % port)
            ru = None
            if "r_uncertain" in spec:
                ru = _finite(spec["r_uncertain"])
                if ru is None or ru < r:
                    raise self.err("setting 'measure': port %r needs an 'r_uncertain' not less than 'r'" % port)
            self.in_ports[port] = (NUMBER, True, True)
            self.measures.append((port, list(self.model.c[row]), r, ru))
        for port, _c, _r, _ru in self.measures:
            self._add_out("innovation_" + port)
            self._add_out("nis_" + port)
            self._add_out("refused_" + port)
            self._add_out("since_" + port)
        self.rebased = False  # between rebase() and the gap() that follows it

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
            "run": {m[0]: 0 for m in self.measures},  # refused in a row
            "nis": {m[0]: [] for m in self.measures},  # of its last `over` considered
            "used": {m[0]: None for m in self.measures},
            "doubt": False,  # a model input was uncertain or unusable at the tick before
            "gap": False,  # the next tick is one a gap runs, with a tick passed over
            "lost": False,  # a gap of no known length, and no measurement used since
        }

    def _predict(self):
        """Rule 7.9.2. Whether the state was stepped."""
        s = self.s
        n = len(self.model.states)
        p = s["p"]
        stepped = all(v is not None for v in s["last"].values())
        if stepped:
            f = self.model.ad
            s["x"] = self.model.step(s["x"], s["last"])
            fp = [[sum(f[i][m] * p[m][j] for m in range(n)) for j in range(n)] for i in range(n)]
            p = [[sum(fp[i][m] * f[j][m] for m in range(n)) for j in range(n)] for i in range(n)]
        s["p"] = [[p[i][j] + self.noise[i][j] for j in range(n)] for i in range(n)]
        return stepped

    def _predict_many(self, count):
        """The result of `count` predictions on the model inputs it last
        had (rule 7.9.9). A few are made one by one. Many are compounded:
        one prediction is x -> F.x + g, P -> F.P.F' + M, and two of those
        one after the other are another of the same form, so `count` of
        them are reached by squaring."""
        if count <= 32:
            for _ in range(count):
                self._predict()
            return
        s = self.s
        n = len(self.model.states)

        def mul(a, b):
            return [[sum(a[i][k] * b[k][j] for k in range(n)) for j in range(n)] for i in range(n)]

        def then(first, second):
            f1, g1, m1 = first
            f2, g2, m2 = second
            fm = mul(f2, m1)
            m = [[sum(fm[i][k] * f2[j][k] for k in range(n)) + m2[i][j] for j in range(n)] for i in range(n)]
            g = [sum(f2[i][k] * g1[k] for k in range(n)) + g2[i] for i in range(n)]
            return (mul(f2, f1), g, m)

        if all(v is not None for v in s["last"].values()):
            one = (self.model.ad, self.model.step([0.0] * n, s["last"]), self.noise)
        else:
            # the state stays, and the covariance takes N
            one = ([[float(i == j) for j in range(n)] for i in range(n)], [0.0] * n, self.noise)
        total = None
        while count:
            if count & 1:
                total = one if total is None else then(total, one)
            one = then(one, one)
            count >>= 1
        f, g, m = total
        s["x"] = [sum(f[i][k] * s["x"][k] for k in range(n)) + g[i] for i in range(n)]
        fp = mul(f, s["p"])
        s["p"] = [[sum(fp[i][k] * f[j][k] for k in range(n)) + m[i][j] for j in range(n)] for i in range(n)]

    def _grow(self):
        for i in range(len(self.p0)):
            self.s["p"][i][i] += self.p0[i]

    def gap(self, g, n):
        # told n: it predicts n times more, on the model inputs it last had
        self._predict_many(n or 0)
        # told nobody knows, and at a rebase whatever its length: by p0
        if n is None or self.rebased:
            self._grow()
        self.rebased = False
        if n is None:
            self.s["lost"] = True  # it does not know where it is until a measurement tells it
        if n != 0:
            self.s["gap"] = True

    def rebase(self):
        for port in self.s["considered"]:
            self.s["considered"][port] = None
            self.s["used"][port] = None
        self.rebased = True

    def output(self, k, t, ins):
        s = self.s
        n = len(self.model.states)
        # rule 7: what makes this tick's outputs uncertain
        doubt = s["gap"]
        s["gap"] = False
        # predict, on the model inputs as they were at the tick before
        if k != 0:
            stepped = self._predict()
            if s["doubt"] or not stepped:
                doubt = True
        # correct
        res = {}
        x = s["x"]
        p = s["p"]
        for port, c, r, ru in self.measures:
            sg = ins[port]
            last = s["considered"][port]
            ok = sg[0] == GOOD or (sg[0] == UNC and ru is not None)
            if ok and sg[2] is not None and (last is None or sg[2] > last):
                s["considered"][port] = sg[2]
                v = r if sg[0] == GOOD else ru
                innovation = sg[1] - sum(c[j] * x[j] for j in range(n))
                pc = [sum(p[i][j] * c[j] for j in range(n)) for i in range(n)]  # P.c'
                spread = sum(c[i] * pc[i] for i in range(n)) + v
                nis = innovation * innovation / spread
                if self.over is not None:
                    s["nis"][port] = (s["nis"][port] + [nis])[-self.over :]
                root = math.sqrt(spread) if spread >= 0 else float("nan")
                use = True
                if self.gate is not None and abs(innovation) > self.gate * root:
                    if s["run"][port] >= self.max_refused:
                        # one more than the most it refuses in a row: it
                        # has disagreed for too long to be an outlier. It
                        # gives in, and the tick is uncertain (rule 7.9.7)
                        self._grow()
                        pc = [sum(p[i][j] * c[j] for j in range(n)) for i in range(n)]
                        spread = sum(c[i] * pc[i] for i in range(n)) + v
                        doubt = True
                    else:
                        use = False
                if use:
                    g = [pc[i] / spread for i in range(n)]
                    for i in range(n):
                        x[i] += g[i] * innovation
                    # P = (1 - g.c).P.(1 - g.c)' + g.v.g': the form that
                    # rounding cannot bring to nothing (rule 7.9.4)
                    w = [[float(i == j) - g[i] * c[j] for j in range(n)] for i in range(n)]
                    wp = [[sum(w[i][m] * p[m][j] for m in range(n)) for j in range(n)] for i in range(n)]
                    for i in range(n):
                        for j in range(n):
                            p[i][j] = sum(wp[i][m] * w[j][m] for m in range(n)) + g[i] * v * g[j]
                    s["used"][port] = sg[2]
                    s["run"][port] = 0
                    s["lost"] = False
                    if sg[0] == UNC:
                        doubt = True
                else:
                    s["refused"][port] += 1
                    s["run"][port] += 1
                    doubt = True
                res["innovation_" + port] = out(GOOD, innovation)
                res["nis_" + port] = out(GOOD, nis)
            else:
                res["innovation_" + port] = out(NR)
                res["nis_" + port] = out(NR)
            res["refused_" + port] = out(GOOD, float(s["refused"][port]))
            if s["used"][port] is None:
                res["since_" + port] = out(NR)
            else:
                res["since_" + port] = out(GOOD, max(0, t - s["used"][port]) / 1e9)
        if self.over is not None:
            for port, _c, _r, _ru in self.measures:
                kept = s["nis"][port]
                if len(kept) == self.over and sum(kept) / self.over > self.limit:
                    doubt = True  # the port is inconsistent
        if s["lost"]:
            doubt = True
        for i, name in enumerate(self.model.states):
            var = p[i][i]
            sigma = math.sqrt(var) if var >= 0 else float("nan")
            st = UNC if doubt else GOOD
            if self.sigma_max[i] is not None and sigma > self.sigma_max[i]:
                st = UNC
            res[name] = out(st, x[i])
            res["sigma_" + name] = out(st, sigma)
        return res

    def update(self, k, t, ins):
        # the model inputs are deferred: the step to the next tick is on
        # them as they are at this one
        s = self.s
        s["doubt"] = False
        for name in self.model.inputs:
            sg = ins[name]
            if usable(sg[0]):
                s["last"][name] = sg[1]
            if sg[0] != GOOD:
                s["doubt"] = True


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
    "rate_limit": RateLimit,
    "pid": Pid,
    "estimator": Estimator,
}
for _model_type in MODELS:
    BLOCK_TYPES[_model_type] = _model_block(_model_type)


# ------------------------------------------------------------------ engine


class _Ctx:
    def __init__(self, period_ns):
        self.period_ns = period_ns  # the period, in nanoseconds
        self.period = float(Fraction(period_ns, _NS))  # and in seconds


class _Input:
    def __init__(self, type_, max_age, max_ahead, has_initial, initial):
        self.type = type_
        self.max_age = max_age  # nanoseconds, or None for `none`
        self.max_ahead = max_ahead  # nanoseconds
        self.has_initial = has_initial
        self.initial = initial


def _const_type(v):
    return BOOLEAN if isinstance(v, bool) else NUMBER


class Engine:
    def __init__(self, graph):
        if not isinstance(graph, dict):
            raise CompileError("the graph must be a map")
        for key in graph:
            if key not in ("period", "max_catch_up", "max_waiting", "inputs", "blocks"):
                raise CompileError("unknown key %r at the top of the graph" % (key,))
        if "period" not in graph:
            raise CompileError("the graph has no 'period'")
        period_ns = parse_duration("period", graph["period"])
        if period_ns <= 0:
            raise CompileError("period: must be more than zero")
        self._ctx = _Ctx(period_ns)
        self._period_ns = period_ns
        self._max_catch_up = graph.get("max_catch_up", 100)
        if not isinstance(self._max_catch_up, int) or isinstance(self._max_catch_up, bool) or self._max_catch_up < 1:
            raise CompileError("max_catch_up: must be a whole number, at least 1")
        if self._max_catch_up > _INT32_MAX:
            raise CompileError("max_catch_up: must be at most %d" % _INT32_MAX)
        self._max_waiting = graph.get("max_waiting", 1024)
        if not isinstance(self._max_waiting, int) or isinstance(self._max_waiting, bool) or self._max_waiting < 1:
            raise CompileError("max_waiting: must be a whole number, at least 1")
        if self._max_waiting > _INT32_MAX:
            raise CompileError("max_waiting: must be at most %d" % _INT32_MAX)
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
            if name == "":
                raise CompileError("%s: the name of an input is not empty" % what)
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
                max_age = parse_duration(what + " max_age", d["max_age"])
                if 2 * max_age < self._period_ns:
                    raise CompileError("%s: max_age is less than half a period" % what)
            if "max_ahead" in d:
                max_ahead = parse_duration(what + " max_ahead", d["max_ahead"])
                if 2 * max_ahead < self._period_ns:
                    raise CompileError("%s: max_ahead is less than half a period" % what)
            else:
                max_ahead = self._period_ns
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
            if bid == "" or "." in bid:
                raise CompileError("block id %r: an id is not empty and holds no dot" % (bid,))
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
                if v == "" and isinstance(v, str):
                    raise CompileError("block %r: input port %r is given a signal with no name" % (bid, port))
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
                if name == "":
                    raise b.err("output port %r: a published name is not empty" % port)
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
        self._find_loops()
        self._check_measurements()

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

    def _find_loops(self):
        """Rule 7.8.8: the loops that hold a model, each as one block."""
        deps = {bid: set() for bid in self._blocks}
        for bid, b in self._blocks.items():
            for conn in b.conns.values():
                if conn[0] == "blk":
                    deps[bid].add(conn[1])
        reach = {bid: self._reach(deps, bid) for bid in self._blocks}
        self._loops = []
        seen = set()
        for bid in sorted(self._blocks):
            if bid in seen or bid not in reach[bid]:
                continue
            ids = set(x for x in reach[bid] if bid in reach[x])
            seen |= ids
            members = [self._blocks[x] for x in sorted(ids)]
            models = [b for b in members if isinstance(b, ModelBlock)]
            if not models:
                continue
            if len(models) > 1:
                raise models[0].err(
                    "the model blocks %s are on one loop, a tick apart: write them as one model "
                    "(`linear` takes any number of states)" % ", ".join(repr(b.id) for b in models)
                )
            if "settle" not in models[0].st:
                raise models[0].err("setting 'settle' is missing, and the block is on a loop")
            settle = models[0].settle
            for b in members:
                if isinstance(b, Estimator):
                    raise b.err("an estimator on a loop that holds a model block is refused")
            # what else remembers on the loop is held against its settle
            held = [(b, b.ticks) for b in members if isinstance(b, Delay)]
            held += [(b, b.n) for b in members if isinstance(b, Window)]
            held += [(b, b.settle) for b in members if isinstance(b, Lowpass)]
            if sum(length for b, length in held) > settle:
                raise held[0][0].err(
                    "the delays, windows and low-passes on its loop add up to more than the loop's 'settle'"
                )
            loop = _Loop(ids, settle)
            self._loops.append(loop)
            for b in members:
                b.loop = loop
                # the outputs a block of the loop reads, in either phase
                for conn in b.conns.values():
                    if conn[0] == "blk" and conn[1] in ids:
                        loop.read.add((conn[1], conn[2]))

    def _check_measurements(self):
        """Rule 7.9.3: a measurement carries the time of a sample. Its port
        is connected to an input, or to a delay or a formula that takes its
        sample time, through any number of those, from an input."""
        for b in self._blocks.values():
            if not isinstance(b, Estimator):
                continue
            for port, _c, _r, _ru in b.measures:
                conn = b.conns[port]
                if conn[0] == "const":
                    raise b.err("measurement %r is given a constant, which is not a sample of anything" % port)
                seen = set()
                while conn[0] == "blk":
                    src = self._blocks[conn[1]]
                    if conn[1] in seen:
                        src = None  # round a loop of delays: it never comes from an input
                    seen.add(conn[1])
                    if isinstance(src, Delay):
                        conn = src.conns["x"]
                    elif isinstance(src, Formula) and src.sample_port is not None:
                        conn = src.conns[src.sample_port]
                    else:
                        raise b.err(
                            "measurement %r does not carry the time of a sample: it comes by block %r, "
                            "which gives its output the time of the tick" % (port, conn[1])
                        )

    # ------------------------------------------------------------- running

    def reset(self):
        self._last_k = None  # number of the last tick run
        self._anchor_k = 0  # a tick whose time is known ...
        self._anchor_t = 0  # ... and its time
        self._origin_t = 0  # time of tick 0, or of the last rebase's tick
        self._last_now = None
        self._rebase = False  # the next call is a rebase (rule 8.3)
        self._away = None  # how long the host says the graph was away, if it does
        self._rebased = False  # there has been a rebase since the engine was made or last reset
        self._standing = {}  # name -> (state, value, time)
        self._waiting = {}  # name -> [(state, value, time)], in the order made
        self._thrown = 0  # writes thrown away since the last call that ran a tick
        self.info = None
        for b in self._blocks.values():
            b.reset()
        for lp in self._loops:
            lp.reset()

    def save(self):
        return {
            "graph": self._graph_key,
            "engine": copy.deepcopy(
                (self._last_k, self._anchor_k, self._anchor_t, self._origin_t, self._last_now, self._standing)
            ),
            "blocks": {bid: copy.deepcopy(b.s) for bid, b in self._blocks.items()},
            "loops": [copy.deepcopy(lp.s) for lp in self._loops],
        }

    def restore(self, saved):
        if not isinstance(saved, dict) or saved.get("graph") != self._graph_key:
            raise ValueError("this state was not saved from the same graph")
        if saved["engine"][0] is None:
            # saved before any tick had run: a reset, and no gap (rule 8.3)
            self.reset()
            return
        (self._last_k, self._anchor_k, self._anchor_t, self._origin_t, self._last_now, self._standing) = copy.deepcopy(
            saved["engine"]
        )
        for bid, b in self._blocks.items():
            b.s = copy.deepcopy(saved["blocks"][bid])
        for lp, s in zip(self._loops, saved["loops"]):
            lp.s = copy.deepcopy(s)
        # nothing stands or waits from this moment (rule 8.5)
        self._standing = {}
        self._waiting = {}
        self._rebase = True
        self._away = None

    def rebase(self, away=None):
        """The host says that its clock has stepped (rule 8.3), and may say
        how long the graph was away (rule 8.5)."""
        if away is not None and not (_is_time(away) and away >= 0):
            raise ValueError("the length of a rebase is a whole number of nanoseconds, not less than zero")
        self._waiting = {}
        if self._last_k is not None:
            # nothing stands from this moment (rule 8.5)
            self._standing = {}
            self._rebase = True
            self._away = away  # of two before the call, the second counts

    def write(self, name, state, value, at):
        if name not in self.inputs:
            raise KeyError("no input named %r" % (name,))
        if state not in _RANK:
            raise ValueError("unknown state %r" % (state,))
        if not _is_time(at):
            raise ValueError("the time of a write is a whole number of nanoseconds")
        if not usable(state):
            value = None
        elif self.inputs[name].type == BOOLEAN:
            if not isinstance(value, bool):
                raise ValueError("input %r takes a boolean" % name)
        else:
            if not _is_num(value):
                raise ValueError("input %r takes a number" % name)
            value = float(value)
        standing = self._standing.get(name)
        if standing is not None and at < standing[2]:
            # it can never stand: thrown away as it is made (rule 6.8)
            self._thrown += 1
            return
        writes = self._waiting.setdefault(name, [])
        writes.append((state, value, at))
        if len(writes) > self._max_waiting:
            # the earliest time goes, the earlier written of two the same
            del writes[min(range(len(writes)), key=lambda i: writes[i][2])]
            self._thrown += 1

    def _time(self, k):
        return self._anchor_t + (k - self._anchor_k) * self._period_ns

    def tick(self, now):
        if not _is_time(now):
            raise ValueError("now is a whole number of nanoseconds")
        period = self._period_ns
        gap = False
        skipped = 0
        if self._last_k is not None and not self._rebase and now < self._last_now:
            raise ValueError("now is earlier than the last call's")
        # a call that would run a tick whose number or whose time does not
        # fit in 64 bits, signed, is refused, and changes nothing (rule 6.11)
        if self._last_k is not None:
            if self._rebase:
                due = 1 if self._away is None else max((2 * self._away + period) // (2 * period), 1)
                last = (self._last_k + due, now)
            else:
                due = (2 * (now - self._time(self._last_k)) + period) // (2 * period)
                last = (self._last_k + due, self._time(self._last_k) + due * period) if due > 0 else None
            if last is not None and not (_is_time(last[0]) and _is_time(last[1])):
                raise ValueError("the call would run a tick whose number or time does not fit in 64 bits")
        # stamped ahead (rule 6.8): at every call, a waiting write whose
        # time is more than max_ahead after now is thrown away
        for name, writes in self._waiting.items():
            limit = now + self.inputs[name].max_ahead
            kept = [w for w in writes if w[2] <= limit]
            self._thrown += len(writes) - len(kept)
            writes[:] = kept
        if self._last_k is None:
            ticks = [(0, now)]
            self._anchor_k, self._anchor_t = 0, now
            self._origin_t = now
        elif self._rebase:
            # a rebase: one tick, at `now`, whatever `now` is (rule 8.5)
            gap = True
            if self._away is None:
                # nobody knows how many ticks were passed over
                skipped = None
                g = self._last_k + 1
            else:
                # the ticks that would have been due in that time: the
                # last of them runs, and the rest are passed over
                due = (2 * self._away + period) // (2 * period)
                skipped = max(due - 1, 0)
                g = self._last_k + 1 + skipped
            self._anchor_k, self._anchor_t = g, now
            self._origin_t = now
            self._rebased = True
            for b in self._blocks.values():
                b.rebase()
                b.gap(g, skipped)
            if skipped != 0:
                for lp in self._loops:
                    lp.s["doubt"] = _later(lp.s["doubt"], g - 1)
            ticks = [(g, now)]
        else:
            last_t = self._time(self._last_k)
            # how many ticks not yet run are no more than half a period
            # after now: last_t + j * period <= now + period / 2
            due = (2 * (now - last_t) + period) // (2 * period)
            if due <= 0:
                self._last_now = now
                self.info = None
                return (0, None)
            if due > self._max_catch_up:
                # a stall: one tick, the last that was due (rule 8.4)
                # under its own number, at its own time; the due ticks
                # before it are passed over
                gap = True
                skipped = due - 1
                g = self._last_k + due
                t = last_t + due * period
                self._anchor_k, self._anchor_t = g, t
                for b in self._blocks.values():
                    b.gap(g, skipped)
                for lp in self._loops:
                    lp.s["doubt"] = _later(lp.s["doubt"], g - 1)
                ticks = [(g, t)]
            else:
                ticks = [(self._last_k + j, last_t + j * period) for j in range(1, due + 1)]
        self._rebase = False
        self._away = None
        sig = None
        for i, (k, t) in enumerate(ticks):
            # the last tick of a call may see what the host has in hand
            self._take_up(max(t, now) if i == len(ticks) - 1 else t)
            sig = self._run_tick(k, t)
            self._last_k = k
        self._last_now = now
        self.info = {
            "gap": gap,
            "skipped": skipped,
            "tick": ticks[-1][0],
            "time": ticks[-1][1],
            "thrown": self._thrown,
            "waiting": sum(len(w) for w in self._waiting.values()),
        }
        self._thrown = 0
        outputs = {}
        for name, key in self._published.items():
            s = sig[key]
            outputs[name] = (s[0], s[1])
        return (len(ticks), outputs)

    def _take_up(self, limit):
        """Rule 6.8: the writes waiting whose time is not after `limit` are
        done with. Among them and what stood, the one with the latest time
        stands; of two with the same time, the one written later."""
        for name, writes in self._waiting.items():
            best = self._standing.get(name)
            for w in writes:
                if w[2] <= limit and (best is None or w[2] >= best[2]):
                    best = w
            writes[:] = [w for w in writes if w[2] > limit]
            if best is not None:
                self._standing[name] = best

    def _input_signal(self, name, k, t):
        d = self.inputs[name]
        standing = self._standing.get(name)
        if standing is None:
            too_long = d.max_age is not None and t - self._origin_t > d.max_age
            if not too_long:
                if d.has_initial and not self._rebased:
                    # it stands in for the first measurement and for nothing
                    # later: not after a rebase (rule 7.2.1)
                    return (UNC, d.initial, None)
                return (NR, None, None)
            return (BAD, None, None)
        state, value, at = standing
        if not usable(state):
            return (state, None, None)
        if d.type == NUMBER and not math.isfinite(value):
            return (BAD, None, None)
        if d.max_age is not None and t - at > d.max_age:
            return (BAD, None, None)
        return (state, value, at)

    @staticmethod
    def _get(conn, sig):
        if conn[0] == "const":
            return (GOOD, conn[1], None)
        return sig[conn]

    @staticmethod
    def _loop_reads(b, ins, k):
        """Rule 7.8.8: a block on a loop that uses a value that is not good,
        read from outside the loop, is the loop's doubt."""
        for port in b.uses(ins):
            conn = b.conns[port]
            if conn[0] == "in" or (conn[0] == "blk" and conn[1] not in b.loop.ids):
                if ins[port][0] != GOOD:
                    b.loop.s["doubt"] = k

    def _run_tick(self, k, t):
        sig = {}
        for lp in self._loops:
            lp.s["prev"] = lp.s["doubt"]
        for name in self.inputs:
            sig[("in", name)] = self._input_signal(name, k, t)
        # first phase: every block gives its outputs
        for b in self._order:
            ins = {port: self._get(conn, sig) for port, conn in b.conns.items() if b.in_ports[port][2]}
            if b.loop is not None:
                self._loop_reads(b, ins, k)
            outs = b.output(k, t, ins)
            for port in b.out_ports:
                state, value, stime = outs[port]
                ptype = self._types[(b.id, port)]
                if usable(state) and ptype == NUMBER:
                    value = float(value)
                    if not math.isfinite(value):
                        state = BAD
                if not usable(state):
                    if b.loop is not None and (b.id, port) in b.loop.read:
                        # not usable, to a block of the loop that reads it,
                        # fallback or not
                        b.loop.s["doubt"] = k
                    if port in b.fallback:
                        # it is not a sample of anything: no sample time (rule 3.7)
                        res = (UNC, b.fallback[port], None)
                    else:
                        res = (state, None, None)
                else:
                    if stime is TICK:
                        stime = t
                    res = (state, value, stime)
                sig[("blk", b.id, port)] = res
        # second phase: every block updates its state
        for b in self._order:
            if b.has_update:
                ins = {port: self._get(conn, sig) for port, conn in b.conns.items()}
                if b.loop is not None:
                    self._loop_reads(b, {p: s for p, s in ins.items() if not b.in_ports[p][2]}, k)
                b.update(k, t, ins)
        return sig

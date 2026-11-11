#!/usr/bin/env python3
"""The formula block's language, for the reference: Appendix A's grammar and types, section 7.1's states.

Kept apart from reference.py so that the engine can be read without it.
Its own parser: nothing here uses Python's.
"""

from __future__ import annotations

import collections
import math
import re

GOOD, UNCERTAIN, NOT_READY, BAD = "good", "uncertain", "not_ready", "bad"
_WORST_FIRST = (BAD, NOT_READY, UNCERTAIN, GOOD)  # section 3 rule 3
NUMBER, BOOLEAN = "number", "boolean"

# A signal: its state, its value, the time it was sampled, and if it is uncertain the tick of the cause.
Val = collections.namedtuple("Val", "state v at cause", defaults=(None, None, None))


class CompileError(Exception):
    """The graph is refused. Raised when a graph is built, never while it runs."""


def usable(val):
    return val.state in (GOOD, UNCERTAIN)


def worst(states):
    states = set(states)
    return next((s for s in _WORST_FIRST if s in states), GOOD)


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

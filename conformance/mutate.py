#!/usr/bin/env python3
"""Break the reference one way at a time and check that a vector notices.

The proposal (section 11) accepts a vector only once a deliberately broken
implementation has been shown to fail it. This is that check, kept beside
the vectors so that it is rerun when either changes.

  python3 conformance/mutate.py

Each entry below names the rule it breaks, a piece of reference.py and what
to put in its place; an entry may give several such pairs. Each piece has to
occur exactly once. Exits 1 if any breakage passes every vector, or if an
entry no longer matches the file. Also lists the vectors that no breakage
failed. Writes only to a temporary directory.
"""

# ruff: noqa: E501 - the entries quote lines of reference.py as they are
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

NUMBER = '_NUMBER = r"[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"'
IF_FALSE = "if False:"

MUTATIONS = [
    # ---- states
    ("3.3 not_ready outranks bad",
     "_WORST_FIRST = (BAD, NOT_READY, UNCERTAIN, GOOD)", "_WORST_FIRST = (NOT_READY, BAD, UNCERTAIN, GOOD)"),
    ("3.3 uncertain outranks not_ready",
     "_WORST_FIRST = (BAD, NOT_READY, UNCERTAIN, GOOD)", "_WORST_FIRST = (BAD, UNCERTAIN, NOT_READY, GOOD)"),
    ("3.6 a block output that is not finite stays usable",
     "if usable(val) and isinstance(val.v, float) and not math.isfinite(val.v):", IF_FALSE),
    # ---- formulas
    ("7.1.1 an uncertain operand gives a good result",
     "        state = worst(v.state for v in vals)  # 7.1 rule 1\n",
     "        state = worst(v.state for v in vals)  # 7.1 rule 1\n        state = GOOD if state == UNCERTAIN else state\n"),
    ("7.1.2 and/or swapped", 'decides = kind == "or"', 'decides = kind == "and"'),
    ("7.1.2 logic made strict", "            if deciders:\n", "            if False:\n"),
    ("7.1.2 a decided result is always good",
     "return Val(GOOD if any(v.state == GOOD for v in deciders) else UNCERTAIN, decides)", "return Val(GOOD, decides)"),
    ("7.1.2 an uncertain decider outweighs a good one",
     "return Val(GOOD if any(v.state == GOOD for v in deciders) else UNCERTAIN, decides)",
     "return Val(UNCERTAIN if any(v.state == UNCERTAIN for v in deciders) else GOOD, decides)"),
    ("7.1.3 an unusable condition takes the else branch",
     "            if not usable(cond):\n                return Val(cond.state, None)\n",
     "            if not usable(cond):\n                return self._eval(node[4], env)\n"),
    ("7.1.3 branches swapped", "node[3] if cond.v else node[4]", "node[4] if cond.v else node[3]"),
    ("7.1.3 the condition's state is dropped", "state = worst((cond.state, branch.state))", "state = branch.state"),
    ("7.1.3 the branch not chosen is looked at",
     "state = worst((cond.state, branch.state))",
     "state = worst((cond.state, self._eval(node[3], env).state, self._eval(node[4], env).state))"),
    ("7.1.4 a failed operation gives zero",
     "        except (ZeroDivisionError, ValueError, OverflowError):  # 7.1 rule 4\n            return Val(BAD, None)",
     "        except (ZeroDivisionError, ValueError, OverflowError):  # 7.1 rule 4\n            return Val(GOOD, 0.0)"),
    ("7.1.4 a result that is not finite is used by the next operation",
     "        if isinstance(value, float) and not math.isfinite(value):\n            return Val(BAD, None)\n"
     "        return Val(state, value)",
     "        return Val(state, value)"),
    ("7.1.6 equality with a tolerance",
     '"==": lambda a, b: a == b,',
     '"==": lambda a, b: a == b or (not isinstance(a, bool) and abs(a - b) < 1e-9),'),
    ("A.formula * and + at one level",
     '        return self._binary("+-", self._mul)', '        return self._binary("+-*/", self._unary)'),
    ("A.formula <= read as <", '"<=": lambda a, b: a <= b,', '"<=": lambda a, b: a < b,'),
    ("A.formula >= read as >", '">=": lambda a, b: a >= b,', '">=": lambda a, b: a > b,'),
    ("A.formula != read as ==", '"!=": lambda a, b: a != b,', '"!=": lambda a, b: a == b,'),
    ("A.formula min and max swapped", '"min": min,\n                "max": max,', '"min": max,\n                "max": min,'),
    ("A.formula operand types not checked",
     "        if node[1] != want:\n            raise CompileError(f\"formula: {what} takes a {want}, and was given a {node[1]}\")",
     "        if False:\n            pass"),
    ("A.formula == between two types accepted",
     "                if node[1] != right[1]:\n                    raise CompileError(f\"formula: {op} takes two of one type\")",
     "                if False:\n                    pass"),
    ("A.formula branches of two types accepted",
     "                if args[1][1] != args[2][1]:\n"
     "                    raise CompileError(\"formula: the two branches of when are of one type\")",
     "                if False:\n                    pass"),
    ("A.formula hexadecimal numbers accepted",
     [(NUMBER, '_NUMBER = r"0x[0-9a-fA-F]+|[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"'),
      ('return ("const", NUMBER, float(text))',
       'return ("const", NUMBER, float(int(text, 16)) if text.startswith("0x") else float(text))')]),
    ("A.formula separators in numbers accepted",
     NUMBER, '_NUMBER = r"[0-9][0-9_]*(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"'),
    ("A.formula a number may end in a point",
     NUMBER, '_NUMBER = r"[0-9]+(?:\\.[0-9]*)?(?:[eE][+-]?[0-9]+)?"'),
    ("A.formula a number may start with a point",
     NUMBER, '_NUMBER = r"[0-9]*\\.?[0-9]+(?:[eE][+-]?[0-9]+)?"'),
    ("A.formula a trailing comma accepted",
     '            while self._peek() == ("op", ","):\n                self._take()\n',
     '            while self._peek() == ("op", ","):\n                self._take()\n'
     '                if self._peek() == ("op", ")"):\n                    break\n'),
    ("A.formula True read as true",
     '        if text in ("true", "false"):\n            return ("const", BOOLEAN, text == "true")',
     '        if text.lower() in ("true", "false"):\n            return ("const", BOOLEAN, text.lower() == "true")'),
    ("A.formula comparisons may chain",
     [('                raise CompileError("comparisons do not chain: write (a < b) and (b < c)")', "                pass"),
      ('        if self.i != len(self.tokens):\n            raise CompileError(f"formula: unexpected {self.tokens[self.i][1]!r}")',
       "        if False:\n            pass")]),
    ("A.formula an input may be named for a function",
     [("        if bad:\n", "        if False:\n"),
      ('        if text in _FUNCTIONS:\n            self._take("(")',
       '        if text in _FUNCTIONS and text not in self.types:\n            self._take("(")')]),
    ("A.formula % accepted as an operator",
     [("[-+*/<>(),]))", "[-+*/%<>(),]))"),
      ('        return self._binary("*/", self._unary)', '        return self._binary("*/%", self._unary)')]),
    ("A.formula an empty formula is zero",
     [("        self.tree = self._or()\n", '        self.tree = self._or() if self.tokens else ("const", NUMBER, 0.0)\n'),
      ("        if unused:\n", "        if False:\n")]),
    ("A.formula a number too large for a double accepted", "            if not math.isfinite(float(text)):", "            if False:"),
    ("4.7 a constant that is not finite accepted",
     "if not isinstance(ref, bool) and not math.isfinite(ref):", IF_FALSE),
    ("9.3 a length of time without a unit accepted",
     "    m = _DURATION.match(text) if isinstance(text, str) else None\n",
     "    if isinstance(text, (int, float)) and not isinstance(text, bool):\n        return float(text)\n"
     "    m = _DURATION.match(str(text))\n"),
    ("9.2 a signal name that is not text accepted", "                if not isinstance(signal, str) or not signal:", "                if False:"),
    ("A.formula an unused input accepted", "        if unused:\n", "        if False:\n"),
    ("A.formula an unknown name reads as zero",
     "            raise CompileError(f\"formula uses {text!r}, which is not one of the block's inputs\")",
     '            return ("const", NUMBER, 0.0)'),
    ("A.formula a function takes any number of arguments", "            if len(args) != _FUNCTIONS[text]:", "            if False:"),
    ("A.formula an unclosed bracket accepted",
     '            node = self._or()\n            self._take(")")\n            return node',
     '            node = self._or()\n            if self._peek() == ("op", ")"):\n                self._take()\n            return node'),
    # ---- blocks
    ("A.all_good counts uncertain as good",
     "all(v.state == GOOD for v in ins.values())", "all(usable(v) for v in ins.values())"),
    ("A.delay one tick short", 'if len(self.past) < self.s["ticks"]:', 'if len(self.past) < self.s["ticks"] - 1:'),
    ("4.4 a delay's input is direct", 'ports = {"x": (None, True, False)}', 'ports = {"x": (None, True, True)}'),
    ("A.delay drops the state of what it gives",
     '        self.past.append(ins["x"])',
     '        self.past.append(Val(GOOD, ins["x"].v, ins["x"].new) if usable(ins["x"]) else ins["x"])'),
    ("A.delay its initial value is uncertain",
     'return {"y": Val(GOOD, initial) if initial is not None else Val(NOT_READY)}',
     'return {"y": Val(UNCERTAIN, initial) if initial is not None else Val(NOT_READY)}'),
    ("7.2 a delay's output is always new",
     "    own_new = True  # its output is new when the input it gives was new\n", "    own_new = False\n"),
    ("5.4 a delay on a loop without an initial value accepted",
     [('            if isinstance(block, Delay) and block.s["initial"] is None and self._reaches(every, bid, bid):',
       "            if False:"),
      ('                    elif cls is Delay and (b.get("settings") or {}).get("initial") is not None:',
       "                    elif cls is Delay:")]),
    ("7.3.2 min_good ignored: every sample required",
     'if len(held) < math.ceil(self.s["min_good"] * self.n - 1e-9):', "if len(held) < self.n:"),
    ("7.3.2 min_good times n compared as it comes out in binary",
     'if len(held) < math.ceil(self.s["min_good"] * self.n - 1e-9):', 'if len(held) < self.s["min_good"] * self.n:'),
    ("7.3.2 min_good ignored: one sample is enough",
     'if len(held) < math.ceil(self.s["min_good"] * self.n - 1e-9):', "if len(held) < 1:"),
    ("7.3.3 a short window is always bad",
     "return out | dict.fromkeys(names, Val(worst(missing)))", "return out | dict.fromkeys(names, Val(BAD))"),
    ("7.3.3 a tick before the start counts as bad",
     "missing = [v.state for v in self.buf if not usable(v)] + [NOT_READY] * first",
     "missing = [v.state for v in self.buf if not usable(v)] + [BAD] * first"),
    ("7.3.1 a window keeps one sample too many",
     "self.buf = collections.deque(maxlen=self.n)", "self.buf = collections.deque(maxlen=self.n + 1)"),
    ("7.3.4 a window with holes is good", "state = GOOD if whole else UNCERTAIN", "state = GOOD"),
    ("7.3.4 an uncertain sample counts as good",
     "all(v.state == GOOD for v in self.buf)", "all(usable(v) for v in self.buf)"),
    ("A.window median is the mean",
     '"median": Val(state, statistics.median(ys)),', '"median": Val(state, sum(ys) / len(ys)),'),
    ("A.window min is the oldest sample", '"min": Val(state, min(ys)),', '"min": Val(state, ys[0]),'),
    ("A.window max is the newest sample", '"max": Val(state, max(ys)),', '"max": Val(state, ys[-1]),'),
    ("A.window spread is last minus first",
     '"spread": Val(state, max(ys) - min(ys)),', '"spread": Val(state, ys[-1] - ys[0]),'),
    ("A.window slope per tick",
     "ts = [i * self.period for i, _ in held]", "ts = [float(i) for i, _ in held]"),
    ("A.window slope by sample count, not by time",
     "ts = [i * self.period for i, _ in held]", "ts = [n * self.period for n, _ in enumerate(held)]"),
    ("7.3.5 one sample has a slope of zero", 'out["slope"] = Val(BAD)', 'out["slope"] = Val(state, 0.0)'),
    ("7.3.6 count is of every tick",
     'out = {"count": Val(GOOD, float(len(held)))}', 'out = {"count": Val(GOOD, float(len(self.buf)))}'),
    ("7.4.1 a holder's output is always good",
     '            return {"y": Val(x.state, self.held)}', '            return {"y": Val(GOOD, self.held)}'),
    ("7.4.2 ride_through ignored",
     'if self.held is not None and k - self.seen <= self.s["ride_through"]:', IF_FALSE),
    ("7.4.2 ride_through one tick short",
     'k - self.seen <= self.s["ride_through"]:', 'k - self.seen < self.s["ride_through"]:'),
    ("7.4.2 a held value is good", '            return {"y": Val(UNCERTAIN, self.held)}', '            return {"y": Val(GOOD, self.held)}'),
    ("7.4.2 a holder forgets what it held",
     '        return {"y": Val(x.state)}\n\n\nclass Deadband',
     '        self.held = None\n        return {"y": Val(x.state)}\n\n\nclass Deadband'),
    ("7.4.4 a holder starts from zero",
     "            self.held = x.v if self.held is None else self.move(x.v)",
     "            self.held = self.move(x.v) if self.held is not None else 0.0"),
    ("A.deadband needs more than the step",
     'abs(x - self.held) >= self.s["step"]', 'abs(x - self.held) > self.s["step"]'),
    ("A.lowpass a is 1 - period / tau",
     'self.a = math.exp(-self.period / self.s["tau"])\n\n    def move',
     'self.a = 1 - self.period / self.s["tau"]\n\n    def move'),
    ("A.lowpass weights swapped",
     "return self.a * self.held + (1 - self.a) * x", "return (1 - self.a) * self.held + self.a * x"),
    ("7.5.1 true only above rise", 'if x.v >= self.s["rise"]:', 'if x.v > self.s["rise"]:'),
    ("7.5.1 false only below fall", 'elif x.v <= self.s["fall"]:', 'elif x.v < self.s["fall"]:'),
    ("7.5.2 hysteresis starts false",
     '            raise CompileError("rise is more than fall")\n        self.on = None',
     '            raise CompileError("rise is more than fall")\n        self.on = False'),
    ("7.5.3 an unusable input clears a hysteresis",
     '            return {"y": Val(x.state)}\n        if x.v >= self.s["rise"]:',
     '            self.on = None\n            return {"y": Val(x.state)}\n        if x.v >= self.s["rise"]:'),
    ("7.5.2 a bad input before any threshold reads not_ready",
     '            return {"y": Val(x.state)}\n        if x.v >= self.s["rise"]:',
     '            return {"y": Val(x.state if self.on is not None else NOT_READY)}\n        if x.v >= self.s["rise"]:'),
    ("7.5.3 a hysteresis output is always good",
     'return {"y": Val(NOT_READY) if self.on is None else Val(x.state, self.on)}',
     'return {"y": Val(NOT_READY) if self.on is None else Val(GOOD, self.on)}'),
    ("7.6.1 held_for true at the time, not after it",
     'return {"y": Val(UNCERTAIN if self.degraded else GOOD, k - self.since > self.s["time"])}',
     'return {"y": Val(UNCERTAIN if self.degraded else GOOD, k - self.since >= self.s["time"])}'),
    ("7.6.1 held_for true at the time while holding",
     '        return {"y": Val(UNCERTAIN, k - self.since > self.s["time"])}',
     '        return {"y": Val(UNCERTAIN, k - self.since >= self.s["time"])}'),
    ("7.6.1 the reset policy holds",
     'if self.s["on_bad"] == "reset" or self.since is None or self.gap > self.s["hold_limit"]:',
     'if self.since is None or (self.s["hold_limit"] is not None and self.gap > self.s["hold_limit"]):'),
    ("7.6.1 hold_limit ignored",
     'if self.s["on_bad"] == "reset" or self.since is None or self.gap > self.s["hold_limit"]:',
     'if self.s["on_bad"] == "reset" or self.since is None:'),
    ("7.6.1 hold_limit one tick short", 'self.gap > self.s["hold_limit"]:', 'self.gap >= self.s["hold_limit"]:'),
    ("7.6.1 a held timer's output is good",
     '        return {"y": Val(UNCERTAIN, k - self.since > self.s["time"])}',
     '        return {"y": Val(GOOD, k - self.since > self.s["time"])}'),
    ("7.6.1 a gap is forgotten once the input is back", "        self.degraded = True\n", ""),
    ("7.6.1 an uncertain input is forgotten",
     "            self.degraded = self.degraded or x.state == UNCERTAIN\n            return",
     "            self.degraded = x.state == UNCERTAIN\n            return"),
    ("7.6.1 a false input gives good", '                return {"y": Val(x.state, False)}', '                return {"y": Val(GOOD, False)}'),
    ("7.6.1 a false input does not stop the timer",
     "            if not x.v:\n                self.since, self.degraded = None, False\n", "            if not x.v:\n"),
    ("7.6.1 unusable stretches add up", "            self.gap = 0\n", ""),
    ("7.6.2 since_true true at the time, not after it",
     'late = k - self.last > self.s["time"]', 'late = k - self.last >= self.s["time"]'),
    ("7.6.2 an unusable input counts as true",
     "if self.last is None or (usable(x) and x.v):", "if self.last is None or not usable(x) or x.v:"),
    ("7.6.2 assume_false gives good",
     'return {"y": Val(UNCERTAIN, late) if self.s["on_bad"] == "assume_false" else Val(x.state)}',
     'return {"y": Val(GOOD, late) if self.s["on_bad"] == "assume_false" else Val(x.state)}'),
    ("7.6.2 the policies swapped",
     'if self.s["on_bad"] == "assume_false" else Val(x.state)}', 'if self.s["on_bad"] == "unknown" else Val(x.state)}'),
    ("7.6.2 since_true is always good", '            return {"y": Val(x.state, late)}', '            return {"y": Val(GOOD, late)}'),
    ("7.6.3 an unusable input sets the latch",
     "        elif usable(s) and s.v:\n            self.on = True", "        elif not usable(s) or s.v:\n            self.on = True"),
    ("7.6.3 the latch does not latch", "        if self.on:\n", "        if self.on and usable(s) and s.v:\n"),
    ("7.6.3 a set latch takes the state of set",
     '            return {"y": Val(GOOD, True)}', '            return {"y": Val(s.state, True) if usable(s) else Val(s.state)}'),
    ("7.6.3 an unset latch is always good",
     'return {"y": Val(s.state, False) if usable(s) else Val(s.state)}', 'return {"y": Val(GOOD, False)}'),
    ("7.6.3 set wins over reset",
     "        if r is not None and usable(r) and r.v:\n            self.on = False\n"
     "        elif usable(s) and s.v:\n            self.on = True",
     "        if usable(s) and s.v:\n            self.on = True\n"
     "        elif r is not None and usable(r) and r.v:\n            self.on = False"),
    ("7.6.3 an unusable reset clears the latch",
     "        if r is not None and usable(r) and r.v:\n            self.on = False",
     "        if r is not None and (not usable(r) or r.v):\n            self.on = False"),
    ("7.6.3 an uncertain reset is ignored",
     "        if r is not None and usable(r) and r.v:\n            self.on = False",
     "        if r is not None and r.state == GOOD and r.v:\n            self.on = False"),
    ("7.7.1 the integrator ignores the period",
     'self.total += x.v * self.period / self.s["per"]', 'self.total += x.v / self.s["per"]'),
    ("A.integrate per ignored", 'self.total += x.v * self.period / self.s["per"]', "self.total += x.v * self.period"),
    ("7.7.2 missed time not counted", "            self.missed += 1\n        limit", "            self.missed += 0\n        limit"),
    ("7.7.2 missed is in ticks",
     '"missed": Val(GOOD, self.missed * self.period)', '"missed": Val(GOOD, float(self.missed))'),
    ("7.7.3 a total that missed time is good",
     "y = Val(UNCERTAIN if self.missed or self.degraded else GOOD, self.total)",
     "y = Val(UNCERTAIN if self.degraded else GOOD, self.total)"),
    ("7.7.3 a total that added an uncertain input is good",
     "y = Val(UNCERTAIN if self.missed or self.degraded else GOOD, self.total)",
     "y = Val(UNCERTAIN if self.missed else GOOD, self.total)"),
    ("7.7.4 max_missed ignored", "if limit is not None and self.missed > limit:", IF_FALSE),
    ("7.7.4 max_missed one tick short",
     "if limit is not None and self.missed > limit:", "if limit is not None and self.missed >= limit:"),
    ("7.7.5 reset after the addition",
     "        if r is not None and usable(r) and r.v:\n"
     "            self.total, self.missed, self.degraded = 0.0, 0, False\n"
     "        if usable(x):\n"
     '            self.total += x.v * self.period / self.s["per"]\n'
     "            self.degraded = self.degraded or x.state == UNCERTAIN\n"
     "        else:\n"
     "            self.missed += 1\n",
     "        if usable(x):\n"
     '            self.total += x.v * self.period / self.s["per"]\n'
     "            self.degraded = self.degraded or x.state == UNCERTAIN\n"
     "        else:\n"
     "            self.missed += 1\n"
     "        if r is not None and usable(r) and r.v:\n"
     "            self.total, self.missed, self.degraded = 0.0, 0, False\n"),
    ("7.7.5 reset keeps missed",
     "            self.total, self.missed, self.degraded = 0.0, 0, False\n        if usable(x):",
     "            self.total, self.degraded = 0.0, False\n        if usable(x):"),
    ("7.7.5 reset keeps the total uncertain",
     "            self.total, self.missed, self.degraded = 0.0, 0, False\n        if usable(x):",
     "            self.total, self.missed = 0.0, 0\n        if usable(x):"),
    ("7.7.5 an unusable reset resets",
     "        if r is not None and usable(r) and r.v:\n            self.total",
     "        if r is not None and (not usable(r) or r.v):\n            self.total"),
    ("7.9.1 an estimator starts on a measurement that is not new", "fresh = usable(z) and z.new", "fresh = usable(z)"),
    ("B an estimator starts with no uncertainty", 'self.x, self.var = z.v, self.s["r"]', "self.x, self.var = z.v, 0.0"),
    ("B a correction does not narrow the uncertainty", "self.var *= 1 - gain", "self.var *= 1"),
    ("B no growth without the model input",
     '            else:\n                self.var += self.s["q"] * self.period\n            if fresh:',
     "            else:\n                self.var += 0.0\n            if fresh:"),
    ("B a is 1 - period / tau",
     'self.a = math.exp(-self.period / self.s["tau"])\n        self.x, self.var',
     'self.a = 1 - self.period / self.s["tau"]\n        self.x, self.var'),
    ("7.9.4 max_coast ignored", 'coasting = k - self.corrected > self.s["max_coast"]', "coasting = False"),
    ("7.9.4 max_coast one tick short",
     'coasting = k - self.corrected > self.s["max_coast"]', 'coasting = k - self.corrected >= self.s["max_coast"]'),
    ("7.9.4 an uncertain measurement gives good outputs",
     "state = UNCERTAIN if coasting or self.on_uncertain else GOOD", "state = UNCERTAIN if coasting else GOOD"),
    # ---- inputs and time
    ("3.4 an unwritten input reads as zero",
     '            return Val(BAD) if k * self.period > spec["max_age"] else Val(NOT_READY)', "            return Val(GOOD, 0.0)"),
    ("7.2.2 an unwritten input never turns bad",
     '            return Val(BAD) if k * self.period > spec["max_age"] else Val(NOT_READY)', "            return Val(NOT_READY)"),
    ("7.2.2 an unwritten input turns bad a tick early",
     'if k * self.period > spec["max_age"] else Val(NOT_READY)', 'if k * self.period >= spec["max_age"] else Val(NOT_READY)'),
    ("7.2.2 an initial value is good",
     "                return Val(UNCERTAIN, value if isinstance(value, bool) else float(value))",
     "                return Val(GOOD, value if isinstance(value, bool) else float(value))"),
    ("7.2.2 an initial value is ignored", '            if spec["initial"] is not None:\n', "            if False:\n"),
    ("7.2.1 a missed tick reads what was written",
     "        if missed:\n            return Val(BAD)\n", "        if False:\n            return Val(BAD)\n"),
    ("7.2.3 a write of not_ready grows old and turns bad",
     "        if state in (NOT_READY, BAD):\n            return Val(state, None, new)\n"
     "        age = 0.0 if sampled is None else max(0.0, t - sampled)\n",
     "        age = 0.0 if sampled is None else max(0.0, t - sampled)\n"
     '        if state == BAD or (state == NOT_READY and age > spec["max_age"]):\n            return Val(BAD, None, new)\n'
     "        if state == NOT_READY:\n            return Val(state, None, new)\n"),
    ("7.2.4 a value that is not finite is usable",
     '(spec["type"] == NUMBER and not math.isfinite(value)) or age > spec["max_age"] or ahead',
     'age > spec["max_age"] or ahead'),
    ("7.2.4 maximum age ignored",
     '(spec["type"] == NUMBER and not math.isfinite(value)) or age > spec["max_age"] or ahead',
     '(spec["type"] == NUMBER and not math.isfinite(value)) or ahead'),
    ("7.2.4 maximum age one tick short", 'age > spec["max_age"] or ahead', 'age >= spec["max_age"] or ahead'),
    ("7.2.4 a sample from the future is usable",
     "ahead = sampled is not None and sampled - t > self.period", "ahead = False"),
    ("7.2.4 a sample at all ahead is bad",
     "ahead = sampled is not None and sampled - t > self.period", "ahead = sampled is not None and sampled - t > 0"),
    ("7.2.5 an input written uncertain reads good",
     "        return Val(state, value, new)\n\n    # ---- time", "        return Val(GOOD, value, new)\n\n    # ---- time"),
    ("6.6 the write with the latest sample time wins",
     "        self.written[name] = (state, value, sampled, self.serial)",
     "        if name not in self.written or sampled >= self.written[name][2]:\n"
     "            self.written[name] = (state, value, sampled, self.serial)"),
    ("7.2 an input is always new", "new = serial > self.seen", "new = True"),
    ("7.2 a write before missed ticks is not new after them",
     "        if not missed:\n            self.seen = self.serial\n", "        self.seen = self.serial\n"),
    ("6.4 a call a little early runs nothing",
     "<= now + self.period / 2:  # 6 rule 4", "<= now:  # 6 rule 4"),
    ("6.4 a call runs the tick a whole period ahead",
     "<= now + self.period / 2:  # 6 rule 4", "<= now + self.period:  # 6 rule 4"),
    ("6.5 missed ticks are skipped", "        for k in due:\n", "        for k in due[-1:]:\n"),
    ("6.5 a missed tick is run as an ordinary one", "missed=k != due[-1]", "missed=False"),
    ("6.4 a call earlier than the last accepted", "if self.last_now is not None and now < self.last_now:", IF_FALSE),
    ("6.3 tick 0 is at time zero", "self.zero = now - self.k * self.period", "self.zero = -self.k * self.period"),
    # ---- order
    ("5.1 blocks run in the order declared", "self.order = self._order(direct)", "self.order = list(direct)"),
    ("5.3 a loop of direct inputs accepted",
     '                raise CompileError(f"loop of direct inputs among blocks {sorted(set(deps) - done)}")',
     "                ready = sorted(set(deps) - done)"),
    ("4.7 a constant input is not ready", "                    ins[port] = Val(GOOD, src[1])", "                    ins[port] = Val(NOT_READY)"),
    # ---- fallbacks and state
    ("7.10 a fallback is good",
     "                        val = Val(UNCERTAIN, value if isinstance(value, bool) else float(value))",
     "                        val = Val(GOOD, value if isinstance(value, bool) else float(value))"),
    ("7.10 a fallback for bad only",
     "                    if port in self.fallback[bid]:  # 7.10",
     "                    if val.state == BAD and port in self.fallback[bid]:  # 7.10"),
    ("7.10 a fallback on every output of the block",
     [("                    if port in self.fallback[bid]:  # 7.10", "                    if self.fallback[bid]:  # 7.10"),
      ("                        value = self.fallback[bid][port]",
       "                        value = next(iter(self.fallback[bid].values()))")]),
    ("8.1 reset keeps block state",
     "        self.blocks = copy.deepcopy(self.initial_blocks)\n        self.k = 0", "        self.k = 0"),
    ("8.1 reset keeps the time of tick 0",
     "        self.zero = None  # the time of tick 0", '        self.zero = getattr(self, "zero", None)'),
    ("8.2 restore does nothing",
     "        self.blocks, self.k, self.written, self.serial, self.seen = copy.deepcopy(state)\n", ""),
    ("8.4 a restore catches up the time between",
     "        self.zero, self.last_now = None, None  # 8 rule 4: time did not pass", "        self.last_now = None"),
    # ---- refusals
    ("9.4 an unknown top-level key accepted",
     "if not isinstance(graph, dict) or set(graph) - _GRAPH_KEYS:", "if not isinstance(graph, dict):"),
    ("6.1 a graph with no period accepted",
     '        if "period" not in graph:\n            raise CompileError("a graph states its period")',
     '        if "period" not in graph:\n            graph = {**graph, "period": "1s"}'),
    ("9.4 an unknown key in a block accepted", "            if set(b) - _BLOCK_KEYS:", "            if False:"),
    ("9.4 an unknown key in an input accepted", "            if set(spec) - _INPUT_KEYS:", "            if False:"),
    ("9.4 an unknown block type not refused", '            if b.get("type") not in CATALOGUE:', "            if False:"),
    ("9.4 two blocks with one id accepted", "if len(set(ids)) != len(ids) or None in ids:", "if None in ids:"),
    ("9.4 an unknown output port accepted",
     "                if port not in cls.outputs:\n                    raise CompileError(f\"{where}: no output {port!r}\")",
     "                if False:\n                    pass"),
    ("4.6 two writers accepted", "if signal in writer or signal in self.inputs:", "if signal in self.inputs:"),
    ("4.6 a block may write an external input", "if signal in writer or signal in self.inputs:", "if signal in writer:"),
    ("9.4 an unknown input port not refused", "                if set(given) - set(cls.ports):", "                if False:"),
    ("9.4 a missing input accepted",
     "                if missing:\n                    raise CompileError(f\"{where}: missing input(s) {missing}\")",
     "                if False:\n                    pass"),
    ("9.1 an unknown signal reads as zero",
     "                    raise CompileError(f\"{where}: {ref} is neither an input nor a block's output\")",
     '                    wires[port] = ("const", 0.0)'),
    ("3.5 port types not checked", "                    if want is not None and kind != want:", "                    if False:"),
    ("9.4 an unknown setting accepted", "        if set(raw) - set(cls.settings):", "        if False:"),
    ("9.4 a missing required setting accepted",
     "                if required:\n                    raise CompileError(f\"{where}: missing setting {name!r}\")",
     "                if False:\n                    pass"),
    ("9.4 a setting of the wrong type not refused",
     "                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):\n"
     "                    raise CompileError(f\"{where}: setting {name!r} must be a finite number\")",
     "                if False:\n                    pass"),
    ("6.2 a length of part of a period accepted", "    if abs(n - round(n)) > 1e-9:", "    if False:"),
    ("A a window of no periods accepted", "    if round(n) < least:", "    if False:"),
    ("A min_good of zero accepted", 'if not 0.0 < self.s["min_good"] <= 1.0:', 'if not 0.0 <= self.s["min_good"] <= 1.0:'),
    ("A min_good above one accepted", 'if not 0.0 < self.s["min_good"] <= 1.0:', 'if not 0.0 < self.s["min_good"]:'),
    ("A a negative step accepted", '        if self.s["step"] < 0:', "        if False:"),
    ("A a delay of no ticks accepted", '        if self.s["ticks"] < 1:', "        if False:"),
    ("A a delay's initial value of the other type accepted",
     'if initial is not None and "x" in a[2] and _type_of(initial) != a[2]["x"]:', IF_FALSE),
    ("A a time constant of zero not refused", '        if self.s["tau"] <= 0:', "        if False:"),
    ("A an integrator per zero time accepted", '        if self.s["per"] <= 0:', "        if False:"),
    ("A rise equal to fall accepted", '        if not self.s["rise"] > self.s["fall"]:', "        if False:"),
    ("A hold without hold_limit not refused",
     'if (self.s["on_bad"] == "hold") != (self.s["hold_limit"] is not None):',
     'if self.s["on_bad"] != "hold" and self.s["hold_limit"] is not None:'),
    ("A hold_limit without hold accepted",
     'if (self.s["on_bad"] == "hold") != (self.s["hold_limit"] is not None):',
     'if self.s["on_bad"] == "hold" and self.s["hold_limit"] is None:'),
    ("A an unknown choice accepted", "                if value not in default:", "                if False:"),
    ("9.4 an unknown fallback port not refused",
     "                    if port not in cls.outputs:\n"
     "                        raise CompileError(f\"{where}: fallback names no output {port!r}\")",
     "                    if False:\n                        pass"),
    ("A a fallback of the other type accepted",
     "if not _is_constant(value) or _type_of(value) != out_types[port]:", "if not _is_constant(value):"),
    ("A a fallback that is not finite accepted",
     "                    if out_types[port] == NUMBER and not math.isfinite(value):", "                    if False:"),
    ("9.1 an initial value of the other type accepted",
     "if initial is not None and (not _is_constant(initial) or _type_of(initial) != kind):", IF_FALSE),
]  # fmt: skip


def main():
    text = (HERE / "reference.py").read_text()
    vectors = sorted(HERE.glob("vectors/*.yaml"))
    survivors, stale, ever_failed = [], [], set()
    print(f"{'breakage':58s} result")
    for label, *rest in MUTATIONS:
        pairs = rest[0] if len(rest) == 1 else [tuple(rest)]
        counts = [text.count(old) for old, _ in pairs]
        if counts != [1] * len(pairs):
            stale.append(label)
            print(f"{label:58s} ENTRY MATCHES {counts} TIMES")
            continue
        broken = text
        for old, new in pairs:
            broken = broken.replace(old, new)
        if hashlib.sha256(broken.encode()).digest() == hashlib.sha256(text.encode()).digest():
            stale.append(label)
            print(f"{label:58s} ENTRY CHANGES NOTHING")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "reference.py").write_text(broken)
            shutil.copy(HERE / "run.py", tmp)
            run = subprocess.run(
                [sys.executable, "run.py", *map(str, vectors)], cwd=tmp, capture_output=True, text=True
            )
        failed = [line.split()[0] for line in run.stdout.splitlines() if line.rstrip().endswith("DIFFERS")]
        ever_failed.update(failed)
        if run.returncode == 0 or not failed:
            survivors.append(label)
            print(f"{label:58s} NOT NOTICED")
        else:
            shown = ", ".join(failed[:3]) + (f" and {len(failed) - 3} more" if len(failed) > 3 else "")
            print(f"{label:58s} fails {shown}")
    print()
    print(
        f"{len(MUTATIONS)} breakages: {len(MUTATIONS) - len(survivors) - len(stale)} noticed, "
        f"{len(survivors)} not noticed, {len(stale)} entries out of date"
    )
    never = [p.stem for p in vectors if p.stem not in ever_failed]
    print(f"{len(vectors)} vectors: {len(vectors) - len(never)} failed by a breakage, {len(never)} by none")
    for name in never:
        print(f"    {name}")
    sys.exit(1 if survivors or stale else 0)


if __name__ == "__main__":
    main()

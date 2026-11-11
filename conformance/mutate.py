#!/usr/bin/env python3
"""Break the reference one way at a time and check that a vector notices.

The proposal (section 11) accepts a vector only once a deliberately broken
implementation has been shown to fail it. This is that check, kept beside
the vectors so that it is rerun when either changes.

  python3 conformance/mutate.py

Each entry below names the rule it breaks, a piece of reference.py and what
to put in its place. The piece has to occur exactly once. Exits 1 if any
breakage passes every vector, or if an entry no longer matches the file.
Writes only to a temporary directory.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

MUTATIONS = [
    ("7.1.1 not_ready outranks bad",
     "return BAD if BAD in states else NOT_READY if NOT_READY in states else GOOD",
     "return NOT_READY if NOT_READY in states else BAD if BAD in states else GOOD"),
    ("7.1.2 and/or swapped", "decides = isinstance(node.op, ast.Or)", "decides = isinstance(node.op, ast.And)"),
    ("7.1.2 logic made strict",
     "if any(v.state == GOOD and bool(v.v) == decides for v in vals):", "if False:"),
    ("7.1.3 a bad condition takes the else branch",
     "            if cond.state != GOOD:\n                return Val(cond.state, None)\n",
     "            if cond.state != GOOD:\n                return self._eval(node.args[2], env)\n"),
    ("7.1.3 branches swapped", "node.args[1] if cond.v else node.args[2]", "node.args[2] if cond.v else node.args[1]"),
    ("7.1.4 division by zero is good",
     "        except ZeroDivisionError:  # 7.1 rule 4\n            return BAD_VAL",
     "        except ZeroDivisionError:  # 7.1 rule 4\n            return good(0.0)"),
    ("7.1.4 a result that is not finite stays good",
     "if val.state == GOOD and not math.isfinite(val.v):", "if False:"),
    ("7.7 an input that is not finite is usable",
     "if not math.isfinite(value) or t - sampled > self.max_age[name] + 1e-9:",
     "if t - sampled > self.max_age[name] + 1e-9:"),
    ("7.7 maximum age ignored",
     "if not math.isfinite(value) or t - sampled > self.max_age[name] + 1e-9:", "if not math.isfinite(value):"),
    ("7.7 maximum age off by one tick",
     "t - sampled > self.max_age[name] + 1e-9:", "t - sampled >= self.max_age[name] - 1e-9:"),
    ("3.3 an unwritten input reads as zero",
     "        if name not in self.written:\n            return NOT_READY_VAL",
     "        if name not in self.written:\n            return good(0.0)"),
    ("5.1 blocks run in the order declared", "self.order = self._order(deps)", "self.order = list(deps)"),
    ("5.3 a delay does not break a loop", 'previous = frozenset({"x"})', "previous = frozenset()"),
    ("4.2 delay one tick short", 'if self.count <= self.s["ticks"]:', 'if self.count < self.s["ticks"]:'),
    ("7.2 min_good ignored: every sample required",
     'self.need = math.ceil(self.s["min_good"] * self.n - 1e-9)', "self.need = self.n"),
    ("7.2 min_good ignored: one sample is enough",
     'self.need = math.ceil(self.s["min_good"] * self.n - 1e-9)', "self.need = 1"),
    ("7.2.3 a short window is always bad",
     "return dict.fromkeys(self.outputs, Val(worst(missing), None))", "return dict.fromkeys(self.outputs, BAD_VAL)"),
    ("7.2 window keeps samples of any age",
     "self.buf = collections.deque(maxlen=self.n)", "self.buf = collections.deque(maxlen=self.n + 1)"),
    ("7.2 median is the mean", '"median": good(statistics.median(ys)),', '"median": good(sum(ys) / len(ys)),'),
    ("7.2 spread is last minus first", '"spread": good(max(ys) - min(ys)),', '"spread": good(ys[-1] - ys[0]),'),
    ("7.2 slope per minute", "/ den)\n        return out", "/ den * 60.0)\n        return out"),
    ("7.2 slope by sample count, not by time",
     "usable = [(ti, v.v) for ti, v in self.buf if v.state == GOOD]",
     "usable = [(float(i), v.v) for i, (ti, v) in enumerate(x for x in self.buf if x[1].state == GOOD)]"),
    ("7.2.4 one sample has a slope of zero",
     'out["slope"] = BAD_VAL  # one sample has no slope', 'out["slope"] = good(0.0)  # one sample has no slope'),
    ("7.2.5 deadband needs more than the step",
     'abs(x.v - self.held) >= self.s["step"]', 'abs(x.v - self.held) > self.s["step"]'),
    ("7.2.6 ride_through ignored",
     'if self.held is not None and t - self.seen <= self.s["ride_through"] + 1e-9:', "if False:"),
    ("7.2.6 ride_through one tick short",
     't - self.seen <= self.s["ride_through"] + 1e-9:', 't - self.seen < self.s["ride_through"] - 1e-9:'),
    ("7.2.6 a holder forgets what it held",
     '        return {"y": Val(x.state, None)}\n\n\nclass HeldFor',
     '        self.held = None\n        return {"y": Val(x.state, None)}\n\n\nclass HeldFor'),
    ("7.3.1 reset policy ignored",
     'if self.s["on_bad"] == "reset" or self.since is None:', "if self.since is None:"),
    ("7.3.1 hold cannot run out while unusable",
     '        return {"y": good(t - self.since > self.s["time"] + 1e-9)}', '        return {"y": Val(x.state, None)}'),
    ("7.3.1 held_for true at the time, not after it",
     'good(self.since is not None and t - self.since > self.s["time"] + 1e-9)',
     'good(self.since is not None and t - self.since >= self.s["time"] - 1e-9)'),
    ("7.3.2 an unusable input counts as true",
     "if self.last is None or (x.state == GOOD and x.v):", "if self.last is None or x.state != GOOD or x.v:"),
    ("7.3.2 since_true true at the time, not after it",
     'good(t - self.last > self.s["time"] + 1e-9)', 'good(t - self.last >= self.s["time"] - 1e-9)'),
    ("7.3.3 an unusable input sets the latch",
     'self.on = self.on or (ins["set"].state == GOOD and bool(ins["set"].v))',
     'self.on = self.on or ins["set"].state != GOOD or bool(ins["set"].v)'),
    ("7.3.3 the latch does not latch",
     'self.on = self.on or (ins["set"].state == GOOD and bool(ins["set"].v))',
     'self.on = ins["set"].state == GOOD and bool(ins["set"].v)'),
    ("7.4 the total ignores the period",
     'ins["x"].v * self.period / self.s["per"]', 'ins["x"].v / self.s["per"]'),
    ("7.4 missed time not counted", "self.missed += self.period", "self.missed += 0.0"),
    ("7.5.1 an estimator starts with no uncertainty",
     'self.x, self.var = z.v, self.s["r"]', "self.x, self.var = z.v, 0.0"),
    ("7.5.2 a correction does not narrow the uncertainty", "self.var *= 1 - k", "self.var *= 1"),
    ("7.5.3 no growth without the model input",
     '        else:\n            self.var += self.s["q"] * self.period', "        else:\n            self.var += 0.0"),
    ("7.6 a fallback for bad only", "if val.state != GOOD and port in self.fallback[bid]:",
     "if val.state == BAD and port in self.fallback[bid]:"),
    ("7.6 a fallback on every output of the block",
     "                    val = good(self.fallback[bid][port])  # 7.6",
     "                    val = good(self.fallback[bid][port])  # 7.6\n"
     "                elif val.state != GOOD and self.fallback[bid]:\n"
     "                    val = good(next(iter(self.fallback[bid].values())))"),
    ("all_good counts not_ready as usable",
     "all(v.state == GOOD for v in ins.values())", "all(v.state != BAD for v in ins.values())"),
    ("8.2 restore does nothing",
     "self.blocks, self.k, self.written, self.last, self.last_inputs = copy.deepcopy(state)", "pass"),
    ("3.6 only exactly 1 is true", "bool(v.v) == decides for v in vals", "(v.v == 1.0) == decides for v in vals"),
    ("3.6 a timer takes only exactly 1 as true",
     "(self.since if self.since is not None else t) if x.v else None",
     "(self.since if self.since is not None else t) if x.v == 1.0 else None"),
    ("7.7 a not_ready write grows old and turns bad",
     "        if state != GOOD:\n            return Val(state, None)\n        if not math.isfinite(value)",
     "        if state == BAD or t - sampled > self.max_age[name] + 1e-9:\n            return BAD_VAL\n"
     "        if state != GOOD:\n            return Val(state, None)\n        if not math.isfinite(value)"),
    ("Appendix A: a formula may leave an input unused", "        if unused:\n", "        if False:\n"),
    ("Appendix A: comparisons may chain",
     '            raise CompileError("comparisons do not chain: write (a < b) and (b < c)")',
     "            children = [node.left, *node.comparators]"),
    ("Appendix A: min_good of zero accepted",
     'if not 0.0 < self.s["min_good"] <= 1.0:', 'if not 0.0 <= self.s["min_good"] <= 1.0:'),
    ("Appendix A: a negative step accepted", 'if self.s["step"] < 0 or self.s["ride_through"] < 0:', "if False:"),
    ("Appendix A: a period longer than tau accepted", 'if self.period > self.s["tau"] + 1e-12:', "if False:"),
    ("9.3 a missing input accepted",
     "                if missing:\n                    raise CompileError(f\"{where}: missing input(s) {missing}\")",
     "                if False:\n                    pass"),
    ("9.3 an unknown output port accepted",
     "                if port not in cls.outputs:\n"
     '                    raise CompileError(f"{where}: no output {port!r}")',
     "                if False:\n                    pass"),
    ("9.3 two blocks with one id accepted", "if len(set(ids)) != len(ids) or None in ids:", "if None in ids:"),
    ("4.6 a constant input is not ready",
     '                    ins[port] = good(src[1])', "                    ins[port] = NOT_READY_VAL"),
    ("8.1 reset keeps block state",
     "        self.blocks = copy.deepcopy(self.initial)\n        self.k = 0", "        self.k = 0"),
    ("4.5 two writers accepted", "if signal in writer or signal in self.max_age:", "if False:"),
    ("9.3 unknown setting accepted", "if set(raw) - set(cls.settings):", "if False:"),
    ("9.3 missing required setting accepted",
     "                    if required:\n"
     '                        raise CompileError(f"{where}: missing setting {name!r}")',
     "                    if False:\n                        pass"),
    ("9.3 unknown top-level key accepted",
     "if not isinstance(graph, dict) or set(graph) - _GRAPH_KEYS:", "if not isinstance(graph, dict):"),
    ("9.1 an unknown signal reads as zero",
     'raise CompileError(f"{where}: {ref} is neither an input nor a block\'s output")', 'wires[port] = ("const", 0.0)'),
    ("6.2 a window of part of a period accepted",
     "if abs(n - round(n)) > 1e-9 or round(n) < 1:", "if round(n) < 1:"),
]  # fmt: skip


def main():
    text = (HERE / "reference.py").read_text()
    survivors, stale = [], []
    print(f"{'breakage':52s} result")
    for label, old, new in MUTATIONS:
        if text.count(old) != 1:
            stale.append(label)
            print(f"{label:52s} ENTRY MATCHES {text.count(old)} TIMES")
            continue
        broken = text.replace(old, new)
        if hashlib.sha256(broken.encode()).digest() == hashlib.sha256(text.encode()).digest():
            stale.append(label)
            print(f"{label:52s} ENTRY CHANGES NOTHING")
            continue
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "reference.py").write_text(broken)
            shutil.copy(HERE / "run.py", tmp)
            vectors = sorted(str(p) for p in (HERE / "vectors").glob("*.yaml"))
            run = subprocess.run([sys.executable, "run.py", *vectors], cwd=tmp, capture_output=True, text=True)
        failed = [line.split()[0] for line in run.stdout.splitlines() if line.rstrip().endswith("DIFFERS")]
        if run.returncode == 0 or not failed:
            survivors.append(label)
            print(f"{label:52s} NOT NOTICED")
        else:
            shown = ", ".join(failed[:3]) + (f" and {len(failed) - 3} more" if len(failed) > 3 else "")
            print(f"{label:52s} fails {shown}")
    print()
    print(
        f"{len(MUTATIONS)} breakages: {len(MUTATIONS) - len(survivors) - len(stale)} noticed, "
        f"{len(survivors)} not noticed, {len(stale)} entries out of date"
    )
    sys.exit(1 if survivors or stale else 0)


if __name__ == "__main__":
    main()

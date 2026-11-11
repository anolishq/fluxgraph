"""Checks worked out by hand from the proposal. Run: python3 selftest.py"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from impl import CompileError, Engine  # noqa: E402

G, U, N, B = "good", "uncertain", "not_ready", "bad"
passed = 0
failed = 0


def check(name, got, want):
    global passed, failed
    ok = got == want
    if not ok and isinstance(got, tuple) and isinstance(want, tuple) and len(got) == len(want) == 2:
        if got[0] == want[0] and isinstance(got[1], float) and isinstance(want[1], float):
            ok = math.isclose(got[1], want[1], rel_tol=1e-9, abs_tol=1e-12)
    if ok:
        passed += 1
    else:
        failed += 1
        print("FAIL %s: got %r, want %r" % (name, got, want))


def refused(name, graph):
    global passed, failed
    try:
        Engine(graph)
    except CompileError:
        passed += 1
        return
    failed += 1
    print("FAIL %s: graph was accepted" % name)


def raises(name, fn):
    global passed, failed
    try:
        fn()
    except CompileError:
        pass
    except Exception:
        passed += 1
        return
    failed += 1
    print("FAIL %s: no exception (or a CompileError)" % name)


def formula(expr, ins, inputs):
    return {
        "period": "1s",
        "inputs": inputs,
        "blocks": [{"id": "f", "type": "formula", "in": ins, "settings": {"expr": expr}, "out": {"y": "y"}}],
    }


def run(graph, steps):
    """steps: list of (now, {name: (state, value)}) -> list of outputs."""
    e = Engine(graph)
    res = []
    for now, writes in steps:
        for name, (s, v) in writes.items():
            e.write(name, s, v, now)
        res.append(e.tick(now)[1])
    return res


NUM = {"type": "number"}
BOOL = {"type": "boolean"}

# ---- 3, 7.1 formulas
g = formula("a + b * 2", {"a": "a", "b": "b"}, {"a": NUM, "b": NUM})
r = run(g, [(0, {}), (1, {"a": (G, 1.0)}), (2, {"b": (U, 3.0)}), (3, {"a": (B, None)})])
check("3.4 unwritten is not_ready", r[0]["y"], (N, None))
check("7.1.1 worst of good and not_ready", r[1]["y"], (N, None))
check("7.1.1 uncertain operand, precedence", r[2]["y"], (U, 7.0))
check("7.1.1 bad operand", r[3]["y"], (B, None))

g = formula("(a or b) and c", {"a": "a", "b": "b", "c": "c"}, {"a": BOOL, "b": BOOL, "c": BOOL})
r = run(
    g,
    [
        (0, {"a": (G, True), "b": (B, None), "c": (G, True)}),
        (1, {"a": (U, True)}),
        (2, {"a": (G, False)}),
        (3, {"c": (U, False)}),
    ],
)
check("7.1.5 example", r[0]["y"], (G, True))
check("7.1.2 decided by an uncertain operand", r[1]["y"], (U, True))
check("7.1.2 nothing decides", r[2]["y"], (B, None))
check("7.1.2 and decided by false", r[3]["y"], (U, False))

g = formula("when(c, a, b)", {"a": "a", "b": "b", "c": "c"}, {"a": NUM, "b": NUM, "c": BOOL})
r = run(
    g,
    [
        (0, {"c": (G, True), "a": (U, 1.0)}),
        (1, {"c": (U, False), "b": (G, 2.0), "a": (B, None)}),
        (2, {"c": (N, None)}),
    ],
)
check("7.1.3 chosen branch, other not looked at", r[0]["y"], (U, 1.0))
check("7.1.3 worse of branch and condition", r[1]["y"], (U, 2.0))
check("7.1.3 condition not usable", r[2]["y"], (N, None))

g = formula("a / b", {"a": "a", "b": "b"}, {"a": NUM, "b": NUM})
r = run(g, [(0, {"a": (G, 1.0), "b": (G, 0.0)}), (1, {"b": (G, 4.0)})])
check("7.1.4 division by zero", r[0]["y"], (B, None))
check("division", r[1]["y"], (G, 0.25))
g = formula("sqrt(a) + ln(a)", {"a": "a"}, {"a": NUM})
check("7.1.4 sqrt of negative", run(g, [(0, {"a": (G, -1.0)})])[0]["y"], (B, None))
g = formula("a * a", {"a": "a"}, {"a": NUM})
check("7.1.4 not finite", run(g, [(0, {"a": (G, 1e200)})])[0]["y"], (B, None))
g = formula("not a < 2 and -a * 2 == -6", {"a": "a"}, {"a": NUM})
check("precedence of not, comparison, unary minus", run(g, [(0, {"a": (G, 3.0)})])[0]["y"], (G, True))
g = formula("8 - 2 - 1 + pow(2, 3) / 4 / 2 + 1.5e1", {"a": "a"}, {"a": NUM})
refused("every input must be used", g)
g = formula("a * 0 + 8 - 2 - 1 + pow(2, 3) / 4 / 2 + 1.5e1", {"a": 1}, {})
check("left grouping, constant input", run(g, [(0, {})])[0]["y"], (G, 21.0))

refused("comparisons do not chain", formula("a < b < a", {"a": 1, "b": 2}, {}))
refused("name not an input", formula("a + b", {"a": 1}, {}))
refused("type: number and boolean", formula("a + true", {"a": 1}, {}))
refused("number with a leading point", formula("a + .5", {"a": 1}, {}))
refused("function name as input", formula("min + 1", {"min": 1}, {}))
refused("== of two types", formula("a == true", {"a": 1}, {}))

# ---- 7.10 fallback, all_good
g = {
    "period": "1s",
    "inputs": {"a": NUM},
    "blocks": [
        {
            "id": "f",
            "type": "formula",
            "in": {"a": "a"},
            "settings": {"expr": "a + 1"},
            "out": {"y": "y"},
            "fallback": {"y": 9},
        },
        {"id": "g", "type": "all_good", "in": {"p": "y", "q": "f.y"}, "out": {"y": "ok"}},
    ],
}
r = run(g, [(0, {}), (1, {"a": (G, 1.0)})])
check("7.10 fallback is uncertain", r[0]["y"], (U, 9.0))
check("all_good sees the substituted value", r[0]["ok"], (G, False))
check("all_good true", r[1]["ok"], (G, True))

# ---- 6 time
e = Engine(formula("a", {"a": "a"}, {"a": {"max_age": "2s"}}))
e.write("a", G, 5.0, 100.0)
check("6.3 first call runs tick 0", e.tick(100.0), (1, {"y": (G, 5.0)}))
check("6.4 nothing due", e.tick(100.4), (0, None))
check("6.4 nearest tick", e.tick(100.6), (1, {"y": (G, 5.0)}))
check("7.2 age equal to the maximum is usable", e.tick(102.0), (1, {"y": (G, 5.0)}))
check("7.2.4 too old", e.tick(103.0), (1, {"y": (B, None)}))
raises("6.4 now goes backwards", lambda: e.tick(102.0))
e.write("a", G, 6.0, 106.0)
check("6.5 three ticks, last uses the write", e.tick(106.0), (3, {"y": (G, 6.0)}))
e.write("a", G, 7.0, 108.5)
check("7.2.4 sample from the future", e.tick(107.0), (1, {"y": (B, None)}))
e.write("a", G, float("inf"), 108.0)
check("7.2.4 not finite", e.tick(108.0), (1, {"y": (B, None)}))
raises("write to an unknown input", lambda: e.write("zz", G, 1.0, 0.0))

e = Engine(
    formula(
        "a",
        {"a": "a"},
        {
            "a": {"max_age": "2s"},
        },
    )
)
check("7.2.2 not_ready at first", e.tick(0.0)[1]["y"], (N, None))
e.tick(1.0)
check("7.2.2 run for exactly max age", e.tick(2.0)[1]["y"], (N, None))
check("7.2.2 run for longer than max age", e.tick(3.0)[1]["y"], (B, None))
e = Engine(formula("a", {"a": "a"}, {"a": {"initial": 20}}))
check("7.2.2 initial value", e.tick(0.0)[1]["y"], (U, 20.0))

# ---- delay
g = {
    "period": "1s",
    "inputs": {"a": NUM},
    "blocks": [{"id": "d", "type": "delay", "in": {"x": "a"}, "settings": {"ticks": 2}, "out": {"y": "y"}}],
}
r = run(g, [(0, {"a": (G, 1.0)}), (1, {"a": (U, 2.0)}), (2, {"a": (B, None)}), (3, {}), (4, {})])
check("delay before history", r[1]["y"], (N, None))
check("delay by two", r[2]["y"], (G, 1.0))
check("delay keeps state", r[3]["y"], (U, 2.0))
check("delay of a bad input", r[4]["y"], (B, None))

# a counter: a loop through a deferred input
g = {
    "period": "1s",
    "blocks": [
        {"id": "d", "type": "delay", "in": {"x": "n"}, "settings": {"initial": 0}},
        {"id": "f", "type": "formula", "in": {"p": "d.y"}, "settings": {"expr": "p + 1"}, "out": {"y": "n"}},
    ],
}
r = run(g, [(0, {}), (1, {}), (2, {})])
check("5.3 loop through a delay", [x["n"] for x in r], [(G, 1.0), (G, 2.0), (G, 3.0)])
g["blocks"][0]["settings"] = {}
refused("5.4 delay on a loop without initial", g)
refused(
    "5.3 loop of direct inputs",
    {
        "period": "1s",
        "blocks": [
            {"id": "a", "type": "formula", "in": {"p": "b.y"}, "settings": {"expr": "p"}},
            {"id": "b", "type": "formula", "in": {"p": "a.y"}, "settings": {"expr": "p"}},
        ],
    },
)

# ---- window
g = {
    "period": "2s",
    "inputs": {"a": NUM},
    "blocks": [
        {
            "id": "w",
            "type": "window",
            "in": {"x": "a"},
            "settings": {"window": "6s"},
            "out": {p: p for p in ("mean", "median", "min", "max", "spread", "slope", "count")},
        }
    ],
}
r = run(
    g, [(0, {"a": (G, 1.0)}), (2, {"a": (G, 5.0)}), (4, {"a": (G, 3.0)}), (6, {"a": (U, 7.0)}), (8, {"a": (B, None)})]
)
check("7.3.3 filling", r[1]["mean"], (N, None))
check("7.3.6 count", r[1]["count"], (G, 2.0))
check("window mean", r[2]["mean"], (G, 3.0))
check("window median", r[2]["median"], (G, 3.0))
check("window spread", r[2]["spread"], (G, 4.0))
check("window slope per second", r[2]["slope"], (G, 0.5))
check("7.3.4 an uncertain sample", r[3]["max"], (U, 7.0))
check("7.3.3 a hole", r[4]["mean"], (B, None))
g["blocks"][0]["settings"]["min_good"] = 0.25
r = run(g, [(0, {"a": (G, 1.0)}), (2, {"a": (G, 5.0)}), (4, {"a": (B, None)}), (6, {})])
check("7.3.4 one sample is enough at min_good 0.25", r[0]["mean"], (U, 1.0))
check("7.3.4 min_good with a tick before start", r[1]["median"], (U, 3.0))
check("7.3.5 slope of one sample", r[3]["slope"], (B, None))
check("7.3.5 other statistics of one sample", r[3]["mean"], (U, 5.0))
g["blocks"][0]["settings"] = {"window": "5s"}
refused("6.2 window not whole periods", g)

# ---- deadband, lowpass
g = {
    "period": "1s",
    "inputs": {"a": NUM},
    "blocks": [
        {
            "id": "d",
            "type": "deadband",
            "in": {"x": "a"},
            "settings": {"step": 0.5, "ride_through": "1s"},
            "out": {"y": "y"},
        }
    ],
}
r = run(g, [(0, {"a": (G, 1.0)}), (1, {"a": (U, 1.25)}), (2, {"a": (G, 1.5)}), (3, {"a": (B, None)}), (4, {})])
check("7.4.4 first input", r[0]["y"], (G, 1.0))
check("deadband holds, input's state", r[1]["y"], (U, 1.0))
check("deadband step exactly", r[2]["y"], (G, 1.5))
check("7.4.2 ride through", r[3]["y"], (U, 1.5))
check("7.4.2 past ride through", r[4]["y"], (B, None))
g = {
    "period": "1s",
    "inputs": {"a": NUM},
    "blocks": [{"id": "l", "type": "lowpass", "in": {"x": "a"}, "settings": {"tau": "2s"}, "out": {"y": "y"}}],
}
r = run(g, [(0, {"a": (G, 4.0)}), (1, {"a": (G, 0.0)}), (2, {"a": (N, None)})])
check("lowpass first", r[0]["y"], (G, 4.0))
check("lowpass step", r[1]["y"], (G, 4.0 * math.exp(-0.5)))
check("7.4.3 ride_through zero", r[2]["y"], (N, None))

# ---- hysteresis
g = {
    "period": "1s",
    "inputs": {"a": NUM},
    "blocks": [
        {"id": "h", "type": "hysteresis", "in": {"x": "a"}, "settings": {"rise": 2, "fall": 1}, "out": {"y": "y"}}
    ],
}
r = run(
    g, [(0, {"a": (G, 1.5)}), (1, {"a": (G, 2.0)}), (2, {"a": (U, 1.5)}), (3, {"a": (B, None)}), (4, {"a": (G, 1.0)})]
)
check("7.5", [x["y"] for x in r], [(N, None), (G, True), (U, True), (B, None), (G, False)])
g["blocks"][0]["settings"] = {"rise": 1, "fall": 1}
refused("rise more than fall", g)


# ---- held_for
def hf(settings):
    return {
        "period": "1s",
        "inputs": {"a": BOOL},
        "blocks": [{"id": "h", "type": "held_for", "in": {"x": "a"}, "settings": settings, "out": {"y": "y"}}],
    }


r = run(
    hf({"time": "2s", "on_bad": "reset"}),
    [
        (0, {"a": (G, True)}),
        (1, {}),
        (2, {}),
        (3, {"a": (U, True)}),
        (4, {"a": (B, None)}),
        (5, {"a": (G, True)}),
        (6, {"a": (G, False)}),
    ],
)
check(
    "7.6.1 held_for",
    [x["y"] for x in r],
    [(G, False), (G, False), (G, False), (U, True), (B, None), (G, False), (G, False)],
)
r = run(
    hf({"time": "1s", "on_bad": "hold", "hold_limit": "2s"}),
    [
        (0, {"a": (G, True)}),
        (1, {"a": (B, None)}),
        (2, {}),
        (3, {"a": (G, True)}),
        (4, {"a": (N, None)}),
        (5, {}),
        (6, {}),
        (7, {"a": (G, True)}),
    ],
)
check(
    "7.6.1 hold",
    [x["y"] for x in r],
    [(G, False), (U, False), (U, True), (U, True), (U, True), (U, True), (N, None), (G, False)],
)
refused("hold_limit required with hold", hf({"time": "1s", "on_bad": "hold"}))
refused("hold_limit refused without hold", hf({"time": "1s", "on_bad": "reset", "hold_limit": "1s"}))


# ---- since_true
def st(on_bad):
    return {
        "period": "1s",
        "inputs": {"a": BOOL},
        "blocks": [
            {
                "id": "s",
                "type": "since_true",
                "in": {"x": "a"},
                "settings": {"time": "1s", "on_bad": on_bad},
                "out": {"y": "y"},
            }
        ],
    }


steps = [(0, {"a": (G, False)}), (1, {}), (2, {}), (3, {"a": (U, True)}), (4, {"a": (B, None)}), (5, {})]
check(
    "7.6.2 assume_false",
    [x["y"] for x in run(st("assume_false"), steps)],
    [(G, False), (G, False), (G, True), (U, False), (U, False), (U, True)],
)
check(
    "7.6.2 unknown",
    [x["y"] for x in run(st("unknown"), steps)],
    [(G, False), (G, False), (G, True), (U, False), (B, None), (B, None)],
)

# ---- latch
g = {
    "period": "1s",
    "inputs": {"s": BOOL, "r": BOOL},
    "blocks": [{"id": "l", "type": "latch", "in": {"set": "s", "reset": "r"}, "out": {"y": "y"}}],
}
r = run(
    g,
    [
        (0, {}),
        (1, {"s": (U, False)}),
        (2, {"s": (U, True)}),
        (3, {"s": (B, None)}),
        (4, {"s": (G, True), "r": (G, True)}),
        (5, {"r": (B, None)}),
    ],
)
check("7.6.3 latch", [x["y"] for x in r], [(N, None), (U, False), (G, True), (G, True), (G, False), (G, True)])

# ---- integrate
g = {
    "period": "2s",
    "inputs": {"a": NUM, "r": BOOL},
    "blocks": [
        {
            "id": "i",
            "type": "integrate",
            "in": {"x": "a", "reset": "r"},
            "settings": {"max_missed": "2s"},
            "out": {"y": "y", "missed": "m"},
        }
    ],
}
r = run(g, [(0, {"a": (G, 1.5)}), (2, {}), (4, {"a": (B, None)}), (6, {}), (8, {"a": (G, 1.0), "r": (G, True)})])
check("7.7.1", r[0]["y"], (G, 3.0))
check("7.7.1 again", r[1]["y"], (G, 6.0))
check("7.7.3 missed makes it uncertain", r[2]["y"], (U, 6.0))
check("7.7.2 missed", r[2]["m"], (G, 2.0))
check("7.7.4 max_missed", r[3]["y"], (B, None))
check("7.7.5 reset before the addition", r[4]["y"], (G, 2.0))
check("7.7.5 missed after reset", r[4]["m"], (G, 0.0))

# ---- kalman1
g = {
    "period": "1s",
    "inputs": {"z": NUM},
    "blocks": [
        {
            "id": "k",
            "type": "kalman1",
            "in": {"z": "z", "model": 0},
            "settings": {"tau": "1s", "q": 1, "r": 1, "max_coast": "1s"},
            "out": {"x": "x", "sigma": "s"},
        }
    ],
}
a = math.exp(-1.0)
r = run(g, [(0, {}), (1, {"z": (G, 2.0)}), (2, {}), (3, {}), (4, {"z": (U, 2.0)})])
check("7.9.1 not_ready", r[0]["x"], (N, None))
check("B first measurement", (r[1]["x"], r[1]["s"]), ((G, 2.0), (G, 1.0)))
check("7.9.2 standing measurement not used twice", r[2]["x"], (G, 2.0 * a))
check("B variance on predict", r[2]["s"], (G, math.sqrt(a * a + 1.0)))
check("7.9.4 coasted too long", r[3]["x"], (U, 2.0 * a * a))
v = a * a * (a * a * (a * a + 1.0) + 1.0) + 1.0
x = 2.0 * a * a * a
check("B correct, 7.9.4 uncertain measurement", r[4]["x"], (U, x + v / (v + 1.0) * (2.0 - x)))

# ---- 8 save, restore, reset
g = {
    "period": "1s",
    "inputs": {"a": NUM},
    "blocks": [{"id": "i", "type": "integrate", "in": {"x": "a"}, "out": {"y": "y"}}],
}
e = Engine(g)
e.write("a", G, 1.0, 0.0)
e.tick(0.0)
e.tick(1.0)
saved = e.save()
e.tick(2.0)
e.restore(saved)
check("8.4 restore runs one tick and does not catch up", e.tick(500.0), (1, {"y": (G, 3.0)}))
e.reset()
check("8.1 reset", e.tick(0.0), (1, {"y": (U, 0.0)}))
other = Engine(formula("a", {"a": "a"}, {"a": NUM}))
raises("8.3 state from another graph", lambda: other.restore(saved))
check("inputs container", ("a" in e.inputs, "y" in e.inputs), (True, False))

# ---- 9 compile errors
ok = {
    "period": "1s",
    "inputs": {"a": NUM, "b": BOOL},
    "blocks": [{"id": "w", "type": "lowpass", "in": {"x": "a"}, "settings": {"tau": "1s"}}],
}
Engine(ok)


def variant(**kw):
    import copy

    g2 = copy.deepcopy(ok)
    for key, val in kw.items():
        if key == "top":
            g2.update(val)
        else:
            g2["blocks"][0][key] = val
    return g2


refused("unknown top key", variant(top={"rules": []}))
refused("unknown block key", variant(note="x"))
refused("unknown input key", variant(top={"inputs": {"a": {"kind": "number"}}}))
refused("unknown block type", variant(type="highpass"))
refused("unknown port in in", variant(**{"in": {"x": "a", "q": "a"}}))
refused("unknown port in out", variant(out={"z": "s"}))
refused("unknown port in fallback", variant(fallback={"z": 1}))
refused("required input unconnected", variant(**{"in": {}}))
refused("signal of the other type", variant(**{"in": {"x": "b"}}))
refused("constant of the other type", variant(**{"in": {"x": True}}))
refused("unknown setting", variant(settings={"tau": "1s", "gain": 2}))
refused("setting of the wrong type", variant(settings={"tau": 1}))
refused("setting out of range", variant(settings={"tau": "0s"}))
refused("missing required setting", variant(settings={}))
refused("unknown signal", variant(**{"in": {"x": "nope"}}))
refused("two writers", variant(out={"y": "a"}))
refused("bad time unit", variant(settings={"tau": "1 s"}))
refused("no id", {"period": "1s", "blocks": [{"type": "latch", "in": {"set": True}}]})
refused(
    "duplicate id",
    {
        "period": "1s",
        "blocks": [
            {"id": "l", "type": "latch", "in": {"set": True}},
            {"id": "l", "type": "latch", "in": {"set": True}},
        ],
    },
)

print("%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)

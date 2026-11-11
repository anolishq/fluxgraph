"""Checks of impl.py, each worked out by hand from the proposal."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from impl import CompileError, Engine  # noqa: E402

PASSED = 0
FAILED = 0


def close(a, b):
    if a is None or b is None or isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def check(label, got, want):
    """got and want are (state, value) tuples, or plain values."""
    global PASSED, FAILED
    if isinstance(want, tuple) and isinstance(want[0], str):
        ok = isinstance(got, tuple) and got[0] == want[0] and close(got[1], want[1])
    else:
        ok = got == want
    if ok:
        PASSED += 1
    else:
        FAILED += 1
        print("FAIL %s: got %r, want %r" % (label, got, want))


def refused(label, graph):
    global PASSED, FAILED
    try:
        Engine(graph)
    except CompileError:
        PASSED += 1
        return
    FAILED += 1
    print("FAIL %s: the graph was accepted" % label)


def raises(label, fn):
    """fn must raise something that is not a CompileError."""
    global PASSED, FAILED
    try:
        fn()
    except CompileError:
        pass
    except Exception:
        PASSED += 1
        return
    FAILED += 1
    print("FAIL %s: no refusal" % label)


def integ_graph(**top):
    g = {
        "period": "1s",
        "inputs": {"x": {"max_age": "10s"}},
        "blocks": [{"id": "i", "type": "integrate", "in": {"x": "x"}, "out": {"y": "y", "missed": "missed"}}],
    }
    g.update(top)
    return g


def test_catch_up():
    e = Engine(integ_graph())
    check("inputs", "x" in e.inputs, True)
    ran, o = e.tick(0.0)
    check("cu ran0", ran, 1)
    check("cu y0", o["y"], ("uncertain", 0.0))
    check("cu missed0", o["missed"], ("good", 1.0))
    e.write("x", "good", 3.0, 2.9)
    ran, o = e.tick(3.0)
    check("cu ran3", ran, 3)
    # ticks 1 and 2 are catch-up ticks and see nothing; tick 3 adds 3
    check("cu y3", o["y"], ("uncertain", 3.0))
    check("cu missed3", o["missed"], ("good", 3.0))
    check("cu none due", e.tick(3.4), (0, None))
    ran, o = e.tick(3.5)
    check("cu ran half", ran, 1)
    check("cu y4", o["y"], ("uncertain", 6.0))
    raises("cu backwards", lambda: e.tick(3.0))
    raises("cu nan", lambda: e.tick(float("nan")))
    check("cu same now", e.tick(3.5), (0, None))
    # a write made before a call that runs no tick waits for the next
    e.write("x", "good", 10.0, 4.0)
    check("cu no tick", e.tick(3.6), (0, None))
    ran, o = e.tick(5.0)
    check("cu y5", o["y"], ("uncertain", 16.0))


def test_age():
    g = {
        "period": "1s",
        "inputs": {"x": {"max_age": "2s"}},
        "blocks": [{"id": "f", "type": "formula", "in": {"a": "x"}, "settings": {"expr": "a * 2"}, "out": {"y": "y"}}],
    }
    e = Engine(g)
    e.write("x", "good", 1.5, 0.0)
    check("age t0", e.tick(0.0)[1]["y"], ("good", 3.0))
    check("age t2", e.tick(2.0)[1]["y"], ("good", 3.0))
    check("age t3", e.tick(3.0)[1]["y"], ("bad", None))
    # stamped too far ahead: refused, and stays refused
    e.write("x", "good", 1.0, 9.0)
    check("ahead t4", e.tick(4.0)[1]["y"], ("bad", None))
    check("ahead t9", e.tick(9.0)[1]["y"], ("bad", None))
    e.write("x", "good", float("inf"), 10.0)
    check("inf", e.tick(10.0)[1]["y"], ("bad", None))
    # nothing standing: not_ready, then bad once run for more than max_age
    e2 = Engine(g)
    check("nr t0", e2.tick(0.0)[1]["y"], ("not_ready", None))
    check("nr t2", e2.tick(2.0)[1]["y"], ("not_ready", None))
    check("nr t3", e2.tick(3.0)[1]["y"], ("bad", None))


def test_gap():
    e = Engine(integ_graph(max_catch_up=3))
    e.write("x", "good", 1.0, 0.0)
    check("gap y0", e.tick(0.0)[1]["y"], ("good", 1.0))
    ran, o = e.tick(10.0)
    check("gap ran", ran, 1)
    check("gap y", o["y"], ("uncertain", 1.0))
    check("gap missed", o["missed"], ("good", 1.0))
    e.write("x", "good", 1.0, 11.0)
    ran, o = e.tick(11.0)
    check("gap next ran", ran, 1)
    check("gap next y", o["y"], ("uncertain", 2.0))
    check("gap three", e.tick(14.0)[0], 3)


def test_save_restore():
    g = {"period": "1s", "blocks": [{"id": "i", "type": "integrate", "in": {"x": 1}, "out": {"y": "y"}}]}
    e = Engine(g)
    check("sr y0", e.tick(0.0)[1]["y"], ("good", 1.0))
    check("sr y1", e.tick(1.0)[1]["y"], ("good", 2.0))
    saved = e.save()
    check("sr y2", e.tick(2.0)[1]["y"], ("good", 3.0))
    e.restore(saved)
    ran, o = e.tick(0.5)  # a gap: any now, one tick
    check("sr ran", ran, 1)
    check("sr y", o["y"], ("uncertain", 3.0))
    # the next tick is at 1.5, due once now is within half a period of it
    check("sr none due", e.tick(0.9), (0, None))
    check("sr y next", e.tick(1.0)[1]["y"], ("uncertain", 4.0))
    other = Engine(integ_graph())
    raises("sr other graph", lambda: other.restore(saved))
    e.reset()
    check("reset", e.tick(0.0), (1, {"y": ("good", 1.0)}))


def test_sample_times():
    win = {"window": "2s", "min_good": 0.5, "only_new": True}
    g = {
        "period": "1s",
        "inputs": {"x": {"max_age": "none"}, "z": {"max_age": "none", "initial": 0}},
        "blocks": [
            {"id": "f", "type": "formula", "in": {"a": "x"}, "settings": {"expr": "a * 1"}},
            {"id": "d", "type": "delay", "in": {"x": "f.y"}},
            {"id": "g", "type": "formula", "in": {"a": "x", "b": "z"}, "settings": {"expr": "a + b * 0"}},
            {
                "id": "h",
                "type": "formula",
                "in": {"a": "x", "b": "z"},
                "settings": {"expr": "a + b * 0", "sample_of": "a"},
            },
            {"id": "w1", "type": "window", "in": {"x": "f.y"}, "settings": win, "out": {"count": "c1"}},
            {"id": "w2", "type": "window", "in": {"x": "d.y"}, "settings": win, "out": {"count": "c2"}},
            {"id": "w3", "type": "window", "in": {"x": "g.y"}, "settings": win, "out": {"count": "c3"}},
            {"id": "w4", "type": "window", "in": {"x": "h.y"}, "settings": win, "out": {"count": "c4"}},
        ],
    }
    e = Engine(g)
    e.write("x", "good", 1.0, 0.0)
    want = [(1, 0, 1, 1), (1, 1, 2, 1), (0, 1, 2, 0), (0, 0, 2, 0)]
    for k, w in enumerate(want):
        o = e.tick(float(k))[1]
        for name, n in zip(("c1", "c2", "c3", "c4"), w):
            check("st %s tick %d" % (name, k), o[name], ("good", float(n)))


def test_lowpass():
    g = {
        "period": "1s",
        "inputs": {"x": {"max_age": "none"}},
        "blocks": [
            {
                "id": "lp",
                "type": "lowpass",
                "in": {"x": "x"},
                "settings": {"tau": "1s", "ride_through": "1s"},
                "out": {"y": "y"},
            }
        ],
    }
    e = Engine(g)
    a = math.exp(-1.0)

    def step(k, state, value):
        e.write("x", state, value, float(k) if value is not None else None)
        return e.tick(float(k))[1]["y"]

    check("lp 0", step(0, "good", 0.0), ("good", 0.0))
    y = 1 - a
    check("lp 1", step(1, "good", 1.0), ("good", y))
    y = a * y + (1 - a)
    check("lp 2", step(2, "uncertain", 1.0), ("uncertain", y))
    y = a * y + (1 - a)
    check("lp 3", step(3, "good", 1.0), ("uncertain", y))
    y = a * y + (1 - a)
    check("lp 4", step(4, "good", 1.0), ("uncertain", y))
    y = a * y + (1 - a)
    check("lp 5", step(5, "good", 1.0), ("good", y))
    check("lp 6", step(6, "bad", None), ("uncertain", y))
    y = a * a * y + (1 - a * a)
    check("lp 7", step(7, "good", 1.0), ("uncertain", y))
    check("lp 8", step(8, "bad", None), ("uncertain", y))
    check("lp 9", step(9, "bad", None), ("bad", None))
    check("lp 10", step(10, "good", 2.0), ("good", 2.0))


def run_seq(block, in_type, seq, port="y"):
    """One input `x`, one block reading it; seq is [(state, value)]."""
    g = {
        "period": "1s",
        "inputs": {"x": {"type": in_type, "max_age": "none"}},
        "blocks": [dict(block, id="b", out={port: "out"})],
    }
    e = Engine(g)
    res = []
    for k, (state, value) in enumerate(seq):
        e.write("x", state, value, float(k) if value is not None else None)
        res.append(e.tick(float(k))[1]["out"])
    return res


def test_hysteresis():
    got = run_seq(
        {"type": "hysteresis", "in": {"x": "x"}, "settings": {"rise": 10, "fall": 5}},
        "number",
        [
            ("good", 7.0),
            ("good", 10.0),
            ("good", 7.0),
            ("bad", None),
            ("good", 7.0),
            ("uncertain", 12.0),
            ("good", 7.0),
            ("good", 5.0),
        ],
    )
    want = [
        ("not_ready", None),
        ("good", True),
        ("good", True),
        ("bad", None),
        ("uncertain", True),
        ("uncertain", True),
        ("uncertain", True),
        ("good", False),
    ]
    for k, (g_, w) in enumerate(zip(got, want)):
        check("hyst %d" % k, g_, w)


def test_latch():
    got = run_seq(
        {"type": "latch", "in": {"set": "x"}},
        "boolean",
        [
            ("good", False),
            ("uncertain", False),
            ("good", False),
            ("bad", None),
            ("good", True),
            ("bad", None),
            ("uncertain", True),
        ],
    )
    want = [
        ("good", False),
        ("uncertain", False),
        ("uncertain", False),
        ("bad", None),
        ("good", True),
        ("good", True),
        ("good", True),
    ]
    for k, (g_, w) in enumerate(zip(got, want)):
        check("latch %d" % k, g_, w)
    # an uncertain set of a latch that was not set leaves it not sure
    got = run_seq(
        {"type": "latch", "in": {"set": "x"}}, "boolean", [("uncertain", True), ("good", False), ("good", True)]
    )
    want = [("uncertain", True), ("uncertain", True), ("good", True)]
    for k, (g_, w) in enumerate(zip(got, want)):
        check("latch unc %d" % k, g_, w)
    # reset wins over set
    got = run_seq(
        {"type": "latch", "in": {"set": True, "reset": "x"}},
        "boolean",
        [("good", False), ("good", True), ("bad", None)],
    )
    want = [("good", True), ("good", False), ("good", True)]
    for k, (g_, w) in enumerate(zip(got, want)):
        check("latch reset %d" % k, g_, w)


def test_integrate():
    got = run_seq(
        {"type": "integrate", "in": {"x": "x"}, "settings": {"tolerance": 0.25}},
        "number",
        [("good", 1.0), ("good", 1.0), ("good", 1.0), ("bad", None), ("bad", None)],
    )
    want = [
        ("good", 1.0),
        ("good", 2.0),
        ("good", 3.0),
        ("good", 3.0),  # 1 missed of 4 run: not more than 0.25 * 4
        ("uncertain", 3.0),
    ]  # 2 missed of 5 run
    for k, (g_, w) in enumerate(zip(got, want)):
        check("integ %d" % k, g_, w)
    got = run_seq(
        {"type": "integrate", "in": {"x": "x"}, "settings": {"per": "1m", "max_missed": "1s"}},
        "number",
        [("good", 60.0), ("bad", None), ("bad", None), ("uncertain", 60.0)],
    )
    want = [("good", 1.0), ("uncertain", 1.0), ("bad", None), ("bad", None)]
    for k, (g_, w) in enumerate(zip(got, want)):
        check("integ max_missed %d" % k, g_, w)


def test_timers():
    got = run_seq(
        {"type": "held_for", "in": {"x": "x"}, "settings": {"time": "2s", "on_bad": "reset"}},
        "boolean",
        [("good", True)] * 4 + [("bad", None), ("good", True)],
    )
    want = [("good", False)] * 3 + [("good", True), ("bad", None), ("good", False)]
    for k, (g_, w) in enumerate(zip(got, want)):
        check("held_for %d" % k, g_, w)
    got = run_seq(
        {"type": "held_for", "in": {"x": "x"}, "settings": {"time": "2s", "on_bad": "hold", "hold_limit": "1s"}},
        "boolean",
        [("good", True), ("good", True), ("bad", None), ("good", True), ("bad", None), ("bad", None)],
    )
    want = [
        ("good", False),
        ("good", False),
        ("uncertain", False),
        ("uncertain", True),
        ("uncertain", True),
        ("bad", None),
    ]
    for k, (g_, w) in enumerate(zip(got, want)):
        check("held_for hold %d" % k, g_, w)
    got = run_seq(
        {"type": "since_true", "in": {"x": "x"}, "settings": {"time": "2s", "on_bad": "assume_false"}},
        "boolean",
        [("good", False)] * 4 + [("uncertain", True)] + [("good", False)] * 4,
    )
    want = [("good", False)] * 3 + [
        ("good", True),
        ("uncertain", False),
        ("uncertain", False),
        ("uncertain", False),
        ("good", True),
        ("good", True),
    ]
    for k, (g_, w) in enumerate(zip(got, want)):
        check("since_true %d" % k, g_, w)


def test_deadband_window():
    got = run_seq(
        {"type": "deadband", "in": {"x": "x"}, "settings": {"step": 1}},
        "number",
        [("good", 0.0), ("good", 0.5), ("uncertain", 0.75), ("good", 1.0), ("bad", None)],
    )
    want = [("good", 0.0), ("good", 0.0), ("uncertain", 0.0), ("good", 1.0), ("bad", None)]
    for k, (g_, w) in enumerate(zip(got, want)):
        check("deadband %d" % k, g_, w)
    seq = [("good", 1.0), ("good", 2.0), ("good", 4.0), ("uncertain", 4.0)]
    blk = {"type": "window", "in": {"x": "x"}, "settings": {"window": "3s"}}
    for port, w2, w3 in (
        ("mean", 7.0 / 3, 10.0 / 3),
        ("median", 2.0, 4.0),
        ("min", 1.0, 2.0),
        ("max", 4.0, 4.0),
        ("spread", 3.0, 2.0),
        ("slope", 1.5, 1.0),
    ):
        got = run_seq(blk, "number", seq, port)
        check("window %s 0" % port, got[0], ("not_ready", None))
        check("window %s 2" % port, got[2], ("good", w2))
        check("window %s 3" % port, got[3], ("uncertain", w3))
    got = run_seq(blk, "number", seq, "count")
    check("window count 0", got[0], ("good", 1.0))
    check("window count 2", got[2], ("good", 3.0))


def test_formula():
    def one(expr, ins, inputs):
        g = {
            "period": "1s",
            "inputs": inputs,
            "blocks": [{"id": "f", "type": "formula", "in": ins, "settings": {"expr": expr}, "out": {"y": "y"}}],
        }
        return Engine(g)

    num = {"x": {"max_age": "none"}, "ok": {"type": "boolean", "max_age": "none"}}
    e = one("when(ok, x, 20)", {"ok": "ok", "x": "x"}, num)
    e.write("ok", "good", False, 0.0)
    e.write("x", "bad", None, None)
    check("when const", e.tick(0.0)[1]["y"], ("good", 20.0))
    e.write("ok", "uncertain", True, 1.0)
    check("when bad branch", e.tick(1.0)[1]["y"], ("bad", None))
    e.write("x", "good", 4.0, 2.0)
    check("when unc cond", e.tick(2.0)[1]["y"], ("uncertain", 4.0))

    e = one("ok or x > 1", {"ok": "ok", "x": "x"}, num)
    e.write("ok", "good", True, 0.0)
    check("or decides", e.tick(0.0)[1]["y"], ("good", True))
    e.write("ok", "uncertain", True, 1.0)
    e.write("x", "good", 0.0, 1.0)
    check("or unc decides", e.tick(1.0)[1]["y"], ("uncertain", True))
    e.write("ok", "good", False, 2.0)
    e.write("x", "bad", None, None)
    check("or undecided", e.tick(2.0)[1]["y"], ("bad", None))

    e = one("1 / x + 2 * -3", {"x": "x"}, num and {"x": num["x"]})
    e.write("x", "good", 0.0, 0.0)
    check("div zero", e.tick(0.0)[1]["y"], ("bad", None))
    e.write("x", "good", 4.0, 1.0)
    check("arith", e.tick(1.0)[1]["y"], ("good", -5.75))

    e = one("not 1 + 2 * 3 == 7 and pow(2, 3) - 1 >= 7 or sqrt(a) < ln(a)", {"a": -1}, {})
    # not (7 == 7) -> false; false and ... -> false (decided, good);
    # sqrt(-1) is bad, so the `or` is not decided and takes the worst state
    check("precedence", e.tick(0.0)[1]["y"], ("bad", None))

    # a fallback replaces what is not usable, as uncertain
    g = {
        "period": "1s",
        "inputs": {"x": {"max_age": "none"}},
        "blocks": [
            {
                "id": "f",
                "type": "formula",
                "in": {"a": "x"},
                "settings": {"expr": "a * 2"},
                "fallback": {"y": 0},
                "out": {"y": "y"},
            },
            {"id": "ag", "type": "all_good", "in": {"p": "y", "q": 1}, "out": {"y": "ok"}},
        ],
    }
    e = Engine(g)
    o = e.tick(0.0)[1]
    check("fallback", o["y"], ("uncertain", 0.0))
    check("all_good false", o["ok"], ("good", False))
    e.write("x", "good", 2.0, 1.0)
    o = e.tick(1.0)[1]
    check("no fallback", o["y"], ("good", 4.0))
    check("all_good true", o["ok"], ("good", True))


def test_loops():
    # a counter: a formula and a delay with an initial value
    g = {
        "period": "1s",
        "blocks": [
            {"id": "d", "type": "delay", "in": {"x": "n"}, "settings": {"initial": 0}},
            {"id": "f", "type": "formula", "in": {"p": "d.y"}, "settings": {"expr": "p + 1"}, "out": {"y": "n"}},
        ],
    }
    e = Engine(g)
    for k in range(3):
        check("counter %d" % k, e.tick(float(k))[1]["n"], ("good", float(k + 1)))
    del g["blocks"][0]["settings"]["initial"]
    refused("delay loop with no initial", g)
    refused(
        "direct loop",
        {
            "period": "1s",
            "blocks": [
                {"id": "a", "type": "formula", "in": {"p": "b.y"}, "settings": {"expr": "p + 1"}},
                {"id": "b", "type": "formula", "in": {"p": "a.y"}, "settings": {"expr": "p + 1"}},
            ],
        },
    )

    # a thermal mass and a thermostat formula that read each other
    g = {
        "period": "1s",
        "blocks": [
            {
                "id": "plant",
                "type": "thermal_mass",
                "in": {"power": "heat", "ambient": 20},
                "settings": {"thermal_mass": 100, "heat_transfer": 1, "initial": 20},
                "out": {"temp": "temp"},
            },
            {
                "id": "ctl",
                "type": "formula",
                "in": {"t": "temp"},
                "settings": {"expr": "when(t < 30, 100, 0)"},
                "out": {"y": "heat"},
            },
        ],
    }
    e = Engine(g)
    o = e.tick(0.0)[1]
    check("model 0", o["temp"], ("good", 20.0))
    check("model heat", o["heat"], ("good", 100.0))
    # d temp/dt = -(temp - 120)/100; RK4 on a linear equation multiplies
    # the distance from 120 by 1 + z + z^2/2 + z^3/6 + z^4/24, z = -0.01
    z = -0.01
    s = 1 + z + z**2 / 2 + z**3 / 6 + z**4 / 24
    check("model 1", e.tick(1.0)[1]["temp"], ("good", 120 - 100 * s))
    check("model 2", e.tick(2.0)[1]["temp"], ("good", 120 - 100 * s * s))

    # a missed step is a doubt, seen from the next tick, for `settle`
    g = {
        "period": "1s",
        "inputs": {"p": {"max_age": "none"}},
        "blocks": [
            {
                "id": "plant",
                "type": "thermal_mass",
                "in": {"power": "p", "ambient": 20},
                "settings": {"thermal_mass": 10, "heat_transfer": 1, "initial": 20, "settle": "2s"},
                "out": {"temp": "temp"},
            }
        ],
    }
    e = Engine(g)
    check("doubt 0", e.tick(0.0)[1]["temp"], ("good", 20.0))
    e.write("p", "good", 0.0, 1.0)
    check("doubt 1", e.tick(1.0)[1]["temp"], ("uncertain", 20.0))
    check("doubt 2", e.tick(2.0)[1]["temp"], ("good", 20.0))
    refused(
        "unstable",
        {
            "period": "30s",
            "blocks": [
                {
                    "id": "plant",
                    "type": "thermal_mass",
                    "in": {"power": 0, "ambient": 20},
                    "settings": {"thermal_mass": 10, "heat_transfer": 1, "initial": 20},
                }
            ],
        },
    )

    # a state-space block with D not zero reads u at the same tick
    g = {
        "period": "1s",
        "inputs": {"u": {"max_age": "none"}},
        "blocks": [
            {
                "id": "ss",
                "type": "state_space",
                "in": {"u": "u"},
                "settings": {"A": [[0.5]], "B": [1], "C": [2], "D": 1},
                "out": {"y": "y"},
            }
        ],
    }
    e = Engine(g)
    e.write("u", "good", 1.0, 0.0)
    check("ss 0", e.tick(0.0)[1]["y"], ("good", 1.0))
    check("ss 1", e.tick(1.0)[1]["y"], ("good", 3.0))
    check("ss 2", e.tick(2.0)[1]["y"], ("good", 4.0))


def test_estimator():
    g = {
        "period": "1s",
        "inputs": {"z": {"max_age": "none"}},
        "blocks": [
            {
                "id": "est",
                "type": "estimator",
                "in": {"u": 0, "z": "z"},
                "settings": {
                    "model": {"type": "state_space", "A": [[1]], "B": [0], "C": [1]},
                    "q": {"x0": 1},
                    "p0": {"x0": 4},
                    "measure": {"z": {"of": "x0", "r": 1}},
                    "gate": 3,
                },
                "out": {
                    "x0": "x",
                    "sigma_x0": "sigma",
                    "innovation_z": "innov",
                    "refused_z": "refused",
                    "since_z": "since",
                },
            }
        ],
    }
    e = Engine(g)
    # tick 0: no predict. P = 4, z = 5: innovation 5, s = 5, g = 0.8
    e.write("z", "good", 5.0, 0.0)
    o = e.tick(0.0)[1]
    check("est x 0", o["x"], ("good", 4.0))
    check("est sigma 0", o["sigma"], ("good", math.sqrt(0.8)))
    check("est innov 0", o["innov"], ("good", 5.0))
    check("est refused 0", o["refused"], ("good", 0.0))
    check("est since 0", o["since"], ("good", 0.0))
    # tick 1: predict only; the same sample is not considered again
    o = e.tick(1.0)[1]
    check("est x 1", o["x"], ("good", 4.0))
    check("est sigma 1", o["sigma"], ("good", math.sqrt(1.8)))
    check("est innov 1", o["innov"], ("not_ready", None))
    check("est since 1", o["since"], ("good", 1.0))
    # tick 2: P = 2.8, s = 3.8, innovation 96 > 3 sqrt(3.8): refused
    e.write("z", "good", 100.0, 2.0)
    o = e.tick(2.0)[1]
    check("est x 2", o["x"], ("good", 4.0))
    check("est sigma 2", o["sigma"], ("good", math.sqrt(2.8)))
    check("est innov 2", o["innov"], ("good", 96.0))
    check("est refused 2", o["refused"], ("good", 1.0))
    check("est since 2", o["since"], ("good", 2.0))
    # tick 3: P = 3.8, s = 4.8, innovation 1: used
    e.write("z", "good", 5.0, 3.0)
    o = e.tick(3.0)[1]
    gain = 3.8 / 4.8
    check("est x 3", o["x"], ("good", 4.0 + gain))
    check("est sigma 3", o["sigma"], ("good", math.sqrt(3.8 - gain * 3.8)))
    check("est since 3", o["since"], ("good", 0.0))
    # an uncertain measurement is not considered unless asked for
    e.write("z", "uncertain", 9.0, 4.0)
    o = e.tick(4.0)[1]
    check("est innov 4", o["innov"], ("not_ready", None))
    check("est since 4", o["since"], ("good", 1.0))


def test_refusals():
    ok = {
        "period": "1s",
        "inputs": {"x": {"max_age": "5s"}},
        "blocks": [{"id": "w", "type": "window", "in": {"x": "x"}, "settings": {"window": "3s"}, "out": {"mean": "m"}}],
    }
    Engine(ok)

    def variant(**change):
        g = {"period": ok["period"], "inputs": {"x": dict(ok["inputs"]["x"])}, "blocks": [dict(ok["blocks"][0])]}
        for key, v in change.items():
            if key in ("period", "extra"):
                g[key] = v
            elif key == "input":
                g["inputs"]["x"] = v
            else:
                g["blocks"][0][key] = v
        return g

    refused("unknown top key", variant(extra=1))
    refused("unknown block key", variant(colour="red"))
    refused("unknown type", variant(type="windmill"))
    refused("no max_age", variant(input={"type": "number"}))
    refused("unknown input key", variant(input={"max_age": "1s", "x": 1}))
    refused("not whole periods", variant(settings={"window": "2500ms"}))
    refused("no unit", variant(settings={"window": 3}))
    refused("unknown setting", variant(settings={"window": "3s", "n": 1}))
    refused("missing setting", variant(settings={}))
    refused("out of range", variant(settings={"window": "3s", "min_good": 0}))
    refused("unknown signal", variant(**{"in": {"x": "nope"}}))
    refused("unknown in port", variant(**{"in": {"x": "x", "q": "x"}}))
    refused("unconnected", variant(**{"in": {}}))
    refused("unknown out port", variant(out={"nope": "m"}))
    refused("writes an input", variant(out={"mean": "x"}))
    refused("dotted name", variant(out={"mean": "w.max"}))
    refused("wrong type", variant(input={"type": "boolean", "max_age": "1s"}))
    refused("bad fallback", variant(fallback={"mean": True}))
    refused("period not exact", variant(period="900.0000001ms", settings={"window": "2700ms"}))
    Engine(variant(period="0.1s", settings={"window": "0.3s"}))

    def formula(expr, ins=None):
        return {
            "period": "1s",
            "blocks": [
                {
                    "id": "f",
                    "type": "formula",
                    "in": ins if ins is not None else {"a": 1, "b": 2, "c": 3},
                    "settings": {"expr": expr},
                }
            ],
        }

    Engine(formula("a < b and b < c"))
    refused("chained comparison", formula("a < b < c"))
    refused("unused input", formula("a + b"))
    refused("unknown name", formula("a + b + c + d"))
    refused("type", formula("a + (b < c)"))
    refused("number", formula("a + b + c + 1."))
    refused("hex", formula("a + b + c + 0x10"))
    refused("too large", formula("a + b + c + 1e999"))
    refused("empty", formula("  ", {"a": 1}))
    refused(
        "two writers",
        {
            "period": "1s",
            "blocks": [
                {"id": "f", "type": "formula", "in": {"a": 1}, "settings": {"expr": "a"}, "out": {"y": "s"}},
                {"id": "g", "type": "formula", "in": {"a": 1}, "settings": {"expr": "a"}, "out": {"y": "s"}},
            ],
        },
    )
    refused(
        "hold_limit without hold",
        {
            "period": "1s",
            "blocks": [
                {
                    "id": "h",
                    "type": "held_for",
                    "in": {"x": True},
                    "settings": {"time": "1s", "on_bad": "reset", "hold_limit": "1s"},
                }
            ],
        },
    )


for name, fn in sorted(globals().items()):
    if name.startswith("test_") and callable(fn):
        fn()
print("%d passed, %d failed" % (PASSED, FAILED))
sys.exit(1 if FAILED else 0)

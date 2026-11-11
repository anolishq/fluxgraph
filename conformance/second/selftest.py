"""Checks of impl.py, each worked out by hand from the proposal."""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from impl import CompileError, Engine  # noqa: E402

PASSED = 0
FAILED = 0

S = 10**9  # one second, in nanoseconds


def ns(seconds):
    """A time in whole nanoseconds, from seconds."""
    return int(round(seconds * S))


def info(gap, tick, time, thrown=0, waiting=0):
    """What a call that ran a tick reports (rule 6.10)."""
    return {"gap": gap, "tick": tick, "time": time, "thrown": thrown, "waiting": waiting}


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
    ran, o = e.tick(ns(0.0))
    check("cu ran0", ran, 1)
    check("cu y0", o["y"], ("uncertain", 0.0))
    check("cu missed0", o["missed"], ("good", 1.0))
    e.write("x", "good", 3.0, ns(2.9))
    ran, o = e.tick(ns(3.0))
    check("cu ran3", ran, 3)
    # the write is stamped 2.9 s: ticks 1 and 2 are before it and see
    # nothing; tick 3 is the first at or after it, and adds 3
    check("cu y3", o["y"], ("uncertain", 3.0))
    check("cu missed3", o["missed"], ("good", 3.0))
    check("cu info3", e.info, info(False, 3, 3 * S))
    check("cu none due", e.tick(ns(3.4)), (0, None))
    check("cu none due, one ns short", e.tick(ns(3.5) - 1), (0, None))
    ran, o = e.tick(ns(3.5))  # exactly half a period before tick 4
    check("cu ran half", ran, 1)
    check("cu y4", o["y"], ("uncertain", 6.0))
    check("cu info4", e.info, info(False, 4, 4 * S))
    raises("cu backwards", lambda: e.tick(ns(3.0)))
    raises("cu nan", lambda: e.tick(float("nan")))
    check("cu same now", e.tick(ns(3.5)), (0, None))
    # a write made before a call that runs no tick waits for the next
    e.write("x", "good", 10.0, ns(4.0))
    check("cu no tick", e.tick(ns(3.6)), (0, None))
    check("cu no tick info", e.info, None)
    ran, o = e.tick(ns(5.0))
    check("cu y5", o["y"], ("uncertain", 16.0))


def test_age():
    g = {
        "period": "1s",
        "inputs": {"x": {"max_age": "2s"}},
        "blocks": [{"id": "f", "type": "formula", "in": {"a": "x"}, "settings": {"expr": "a * 2"}, "out": {"y": "y"}}],
    }
    e = Engine(g)
    e.write("x", "good", 1.5, ns(0.0))
    check("age t0", e.tick(ns(0.0))[1]["y"], ("good", 3.0))
    check("age t2", e.tick(ns(2.0))[1]["y"], ("good", 3.0))
    check("age t3", e.tick(ns(3.0))[1]["y"], ("bad", None))
    # stamped 9 s at a call at 4 s, more than max_ahead (one period) ahead:
    # done with at that call, and it never stands, even when 9 s comes
    e.write("x", "good", 1.0, ns(9.0))
    check("ahead t4", e.tick(ns(4.0))[1]["y"], ("bad", None))
    check("ahead t8", e.tick(ns(8.0))[1]["y"], ("bad", None))
    check("ahead t9", e.tick(ns(9.0))[1]["y"], ("bad", None))
    e.write("x", "good", float("inf"), 10 * S)
    check("inf", e.tick(ns(10.0))[1]["y"], ("bad", None))
    # one ns after tick 11 it waits for tick 12; no tolerance on an age
    e.write("x", "good", 1.0, 11 * S + 1)
    check("ns t11", e.tick(ns(11.0))[1]["y"], ("bad", None))  # still the inf
    check("ns t12", e.tick(ns(12.0))[1]["y"], ("good", 2.0))
    e.write("x", "good", 1.0, 12 * S - 1)
    check("ns t13", e.tick(ns(13.0))[1]["y"], ("good", 2.0))
    check("ns t14", e.tick(ns(14.0))[1]["y"], ("bad", None))  # 2 s and 1 ns old
    e.write("x", "good", 1.0, 13 * S)
    check("ns t15", e.tick(ns(15.0))[1]["y"], ("good", 2.0))  # exactly 2 s old
    # nothing standing: not_ready, then bad once run for more than max_age
    e2 = Engine(g)
    check("nr t0", e2.tick(ns(0.0))[1]["y"], ("not_ready", None))
    check("nr t2", e2.tick(ns(2.0))[1]["y"], ("not_ready", None))
    check("nr t3", e2.tick(ns(3.0))[1]["y"], ("bad", None))


def test_gap():
    e = Engine(integ_graph(max_catch_up=3))
    e.write("x", "good", 1.0, ns(0.0))
    check("gap y0", e.tick(ns(0.0))[1]["y"], ("good", 1.0))
    # ticks 1 to 8 are due, more than 3: a stall. One tick runs, numbered 1,
    # at 8 s. What stood goes on standing, 8 s old, under its 10 s maximum.
    ran, o = e.tick(ns(8.0))
    check("gap ran", ran, 1)
    check("gap info", e.info, info(True, 1, 8 * S))
    check("gap y", o["y"], ("uncertain", 2.0))
    check("gap missed", o["missed"], ("good", 0.0))
    # three ticks are not more than three: ticks 2, 3, 4 at 9, 10, 11 s.
    # The value is 9 and 10 s old, usable, then 11 s old, bad.
    ran, o = e.tick(ns(11.0))
    check("gap three ran", ran, 3)
    check("gap three info", e.info, info(False, 4, 11 * S))
    check("gap three y", o["y"], ("uncertain", 4.0))
    check("gap three missed", o["missed"], ("good", 1.0))


def test_stall_writes():
    """A stall longer than max_catch_up, with writes stamped inside it."""
    e = Engine(integ_graph(max_catch_up=3))
    e.write("x", "good", 1.0, 0)
    ran, o = e.tick(0)
    check("stall y0", o["y"], ("good", 1.0))
    check("stall info0", e.info, info(False, 0, 0))
    e.write("x", "good", 5.0, 2 * S)
    e.write("x", "good", 7.0, ns(6.2))
    e.write("x", "good", 9.0, 8 * S)
    # ticks at 1..7 s are no more than half a period after 7.4 s: seven due,
    # more than 3. One tick runs: number 1, at 7 s, the last that was due.
    # It is the call's last tick and may see writes up to 7.4 s: of those
    # the latest time (7.0, at 6.2 s) stands; 9.0, at 8 s, still waits.
    ran, o = e.tick(ns(7.4))
    check("stall ran", ran, 1)
    check("stall info", e.info, info(True, 1, 7 * S, waiting=1))
    check("stall y", o["y"], ("uncertain", 8.0))
    check("stall missed", o["missed"], ("good", 0.0))
    # later ticks follow at whole periods: tick 2 at 8 s, due at 7.5 s
    check("stall none due", e.tick(ns(7.5) - 1), (0, None))
    ran, o = e.tick(ns(7.5))
    check("stall next ran", ran, 1)
    check("stall next info", e.info, info(False, 2, 8 * S))
    check("stall next y", o["y"], ("uncertain", 17.0))


def test_catch_up_writes():
    """Catch-up ticks of one call see writes by their times (rule 6.8)."""
    e = Engine(integ_graph())
    e.write("x", "good", 1.0, 0)
    check("cw y0", e.tick(0)[1]["y"], ("good", 1.0))
    e.write("x", "good", 2.0, ns(1.5))
    e.write("x", "good", 3.0, 3 * S)
    e.write("x", "good", 100.0, 9 * S)
    # tick 1 (1 s) sees 1; tick 2 (2 s) takes up 2; ticks 3 and 4 see 3.
    # The 100 is stamped more than one period after 4 s and is thrown away.
    ran, o = e.tick(4 * S)
    check("cw ran", ran, 4)
    check("cw info", e.info, info(False, 4, 4 * S, thrown=1))
    check("cw y4", o["y"], ("good", 10.0))
    check("cw missed", o["missed"], ("good", 0.0))
    # ticks 5 to 9 add 3 each: the 100 never stands
    ran, o = e.tick(9 * S)
    check("cw ran9", ran, 5)
    check("cw y9", o["y"], ("good", 25.0))


def test_catch_up_and_last():
    """A catch-up tick sees writes up to its own time; the call's last tick
    sees them up to `now` (rule 6.8)."""
    e = Engine(integ_graph())
    e.write("x", "good", 1.0, 0)
    check("cl y0", e.tick(0)[1]["y"], ("good", 1.0))
    e.write("x", "good", 10.0, ns(1.2))
    e.write("x", "good", 20.0, ns(2.2))
    # at 2.3 s ticks 1 (1 s) and 2 (2 s) are due. Tick 1 is a catch-up tick
    # and may see neither write: it adds 1. Tick 2 is the last and may see
    # both, up to 2.3 s; the later time stands: it adds 20.
    ran, o = e.tick(ns(2.3))
    check("cl ran", ran, 2)
    check("cl info", e.info, info(False, 2, 2 * S))
    check("cl y", o["y"], ("good", 22.0))
    # both were done with: tick 3 adds 20 again
    check("cl y3", e.tick(3 * S)[1]["y"], ("good", 42.0))


def test_call_near_tick():
    e = Engine(echo_graph())
    e.write("x", "good", 1.0, 0)
    check("nt 0", e.tick(0)[1]["y"], ("good", 1.0))
    # 3 ms late: the sample just taken is stamped after tick 1's time and
    # not after now, and tick 1 is the call's last tick
    e.write("x", "good", 2.0, ns(1.003))
    ran, o = e.tick(ns(1.003))
    check("nt late ran", ran, 1)
    check("nt late info", e.info, info(False, 1, 1 * S))
    check("nt late y", o["y"], ("good", 2.0))
    # 3 ms early: tick 2 (2 s) is no more than half a period after now. It
    # may see up to the later of 2 s and now, so also a write stamped
    # between now and its own time
    e.write("x", "good", 3.0, ns(1.997))
    ran, o = e.tick(ns(1.997))
    check("nt early ran", ran, 1)
    check("nt early info", e.info, info(False, 2, 2 * S))
    check("nt early y", o["y"], ("good", 3.0))
    e.write("x", "good", 4.0, ns(2.997))
    e.write("x", "good", 4.5, ns(2.999))
    check("nt early y 3", e.tick(ns(2.997))[1]["y"], ("good", 4.5))
    # one ns after the tick's time and after now: it waits
    e.write("x", "good", 5.0, 4 * S + 1)
    check("nt early y 4", e.tick(ns(3.997))[1]["y"], ("good", 4.5))
    check("nt y 5", e.tick(5 * S)[1]["y"], ("good", 5.0))


def echo_graph(max_age="none", **more):
    return {
        "period": "1s",
        "inputs": {"x": dict(more, max_age=max_age)},
        "blocks": [{"id": "f", "type": "formula", "in": {"a": "x"}, "settings": {"expr": "a * 1"}, "out": {"y": "y"}}],
    }


def test_write_ahead():
    e = Engine(echo_graph())
    e.write("x", "good", 1.0, 0)
    check("wa 0", e.tick(0)[1]["y"], ("good", 1.0))
    # stamped 1.5 s: within one period of the call at 1 s, so it waits
    # there, and stands from tick 2
    e.write("x", "good", 2.0, ns(1.5))
    check("wa 1", e.tick(1 * S)[1]["y"], ("good", 1.0))
    check("wa 2", e.tick(2 * S)[1]["y"], ("good", 2.0))
    # a write stamped exactly at a tick's time is seen by that tick
    e.write("x", "good", 5.0, 3 * S)
    check("wa 3", e.tick(3 * S)[1]["y"], ("good", 5.0))
    # one ns after the tick's time and now, it waits a tick
    e.write("x", "good", 6.0, 4 * S + 1)
    check("wa 4", e.tick(4 * S)[1]["y"], ("good", 5.0))
    check("wa 5", e.tick(5 * S)[1]["y"], ("good", 6.0))
    # exactly max_ahead after now is not more than max_ahead: it waits
    e.write("x", "good", 8.0, 7 * S)
    check("wa 6", e.tick(6 * S)[1]["y"], ("good", 6.0))
    check("wa 7", e.tick(7 * S)[1]["y"], ("good", 8.0))
    # one ns more: done with at the call at 8 s, and never stands
    e.write("x", "good", 9.0, 9 * S + 1)
    check("wa 8", e.tick(8 * S)[1]["y"], ("good", 8.0))
    check("wa 9", e.tick(9 * S)[1]["y"], ("good", 8.0))
    check("wa 10", e.tick(10 * S)[1]["y"], ("good", 8.0))
    check("wa 11", e.tick(11 * S)[1]["y"], ("good", 8.0))
    # a call that runs no tick throws away what is too far ahead as well
    e.write("x", "good", 9.5, ns(12.4))
    check("wa no tick", e.tick(ns(11.3)), (0, None))
    check("wa 12", e.tick(12 * S)[1]["y"], ("good", 8.0))
    check("wa 13", e.tick(13 * S)[1]["y"], ("good", 8.0))
    # with max_ahead given: 2.5 s ahead waits, 3 s and 1 ns ahead does not
    e = Engine(echo_graph(max_ahead="3s"))
    e.write("x", "good", 1.0, 0)
    e.write("x", "good", 2.0, ns(2.5))
    e.write("x", "good", 3.0, 3 * S + 1)
    check("wa given 0", e.tick(0)[1]["y"], ("good", 1.0))
    check("wa given 2", e.tick(2 * S)[1]["y"], ("good", 1.0))
    check("wa given 3", e.tick(3 * S)[1]["y"], ("good", 2.0))
    check("wa given 4", e.tick(4 * S)[1]["y"], ("good", 2.0))


def test_latest_time_stands():
    e = Engine(echo_graph("2s"))
    e.write("x", "good", 1.0, 0)
    check("lt 0", e.tick(0)[1]["y"], ("good", 1.0))
    e.write("x", "good", 5.0, ns(0.9))
    check("lt 1", e.tick(1 * S)[1]["y"], ("good", 5.0))
    # an older sample that arrives late does not displace the newer one
    e.write("x", "good", 4.0, ns(0.5))
    check("lt 2", e.tick(2 * S)[1]["y"], ("good", 5.0))
    # it was done with: the 5 grows old on its own time (2.1 s at tick 3)
    check("lt 3", e.tick(3 * S)[1]["y"], ("bad", None))
    # two writes with the same time: the one written later stands
    e.write("x", "good", 7.0, ns(3.5))
    e.write("x", "good", 8.0, ns(3.5))
    check("lt 4", e.tick(4 * S)[1]["y"], ("good", 8.0))
    # of two seen by one tick the later time stands, whichever was written
    # last, and the other never stands
    e.write("x", "good", 1.0, ns(4.8))
    e.write("x", "good", 2.0, ns(4.5))
    check("lt 5", e.tick(5 * S)[1]["y"], ("good", 1.0))
    check("lt 6", e.tick(6 * S)[1]["y"], ("good", 1.0))
    # a write with the same time as what stands was written later: it stands
    e = Engine(echo_graph())
    e.write("x", "good", 5.0, ns(0.9))
    check("lt same 1", e.tick(1 * S)[1]["y"], ("good", 5.0))
    e.write("x", "good", 6.0, ns(0.9))
    check("lt same 2", e.tick(2 * S)[1]["y"], ("good", 6.0))
    # a `bad` write is judged by its time like any other
    e.write("x", "bad", None, ns(0.8))
    check("lt bad older", e.tick(3 * S)[1]["y"], ("good", 6.0))
    e.write("x", "bad", None, ns(3.5))
    check("lt bad newer", e.tick(4 * S)[1]["y"], ("bad", None))


def test_thrown_and_waiting():
    e = Engine(echo_graph())
    e.write("x", "good", 1.0, 0)
    check("tw 0", e.tick(0), (1, {"y": ("good", 1.0)}))
    check("tw info 0", e.info, info(False, 0, 0))
    e.write("x", "good", 2.0, ns(0.5))  # waits
    e.write("x", "good", 0.5, -1 * S)  # earlier than what stands: thrown as made
    e.write("x", "bad", None, -1)  # and so is a failed read
    e.write("x", "good", 9.0, 5 * S)  # waits, until a call finds it too far ahead
    # no tick is due at 0.2 s, but the call throws the 9 away all the same
    check("tw no tick", e.tick(ns(0.2)), (0, None))
    check("tw no tick info", e.info, None)
    e.write("x", "good", 3.0, ns(1.4))  # waits past tick 1
    # three thrown since the call that ran tick 0; the 3 still waits
    check("tw 1", e.tick(1 * S), (1, {"y": ("good", 2.0)}))
    check("tw info 1", e.info, info(False, 1, 1 * S, thrown=3, waiting=1))
    # the count starts again at a call that ran a tick
    check("tw 2", e.tick(2 * S), (1, {"y": ("good", 3.0)}))
    check("tw info 2", e.info, info(False, 2, 2 * S))
    # the same time as what stands is not earlier: it waits, and stands
    e.write("x", "good", 7.0, ns(1.4))
    check("tw 3", e.tick(3 * S), (1, {"y": ("good", 7.0)}))
    check("tw info 3", e.info, info(False, 3, 3 * S))
    # a refused write is not one thrown away
    raises("tw refused", lambda: e.write("x", "good", "7", 0))
    check("tw 4", e.tick(4 * S), (1, {"y": ("good", 7.0)}))
    check("tw info 4", e.info, info(False, 4, 4 * S))
    # nothing stands after a reset: an earlier time is not thrown away
    e.reset()
    e.write("x", "good", 8.0, -5 * S)
    check("tw reset", e.tick(0), (1, {"y": ("good", 8.0)}))
    check("tw reset info", e.info, info(False, 0, 0))


def test_max_waiting():
    g = echo_graph()
    g["max_waiting"] = 2
    e = Engine(g)
    e.write("x", "good", 1.0, 0)
    check("mw 0", e.tick(0)[1]["y"], ("good", 1.0))
    e.write("x", "good", 10.0, ns(0.3))
    e.write("x", "good", 20.0, ns(0.2))
    # a third: the earliest time, the 20 at 0.2 s, is thrown away
    e.write("x", "good", 30.0, ns(1.4))
    # a fourth that is itself the earliest of the three is the one thrown
    e.write("x", "good", 40.0, ns(0.1))
    # tick 1 sees the 10; the 30 waits
    check("mw 1", e.tick(1 * S)[1]["y"], ("good", 10.0))
    check("mw info 1", e.info, info(False, 1, 1 * S, thrown=2, waiting=1))
    check("mw 2", e.tick(2 * S)[1]["y"], ("good", 30.0))
    check("mw info 2", e.info, info(False, 2, 2 * S))
    # of two with the same time the earlier written is thrown away
    g["max_waiting"] = 1
    e = Engine(g)
    e.write("x", "good", 1.0, 0)
    check("mw1 0", e.tick(0)[1]["y"], ("good", 1.0))
    e.write("x", "good", 10.0, ns(0.3))
    e.write("x", "good", 50.0, ns(0.3))
    check("mw1 1", e.tick(1 * S)[1]["y"], ("good", 50.0))
    check("mw1 info 1", e.info, info(False, 1, 1 * S, thrown=1))
    # the limit is for each input: one waiting on each of two is not over it
    g["inputs"]["b"] = {"type": "boolean", "max_age": "none"}
    e = Engine(g)
    e.write("x", "good", 1.0, 0)
    e.write("b", "good", True, 0)
    check("mw2 0", e.tick(0)[1]["y"], ("good", 1.0))
    check("mw2 info 0", e.info, info(False, 0, 0))
    e.write("x", "good", 2.0, ns(1.2))
    e.write("b", "good", False, ns(1.2))
    check("mw2 1", e.tick(1 * S)[1]["y"], ("good", 1.0))
    check("mw2 info 1", e.info, info(False, 1, 1 * S, waiting=2))


def test_sample_after_tick():
    # the age of a sample stamped after the tick is below zero: usable
    e = Engine(echo_graph("500ms"))
    e.write("x", "good", 1.0, 0)
    check("sa 0", e.tick(0)[1]["y"], ("good", 1.0))
    e.write("x", "good", 2.0, ns(1.4))
    check("sa 1", e.tick(ns(1.4))[1]["y"], ("good", 2.0))  # tick 1, at 1 s
    check("sa 2", e.tick(2 * S)[1]["y"], ("bad", None))  # 0.6 s old
    # and an estimator's `since` is not less than zero
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
                },
                "out": {"since_z": "since"},
            }
        ],
    }
    e = Engine(g)
    check("sa since 0", e.tick(0)[1]["since"], ("not_ready", None))
    e.write("z", "good", 5.0, ns(1.003))
    check("sa since 1", e.tick(ns(1.003))[1]["since"], ("good", 0.0))
    check("sa since 2", e.tick(2 * S)[1]["since"], ("good", 0.997))


def test_rebase():
    g = echo_graph("3s")
    g["blocks"].append(
        {
            "id": "w",
            "type": "window",
            "in": {"x": "x"},
            "settings": {"window": "2s", "min_good": 0.5, "only_new": True},
            "out": {"count": "c"},
        }
    )
    e = Engine(g)
    e.write("x", "good", 1.0, 100 * S)
    o = e.tick(100 * S)[1]
    check("rb y0", o["y"], ("good", 1.0))
    check("rb c0", o["c"], ("good", 1.0))
    check("rb c1", e.tick(101 * S)[1]["c"], ("good", 1.0))
    e.write("x", "good", 4.0, 102 * S)  # waiting at the rebase: done with
    e.rebase()
    # nothing stands from the moment of the rebase: a write stamped before
    # the 100 s that stood is not thrown away, and waits as usual
    e.write("x", "good", 2.0, 40 * S)
    # an earlier `now` is accepted. One tick: number 2, at 40 s. The window
    # was emptied and has forgotten the 100 s it last took, so a sample
    # stamped 40 s is a new one. The write done with at the rebase is not
    # one thrown away: had it waited, max_ahead would have thrown it here.
    ran, o = e.tick(40 * S)
    check("rb ran", ran, 1)
    check("rb info", e.info, info(True, 2, 40 * S))
    check("rb y", o["y"], ("good", 2.0))
    check("rb c", o["c"], ("good", 1.0))
    # later ticks are at whole periods from it, and the sample is not new again
    ran, o = e.tick(41 * S)
    check("rb next ran", ran, 1)
    check("rb next info", e.info, info(False, 3, 41 * S))
    check("rb next c", o["c"], ("good", 1.0))
    check("rb c 42", e.tick(42 * S)[1]["c"], ("good", 0.0))
    check("rb y 43", e.tick(43 * S)[1]["y"], ("good", 2.0))  # 3 s old
    check("rb y 44", e.tick(44 * S)[1]["y"], ("bad", None))
    # a rebase with nothing written after it: nothing stands, the write
    # made before it is done with, and the graph has run since the rebase's
    # tick (rule 7.2.1)
    e.write("x", "good", 4.0, 45 * S)
    e.rebase()
    ran, o = e.tick(45 * S)
    check("rb2 info", e.info, info(True, 7, 45 * S))
    check("rb2 y", o["y"], ("not_ready", None))
    ran, o = e.tick(48 * S)
    check("rb2 ran", ran, 3)
    check("rb2 y 48", o["y"], ("not_ready", None))
    check("rb2 y 49", e.tick(49 * S)[1]["y"], ("bad", None))
    # only the first call after a rebase may go backwards
    raises("rb2 backwards", lambda: e.tick(48 * S))
    # the call after a rebase runs one tick even with the same now, and
    # throws away what is stamped too far ahead of it like any other call
    e.rebase()
    e.write("x", "good", 6.0, 50 * S + 1)
    e.write("x", "bad", None, 50 * S + 1)
    ran, o = e.tick(49 * S)
    check("rb3 ran", ran, 1)
    check("rb3 info", e.info, info(True, 12, 49 * S, thrown=2))
    check("rb3 y", o["y"], ("not_ready", None))
    check("rb3 y 51", e.tick(51 * S)[1]["y"], ("not_ready", None))
    # a second rebase before the call does away with what was written
    # since the first
    e.rebase()
    e.write("x", "good", 7.0, 5 * S)
    e.rebase()
    ran, o = e.tick(5 * S)
    check("rb4 info", e.info, info(True, 15, 5 * S))
    check("rb4 y", o["y"], ("not_ready", None))
    # a restore: nothing stands from that moment either
    e = Engine(echo_graph())
    e.write("x", "good", 1.0, 100 * S)
    check("rs0 y", e.tick(100 * S)[1]["y"], ("good", 1.0))
    saved = e.save()
    e.restore(saved)
    e.write("x", "good", 2.0, 40 * S)
    ran, o = e.tick(40 * S)
    check("rs0 info", e.info, info(True, 1, 40 * S))
    check("rs0 y 40", o["y"], ("good", 2.0))
    # a state saved between a rebase and its call is as one saved before it
    e.rebase()
    saved = e.save()
    check("rs1 y", e.tick(90 * S)[1]["y"], ("not_ready", None))
    check("rs1 info", e.info, info(True, 2, 90 * S))
    e.restore(saved)
    e.write("x", "good", 3.0, 7 * S)
    ran, o = e.tick(7 * S)
    check("rs1 restored info", e.info, info(True, 2, 7 * S))
    check("rs1 restored y", o["y"], ("good", 3.0))
    # restoring a state saved before any tick: the writes waiting are done
    # with, the next call runs tick 0 and is not a gap
    e = Engine(echo_graph())
    saved = e.save()
    e.write("x", "good", 1.0, 0)
    check("rs2 y0", e.tick(0)[1]["y"], ("good", 1.0))
    e.write("x", "good", 5.0, ns(0.5))
    e.restore(saved)
    ran, o = e.tick(9 * S)
    check("rs2 info", e.info, info(False, 0, 9 * S))
    check("rs2 y", o["y"], ("not_ready", None))
    # a restore is a rebase too: a write made before it is done with
    e = Engine(echo_graph())
    e.write("x", "good", 1.0, 0)
    check("rs y0", e.tick(0)[1]["y"], ("good", 1.0))
    saved = e.save()
    e.write("x", "good", 5.0, 1 * S)
    e.restore(saved)
    ran, o = e.tick(1 * S)
    check("rs info", e.info, info(True, 1, 1 * S))
    check("rs y", o["y"], ("not_ready", None))


def test_refused_calls_and_writes():
    g = echo_graph()
    g["inputs"]["b"] = {"type": "boolean", "max_age": "none"}
    e = Engine(g)
    e.write("x", "good", 1.0, 0)
    check("rf y0", e.tick(0)[1]["y"], ("good", 1.0))
    check("rf y1", e.tick(1 * S)[1]["y"], ("good", 1.0))
    before = dict(e.info)
    raises("rf earlier now", lambda: e.tick(1 * S - 1))
    raises("rf float now", lambda: e.tick(2.0 * S))
    raises("rf fraction now", lambda: e.tick(2 * S + 0.5))
    raises("rf true for now", lambda: e.tick(True))
    raises("rf no now", lambda: e.tick(None))
    raises("rf unknown name", lambda: e.write("nope", "good", 2.0, 1 * S))
    raises("rf output name", lambda: e.write("y", "good", 2.0, 1 * S))
    raises("rf text for number", lambda: e.write("x", "good", "2", 1 * S))
    raises("rf boolean for number", lambda: e.write("x", "good", True, 1 * S))
    raises("rf number for boolean", lambda: e.write("b", "uncertain", 1.0, 1 * S))
    raises("rf fraction time", lambda: e.write("x", "good", 2.0, 1.5))
    raises("rf float time", lambda: e.write("x", "good", 2.0, 2.0))
    raises("rf no time", lambda: e.write("x", "good", 2.0, None))
    raises("rf bad with no time", lambda: e.write("x", "bad", None, None))
    raises("rf usable with no value", lambda: e.write("x", "good", None, 1 * S))
    raises("rf unknown state", lambda: e.write("x", "fine", 2.0, 1 * S))
    raises("rf time over 64 bits", lambda: e.write("x", "good", 2.0, 2**63))
    raises("rf now over 64 bits", lambda: e.tick(2**63))
    # none of that changed anything
    check("rf info", e.info, before)
    # a call with the same now is accepted, runs no tick and gives nothing
    check("rf same now", e.tick(1 * S), (0, None))
    check("rf info none", e.info, None)
    # a call that ran no tick is still the last call that was not refused
    check("rf later, no tick", e.tick(1 * S + 5), (0, None))
    raises("rf earlier than a call with no tick", lambda: e.tick(1 * S + 4))
    check("rf y2", e.tick(2 * S)[1]["y"], ("good", 1.0))
    # a `bad` write with a whole time is taken, value or not
    e.write("x", "bad", None, 3 * S)
    check("rf y3", e.tick(3 * S)[1]["y"], ("bad", None))


def test_reset_waiting():
    e = Engine(echo_graph())
    e.write("x", "good", 1.0, 0)
    check("rw y0", e.tick(0)[1]["y"], ("good", 1.0))
    check("rw y1", e.tick(1 * S)[1]["y"], ("good", 1.0))
    e.write("x", "good", 9.0, 5 * S)  # waiting, ahead
    e.write("x", "good", 3.0, 2 * S)  # waiting for the next tick
    e.reset()
    # tick 0 again, at whatever now; nothing stands and both writes are gone
    ran, o = e.tick(5 * S)
    check("rw ran", ran, 1)
    check("rw info", e.info, info(False, 0, 5 * S))
    check("rw y", o["y"], ("not_ready", None))
    check("rw y 6", e.tick(6 * S)[1]["y"], ("not_ready", None))
    # an earlier now is accepted after a reset
    e.reset()
    e.write("x", "good", 4.0, 2 * S)
    check("rw again", e.tick(2 * S), (1, {"y": ("good", 4.0)}))
    # a reset after a rebase is a reset: tick 0, and not a gap
    check("rw y3", e.tick(3 * S)[1]["y"], ("good", 4.0))
    e.rebase()
    e.reset()
    e.write("x", "good", 6.0, 1 * S)
    check("rw after rebase", e.tick(1 * S), (1, {"y": ("good", 6.0)}))
    check("rw after rebase info", e.info, info(False, 0, 1 * S))


def test_rebase_before_any_tick():
    # it does away with the writes waiting, and nothing else
    e = Engine(echo_graph())
    e.write("x", "good", 9.0, 5 * S)
    e.rebase()
    ran, o = e.tick(5 * S)
    check("rb0 ran", ran, 1)
    check("rb0 info", e.info, info(False, 0, 5 * S))
    check("rb0 y", o["y"], ("not_ready", None))
    # what is written after it waits as usual, and the ticks go on from tick 0
    e = Engine(echo_graph())
    e.write("x", "good", 9.0, 5 * S)
    e.rebase()
    e.write("x", "good", 2.0, 4 * S)
    check("rb0 after", e.tick(5 * S), (1, {"y": ("good", 2.0)}))
    check("rb0 after info", e.info, info(False, 0, 5 * S))
    check("rb0 next", e.tick(6 * S), (1, {"y": ("good", 2.0)}))
    check("rb0 next info", e.info, info(False, 1, 6 * S))
    raises("rb0 backwards", lambda: e.tick(5 * S))


def test_delay_window_rebase():
    g = {
        "period": "1s",
        "inputs": {"x": {"max_age": "none"}},
        "blocks": [
            {"id": "d", "type": "delay", "in": {"x": "x"}, "out": {"y": "dy"}},
            {
                "id": "w",
                "type": "window",
                "in": {"x": "d.y"},
                "settings": {"window": "2s", "min_good": 0.5, "only_new": True},
                "out": {"count": "c"},
            },
        ],
    }
    e = Engine(g)
    e.write("x", "good", 1.0, 100 * S)
    o = e.tick(100 * S)[1]  # tick 0: the delay has nothing to give
    check("dw dy 0", o["dy"], ("not_ready", None))
    check("dw c 0", o["c"], ("good", 0.0))
    e.write("x", "good", 2.0, 101 * S)
    o = e.tick(101 * S)[1]  # tick 1: it gives the 1, sampled at 100 s
    check("dw dy 1", o["dy"], ("good", 1.0))
    check("dw c 1", o["c"], ("good", 1.0))
    # the delay now holds the 2, sampled at 101 s. At the rebase it becomes
    # uncertain and carries no sample time, so the emptied window, which
    # would take any sample with a time, does not take it.
    e.rebase()
    e.write("x", "good", 3.0, 10 * S)
    o = e.tick(10 * S)[1]  # tick 2
    check("dw info", e.info, info(True, 2, 10 * S))
    check("dw dy 2", o["dy"], ("uncertain", 2.0))
    check("dw c 2", o["c"], ("good", 0.0))
    # what the delay took in after the rebase carries its time again
    e.write("x", "good", 4.0, 11 * S)
    o = e.tick(11 * S)[1]  # tick 3: the 3, sampled at 10 s
    check("dw dy 3", o["dy"], ("good", 3.0))
    check("dw c 3", o["c"], ("good", 1.0))
    o = e.tick(12 * S)[1]  # tick 4: the 4, sampled at 11 s
    check("dw dy 4", o["dy"], ("good", 4.0))
    check("dw c 4", o["c"], ("good", 2.0))
    o = e.tick(13 * S)[1]  # tick 5: the 4 again, not a new sample
    check("dw c 5", o["c"], ("good", 1.0))


def test_save_restore():
    g = {"period": "1s", "blocks": [{"id": "i", "type": "integrate", "in": {"x": 1}, "out": {"y": "y"}}]}
    e = Engine(g)
    check("sr y0", e.tick(ns(0.0))[1]["y"], ("good", 1.0))
    check("sr y1", e.tick(ns(1.0))[1]["y"], ("good", 2.0))
    saved = e.save()
    check("sr y2", e.tick(ns(2.0))[1]["y"], ("good", 3.0))
    e.restore(saved)
    ran, o = e.tick(ns(0.5))  # a gap: any now, one tick
    check("sr ran", ran, 1)
    check("sr info", e.info, info(True, 2, ns(0.5)))
    check("sr y", o["y"], ("uncertain", 3.0))
    # the next tick is at 1.5, due once now is within half a period of it
    check("sr none due", e.tick(ns(0.9)), (0, None))
    check("sr y next", e.tick(ns(1.0))[1]["y"], ("uncertain", 4.0))
    other = Engine(integ_graph())
    raises("sr other graph", lambda: other.restore(saved))
    e.reset()
    check("reset", e.tick(ns(0.0)), (1, {"y": ("good", 1.0)}))


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
    e.write("x", "good", 1.0, ns(0.0))
    want = [(1, 0, 1, 1), (1, 1, 2, 1), (0, 1, 2, 0), (0, 0, 2, 0)]
    for k, w in enumerate(want):
        o = e.tick(k * S)[1]
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
        e.write("x", state, value, k * S)
        return e.tick(k * S)[1]["y"]

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
        e.write("x", state, value, k * S)
        res.append(e.tick(k * S)[1]["out"])
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
    e.write("ok", "good", False, ns(0.0))
    e.write("x", "bad", None, ns(0.0))
    check("when const", e.tick(ns(0.0))[1]["y"], ("good", 20.0))
    e.write("ok", "uncertain", True, ns(1.0))
    check("when bad branch", e.tick(ns(1.0))[1]["y"], ("bad", None))
    e.write("x", "good", 4.0, ns(2.0))
    check("when unc cond", e.tick(ns(2.0))[1]["y"], ("uncertain", 4.0))

    e = one("ok or x > 1", {"ok": "ok", "x": "x"}, num)
    e.write("ok", "good", True, ns(0.0))
    check("or decides", e.tick(ns(0.0))[1]["y"], ("good", True))
    e.write("ok", "uncertain", True, ns(1.0))
    e.write("x", "good", 0.0, ns(1.0))
    check("or unc decides", e.tick(ns(1.0))[1]["y"], ("uncertain", True))
    e.write("ok", "good", False, ns(2.0))
    e.write("x", "bad", None, ns(2.0))
    check("or undecided", e.tick(ns(2.0))[1]["y"], ("bad", None))

    e = one("1 / x + 2 * -3", {"x": "x"}, num and {"x": num["x"]})
    e.write("x", "good", 0.0, ns(0.0))
    check("div zero", e.tick(ns(0.0))[1]["y"], ("bad", None))
    e.write("x", "good", 4.0, ns(1.0))
    check("arith", e.tick(ns(1.0))[1]["y"], ("good", -5.75))

    e = one("not 1 + 2 * 3 == 7 and pow(2, 3) - 1 >= 7 or sqrt(a) < ln(a)", {"a": -1}, {})
    # not (7 == 7) -> false; false and ... -> false (decided, good);
    # sqrt(-1) is bad, so the `or` is not decided and takes the worst state
    check("precedence", e.tick(ns(0.0))[1]["y"], ("bad", None))

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
    o = e.tick(ns(0.0))[1]
    check("fallback", o["y"], ("uncertain", 0.0))
    check("all_good false", o["ok"], ("good", False))
    e.write("x", "good", 2.0, ns(1.0))
    o = e.tick(ns(1.0))[1]
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
        check("counter %d" % k, e.tick(k * S)[1]["n"], ("good", float(k + 1)))
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
    o = e.tick(ns(0.0))[1]
    check("model 0", o["temp"], ("good", 20.0))
    check("model heat", o["heat"], ("good", 100.0))
    # d temp/dt = -(temp - 120)/100; RK4 on a linear equation multiplies
    # the distance from 120 by 1 + z + z^2/2 + z^3/6 + z^4/24, z = -0.01
    z = -0.01
    s = 1 + z + z**2 / 2 + z**3 / 6 + z**4 / 24
    check("model 1", e.tick(ns(1.0))[1]["temp"], ("good", 120 - 100 * s))
    check("model 2", e.tick(ns(2.0))[1]["temp"], ("good", 120 - 100 * s * s))

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
    check("doubt 0", e.tick(ns(0.0))[1]["temp"], ("good", 20.0))
    e.write("p", "good", 0.0, ns(1.0))
    check("doubt 1", e.tick(ns(1.0))[1]["temp"], ("uncertain", 20.0))
    check("doubt 2", e.tick(ns(2.0))[1]["temp"], ("good", 20.0))
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
    e.write("u", "good", 1.0, ns(0.0))
    check("ss 0", e.tick(ns(0.0))[1]["y"], ("good", 1.0))
    check("ss 1", e.tick(ns(1.0))[1]["y"], ("good", 3.0))
    check("ss 2", e.tick(ns(2.0))[1]["y"], ("good", 4.0))


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
    e.write("z", "good", 5.0, ns(0.0))
    o = e.tick(ns(0.0))[1]
    check("est x 0", o["x"], ("good", 4.0))
    check("est sigma 0", o["sigma"], ("good", math.sqrt(0.8)))
    check("est innov 0", o["innov"], ("good", 5.0))
    check("est refused 0", o["refused"], ("good", 0.0))
    check("est since 0", o["since"], ("good", 0.0))
    # tick 1: predict only; the same sample is not considered again
    o = e.tick(ns(1.0))[1]
    check("est x 1", o["x"], ("good", 4.0))
    check("est sigma 1", o["sigma"], ("good", math.sqrt(1.8)))
    check("est innov 1", o["innov"], ("not_ready", None))
    check("est since 1", o["since"], ("good", 1.0))
    # tick 2: P = 2.8, s = 3.8, innovation 96 > 3 sqrt(3.8): refused
    e.write("z", "good", 100.0, ns(2.0))
    o = e.tick(ns(2.0))[1]
    check("est x 2", o["x"], ("good", 4.0))
    check("est sigma 2", o["sigma"], ("good", math.sqrt(2.8)))
    check("est innov 2", o["innov"], ("good", 96.0))
    check("est refused 2", o["refused"], ("good", 1.0))
    check("est since 2", o["since"], ("good", 2.0))
    # tick 3: P = 3.8, s = 4.8, innovation 1: used
    e.write("z", "good", 5.0, ns(3.0))
    o = e.tick(ns(3.0))[1]
    gain = 3.8 / 4.8
    check("est x 3", o["x"], ("good", 4.0 + gain))
    check("est sigma 3", o["sigma"], ("good", math.sqrt(3.8 - gain * 3.8)))
    check("est since 3", o["since"], ("good", 0.0))
    # an uncertain measurement is not considered unless asked for
    e.write("z", "uncertain", 9.0, ns(4.0))
    o = e.tick(ns(4.0))[1]
    check("est innov 4", o["innov"], ("not_ready", None))
    check("est since 4", o["since"], ("good", 1.0))
    # a rebase: tick 5, at 1 s on another clock. The variance grows by p0
    # at the gap and by q at the predict; nothing stands on z. The sample
    # time last used is forgotten with the rest, so `since` is not_ready.
    p4 = 3.8 - gain * 3.8 + 1
    e.rebase()
    o = e.tick(1 * S)[1]
    check("est rb x", o["x"], ("good", 4.0 + gain))
    check("est rb sigma", o["sigma"], ("good", math.sqrt(p4 + 4 + 1)))
    check("est rb innov", o["innov"], ("not_ready", None))
    check("est rb refused", o["refused"], ("good", 1.0))
    check("est rb since", o["since"], ("not_ready", None))
    # a measurement stamped 2 s, before the 3 s last considered on the old
    # clock, is considered: P = p4 + 6, s = p4 + 7, innovation 1 - gain
    e.write("z", "good", 5.0, 2 * S)
    o = e.tick(2 * S)[1]
    p = p4 + 6
    check("est rb innov 2", o["innov"], ("good", 1 - gain))
    check("est rb x 2", o["x"], ("good", 4.0 + gain + p / (p + 1) * (1 - gain)))
    check("est rb since 2", o["since"], ("good", 0.0))
    check("est rb since 3", e.tick(3 * S)[1]["since"], ("good", 1.0))


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
    Engine(variant(period="1000000us", settings={"window": "3000000000ns"}))
    # a maximum age and max_ahead are not less than half a period
    Engine(variant(input={"max_age": "500ms"}))
    refused("max_age under half a period", variant(input={"max_age": "499999999ns"}))
    Engine(variant(input={"max_age": "5s", "max_ahead": "500ms"}))
    refused("max_ahead under half a period", variant(input={"max_age": "5s", "max_ahead": "499999999ns"}))
    Engine(variant(period="3ns", input={"max_age": "2ns"}, settings={"window": "3ns"}))
    refused("max_age under half of 3 ns", variant(period="3ns", input={"max_age": "1ns"}, settings={"window": "3ns"}))
    refused("max_waiting zero", dict(ok, max_waiting=0))
    refused("max_waiting not whole", dict(ok, max_waiting="2"))
    Engine(dict(ok, max_waiting=1))
    Engine(variant(input={"max_age": "5s", "max_ahead": "1500ms"}))
    refused("max_ahead not whole ns", variant(input={"max_age": "5s", "max_ahead": "0.5ns"}))
    refused("max_ahead no unit", variant(input={"max_age": "5s", "max_ahead": 1}))
    refused("period not whole ns", variant(period="0.5ns", settings={"window": "1.5ns"}))
    refused("max_age not whole ns", variant(input={"max_age": "1.5ns"}))
    refused("window not whole ns", variant(settings={"window": "3000000000.5ns"}))
    refused("unit", variant(input={"max_age": "5sec"}))
    # `tau` only scales a value and "may be any length at all" (rule 6.3)
    lp = {"period": "1s", "blocks": [{"id": "l", "type": "lowpass", "in": {"x": 1}, "settings": {"tau": "0.5ns"}}]}
    Engine(lp)

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

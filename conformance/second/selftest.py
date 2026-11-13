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


def info(gap, tick, time, thrown=0, waiting=0, skipped=0):
    """What a call that ran a tick reports (rule 6.10). `skipped` is the
    ticks passed over at a gap, or None where nobody knows."""
    return {"gap": gap, "skipped": skipped, "tick": tick, "time": time, "thrown": thrown, "waiting": waiting}


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
    # a total is good on a tick where it lacks its input (rule 7.7.2)
    check("cu y0", o["y"], ("good", 0.0))
    check("cu missed0", o["missed"], ("good", 1.0))
    e.write("x", "good", 3.0, ns(2.9))
    ran, o = e.tick(ns(3.0))
    check("cu ran3", ran, 3)
    # the write is stamped 2.9 s: ticks 1 and 2 are before it and see
    # nothing; tick 3 is the first at or after it, and adds 3
    check("cu y3", o["y"], ("good", 3.0))
    check("cu missed3", o["missed"], ("good", 3.0))
    check("cu info3", e.info, info(False, 3, 3 * S))
    check("cu none due", e.tick(ns(3.4)), (0, None))
    check("cu none due, one ns short", e.tick(ns(3.5) - 1), (0, None))
    ran, o = e.tick(ns(3.5))  # exactly half a period before tick 4
    check("cu ran half", ran, 1)
    check("cu y4", o["y"], ("good", 6.0))
    check("cu info4", e.info, info(False, 4, 4 * S))
    raises("cu backwards", lambda: e.tick(ns(3.0)))
    raises("cu nan", lambda: e.tick(float("nan")))
    check("cu same now", e.tick(ns(3.5)), (0, None))
    # a write made before a call that runs no tick waits for the next
    e.write("x", "good", 10.0, ns(4.0))
    check("cu no tick", e.tick(ns(3.6)), (0, None))
    check("cu no tick info", e.info, None)
    ran, o = e.tick(ns(5.0))
    check("cu y5", o["y"], ("good", 16.0))


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
    # ticks 1 to 8 are due, more than 3: a stall. One tick runs, tick 8,
    # at 8 s. What stood goes on standing, 8 s old, under its 10 s maximum.
    # The total is unchanged by the gap, and good (section 8.6).
    ran, o = e.tick(ns(8.0))
    check("gap ran", ran, 1)
    check("gap info", e.info, info(True, 8, 8 * S, skipped=7))
    check("gap y", o["y"], ("good", 2.0))
    check("gap missed", o["missed"], ("good", 7.0))  # the seven ticks passed over
    # three ticks are not more than three: ticks 2, 3, 4 at 9, 10, 11 s.
    # The value is 9 and 10 s old, usable, then 11 s old, bad.
    ran, o = e.tick(ns(11.0))
    check("gap three ran", ran, 3)
    check("gap three info", e.info, info(False, 11, 11 * S))
    check("gap three y", o["y"], ("good", 4.0))
    check("gap three missed", o["missed"], ("good", 8.0))


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
    # more than 3. One tick runs: tick 7, at 7 s, the last that was due.
    # It is the call's last tick and may see writes up to 7.4 s: of those
    # the latest time (7.0, at 6.2 s) stands; 9.0, at 8 s, still waits.
    ran, o = e.tick(ns(7.4))
    check("stall ran", ran, 1)
    check("stall info", e.info, info(True, 7, 7 * S, waiting=1, skipped=6))
    check("stall y", o["y"], ("good", 8.0))
    check("stall missed", o["missed"], ("good", 6.0))
    # later ticks follow at whole periods: tick 2 at 8 s, due at 7.5 s
    check("stall none due", e.tick(ns(7.5) - 1), (0, None))
    ran, o = e.tick(ns(7.5))
    check("stall next ran", ran, 1)
    check("stall next info", e.info, info(False, 8, 8 * S))
    check("stall next y", o["y"], ("good", 17.0))


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
                    "measure": {"z": {"of": "y", "r": 1}},
                    "consistency": "none",
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
    check("rb info", e.info, info(True, 2, 40 * S, skipped=None))
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
    check("rb2 info", e.info, info(True, 7, 45 * S, skipped=None))
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
    check("rb3 info", e.info, info(True, 12, 49 * S, thrown=2, skipped=None))
    check("rb3 y", o["y"], ("not_ready", None))
    check("rb3 y 51", e.tick(51 * S)[1]["y"], ("not_ready", None))
    # a second rebase before the call does away with what was written
    # since the first
    e.rebase()
    e.write("x", "good", 7.0, 5 * S)
    e.rebase()
    ran, o = e.tick(5 * S)
    check("rb4 info", e.info, info(True, 15, 5 * S, skipped=None))
    check("rb4 y", o["y"], ("not_ready", None))
    # a restore: nothing stands from that moment either
    e = Engine(echo_graph())
    e.write("x", "good", 1.0, 100 * S)
    check("rs0 y", e.tick(100 * S)[1]["y"], ("good", 1.0))
    saved = e.save()
    e.restore(saved)
    e.write("x", "good", 2.0, 40 * S)
    ran, o = e.tick(40 * S)
    check("rs0 info", e.info, info(True, 1, 40 * S, skipped=None))
    check("rs0 y 40", o["y"], ("good", 2.0))
    # a state saved between a rebase and its call is as one saved before it
    e.rebase()
    saved = e.save()
    check("rs1 y", e.tick(90 * S)[1]["y"], ("not_ready", None))
    check("rs1 info", e.info, info(True, 2, 90 * S, skipped=None))
    e.restore(saved)
    e.write("x", "good", 3.0, 7 * S)
    ran, o = e.tick(7 * S)
    check("rs1 restored info", e.info, info(True, 2, 7 * S, skipped=None))
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
    check("rs info", e.info, info(True, 1, 1 * S, skipped=None))
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
    check("dw info", e.info, info(True, 2, 10 * S, skipped=None))
    check("dw dy 2", o["dy"], ("not_ready", None))
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
    check("sr info", e.info, info(True, 2, ns(0.5), skipped=None))
    check("sr y", o["y"], ("good", 3.0))
    # the next tick is at 1.5, due once now is within half a period of it
    check("sr none due", e.tick(ns(0.9)), (0, None))
    check("sr y next", e.tick(ns(1.0))[1]["y"], ("good", 4.0))
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

    # settle is three time constants: 3 ticks. An uncertain input at tick 2
    # is a doubt: uncertain at tick 2 by the input, and on ticks 3, 4, 5.
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
    check("lp 5", step(5, "good", 1.0), ("uncertain", y))
    y = a * y + (1 - a)
    check("lp 6", step(6, "good", 1.0), ("good", y))
    # riding through is uncertain while it lasts, and is not a doubt
    check("lp 7", step(7, "bad", None), ("uncertain", y))
    y = a * a * y + (1 - a * a)
    check("lp 8", step(8, "good", 1.0), ("good", y))
    check("lp 9", step(9, "bad", None), ("uncertain", y))
    check("lp 10", step(10, "bad", None), ("bad", None))
    check("lp 11", step(11, "good", 2.0), ("good", 2.0))
    # forgetting clears the doubt: the doubt of tick 12 would have made
    # tick 15 uncertain (15 - 12 is not more than 3)
    check("lp 12", step(12, "uncertain", 2.0), ("uncertain", 2.0))
    check("lp 13", step(13, "bad", None), ("uncertain", 2.0))
    check("lp 14", step(14, "bad", None), ("bad", None))
    check("lp 15", step(15, "good", 5.0), ("good", 5.0))
    # a first input that is uncertain is a doubt
    got = run_seq(
        {"type": "lowpass", "in": {"x": "x"}, "settings": {"tau": "1s", "settle": "1s"}},
        "number",
        [("uncertain", 1.0), ("good", 1.0), ("good", 1.0)],
    )
    want = [("uncertain", 1.0), ("uncertain", 1.0), ("good", 1.0)]
    for k, (g_, w) in enumerate(zip(got, want)):
        check("lp first %d" % k, g_, w)
    # settle of 0s: uncertain only on the tick the input is
    got = run_seq(
        {"type": "lowpass", "in": {"x": "x"}, "settings": {"tau": "1s", "settle": "0s"}},
        "number",
        [("uncertain", 1.0), ("good", 1.0)],
    )
    check("lp settle 0, 0", got[0], ("uncertain", 1.0))
    check("lp settle 0, 1", got[1], ("good", 1.0))
    # a gap forgets what it held, and (as assumed) the doubt with it
    e = Engine(g)
    check("lp gap 0", step(0, "uncertain", 1.0), ("uncertain", 1.0))
    e.rebase()
    check("lp gap 1", step(1, "good", 3.0), ("good", 3.0))


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


def check_seq(label, block, in_type, seq, **want):
    """want: for each port, the list of (state, value) expected; a counter
    may be given as a list of plain numbers, each `good`."""
    for port, exp in want.items():
        got = run_seq(block, in_type, seq, port)
        check("%s %s length" % (label, port), len(got), len(exp))
        for k, (g_, w) in enumerate(zip(got, exp)):
            if not isinstance(w, tuple):
                w = ("good", float(w))
            check("%s %s %d" % (label, port, k), g_, w)


def test_hysteresis():
    # the output takes the input's state; nothing is remembered of a doubt.
    # The counters start again at ticks 1 and 7, where the value changes.
    check_seq(
        "hyst",
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
            ("uncertain", 5.0),
            ("good", 5.0),
        ],
        y=[
            ("not_ready", None),
            ("good", True),
            ("good", True),
            ("bad", None),
            ("good", True),
            ("uncertain", True),
            ("good", True),
            ("uncertain", False),
            ("good", False),
        ],
        elapsed=[1, 1, 2, 3, 4, 5, 6, 1, 2],
        doubtful=[0, 0, 0, 1, 1, 2, 2, 1, 1],
    )
    # with an initial value: no change until it switches
    check_seq(
        "hyst initial",
        {"type": "hysteresis", "in": {"x": "x"}, "settings": {"rise": 10, "fall": 5, "initial": True}},
        "number",
        [("good", 7.0), ("bad", None), ("good", 12.0), ("good", 4.0)],
        y=[("good", True), ("bad", None), ("good", True), ("good", False)],
        elapsed=[1, 2, 3, 1],
        doubtful=[0, 1, 1, 0],
    )


def test_latch():
    check_seq(
        "latch",
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
        y=[
            ("good", False),
            ("uncertain", False),
            ("good", False),
            ("bad", None),
            ("good", True),
            ("good", True),
            ("good", True),
        ],
        elapsed=[1, 2, 3, 4, 5, 6, 7],
        # ticks 5 and 6: it was set when the tick began
        doubtful=[0, 1, 1, 2, 2, 2, 2],
    )
    # set by an uncertain true: uncertain on that tick, good from the next
    check_seq(
        "latch unc",
        {"type": "latch", "in": {"set": "x"}},
        "boolean",
        [("uncertain", True), ("good", False), ("good", True)],
        y=[("uncertain", True), ("good", True), ("good", True)],
        doubtful=[1, 1, 1],
    )
    # reset wins over set, and gives its state; unusable, it is not used
    check_seq(
        "latch reset",
        {"type": "latch", "in": {"set": True, "reset": "x"}},
        "boolean",
        [("good", False), ("good", True), ("bad", None), ("uncertain", True), ("good", False)],
        y=[("good", True), ("good", False), ("good", True), ("uncertain", False), ("good", True)],
        elapsed=[1, 1, 2, 1, 2],
        doubtful=[0, 0, 0, 0, 0],
    )
    # cleared on every tick: the output has the state of `reset`, and each
    # tick is one on which it was not set when it began
    check_seq(
        "latch held clear",
        {"type": "latch", "in": {"set": "x", "reset": True}},
        "boolean",
        [("uncertain", True), ("bad", None), ("good", True)],
        y=[("good", False), ("good", False), ("good", False)],
        elapsed=[1, 1, 1],
        doubtful=[1, 1, 0],
    )


def test_integrate():
    check_seq(
        "integ",
        {"type": "integrate", "in": {"x": "x"}},
        "number",
        [("good", 1.0), ("good", 1.0), ("uncertain", 1.0), ("bad", None), ("bad", None), ("good", 1.0)],
        # uncertain only on the tick the input is; good on a tick it lacks
        y=[("good", 1.0), ("good", 2.0), ("uncertain", 3.0), ("good", 3.0), ("good", 3.0), ("good", 4.0)],
        missed=[0, 0, 0, 1, 2, 2],
        doubtful=[0, 0, 1, 1, 1, 1],
        elapsed=[1, 2, 3, 4, 5, 6],
        gaps=[0, 0, 0, 0, 0, 0],
    )
    check_seq(
        "integ max_missed",
        {"type": "integrate", "in": {"x": "x"}, "settings": {"per": "1m", "max_missed": "1s"}},
        "number",
        [("good", 60.0), ("bad", None), ("bad", None), ("uncertain", 60.0)],
        # one second missed is not more than max_missed; two are, for good
        y=[("good", 1.0), ("good", 1.0), ("bad", None), ("bad", None)],
        missed=[0, 1, 2, 2],
    )
    refused(
        "integ tolerance is gone",
        {"period": "1s", "blocks": [{"id": "i", "type": "integrate", "in": {"x": 1}, "settings": {"tolerance": 0.5}}]},
    )
    # reset, and a gap
    ports = ("y", "missed", "doubtful", "elapsed", "gaps")
    g = {
        "period": "1s",
        "max_catch_up": 3,
        "inputs": {"x": {"max_age": "none"}, "r": {"type": "boolean", "max_age": "none"}},
        "blocks": [{"id": "i", "type": "integrate", "in": {"x": "x", "reset": "r"}, "out": {p: p for p in ports}}],
    }
    e = Engine(g)

    def step(label, k, x, r, want):
        e.write("x", x[0], x[1], k * S)
        e.write("r", r[0], r[1], k * S)
        o = e.tick(k * S)[1]
        check("integ r %s y" % label, o["y"], want[0])
        for p, w in zip(ports[1:], want[1:]):
            check("integ r %s %s" % (label, p), o[p], ("good", float(w)))

    step("0", 0, ("good", 2.0), ("good", False), (("good", 2.0), 0, 0, 1, 0))
    step("1", 1, ("bad", None), ("good", False), (("good", 2.0), 1, 0, 2, 0))
    # an uncertain true reset: everything to zero, then this tick's addition
    step("2", 2, ("good", 2.0), ("uncertain", True), (("uncertain", 2.0), 0, 0, 1, 0))
    step("3", 3, ("good", 2.0), ("bad", None), (("good", 4.0), 0, 0, 2, 0))
    # a stall: tick 10, six passed over. The total is unchanged by it, and good
    step("4", 10, ("uncertain", 2.0), ("uncertain", False), (("uncertain", 6.0), 6, 1, 9, 1))
    check("integ r gap info", e.info, info(True, 10, 10 * S, skipped=6))
    step("5", 11, ("good", 2.0), ("good", False), (("good", 8.0), 6, 1, 10, 1))
    # a reset returns `gaps` to zero with the rest
    step("6", 12, ("uncertain", 2.0), ("good", True), (("uncertain", 2.0), 0, 1, 1, 0))


def test_timers():
    check_seq(
        "held_for",
        {"type": "held_for", "in": {"x": "x"}, "settings": {"time": "2s", "on_bad": "reset"}},
        "boolean",
        [("good", True)] * 4 + [("bad", None), ("good", True)] + [("uncertain", True)] * 3 + [("good", False)],
        # the timer starts at tick 0, stops at tick 4, starts again at tick 5
        y=[("good", False)] * 3
        + [("good", True), ("bad", None), ("good", False)]
        + [("uncertain", False), ("uncertain", False), ("uncertain", True), ("good", False)],
        elapsed=[1, 2, 3, 4, 0, 1, 2, 3, 4, 0],
        doubtful=[0, 0, 0, 0, 0, 0, 1, 2, 3, 0],
    )
    check_seq(
        "held_for hold",
        {"type": "held_for", "in": {"x": "x"}, "settings": {"time": "2s", "on_bad": "hold", "hold_limit": "1s"}},
        "boolean",
        [
            ("good", True),
            ("good", True),
            ("bad", None),
            ("good", True),
            ("bad", None),
            ("bad", None),
            ("good", True),
        ],
        # uncertain only while it runs on an unusable input; tick 3 is good
        y=[
            ("good", False),
            ("good", False),
            ("uncertain", False),
            ("good", True),
            ("uncertain", True),
            ("bad", None),
            ("good", False),
        ],
        elapsed=[1, 2, 3, 4, 5, 0, 1],
        doubtful=[0, 0, 1, 1, 2, 0, 0],
    )
    check_seq(
        "since_true",
        {"type": "since_true", "in": {"x": "x"}, "settings": {"time": "2s", "on_bad": "assume_false"}},
        "boolean",
        [("good", False)] * 4 + [("uncertain", True), ("good", False), ("bad", None), ("good", False), ("good", False)],
        # the clock is set at tick 0 and again at tick 4
        y=[("good", False)] * 3
        + [
            ("good", True),
            ("uncertain", False),
            ("good", False),
            ("uncertain", False),
            ("good", True),
            ("good", True),
        ],
        elapsed=[1, 2, 3, 4, 1, 2, 3, 4, 5],
        doubtful=[0, 0, 0, 0, 1, 1, 2, 2, 2],
    )
    check_seq(
        "since_true unknown",
        {"type": "since_true", "in": {"x": "x"}, "settings": {"time": "0s", "on_bad": "unknown"}},
        "boolean",
        [("good", True), ("bad", None), ("good", False)],
        y=[("good", False), ("bad", None), ("good", True)],
        elapsed=[1, 2, 3],
        doubtful=[0, 1, 1],
    )
    # at a gap the held_for timer stops and the since_true clock is set
    g = {
        "period": "1s",
        "max_catch_up": 3,
        "blocks": [
            {
                "id": "h",
                "type": "held_for",
                "in": {"x": True},
                "settings": {"time": "1s", "on_bad": "reset"},
                "out": {"y": "h", "elapsed": "he"},
            },
            {
                "id": "s",
                "type": "since_true",
                "in": {"x": False},
                "settings": {"time": "1s", "on_bad": "unknown"},
                "out": {"y": "s", "elapsed": "se"},
            },
        ],
    }
    e = Engine(g)
    e.tick(0)
    e.tick(1 * S)
    o = e.tick(2 * S)[1]
    check("timers h 2", o["h"], ("good", True))
    check("timers he 2", o["he"], ("good", 3.0))
    check("timers s 2", o["s"], ("good", True))
    check("timers se 2", o["se"], ("good", 3.0))
    o = e.tick(10 * S)[1]  # a stall: tick 10; the clock is not set, the timer stops
    check("timers gap info", e.info, info(True, 10, 10 * S, skipped=7))
    check("timers h gap", o["h"], ("good", False))
    check("timers he gap", o["he"], ("good", 1.0))
    check("timers s gap", o["s"], ("good", True))
    check("timers se gap", o["se"], ("good", 11.0))
    o = e.tick(12 * S)[1]  # ticks 4 and 5
    check("timers h 5", o["h"], ("good", True))
    check("timers s 5", o["s"], ("good", True))
    check("timers se 5", o["se"], ("good", 13.0))


def test_deadband_window():
    check_seq(
        "deadband",
        {"type": "deadband", "in": {"x": "x"}, "settings": {"step": 1}},
        "number",
        [("good", 0.0), ("good", 0.5), ("uncertain", 0.75), ("good", 1.0), ("bad", None)],
        y=[("good", 0.0), ("good", 0.0), ("uncertain", 0.0), ("good", 1.0), ("bad", None)],
    )
    # a sample that was uncertain when taken is good once its input is
    check_seq(
        "deadband unc",
        {"type": "deadband", "in": {"x": "x"}, "settings": {"step": 1, "ride_through": "1s"}},
        "number",
        [("uncertain", 0.0), ("good", 0.5), ("bad", None), ("bad", None), ("good", 5.0)],
        y=[("uncertain", 0.0), ("good", 0.0), ("uncertain", 0.0), ("bad", None), ("good", 5.0)],
    )
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
        # three usable, two good, three needed: of its usable samples
        check("window %s 3" % port, got[3], ("uncertain", w3))
    got = run_seq(blk, "number", seq, "count")
    check("window count 0", got[0], ("good", 1.0))
    check("window count 2", got[2], ("good", 3.0))
    # a tolerance: 4 ticks, 2 needed. The windows, oldest first:
    #  0: -  -  -  1         one usable: the worst of the ticks with none
    #  1: -  -  1  10u       two usable, one good: uncertain, of both
    #  2: -  1  10u 3        two good: good, of the good ones alone
    #  3: 1  10u 3  bad      the same
    #  4: 10u 3  bad 5       good, of 3 and 5
    #  5: 3  bad 5  7u       good, of 3 and 5
    #  6: bad 5  7u 9u       three usable, one good: uncertain, of all three
    #  7: 5  7u 9u bad       the same
    #  8: 7u 9u bad bad      two usable, none good: uncertain
    #  9: 9u bad bad bad     one usable: bad
    seq = [
        ("good", 1.0),
        ("uncertain", 10.0),
        ("good", 3.0),
        ("bad", None),
        ("good", 5.0),
        ("uncertain", 7.0),
        ("uncertain", 9.0),
        ("bad", None),
        ("bad", None),
        ("bad", None),
    ]
    check_seq(
        "window tol",
        {"type": "window", "in": {"x": "x"}, "settings": {"window": "4s", "min_good": 0.5}},
        "number",
        seq,
        mean=[
            ("not_ready", None),
            ("uncertain", 5.5),
            ("good", 2.0),
            ("good", 2.0),
            ("good", 4.0),
            ("good", 4.0),
            ("uncertain", 7.0),
            ("uncertain", 7.0),
            ("uncertain", 8.0),
            ("bad", None),
        ],
        max=[
            ("not_ready", None),
            ("uncertain", 10.0),
            ("good", 3.0),
            ("good", 3.0),
            ("good", 5.0),
            ("good", 5.0),
            ("uncertain", 9.0),
            ("uncertain", 9.0),
            ("uncertain", 9.0),
            ("bad", None),
        ],
        # tick 2: 1 at 1 s and 3 at 3 s of the window; tick 6: 5, 7, 9 a
        # second apart; tick 8: 7 and 9 at 0 s and 1 s
        slope=[
            ("not_ready", None),
            ("uncertain", 9.0),
            ("good", 1.0),
            ("good", 1.0),
            ("good", 1.0),
            ("good", 1.0),
            ("uncertain", 2.0),
            ("uncertain", 2.0),
            ("uncertain", 2.0),
            ("bad", None),
        ],
        count=[1, 2, 3, 3, 3, 3, 3, 3, 2, 1],
    )
    # a slope needs two samples: with one good sample and two usable ones
    # it is of the usable ones, and uncertain (rule 7.3.6, round three)
    check_seq(
        "window slope",
        {"type": "window", "in": {"x": "x"}, "settings": {"window": "2s", "min_good": 0.5}},
        "number",
        [("good", 1.0), ("uncertain", 5.0), ("uncertain", 7.0)],
        mean=[("good", 1.0), ("good", 1.0), ("uncertain", 6.0)],
        slope=[("bad", None), ("uncertain", 4.0), ("uncertain", 2.0)],
        count=[1, 2, 2],
    )
    # only_new: a tick with no new sample is a hole the tolerance covers
    g = {
        "period": "1s",
        "inputs": {"x": {"max_age": "none"}},
        "blocks": [
            {
                "id": "w",
                "type": "window",
                "in": {"x": "x"},
                "settings": {"window": "2s", "min_good": 0.5, "only_new": True},
                "out": {"mean": "mean", "count": "count"},
            }
        ],
    }
    e = Engine(g)
    e.write("x", "good", 1.0, 0)
    check("window new 0", e.tick(0)[1]["mean"], ("good", 1.0))
    check("window new 1", e.tick(1 * S)[1]["mean"], ("good", 1.0))
    check("window new 2", e.tick(2 * S)[1]["mean"], ("not_ready", None))
    e.write("x", "uncertain", 3.0, 3 * S)
    check("window new 3", e.tick(3 * S)[1]["mean"], ("uncertain", 3.0))
    del g["blocks"][0]["settings"]["min_good"]
    refused("window only_new with no min_good", g)


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
                "settings": {"thermal_mass": 100, "heat_transfer": 1, "initial": 20, "settle": "2s"},
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
    # d temp/dt = -(temp - 120)/100, stepped exactly with its inputs held:
    # the distance from 120 is multiplied by exp(-0.01) each period
    s = math.exp(-0.01)
    check("model 1", e.tick(ns(1.0))[1]["temp"], ("good", 120 - 100 * s))
    check("model 2", e.tick(ns(2.0))[1]["temp"], ("good", 120 - 100 * s * s))
    # the two are a loop that holds a model: without `settle` it is refused
    del g["blocks"][0]["settings"]["settle"]
    refused("model loop with no settle", g)

    # a missed step is a doubt, seen on the `settle` ticks after it
    g = {
        "period": "1s",
        "max_catch_up": 3,
        "inputs": {"p": {"max_age": "none"}},
        "blocks": [
            {
                "id": "plant",
                "type": "thermal_mass",
                "in": {"power": "p", "ambient": 20},
                "settings": {
                    "thermal_mass": 10,
                    "heat_transfer": 1,
                    "initial": 20,
                    "settle": "2s",
                    "ride_through": "1s",
                },
                "out": {"temp": "temp", "elapsed": "el", "doubtful": "db"},
            }
        ],
    }
    e = Engine(g)

    def step(label, k, p, temp_state, doubtful):
        if p is not None:
            e.write("p", p[0], p[1], k * S)
        o = e.tick(k * S)[1]
        check("doubt %s temp" % label, o["temp"], (temp_state, 20.0))
        check("doubt %s elapsed" % label, o["el"], ("good", float(label) + 1))
        check("doubt %s doubtful" % label, o["db"], ("good", float(doubtful)))

    # tick 0: no power yet, so no step: a doubt, tick 0. It shows on ticks
    # 1 and 2, and `doubtful` counts it from tick 1, when the step is done.
    step("0", 0, None, "good", 0)
    step("1", 1, ("good", 0.0), "uncertain", 1)
    step("2", 2, None, "uncertain", 1)
    step("3", 3, None, "good", 1)
    # a step on an uncertain value at tick 4: ticks 5 and 6
    step("4", 4, ("uncertain", 0.0), "good", 1)
    step("5", 5, ("good", 0.0), "uncertain", 2)
    step("6", 6, None, "uncertain", 2)
    step("7", 7, None, "good", 2)
    # tick 8 steps on a held value, tick 9 does not step: the doubt is tick 9
    step("8", 8, ("bad", None), "good", 2)
    step("9", 9, None, "uncertain", 3)
    step("10", 10, ("good", 0.0), "uncertain", 4)
    step("11", 11, None, "uncertain", 4)
    step("12", 12, None, "good", 4)
    # a stall: tick 20, seven steps not taken. The tick before it is a doubt: uncertain
    # on ticks 13 and 14. The counters go on, and the gap is not counted.
    step("20", 20, None, "uncertain", 11)
    check("doubt gap info", e.info, info(True, 20, 20 * S, skipped=7))
    step("21", 21, None, "uncertain", 11)
    step("22", 22, None, "good", 11)
    # no step is too long: three time constants a period is accepted, and
    # there are no sub-steps (rule 7.8.7)
    g = {
        "period": "30s",
        "blocks": [
            {
                "id": "plant",
                "type": "thermal_mass",
                "in": {"power": 0, "ambient": 20},
                "settings": {"thermal_mass": 10, "heat_transfer": 1, "initial": 50},
                "out": {"temp": "temp"},
            }
        ],
    }
    e = Engine(g)
    e.tick(0)
    check("long step", e.tick(30 * S)[1]["temp"], ("good", 20 + 30 * math.exp(-3.0)))
    g["blocks"][0]["settings"]["substeps"] = 2
    refused("substeps is gone", g)

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
                "out": {"y": "y", "doubtful": "db"},
            }
        ],
    }
    e = Engine(g)
    e.write("u", "good", 1.0, ns(0.0))
    check("ss 0", e.tick(ns(0.0))[1]["y"], ("good", 1.0))
    check("ss 1", e.tick(ns(1.0))[1]["y"], ("good", 3.0))
    check("ss 2", e.tick(ns(2.0))[1]["y"], ("good", 4.0))
    # x is 1.75. u unusable: worked out on its last value, uncertain; no step
    e.write("u", "bad", None, 3 * S)
    o = e.tick(3 * S)[1]
    check("ss 3", o["y"], ("uncertain", 4.5))
    check("ss 3 doubtful", o["db"], ("good", 0.0))
    # no settle and no time constant: good again, and the counter says
    e.write("u", "good", 1.0, 4 * S)
    o = e.tick(4 * S)[1]
    check("ss 4", o["y"], ("good", 4.5))
    check("ss 4 doubtful", o["db"], ("good", 1.0))
    # rule D: an uncertain direct input. x is 1.875
    e.write("u", "uncertain", 1.0, 5 * S)
    check("ss 5", e.tick(5 * S)[1]["y"], ("uncertain", 4.75))
    e.write("u", "good", 1.0, 6 * S)
    o = e.tick(6 * S)[1]
    check("ss 6", o["y"], ("good", 4.875))
    check("ss 6 doubtful", o["db"], ("good", 2.0))


def two_masses(settle="2s"):
    """Since amendment 4 a loop holds one model block: a thermal mass whose
    ambient is its own temperature, by way of a formula. The formula's
    output is published as `b`."""
    st = {"thermal_mass": 10, "heat_transfer": 1, "initial": 20}
    if settle is not None:
        st["settle"] = settle
    return {
        "period": "1s",
        "max_catch_up": 3,
        "inputs": {"p": {"max_age": "none"}},
        "blocks": [
            {
                "id": "a",
                "type": "thermal_mass",
                "in": {"power": "p", "ambient": "b"},
                "settings": st,
                "out": {"temp": "a"},
            },
            {"id": "f", "type": "formula", "in": {"t": "a.temp"}, "settings": {"expr": "t"}, "out": {"y": "b"}},
        ],
    }


def test_model_loops():
    """Rule 7.8.8: a loop that holds a model is one block."""
    # a mass that takes its own temperature as its ambient, through a
    # formula: one loop. Nothing moves: it starts at 20 and the power is 0.
    e = Engine(two_masses())

    def step(k, p, want):
        if p is not None:
            e.write("p", p[0], p[1], k * S)
        o = e.tick(k * S)[1]
        check("masses %d a" % k, o["a"], (want, 20.0))
        check("masses %d b" % k, o["b"], (want, 20.0))

    step(0, ("good", 0.0), "good")
    # one bad sample to one of them, at tick 1: both uncertain for settle
    step(1, ("bad", None), "good")
    step(2, ("good", 0.0), "uncertain")
    step(3, None, "uncertain")
    step(4, None, "good")
    # an uncertain value from outside is a doubt as well
    step(5, ("uncertain", 0.0), "good")
    step(6, ("good", 0.0), "uncertain")
    step(7, None, "uncertain")
    step(8, None, "good")
    # a stall: tick 20; the tick before it is the loop's doubt
    step(20, None, "uncertain")
    check("masses gap info", e.info, info(True, 20, 20 * S, skipped=11))
    step(21, None, "uncertain")
    saved = e.save()
    step(22, ("bad", None), "good")  # tick 11 is a doubt, after the save
    # the loop's doubt is part of what a save holds; a restore is a gap
    e.restore(saved)
    e.write("p", "good", 0.0, 0)
    step(0, None, "uncertain")  # tick 22: the doubt is tick 21
    step(1, None, "uncertain")
    step(2, None, "good")
    refused("a model on a loop with no settle", two_masses(None))
    g = two_masses(None)
    g["blocks"][0]["in"]["ambient"] = 20
    Engine(g)  # no loop: the formula reads a, and a reads nothing of it
    g["blocks"][0]["in"]["ambient"] = "a.temp"
    refused("a model that reads its own output, with no settle", g)
    g["blocks"][0]["settings"]["settle"] = "0s"
    Engine(g)

    # a loop holds one model block and no more (amendment 4): two thermal
    # masses that each take the other's temperature are refused
    def mass(bid, ambient):
        return {
            "id": bid,
            "type": "thermal_mass",
            "in": {"power": 0, "ambient": ambient},
            "settings": {"thermal_mass": 10, "heat_transfer": 1, "initial": 20, "settle": "2s"},
        }

    refused("two model blocks on a loop", {"period": "1s", "blocks": [mass("a", "b.temp"), mass("b", "a.temp")]})
    # also when a formula and a delay stand between them
    refused(
        "two model blocks on a loop, apart",
        {
            "period": "1s",
            "blocks": [
                mass("a", "f.y"),
                mass("b", "a.temp"),
                {"id": "d", "type": "delay", "in": {"x": "b.temp"}, "settings": {"initial": 20}},
                {"id": "f", "type": "formula", "in": {"t": "d.y"}, "settings": {"expr": "t"}},
            ],
        },
    )
    # one after the other, with no way back, is no loop
    Engine({"period": "1s", "blocks": [mass("a", 20), mass("b", "a.temp")]})

    # a plant, a delay and a controller in one loop:
    #   plant: x' = 0.5 x + u, y = x;  d: plant.y one tick late;
    #   ctl: sp - d
    def loop(expr="sp - d", settle="2s", ticks=1, fallback=None):
        ctl = {"id": "ctl", "type": "formula", "in": {"sp": "sp", "d": "d.y"}, "settings": {"expr": expr}}
        ctl["out"] = {"y": "u"}
        if expr.startswith("when"):
            ctl["in"]["en"] = "en"
        if fallback is not None:
            ctl["fallback"] = {"y": fallback}
        return {
            "period": "1s",
            "inputs": {"sp": {"max_age": "none"}, "en": {"type": "boolean", "max_age": "none"}},
            "blocks": [
                {
                    "id": "plant",
                    "type": "state_space",
                    "in": {"u": "ctl.y"},
                    "settings": {"A": [[0.5]], "B": [1], "C": [1], "settle": settle},
                    "out": {"y": "y"},
                },
                {"id": "d", "type": "delay", "in": {"x": "plant.y"}, "settings": {"ticks": ticks, "initial": 0}},
                {"id": "dy", "type": "formula", "in": {"a": "d.y"}, "settings": {"expr": "a"}, "out": {"y": "dy"}},
                ctl,
            ],
        }

    e = Engine(loop())

    def step(k, sp, y, dy, u):
        e.write("sp", sp, 1.0, k * S)
        o = e.tick(k * S)[1]
        check("loop %d y" % k, o["y"], y)
        check("loop %d dy" % k, o["dy"], dy)
        check("loop %d u" % k, o["u"], u)

    #        plant.y              the delay          ctl
    step(0, "good", ("good", 0.0), ("good", 0.0), ("good", 1.0))
    step(1, "good", ("good", 1.0), ("good", 0.0), ("good", 1.0))
    # tick 2: the formula uses an uncertain value from outside: a doubt
    step(2, "uncertain", ("good", 1.5), ("good", 1.0), ("uncertain", 0.0))
    # ticks 3 and 4: the plant is uncertain. The formula follows its own
    # rule: at tick 3 both its values are good.
    step(3, "good", ("uncertain", 0.75), ("good", 1.5), ("good", -0.5))
    # tick 4: the delay gives what it took in at tick 3, uncertain
    step(4, "good", ("uncertain", -0.125), ("uncertain", 0.75), ("uncertain", 0.25))
    # tick 5: the loop is no longer within settle of its doubt, and the
    # delay gives the uncertain value it took in at tick 4 as good
    step(5, "good", ("good", 0.1875), ("good", -0.125), ("good", 1.125))
    step(6, "good", ("good", 1.21875), ("good", 0.1875), ("good", 0.8125))

    # the delays of a loop may not add up to more than settle
    Engine(loop(ticks=2))
    refused("loop: delays longer than settle", loop(ticks=3))
    refused("loop: a delay and settle of 0s", loop(settle="0s"))

    # a setpoint uncertain on every tick: the plant is uncertain on every
    # tick but the first, which gives its initial state
    e = Engine(loop())
    for k in range(5):
        e.write("sp", "uncertain", 1.0, k * S)
        o = e.tick(k * S)[1]
        check("loop unc %d" % k, o["y"][0], "good" if k == 0 else "uncertain")

    # an output that is not usable is a doubt, whether or not a fallback
    # stands in for it: sp / d divides by zero at tick 0
    e = Engine(loop(expr="sp / d", fallback=0))
    e.write("sp", "good", 1.0, 0)
    o = e.tick(0)[1]
    check("loop fb 0 u", o["u"], ("uncertain", 0.0))
    check("loop fb 0 y", o["y"], ("good", 0.0))
    o = e.tick(1 * S)[1]
    check("loop fb 1 u", o["u"], ("uncertain", 0.0))
    check("loop fb 1 y", o["y"], ("uncertain", 0.0))

    # round two: an output no block of the loop reads starts nothing. The
    # window's slope is bad at tick 0 (one sample); only its mean is read.
    #   plant: x' = 0.5 x + u, y = x;  w: plant.y over 2 ticks;  ctl: 1 - m
    def wloop(expr, ins):
        return {
            "period": "1s",
            "blocks": [
                {
                    "id": "plant",
                    "type": "state_space",
                    "in": {"u": "ctl.y"},
                    "settings": {"A": [[0.5]], "B": [1], "C": [1], "settle": "2s"},
                    "out": {"y": "y"},
                },
                {
                    "id": "w",
                    "type": "window",
                    "in": {"x": "plant.y"},
                    "settings": {"window": "2s", "min_good": 0.5},
                    "out": {"slope": "slope"},
                },
                {"id": "ctl", "type": "formula", "in": ins, "settings": {"expr": expr}, "out": {"y": "u"}},
            ],
        }

    e = Engine(wloop("1 - m", {"m": "w.mean"}))
    o = e.tick(0)[1]
    check("wloop 0 slope", o["slope"], ("bad", None))
    check("wloop 0 y", o["y"], ("good", 0.0))
    check("wloop 0 u", o["u"], ("good", 1.0))
    o = e.tick(1 * S)[1]  # the window holds 0 and 1
    check("wloop 1 slope", o["slope"], ("good", 1.0))
    check("wloop 1 y", o["y"], ("good", 1.0))
    check("wloop 1 u", o["u"], ("good", 0.5))
    check("wloop 2 y", e.tick(2 * S)[1]["y"], ("good", 1.0))
    # the same with the slope read by the formula: bad at tick 0 to a block
    # of the loop, so tick 0 is the loop's doubt and the plant misses a step
    e = Engine(wloop("1 - m + 0 * s", {"m": "w.mean", "s": "w.slope"}))
    o = e.tick(0)[1]
    check("wloop read 0 y", o["y"], ("good", 0.0))
    check("wloop read 0 u", o["u"], ("bad", None))
    # round three. Tick 1: the window holds a good 0 and an uncertain 0.
    # It is good on the one good sample, and its slope is of both usable
    # ones, uncertain and 0 (rule 7.3.6): the formula is uncertain, and
    # that starts nothing. The plant steps.
    o = e.tick(1 * S)[1]
    check("wloop read 1 y", o["y"], ("uncertain", 0.0))
    check("wloop read 1 u", o["u"], ("uncertain", 1.0))
    # tick 2: within settle of tick 0; two uncertain samples, 0 and 1
    o = e.tick(2 * S)[1]
    check("wloop read 2 y", o["y"], ("uncertain", 1.0))
    check("wloop read 2 u", o["u"], ("uncertain", 0.5))
    # tick 3: the loop has settled. The window counts the uncertain 1 it
    # took in at tick 2 as a good one (rule 7.8.8): 1 and 1, slope 0
    o = e.tick(3 * S)[1]
    check("wloop read 3 y", o["y"], ("good", 1.0))
    check("wloop read 3 u", o["u"], ("good", 0.0))
    o = e.tick(4 * S)[1]  # 1 and 0.5
    check("wloop read 4 y", o["y"], ("good", 0.5))
    check("wloop read 4 u", o["u"], ("good", 0.25))
    check("wloop read 5 y", e.tick(5 * S)[1]["y"], ("good", 0.5))

    # round two: for the loop's doubt a block counts as using every input
    # it has, whatever its own rule says. An integrator does not use a
    # `reset` that is false (rule 7.7.4), and its total is good; read from
    # outside the loop and uncertain, that `reset` is still a doubt.
    g = {
        "period": "1s",
        "inputs": {"r": {"type": "boolean", "max_age": "none"}},
        "blocks": [
            {
                "id": "plant",
                "type": "state_space",
                "in": {"u": "ctl.y"},
                "settings": {"A": [[0.5]], "B": [1], "C": [1], "settle": "2s"},
                "out": {"y": "y"},
            },
            {"id": "i", "type": "integrate", "in": {"x": "plant.y", "reset": "r"}, "out": {"y": "total"}},
            {"id": "ctl", "type": "formula", "in": {"t": "i.y"}, "settings": {"expr": "1 - 0 * t"}},
        ],
    }
    e = Engine(g)
    e.write("r", "uncertain", False, 0)
    o = e.tick(0)[1]
    check("iloop 0 total", o["total"], ("good", 0.0))
    check("iloop 0 y", o["y"], ("good", 0.0))
    e.write("r", "good", False, 1 * S)
    check("iloop 1 y", e.tick(1 * S)[1]["y"], ("uncertain", 1.0))
    check("iloop 2 y", e.tick(2 * S)[1]["y"], ("uncertain", 1.5))
    check("iloop 3 y", e.tick(3 * S)[1]["y"], ("good", 1.75))

    # round two, 7.11: an unusable value that gets into this loop does not
    # go round: the model does not step on it and still gives its state
    e = Engine(loop())
    want = [
        ("good", ("good", 0.0), ("good", 0.0), ("good", 1.0)),
        ("good", ("good", 1.0), ("good", 0.0), ("good", 1.0)),
        ("bad", ("good", 1.5), ("good", 1.0), ("bad", None)),
        ("good", ("uncertain", 1.5), ("good", 1.5), ("good", -0.5)),
        ("good", ("uncertain", 0.25), ("uncertain", 1.5), ("uncertain", -0.5)),
        ("good", ("good", -0.375), ("good", 0.25), ("good", 0.75)),
    ]
    for k, (sp, y, dy, u) in enumerate(want):
        e.write("sp", sp, 1.0 if sp == "good" else None, k * S)
        o = e.tick(k * S)[1]
        check("loop bad %d y" % k, o["y"], y)
        check("loop bad %d dy" % k, o["dy"], dy)
        check("loop bad %d u" % k, o["u"], u)

    # a formula does not use the branch it did not take: with en false the
    # uncertain setpoint is not used, and starts nothing
    e = Engine(loop(expr="when(en, sp - d, 0 * d)"))
    for k in range(3):
        e.write("sp", "uncertain", 1.0, k * S)
        e.write("en", "good", False, k * S)
        o = e.tick(k * S)[1]
        check("loop when %d u" % k, o["u"], ("good", 0.0))
        check("loop when %d y" % k, o["y"], ("good", 0.0))
    e.write("en", "good", True, 3 * S)
    o = e.tick(3 * S)[1]
    check("loop when 3 u", o["u"], ("uncertain", 1.0))
    check("loop when 3 y", o["y"], ("good", 0.0))
    check("loop when 4 y", e.tick(4 * S)[1]["y"], ("uncertain", 1.0))

    # a loop with no model is left alone (rule 5.6): one uncertain value
    # stays in it
    g = {
        "period": "1s",
        "inputs": {"x": {"max_age": "none"}},
        "blocks": [
            {"id": "d", "type": "delay", "in": {"x": "n"}, "settings": {"initial": 0}},
            {
                "id": "f",
                "type": "formula",
                "in": {"p": "d.y", "x": "x"},
                "settings": {"expr": "p + x"},
                "out": {"y": "n"},
            },
        ],
    }
    e = Engine(g)
    e.write("x", "uncertain", 1.0, 0)
    check("bare loop 0", e.tick(0)[1]["n"], ("uncertain", 1.0))
    e.write("x", "good", 1.0, 1 * S)
    check("bare loop 1", e.tick(1 * S)[1]["n"], ("uncertain", 2.0))
    check("bare loop 9", e.tick(9 * S)[1]["n"], ("uncertain", 10.0))


def test_round_three():
    """`gaps` on every block that gives `elapsed`; what a loop holds against
    its settle; a low-pass on a loop that has settled."""
    ports = ("elapsed", "gaps")
    g = {
        "period": "1s",
        "max_catch_up": 3,
        "inputs": {
            "x": {"max_age": "none"},
            "b": {"type": "boolean", "max_age": "none"},
            "r": {"type": "boolean", "max_age": "none"},
        },
        "blocks": [
            {"id": "h", "type": "hysteresis", "in": {"x": "x"}, "settings": {"rise": 10, "fall": 5}},
            {"id": "l", "type": "latch", "in": {"set": "b", "reset": "r"}},
            {"id": "hf", "type": "held_for", "in": {"x": "b"}, "settings": {"time": "1s", "on_bad": "reset"}},
            {"id": "st", "type": "since_true", "in": {"x": "b"}, "settings": {"time": "1s", "on_bad": "unknown"}},
            {
                "id": "m",
                "type": "thermal_mass",
                "in": {"power": 0, "ambient": 20},
                "settings": {"thermal_mass": 10, "heat_transfer": 1, "initial": 20},
            },
        ],
    }
    for b in g["blocks"]:
        b["out"] = {p: "%s_%s" % (b["id"], p) for p in ports}
    e = Engine(g)

    def step(label, now, x, b, r, want):
        """want: for h, l, hf, st, m in turn, (elapsed, gaps)."""
        e.write("x", "good", x, now * S)
        e.write("b", "good", b, now * S)
        e.write("r", "good", r, now * S)
        o = e.tick(now * S)[1]
        for bid, (el, gp) in zip(("h", "l", "hf", "st", "m"), want):
            check("gaps %s %s elapsed" % (label, bid), o[bid + "_elapsed"], ("good", float(el)))
            check("gaps %s %s gaps" % (label, bid), o[bid + "_gaps"], ("good", float(gp)))

    #                               h       l       hf      st      m
    step("0", 0, 7.0, False, False, [(1, 0), (1, 0), (0, 0), (1, 0), (1, 0)])
    step("1", 1, 12.0, False, False, [(1, 0), (2, 0), (0, 0), (2, 0), (2, 0)])
    # a stall: tick 10, eight passed over. The hysteresis and the latch go on and count it. The
    # timer starts, and the clock is set, at the gap's tick: one each.
    step("2", 10, 7.0, True, False, [(10, 1), (11, 1), (1, 1), (1, 1), (11, 1)])
    check("gaps 2 info", e.info, info(True, 10, 10 * S, skipped=8))
    # tick 3: the hysteresis changes and the clock is set again, after the
    # gap: none. The timer's run still began at the gap's tick.
    step("3", 11, 4.0, True, False, [(1, 0), (12, 1), (2, 1), (1, 0), (12, 1)])
    # tick 4: the latch is cleared, after the gap; the timer stops
    step("4", 12, 4.0, False, True, [(2, 0), (1, 0), (0, 0), (2, 0), (13, 1)])
    # a second stall: tick 5. The hysteresis changes, and the latch is
    # cleared, at the gap's tick: each counts from it, and counts it.
    step("5", 20, 12.0, False, True, [(1, 1), (1, 1), (0, 0), (10, 1), (21, 2)])
    check("gaps 5 info", e.info, info(True, 20, 20 * S, skipped=7))
    # tick 6: the timer starts a tick after the gap: none
    step("6", 21, 12.0, True, False, [(2, 1), (2, 1), (1, 0), (1, 0), (22, 2)])
    # a reset sets them to zero
    e.reset()
    step("reset", 0, 7.0, False, False, [(1, 0), (1, 0), (0, 0), (1, 0), (1, 0)])

    # a gap whose tick is the tick of an integrator's reset is counted
    g = {
        "period": "1s",
        "max_catch_up": 3,
        "inputs": {"r": {"type": "boolean", "max_age": "none"}},
        "blocks": [{"id": "i", "type": "integrate", "in": {"x": 1, "reset": "r"}, "out": {"y": "y", "gaps": "gaps"}}],
    }
    e = Engine(g)
    e.write("r", "good", False, 0)
    check("integ gap reset 0", e.tick(0)[1]["gaps"], ("good", 0.0))
    o = e.tick(10 * S)[1]  # a stall, tick 10, and no reset
    check("integ gap reset 1 gaps", o["gaps"], ("good", 1.0))
    check("integ gap reset 1 y", o["y"], ("good", 2.0))
    e.write("r", "good", True, 11 * S)
    o = e.tick(11 * S)[1]  # a reset a tick after the gap: none
    check("integ gap reset 2 gaps", o["gaps"], ("good", 0.0))
    o = e.tick(20 * S)[1]  # a stall, tick 20, with the reset still true
    check("integ gap reset 3 info", e.info, info(True, 20, 20 * S, skipped=8))
    check("integ gap reset 3 gaps", o["gaps"], ("good", 1.0))
    check("integ gap reset 3 y", o["y"], ("good", 1.0))
    o = e.tick(21 * S)[1]  # reset again, a tick after the gap
    check("integ gap reset 4 gaps", o["gaps"], ("good", 0.0))

    # the slope of a window that is good on one good sample is of its
    # usable samples, and uncertain (rule 7.3.6)
    check_seq(
        "slope usable",
        {"type": "window", "in": {"x": "x"}, "settings": {"window": "4s", "min_good": 0.25}},
        "number",
        [("good", 1.0), ("uncertain", 2.0), ("uncertain", 3.0), ("uncertain", 4.0), ("good", 5.0)],
        # tick 4: the window is 2u 3u 4u 5: one good sample still
        mean=[("good", 1.0), ("good", 1.0), ("good", 1.0), ("good", 1.0), ("good", 5.0)],
        slope=[("bad", None), ("uncertain", 1.0), ("uncertain", 1.0), ("uncertain", 1.0), ("uncertain", 1.0)],
    )
    # with fewer usable samples than are needed, rule 7.3.3 gives the slope
    # its state as it gives the rest (as assumed): 4 ticks, 3 needed
    check_seq(
        "slope too few",
        {"type": "window", "in": {"x": "x"}, "settings": {"window": "4s", "min_good": 0.75}},
        "number",
        [("good", 1.0), ("good", 2.0), ("good", 3.0)],
        slope=[("not_ready", None), ("not_ready", None), ("good", 1.0)],
    )

    # what else remembers on a loop is held against its settle
    def plant(settle="3s", u="ctl.y"):
        return {
            "id": "plant",
            "type": "state_space",
            "in": {"u": u},
            "settings": {"A": [[0.5]], "B": [1], "C": [1], "settle": settle},
            "out": {"y": "y"},
        }

    def lploop(lp_settings, settle="3s", more=()):
        return {
            "period": "1s",
            "inputs": {"sp": {"max_age": "none"}},
            "blocks": [
                plant(settle),
                {"id": "lp", "type": "lowpass", "in": {"x": "plant.y"}, "settings": lp_settings, "out": {"y": "lp"}},
                # the same low-pass, off the loop
                {"id": "lq", "type": "lowpass", "in": {"x": "plant.y"}, "settings": lp_settings, "out": {"y": "lq"}},
                {
                    "id": "ctl",
                    "type": "formula",
                    "in": {"sp": "sp", "a": "lp.y"},
                    "settings": {"expr": "sp + 0 * a"},
                    "out": {"y": "u"},
                },
            ]
            + list(more),
        }

    Engine(lploop({"tau": "1s", "settle": "3s"}))
    Engine(lploop({"tau": "1s"}))  # three time constants: 3 ticks
    refused("loop: low-pass settle longer than the loop's", lploop({"tau": "1s", "settle": "4s"}))
    refused("loop: low-pass default settle longer than the loop's", lploop({"tau": "1s"}, settle="2s"))
    g = lploop({"tau": "1s", "settle": "2s"})
    g["blocks"].append({"id": "d", "type": "delay", "in": {"x": "lp.y"}, "settings": {"initial": 0}})
    g["blocks"][3]["in"]["a"] = "d.y"
    Engine(g)  # 2 and 1 are not more than 3
    g["blocks"][4]["settings"]["ticks"] = 2
    refused("loop: a low-pass and a delay longer than settle", g)
    w = {"id": "w", "type": "window", "in": {"x": "plant.y"}, "settings": {"window": "3s", "min_good": 0.5}}
    ctl = {"id": "ctl", "type": "formula", "in": {"m": "w.mean"}, "settings": {"expr": "1 - m"}}
    Engine({"period": "1s", "blocks": [plant("3s"), w, ctl]})
    refused("loop: a window longer than settle", {"period": "1s", "blocks": [plant("2s"), w, ctl]})
    # an estimator on a loop that holds a model block is refused
    est = {
        "id": "est",
        "type": "estimator",
        "in": {"u": "plant.y", "z": "zz"},
        "settings": {
            "model": {"type": "state_space", "A": [[1]], "B": [0], "C": [1]},
            "q": {"x0": 1},
            "p0": {"x0": 4},
            "measure": {"z": {"of": "y", "r": 1}},
            "consistency": "none",
        },
    }
    refused(
        "loop: a model block and an estimator",
        {"period": "1s", "inputs": {"zz": {"max_age": "none"}}, "blocks": [plant("3s", "est.x0"), est]},
    )
    # off the loop it is accepted, and so is an estimator on a loop with
    # no model block
    Engine({"period": "1s", "inputs": {"zz": {"max_age": "none"}}, "blocks": [plant("3s", 1), est]})
    est2 = dict(est, **{"in": {"u": "d.y", "z": "zz"}})
    d = {"id": "d", "type": "delay", "in": {"x": "est.x0"}, "settings": {"initial": 0}}
    Engine({"period": "1s", "inputs": {"zz": {"max_age": "none"}}, "blocks": [est2, d]})

    # a low-pass on a loop that has settled has no doubt. The setpoint is
    # uncertain at tick 1: the loop's doubt. The plant is uncertain on
    # ticks 2, 3, 4, and so are both low-passes, by their input; each has
    # tick 4 for its doubt. At tick 5 the loop has settled: the one on the
    # loop is good, and the one off it is uncertain for its own settle,
    # ticks 5, 6, 7.
    e = Engine(lploop({"tau": "1s", "settle": "3s"}))
    want = [
        # sp,        plant,       lp,          lq
        ("good", "good", "good", "good"),
        ("uncertain", "good", "good", "good"),
        ("good", "uncertain", "uncertain", "uncertain"),
        ("good", "uncertain", "uncertain", "uncertain"),
        ("good", "uncertain", "uncertain", "uncertain"),
        ("good", "good", "good", "uncertain"),
        ("good", "good", "good", "uncertain"),
        ("good", "good", "good", "uncertain"),
        ("good", "good", "good", "good"),
    ]
    for k, (sp, y, lp, lq) in enumerate(want):
        e.write("sp", sp, 1.0, k * S)
        o = e.tick(k * S)[1]
        check("lploop %d y" % k, o["y"][0], y)
        check("lploop %d lp" % k, o["lp"][0], lp)
        check("lploop %d lq" % k, o["lq"][0], lq)
        check("lploop %d same value" % k, o["lp"][1], o["lq"][1])


def test_round_four():
    """Rule 7.8.8: on a settled loop what was taken in as uncertain becomes
    good and stays so; a window still filling is the loop's doubt."""

    def plant(settle):
        return {
            "id": "plant",
            "type": "state_space",
            "in": {"u": "ctl.y"},
            "settings": {"A": [[0.5]], "B": [1], "C": [1], "settle": settle},
            "out": {"y": "y"},
        }

    # a window. The plant's state is 0, 0, 1, 1.5, 1.75, 1.875, 1.9375,
    # 1.96875 on ticks 0 to 7 (it misses the step of tick 0, when the
    # window, with one sample of two needed, is not_ready: the loop's
    # doubt from the start). The setpoint is uncertain at ticks 1 and 5.
    g = {
        "period": "1s",
        "inputs": {"sp": {"max_age": "none"}},
        "blocks": [
            plant("3s"),
            {
                "id": "w",
                "type": "window",
                "in": {"x": "plant.y"},
                "settings": {"window": "3s", "min_good": 0.6},
                "out": {"mean": "mean"},
            },
            {"id": "ctl", "type": "formula", "in": {"sp": "sp", "m": "w.mean"}, "settings": {"expr": "sp + 0 * m"}},
        ],
    }
    e = Engine(g)
    want = [
        (("good", 0.0), ("not_ready", None)),
        # the doubts of ticks 0 and 1: uncertain on ticks 1 to 4
        (("uncertain", 0.0), ("uncertain", 0.0)),
        (("uncertain", 1.0), ("uncertain", 1.0 / 3)),
        (("uncertain", 1.5), ("uncertain", 2.5 / 3)),
        (("uncertain", 1.75), ("uncertain", 4.25 / 3)),
        # tick 5: settled. The samples of ticks 3 and 4 become good.
        (("good", 1.875), ("good", 5.125 / 3)),
        # tick 6: in doubt again (tick 5). The sample of tick 4 stays good:
        # two good ones, 1.75 and 1.875, and the statistics are of those
        (("uncertain", 1.9375), ("good", 1.8125)),
        # tick 7: the samples of ticks 5, 6, 7: one good one
        (("uncertain", 1.96875), ("uncertain", 5.78125 / 3)),
    ]
    for k, (y, mean) in enumerate(want):
        e.write("sp", "uncertain" if k in (1, 5) else "good", 1.0, k * S)
        o = e.tick(k * S)[1]
        check("r4 window %d y" % k, o["y"], y)
        check("r4 window %d mean" % k, o["mean"], mean)

    # a delay of two ticks; the setpoint is uncertain at ticks 1 and 4.
    #   plant: x' = 0.5 x + u;  d: plant.y two ticks late;  ctl: sp - d
    g = {
        "period": "1s",
        "inputs": {"sp": {"max_age": "none"}},
        "blocks": [
            plant("2s"),
            {"id": "d", "type": "delay", "in": {"x": "plant.y"}, "settings": {"ticks": 2, "initial": 0}},
            {"id": "dy", "type": "formula", "in": {"a": "d.y"}, "settings": {"expr": "a"}, "out": {"y": "dy"}},
            {
                "id": "ctl",
                "type": "formula",
                "in": {"sp": "sp", "d": "d.y"},
                "settings": {"expr": "sp - d"},
                "out": {"y": "u"},
            },
        ],
    }
    e = Engine(g)
    want = [
        #  plant.y               the delay          ctl
        (("good", 0.0), ("good", 0.0), ("good", 1.0)),
        (("good", 1.0), ("good", 0.0), ("uncertain", 1.0)),
        (("uncertain", 1.5), ("good", 0.0), ("good", 1.0)),
        (("uncertain", 1.75), ("good", 1.0), ("good", 0.0)),
        # tick 4: settled. The delay holds 1.5 and 1.75, both taken in as
        # uncertain: both become good. The setpoint is a new doubt.
        (("good", 0.875), ("good", 1.5), ("uncertain", -0.5)),
        # tick 5: within settle of tick 4, and the 1.75 stays good
        (("uncertain", -0.0625), ("good", 1.75), ("good", -0.75)),
    ]
    for k, (y, dy, u) in enumerate(want):
        e.write("sp", "uncertain" if k in (1, 4) else "good", 1.0, k * S)
        o = e.tick(k * S)[1]
        check("r4 delay %d y" % k, o["y"], y)
        check("r4 delay %d dy" % k, o["dy"], dy)
        check("r4 delay %d u" % k, o["u"], u)

    # a low-pass. f passes the plant's output at tick 4 only, and gives a
    # good 5 otherwise; the setpoint is uncertain at ticks 1 and 5. The
    # low-pass takes an uncertain input at tick 4: its doubt. At tick 5
    # the loop has settled and that doubt is cleared; at ticks 6 and 7
    # the loop is in doubt again and the low-pass, on a good input, is good
    # (its own settle would have run to tick 7).
    g = {
        "period": "1s",
        "inputs": {"sp": {"max_age": "none"}, "en": {"type": "boolean", "max_age": "none"}},
        "blocks": [
            plant("3s"),
            {"id": "f", "type": "formula", "in": {"en": "en", "y": "plant.y"}, "settings": {"expr": "when(en, y, 5)"}},
            {
                "id": "lp",
                "type": "lowpass",
                "in": {"x": "f.y"},
                "settings": {"tau": "1s", "settle": "3s"},
                "out": {"y": "lp"},
            },
            {"id": "ctl", "type": "formula", "in": {"sp": "sp", "a": "lp.y"}, "settings": {"expr": "sp + 0 * a"}},
        ],
    }
    e = Engine(g)
    want = [
        # plant,      lp
        ("good", "good"),
        ("good", "good"),
        ("uncertain", "good"),
        ("uncertain", "good"),
        ("uncertain", "uncertain"),
        ("good", "good"),
        ("uncertain", "good"),
        ("uncertain", "good"),
    ]
    for k, (y, lp) in enumerate(want):
        e.write("sp", "uncertain" if k in (1, 5) else "good", 1.0, k * S)
        e.write("en", "good", k == 4, k * S)
        o = e.tick(k * S)[1]
        check("r4 lowpass %d y" % k, o["y"][0], y)
        check("r4 lowpass %d lp" % k, o["lp"][0], lp)


def one_block(block, in_type="number", max_catch_up=1):
    """One input `x`, one block, every output published under its port's
    name. A call more than `max_catch_up` ticks late is a stall."""
    blk = dict(block, id="b")
    g = {
        "period": "1s",
        "max_catch_up": max_catch_up,
        "inputs": {"x": {"type": in_type, "max_age": "none"}},
        "blocks": [blk],
    }
    e = Engine(g)
    blk["out"] = {p: p for p in e._blocks["b"].out_ports}
    return Engine(g)


def put(e, now, state=None, value=None):
    """Write x (if a state is given), call, and give the outputs."""
    if state is not None:
        e.write("x", state, value, now * S)
    return e.tick(now * S)[1]


def counts(label, o, **want):
    for port, w in want.items():
        check("%s %s" % (label, port), o[port], ("good", float(w)))


def test_gap_length():
    """Amendment 3: the tick a gap runs, and how many it passed over."""
    g = {
        "period": "1s",
        "blocks": [
            {
                "id": "i",
                "type": "integrate",
                "in": {"x": 1},
                "out": {"y": "y", "missed": "missed", "elapsed": "elapsed", "gaps": "gaps"},
            }
        ],
    }
    e = Engine(g)

    def call(label, now, inf, y, missed, elapsed, gaps):
        o = e.tick(now)[1]
        check("len %s info" % label, e.info, inf)
        check("len %s y" % label, o["y"], ("good", float(y)))
        counts("len " + label, o, missed=missed, elapsed=elapsed, gaps=gaps)

    call("0", 0, info(False, 0, 0), 1, 0, 1, 0)
    call("1", 1 * S, info(False, 1, 1 * S), 2, 0, 2, 0)
    # away 5 s: five ticks would have been due, 2 to 6. Tick 6 runs, at the
    # call's now, and four are passed over: missed and elapsed take them in.
    e.rebase(5 * S)
    call("6", 100 * S, info(True, 6, 100 * S, skipped=4), 3, 4, 7, 1)
    call("7", 101 * S, info(False, 7, 101 * S), 4, 4, 8, 1)
    # a half rounds up: 1.5 s is two ticks, 8 and 9
    e.rebase(1500000000)
    call("9", 200 * S, info(True, 9, 200 * S, skipped=1), 5, 5, 10, 2)
    # one ns less is one tick: none passed over
    e.rebase(1499999999)
    call("10", 300 * S, info(True, 10, 300 * S), 6, 5, 11, 3)
    # less than half a period: none would have been due; the next tick runs
    e.rebase(499999999)
    call("11", 10 * S, info(True, 11, 10 * S), 7, 5, 12, 4)
    e.rebase(0)
    call("12", 20 * S, info(True, 12, 20 * S), 8, 5, 13, 5)
    # refused, and nothing changes: the next call is no rebase
    raises("len negative", lambda: e.rebase(-1))
    raises("len fraction", lambda: e.rebase(1.5))
    raises("len float", lambda: e.rebase(2.0 * S))
    raises("len true", lambda: e.rebase(True))
    raises("len text", lambda: e.rebase("1s"))
    raises("len over 64 bits", lambda: e.rebase(2**63))
    raises("len refused, so no rebase: backwards", lambda: e.tick(19 * S))
    call("13", 21 * S, info(False, 13, 21 * S), 9, 5, 14, 5)
    # of two before the call, the second counts
    e.rebase(5 * S)
    e.rebase()
    call("14", 0, info(True, 14, 0, skipped=None), 10, 5, 15, 6)
    e.rebase()
    e.rebase(3 * S)
    call("17", 0, info(True, 17, 0, skipped=2), 11, 7, 18, 7)
    # a restore, and the host says how long: a gap of that length
    saved = e.save()
    call("18", 1 * S, info(False, 18, 1 * S), 12, 7, 19, 7)
    e.restore(saved)
    e.rebase(2 * S)
    call("19", 50 * S, info(True, 19, 50 * S, skipped=1), 12, 8, 20, 8)
    # a restore alone: nobody knows. One more than the last tick run, and
    # nothing is added to a count but one to gaps
    e.restore(saved)
    call("18 again", 60 * S, info(True, 18, 60 * S, skipped=None), 12, 7, 19, 8)
    # a state saved between a rebase and its call is as one saved before it
    e.rebase(4 * S)
    saved = e.save()
    call("22", 0, info(True, 22, 0, skipped=3), 13, 10, 23, 9)
    e.restore(saved)
    call("19 again", 0, info(True, 19, 0, skipped=None), 13, 7, 20, 9)
    # a restore after a rebase with a length: the length went with the
    # rebase, and nobody knows (as assumed)
    e.rebase(5 * S)
    e.restore(saved)
    call("19 once more", 0, info(True, 19, 0, skipped=None), 13, 7, 20, 9)
    # a reset after a rebase with a length is a reset
    e.rebase(9 * S)
    e.reset()
    call("reset", 5 * S, info(False, 0, 5 * S), 1, 0, 1, 0)
    # and a rebase with a length before any tick is none
    e.reset()
    e.rebase(9 * S)
    call("before any tick", 5 * S, info(False, 0, 5 * S), 1, 0, 1, 0)

    # a stall: the tick that runs keeps its own number and time
    g["max_catch_up"] = 3
    e = Engine(g)
    call("s0", 0, info(False, 0, 0), 1, 0, 1, 0)
    call("s3", 3 * S, info(False, 3, 3 * S), 4, 0, 4, 0)  # three, not more
    call("s7", 7 * S + 499999999, info(True, 7, 7 * S, skipped=3), 5, 3, 8, 1)
    check("len s none due", e.tick(7 * S + 499999999), (0, None))
    call("s8", 7 * S + 500000000, info(False, 8, 8 * S), 6, 3, 9, 1)


def test_gap_blocks():
    """Amendment 3, rule 8.6: each block does what the ticks nobody saw
    would have done, had each been run with nothing usable to read."""
    # --- delay: three ticks, with an initial value
    e = one_block({"type": "delay", "in": {"x": "x"}, "settings": {"ticks": 3, "initial": 0}})
    for k in range(3):
        check("gd delay %d" % k, put(e, k, "good", k + 1.0)["y"], ("good", 0.0))
    # it holds 1, 2, 3. Ticks 3 and 4 are passed over: it moves on two
    # places, and at tick 5 gives its input of tick 2
    o = put(e, 5, "good", 9.0)
    check("gd delay info", e.info, info(True, 5, 5 * S, skipped=2))
    check("gd delay 5", o["y"], ("good", 3.0))
    check("gd delay 6", put(e, 6)["y"], ("not_ready", None))  # tick 3
    check("gd delay 7", put(e, 7)["y"], ("not_ready", None))  # tick 4
    check("gd delay 8", put(e, 8)["y"], ("good", 9.0))  # tick 5
    # more passed over than it holds
    check("gd delay 20", put(e, 20)["y"], ("not_ready", None))
    check("gd delay 20 info", e.info, info(True, 20, 20 * S, skipped=11))
    check("gd delay 22", put(e, 22)["y"], ("not_ready", None))
    check("gd delay 23", put(e, 23)["y"], ("good", 9.0))  # tick 20
    # nobody knows: everything it holds is not_ready, an initial value too
    e = one_block({"type": "delay", "in": {"x": "x"}, "settings": {"ticks": 3, "initial": 0}})
    check("gd delay unknown 0", put(e, 0, "good", 1.0)["y"], ("good", 0.0))
    e.rebase()
    for k in (1, 2, 3):
        check("gd delay unknown %d" % k, put(e, k, "good", 4.0)["y"], ("not_ready", None))
    check("gd delay unknown 4", put(e, 4)["y"], ("good", 4.0))
    # a running value kept by a formula and a delay is not_ready after a
    # gap as long as its delay, and goes on being so (7.11)
    g = {
        "period": "1s",
        "max_catch_up": 1,
        "blocks": [
            {"id": "d", "type": "delay", "in": {"x": "n"}, "settings": {"initial": 0}},
            {"id": "f", "type": "formula", "in": {"p": "d.y"}, "settings": {"expr": "p + 1"}, "out": {"y": "n"}},
        ],
    }
    e = Engine(g)
    check("gd counter 0", e.tick(0)[1]["n"], ("good", 1.0))
    check("gd counter 1", e.tick(1 * S)[1]["n"], ("good", 2.0))
    check("gd counter 3", e.tick(3 * S)[1]["n"], ("not_ready", None))
    check("gd counter 4", e.tick(4 * S)[1]["n"], ("not_ready", None))

    # --- window: 4 ticks, two needed
    win = {"type": "window", "in": {"x": "x"}, "settings": {"window": "4s", "min_good": 0.5}}

    def filled():
        e = one_block(win)
        for k in range(4):
            o = put(e, k, "good", k + 1.0)
        check("gd window filled", o["mean"], ("good", 2.5))
        return e

    # two passed over: the window at tick 6 is 4, -, -, 7
    e = filled()
    o = put(e, 6, "good", 7.0)
    check("gd window 2 mean", o["mean"], ("good", 5.5))
    check("gd window 2 count", o["count"], ("good", 2.0))
    # three passed over: -, -, -, 7: one usable, and the rest not_ready
    e = filled()
    o = put(e, 7, "good", 7.0)
    check("gd window 3 mean", o["mean"], ("not_ready", None))
    check("gd window 3 count", o["count"], ("good", 1.0))
    # a rebase of known length keeps what the window holds: away 2 s is
    # ticks 4 and 5, one passed over: 3, 4, -, 7
    e = filled()
    e.rebase(2 * S)
    o = put(e, 0, "good", 7.0)
    check("gd window known info", e.info, info(True, 5, 0, skipped=1))
    check("gd window known mean", o["mean"], ("good", 14.0 / 3))
    check("gd window known count", o["count"], ("good", 3.0))
    # nobody knows: none of its ticks holds a sample
    e = filled()
    e.rebase()
    o = put(e, 0, "good", 7.0)
    check("gd window unknown mean", o["mean"], ("not_ready", None))
    check("gd window unknown count", o["count"], ("good", 1.0))

    # --- deadband, ride_through of 3 ticks
    dead = {"type": "deadband", "in": {"x": "x"}, "settings": {"step": 1, "ride_through": "3s"}}

    def held():
        e = one_block(dead)
        check("gd deadband 0", put(e, 0, "good", 0.0)["y"], ("good", 0.0))
        return e

    # two passed over, within ride_through: it holds the 0
    check("gd deadband 2", put(held(), 3, "good", 0.5)["y"], ("good", 0.0))
    # and the tick that runs is the third unusable one in a row
    check("gd deadband 2, bad", put(held(), 3, "bad")["y"], ("uncertain", 0.0))
    # three passed over, and unusable at the tick that runs: the fourth
    check("gd deadband 3, bad", put(held(), 4, "bad")["y"], ("bad", None))
    check("gd deadband 3", put(held(), 4, "good", 0.5)["y"], ("good", 0.0))
    # four passed over: it forgets, and the next usable input is a first one
    check("gd deadband 4", put(held(), 5, "good", 0.5)["y"], ("good", 0.5))
    # nobody knows: it forgets
    e = held()
    e.rebase()
    check("gd deadband unknown", put(e, 0, "good", 0.5)["y"], ("good", 0.5))
    # none passed over: it holds
    e = held()
    e.rebase(1 * S)
    check("gd deadband none", put(e, 0, "good", 0.5)["y"], ("good", 0.0))
    check("gd deadband none info", e.info, info(True, 1, 0))

    # --- low-pass: it decays over the ticks it missed (rule 7.4.5)
    a = math.exp(-1.0)
    e = one_block({"type": "lowpass", "in": {"x": "x"}, "settings": {"tau": "1s", "ride_through": "3s"}})
    check("gd lowpass 0", put(e, 0, "good", 0.0)["y"], ("good", 0.0))
    check("gd lowpass ride", put(e, 3, "good", 1.0)["y"], ("good", 1 - a**3))
    e = one_block({"type": "lowpass", "in": {"x": "x"}, "settings": {"tau": "1s"}})
    check("gd lowpass 0", put(e, 0, "good", 0.0)["y"], ("good", 0.0))
    check("gd lowpass forgot", put(e, 3, "good", 1.0)["y"], ("good", 1.0))

    # --- hysteresis: stays as it was; the ticks passed over are doubtful
    e = one_block({"type": "hysteresis", "in": {"x": "x"}, "settings": {"rise": 10, "fall": 5}})
    counts("gd hyst 0", put(e, 0, "good", 12.0), elapsed=1, doubtful=0, gaps=0)
    o = put(e, 4)
    check("gd hyst 4", o["y"], ("good", True))
    counts("gd hyst 4", o, elapsed=5, doubtful=3, gaps=1)
    e.rebase()  # nobody knows: one more gap, and nothing else
    o = put(e, 0, "good", 12.0)
    check("gd hyst unknown", o["y"], ("good", True))
    counts("gd hyst unknown", o, elapsed=6, doubtful=3, gaps=2)

    # --- latch: doubtful goes up only while it is not set
    e = one_block({"type": "latch", "in": {"set": "x"}}, "boolean")
    counts("gd latch 0", put(e, 0, "good", False), elapsed=1, doubtful=0, gaps=0)
    counts("gd latch 4", put(e, 4), elapsed=5, doubtful=3, gaps=1)
    o = put(e, 5, "good", True)
    check("gd latch 5", o["y"], ("good", True))
    counts("gd latch 9", put(e, 9), elapsed=10, doubtful=3, gaps=2)

    # --- held_for with hold: 5 s, hold_limit 3 s
    hold = {"type": "held_for", "in": {"x": "x"}, "settings": {"time": "5s", "on_bad": "hold", "hold_limit": "3s"}}
    e = one_block(hold, "boolean")
    counts("gd hold 0", put(e, 0, "good", True), elapsed=1, doubtful=0, gaps=0)
    # two passed over, within the limit: the timer runs on
    o = put(e, 3)
    check("gd hold 3", o["y"], ("good", False))
    counts("gd hold 3", o, elapsed=4, doubtful=2, gaps=1)
    put(e, 4)
    check("gd hold 5", put(e, 5)["y"], ("good", False))
    o = put(e, 6)  # started more than five ticks before
    check("gd hold 6", o["y"], ("good", True))
    counts("gd hold 6", o, elapsed=7, doubtful=2, gaps=1)
    # four passed over, past the limit: it stops, and starts at tick 11
    o = put(e, 11)
    check("gd hold 11", o["y"], ("good", False))
    counts("gd hold 11", o, elapsed=1, doubtful=0, gaps=1)
    # the stretch is the unusable ticks before the gap, and those passed
    # over, and the one that runs: 1 + 2 is within 3, and then 4 is not
    e = one_block(hold, "boolean")
    put(e, 0, "good", True)
    counts("gd hold stretch 1", put(e, 1, "bad"), elapsed=2, doubtful=1, gaps=0)
    o = put(e, 4)
    check("gd hold stretch 4", o["y"], ("bad", None))
    counts("gd hold stretch 4", o, elapsed=0, doubtful=0, gaps=0)
    e = one_block(hold, "boolean")
    put(e, 0, "good", True)
    put(e, 1, "bad")
    o = put(e, 3)  # one passed over: the stretch is 2, and 3 at this tick
    check("gd hold stretch 3", o["y"], ("uncertain", False))
    counts("gd hold stretch 3", o, elapsed=4, doubtful=3, gaps=1)
    # nobody knows: the timer stops
    e = one_block(hold, "boolean")
    put(e, 0, "good", True)
    e.rebase()
    counts("gd hold unknown", put(e, 0, "good", True), elapsed=1, doubtful=0, gaps=1)
    # a gap that passed over none adds one to gaps and does nothing else,
    # whatever the table says (rule 8.6, round two): no timer stops
    e = one_block({"type": "held_for", "in": {"x": "x"}, "settings": {"time": "1s", "on_bad": "reset"}}, "boolean")
    put(e, 0, "good", True)
    put(e, 1)
    e.rebase(1 * S)
    o = put(e, 0, "good", True)
    check("gd reset none", o["y"], ("good", True))
    counts("gd reset none", o, elapsed=3, doubtful=0, gaps=1)
    e = one_block(
        {"type": "held_for", "in": {"x": "x"}, "settings": {"time": "1s", "on_bad": "hold", "hold_limit": "1s"}},
        "boolean",
    )
    put(e, 0, "good", True)
    put(e, 1)
    e.rebase(1 * S)
    o = put(e, 0, "good", True)
    check("gd hold none", o["y"], ("good", True))
    counts("gd hold none", o, elapsed=3, doubtful=0, gaps=1)

    # --- since_true: the clock is not set, so a long gap is a long quiet
    since = {"type": "since_true", "in": {"x": "x"}, "settings": {"time": "3s", "on_bad": "assume_false"}}
    e = one_block(since, "boolean")
    check("gd since 0", put(e, 0, "good", True)["y"], ("good", False))
    check("gd since 1", put(e, 1, "good", False)["y"], ("good", False))
    o = put(e, 7)  # five passed over
    check("gd since 7", o["y"], ("good", True))
    counts("gd since 7", o, elapsed=8, doubtful=5, gaps=1)
    # nobody knows: last true longer ago than `time`, until the clock is
    # next set; the counts start at the gap's tick. Nothing stands at that
    # tick, which assume_false takes as not true, uncertain.
    e = one_block(since, "boolean")
    check("gd since unknown 0", put(e, 0, "good", True)["y"], ("good", False))
    e.rebase()
    o = put(e, 0)
    check("gd since unknown 1", o["y"], ("uncertain", True))
    counts("gd since unknown 1", o, elapsed=1, doubtful=1, gaps=1)
    o = put(e, 1, "good", False)
    check("gd since unknown 2", o["y"], ("good", True))
    counts("gd since unknown 2", o, elapsed=2, doubtful=1, gaps=1)
    o = put(e, 2, "good", True)
    check("gd since unknown 3", o["y"], ("good", False))
    counts("gd since unknown 3", o, elapsed=1, doubtful=0, gaps=0)

    # --- integrate: what a gap adds to `missed` counts against max_missed
    e = one_block({"type": "integrate", "in": {"x": 1}, "settings": {"max_missed": "2s"}})
    check("gd integ 0", put(e, 0)["y"], ("good", 1.0))
    o = put(e, 3)
    check("gd integ 3", o["y"], ("good", 2.0))
    counts("gd integ 3", o, missed=2, elapsed=4, gaps=1)
    o = put(e, 7)
    check("gd integ 7", o["y"], ("bad", None))
    counts("gd integ 7", o, missed=5, elapsed=8, gaps=2)

    # --- a model: steps not taken, and riding through a gap
    # d temp/dt = (10 - (temp - 20)) / 10: towards 30, by s per step,
    # exactly: s is exp(-0.1)
    s = math.exp(-0.1)
    t1 = 30 - 10 * s
    t2 = 30 - 10 * s * s
    mass = {
        "type": "thermal_mass",
        "in": {"power": "x", "ambient": 20},
        "settings": {"thermal_mass": 10, "heat_transfer": 1, "initial": 20, "ride_through": "3s"},
    }

    def stepped():
        e = one_block(mass)
        check("gd model 0", put(e, 0, "good", 10.0)["temp"], ("good", 20.0))
        return e

    # ticks 1 and 2 are passed over. For each, in order, it steps on the
    # held 10: both are within ride_through (round three). At tick 3 the
    # power is unusable for the third tick in a row: held again. At tick
    # 4, the fourth, it does not step.
    e = stepped()
    o = put(e, 3, "bad")
    check("gd model 3", o["temp"], ("uncertain", 30 - 10 * s**3))
    counts("gd model 3", o, elapsed=4, doubtful=2, gaps=1)
    o = put(e, 4)
    check("gd model 4", o["temp"], ("uncertain", 30 - 10 * s**4))
    counts("gd model 4", o, elapsed=5, doubtful=3, gaps=1)
    o = put(e, 5)
    check("gd model 5", o["temp"], ("uncertain", 30 - 10 * s**4))
    counts("gd model 5", o, elapsed=6, doubtful=4, gaps=1)
    # five passed over: it steps for ticks 1, 2 and 3, and takes no step
    # from tick 4, the first that is past ride_through
    e = stepped()
    o = put(e, 6, "bad")
    check("gd model past", o["temp"], ("uncertain", 30 - 10 * s**4))
    counts("gd model past", o, elapsed=7, doubtful=5, gaps=1)
    check("gd model past, next", put(e, 7)["temp"], ("uncertain", 30 - 10 * s**4))
    # usable again at the tick that runs: it steps on that
    e = stepped()
    put(e, 6, "good", 10.0)
    check("gd model past, usable", put(e, 7)["temp"], ("uncertain", 30 - 10 * s**5))
    # with no ride_through, no step is taken for a tick passed over
    e = one_block(dict(mass, settings=dict(mass["settings"], ride_through="0s")))
    put(e, 0, "good", 10.0)
    o = put(e, 3, "good", 10.0)
    check("gd model no ride", o["temp"], ("uncertain", t1))
    counts("gd model no ride", o, elapsed=4, doubtful=2, gaps=1)
    # a rebase of known length: away 2 s is ticks 1 and 2, one passed
    # over, with a held step. Nothing stands at tick 2: held again.
    e = stepped()
    e.rebase(2 * S)
    o = put(e, 0)
    check("gd model known info", e.info, info(True, 2, 0, skipped=1))
    check("gd model known 2", o["temp"], ("uncertain", t2))
    counts("gd model known 2", o, elapsed=3, doubtful=1, gaps=1)
    o = put(e, 1)
    check("gd model known 3", o["temp"], ("uncertain", 30 - 10 * s**3))
    counts("gd model known 3", o, elapsed=4, doubtful=2, gaps=1)
    # nobody knows: it does not ride through, until the input is usable
    e = stepped()
    e.rebase()
    o = put(e, 0)
    check("gd model unknown 1", o["temp"], ("uncertain", t1))
    counts("gd model unknown 1", o, elapsed=2, doubtful=0, gaps=1)
    o = put(e, 1)
    check("gd model unknown 2", o["temp"], ("uncertain", t1))
    counts("gd model unknown 2", o, elapsed=3, doubtful=1, gaps=1)
    o = put(e, 2, "good", 10.0)
    check("gd model unknown 3", o["temp"], ("uncertain", t1))
    o = put(e, 3, "bad")  # usable again at tick 3, so it rides through now
    check("gd model unknown 4", o["temp"], ("uncertain", t2))
    check("gd model unknown 5", put(e, 4)["temp"], ("uncertain", 30 - 10 * s**3))


def test_gap_round_two():
    """Amendment 3, round two: a gap that passed over none; a total after a
    gap of no known length."""
    # no model has a doubt where none was passed over
    mass = {
        "type": "thermal_mass",
        "in": {"power": 0, "ambient": 20},
        "settings": {"thermal_mass": 10, "heat_transfer": 1, "initial": 20, "settle": "2s"},
    }
    e = one_block(mass)
    put(e, 0)
    put(e, 1)
    e.rebase(1 * S)  # one tick would have been due: it runs, none passed over
    o = put(e, 0)
    check("g2 model none info", e.info, info(True, 2, 0))
    check("g2 model none", o["temp"], ("good", 20.0))
    counts("g2 model none", o, elapsed=3, doubtful=0, gaps=1)
    # with one passed over it has: a step not taken
    e = one_block(mass)
    put(e, 0)
    put(e, 1)
    e.rebase(2 * S)
    o = put(e, 0)
    check("g2 model one info", e.info, info(True, 3, 0, skipped=1))
    check("g2 model one", o["temp"], ("uncertain", 20.0))
    counts("g2 model one", o, elapsed=4, doubtful=1, gaps=1)
    # nor has a loop
    for away, want in ((499999999, "good"), (1 * S, "good"), (2 * S, "uncertain")):
        e = Engine(two_masses())
        e.write("p", "good", 0.0, 0)
        e.tick(0)
        e.tick(1 * S)
        e.rebase(away)
        e.write("p", "good", 0.0, 0)
        o = e.tick(0)[1]
        check("g2 loop %d a" % away, o["a"], (want, 20.0))
        check("g2 loop %d b" % away, o["b"], (want, 20.0))

    # an estimator: its variance grows by p0 at a gap, whatever n is. q is
    # 1 a second.
    est = {
        "type": "estimator",
        "in": {"u": 0, "z": "x"},
        "settings": {
            "model": {"type": "state_space", "A": [[1]], "B": [0], "C": [1]},
            "q": {"x0": 1},
            "p0": {"x0": 4},
            "measure": {"z": {"of": "y", "r": 1}},
            "consistency": "none",
        },
    }
    # amendment 5, rule 7.9.9: at a rebase the variance grows by p0,
    # whatever its length; told n, it predicts n times more first (1 each);
    # then the tick's own predict. With none passed over the tick is good.
    for label, away, variance, state in (
        ("none", (0,), 4 + 4 + 1.0, "good"),
        ("one", (2 * S,), 4 + 1 + 4 + 1.0, "uncertain"),
        ("unknown", (), 4 + 4 + 1.0, "uncertain"),
    ):
        e = one_block(est)
        check("g2 est %s 0" % label, put(e, 0)["sigma_x0"], ("good", 2.0))
        e.rebase(*away)
        check("g2 est %s" % label, put(e, 0)["sigma_x0"], (state, math.sqrt(variance)))

    # a total with max_missed is bad after a gap of no known length, until
    # a reset; nothing is added to `missed`
    integ = {"type": "integrate", "in": {"x": 1, "reset": "x"}, "settings": {"max_missed": "2s"}}
    e = one_block(integ, "boolean")
    check("g2 integ 0", put(e, 0, "good", False)["y"], ("good", 1.0))
    e.rebase()
    o = put(e, 0, "good", False)
    check("g2 integ unknown", o["y"], ("bad", None))
    counts("g2 integ unknown", o, missed=0, elapsed=2, gaps=1)
    check("g2 integ unknown, next", put(e, 1)["y"], ("bad", None))
    o = put(e, 2, "good", True)
    check("g2 integ reset", o["y"], ("good", 1.0))
    counts("g2 integ reset", o, missed=0, elapsed=1, gaps=0)
    # a reset at the gap's own tick
    e.rebase()
    o = put(e, 0, "good", True)
    check("g2 integ reset at the gap", o["y"], ("good", 1.0))
    counts("g2 integ reset at the gap", o, missed=0, elapsed=1, gaps=1)
    # a length, however short, is not "nobody knows"
    e = one_block(integ, "boolean")
    put(e, 0, "good", False)
    e.rebase(0)
    o = put(e, 0, "good", False)
    check("g2 integ zero", o["y"], ("good", 2.0))
    counts("g2 integ zero", o, missed=0, elapsed=2, gaps=1)
    # with no max_missed it is good after a gap of no known length
    e = one_block({"type": "integrate", "in": {"x": 1}})
    put(e, 0)
    e.rebase()
    check("g2 integ no max", put(e, 0)["y"], ("good", 2.0))


def test_gap_round_three():
    """Amendment 3, round three: a window with only_new keeps no sample
    from before a rebase, whatever length the host gave (rule 8.5)."""
    win = {"type": "window", "in": {"x": "x"}, "settings": {"window": "4s", "min_good": 0.25, "only_new": True}}

    def filled():
        e = one_block(win)
        for k in range(4):
            o = put(e, k, "good", k + 1.0)
        check("g3 window filled", o["count"], ("good", 4.0))
        return e

    # a stall is on one clock: one passed over, and the window is 3, 4, -, 7
    e = filled()
    o = put(e, 5, "good", 7.0)
    check("g3 window stall count", o["count"], ("good", 3.0))
    check("g3 window stall mean", o["mean"], ("good", 14.0 / 3))
    # a rebase, with a length, with a length of zero, or with none
    for label, away in (("two", (2 * S,)), ("zero", (0,)), ("unknown", ())):
        e = filled()
        e.rebase(*away)
        o = put(e, 0, "good", 7.0)
        check("g3 window %s count" % label, o["count"], ("good", 1.0))
        check("g3 window %s mean" % label, o["mean"], ("good", 7.0))
    # a window without only_new keeps what it holds through a rebase that
    # passed over none: 2, 3, 4, 7
    e = one_block({"type": "window", "in": {"x": "x"}, "settings": {"window": "4s", "min_good": 0.25}})
    for k in range(4):
        put(e, k, "good", k + 1.0)
    e.rebase(0)
    o = put(e, 0, "good", 7.0)
    check("g3 window plain count", o["count"], ("good", 4.0))
    check("g3 window plain mean", o["mean"], ("good", 4.0))


def model_run(block, period, ticks, x=None, in_type="number"):
    """One model block with every output published under its port's name;
    the input `x`, if given, is written `good` before tick 0 and stands.
    Gives the outputs of ticks 0 to ticks - 1; tick k is at k periods."""
    blk = dict(block, id="b")
    g = {"period": period, "inputs": {"x": {"type": in_type, "max_age": "none"}}, "blocks": [blk]}
    e = Engine(g)
    blk["out"] = {p: p for p in e._blocks["b"].out_ports}
    e = Engine(g)
    step = e._period_ns
    if x is not None:
        e.write("x", "good", x, 0)
    return [e.tick(k * step)[1] for k in range(ticks)]


def against(label, outs, period_s, **forms):
    """forms: for each port, the closed form as a function of time."""
    for port, f in forms.items():
        for k, o in enumerate(outs):
            check("%s %s %d" % (label, port, k), o[port], ("good", f(k * period_s)))


def test_models_closed_form():
    """Amendment 4, rule 7.8.7: a model is stepped exactly. With its inputs
    constant from tick 0, its state at tick k is the solution of its
    equation at k periods; each closed form here is worked out by hand."""
    exp, cos, sin, sqrt = math.exp, math.cos, math.sin, math.sqrt

    # thermal_mass: temp = amb + P/h + (T0 - amb - P/h) exp(-h t / c)
    blk = {
        "type": "thermal_mass",
        "in": {"power": "x", "ambient": 20},
        "settings": {"thermal_mass": 10, "heat_transfer": 2, "initial": 50},
    }
    against("cf thermal", model_run(blk, "1s", 6, 30.0), 1.0, temp=lambda t: 35 + 15 * exp(-0.2 * t))
    # a period of ten time constants, and of a hundredth of one
    against("cf thermal long", model_run(blk, "50s", 3, 30.0), 50.0, temp=lambda t: 35 + 15 * exp(-0.2 * t))
    against("cf thermal short", model_run(blk, "50ms", 4, 30.0), 0.05, temp=lambda t: 35 + 15 * exp(-0.2 * t))

    # first_order_process: y = g u + (y0 - g u) exp(-t / tau)
    blk = {"type": "first_order_process", "in": {"u": "x"}, "settings": {"tau": "2s", "gain": 3, "initial": 1}}
    against("cf first", model_run(blk, "500ms", 6, 2.0), 0.5, y=lambda t: 6 - 5 * exp(-t / 2))
    # the answer does not depend on the period: 1 s, in one step and in four
    one = model_run(blk, "1s", 2, 2.0)[1]["y"]
    four = model_run(blk, "250ms", 5, 2.0)[4]["y"]
    check("cf first period", one, four)
    blk = {"type": "first_order_process", "in": {"u": "x"}, "settings": {"tau": "2s"}}
    against("cf first defaults", model_run(blk, "1s", 4, 2.0), 1.0, y=lambda t: 2 - 2 * exp(-t / 2))

    # second_order_process, underdamped, from rest, u = 1, gain 5:
    #   y = g (1 - exp(-z w t) (cos wd t + z / sqrt(1 - z^2) sin wd t))
    #   rate = g w / sqrt(1 - z^2) exp(-z w t) sin wd t,  wd = w sqrt(1 - z^2)
    w, z, g = 2.0, 0.25, 5.0
    r = sqrt(1 - z * z)
    wd = w * r
    blk = {"type": "second_order_process", "in": {"u": "x"}, "settings": {"omega_n": w, "zeta": z, "gain": g}}
    against(
        "cf second under",
        model_run(blk, "300ms", 8, 1.0),
        0.3,
        y=lambda t: g * (1 - exp(-z * w * t) * (cos(wd * t) + z / r * sin(wd * t))),
        rate=lambda t: g * w / r * exp(-z * w * t) * sin(wd * t),
    )
    # critically damped: y = 1 - exp(-w t) (1 + w t), rate = w^2 t exp(-w t)
    blk = {"type": "second_order_process", "in": {"u": "x"}, "settings": {"omega_n": w, "zeta": 1}}
    against(
        "cf second critical",
        model_run(blk, "300ms", 8, 1.0),
        0.3,
        y=lambda t: 1 - exp(-w * t) * (1 + w * t),
        rate=lambda t: w * w * t * exp(-w * t),
    )
    # overdamped, w = 1, z = 1.25: roots -0.5 and -2, so
    #   y = 1 - (4 exp(-t / 2) - exp(-2 t)) / 3,  rate = 2 (exp(-t / 2) - exp(-2 t)) / 3
    blk = {"type": "second_order_process", "in": {"u": "x"}, "settings": {"omega_n": 1, "zeta": 1.25}}
    against(
        "cf second over",
        model_run(blk, "700ms", 6, 1.0),
        0.7,
        y=lambda t: 1 - (4 * exp(-t / 2) - exp(-2 * t)) / 3,
        rate=lambda t: 2 * (exp(-t / 2) - exp(-2 * t)) / 3,
    )
    # undamped, no input, from y = 3 with rate 4: y = 3 cos 2t + 2 sin 2t
    blk = {
        "type": "second_order_process",
        "in": {"u": 0},
        "settings": {"omega_n": 2, "zeta": 0, "initial": 3, "initial_rate": 4},
    }
    against(
        "cf second undamped",
        model_run(blk, "400ms", 8),
        0.4,
        y=lambda t: 3 * cos(2 * t) + 2 * sin(2 * t),
        rate=lambda t: -6 * sin(2 * t) + 4 * cos(2 * t),
    )

    # mass_spring_damper. No spring and no damper, force 6 on a mass of 2:
    #   velocity = 3 t, position = 1.5 t^2 (A is not invertible)
    blk = {"type": "mass_spring_damper", "in": {"force": "x"}, "settings": {"mass": 2, "damping": 0, "stiffness": 0}}
    against(
        "cf msd free",
        model_run(blk, "500ms", 6, 6.0),
        0.5,
        position=lambda t: 1.5 * t * t,
        velocity=lambda t: 3 * t,
    )
    # a spring and no damper, mass 2, stiffness 8 (2 rad/s), force 4 from rest:
    #   position = (1 - cos 2t) / 2, velocity = sin 2t
    blk = {"type": "mass_spring_damper", "in": {"force": "x"}, "settings": {"mass": 2, "damping": 0, "stiffness": 8}}
    against(
        "cf msd spring",
        model_run(blk, "250ms", 10, 4.0),
        0.25,
        position=lambda t: (1 - cos(2 * t)) / 2,
        velocity=lambda t: sin(2 * t),
    )
    # a damper and no spring, mass 2, damping 4, force 8:
    #   velocity = 2 (1 - exp(-2t)), position = 2 t - (1 - exp(-2t))
    blk = {"type": "mass_spring_damper", "in": {"force": "x"}, "settings": {"mass": 2, "damping": 4, "stiffness": 0}}
    against(
        "cf msd damper",
        model_run(blk, "250ms", 8, 8.0),
        0.25,
        position=lambda t: 2 * t - (1 - exp(-2 * t)),
        velocity=lambda t: 2 * (1 - exp(-2 * t)),
    )
    # all three, underdamped, released from 1 at rest: m 1, c 2, k 5:
    #   roots -1 +- 2i: position = exp(-t) (cos 2t + sin 2t / 2),
    #   velocity = -2.5 exp(-t) sin 2t
    blk = {
        "type": "mass_spring_damper",
        "in": {"force": 0},
        "settings": {"mass": 1, "damping": 2, "stiffness": 5, "initial_position": 1},
    }
    against(
        "cf msd all",
        model_run(blk, "300ms", 8),
        0.3,
        position=lambda t: exp(-t) * (cos(2 * t) + sin(2 * t) / 2),
        velocity=lambda t: -2.5 * exp(-t) * sin(2 * t),
    )

    # thermal_rc2, both masses 10, both losses 1, coupling 3, no power,
    # ambient 20, from 50 and 30. With a = temp_a - 20 and b = temp_b - 20
    # the sum decays at 1/10 and the difference at (1 + 2*3)/10:
    #   a + b = 40 exp(-0.1 t), a - b = 20 exp(-0.7 t)
    rc2 = {
        "thermal_mass_a": 10,
        "thermal_mass_b": 10,
        "heat_transfer_a": 1,
        "heat_transfer_b": 1,
        "coupling": 3,
        "initial_a": 50,
        "initial_b": 30,
    }
    blk = {"type": "thermal_rc2", "in": {"power": 0, "ambient": 20}, "settings": rc2}
    against(
        "cf rc2",
        model_run(blk, "2s", 6),
        2.0,
        temp_a=lambda t: 20 + 20 * exp(-0.1 * t) + 10 * exp(-0.7 * t),
        temp_b=lambda t: 20 + 20 * exp(-0.1 * t) - 10 * exp(-0.7 * t),
    )
    # the text's case: a conductance of three times the loss, run at half
    # the time constant (5 s): the one block gives the true answer
    against(
        "cf rc2 half",
        model_run(blk, "5s", 5),
        5.0,
        temp_a=lambda t: 20 + 20 * exp(-0.1 * t) + 10 * exp(-0.7 * t),
        temp_b=lambda t: 20 + 20 * exp(-0.1 * t) - 10 * exp(-0.7 * t),
    )
    # with power 11 into the first, unequal masses and losses 1 and 2,
    # coupling 3: at rest, 3 (a - b) = 2 b and 11 = a + 2 b, so b = 3 and
    # a = 5 above ambient. One step of a day gets there.
    rc2b = dict(rc2, thermal_mass_b=40, heat_transfer_b=2)
    blk = {"type": "thermal_rc2", "in": {"power": "x", "ambient": 20}, "settings": rc2b}
    o = model_run(blk, "24h", 2, 11.0)[1]
    check("cf rc2 rest a", o["temp_a"], ("good", 25.0))
    check("cf rc2 rest b", o["temp_b"], ("good", 23.0))

    # dc_motor with no back emf: the current is a first-order lag of the
    # voltage (rate R/L = 4) and the speed a lag of the current (rate
    # b/J = 1):  i = (V/R)(1 - exp(-4t)),
    #   speed = (Kt V / (R b)) (1 - (4 exp(-t) - exp(-4t)) / 3)
    motor = {
        "resistance": 2,
        "inductance": 0.5,
        "back_emf": 0,
        "torque_constant": 3,
        "inertia": 2,
        "friction": 2,
    }
    blk = {"type": "dc_motor", "in": {"voltage": "x", "load_torque": 0}, "settings": motor}
    against(
        "cf motor",
        model_run(blk, "200ms", 8, 4.0),
        0.2,
        current=lambda t: 2 * (1 - exp(-4 * t)),
        torque=lambda t: 6 * (1 - exp(-4 * t)),
        speed=lambda t: 3 * (1 - (4 * exp(-t) - exp(-4 * t)) / 3),
    )
    # a load torque alone: speed = -(TL / b)(1 - exp(-b t / J))
    blk = {"type": "dc_motor", "in": {"voltage": 0, "load_torque": "x"}, "settings": motor}
    against(
        "cf motor load",
        model_run(blk, "500ms", 6, 5.0),
        0.5,
        speed=lambda t: -2.5 * (1 - exp(-t)),
        current=lambda t: 0.0,
    )
    # with back emf, at rest: V = R i + Ke w and Kt i = b w + TL. With
    # R 2, Ke 0.5, Kt 3, b 2, V 8, TL 1: i = 3, w = 4, torque = 9.
    blk = {
        "type": "dc_motor",
        "in": {"voltage": "x", "load_torque": 1},
        "settings": dict(motor, back_emf=0.5, initial_current=1, initial_speed=-2),
    }
    o = model_run(blk, "1h", 2, 8.0)
    check("cf motor initial speed", o[0]["speed"], ("good", -2.0))
    check("cf motor initial current", o[0]["current"], ("good", 1.0))
    check("cf motor initial torque", o[0]["torque"], ("good", 3.0))
    check("cf motor rest speed", o[1]["speed"], ("good", 4.0))
    check("cf motor rest current", o[1]["current"], ("good", 3.0))
    check("cf motor rest torque", o[1]["torque"], ("good", 9.0))

    # linear. Three integrators in a row, u = 6: x2 = 6t, x1 = 3t^2, x0 = t^3
    blk = {
        "type": "linear",
        "in": {"u": "x"},
        "settings": {
            "A": [[0, 1, 0], [0, 0, 1], [0, 0, 0]],
            "B": [[0], [0], [1]],
            "C": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        },  # noqa: E501
    }
    against(
        "cf linear chain",
        model_run(blk, "500ms", 6, 6.0),
        0.5,
        y0=lambda t: t**3,
        y1=lambda t: 3 * t * t,
        y2=lambda t: 6 * t,
    )
    # a turn that grows: A = [[a, -w], [w, a]] gives exp(a t) times a turn by w t
    blk = {
        "type": "linear",
        "in": {"u": 0},
        "settings": {
            "A": [[0.1, -2], [2, 0.1]],
            "B": [[0], [0]],
            "C": [[1, 0], [0, 1]],
            "initial": [1, 0],
            "outputs": ["c", "s"],
        },
    }
    against(
        "cf linear turn",
        model_run(blk, "700ms", 8),
        0.7,
        c=lambda t: exp(0.1 * t) * cos(2 * t),
        s=lambda t: exp(0.1 * t) * sin(2 * t),
    )
    # stiff: rates of a thousand and of a thousandth a second, period 10 s
    # (the first row, summed, times the period is 10,000: within the bound).
    #   x0' = -1e3 x0 + 1e3 u, x1' = x0 - 1e-3 x1, u = 1, from rest:
    #   x0 = 1 - exp(-1e3 t)
    #   x1 = 1e3 (1 - exp(-1e-3 t)) - (exp(-1e-3 t) - exp(-1e3 t)) / (1e3 - 1e-3)
    blk = {
        "type": "linear",
        "in": {"u": "x"},
        "settings": {"A": [[-1e3, 0], [1, -1e-3]], "B": [[1e3], [0]], "C": [[1, 0], [0, 1]]},
    }
    against(
        "cf linear stiff",
        model_run(blk, "10s", 5, 1.0),
        10.0,
        y0=lambda t: 1 - exp(-1e3 * t),
        y1=lambda t: 1e3 * (1 - exp(-1e-3 * t)) - (exp(-1e-3 * t) - exp(-1e3 * t)) / (1e3 - 1e-3),
    )
    # two inputs, two outputs and a D: an output that reads an input reads
    # it at the same tick. x' = -x + u0 + 2 u1; ya = x, yb = 3 x + 4 u1.
    #   with u0 = 1 (constant) and u1 = 2: x = 5 (1 - exp(-t))
    blk = {
        "type": "linear",
        "in": {"p": 1, "q": "x"},
        "settings": {
            "A": [[-1]],
            "B": [[1, 2]],
            "C": [[1], [3]],
            "D": [[0, 0], [0, 4]],
            "inputs": ["p", "q"],
            "states": ["level"],
            "outputs": ["ya", "yb"],
        },
    }
    against(
        "cf linear D",
        model_run(blk, "1s", 5, 2.0),
        1.0,
        ya=lambda t: 5 * (1 - exp(-t)),
        yb=lambda t: 15 * (1 - exp(-t)) + 8,
    )
    # a linear block is the named model it spells out
    blk = {
        "type": "linear",
        "in": {"u0": "x", "u1": 20},
        "settings": {"A": [[-0.2]], "B": [[0.1, 0.2]], "C": [[1]], "initial": [50]},
    }
    against("cf linear as thermal", model_run(blk, "1s", 6, 30.0), 1.0, y=lambda t: 35 + 15 * exp(-0.2 * t))

    # state_space is in discrete time: its A and B are the step itself,
    # at whatever period. x' = 0.5 x + u, u = 1: x = 2 (1 - 0.5^k)
    blk = {"type": "state_space", "in": {"u": "x"}, "settings": {"A": [[0.5]], "B": [1], "C": [1]}}
    for period in ("1s", "10ms", "1h"):
        outs = model_run(blk, period, 5, 1.0)
        for k, o in enumerate(outs):
            check("cf state_space %s %d" % (period, k), o["y"], ("good", 2 * (1 - 0.5**k)))


def test_models_settle_and_names():
    """Amendment 4: where `settle` comes from (rule 7.8.6), the names of a
    `linear` block, and what is refused."""

    def uncertain_ticks(block, period="1s", ticks=60):
        """The input is unusable at tick 1 and at no other: a step not
        taken, the doubt. How many ticks after it are uncertain."""
        blk = dict(block, id="b")
        g = {"period": period, "inputs": {"x": {"max_age": "none"}}, "blocks": [blk]}
        e = Engine(g)
        port = next(iter(e._blocks["b"].out_ports))
        blk["out"] = {port: "o"}
        e = Engine(g)
        step = e._period_ns
        states = []
        for k in range(ticks):
            if k < 3:
                e.write("x", "bad" if k == 1 else "good", None if k == 1 else 0.0, k * step)
            states.append(e.tick(k * step)[1]["o"][0])
        check("settle: good up to the doubt", states[:2], ["good", "good"])
        n = 0
        while 2 + n < ticks and states[2 + n] == "uncertain":
            n += 1
        check("settle: good after it", all(s == "good" for s in states[2 + n :]), True)
        return n

    # thermal_mass: one eigenvalue, -h/c = -0.1: three time constants are 30
    blk = {
        "type": "thermal_mass",
        "in": {"power": "x", "ambient": 20},
        "settings": {"thermal_mass": 10, "heat_transfer": 1, "initial": 20},
    }
    check("settle thermal", uncertain_ticks(blk), 30)
    check("settle thermal, 4 s", uncertain_ticks(blk, "4s"), 8)  # 30 s is 7.5 periods
    check("settle thermal given", uncertain_ticks(dict(blk, settings=dict(blk["settings"], settle="2s"))), 2)
    # first_order_process: tau 2.5 s: 7.5 s, rounded up
    blk = {"type": "first_order_process", "in": {"u": "x"}, "settings": {"tau": "2500ms"}}
    check("settle first", uncertain_ticks(blk), 8)
    # second_order_process, underdamped: the real part is -zeta omega_n = -0.5
    blk = {"type": "second_order_process", "in": {"u": "x"}, "settings": {"omega_n": 2, "zeta": 0.25}}
    check("settle second under", uncertain_ticks(blk), 6)
    # overdamped, omega_n 1, zeta 1.25: eigenvalues -0.5 and -2; the slowest
    blk = {"type": "second_order_process", "in": {"u": "x"}, "settings": {"omega_n": 1, "zeta": 1.25}}
    check("settle second over", uncertain_ticks(blk), 6)
    # critically damped: both are -2: 1.5 s
    blk = {"type": "second_order_process", "in": {"u": "x"}, "settings": {"omega_n": 2, "zeta": 1}}
    check("settle second critical", uncertain_ticks(blk), 2)
    # no damping: a state that does not decay, so no settle: good
    blk = {"type": "second_order_process", "in": {"u": "x"}, "settings": {"omega_n": 2, "zeta": 0}}
    check("settle second undamped", uncertain_ticks(blk), 0)
    # mass_spring_damper: m 1, c 2, k 5: -1 +- 2i: 3 s
    msd = {"type": "mass_spring_damper", "in": {"force": "x"}, "settings": {"mass": 1, "damping": 2, "stiffness": 5}}
    check("settle msd", uncertain_ticks(msd), 3)
    # no spring: an eigenvalue of zero (the position stays where it is)
    check("settle msd no spring", uncertain_ticks(dict(msd, settings={"mass": 1, "damping": 2, "stiffness": 0})), 0)
    check("settle msd no damper", uncertain_ticks(dict(msd, settings={"mass": 1, "damping": 0, "stiffness": 5})), 0)
    # thermal_rc2, masses 10, losses 1, coupling 3: rates 0.1 and 0.7
    rc2 = {
        "thermal_mass_a": 10,
        "thermal_mass_b": 10,
        "heat_transfer_a": 1,
        "heat_transfer_b": 1,
        "coupling": 3,
        "initial_a": 20,
        "initial_b": 20,
    }
    blk = {"type": "thermal_rc2", "in": {"power": "x", "ambient": 20}, "settings": rc2}
    check("settle rc2", uncertain_ticks(blk), 30)
    # with no loss at all the heat stays in: no settle
    blk = dict(blk, settings=dict(rc2, heat_transfer_a=0, heat_transfer_b=0))
    check("settle rc2 no loss", uncertain_ticks(blk), 0)
    # round three: no coupling is allowed. Two masses apart, with rates
    # 0.1 and 0.2: h is -0.15 and d 0.02, h squared is more than d, and
    # the largest real part is d / (h - sqrt(h^2 - d)) = 0.02 / -0.2
    blk = dict(blk, settings=dict(rc2, coupling=0, heat_transfer_b=2))
    check("settle rc2 apart", uncertain_ticks(blk), 30)
    # the second loses nothing: d is zero, and so is the largest real part
    blk = dict(blk, settings=dict(rc2, coupling=0, heat_transfer_b=0))
    check("settle rc2 apart, one kept in", uncertain_ticks(blk), 0)
    # two the same, 0.3 each: h squared is no more than d, and it is h
    blk = dict(blk, settings=dict(rc2, coupling=0, heat_transfer_a=3, heat_transfer_b=3))
    check("settle rc2 apart, alike", uncertain_ticks(blk), 10)
    blk = {"type": "thermal_rc2", "in": {"power": "x", "ambient": 20}, "settings": rc2}
    # round four: the determinant comes from the settings and not from
    # A's entries (rule 7.8.6). Both masses 1, coupling 1, losses of 1e-9:
    # the two cool together at 1e-9 a second, so the constant is 1e9 s and
    # settle three of them. Worked from A's entries, d loses that rate in
    # a subtraction and the constant comes out near 0.99999992e9.
    slow = dict(rc2, thermal_mass_a=1, thermal_mass_b=1, heat_transfer_a=1e-9, heat_transfer_b=1e-9, coupling=1)
    slow = {"id": "b", "type": "thermal_rc2", "in": {"power": 0, "ambient": 0}, "settings": slow}
    e = Engine({"period": "1s", "blocks": [slow]})
    check("settle rc2 slow tau", close(e._blocks["b"].model.tau, 1e9), True)
    check("settle rc2 slow ticks", abs(e._blocks["b"].settle - 3 * 10**9) <= 3, True)
    # dc_motor with no back emf: rates R/L = 4 and b/J = 1: 3 s
    motor = {"resistance": 2, "inductance": 0.5, "back_emf": 0, "torque_constant": 3, "inertia": 2, "friction": 2}
    blk = {"type": "dc_motor", "in": {"voltage": "x", "load_torque": 0}, "settings": motor}
    check("settle motor", uncertain_ticks(blk), 3)
    # with back emf 0.5: h is -2.5 and d (2*2 + 0.5*3) / (0.5*2) = 5.5; the
    # largest real part is 5.5 / (-2.5 - sqrt(0.75)), a constant of 0.612 s
    check("settle motor back emf", uncertain_ticks(dict(blk, settings=dict(motor, back_emf=0.5))), 2)
    # a spring and a heavy damper on a mass of 2: A is [[0, 1], [-4, -5]],
    # d is stiffness / mass = 4, eigenvalues -1 and -4: 3 s
    over = {"type": "mass_spring_damper", "in": {"force": "x"}, "settings": {"mass": 2, "damping": 10, "stiffness": 8}}
    check("settle msd over", uncertain_ticks(over), 3)
    # a motor with no resistance and no friction: d is back_emf times
    # torque_constant over inductance times inertia, h is zero, and the
    # eigenvalues are a pair on the imaginary axis. No state decays, so no
    # settle. (Round five: the two constants are not negative, so no named
    # model has an eigenvalue with a real part above zero.)
    blk = dict(blk, settings=dict(motor, resistance=0, friction=0, back_emf=1, torque_constant=1))
    check("settle motor lossless", uncertain_ticks(blk, ticks=12), 0)
    # nothing at all: d is zero
    blk = dict(blk, settings=dict(motor, resistance=0, friction=0, back_emf=0, torque_constant=0))
    check("settle motor idle", uncertain_ticks(blk, ticks=12), 0)
    # linear and state_space are given none, whatever their A
    blk = {"type": "linear", "in": {"u": "x"}, "settings": {"A": [[-0.1]], "B": [[0.1]], "C": [[1]]}}
    check("settle linear", uncertain_ticks(blk), 0)
    check("settle linear given", uncertain_ticks(dict(blk, settings=dict(blk["settings"], settle="4s"))), 4)
    blk = {"type": "state_space", "in": {"u": "x"}, "settings": {"A": [[0.5]], "B": [1], "C": [1]}}
    check("settle state_space", uncertain_ticks(blk), 0)

    # the names of a linear block
    def lin(**settings):
        st = {"A": [[0, 1], [0, 0]], "B": [[0, 0], [1, 1]], "C": [[1, 0], [0, 1]]}
        st.update(settings)
        st = {k: v for k, v in st.items() if v is not None}
        ins = {name: 0 for name in st.get("inputs", ["u0", "u1"])}
        return {"period": "1s", "blocks": [{"id": "b", "type": "linear", "in": ins, "settings": st}]}

    e = Engine(lin())
    check("lin default inputs", sorted(e._blocks["b"].in_ports), ["u0", "u1"])
    check("lin default outputs", sorted(e._blocks["b"].out_ports), ["doubtful", "elapsed", "gaps", "y0", "y1"])
    check("lin default states", list(e._blocks["b"].model.states), ["x0", "x1"])
    e = Engine(
        {
            "period": "1s",
            "blocks": [{"id": "b", "type": "linear", "in": {"u": 0}, "settings": {"A": [[0]], "B": [[1]], "C": [[1]]}}],
        }
    )  # noqa: E501
    check("lin single input", sorted(e._blocks["b"].in_ports), ["u"])
    check("lin single output", sorted(e._blocks["b"].out_ports), ["doubtful", "elapsed", "gaps", "y"])
    check("lin single state", list(e._blocks["b"].model.states), ["x0"])
    Engine(lin(inputs=["a", "b"], states=["p", "v"], outputs=["pos", "vel"]))
    Engine(lin(outputs=["u0", "x0"]))  # an output may be named as an input or a state is
    refused("lin names repeated", lin(outputs=["pos", "pos"]))
    refused("lin inputs repeated", lin(inputs=["a", "a"]))
    refused("lin states repeated", lin(states=["a", "a"]))
    refused("lin output named as a model output", lin(outputs=["pos", "gaps"]))
    refused("lin too few names", lin(outputs=["pos"]))
    refused("lin a name that is not text", lin(states=["p", 2]))
    refused("lin A not square", lin(A=[[0, 1], [0, 0], [0, 0]]))
    refused("lin A ragged", lin(A=[[0, 1], [0]]))
    refused("lin B rows", lin(B=[[0, 0]]))
    refused("lin B ragged", lin(B=[[0, 0], [1]]))
    refused("lin C width", lin(C=[[1, 0, 0]]))
    refused("lin D size", lin(D=[[0, 0]]))
    refused("lin D width", lin(D=[[0], [0]]))
    refused("lin initial size", lin(initial=[0]))
    refused("lin no A", lin(A=None))
    refused("lin no B", lin(B=None))
    refused("lin no C", lin(C=None))
    refused("lin not finite", lin(A=[[0, float("inf")], [0, 0]]))
    refused("lin substeps", lin(substeps=1))
    # round two: at least one state, one input and one output
    refused("lin no input", lin(B=[[], []], inputs=[]))
    refused("lin no output", lin(C=[]))
    refused("lin no state", lin(A=[], B=[], C=[[]]))
    # the three lists do not have to differ from each other
    Engine(lin(inputs=["a", "b"], states=["a", "b"], outputs=["a", "b"]))

    # round two, rule 7.8.7: a model that grows so fast that Ad or Bd is
    # not finite at the graph's period is refused. exp(5 * 200) is not a
    # double; exp(5 * 100) is, about 1.4e217.
    def grows(period, a=5):
        blk = {"id": "b", "type": "linear", "in": {"u": "x"}, "settings": {"A": [[a]], "B": [[1]], "C": [[1]]}}
        blk["out"] = {"y": "y"}
        return {"period": period, "inputs": {"x": {"max_age": "none"}}, "blocks": [blk]}

    refused("grows: Ad not finite", grows("200s"))
    e = Engine(grows("100s"))
    e.write("x", "good", 0.0, 0)
    check("grows 0", e.tick(0)[1]["y"], ("good", 0.0))
    check("grows 1", e.tick(100 * S)[1]["y"], ("good", 0.0))
    # with u = 1: x = (exp(5 t) - 1) / 5
    e = Engine(grows("100s"))
    e.write("x", "good", 1.0, 0)
    e.tick(0)
    check("grows u", e.tick(100 * S)[1]["y"], ("good", (math.exp(500.0) - 1) / 5))
    # Bd alone: exp(5 * 141) is about 1.5e306, a double, and with a B of
    # 1e10 the integral, a fifth of that times B, is not
    g = grows("141s")
    Engine(g)
    g["blocks"][0]["settings"]["B"] = [[1e10]]
    refused("grows: Bd not finite", g)
    # (round five: no named model can grow, now that a dc_motor's
    # constants are not negative; only `linear` can be refused for this)
    # and the model of an estimator
    est = {
        "id": "b",
        "type": "estimator",
        "in": {"u": 0, "z": "zz"},
        "settings": {
            "model": {"type": "linear", "A": [[5]], "B": [[1]], "C": [[1]]},
            "q": {"x0": 1},
            "p0": {"x0": 1},
            "measure": {"z": {"of": "y", "r": 1}},
            "consistency": "none",
        },
    }
    Engine({"period": "50s", "inputs": {"zz": {"max_age": "none"}}, "blocks": [est]})
    refused("grows: an estimator's model", {"period": "200s", "inputs": {"zz": {"max_age": "none"}}, "blocks": [est]})
    # its process noise grows as the square: (exp(10 T) - 1) / 10 is more
    # than a double holds at 100 s, where Ad, exp(500), is not
    refused(
        "grows: an estimator's process noise",
        {"period": "100s", "inputs": {"zz": {"max_age": "none"}}, "blocks": [est]},
    )
    # round three: the bound. The largest sum of the absolute values along
    # a row of A, times the period, may be 100,000 at most. With A of -5:
    # 20,000 s is 100,000 exactly, and is accepted; a decay of exp(-1e5) is
    # zero, and it rests where its input puts it
    e = Engine(grows("20000s", a=-5))
    e.write("x", "good", 10.0, 0)
    e.tick(0)
    check("bound: at it", e.tick(20000 * S)[1]["y"], ("good", 2.0))
    # a millisecond more is past it (a nanosecond more is within rounding)
    refused("bound: a millisecond past", grows("20000001ms", a=-5))
    refused("bound: far past", grows("1000000s", a=-5))
    # round four: the sum is in double arithmetic, and a graph within
    # rounding of the bound may be taken either way: the double nearest
    # 100,000 / 3, at 3 s, is 7e-12 past it exactly and at it in doubles.
    # Either answer is right; it must not fail some other way.
    try:
        Engine(grows("3s", a=-33333.333333333336))
    except CompileError:
        pass
    Engine(grows("3s", a=-33333.33333333333))  # the double below it

    # it is the sum of a row, not its largest entry or the eigenvalue: a
    # row of -3 and 2 counts as 5
    def two(period, a01):
        st = {"A": [[-3, a01], [0, -1]], "B": [[0], [1]], "C": [[1, 0]]}
        return {"period": period, "blocks": [{"id": "b", "type": "linear", "in": {"u": 0}, "settings": st}]}

    Engine(two("20000s", 2))
    refused("bound: the sum of a row", two("20001s", 2))
    Engine(two("20001s", -1.99))  # 4.99 times 20,001 is 99,804.99
    refused("bound: absolute values", two("20001s", -2))
    # B does not count, and nor does a state_space block
    blk = {"id": "b", "type": "linear", "in": {"u": 0}, "settings": {"A": [[-1]], "B": [[1e9]], "C": [[1]]}}
    Engine({"period": "100000s", "blocks": [blk]})
    blk = {"id": "b", "type": "state_space", "in": {"u": 0}, "settings": {"A": [[1e9]], "B": [1], "C": [1]}}
    Engine({"period": "100000s", "blocks": [blk]})

    # a named model: thermal_mass with h / c of 1000 a second, at 100 s and
    # at one nanosecond more
    def fast(period):
        st = {"thermal_mass": 1, "heat_transfer": 1000, "initial": 0}
        blk = {"id": "b", "type": "thermal_mass", "in": {"power": 0, "ambient": 0}, "settings": st}
        return {"period": period, "blocks": [blk]}

    Engine(fast("100s"))
    refused("bound: a named model", fast("100000000001ns"))
    # and an estimator's model
    est["settings"]["model"]["A"] = [[-5]]
    Engine({"period": "20000s", "inputs": {"zz": {"max_age": "none"}}, "blocks": [est]})
    refused("bound: an estimator's model", {"period": "20001s", "inputs": {"zz": {"max_age": "none"}}, "blocks": [est]})
    # the bound is tried before the size of the step: a model that is both
    # too fast and growing is refused either way
    refused("bound: and grows", grows("1000000s", a=5))
    # an input is direct where its column of D is not all zero
    e = Engine(lin(D=[[0, 0], [0, 2]]))
    check("lin direct", {p: v[2] for p, v in e._blocks["b"].in_ports.items()}, {"u0": False, "u1": True})

    # ranges of the named models
    def named(type_, ins, **settings):
        return {"period": "1s", "blocks": [{"id": "b", "type": type_, "in": ins, "settings": settings}]}

    tm = {"power": 0, "ambient": 0}
    Engine(named("thermal_mass", tm, thermal_mass=1, heat_transfer=1, initial=0))
    refused("tm no initial", named("thermal_mass", tm, thermal_mass=1, heat_transfer=1))
    refused("tm no loss", named("thermal_mass", tm, thermal_mass=1, heat_transfer=0, initial=0))
    refused("tm no mass", named("thermal_mass", tm, thermal_mass=0, heat_transfer=1, initial=0))
    ok = dict(
        thermal_mass_a=1, thermal_mass_b=1, heat_transfer_a=0, heat_transfer_b=0, coupling=1, initial_a=0, initial_b=0
    )  # noqa: E501
    Engine(named("thermal_rc2", tm, **ok))
    Engine(named("thermal_rc2", tm, **dict(ok, coupling=0)))  # round three: not negative
    refused("rc2 coupling below zero", named("thermal_rc2", tm, **dict(ok, coupling=-1)))
    refused("rc2 loss below zero", named("thermal_rc2", tm, **dict(ok, heat_transfer_b=-1)))
    refused("rc2 no mass", named("thermal_rc2", tm, **dict(ok, thermal_mass_b=0)))
    refused("rc2 no initial", named("thermal_rc2", tm, **{k: v for k, v in ok.items() if k != "initial_b"}))
    Engine(named("first_order_process", {"u": 0}, tau="1s", gain=-2))
    refused("fop tau a bare number", named("first_order_process", {"u": 0}, tau=1))
    refused("fop tau zero", named("first_order_process", {"u": 0}, tau="0s"))
    refused("fop no tau", named("first_order_process", {"u": 0}))
    Engine(named("second_order_process", {"u": 0}, omega_n=1, zeta=0))
    refused("sop zeta below zero", named("second_order_process", {"u": 0}, omega_n=1, zeta=-0.1))
    refused("sop omega zero", named("second_order_process", {"u": 0}, omega_n=0, zeta=1))
    Engine(named("mass_spring_damper", {"force": 0}, mass=1, damping=0, stiffness=0))
    refused("msd no mass", named("mass_spring_damper", {"force": 0}, mass=0, damping=0, stiffness=0))
    refused("msd damping below zero", named("mass_spring_damper", {"force": 0}, mass=1, damping=-1, stiffness=0))
    mi = {"voltage": 0, "load_torque": 0}
    mok = dict(resistance=0, inductance=1, back_emf=0, torque_constant=0, inertia=1, friction=0)
    Engine(named("dc_motor", mi, **mok))
    # round five: back_emf and torque_constant are not negative, so that
    # nothing in the determinant is subtracted
    refused("motor back_emf below zero", named("dc_motor", mi, **dict(mok, back_emf=-0.03)))
    refused("motor torque_constant below zero", named("dc_motor", mi, **dict(mok, torque_constant=-1)))
    refused("motor both below zero", named("dc_motor", mi, **dict(mok, back_emf=-1, torque_constant=-1)))
    Engine(named("dc_motor", mi, **dict(mok, back_emf=0.03, torque_constant=1)))
    refused("motor no inductance", named("dc_motor", mi, **dict(mok, inductance=0)))
    refused("motor no inertia", named("dc_motor", mi, **dict(mok, inertia=0)))
    refused("motor resistance below zero", named("dc_motor", mi, **dict(mok, resistance=-1)))
    refused("motor no back_emf", named("dc_motor", mi, **{k: v for k, v in mok.items() if k != "back_emf"}))
    refused("motor one input", named("dc_motor", {"voltage": 0}, **mok))

    # an estimator: F is the model's Ad. thermal_mass, c 10, h 1: Ad is
    # exp(-0.1). p0 4, q 1 a second, no measurement: the process noise
    # over a step is N = (1 - exp(-0.2)) / 0.2 (amendment 5), and after one
    # predict the variance is 4 exp(-0.2) + N. With power 30 and ambient 20
    # it rests at 50, and from 80 the state is 50 + 30 exp(-0.1 k) at tick k.
    est = {
        "id": "est",
        "type": "estimator",
        "in": {"power": 30, "ambient": 20, "z": "z"},
        "settings": {
            "model": {"type": "thermal_mass", "thermal_mass": 10, "heat_transfer": 1, "initial": 80},
            "q": {"temp": 1},
            "p0": {"temp": 4},
            "measure": {"z": {"of": "temp", "r": 1}},
            "consistency": "none",
        },
        "out": {"temp": "temp", "sigma_temp": "sigma"},
    }
    g = {"period": "1s", "inputs": {"z": {"max_age": "none"}}, "blocks": [est]}
    e = Engine(g)
    o = e.tick(0)[1]
    check("est model temp 0", o["temp"], ("good", 80.0))
    check("est model sigma 0", o["sigma"], ("good", 2.0))
    o = e.tick(1 * S)[1]
    check("est model temp 1", o["temp"], ("good", 50 + 30 * math.exp(-0.1)))
    noise = (1 - math.exp(-0.2)) / 0.2
    check("est model sigma 1", o["sigma"], ("good", math.sqrt(4 * math.exp(-0.2) + noise)))
    o = e.tick(2 * S)[1]
    check("est model temp 2", o["temp"], ("good", 50 + 30 * math.exp(-0.2)))
    check("est model sigma 2", o["sigma"], ("good", math.sqrt((4 * math.exp(-0.2) + noise) * math.exp(-0.2) + noise)))
    est["settings"]["substeps"] = 1
    refused("est substeps is gone", g)


def test_models_large_b():
    """Amendment 4, round six: the step does not depend on the size of B.
    Bd is the integral of exp(A.s) over the period, times B."""
    exp, cos, sin = math.exp, math.cos, math.sin
    for b in (1.0, 1e9, 1e80, 1e120, 1e300, 1e-200):
        # x' = -x + b u, from 5:  x = b u (1 - exp(-t)) + 5 exp(-t)
        blk = {"type": "linear", "in": {"u": "x"}, "settings": {"A": [[-1]], "B": [[b]], "C": [[1]], "initial": [5]}}
        # with no input, Ad alone: 5 exp(-t)
        against("large b %g, Ad" % b, model_run(blk, "1s", 5, 0.0), 1.0, y=lambda t: 5 * exp(-t))
        # with u = 1 / b the answer is of order 1 whatever b is
        against("large b %g, 1/b" % b, model_run(blk, "1s", 5, 1 / b), 1.0, y=lambda t: 1 + 4 * exp(-t))
        if b <= 1e120:
            # and with u = 2 it is of the order of b: compared to one part
            # in 1e9 of the value
            outs = model_run(blk, "1s", 5, 2.0)
            for k, o in enumerate(outs):
                want = 2 * b * (1 - exp(-k)) + 5 * exp(-k)
                check("large b %g, u %d state" % (b, k), o["y"][0], "good")
                check("large b %g, u %d" % (b, k), abs(o["y"][1] - want) <= 1e-9 * max(1.0, abs(want)), True)
    # two states, a spring with no damper driven through a large B, and a
    # second input with a small one. m 2, k 8 (2 rad/s), from rest:
    #   position = (b f / k)(1 - cos 2t), velocity = (b f / (2 m)) sin 2t
    for b in (1e9, 1e80, 1e120):
        blk = {
            "type": "linear",
            "in": {"f": "x", "g": 0},
            "settings": {
                "A": [[0, 1], [-4, 0]],
                "B": [[0, 0], [b / 2, 1e-30]],
                "C": [[1, 0], [0, 1]],
                "inputs": ["f", "g"],
            },
        }
        against(
            "large b %g, spring" % b,
            model_run(blk, "250ms", 10, 4 / b),
            0.25,
            y0=lambda t: (1 - cos(2 * t)) / 2,
            y1=lambda t: sin(2 * t),
        )
    # an integrator: A is zero, and Bd is B times the period
    for b in (1e9, 1e120):
        blk = {"type": "linear", "in": {"u": "x"}, "settings": {"A": [[0]], "B": [[b]], "C": [[1]]}}
        against("large b %g, integrator" % b, model_run(blk, "500ms", 4, 3 / b), 0.5, y=lambda t: 3 * t)

    # Bd past what a double holds is refused, and just within it is not
    def big(b, period):
        blk = {"id": "b", "type": "linear", "in": {"u": 0}, "settings": {"A": [[0]], "B": [[b]], "C": [[1]]}}
        return {"period": period, "blocks": [blk]}

    Engine(big(1e307, "10s"))
    refused("large b: Bd more than a double holds", big(1e308, "10s"))
    # the size of B does not count towards the bound on A
    Engine(big(1e300, "100000s"))

    # the named models of the second order: the row holds the square of
    # the rate. A resonance of 50 Hz is 314.159... rad/s, squared 98,696:
    # within the bound at a period of 1 s and past it at 2.5 s
    def resonance(type_, period, **settings):
        ins = {"u": 0} if type_ == "second_order_process" else {"force": 0}
        return {"period": period, "blocks": [{"id": "b", "type": type_, "in": ins, "settings": settings}]}

    w = 2 * math.pi * 50
    Engine(resonance("second_order_process", "1s", omega_n=w, zeta=0))
    refused("bound: 50 Hz at 2.5 s", resonance("second_order_process", "2500ms", omega_n=w, zeta=0))
    Engine(resonance("mass_spring_damper", "1s", mass=1, damping=0, stiffness=w * w))
    refused(
        "bound: 50 Hz spring at 2.5 s", resonance("mass_spring_damper", "2500ms", mass=1, damping=0, stiffness=w * w)
    )


def est_engine(settings=None, model=None, ins=None, inputs=("z",), max_catch_up=100, period="1s"):
    """One estimator, every output published under its port's name. By
    default a random walk (state_space, A 1, B 0, C 1) with q 1, p0 4 and
    one measurement z of its output with r 1."""
    st = {
        "model": model or {"type": "state_space", "A": [[1]], "B": [0], "C": [1]},
        "q": {"x0": 1},
        "p0": {"x0": 4},
        "measure": {"z": {"of": "y", "r": 1}},
        "consistency": "none",
    }
    st.update(settings or {})
    st = {k: v for k, v in st.items() if v is not None}
    blk = {"id": "b", "type": "estimator", "in": ins or {"u": 0, "z": "z"}, "settings": st}
    g = {
        "period": period,
        "max_catch_up": max_catch_up,
        "inputs": {name: {"max_age": "none"} for name in inputs},
        "blocks": [blk],
    }
    e = Engine(g)
    blk["out"] = {p: p for p in e._blocks["b"].out_ports}
    return Engine(g)


def est_step(e, now, **writes):
    """Write each (state, value) given, at `now` seconds, and call."""
    for name, (state, value) in writes.items():
        e.write(name, state, value, now * S)
    return e.tick(now * S)[1]


def test_estimator_noise():
    """Amendment 5, rule 7.9.2: N is the integral of exp(A.s).Q.exp(A'.s)
    over the period; each closed form here is worked by hand."""
    from impl import _noise

    def same(label, got, want):
        for i, row in enumerate(want):
            for j, w in enumerate(row):
                check("%s %d%d" % (label, i, j), ("good", got[i][j]), ("good", w))

    exp, sin, cos = math.exp, math.sin, math.cos  # noqa
    for T, ns_ in ((0.7, 700000000), (1.0, S), (25.0, 25 * S)):
        # one state: q (exp(2 a T) - 1) / (2 a), and q T where a is zero
        same("noise decay %g" % T, _noise([[-0.3]], [2.0], ns_), [[2 * (exp(-0.6 * T) - 1) / -0.6]])
        same("noise walk %g" % T, _noise([[0.0]], [2.0], ns_), [[2 * T]])
        # two integrators, x0' = x1: exp(A s) is [[1, s], [0, 1]], so the
        # integrand is [[q0 + q1 s^2, q1 s], [q1 s, q1]]
        same(
            "noise chain %g" % T,
            _noise([[0.0, 1.0], [0.0, 0.0]], [3.0, 5.0], ns_),
            [[3 * T + 5 * T**3 / 3, 5 * T * T / 2], [5 * T * T / 2, 5 * T]],
        )
        # three, noise on the last: with e = (s^2 / 2, s, 1) it is q e e'
        same(
            "noise chain3 %g" % T,
            _noise([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [0.0, 0.0, 0.0]], [0.0, 0.0, 2.0], ns_),
            [
                [2 * T**5 / 20, 2 * T**4 / 8, 2 * T**3 / 6],
                [2 * T**4 / 8, 2 * T**3 / 3, 2 * T * T / 2],
                [2 * T**3 / 6, 2 * T * T / 2, 2 * T],
            ],
        )
        # a turn at w: noise on the first state alone goes round with it:
        #   q [[cos^2, cos sin], [cos sin, sin^2]] of w s, integrated
        w = 2.0
        same(
            "noise turn %g" % T,
            _noise([[0.0, -w], [w, 0.0]], [3.0, 0.0], ns_),
            [
                [3 * (T / 2 + sin(2 * w * T) / (4 * w)), 3 * sin(w * T) ** 2 / (2 * w)],
                [3 * sin(w * T) ** 2 / (2 * w), 3 * (T / 2 - sin(2 * w * T) / (4 * w))],
            ],
        )
        # the same noise on both: it does not turn at all
        same("noise turn even %g" % T, _noise([[0.0, -w], [w, 0.0]], [3.0, 3.0], ns_), [[3 * T, 0.0], [0.0, 3 * T]])
        # two decays apart, rates 1 and 100
        same(
            "noise apart %g" % T,
            _noise([[-1.0, 0.0], [0.0, -100.0]], [2.0, 4.0], ns_),
            [[(1 - exp(-2 * T)), 0.0], [0.0, 4 * (1 - exp(-200 * T)) / 200]],
        )
        # a decay driving an integrator: x0' = -a x0, x1' = x0, noise on x0.
        # exp(A s) is [[e, 0], [(1 - e) / a, 1]] with e = exp(-a s), so
        #   N00 = q (1 - E^2) / (2 a),  N01 = q (1 - E)^2 / (2 a^2),
        #   N11 = q (T - 2 (1 - E) / a + (1 - E^2) / (2 a)) / a^2,  E = exp(-a T)
        a, q = 0.5, 3.0
        E = exp(-a * T)
        same(
            "noise lag %g" % T,
            _noise([[-a, 0.0], [1.0, 0.0]], [q, 0.0], ns_),
            [
                [q * (1 - E * E) / (2 * a), q * (1 - E) ** 2 / (2 * a * a)],
                [q * (1 - E) ** 2 / (2 * a * a), q * (T - 2 * (1 - E) / a + (1 - E * E) / (2 * a)) / (a * a)],
            ],
        )

    # through the engine. Two integrators, p0 2 and 3, q 3 and 5, period
    # 2 s. After one predict P is Ad P0 Ad' + N with Ad = [[1, 2], [0, 1]]:
    #   P00 = 2 + 3*4 + (3*2 + 5*8/3), P01 = 3*2 + 5*4/2, P11 = 3 + 5*2
    chain = {"type": "linear", "A": [[0, 1], [0, 0]], "B": [[0], [1]], "C": [[1, 0]], "states": ["pos", "vel"]}
    e = est_engine(
        {"q": {"pos": 3, "vel": 5}, "p0": {"pos": 2, "vel": 3}, "measure": {"z": {"of": "y", "r": 4}}},
        model=chain,
        period="2s",
    )
    o = est_step(e, 0)
    check("chain sigma pos 0", o["sigma_pos"], ("good", math.sqrt(2.0)))
    o = est_step(e, 2)
    p00, p01, p11 = 2 + 12 + 6 + 40 / 3, 6 + 10.0, 3 + 10.0
    check("chain sigma pos 1", o["sigma_pos"], ("good", math.sqrt(p00)))
    check("chain sigma vel 1", o["sigma_vel"], ("good", math.sqrt(p11)))
    # a measurement of the position at tick 2 shows the covariance between
    # the two. Predict again: P00' = p00 + 4 p01 + 4 p11 + N00 and so on.
    q00 = p00 + 4 * p01 + 4 * p11 + 6 + 40 / 3
    q01 = p01 + 2 * p11 + 10
    q11 = p11 + 10
    o = est_step(e, 4, z=("good", 7.0))
    s_ = q00 + 4
    check("chain innovation", o["innovation_z"], ("good", 7.0))
    check("chain nis", o["nis_z"], ("good", 49 / s_))
    check("chain pos", o["pos"], ("good", q00 / s_ * 7))
    check("chain vel", o["vel"], ("good", q01 / s_ * 7))
    check("chain sigma pos 2", o["sigma_pos"], ("good", math.sqrt(q00 - q00 * q00 / s_)))
    check("chain sigma vel 2", o["sigma_vel"], ("good", math.sqrt(q11 - q01 * q01 / s_)))
    # state_space is in discrete time: q times the period on the diagonal
    e = est_engine(period="250ms")
    est_step(e, 0)
    check("discrete noise", e.tick(250000000)[1]["sigma_x0"], ("good", math.sqrt(4.25)))


def test_estimator_rules():
    """Amendment 5, rules 7.9.3 to 7.9.9, on a random walk: predict adds 1
    to the variance, and a measurement with r 1 of a state of variance P
    has a gain of P / (P + 1)."""
    # --- the gate and max_refused (rule 5)
    e = est_engine({"gate": 3, "max_refused": 1})
    o = est_step(e, 0, z=("good", 0.0))  # P 4, s 5, used: P 0.8
    check("gate 0 x", o["x0"], ("good", 0.0))
    check("gate 0 nis", o["nis_z"], ("good", 0.0))
    # tick 1: P 1.8, s 2.8, innovation 100, more than 3 sqrt(2.8): refused.
    # Nothing changes but the count, and the tick is uncertain.
    o = est_step(e, 1, z=("good", 100.0))
    check("gate 1 x", o["x0"], ("uncertain", 0.0))
    check("gate 1 sigma", o["sigma_x0"], ("uncertain", math.sqrt(1.8)))
    check("gate 1 innovation", o["innovation_z"], ("good", 100.0))
    check("gate 1 nis", o["nis_z"], ("good", 10000 / 2.8))
    check("gate 1 refused", o["refused_z"], ("good", 1.0))
    check("gate 1 since", o["since_z"], ("good", 1.0))
    # round two: max_refused is the most a port refuses in a row. Tick 2:
    # P 2.8, over the gate again; it would be the second in a row, one more
    # than max_refused, so it is not refused. The variance grows by p0 to
    # 6.8, s is 7.8, and it is used. Its nis is the one from before: s 3.8.
    # It has given in to what it was refusing: the tick is uncertain.
    o = est_step(e, 2, z=("good", 100.0))
    x2 = 6.8 / 7.8 * 100
    check("gate 2 x", o["x0"], ("uncertain", x2))
    check("gate 2 sigma", o["sigma_x0"], ("uncertain", math.sqrt(6.8 / 7.8)))
    check("gate 2 nis", o["nis_z"], ("good", 10000 / 3.8))
    check("gate 2 refused", o["refused_z"], ("good", 1.0))
    check("gate 2 since", o["since_z"], ("good", 0.0))
    # tick 3: P 1.87..., innovation 12.8..., more than 3 sqrt(2.87...):
    # refused, the first of a new run
    o = est_step(e, 3, z=("good", 100.0))
    check("gate 3 x", o["x0"], ("uncertain", x2))
    check("gate 3 refused", o["refused_z"], ("good", 2.0))
    # tick 4: nothing considered: good, and the run is left as it was
    o = est_step(e, 4)
    check("gate 4 x", o["x0"], ("good", x2))
    check("gate 4 nis", o["nis_z"], ("not_ready", None))
    # tick 5: P is 6.8 / 7.8 + 3; over the gate, and one more than the one
    # refused at tick 3: used, with the variance grown by 4
    o = est_step(e, 5, z=("good", 100.0))
    p5 = 6.8 / 7.8 + 3 + 4
    check("gate 5 x", o["x0"], ("uncertain", x2 + p5 / (p5 + 1) * (100 - x2)))
    check("gate 5 refused", o["refused_z"], ("good", 2.0))
    check("gate 5 nis", o["nis_z"], ("good", (100 - x2) ** 2 / (p5 - 4 + 1)))
    # tick 6: within the gate now: used as any other, and good
    o = est_step(e, 6, z=("good", 100.0))
    check("gate 6 state", o["x0"][0], "good")
    check("gate 6 refused", o["refused_z"], ("good", 2.0))
    # max_refused of 0: it refuses none. The first over the gate is used,
    # with the variance grown: P 1.8 + 4, s 6.8
    e = est_engine({"gate": 3, "max_refused": 0})
    est_step(e, 0, z=("good", 0.0))
    o = est_step(e, 1, z=("good", 100.0))
    check("gate m0 1", o["x0"], ("uncertain", 5.8 / 6.8 * 100))
    check("gate m0 1 refused", o["refused_z"], ("good", 0.0))
    check("gate m0 1 nis", o["nis_z"], ("good", 10000 / 2.8))
    # max_refused of 2: two refused, the third used
    e = est_engine({"gate": 3, "max_refused": 2})
    est_step(e, 0, z=("good", 0.0))
    check("gate m2 1", est_step(e, 1, z=("good", 100.0))["refused_z"], ("good", 1.0))
    check("gate m2 2", est_step(e, 2, z=("good", 100.0))["refused_z"], ("good", 2.0))
    o = est_step(e, 3, z=("good", 100.0))  # P 3.8 + 4, s 8.8
    check("gate m2 3", o["x0"], ("uncertain", 7.8 / 8.8 * 100))
    check("gate m2 3 refused", o["refused_z"], ("good", 2.0))
    # within the gate it is used, and exactly at it too: P 4, s 5, gate 2:
    # an innovation of 2 sqrt(5) is not more than that
    e = est_engine({"gate": 2, "max_refused": 0})
    check("gate edge", est_step(e, 0, z=("good", 2 * math.sqrt(5.0)))["refused_z"], ("good", 0.0))

    # --- consistency (rule 6): over 2, limit 2
    e = est_engine({"consistency": {"over": 2, "limit": 2}})
    o = est_step(e, 0, z=("good", 0.0))  # nis 0; one kept, not yet two
    check("cons 0", o["x0"], ("good", 0.0))
    # tick 1: P 1.8, z 3: nis 9 / 2.8 = 3.214; kept 0 and 3.214: mean 1.607
    o = est_step(e, 1, z=("good", 3.0))
    x1 = 3 * 1.8 / 2.8
    check("cons 1", o["x0"], ("good", x1))
    # tick 2: P 1 + 1.8 / 2.8; z 6: the mean of the last two is over 2
    p2 = 1 + 1.8 / 2.8
    n2 = (6 - x1) ** 2 / (p2 + 1)
    check("cons 2 mean over the limit", (9 / 2.8 + n2) / 2 > 2, True)
    o = est_step(e, 2, z=("good", 6.0))
    x2 = x1 + p2 / (p2 + 1) * (6 - x1)
    check("cons 2", o["x0"], ("uncertain", x2))
    check("cons 2 nis", o["nis_z"], ("good", n2))
    check("cons 2 sigma", o["sigma_x0"], ("uncertain", math.sqrt(p2 / (p2 + 1))))
    # tick 3: nothing considered: it is inconsistent while that is so
    check("cons 3", est_step(e, 3)["x0"], ("uncertain", x2))
    # tick 4: z = x, nis 0: kept n2 and 0, mean still over 2
    check("cons 4 mean", n2 / 2 > 2, True)
    check("cons 4", est_step(e, 4, z=("good", x2))["x0"], ("uncertain", x2))
    # tick 5: nis 0 again: kept 0 and 0
    check("cons 5", est_step(e, 5, z=("good", x2))["x0"], ("good", x2))
    # a gap does not empty what a port keeps: 0 and 0, then one large one
    # after a rebase: kept 0 and large
    e.rebase(0)
    o = est_step(e, 0, z=("good", x2 + 30))
    check("cons gap", o["x0"][0], "uncertain")
    # a reset does: one large one alone is not `over` of them
    e.reset()
    check("cons reset", est_step(e, 0, z=("good", 30.0))["x0"][0], "good")
    # refused ones are among them: gate 3, over 1, limit 5
    e = est_engine({"gate": 3, "max_refused": 9, "consistency": {"over": 1, "limit": 5}})
    est_step(e, 0, z=("good", 0.0))
    check("cons refused 1", est_step(e, 1, z=("good", 100.0))["x0"], ("uncertain", 0.0))
    # nothing new at tick 2: no refusal at this tick, but still inconsistent
    check("cons refused 2", est_step(e, 2)["x0"], ("uncertain", 0.0))
    check("cons refused 3", est_step(e, 3, z=("good", 0.0))["x0"], ("good", 0.0))

    # --- an uncertain measurement (rules 3 and 7): r 1, r_uncertain 4
    e = est_engine({"measure": {"z": {"of": "y", "r": 1, "r_uncertain": 4}}})
    o = est_step(e, 0, z=("uncertain", 5.0))  # P 4, s 8, gain 0.5
    check("unc 0 x", o["x0"], ("uncertain", 2.5))
    check("unc 0 sigma", o["sigma_x0"], ("uncertain", math.sqrt(2.0)))
    check("unc 0 innovation", o["innovation_z"], ("good", 5.0))
    check("unc 0 nis", o["nis_z"], ("good", 25 / 8))
    # none of it lasts past its tick. Tick 1: P 3, good 2.5: s 4, gain 0.75
    o = est_step(e, 1, z=("good", 2.5))
    check("unc 1 x", o["x0"], ("good", 2.5))
    check("unc 1 sigma", o["sigma_x0"], ("good", math.sqrt(0.75)))
    # with no r_uncertain it is not considered, and the tick is good
    e = est_engine()
    o = est_step(e, 0, z=("uncertain", 5.0))
    check("unc none x", o["x0"], ("good", 0.0))
    check("unc none nis", o["nis_z"], ("not_ready", None))
    # and its sample time is not taken: written again as good with the
    # same time, 0 s, it is considered at tick 1
    e.write("z", "good", 5.0, 0)
    o = e.tick(1 * S)[1]
    check("unc none 1", o["innovation_z"], ("good", 5.0))
    # an uncertain one that is refused: uncertain, and counted
    e = est_engine({"measure": {"z": {"of": "y", "r": 1, "r_uncertain": 4}}, "gate": 1, "max_refused": 3})
    o = est_step(e, 0, z=("uncertain", 50.0))
    check("unc refused", o["x0"], ("uncertain", 0.0))
    check("unc refused count", o["refused_z"], ("good", 1.0))

    # --- the model inputs are deferred (rules 2 and 7): x' = x + u
    walk = {"type": "state_space", "A": [[1]], "B": [1], "C": [1]}
    e = est_engine(model=walk, ins={"u": "u", "z": "z"}, inputs=("u", "z"))
    check("in 0", est_step(e, 0, u=("good", 1.0))["x0"], ("good", 0.0))
    # tick 1: the step was on a good 1. u is uncertain at tick 1 ...
    check("in 1", est_step(e, 1, u=("uncertain", 2.0))["x0"], ("good", 1.0))
    # ... so the step to tick 2, on that 2, makes tick 2 uncertain. u is
    # unusable at tick 2: the step to tick 3 is on the 2 it last had
    check("in 2", est_step(e, 2, u=("bad", None))["x0"], ("uncertain", 3.0))
    check("in 3", est_step(e, 3, u=("good", 10.0))["x0"], ("uncertain", 5.0))
    check("in 4", est_step(e, 4)["x0"], ("good", 15.0))
    # an input that has never been usable: no step, the covariance is
    # P + N, and the tick is uncertain
    e = est_engine(model=walk, ins={"u": "u", "z": "z"}, inputs=("u", "z"))
    est_step(e, 0)
    o = est_step(e, 1, u=("good", 1.0))
    check("in never x", o["x0"], ("uncertain", 0.0))
    check("in never sigma", o["sigma_x0"], ("uncertain", math.sqrt(5.0)))
    check("in never 2", est_step(e, 2)["x0"], ("good", 1.0))
    # deferred, so a loop through them alone compiles: its own estimate,
    # through a formula, as its model input
    g = {
        "period": "1s",
        "inputs": {"zz": {"max_age": "none"}},
        "blocks": [
            {
                "id": "b",
                "type": "estimator",
                "in": {"u": "f.y", "z": "zz"},
                "settings": {
                    "model": walk,
                    "q": {"x0": 1},
                    "p0": {"x0": 4},
                    "measure": {"z": {"of": "y", "r": 1}},
                    "consistency": "none",
                },
            },
            {"id": "f", "type": "formula", "in": {"x": "b.x0"}, "settings": {"expr": "0 - x"}},
        ],
    }
    Engine(g)

    # --- sigma_max: of that state alone, for as long as it is so
    e = est_engine({"sigma_max": {"x0": 2.5}})
    check("smax 0", est_step(e, 0)["sigma_x0"], ("good", 2.0))
    check("smax 1", est_step(e, 1)["sigma_x0"], ("good", math.sqrt(5.0)))
    check("smax 2", est_step(e, 2)["sigma_x0"], ("good", math.sqrt(6.0)))
    o = est_step(e, 3)
    check("smax 3 sigma", o["sigma_x0"], ("uncertain", math.sqrt(7.0)))
    check("smax 3 x", o["x0"], ("uncertain", 0.0))
    o = est_step(e, 4, z=("good", 0.0))  # P 8, s 9: 8 / 9
    check("smax 4", o["sigma_x0"], ("good", math.sqrt(8.0 / 9)))

    # --- a measurement of an output that is not a state: a motor's torque,
    # 3 times its current. p0 4 and 1, r 1: c is (3, 0), s = 9*4 + 1 = 37.
    # The current starts at 1, so a torque of 6 has an innovation of 3.
    # sigma_max on the speed alone: its sigma of 1 is over 0.5, and the
    # speed's outputs are uncertain while the current's are good.
    motor = {
        "type": "dc_motor",
        "resistance": 1,
        "inductance": 1,
        "back_emf": 1,
        "torque_constant": 3,
        "inertia": 1,
        "friction": 1,
        "initial_current": 1,
    }
    e = est_engine(
        {
            "q": {"current": 0, "speed": 0},
            "p0": {"current": 4, "speed": 1},
            "measure": {"z": {"of": "torque", "r": 1}},
            "sigma_max": {"speed": 0.5},
        },
        model=motor,
        ins={"voltage": 0, "load_torque": 0, "z": "z"},
    )
    o = est_step(e, 0, z=("good", 6.0))
    check("torque innovation", o["innovation_z"], ("good", 3.0))
    check("torque nis", o["nis_z"], ("good", 9 / 37))
    check("torque current", o["current"], ("good", 1 + 12 / 37 * 3))
    check("torque speed", o["speed"], ("uncertain", 0.0))
    check("torque sigma current", o["sigma_current"], ("good", math.sqrt(4 - 144 / 37)))
    check("torque sigma speed", o["sigma_speed"], ("uncertain", 1.0))

    # --- at a gap (rule 9). A stall that passes over three: it predicts
    # three times more, and once for the tick: P = 4 + 3 + 1. Uncertain at
    # that tick and good at the next.
    e = est_engine(max_catch_up=1)
    check("gap 0", est_step(e, 0)["sigma_x0"], ("good", 2.0))
    o = est_step(e, 4)
    check("gap stall info", e.info, info(True, 4, 4 * S, skipped=3))
    check("gap stall", o["sigma_x0"], ("uncertain", math.sqrt(8.0)))
    check("gap stall next", est_step(e, 5)["sigma_x0"], ("good", 3.0))
    # on the model inputs it last had: x' = x + u, u 2: three steps and one
    e = est_engine(model=walk, ins={"u": "u", "z": "z"}, inputs=("u", "z"), max_catch_up=1)
    est_step(e, 0, u=("good", 2.0))
    check("gap stall inputs", est_step(e, 4)["x0"], ("uncertain", 8.0))
    # a model in continuous time: a decay at 0.5 a second, q 3. Each
    # predict is P -> P exp(-1) + 3 (1 - exp(-1)); from 4, twice over
    decay = {"type": "linear", "A": [[-0.5]], "B": [[1]], "C": [[1]]}
    f, nn = math.exp(-1.0), 3 * (1 - math.exp(-1.0))
    e2 = est_engine({"q": {"x0": 3}}, model=decay, max_catch_up=1)
    est_step(e2, 0)
    check("gap stall decay", est_step(e2, 2)["sigma_x0"], ("uncertain", math.sqrt((4 * f + nn) * f + nn)))

    # --- what is refused
    def bad(label, settings=None, **kw):
        try:
            est_engine(settings, **kw)
        except CompileError:
            check("est refused " + label, True, True)
            return
        check("est refused " + label, "accepted", "refused")

    bad("no consistency", {"consistency": None})
    bad("consistency off", {"consistency": "off"})
    bad("consistency false", {"consistency": False})
    bad("consistency no limit", {"consistency": {"over": 5}})
    bad("consistency no over", {"consistency": {"limit": 2}})
    bad("consistency over 0", {"consistency": {"over": 0, "limit": 2}})
    bad("consistency over 2.5", {"consistency": {"over": 2.5, "limit": 2}})
    bad("consistency limit 0", {"consistency": {"over": 5, "limit": 0}})
    bad("consistency unknown key", {"consistency": {"over": 5, "limit": 2, "window": 3}})
    est_engine({"consistency": {"over": 1, "limit": 0.5}})
    bad("gate with no max_refused", {"gate": 3})
    bad("max_refused with no gate", {"max_refused": 3})
    bad("max_refused below zero", {"gate": 3, "max_refused": -1})
    bad("max_refused not whole", {"gate": 3, "max_refused": 1.5})
    est_engine({"gate": 0, "max_refused": 0})
    bad("use_uncertain is gone", {"use_uncertain": True})
    bad("r_uncertain less than r", {"measure": {"z": {"of": "y", "r": 2, "r_uncertain": 1}}})
    est_engine({"measure": {"z": {"of": "y", "r": 2, "r_uncertain": 2}}})
    bad("of a state that is no output", {"measure": {"z": {"of": "x0", "r": 1}}})
    bad("of nothing", {"measure": {"z": {"r": 1}}})
    bad("r zero", {"measure": {"z": {"of": "y", "r": 0}}})
    # a measurement of an output that reads an input directly
    bad("of an output that reads an input", model={"type": "state_space", "A": [[1]], "B": [0], "C": [1], "D": 1})
    lin = {"type": "linear", "A": [[0]], "B": [[1]], "C": [[1], [1]], "D": [[0], [2]], "outputs": ["clean", "fed"]}
    est_engine({"measure": {"z": {"of": "clean", "r": 1}}}, model=lin)
    bad("of a linear output that reads an input", {"measure": {"z": {"of": "fed", "r": 1}}}, model=lin)
    # the model inputs are deferred and the measurements direct
    e = est_engine()
    check("est deferred", {p: v[2] for p, v in e._blocks["b"].in_ports.items()}, {"u": False, "z": True})
    check("est nis port", "nis_z" in e._blocks["b"].out_ports, True)


def test_estimator_long_gap():
    """Amendment 5, round two, rule 7.9.9: what is specified at a gap is the
    result of n predictions, not that they are made one by one."""
    # a random walk: each prediction adds 1 to the variance. A stall that
    # passes over a million ticks, and the tick that runs: 4 + 1,000,001
    e = est_engine(max_catch_up=1)
    est_step(e, 0)
    o = est_step(e, 10**6 + 1)
    check("long gap info", e.info, info(True, 10**6 + 1, (10**6 + 1) * S, skipped=10**6))
    check("long gap walk", o["sigma_x0"], ("uncertain", math.sqrt(4 + 10**6 + 1.0)))
    # a decay at 0.5 a second driven by u = 3, q 2, p0 4, from 0. With
    # a = exp(-0.5): one prediction is x -> a x + 2 (1 - a) u ... the model
    # rests at u / 0.5 = 6, and N = 2 (1 - a^2). After m predictions:
    #   x = 6 (1 - a^m),  P = 4 a^(2m) + 2 (1 - a^(2m))
    decay = {"type": "linear", "A": [[-0.5]], "B": [[1]], "C": [[1]]}
    for passed in (5, 40, 999):
        e = est_engine({"q": {"x0": 2}}, model=decay, ins={"u": "u", "z": "z"}, inputs=("u", "z"), max_catch_up=1)
        est_step(e, 0, u=("good", 3.0))
        o = est_step(e, passed + 1)
        m = passed + 1
        a = math.exp(-0.5)
        check("long gap decay %d x" % passed, o["x0"], ("uncertain", 6 * (1 - a**m)))
        check(
            "long gap decay %d sigma" % passed,
            o["sigma_x0"],
            ("uncertain", math.sqrt(4 * a ** (2 * m) + 2 * (1 - a ** (2 * m)))),
        )
    # two integrators, u = 1: after m predictions of 1 s each, from rest,
    # vel = m and pos = m^2 / 2; and with q on vel alone and p0 (2, 3):
    #   P11 = 3 + q m,  P00 = 2 + 3 m^2 + q m^3 / 3
    chain = {"type": "linear", "A": [[0, 1], [0, 0]], "B": [[0], [1]], "C": [[1, 0]], "states": ["pos", "vel"]}
    for passed in (7, 499):
        e = est_engine(
            {"q": {"pos": 0, "vel": 5}, "p0": {"pos": 2, "vel": 3}},
            model=chain,
            ins={"u": "u", "z": "z"},
            inputs=("u", "z"),
            max_catch_up=1,
        )
        est_step(e, 0, u=("good", 1.0))
        o = est_step(e, passed + 1)
        m = passed + 1
        check("long gap chain %d pos" % passed, o["pos"], ("uncertain", m * m / 2))
        check("long gap chain %d vel" % passed, o["vel"], ("uncertain", float(m)))
        check("long gap chain %d sigma vel" % passed, o["sigma_vel"], ("uncertain", math.sqrt(3 + 5.0 * m)))
        check(
            "long gap chain %d sigma pos" % passed,
            o["sigma_pos"],
            ("uncertain", math.sqrt(2 + 3.0 * m * m + 5 * m**3 / 3)),
        )
    # an input that has never been usable: the state stays, P + N each time
    walk = {"type": "state_space", "A": [[1]], "B": [1], "C": [1]}
    e = est_engine(model=walk, ins={"u": "u", "z": "z"}, inputs=("u", "z"), max_catch_up=1)
    est_step(e, 0)
    o = est_step(e, 100)
    check("long gap never x", o["x0"], ("uncertain", 0.0))
    check("long gap never sigma", o["sigma_x0"], ("uncertain", math.sqrt(4 + 100.0)))
    # a model block across a long stall: it steps while it rides through,
    # 3 ticks here, and no further; a million passed over cost nothing
    mass = {
        "id": "b",
        "type": "thermal_mass",
        "in": {"power": "x", "ambient": 20},
        "settings": {"thermal_mass": 10, "heat_transfer": 1, "initial": 20, "ride_through": "3s"},
        "out": {"temp": "temp", "doubtful": "doubtful", "elapsed": "elapsed"},
    }
    e = Engine({"period": "1s", "max_catch_up": 1, "inputs": {"x": {"max_age": "none"}}, "blocks": [mass]})
    e.write("x", "good", 10.0, 0)
    e.tick(0)
    o = e.tick((10**6 + 1) * S)[1]
    check("long gap model temp", o["temp"], ("uncertain", 30 - 10 * math.exp(-0.4)))
    check("long gap model doubtful", o["doubtful"], ("good", 10.0**6))
    check("long gap model elapsed", o["elapsed"], ("good", 10.0**6 + 2))


def test_estimator_round_three():
    """Amendment 5, round three."""
    # rule 7.9.4: the covariance is updated in the form that rounding
    # cannot bring to nothing. x' = x, q 0, p0 1e16, r 1: the estimate
    # after n measurements is their mean, with a sigma of 1 / sqrt(n).
    # (In the short form the variance is exactly zero after the first.)
    e = est_engine({"q": {"x0": 0}, "p0": {"x0": 1e16}})
    zs = [11.25, 9.5, 10.75, 8.5, 10.0, 12.25, 9.75, 7.0]
    for k, z in enumerate(zs):
        o = est_step(e, k, z=("good", z))
        check("joseph %d x" % k, o["x0"], ("good", sum(zs[: k + 1]) / (k + 1)))
        check("joseph %d sigma" % k, o["sigma_x0"], ("good", (k + 1) ** -0.5))
    # two states: with p0 very large the first measurement of the first
    # state leaves it a variance of r and the second state untouched
    chain = {"type": "linear", "A": [[0, 1], [0, 0]], "B": [[0], [1]], "C": [[1, 0]], "states": ["pos", "vel"]}
    e = est_engine({"q": {"pos": 0, "vel": 0}, "p0": {"pos": 1e16, "vel": 9}}, model=chain)
    o = est_step(e, 0, z=("good", 5.0))
    check("joseph chain pos", o["pos"], ("good", 5.0))
    check("joseph chain sigma pos", o["sigma_pos"], ("good", 1.0))
    check("joseph chain sigma vel", o["sigma_vel"], ("good", 3.0))
    # tick 1: Ad = [[1, 1], [0, 1]]: P = [[1 + 9, 9], [9, 9]]; a measurement
    # of 7: innovation 2, s 11: pos = 5 + 20/11, vel = 18/11;
    # P00 = 10 - 100/11, P11 = 9 - 81/11
    o = est_step(e, 1, z=("good", 7.0))
    check("joseph chain pos 1", o["pos"], ("good", 5 + 20 / 11))
    check("joseph chain vel 1", o["vel"], ("good", 18 / 11))
    check("joseph chain sigma pos 1", o["sigma_pos"], ("good", math.sqrt(10 - 100 / 11)))
    check("joseph chain sigma vel 1", o["sigma_vel"], ("good", math.sqrt(9 - 81 / 11)))

    # rule 7.9.7: after a gap of no known length it is uncertain until a
    # measurement has been used
    e = est_engine()
    check("lost 0", est_step(e, 0, z=("good", 5.0))["x0"], ("good", 4.0))
    saved = e.save()
    e.restore(saved)
    check("lost 1", est_step(e, 0)["x0"], ("uncertain", 4.0))  # the gap's tick
    check("lost 2", est_step(e, 1)["x0"], ("uncertain", 4.0))  # nothing written
    check("lost 3", est_step(e, 2)["x0"], ("uncertain", 4.0))
    # tick 4: P = 0.8 + 1 + 4 + 3 = 8.8; a measurement of 4 is used: good
    o = est_step(e, 3, z=("good", 4.0))
    check("lost 4", o["x0"], ("good", 4.0))
    check("lost 4 sigma", o["sigma_x0"], ("good", math.sqrt(8.8 / 9.8)))
    check("lost 5", est_step(e, 4)["x0"], ("good", 4.0))
    # it is part of what a save holds
    e = est_engine()
    est_step(e, 0, z=("good", 5.0))
    e.rebase()
    est_step(e, 0)
    saved = e.save()
    e.reset()
    e.restore(saved)
    e.rebase(1 * S)  # a length this time: but none has been used since the first
    check("lost saved", est_step(e, 0)["x0"][0], "uncertain")
    # a measurement that is refused does not end it; one taken by rule 5 does
    e = est_engine({"gate": 3, "max_refused": 1})
    est_step(e, 0, z=("good", 0.0))
    e.rebase()
    check("lost refused", est_step(e, 0, z=("good", 100.0))["x0"][0], "uncertain")  # refused
    check("lost given in", est_step(e, 1, z=("good", 100.0))["x0"][0], "uncertain")  # used by rule 5
    # (P was 0.8 + 4 + 1 + 1 + 4 = 10.8 as it gave in: the estimate is at
    # 10.8 / 11.8 of 100; a measurement there is within the gate)
    check("lost after", est_step(e, 2, z=("good", 10.8 / 11.8 * 100))["x0"], ("good", 10.8 / 11.8 * 100))
    # refused at the gap's tick, and nothing written after: still lost
    e = est_engine({"gate": 3, "max_refused": 5})
    est_step(e, 0, z=("good", 0.0))
    e.rebase()
    check("lost, refused", est_step(e, 0, z=("good", 100.0))["refused_z"], ("good", 1.0))
    check("lost, refused, next", est_step(e, 1)["x0"], ("uncertain", 0.0))
    # a gap of known length, and a stall, do not start it
    e = est_engine(max_catch_up=1)
    est_step(e, 0, z=("good", 5.0))
    check("lost stall", est_step(e, 5)["x0"][0], "uncertain")
    check("lost stall next", est_step(e, 6)["x0"][0], "good")
    e.rebase(3 * S)
    check("lost known", est_step(e, 0)["x0"][0], "uncertain")
    check("lost known next", est_step(e, 1)["x0"][0], "good")

    # rule 7.9.3: where a measurement may be read from
    def reads(z, blocks=(), inputs=("m", "n")):
        est = {
            "id": "est",
            "type": "estimator",
            "in": {"u": 0, "z": z},
            "settings": {
                "model": {"type": "state_space", "A": [[1]], "B": [0], "C": [1]},
                "q": {"x0": 1},
                "p0": {"x0": 4},
                "measure": {"z": {"of": "y", "r": 1}},
                "consistency": "none",
            },
            "out": {"x0": "x", "nis_z": "nis"},
        }
        return {
            "period": "1s",
            "inputs": {name: {"max_age": "none"} for name in inputs},
            "blocks": [est] + list(blocks),
        }

    def formula(bid, expr, ins, **settings):
        return {"id": bid, "type": "formula", "in": ins, "settings": dict(settings, expr=expr)}

    delay = {"id": "d", "type": "delay", "in": {"x": "m"}}
    Engine(reads("m"))
    Engine(reads("d.y", [delay]))
    Engine(reads("f.y", [formula("f", "a * 2", {"a": "m"})]))  # one signal input: its time
    Engine(reads("f.y", [formula("f", "a + b", {"a": "m", "b": "n"}, sample_of="b")]))
    Engine(reads("f.y", [formula("f", "a + b", {"a": "m", "b": 3})]))  # one signal and a constant
    # through any number of those
    chain = [
        formula("f", "a * 2", {"a": "m"}),
        {"id": "d", "type": "delay", "in": {"x": "f.y"}, "settings": {"ticks": 2}},
        formula("g", "a + b", {"a": "d.y", "b": "n"}, sample_of="a"),
    ]
    Engine(reads("g.y", chain))
    # a formula of two signals with no sample_of gives the time of the tick
    refused("measure: formula of two", reads("f.y", [formula("f", "a + b", {"a": "m", "b": "n"})]))
    refused("measure: formula of constants", reads("f.y", [formula("f", "a + 1", {"a": 2})]))
    # ... also further up the chain
    chain[0] = formula("f", "a + b", {"a": "m", "b": "n"})
    refused("measure: formula of two, up the chain", reads("g.y", chain))
    # any other block gives the time of the tick
    lp = {"id": "lp", "type": "lowpass", "in": {"x": "m"}, "settings": {"tau": "1s"}}
    refused("measure: a low-pass", reads("lp.y", [lp]))
    win = {"id": "w", "type": "window", "in": {"x": "m"}, "settings": {"window": "2s"}}
    refused("measure: a window", reads("w.mean", [win]))
    mass = {"id": "p", "type": "first_order_process", "in": {"u": "m"}, "settings": {"tau": "1s"}}
    refused("measure: a model block", reads("p.y", [mass]))
    refused("measure: a delay of a model block", reads("d.y", [mass, dict(delay, **{"in": {"x": "p.y"}})]))
    # the sample_of input has to lead to an input too
    refused(
        "measure: sample_of a low-pass",
        reads("f.y", [lp, formula("f", "a + b", {"a": "m", "b": "lp.y"}, sample_of="b")]),
    )
    # its own estimate, by a delay: an estimator's outputs have the time of the tick
    own = {"id": "d", "type": "delay", "in": {"x": "est.x0"}, "settings": {"initial": 0}}
    refused("measure: its own estimate", reads("d.y", [own]))
    # a delay that reads itself through a formula never comes from an input
    loop = [
        {"id": "d", "type": "delay", "in": {"x": "f.y"}, "settings": {"initial": 0}},
        formula("f", "a + 1", {"a": "d.y"}),
    ]
    refused("measure: a loop of a delay and a formula", reads("d.y", loop))
    # round four: a constant is refused: it is not a sample of anything
    refused("measure: a constant", reads(3))
    # a measurement by a formula is a new sample only when its input is:
    # written once, it is considered once
    e = Engine(reads("f.y", [formula("f", "a * 2", {"a": "m"})]))
    e.write("m", "good", 2.5, 0)
    check("measure: by a formula 0", e.tick(0)[1]["x"], ("good", 4.0))
    check("measure: by a formula 1", e.tick(1 * S)[1]["nis"], ("not_ready", None))


def test_fallback_sample_time():
    """Amendment 5, round four, rule 3.7: a value a fallback puts in
    carries no sample time: it is not a sample of anything."""
    # an estimator of x' = x, q 0, p0 4, measuring a formula of an input
    # with a fallback of 7, r 1 and r_uncertain 4. While the input is
    # unusable the fallback's 7 is never considered: nothing moves.
    f = {"id": "f", "type": "formula", "in": {"a": "m"}, "settings": {"expr": "a * 1"}, "fallback": {"y": 7}}
    est = {
        "id": "est",
        "type": "estimator",
        "in": {"u": 0, "z": "f.y"},
        "settings": {
            "model": {"type": "state_space", "A": [[1]], "B": [0], "C": [1]},
            "q": {"x0": 0},
            "p0": {"x0": 4},
            "measure": {"z": {"of": "y", "r": 1, "r_uncertain": 4}},
            "consistency": "none",
        },
        "out": {"x0": "x", "nis_z": "nis", "sigma_x0": "sigma"},
    }
    e = Engine({"period": "1s", "inputs": {"m": {"max_age": "none"}}, "blocks": [est, f]})
    for k in range(6):
        o = e.tick(k * S)[1]
        check("fb est %d nis" % k, o["nis"], ("not_ready", None))
        check("fb est %d x" % k, o["x"], ("good", 0.0))
        check("fb est %d sigma" % k, o["sigma"], ("good", 2.0))
    # the input comes back at tick 6 with a 3: one measurement, P 4, s 5
    e.write("m", "good", 3.0, 6 * S)
    o = e.tick(6 * S)[1]
    check("fb est 6 nis", o["nis"], ("good", 9 / 5))
    check("fb est 6 x", o["x"], ("good", 2.4))
    check("fb est 6 sigma", o["sigma"], ("good", math.sqrt(0.8)))

    # a window with only_new: the fallback's value is no new sample
    g = {
        "period": "1s",
        "inputs": {"m": {"max_age": "2s"}},
        "blocks": [
            f,
            {
                "id": "w",
                "type": "window",
                "in": {"x": "f.y"},
                "settings": {"window": "4s", "min_good": 0.25, "only_new": True},
                "out": {"count": "count", "mean": "mean"},
            },
            {
                "id": "plain",
                "type": "window",
                "in": {"x": "f.y"},
                "settings": {"window": "4s", "min_good": 0.25},
                "out": {"count": "plain_count", "mean": "plain_mean"},
            },
        ],
    }
    e = Engine(g)
    e.write("m", "good", 1.0, 0)
    o = e.tick(0)[1]
    check("fb window 0", o["count"], ("good", 1.0))
    # ticks 1 and 2: the 1 still stands; not new. Ticks 3 and 4: it is too
    # old, and the formula gives its fallback, uncertain: for the window
    # with only_new that holds no sample; a window without takes it.
    for k in (1, 2):
        e.tick(k * S)
    o = e.tick(3 * S)[1]
    check("fb window 3 count", o["count"], ("good", 1.0))
    check("fb window 3 plain count", o["plain_count"], ("good", 4.0))
    o = e.tick(4 * S)[1]
    # the window is ticks 1 to 4: none of them holds a new sample
    check("fb window 4 count", o["count"], ("good", 0.0))
    check("fb window 4 mean", o["mean"], ("not_ready", None))
    check("fb window 4 plain count", o["plain_count"], ("good", 4.0))
    # the plain one: 1, 1 (good) and 7, 7 (uncertain): two good are enough
    check("fb window 4 plain mean", o["plain_mean"], ("good", 1.0))

    # a delay passes a fallback's value on as it took it: with no time
    g = {
        "period": "1s",
        "inputs": {"m": {"max_age": "none"}},
        "blocks": [
            f,
            {"id": "d", "type": "delay", "in": {"x": "f.y"}},
            {
                "id": "w",
                "type": "window",
                "in": {"x": "d.y"},
                "settings": {"window": "2s", "min_good": 0.5, "only_new": True},
                "out": {"count": "count"},
            },
        ],
    }
    e = Engine(g)
    e.tick(0)
    check("fb delay 1", e.tick(1 * S)[1]["count"], ("good", 0.0))
    e.write("m", "good", 2.0, 2 * S)
    e.tick(2 * S)
    check("fb delay 3", e.tick(3 * S)[1]["count"], ("good", 1.0))


def test_amendment_six():
    """Amendment 6: the whole text, read cold."""

    def window_need(min_good, window="10s"):
        st = {"window": window}
        if min_good is not None:
            st["min_good"] = min_good
        g = {"period": "1s", "blocks": [{"id": "w", "type": "window", "in": {"x": 1}, "settings": st}]}
        return Engine(g)._blocks["w"].need

    # rule 6.3: worked exactly from the decimal as it is written, with no
    # tolerance
    check("need 0.7 of 10", window_need(0.7), 7)
    check("need 0.7000000001 of 10", window_need(0.7000000001), 8)
    check("need 0.6999999999 of 10", window_need(0.6999999999), 7)
    # 0.1 as a double is a little more than a tenth; as written it is a tenth
    check("need 0.1 of 10", window_need(0.1), 1)
    check("need 0.1 of 30", window_need(0.1, "30s"), 3)
    check("need 0.3 of 10", window_need(0.3), 3)
    check("need 0.35 of 20", window_need(0.35, "20s"), 7)
    check("need 1 of 10", window_need(1), 10)
    check("need default", window_need(None), 10)
    check("need 1e-12 of 10", window_need(1e-12), 1)
    # and in what a window gives: ten good samples but for three uncertain
    # ones is seven good: good at 0.7, uncertain at 0.7000000001
    for mg, want in ((0.7, "good"), (0.7000000001, "uncertain")):
        got = run_seq(
            {"type": "window", "in": {"x": "x"}, "settings": {"window": "10s", "min_good": mg}},
            "number",
            [("uncertain", 1.0)] * 3 + [("good", 1.0)] * 7,
            "mean",
        )
        check("need in a window %r" % mg, got[9][0], want)

    # a low-pass's default settle is three of tau, which is written as a
    # length: exact. tau of 1.000000001 s at a period of 3 s is
    # 1.000000001 ticks: two.
    def lowpass_settle(tau, period):
        g = {"period": period, "blocks": [{"id": "b", "type": "lowpass", "in": {"x": 1}, "settings": {"tau": tau}}]}
        return Engine(g)._blocks["b"].settle

    check("lowpass settle exact", lowpass_settle("1s", "3s"), 1)
    check("lowpass settle just over", lowpass_settle("1000000001ns", "3s"), 2)
    check("lowpass settle a fraction of a ns over", lowpass_settle("1.0000000001s", "3s"), 2)
    check("lowpass settle 2.5", lowpass_settle("2500ms", "1s"), 8)

    # rule 7.8.6: a named model's settle is not exact: with r three of the
    # constant over the period, the least whole number not less than
    # r - 1e-9. r of 1.0000000005 is one tick, and of 1.000000002 two.
    def model_settle(tau, period):
        blk = {"id": "b", "type": "first_order_process", "in": {"u": 1}, "settings": {"tau": tau}}
        return Engine({"period": period, "blocks": [blk]})._blocks["b"].settle

    check("model settle exact", model_settle("1s", "3s"), 1)
    check("model settle within 1e-9", model_settle("1.0000000005s", "3s"), 1)
    check("model settle past 1e-9", model_settle("1.000000002s", "3s"), 2)
    check("model settle 2.5", model_settle("2500ms", "1s"), 8)

    # rule 6.2: every length the engine keeps fits in 64 bits, signed
    big = "%dns" % (2**63)
    fits = "%dns" % (2**63 - 1)
    refused("width: period", {"period": big})
    Engine({"period": fits})
    refused("width: max_age", {"period": "1s", "inputs": {"x": {"max_age": big}}})
    Engine({"period": "1s", "inputs": {"x": {"max_age": fits}}})
    refused("width: max_ahead", {"period": "1s", "inputs": {"x": {"max_age": "none", "max_ahead": big}}})
    refused(
        "width: a counted length",
        {
            "period": "1ns",
            "blocks": [
                {"id": "h", "type": "hysteresis", "in": {"x": 1}, "settings": {"rise": 1, "fall": 0}},
                {"id": "t", "type": "since_true", "in": {"x": "h.y"}, "settings": {"time": big, "on_bad": "unknown"}},
            ],
        },
    )
    # an age is the true difference, however far apart the two times are
    e = Engine(echo_graph("%dns" % (2**63 - 1)))
    e.write("x", "good", 1.0, -(2**63))
    check("width: an age of nearly 2^64", e.tick(2**63 - 2)[1]["y"], ("bad", None))
    e = Engine(echo_graph("none"))
    e.write("x", "good", 1.0, -(2**63))
    check("width: no maximum age", e.tick(2**63 - 2)[1]["y"], ("good", 1.0))

    # rule 6.11: a call that would run a tick whose time does not fit is
    # refused, and changes nothing. Period 1 s, tick 0 at 0: at a now of
    # 2^63 - 1 ns the last tick due is at 9,223,372,037 s, past 2^63 ns.
    g = integ_graph(max_catch_up=3)
    e = Engine(g)
    e.write("x", "good", 1.0, 0)
    e.tick(0)
    before = dict(e.info)
    e.write("x", "good", 9.0, 5 * S)  # far ahead of a call at 1 s: it would be thrown away
    raises("width: a tick's time", lambda: e.tick(2**63 - 1))
    check("width: refused, nothing changed", e.info, before)
    # the call was refused: the write still waits, and an earlier now is no error
    ran, o = e.tick(5 * S)
    check("width: after the refusal", e.info, info(True, 5, 5 * S, skipped=4))
    check("width: after the refusal y", o["y"], ("good", 10.0))
    # the last now for which the tick's time fits: 9,223,372,036 s is due
    # from half a second before it
    e = Engine(g)
    e.tick(0)
    ran, o = e.tick(9223372036 * S)
    check("width: the last tick that fits", e.info, info(True, 9223372036, 9223372036 * S, skipped=9223372035))
    # the next tick, at 9,223,372,037 s, is due from 0.5 s before it, and
    # its time does not fit: until then a call runs no tick, and from then
    # on it is refused
    check("width: nothing more is due", e.tick(9223372036 * S + 499999999), (0, None))
    raises("width: the next tick is due and does not fit", lambda: e.tick(9223372036 * S + 500000000))
    raises("width: nor at the end of the clock", lambda: e.tick(2**63 - 1))
    # a tick's number: at a period of 1 ns a rebase with a length of
    # 2^63 - 1 runs tick 2^63 - 1; the next tick would be numbered 2^63
    g = {"period": "1ns", "blocks": [{"id": "i", "type": "integrate", "in": {"x": 1}, "out": {"elapsed": "elapsed"}}]}
    e = Engine(g)
    e.tick(0)
    e.rebase(2**63 - 1)
    e.tick(0)
    check("width: the last number that fits", e.info, info(True, 2**63 - 1, 0, skipped=2**63 - 2))
    before = dict(e.info)
    raises("width: a tick's number", lambda: e.tick(1))
    check("width: number refused, nothing changed", e.info, before)
    e.rebase(1)
    raises("width: a tick's number, at a rebase", lambda: e.tick(0))
    raises("width: a tick's number, at a rebase with no length", lambda: (e.rebase(), e.tick(0)))
    e = Engine(g)
    e.tick(0)
    e.rebase(2**63 - 1)
    e.tick(0)
    e.reset()
    check("width: after a reset", e.tick(0)[0], 1)
    e = Engine(g)
    e.tick(0)
    e.tick(1)
    e.rebase(2**63 - 1)
    raises("width: a rebase's length takes the number past", lambda: e.tick(0))

    # rule 7.2.1: an initial value stands in until the first rebase and
    # not after it
    e = Engine(echo_graph("none", initial=5))
    check("initial 0", e.tick(0)[1]["y"], ("uncertain", 5.0))
    check("initial 1", e.tick(1 * S)[1]["y"], ("uncertain", 5.0))
    saved = e.save()
    e.rebase()
    check("initial after a rebase", e.tick(0)[1]["y"], ("not_ready", None))
    check("initial after a rebase, next", e.tick(1 * S)[1]["y"], ("not_ready", None))
    e.write("x", "good", 2.0, 2 * S)
    check("initial after a rebase, written", e.tick(2 * S)[1]["y"], ("good", 4.0 / 2))
    # a rebase with a length is a rebase
    e = Engine(echo_graph("none", initial=5))
    e.tick(0)
    e.rebase(0)
    check("initial after rebase(0)", e.tick(0)[1]["y"], ("not_ready", None))
    # a restore is followed by one
    e = Engine(echo_graph("none", initial=5))
    e.tick(0)
    e.restore(saved)
    check("initial after a restore", e.tick(0)[1]["y"], ("not_ready", None))
    # a reset brings it back; a stall is no rebase; and a rebase before any
    # tick is none either
    e.reset()
    check("initial after a reset", e.tick(0)[1]["y"], ("uncertain", 5.0))
    e = Engine(echo_graph("none", initial=5, **{}))
    e.tick(0)
    check("initial across a stall", e.tick(1000 * S)[1]["y"], ("uncertain", 5.0))
    e = Engine(echo_graph("none", initial=5))
    e.rebase()
    check("initial, rebase before any tick", e.tick(0)[1]["y"], ("uncertain", 5.0))
    # with a maximum age it is not_ready, and bad once the graph has run
    # for longer than that since the rebase's tick
    e = Engine(echo_graph("2s", initial=5))
    check("initial aged 0", e.tick(0)[1]["y"], ("uncertain", 5.0))
    e.rebase()
    check("initial aged, rebase", e.tick(100 * S)[1]["y"], ("not_ready", None))
    check("initial aged, 2 s on", e.tick(102 * S)[1]["y"], ("not_ready", None))
    check("initial aged, 3 s on", e.tick(103 * S)[1]["y"], ("bad", None))

    # rule 9.2: a block id, and a name a block's settings give, is not
    # empty and holds no dot
    def one(bid="b", **more):
        blk = {"id": bid, "type": "formula", "in": {"a": 1}, "settings": {"expr": "a"}}
        blk.update(more)
        return {"period": "1s", "inputs": {"m": {"max_age": "none"}}, "blocks": [blk]}

    Engine(one())
    refused("names: an empty block id", one(""))
    refused("names: a block id with a dot", one("a.b"))
    refused("names: a signal with no name", one(**{"in": {"a": ""}}))
    # ... also where an input from outside has that name
    g = one(**{"in": {"a": ""}})
    g["inputs"][""] = {"max_age": "none"}
    refused("names: a signal with no name that exists", g)
    # the name of an input and a published name are not empty (rule 9.2);
    # they may hold a dot, where that is not <block id>.<port>
    g = one()
    g["inputs"][""] = {"max_age": "none"}
    refused("names: an input with no name", g)
    refused("names: a published name that is empty", one(out={"y": ""}))
    g = one(out={"y": "plant.out"})
    g["inputs"]["room.temp"] = {"max_age": "none"}
    Engine(g)
    refused("names: a published name of the form id.port", one(out={"y": "b.y"}))

    def lin(**names):
        st = {"A": [[0, 1], [0, 0]], "B": [[0], [1]], "C": [[1, 0]]}
        st.update(names)
        ins = {(names.get("inputs") or ["u"])[0]: 0}
        return {"period": "1s", "blocks": [{"id": "b", "type": "linear", "in": ins, "settings": st}]}

    Engine(lin(states=["pos", "vel"], inputs=["force"], outputs=["where"]))
    refused("names: a state with a dot", lin(states=["pos", "v.el"]))
    refused("names: an empty state", lin(states=["pos", ""]))
    refused("names: an output with a dot", lin(outputs=["o.ut"]))
    refused("names: an empty output", lin(outputs=[""]))
    refused("names: an input with a dot", lin(inputs=["f.orce"]))
    refused("names: an empty input", lin(inputs=[""]))
    try:
        est_engine({"measure": {"z.1": {"of": "y", "r": 1}}}, ins={"u": 0, "z.1": "z"})
        check("names: a measurement port with a dot", "accepted", "refused")
    except CompileError:
        check("names: a measurement port with a dot", True, True)
    try:
        est_engine({"measure": {"": {"of": "y", "r": 1}}}, ins={"u": 0, "": "z"})
        check("names: an empty measurement port", "accepted", "refused")
    except CompileError:
        check("names: an empty measurement port", True, True)

    # rule 7.9.8: each of an estimator's outputs has a name of its own
    def est_bad(label, settings=None, **kw):
        try:
            est_engine(settings, **kw)
        except CompileError:
            check(label, True, True)
            return
        check(label, "accepted", "refused")

    twin = {"type": "linear", "A": [[0, 0], [0, 0]], "B": [[1], [1]], "C": [[1, 0]], "states": ["x", "sigma_x"]}
    est_bad("est names: x and sigma_x", {"q": {"x": 1, "sigma_x": 1}, "p0": {"x": 1, "sigma_x": 1}}, model=twin)
    twin = dict(twin, states=["x", "nis_z"])
    est_bad("est names: a state and nis_z", {"q": {"x": 1, "nis_z": 1}, "p0": {"x": 1, "nis_z": 1}}, model=twin)
    twin = dict(twin, states=["x", "v"])
    est_engine({"q": {"x": 1, "v": 1}, "p0": {"x": 1, "v": 1}}, model=twin)

    # Appendix A, ranges
    est_bad("range: sigma_max below zero", {"sigma_max": {"x0": -1}})
    est_engine({"sigma_max": {"x0": 0}})
    est_bad("range: no measurement", {"measure": {}}, ins={"u": 0})
    est_bad("range: over", {"consistency": {"over": 2**31, "limit": 2}})
    est_engine({"consistency": {"over": 2**31 - 1, "limit": 2}})
    est_bad("range: max_refused", {"gate": 3, "max_refused": 2**31})
    est_engine({"gate": 3, "max_refused": 2**31 - 1})
    refused(
        "range: ticks",
        {"period": "1s", "blocks": [{"id": "d", "type": "delay", "in": {"x": 1}, "settings": {"ticks": 2**31}}]},
    )
    refused("range: max_catch_up", {"period": "1s", "max_catch_up": 2**31})
    Engine({"period": "1s", "max_catch_up": 2**31 - 1})
    refused("range: max_catch_up 0", {"period": "1s", "max_catch_up": 0})
    refused("range: max_waiting", {"period": "1s", "max_waiting": 2**31})
    Engine({"period": "1s", "max_waiting": 2**31 - 1})

    # rule 3.6: a statistic is a plain sum in double arithmetic: the mean
    # of two samples of 1e308 passes through a value that is not finite
    blk = {"type": "window", "in": {"x": "x"}, "settings": {"window": "2s"}}
    seq = [("good", 1e308), ("good", 1e308)]
    check("3.6 mean", run_seq(blk, "number", seq, "mean")[1], ("bad", None))
    check("3.6 max", run_seq(blk, "number", seq, "max")[1], ("good", 1e308))
    check("3.6 spread", run_seq(blk, "number", seq, "spread")[1], ("good", 0.0))

    # rule 3.7: inputs are counted by port: one signal on two ports is two,
    # so the formula gives the time of the tick, and with only_new every
    # tick is a new sample
    g = {
        "period": "1s",
        "inputs": {"m": {"max_age": "none"}},
        "blocks": [
            {"id": "one", "type": "formula", "in": {"a": "m"}, "settings": {"expr": "a + a"}},
            {"id": "two", "type": "formula", "in": {"a": "m", "b": "m"}, "settings": {"expr": "a + b"}},
        ],
    }
    for bid in ("one", "two"):
        g["blocks"].append(
            {
                "id": "w_" + bid,
                "type": "window",
                "in": {"x": bid + ".y"},
                "settings": {"window": "3s", "min_good": 0.3, "only_new": True},
                "out": {"count": bid},
            }
        )
    e = Engine(g)
    e.write("m", "good", 1.0, 0)
    e.tick(0)
    e.tick(1 * S)
    o = e.tick(2 * S)[1]
    check("3.7 one port", o["one"], ("good", 1.0))
    check("3.7 two ports", o["two"], ("good", 3.0))

    # rule 7.8.5: a model block's outputs are judged together: a direct
    # input that is uncertain makes every output so, one that reads no
    # input among them
    blk = {
        "id": "b",
        "type": "linear",
        "in": {"u": "x"},
        "settings": {"A": [[0]], "B": [[0]], "C": [[1], [1]], "D": [[0], [2]], "outputs": ["clean", "fed"]},
        "out": {"clean": "clean", "fed": "fed"},
    }
    e = Engine({"period": "1s", "inputs": {"x": {"max_age": "none"}}, "blocks": [blk]})
    e.write("x", "uncertain", 1.0, 0)
    o = e.tick(0)[1]
    check("7.8.5 fed", o["fed"], ("uncertain", 2.0))
    check("7.8.5 clean", o["clean"], ("uncertain", 0.0))


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
                    "measure": {"z": {"of": "y", "r": 1}},
                    "consistency": "none",
                    "gate": 3,
                    "max_refused": 5,
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
    # a refused measurement makes its tick uncertain (rule 7.9.7)
    check("est x 2", o["x"], ("uncertain", 4.0))
    check("est sigma 2", o["sigma"], ("uncertain", math.sqrt(2.8)))
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
    # an uncertain measurement is not considered: the port gives no r_uncertain
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
    # the tick a gap of no known length runs is uncertain (rule 7.9.7)
    check("est rb x", o["x"], ("uncertain", 4.0 + gain))
    check("est rb sigma", o["sigma"], ("uncertain", math.sqrt(p4 + 4 + 1)))
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

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
    # d temp/dt = -(temp - 120)/100; RK4 on a linear equation multiplies
    # the distance from 120 by 1 + z + z^2/2 + z^3/6 + z^4/24, z = -0.01
    z = -0.01
    s = 1 + z + z**2 / 2 + z**3 / 6 + z**4 / 24
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


def two_masses(settle_a="2s", settle_b="2s"):
    def mass(bid, power, ambient, settle):
        st = {"thermal_mass": 10, "heat_transfer": 1, "initial": 20}
        if settle is not None:
            st["settle"] = settle
        return {
            "id": bid,
            "type": "thermal_mass",
            "in": {"power": power, "ambient": ambient},
            "settings": st,
            "out": {"temp": bid},
        }

    return {
        "period": "1s",
        "max_catch_up": 3,
        "inputs": {"p": {"max_age": "none"}},
        "blocks": [mass("a", "p", "b.temp", settle_a), mass("b", 0, "a.temp", settle_b)],
    }


def test_model_loops():
    """Rule 7.8.8: a loop that holds a model is one block."""
    # two masses that each take the other's temperature. Nothing moves:
    # both start at 20 and the power is 0.
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
    refused("masses, one with no settle", two_masses("2s", None))
    refused("masses, neither with settle", two_masses(None, None))
    refused("masses, settles differ", two_masses("2s", "3s"))
    g = two_masses(None, None)
    g["blocks"][0]["in"]["ambient"] = 20
    Engine(g)  # no loop: b reads a, and a reads nothing of b
    g["blocks"][0]["in"]["ambient"] = "a.temp"
    refused("a model that reads its own output, with no settle", g)
    g["blocks"][0]["settings"]["settle"] = "0s"
    Engine(g)

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
        "in": {"u": 0, "z": "plant.y"},
        "settings": {
            "model": {"type": "state_space", "A": [[1]], "B": [0], "C": [1]},
            "q": {"x0": 1},
            "p0": {"x0": 4},
            "measure": {"z": {"of": "x0", "r": 1}},
        },
    }
    refused("loop: a model block and an estimator", {"period": "1s", "blocks": [plant("3s", "est.x0"), est]})
    # off the loop it is accepted, and so is an estimator on a loop with
    # no model block
    Engine({"period": "1s", "blocks": [plant("3s", 1), est]})
    est2 = dict(est, **{"in": {"u": 0, "z": "d.y"}})
    d = {"id": "d", "type": "delay", "in": {"x": "est.x0"}, "settings": {"initial": 0}}
    Engine({"period": "1s", "blocks": [est2, d]})

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
    # d temp/dt = (10 - (temp - 20)) / 10: towards 30, by s per step
    z = -0.1
    s = 1 + z + z**2 / 2 + z**3 / 6 + z**4 / 24
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
            "measure": {"z": {"of": "x0", "r": 1}},
        },
    }
    # round three: by p0 at every gap, none passed over among them
    for label, away, variance in (("none", (0,), 9.0), ("one", (2 * S,), 9.0), ("unknown", (), 9.0)):
        e = one_block(est)
        check("g2 est %s 0" % label, put(e, 0)["sigma_x0"], ("good", 2.0))
        e.rebase(*away)
        check("g2 est %s" % label, put(e, 0)["sigma_x0"], ("good", math.sqrt(variance)))

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

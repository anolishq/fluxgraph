#!/usr/bin/env python3
"""Check the C++ core where 64 bits end.

The vectors, compare.py and contract.py use clocks a host would have. The core's times are 64-bit whole
numbers, and rule 6.2 says an age is the true difference of two times however far apart, and rule 6.11 that a
call which would run a tick whose number or time does not fit is refused. Python's whole numbers have no end,
so the statement of the rules below is right at the edges without trying; the core has to be. This sets one
against the other on times, periods and lengths at and near the ends of the range, and is meant to be run
against a build with the undefined-behaviour sanitizer as well: a sum that wraps there stops the driver.

  FLUXGRAPH_V2_DRIVER=build/v2/tools/fluxgraph_v2_driver/fluxgraph_v2_driver python3 conformance/cpp/edges.py

What is checked:

1. Sections 6, 7.2 and 8 for one input, on random sequences of writes, calls, rebases, resets, saves and
   restores drawn from the ends of the range: which calls are refused, how many ticks run, the number and time
   of the last, gaps and how many ticks they passed over, writes thrown away and waiting, what the input reads
   as, and a total's `elapsed`, `missed` and `gaps`, whose counts pass 2^53 and reach 2^63.
2. The number of samples a window needs (rules 6.3 and 7.3.2), against exact fractions.
3. Lengths of time (rule 9.3) that are, and are just not, whole nanoseconds that fit, in every unit.
4. What the driver refuses because it cannot be handed to the core: a time that is not whole or does not fit.
5. Lengths that only scale a value (`per`, `tau`): the ratio and the rounding up are exact, at any period.

Exits 1 on the first difference, and prints it. Stdlib only.
"""

from __future__ import annotations

import math
import os
import random
import sys
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cpp import adapter  # noqa: E402

GOOD, UNCERTAIN, NOT_READY, BAD = "good", "uncertain", "not_ready", "bad"
LOW, HIGH = -(2**63), 2**63 - 1
MAX_CATCH_UP = 3


class Refused(Exception):
    pass


class Text:
    """Sections 6, 7.2 and 8 for one input read by a formula and a total, in whole numbers with no end."""

    def __init__(self, period, max_age, max_ahead):
        self.p, self.max_age, self.max_ahead = period, max_age, max_ahead
        self.reset()

    def reset(self):
        self.last = -1  # the number of the last tick run
        self.anchor = None  # (number, time) of tick 0, or of the last rebase's tick
        self.last_now, self.rebased = None, None
        self.stands, self.waiting, self.thrown = None, [], 0
        self.counts = {"elapsed": 0, "missed": 0, "gaps": 0}

    def write(self, state, value, at):
        if self.stands is not None and at < self.stands[0]:
            self.thrown += 1
        else:
            self.waiting.append((at, state, value))

    def rebase(self, away=None):
        if away is not None and away < 0:
            raise Refused
        self.stands, self.waiting = None, []
        if self.last < 0:
            return
        # 8.5: the length over the period, to the nearest whole number, a half rounding up
        self.rebased = (None if away is None else (2 * away + self.p) // (2 * self.p),)
        self.last_now = None

    def save(self):
        return self.last, dict(self.counts)

    def restore(self, saved):
        if saved[0] < 0:
            return self.reset()
        self.last, self.counts = saved[0], dict(saved[1])
        self.stands, self.waiting, self.rebased, self.last_now = None, [], (None,), None

    def tick(self, now):
        if self.last_now is not None and now < self.last_now:
            raise Refused
        gap, over = False, 0
        if self.last < 0:
            numbers, anchor = [0], (0, now)
        elif self.rebased is not None:
            (due,) = self.rebased
            gap, over = True, None if due is None else max(due, 1) - 1
            numbers = [self.last + 1 + (over or 0)]
            anchor = (numbers[0], now)
            if numbers[0] > HIGH:
                raise Refused  # 6.11: the number does not fit
        else:
            anchor = self.anchor
            # 6.6: every tick not yet run whose time is no more than half a period after now
            reach = anchor[0] + (2 * (now - anchor[1]) + self.p) // (2 * self.p)
            if reach > self.last and (reach > HIGH or anchor[1] + (reach - anchor[0]) * self.p > HIGH):
                raise Refused  # 6.11: the number or the time does not fit
            numbers = list(range(self.last + 1, min(reach, self.last + MAX_CATCH_UP) + 1))
            if reach - self.last > MAX_CATCH_UP:  # 6.9: a stall
                gap, over, numbers = True, reach - self.last - 1, [reach]
        self.last_now = now
        ahead = [w for w in self.waiting if w[0] - now > self.max_ahead]  # 6.8
        self.waiting = [w for w in self.waiting if w not in ahead]
        self.thrown += len(ahead)
        if not numbers:
            return 0, None, None
        self.anchor, self.rebased = anchor, None
        if gap:
            self.counts["gaps"] += 1
            self.counts["elapsed"] += over or 0
            self.counts["missed"] += over or 0
        for number in numbers:
            t = anchor[1] + (number - anchor[0]) * self.p
            y = self._read(t, max(t, now) if number == numbers[-1] else t)
            self.counts["elapsed"] += 1
            self.counts["missed"] += y[1] is None
        self.last = numbers[-1]
        info = {"gap": gap, "skipped": over, "tick": self.last, "time": t}
        info.update(thrown=self.thrown, waiting=len(self.waiting))
        self.thrown = 0
        return len(numbers), info, (y, dict(self.counts))

    def _read(self, t, limit):
        for write in [w for w in self.waiting if w[0] <= limit]:
            if self.stands is None or write[0] >= self.stands[0]:
                self.stands = write
        self.waiting = [w for w in self.waiting if w[0] > limit]
        if self.stands is None:  # 7.2.1
            return (BAD if self.max_age is not None and t - self.anchor[1] > self.max_age else NOT_READY, None)
        if self.stands[1] in (NOT_READY, BAD):
            return (self.stands[1], None)
        if self.max_age is not None and t - self.stands[0] > self.max_age:  # 7.2.4: the true difference
            return (BAD, None)
        return (self.stands[1], self.stands[2])


def graph(period, max_age, max_ahead):
    x = {"max_age": "none" if max_age is None else f"{max_age}ns"}
    if max_ahead is not None:
        x["max_ahead"] = f"{max_ahead}ns"
    return {
        "period": f"{period}ns",
        "max_catch_up": MAX_CATCH_UP,
        "inputs": {"x": x},
        "blocks": [
            {"id": "pass", "type": "formula", "in": {"x": "x"}, "settings": {"expr": "x"}, "out": {"y": "y"}},
            {
                "id": "seen",
                "type": "integrate",
                "in": {"x": "x"},
                "out": {"elapsed": "elapsed", "missed": "missed", "gaps": "gaps"},
            },
        ],
    }


def close(a, b):
    return abs(a - b) <= 1e-9 * max(1.0, abs(b))


def fail(what, *shown):
    print(f"FAILS: {what}")
    for label, value in shown:
        print(f"  {label}: {value}")
    sys.exit(1)


def clip(value):
    return max(LOW, min(HIGH, value))


def sequences(rng, period, runs, steps):
    """1: random sequences at the ends of the range."""
    half = period // 2 + period % 2
    tried = 0
    for run in range(runs):
        max_age = rng.choice([None, half, period, clip(3 * period), HIGH])
        max_ahead = rng.choice([None, half, HIGH])
        engine = adapter.Engine(graph(period, max_age, max_ahead))
        text = Text(period, max_age, period if max_ahead is None else max_ahead)
        now = rng.choice([LOW, LOW + 1, -period, -1, 0, 1, clip(HIGH - 3 * period), HIGH - period // 2, HIGH - 1, HIGH])
        saved, done = None, []
        for step in range(steps):
            r, tried = rng.random(), tried + 1
            if r < 0.4:
                at = rng.choice([LOW, LOW + 1, now - period, now - 1, now, now + 1, now + half, now + period])
                at = clip(rng.choice([at, at, now + period + 1, HIGH - 1, HIGH, rng.randint(LOW, HIGH)]))
                state = rng.choice([GOOD, GOOD, GOOD, UNCERTAIN, BAD, NOT_READY])
                value = float(step) if state in (GOOD, UNCERTAIN) else None
                done.append(("write", state, value, at))
                engine.write("x", state, value, at)
                text.write(state, value, at)
                continue
            if r < 0.5:
                away = rng.choice([None, 0, 1, half - 1, half, period, 3 * half, 5 * period, HIGH - 1, HIGH, -1])
                if away is not None and rng.random() < 0.3:
                    away = rng.randint(0, HIGH)
                away = None if away is None else min(away, HIGH)
                done.append(("rebase", away))
                results = []
                for one in (engine, text):
                    try:
                        one.rebase(away)
                        results.append("accepted")
                    except (adapter.Refused, Refused):
                        results.append("refused")
                if results[0] != results[1]:
                    fail("a rebase", ("period", period), ("steps", done), ("core", results[0]), ("text", results[1]))
                if results[0] == "accepted" and text.last >= 0 and rng.random() < 0.5:
                    now = rng.choice([LOW, -1, 0, now, HIGH - 1])  # the clock may be another clock altogether
                continue
            if r < 0.53:
                done.append(("reset",))
                engine.reset()
                text.reset()
                continue
            if r < 0.57:
                done.append(("save",))
                saved = (engine.save(), text.save())
                continue
            if r < 0.6 and saved is not None:
                done.append(("restore",))
                engine.restore(saved[0])
                text.restore(saved[1])
                continue
            move = rng.choice([0, 1, half - 1, half, half + 1, period - 1, period, period + 1, 3 * period, 9 * period])
            move = rng.choice([move, move, move, rng.randint(0, HIGH), HIGH - now if now >= 0 else HIGH, -1])
            called = clip(now + move)
            done.append(("tick", called))
            try:
                have = engine.tick(called)
                have = (have[0], engine.info, have[1])
            except adapter.Refused:
                have = "refused"
            try:
                want = text.tick(called)
            except Refused:
                want = "refused"
            if (have == "refused") != (want == "refused"):
                fail(
                    "a call", ("period", period), ("max_age", max_age), ("steps", done), ("core", have), ("text", want)
                )
            if have == "refused":
                continue
            now = called
            same = have[0] == want[0] and have[1] == want[1]
            if same and have[0]:
                (state, value), counts, out = want[2][0], want[2][1], have[2]
                seconds = period / 1e9
                same = (
                    (out["y"].state, out["y"].v) == (state, value)
                    and close(out["elapsed"].v, counts["elapsed"] * seconds)
                    and close(out["missed"].v, counts["missed"] * seconds)
                    and out["gaps"].v == float(counts["gaps"])
                )
            if not same:
                shown = have if not have[0] else (have[0], have[1], {k: tuple(v) for k, v in have[2].items()})
                fail(
                    "not what the text gives",
                    ("period", period),
                    ("max_age", max_age),
                    ("max_ahead", max_ahead),
                    ("steps", done),
                    ("core", shown),
                    ("text", want),
                )
    return tried


def last_number():
    """1, a case by hand: the last tick there is, at a period of 1 ns, and what follows it."""
    engine = adapter.Engine(graph(1, None, None))
    engine.tick(0)
    engine.rebase(HIGH - 1)  # HIGH - 1 ticks would have been due: the last of them is tick HIGH - 1
    ran, _ = engine.tick(5)
    if (ran, engine.info["tick"], engine.info["skipped"]) != (1, HIGH - 1, HIGH - 2):
        fail("the tick before the last", ("gave", (ran, engine.info)))
    ran, out = engine.tick(6)
    if (ran, engine.info["tick"]) != (1, HIGH) or not close(out["elapsed"].v, float(2**63) * 1e-9):
        fail("the last tick there is", ("gave", (ran, engine.info, out["elapsed"])))
    saved = engine.save()
    for what, again in (("call", lambda: None), ("rebase", engine.rebase), ("restore", lambda: engine.restore(saved))):
        again()
        for now in (7, 100, HIGH):
            try:
                engine.tick(now)
            except adapter.Refused:
                continue
            fail(f"a tick past the last was run, after a {what}", ("now", now), ("gave", engine.info))
    engine.reset()
    if engine.tick(-5)[0] != 1 or engine.info["tick"] != 0:
        fail("a reset after the last tick", ("gave", engine.info))
    return 12


def needed(rng):
    """2: the first tick on which a window fed good samples is good is the tick it has as many as it needs."""
    tried = 0
    pairs = [(0.7, 10), (0.7000000001, 10), (0.07, 100), (0.29, 100), (0.57, 100), (1e-10, 3), (1.0, 7), (0.3, 10)]
    pairs += [(1 / 3, 9), (0.1 + 0.2, 10), (0.9999999999999999, 40), (5e-324, 5), (0.5, 1)]
    pairs += [(rng.randint(1, 1000) / 1000, rng.randint(1, 200)) for _ in range(120)]
    pairs += [(rng.random() or 0.5, rng.randint(1, 60)) for _ in range(60)]
    for min_good, n in pairs:
        tried += 1
        want = max(1, math.ceil(Fraction(repr(min_good)) * n))  # 6.3: the shortest decimal that reads back
        blocks = [{"id": "w", "type": "window", "in": {"x": 1}, "settings": {"window": f"{n}s", "min_good": min_good}}]
        blocks[0]["out"] = {"mean": "mean"}
        engine = adapter.Engine({"period": "1s", "blocks": blocks})
        first = next(k for k in range(n + 1) if engine.tick(k * 10**9)[1]["mean"].v is not None)
        if first + 1 != want:
            fail(
                "the samples a window needs",
                ("min_good", repr(min_good)),
                ("ticks", n),
                ("core", first + 1),
                ("text", want),
            )
    return tried


def lengths():
    """3: a period is accepted exactly when it is a whole number of nanoseconds, more than zero, that fits."""
    units = {"ns": 1, "us": 10**3, "ms": 10**6, "s": 10**9, "m": 60 * 10**9, "h": 3600 * 10**9}
    written = ["1", "0.5", "0.000000001", "0.0000000005", "2.50", "9223372036854775807", "9223372036854775808"]
    written += ["9223372036.854775807", "9223372036.854775808", "153722867.28091293", "2562047.7880152305", "0.1"]
    written += ["153722867", "153722868", "2562047", "2562048", "0.00000000005", "0.000000000001", "1e3", "1.", ".5"]
    written += ["0", "0.0", "000001.000", "18446744073709551616", "0.00000000000027777777777777777777"]
    tried = 0
    for number in written:
        for unit, scale in units.items():
            tried += 1
            try:
                exact = Fraction(number) * scale if number.replace(".", "", 1).isdigit() and number[-1] != "." else None
                if number.startswith("."):
                    exact = None
            except ValueError:
                exact = None
            want = None if exact is None or exact.denominator != 1 or not 0 < exact <= HIGH else int(exact)
            try:
                engine = adapter.Engine({"period": number + unit, "blocks": []})
            except adapter.CompileError:
                if want is not None:
                    fail("a period was refused", ("period", number + unit), ("it is, in nanoseconds", want))
                continue
            if want is None:
                fail("a period was accepted", ("period", number + unit))
            engine.tick(0)
            if want <= HIGH // 2:  # the second tick is a period after the first
                engine.tick(want)
                if (engine.info["tick"], engine.info["time"]) != (1, want):
                    fail("a period is not what was written", ("period", number + unit), ("gave", engine.info))
    return tried


def refused(make):
    try:
        make()
    except (adapter.CompileError, adapter.Refused):
        return True
    return False


def limits():
    """3 and 4: a counted length past 64 bits, the engine's own limit on memory, and what the driver refuses
    because it cannot be handed to the core at all."""

    def total(max_missed):
        blocks = [{"id": "i", "type": "integrate", "in": {"x": 1}, "settings": {"max_missed": max_missed}}]
        return adapter.Engine({"period": "1ns", "blocks": blocks})

    def delay(ticks):
        blocks = [{"id": "d", "type": "delay", "in": {"x": 1}, "settings": {"ticks": ticks}}]
        return adapter.Engine({"period": "1s", "blocks": blocks})

    wanted = [
        ("a max_missed of the most 64 bits hold", lambda: total(f"{HIGH}ns"), False),
        ("a max_missed one past it", lambda: total(f"{HIGH + 1}ns"), True),
        ("a max_missed of 2^64 - 1", lambda: total(f"{2**64 - 1}ns"), True),
        ("a max_missed of 2^64", lambda: total(f"{2**64}ns"), True),
        ("a delay of 2^24 ticks", lambda: delay(2**24), False),
        ("a delay of 2^24 + 1 ticks", lambda: delay(2**24 + 1), True),
        ("a delay of 2^31 ticks", lambda: delay(2**31), True),
    ]
    engine = adapter.Engine(graph(10**9, None, None))
    driver = adapter.start()
    for line in (
        f"tick {engine._id} {HIGH + 1}",
        f"tick {engine._id} {LOW - 1}",
        f"tick {engine._id} 0.5",
        f"tick {engine._id} 1e3",
        f"write {engine._id} =x good n 1.0 {HIGH + 1}",
        f"write {engine._id} =x good n 1.0 1.5",
        f"rebase {engine._id} {HIGH + 1}",
        f"rebase {engine._id} 0.5",
    ):
        wanted.append((f"the line {line!r}", lambda line=line: driver.ask(line), True))
    for what, make, want in wanted:
        if refused(make) != want:
            fail(f"{what} was {'accepted' if want else 'refused'}")
    if engine.tick(HIGH)[0] != 1 or engine.info["tick"] != 0:  # none of the refused lines changed anything
        fail("a refused line changed something", ("gave", engine.info))

    # Rule 8.2: a state of another graph, and one cut short, are refused and change nothing.
    one, other = adapter.Engine(graph(10**9, None, None)), adapter.Engine(graph(10**9, 10**9, None))
    for k in range(3):
        one.write("x", GOOD, 1.0, k * 10**9)
        one.tick(k * 10**9)
        other.tick(k * 10**9)
    saved = one.save()
    for what, state in (
        ("of another graph", other.save()),
        ("cut short", saved[:-2]),
        ("with more after it", saved + "00"),
    ):
        if not refused(lambda state=state: one.restore(state)):
            fail(f"a state {what} was taken back")
    ran, out = one.tick(3 * 10**9)
    if (ran, one.info["gap"], one.info["tick"], out["elapsed"].v) != (1, False, 3, 4.0):
        fail("a refused state changed something", ("gave", (ran, one.info, out)))
    one.restore(saved)
    ran, out = one.tick(0)
    if (ran, one.info["gap"], one.info["tick"], out["elapsed"].v) != (1, True, 3, 4.0):
        fail("a state was not taken back as it was saved", ("gave", (ran, one.info, out)))
    return len(wanted) + 5


def ratios():
    """5: a length that only scales a value is taken exactly (rule 6.3; Appendix A, `integrate` and `lowpass`)."""
    units = {"ns": 1, "us": 10**3, "ms": 10**6, "s": 10**9, "m": 60 * 10**9, "h": 3600 * 10**9}
    tried = 0
    # An integrate adds x times the ratio of the period to `per`, worked exactly and then taken as a double.
    pers = [
        "300ms",
        "0.3s",
        "0.1ns",
        "7s",
        "1h",
        "0.7m",
        "3ns",
        "0.000000001s",
        "9223372036854775807ns",
        "123456789.123456789us",
    ]
    pers += ["0.000000000000000000001ns", "99999999999999999999999999h", "1.1s", "0.9s", "49ns"]
    pairs = [(period, per) for period in (1, 3, 10**8, 10**9, 37 * 10**6, 2**53 + 1, 2**62 + 1, HIGH) for per in pers]
    # Ratios whose 54th bit is set and whose next ten are not, with more after: half-way but for what is far below.
    pairs += [(124909972, "865811861ns"), (916708312, "276467299ns"), (273471883, "230981431ns")]
    # And two that divide exactly, where what is far below is in the quotient itself.
    pairs += [(3277024805645671066, "0.00000000000000000001ns"), (341157100118808736, "0.00000000000000000001ns")]
    for period, per in pairs:
        tried += 1
        number, unit = next((per[: -len(u)], u) for u in ("ns", "us", "ms", "s", "m", "h") if per.endswith(u))
        want = float(Fraction(period) / (Fraction(number) * units[unit]))  # a Fraction's float is the nearest
        blocks = [{"id": "i", "type": "integrate", "in": {"x": 1}, "settings": {"per": per}, "out": {"y": "y"}}]
        y = adapter.Engine({"period": f"{period}ns", "blocks": blocks}).tick(0)[1]["y"]
        if (y.v if math.isfinite(want) and y.v is not None else None) != (want if math.isfinite(want) else None):
            fail("the ratio of the period to per", ("period", period), ("per", per), ("core", y), ("text", want))
    # A low-pass's settle is three time constants, rounded up to whole ticks, exactly: it is uncertain on that
    # many ticks after an uncertain input, and no more.
    for period, tau in (
        ("100ms", "0.7s"),
        ("1s", "0.3333333333s"),
        ("1s", "0.3333333334s"),
        ("1s", "1s"),
        ("3ns", "1ns"),
    ):
        tried += 1
        ticks = Fraction(adapter.seconds(period)).limit_denominator(10**12)
        ticks = math.ceil(
            3 * Fraction(tau[:-1] if tau.endswith("s") and not tau.endswith("ns") else tau[:-2] + "e-9") / ticks
        )
        blocks = [{"id": "f", "type": "lowpass", "in": {"x": "x"}, "settings": {"tau": tau}, "out": {"y": "y"}}]
        engine = adapter.Engine({"period": period, "inputs": {"x": {"max_age": "none"}}, "blocks": blocks})
        step = round(adapter.seconds(period) * 10**9)
        engine.write("x", UNCERTAIN, 1.0, 0)
        engine.tick(0)
        engine.write("x", GOOD, 1.0, step)
        first = next(k for k in range(1, ticks + 3) if engine.tick(k * step)[1]["y"].state == GOOD)
        if first != ticks + 1:
            fail("a low-pass's settle", ("period", period), ("tau", tau), ("core", first - 1), ("text", ticks))
    return tried


def main():
    adapter.start()
    rng = random.Random(20261113)
    total = last_number() + needed(rng) + lengths() + limits() + ratios()
    for period in (1, 2, 3, 7, 10**9, 2**61, 2**62, 2**62 + 1, 2**63 - 2, 2**63 - 1):
        tried = sequences(rng, period, runs=60, steps=120)
        total += tried
        print(f"period {period} ns: {tried} steps")
    print(f"{total} checks: ALL HOLD")


if __name__ == "__main__":
    main()

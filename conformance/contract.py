#!/usr/bin/env python3
"""Check the host contract by trying every short sequence of writes and calls.

The vectors pin down cases someone thought of, and compare.py sets two
readings against each other, so a fault they share passes both. This checks
sections 6, 7.2 and 8 of the proposal against statements of what a host is
promised, on every sequence of a few steps taken from a small set: writes
stamped from two periods behind the host's clock to past `max_ahead`; calls
that are repeated, early, on time, late, late enough to catch up and late
enough to stall; a call with an earlier time; rebases with and without a
length; resets, saves and restores. Times are on a grid of quarter periods,
at a period of 1 s on a clock near 1.7e9 s and at 100 ms on a clock that
starts below zero.

  python3 conformance/contract.py              the reference
  python3 conformance/contract.py --second     the second implementation
  python3 conformance/contract.py --depth 5    longer sequences (default 4)

What is checked:

1. A host that calls once a period, each call within half a period of its
   tick, loses nothing: every call runs one tick, the tick reads the sample
   last written, and a sample is new at one tick and no more.
2. Every sequence gives what `Contract` below gives, with and without an
   initial value on the input: a short statement of
   rules 6.5 to 6.11, 7.2 and 8.1 to 8.6 for one input, written from the
   text. The graph publishes the input as it is read, how many ticks held
   a new sample, and a total's `elapsed`, `missed` and `gaps`, so the count
   takes in the ticks whose outputs a call does not give.
3. An input not written again stops being usable within a bound: no tick
   later than `max_ahead` and the maximum age after the call that followed
   its last write reads it as usable, whatever time the write carried.
   After a reset, a restore or a rebase it is not usable until written.
4. A refused write or call changes nothing: with one of each kind tried
   before every step, a sequence gives what it gives without them.
5. A reset gives what a new engine gives. A restore gives what a rebase
   with no length gives, and a restore of a state saved before any tick
   what a reset gives, whatever was done between the save and the restore.
   The last `rebase` before a call is the one that counts, and a reset
   after a `rebase` is a reset.
6. What a graph gives does not depend on when the host calls, short of a
   stall: with every sample stamped on a tick and written beforehand, any
   pattern of calls that ends at one time gives one answer.

Exits 1 on the first sequence that fails any of them, and prints it.
Stdlib only.

What this cannot see. Each check holds to the depth it was run at and no
further: a state that takes more steps to reach is not reached, and at the
default depth the fifth check saves at tick 0 or 1 only. Times are on the
quarter-period grid. The graph has one input, a number, with the default
`max_ahead` (but for check 6) and the default `max_waiting`, and its
window is one tick long: a value that is not finite, a boolean input,
two inputs a tick apart, a full queue of waiting writes, a refusal at
compile, a call or a rebase past 64 bits, a state saved from another
graph, and what any other block does at a gap are all left to the vectors.
`mutate.py --contract` says which breakages of sections 6, 7.2 and 8 this
notices by itself.
"""

from __future__ import annotations

import argparse
import itertools
import sys

import reference

impl = reference  # the implementation under test; --second swaps it

GOOD, UNCERTAIN, NOT_READY, BAD = "good", "uncertain", "not_ready", "bad"
MAX_CATCH_UP = 2
NAMES = ("y", "taken", "elapsed", "missed", "gaps")


def graph(period, max_age, max_ahead=None, max_catch_up=MAX_CATCH_UP, initial=None):
    x = {"max_age": "none" if max_age is None else f"{max_age}ns"}
    if initial is not None:
        x["initial"] = initial
    if max_ahead is not None:
        x["max_ahead"] = f"{max_ahead}ns"
    length = f"{period}ns"
    return {
        "period": length,
        "max_catch_up": max_catch_up,
        "inputs": {"x": x},
        "blocks": [
            {"id": "pass", "type": "formula", "in": {"x": "x"}, "settings": {"expr": "x"}, "out": {"y": "y"}},
            {
                "id": "new",
                "type": "window",
                "in": {"x": "x"},
                "settings": {"window": length, "only_new": True, "min_good": 1},
            },
            {
                "id": "total",
                "type": "integrate",
                "in": {"x": "new.count"},
                "settings": {"per": length},
                "out": {"y": "taken"},
            },
            {
                "id": "seen",
                "type": "integrate",
                "in": {"x": "x"},
                "out": {"elapsed": "elapsed", "missed": "missed", "gaps": "gaps"},
            },
        ],
    }


class Refused(Exception):
    pass


class Contract:
    """Sections 6, 7.2 and 8 for the graph above, from the text and not from either reading."""

    def __init__(self, period, max_age, max_ahead=None, max_catch_up=MAX_CATCH_UP, initial=None):
        self.p, self.max_age, self.max_catch_up, self.initial = period, max_age, max_catch_up, initial
        self.max_ahead = period if max_ahead is None else max_ahead
        self.reset()

    def reset(self):  # 8.1
        self.k = 0  # the number of the next tick
        self.zero = self.since = self.last_now = None
        self.stands, self.waiting, self.written = None, [], 0
        self.rebased = None  # (ticks passed over, or None,) between a rebase and its call
        self.first_run = True  # no rebase since the engine was made or reset (7.2.1)
        self.thrown = 0
        self.taken_at, self.counts = None, {"taken": 0, "elapsed": 0, "missed": 0, "gaps": 0}
        self.info = None

    def write(self, name, state, value=None, at=None):
        if name != "x" or state not in (GOOD, UNCERTAIN, NOT_READY, BAD):  # 6.11
            raise Refused
        if isinstance(at, bool) or not isinstance(at, int) or not -(2**63) <= at < 2**63:
            raise Refused
        usable = state in (GOOD, UNCERTAIN)
        if usable and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise Refused
        if self.stands is not None and at < self.stands[0]:  # 6.8: it can never stand
            self.thrown += 1
            return
        self.waiting.append((at, self.written, state, float(value) if usable else None))
        self.written += 1

    def rebase(self, away=None):  # 8.5
        if away is not None and (isinstance(away, bool) or not isinstance(away, int) or not 0 <= away < 2**63):
            raise Refused
        self.stands, self.waiting = None, []
        if self.k == 0:  # nothing has run: the writes are done with, and nothing else
            return
        over = None if away is None else max(0, (2 * away + self.p) // (2 * self.p) - 1)  # a half rounds up
        self.rebased, self.last_now = (over,), None

    def save(self):  # 8.2
        return self.k, dict(self.counts)

    def restore(self, saved):
        if saved[0] == 0:  # 8.3: saved before any tick had run
            return self.reset()
        self.k, self.counts = saved[0], dict(saved[1])
        self.stands, self.waiting = None, []
        self.rebased, self.last_now = (None,), None  # a restore puts back "nobody knows"

    def tick(self, now):
        if isinstance(now, bool) or not isinstance(now, int) or not -(2**63) <= now < 2**63:
            raise Refused
        if self.last_now is not None and now < self.last_now:  # 6.11
            raise Refused
        self.last_now = now
        ahead = [w for w in self.waiting if w[0] - now > self.max_ahead]  # 6.8: stamped ahead
        self.waiting = [w for w in self.waiting if w not in ahead]
        self.thrown += len(ahead)
        if self.zero is None:  # 6.5
            self.zero = self.since = now
        gap, over = False, 0
        if self.rebased is not None:  # 8.5
            (over,), self.rebased, gap, due = self.rebased, None, True, 1
            self.k += over or 0
            self.zero, self.since, self.taken_at = now - self.k * self.p, now, None
            self.first_run = False
        else:
            # 6.6: the ticks not yet run whose time is no more than half a period after now
            due = (2 * (now - self.zero) + self.p) // (2 * self.p) - self.k + 1
            if due <= 0:
                self.info = None
                return 0, None
            if due > self.max_catch_up:  # 6.9 and 8.4
                gap, over, due = True, due - 1, 1
                self.k += over
        if gap:  # 8.6: the total's counters
            self.counts["gaps"] += 1
            self.counts["elapsed"] += over or 0
            self.counts["missed"] += over or 0
        for i in range(due):
            y = self._run(now if i == due - 1 else None)
        self.info = {
            "gap": gap,
            "skipped": over,
            "tick": self.k - 1,
            "time": self.zero + (self.k - 1) * self.p,
            "thrown": self.thrown,
            "waiting": len(self.waiting),
        }
        self.thrown = 0
        seconds = self.p / 1e9
        out = {"y": y, "taken": (GOOD, float(self.counts["taken"])), "gaps": (GOOD, float(self.counts["gaps"]))}
        out.update({name: (GOOD, self.counts[name] * seconds) for name in ("elapsed", "missed")})
        return due, out

    def _run(self, now):
        """One tick. `now` is the call's, for the last tick of a call, and None for a catch-up tick."""
        t = self.zero + self.k * self.p
        limit = t if now is None else max(t, now)  # 6.8: which writes a tick may see
        for write in sorted((w for w in self.waiting if w[0] <= limit), key=lambda w: w[1]):
            if self.stands is None or write[0] >= self.stands[0]:
                self.stands = write
        self.waiting = [w for w in self.waiting if w[0] > limit]
        if self.stands is None:  # 7.2
            old = self.max_age is not None and t - self.since > self.max_age
            y = (BAD, None) if old else (NOT_READY, None)
            if self.initial is not None and self.first_run and not old:
                y = (UNCERTAIN, self.initial)  # usable, and no sample: it has no sample time
        elif self.stands[2] in (NOT_READY, BAD):
            y = (self.stands[2], None)
        elif self.max_age is not None and t - self.stands[0] > self.max_age:
            y = (BAD, None)
        else:
            y = (self.stands[2], self.stands[3])
            if self.taken_at is None or self.stands[0] > self.taken_at:  # 7.3.8: a new sample
                self.taken_at = self.stands[0]
                self.counts["taken"] += 1
        self.counts["elapsed"] += 1
        self.counts["missed"] += y[1] is None
        self.k += 1
        return y


# ---- playing a sequence

REFUSALS = (ValueError, KeyError, TypeError, Refused)

# Each is tried and has to be refused. `clock` is the time of the host's last call.
BAD_STEPS = (
    lambda e, clock: e.write("nobody", GOOD, 1.0, clock),
    lambda e, clock: e.write("x", GOOD, None, clock),
    lambda e, clock: e.write("x", GOOD, True, clock),
    lambda e, clock: e.write("x", "fine", 1.0, clock),
    lambda e, clock: e.write("x", GOOD, 1.0, clock + 0.5),
    lambda e, clock: e.write("x", GOOD, 1.0, 2**63),
    lambda e, clock: e.rebase(-1),
    lambda e, clock: e.rebase(1.5),
    lambda e, clock: e.tick(clock + 0.5),
    lambda e, clock: e.tick(2**63),
)


def play(engine, steps, period, base, pester=False):
    """-> what each step gave. A step is ("w", quarters from the clock, state), ("t", quarters to move the
    clock by), ("rebase", quarters or None), ("reset",), ("save",) or ("restore",). With `pester`, every
    kind of write and call that has to be refused is tried before each step."""
    quarter, clock, saved, gave = period // 4, base, None, []
    for i, step in enumerate(steps):
        value = float(len(steps) - i)  # counted from the end, so that two sequences with one tail write alike
        if pester:
            for bad in BAD_STEPS:
                try:
                    bad(engine, clock)
                except REFUSALS:
                    continue
                gave.append(("NOT REFUSED", BAD_STEPS.index(bad)))
        kind = step[0]
        try:
            if kind == "w":
                engine.write("x", step[2], value if step[2] in (GOOD, UNCERTAIN) else None, clock + step[1] * quarter)
                gave.append(None)
            elif kind == "t":
                ran, out = engine.tick(clock + step[1] * quarter)
                clock += step[1] * quarter
                info = engine.info
                shown = None if out is None else {n: (out[n][0], out[n][1]) for n in NAMES}
                gave.append((ran, None if info is None else dict(info), shown))
            elif kind == "rebase":
                engine.rebase(None if step[1] is None else step[1] * quarter)
                gave.append(None)
            elif kind == "reset":
                engine.reset()
                gave.append(None)
            elif kind == "save":
                saved = engine.save()
                gave.append(None)
            elif kind == "restore":
                if saved is not None:
                    engine.restore(saved)
                gave.append(None)
        except REFUSALS:
            gave.append("refused")
    return gave


def same(a, b, skip=()):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(k in skip or same(a[k], b[k], skip) for k in a)
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(same(x, y, skip) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= 1e-9 * max(1.0, abs(b))
    return type(a) is type(b) and a == b


def fail(what, steps, *shown):
    print(f"FAILS: {what}")
    print(f"  steps: {steps}")
    for label, value in shown:
        print(f"  {label}: {value}")
    sys.exit(1)


class Engines:
    """One engine per graph, reset between sequences: compiling is most of the cost. Check 5 holds reset
    to a new engine's answers."""

    def __init__(self):
        self.made = {}

    def get(self, *key):
        if key not in self.made:
            self.made[key] = impl.Engine(graph(*key))
        self.made[key].reset()
        return self.made[key]


# ---- the checks

WRITES = [("w", q, GOOD) for q in (-8, -1, 0, 1, 4, 5)] + [("w", 0, state) for state in (UNCERTAIN, NOT_READY, BAD)]
CALLS = [("t", q) for q in (-4, -1, 0, 2, 3, 4, 8, 12, 13)]
REBASES = [("rebase", q) for q in (None, 0, 5, 6, 12)]
OTHERS = [("reset",), ("save",), ("restore",)]
STEPS = WRITES + CALLS + REBASES + OTHERS
ON_TIME = ("t", 4)


def sequences(steps, depth):
    """Every sequence of `depth` steps that ends in a call: what follows the last call shows nothing."""
    for head in itertools.product(steps, repeat=depth - 1):
        for call in CALLS:
            yield (*head, call)


def regular_host(engines, period, base):
    """1: once a period, within half a period of the tick, with a sample in hand or none."""
    quarter, tried = period // 4, 0
    early_or_late = (
        -2,
        -1,
        0,
        1,
    )  # a tick exactly half a period after `now` is run; one half a period before is the next call's
    ages = (None, 0, 1, 3)  # no write, or a sample taken that many quarters before the call
    for max_age, age_choices in ((None, ages), (period // 2, (0,))):
        for offsets in itertools.product(early_or_late, repeat=3):
            for taken_ago in itertools.product(age_choices, repeat=4):
                engine, value, last, count, tried = engines.get(period, max_age), 0.0, None, 0, tried + 1
                for i, ago in enumerate(taken_ago):
                    now = base + i * period + (offsets[i - 1] * quarter if i else 0)
                    if ago is not None and (last is None or now - ago * quarter > last[0]):
                        value, count = value + 1.0, count + 1
                        last = (now - ago * quarter, value)
                        engine.write("x", GOOD, value, last[0])
                    ran, out = engine.tick(now)
                    want = (NOT_READY, None) if last is None else (GOOD, last[1])
                    have = None if out is None else ((out["y"][0], out["y"][1]), out["taken"][1])
                    if ran != 1 or engine.info["tick"] != i or have != (want, float(count)):
                        fail(
                            "a regular host lost a sample, a tick or a count",
                            f"max_age {max_age}, calls off by {offsets} quarters, samples {taken_ago} quarters old",
                            ("call", i),
                            ("ran", ran),
                            ("gave", have),
                            ("promised", (want, float(count))),
                        )
    return tried


def every_sequence(engines, period, base, depth, max_age, initial=None):
    """2 and 3: against Contract, and against the bound on how long a value outlives its last write."""
    tried, quarter = 0, period // 4
    for steps in sequences(STEPS, depth):
        tried += 1
        have = play(engines.get(period, max_age, None, MAX_CATCH_UP, initial), steps, period, base)
        want = play(Contract(period, max_age, initial=initial), steps, period, base)
        if not same(have, want):
            at = next(i for i, (h, w) in enumerate(zip(have, want)) if not same(h, w))
            fail("not what the text gives", steps, ("at step", at), ("gave", have[at]), ("the text", want[at]))
        clock, judged, fresh, saved = base, None, False, False  # judged: the call that followed the last write
        for step, gave in zip(steps, have):
            if step[0] == "w":
                fresh = True
            elif step[0] == "save":
                saved = True
            elif step[0] != "t":
                if step[0] != "restore" or saved:  # nothing written before it is left
                    judged, fresh = None, False
            elif gave != "refused":
                clock += step[1] * quarter
                if fresh:
                    judged, fresh = clock, False
                if gave[0] and gave[2]["y"][1] is not None and initial is None:
                    if judged is None or gave[1]["time"] > judged + period + max_age:
                        fail("a value outlived its bound", steps, ("at", step), ("gave", gave))
    return tried


def refusals(engines, period, base, depth, max_age):
    """4: a refused write or call changes nothing."""
    tried = 0
    for steps in sequences(STEPS, depth):
        tried += 1
        plain = play(engines.get(period, max_age), steps, period, base)
        pestered = play(engines.get(period, max_age), steps, period, base, pester=True)
        if not same(plain, pestered):
            fail("a refused step changed something, or was not refused", steps, ("plain", plain), ("with", pestered))
    return tried


def resets_and_restores(engines, period, base, depth, max_age):
    """5: each pair of sequences gives the same answers from the tail on. The two sides may have thrown
    away different writes before the tail, which a restore and a rebase do not set to zero (rule 6.8), and
    may start the tail at different times, so `thrown` and `time` are left out where they do."""
    plain = [("w", -1, GOOD), ("w", 0, GOOD), ("w", 1, GOOD), ("w", 0, BAD)] + [("t", q) for q in (0, 2, 4, 8, 12)]
    heads = [h for n in range(depth) for h in itertools.product(plain, repeat=n)]
    tails = [(*t, call) for n in range(depth) for t in itertools.product(plain, repeat=n) for call in plain[4:]]
    mid = (("w", 0, GOOD), ON_TIME, ("w", 1, GOOD))
    tried = 0

    def agree(what, left, right, tail, skip=(), new=False):
        nonlocal tried
        tried += 1
        a = play(engines.get(period, max_age), left + tail, period, base)[len(left) :]
        other = impl.Engine(graph(period, max_age)) if new else engines.get(period, max_age)
        b = play(other, right + tail, period, base)[len(right) :]
        if not same(a, b, skip):
            fail(what, f"{left + tail} against {right + tail}", ("one", a), ("the other", b))

    for head in heads:
        # the first call always runs tick 0; before it a rebase does nothing and a save is of no tick
        after = ("rebase", None) if any(step[0] == "t" for step in head) else ("reset",)
        for tail in tails:
            agree("a reset is not a new engine", (*head, ("reset",)), (), tail, skip=("time",), new=True)
            agree(
                "a reset after a rebase is not a reset",
                (*head, ("rebase", 8), ("reset",)),
                (),
                tail,
                skip=("time",),
                new=True,
            )
            agree("a restore is not a rebase", (*head, ("save",), ("restore",)), (*head, after), tail)
            agree(
                "a restore keeps something from after its save",
                (*head, ("save",), *mid, ("restore",)),
                (*head, after),
                tail,
                skip=("thrown", "time"),
            )
            for length in (None, 5, 12):
                agree(
                    "an earlier rebase counted",
                    (*head, ("rebase", 12 if length is None else None), ("w", 0, GOOD), ("rebase", length)),
                    (*head, ("rebase", length)),
                    tail,
                )
            agree(
                "a save between a rebase and its call is not as one before it",
                (*head, ("rebase", 12), ("save",), *mid, ("restore",)),
                (*head, after),
                tail,
                skip=("thrown", "time"),
            )
    return tried


def call_times(period, base):
    """6: samples stamped on ticks and written beforehand; every pattern of calls short of a stall."""
    ticks, quarter, tried = 3, period // 4, 0
    long = 100 * period

    def patterns(left):
        if left == 0:
            yield ()
        for move in (1, 2, 3, 4, 5, 6, 8):
            if move <= left:
                for rest in patterns(left - move):
                    yield (move, *rest)

    engine = impl.Engine(graph(period, None, max_ahead=long, max_catch_up=100))
    for stamped in itertools.product((False, True), repeat=ticks + 1):
        first = None
        for moves in patterns(4 * ticks):
            tried += 1
            engine.reset()
            for i, there in enumerate(stamped):
                if there:
                    engine.write("x", GOOD, float(i + 1), base + i * period)
            now, last = base, None
            for move in (0, *moves):
                now += move * quarter
                ran, out = engine.tick(now)
                if ran:
                    last = (engine.info["tick"], {n: (out[n][0], out[n][1]) for n in NAMES})
            first = first or (moves, last)
            if not same(last, first[1]):
                fail(
                    "what a graph gives depends on when it was called",
                    f"samples on ticks {[i for i, s in enumerate(stamped) if s]}",
                    (f"calls {first[0]} quarters apart", first[1]),
                    (f"calls {moves} quarters apart", last),
                )
    return tried


def main():
    global impl
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--second", action="store_true", help="check the second implementation")
    parser.add_argument("--depth", type=int, default=4, help="steps in a sequence (default 4)")
    args = parser.parse_args()
    if args.second:
        from second import adapter

        impl = adapter
    total = 0
    for period, base in ((10**9, 1_700_000_000 * 10**9 + 123), (10**8, -(10**8) - 1)):
        engines, max_age = Engines(), 2 * period
        counts = {
            "a regular host": regular_host(engines, period, base),
            "every sequence": every_sequence(engines, period, base, args.depth, max_age),
            "with an initial value": every_sequence(engines, period, base, args.depth, max_age, 7.0),
            "refusals": refusals(engines, period, base, args.depth - 1, max_age),
            "resets and restores": resets_and_restores(engines, period, base, args.depth - 2, max_age),
            "call times": call_times(period, base),
        }
        total += sum(counts.values())
        print(f"period {period} ns, clock from {base}: " + ", ".join(f"{name} {n}" for name, n in counts.items()))
    print(f"{total} sequences: ALL HOLD")


if __name__ == "__main__":
    main()

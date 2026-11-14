<!-- markdownlint-disable MD029 -- entries keep one numbering -->
# Assumptions made in bringing `impl.py` up to Amendment 1

Every place where the amended sections (3.7, 6, 7.2, 8, 9) did not say what
to do, could be read two ways, or disagreed with another part of the
document, and what `impl.py` does. Ordered with the ones most likely to make
two honest implementations disagree first. Rule numbers are those of the
amended `proposal.md`.

1. **Does an estimator forget the sample time it last *used* at a rebase?**
   Rule 8.5: "every sample time a block remembers is forgotten: a window
   with `only_new` takes the next usable sample, and an estimator considers
   the next measurement, as if it had seen none." The closing paragraph of
   section 8: "Nothing else changes at a gap. An estimator keeps its state
   and its counts". An estimator remembers two sample times per port: the
   one last *considered* (rule 7.9.3) and the one last *used* (rule 7.9.6,
   `since_<port>`). The example in 8.5 speaks only of the first.
   *Chosen:* "every" is taken literally and both are forgotten. After a
   rebase `since_<port>` is `not_ready` "until one has been used" again.
   The other reading keeps the time last used, and `since_<port>` is then a
   difference between two clocks (it can be negative).

2. **Is a length that "only scales a value" held to whole nanoseconds?**
   Rule 6.2: "That is so ... for every length of time in a graph. A length
   that is not a whole number of nanoseconds is refused." Rule 9.3: "A
   number without a unit is refused, and so is a length that is not a whole
   number of nanoseconds." Rule 6.3: "A setting that only scales a value
   (`tau`, `per`) is not a time the engine keeps: it is written as a length
   and may be any length at all."
   *Chosen:* 6.3 wins for `tau` and `per`: `tau: 0.5ns` is accepted. Every
   other length (the period, `max_age`, and every counted length) must be a
   whole number of nanoseconds. The other reading refuses `0.5ns`
   everywhere.

3. **What "a whole number" is for a call's `now` and a write's time.** Rule
   6.11: "a write or a call whose time is not a whole number."
   *Chosen:* the time must be a Python `int` and not a `bool`. `2.0` and
   `2000000000.0` are refused although their value is whole; `None` is
   refused; a negative `int` is accepted (the text does not say a clock
   starts at or above zero, and after a rebase "the call may carry any
   `now`").

4. **`rebase` before any tick has run.** Rule 8.3 defines a rebase as "the
   first call after ... the host has said that its clock has stepped", and
   8.5 gives its tick a number "one more than that of the last tick run".
   With no tick run there is no such number. Rule 8.3 settles the like case
   for a restore only ("Restoring a state saved before any tick had run is
   a reset, and neither").
   *Chosen:* by analogy it is a reset: every write not yet taken up is done
   with, the next call runs tick 0 at its `now` and does not report a gap.
   Other readings: `rebase` does nothing at all there (waiting writes
   survive), or it is refused.

5. **When the waiting writes are done with at a rebase.** Rule 8.5 says
   "Before it runs: nothing stands on any input, and every write not yet
   taken up is done with. What the host writes after the restore, or after
   it said its clock had stepped, is taken up as usual." "Before it runs"
   puts the discarding at the call; the second sentence only holds if it
   happens at the `restore` or the `rebase`.
   *Chosen:* writes waiting are discarded at the moment of `restore()` or
   `rebase()`; what stands is cleared when the rebase's tick is about to
   run. Writes made between the two are kept, and are taken up or wait by
   their times against the new ticks. A second `rebase()` before the call
   discards what was written since the first. `restore()` then `rebase()`,
   or the reverse, makes one rebase.

6. **A write made later with an earlier time replaces what stands.** Rule
   6.8: "the one written last **stands** from this tick on", and "of two
   writes between two ticks, the later made is the one seen, even if it
   carries the earlier time". Nothing says what happens when the write
   taken up carries an earlier time than the write already standing from an
   earlier tick.
   *Chosen:* the literal rule: it stands, with its own (earlier) time as
   sample time and for its age. No write is ever refused or ignored for
   being older than what stands. (See "wrong" in the report: this lets an
   older sample displace a newer one.)

7. **An earlier-made write that is still ahead is discarded without ever
   being taken up.** The headline of rule 6.8 is "A write is taken up at
   the first tick whose time is at or after the write's", but its body says
   "it and every write made before it are done with", and a bullet says
   "any later write that is taken up does away with it".
   *Chosen:* the body. Write A stamped 10 s, then write B stamped 5 s: at
   the tick at 5 s B stands and A is gone; A is never seen. A write made
   *after* the one taken up, and still ahead, goes on waiting.

8. **What a stall does to "the graph has run for" (rule 7.2.1).** "The
   graph has run for `t` less the time of tick 0, or since the last rebase
   (section 8)." A stall is not mentioned. Before the amendment a gap of
   either kind restarted it.
   *Chosen:* a stall does not restart it; only a rebase (and a reset) does.

9. **Rule 6.5 against rules 8.4 and 8.5.** 6.5: "Tick `k` is at the time of
   tick 0 plus `k` periods." After a stall or a rebase the tick is numbered
   "one more than that of the last tick run" at another time.
   *Chosen:* 8.4 and 8.5. Tick times are kept as "a tick whose time is
   known, plus whole periods", re-anchored at every gap.

10. **How many ticks "would run" (rules 6.6, 6.9, 8.3).** *Chosen:* the
    count of ticks not yet run whose time is no more than half a period
    after `now`, compared exactly as `2·t ≤ 2·now + period` so that an odd
    period needs no rounding of its half. More than `max_catch_up` is a
    stall; exactly `max_catch_up` is not. A rebase is never also a stall,
    and neither is the first call (tick 0). At a stall the one tick's time
    is the time of the last due tick on the old grid, not `now`.

11. **What "the last call's" `now` is (rule 6.11).** *Chosen:* the `now` of
    the last call that was accepted, whether or not it ran a tick. A
    refused call does not count. The first call ever, the first after a
    reset, and the first after a `restore` or `rebase` may carry any `now`
    (rules 8.1, 8.3). After a rebase's tick, the rule applies again from
    that call's `now`.

12. **A call after a rebase always runs one tick**, even with the same
    `now` as the call before: rule 8.5 "At a rebase, one tick runs."

13. **A write with a state that is not one of the four.** Rule 6.11 does
    not list it. *Chosen:* refused, changes nothing.

14. **A usable write of a number that is not finite.** Rule 6.11 refuses "a
    usable write whose value is not of the input's type"; rule 7.2.3 says
    an input is "`bad`, if the value that stands is not finite", so such a
    value can stand.
    *Chosen:* `inf` and `nan` are of type number: the write is accepted and
    reads `bad`. A Python `int` is accepted for a number input (and held as
    a double); a `bool` is not; only a `bool` is accepted for a boolean.

15. **A value given with a `bad` or `not_ready` write.** Rule 6.7: "a value
    if the state is usable". *Chosen:* a value given with an unusable state
    is ignored, not refused. The time is still required and checked.

16. **No bound on a write's time.** Nothing refuses a write stamped before
    the last tick, before tick 0, or arbitrarily far ahead. *Chosen:* all
    are accepted. One stamped in the past is taken up at the next tick with
    the age it has. One stamped ahead waits for as long as it takes, and
    the number of writes waiting is not limited.

17. **Do values held in a `delay` lose their sample times at a rebase?**
    Rule 8.5: "every sample time a block remembers is forgotten". Rule 3.7
    uses "remembers" for "the sample time it last used"; a delay does not
    remember a time, it holds signals that carry one ("A `delay` output
    carries the sample time of what it gives").
    *Chosen:* a delay's held values keep their sample times through a
    rebase (the gap table's row for `delay` changes states only). After a
    rebase a delay therefore gives sample times of the old clock for
    `ticks` more ticks.

18. **An input's initial value after a rebase.** Rule 7.2.1 with 8.5 ("For
    rule 7.2.1 the graph has run since this tick").
    *Chosen:* literally: after a rebase, an input on which nothing stands
    is again `uncertain` with its initial value for `max_age` from the
    rebase's tick (or `not_ready` for that long if it declares none).

19. **What `restore` of a state "saved before any tick had run" does to
    writes waiting in the engine being restored into.** Rule 8.3: "is a
    reset, and neither"; rule 8.1: a reset means "every write not yet taken
    up is done with". *Chosen:* they are done with, as at any reset.

20. **What a saved state holds of the host interface.** Not said.
    *Chosen:* writes waiting are not saved (a restore discards them by rule
    8.5 in any case); what stands is saved but is cleared by the rebase
    that follows every restore, so it has no effect. A `rebase()` made
    before `save()` and not yet followed by a call is not recorded; the
    restore makes the next call a rebase anyway.

21. **What a call that ran no tick reports (rule 6.10).** "If none is due
    the call does nothing, and says it ran no tick." *Chosen:* it returns
    `(0, None)` and leaves `engine.info` as the last tick-running call left
    it. `engine.info` is `None` before the first call and after a reset.
    Such a call still counts as "the last call" for rule 6.11.

22. **Whether a refused call or write is told from an error in the
    engine.** *Chosen:* refusals raise `ValueError` or `KeyError`; all
    checks are made before anything is changed.

23. **The unit of a length of time the engine gives.** Rule 6.2 makes every
    time a whole number of nanoseconds; rule 7.9.6 (`since_<port>`:
    "the time from the sample time of the measurement last used to the
    tick") and Appendix A ("`missed` is in seconds", `slope` "per second")
    were not touched.
    *Chosen:* outputs stay doubles in seconds: `since_<port>` is the
    difference in nanoseconds divided by 10⁹. A sample time carried inside
    the graph is an `int` of nanoseconds.

24. **Comparisons that are still made in floating point.** Rule 6.2: "No
    comparison of times has a tolerance". Three places still divide a
    length by the period as doubles: the default `settle` ("three time
    constants, rounded up to whole ticks", rules 7.4.8 and 7.8.6, with the
    10⁻⁹ rounding of rule 6.3), the stability limit of rule 7.8.7 ("period,
    divided by ... `substeps`, is longer than that"), and `a = exp(-period
    / tau)`. *Chosen:* these are unchanged: the period in seconds is the
    double nearest to its nanoseconds over 10⁹, and the comparison in
    7.8.7 has no tolerance.

25. **Whether a counted length is whole periods (rule 6.3)** is now tested
    on whole nanoseconds: `length mod period == 0`. The sentence "The test
    is exact, on the numbers as written" was removed by the amendment.
    *Chosen:* a length as written is turned into nanoseconds in exact
    rational arithmetic (`0.1s` is exactly 100000000 ns), never through a
    double.

26. **The period itself.** *Chosen:* it must be a whole number of
    nanoseconds and more than zero; `0s` is refused. The text gives no
    range for it.

27. **A `max_age` of zero.** Rule 6.3: "may be any whole number of
    nanoseconds". *Chosen:* `0s` is accepted: a value is usable only at a
    tick whose time is exactly its own. `none` arrives as the text
    `"none"`.

28. **`max_ahead`.** The amendment removes it from 7.2 and 9.1.
    *Chosen:* it is now an unknown key in an input and the graph is refused
    (rule 9.5).

29. **Units of a length (rule 9.3).** *Chosen:* exactly `ns`, `us`, `ms`,
    `s`, `m`, `h`, lower case; `µs` is not accepted.

30. **Counts kept in ticks across a stall.** Rule 8.4 numbers the stall's
    tick "one more than that of the last tick run" though many periods
    passed; the table of 8.6 and "Nothing else changes at a gap" govern the
    blocks. *Chosen:* nothing but the table is applied. In particular a
    model block's `ride_through` count (rule 7.8.4, "counted as in rule
    7.4.3": "On the `m`-th unusable tick in a row the last usable input was
    `m` periods ago") and an integrator's `missed` go up by one tick's
    worth at a stall, not by the time skipped, and an estimator predicts
    over one period.

31. **Order of the two things done before a rebase's tick** (forgetting
    sample times, rule 8.5; telling every block, rule 8.6). *Chosen:*
    forget, then tell. No block's result depends on the order.

32. **"Writes are made one at a time" (rule 6.12) and "the one written
    last".** *Chosen:* "last" is the order of the `write` calls on that
    input, whatever their times. Each input is judged on its own writes:
    two inputs written together are taken up together only if their times
    fall between the same two ticks.

## Revised text

What the revision of Amendment 1 (rule 6.8 rewritten, `max_ahead` back,
rules 6.5 to 6.7, 6.10, 6.11, section 7.2 and rule 8.5 adjusted) still
leaves open, and what `impl.py` now does. The entries above describe the
implementation as it was before this revision; the list at the end says
which of them the revised text settles. Most likely to make two
implementations disagree first.

1. **`max_ahead` shorter than half a period: is a write thrown away that
   the call's last tick may see?** Rule 6.8: "The **last** tick a call runs
   may see every write whose time is not after the later of that tick's
   time and the call's `now`", and "At every call, a waiting write whose
   time is more than `max_ahead` after `now` is done with, and never
   stands." A tick is run up to half a period after `now` (rule 6.6), so
   with `max_ahead` under half a period a write can be both.
   *Chosen:* the throwing away is done first, when the call is accepted,
   before any tick of the call: "never stands" wins. Measured: period 1 s,
   `max_ahead: 100ms`, a write stamped 1 s, a call at 0.6 s runs tick 1
   (at 1 s) and reads the old value, and the write is gone for good. The
   other reading lets tick 1 see it.

2. **Which calls "every call" is, for `max_ahead`.** *Chosen:* every call
   that is not refused: one that runs no tick, the first call, a stall and
   a rebase's call among them, each against its own `now`. A refused call
   "changes nothing" and throws nothing away. So a write stamped 1.2
   periods ahead of a call that runs no tick is lost, though the next call
   would have found it within `max_ahead`.

3. **A time that does not fit in 64 bits.** Rule 6.7: "A time may be any
   whole number that fits in 64 bits, signed." Rule 6.11 does not list a
   time out of that range among what is refused, and 6.7 speaks of a
   write's time only.
   *Chosen:* a write's time and a call's `now` outside −2⁶³ … 2⁶³−1 are
   both refused. Sums the engine forms (`now` plus `max_ahead`, a tick's
   time) are not limited: a time within a period or a `max_ahead` of the
   ends of the range works here and may overflow elsewhere.

4. **A waiting write with the same time as what stands.** Rule 6.8: "Among
   them, and what stood before, the one with the latest time stands ... Of
   two with the same time, the one written later stands."
   *Chosen:* what stood was written earlier than anything still waiting, so
   the waiting write stands. This matters when the two differ in value or
   state.

5. **`bad` and `not_ready` writes under "the latest time stands".**
   *Chosen:* they are judged by their times like any other write. A `bad`
   stamped earlier than a usable value that stands never stands; one
   stamped later does, and then "does not grow old" (section 7.2).

6. **"What stands" in section 7.2 against rule 6.8.** Section 7.2: "'What
   stands' is the write last taken up (rule 6.8)." Rule 6.8: a write taken
   with "an earlier time than what stands never stands". *Chosen:* 6.8.

7. **An age below zero.** The last tick of a call may see a write stamped
   after its own time (up to `now`). Rule 7.2.4: "`bad`, if its age, `t`
   less its time, is more than the maximum age". The sentence the third
   revision had about an age below zero is gone.
   *Chosen:* an age below zero is not more than any maximum (zero among
   them): the value is usable, and carries its own time as sample time
   though that is after the tick's. An estimator's `since_<port>` is then
   below zero (measured: −0.003 for a call 3 ms late).

8. **A stall's tick and a rebase's tick as "the last tick a call runs".**
   *Chosen:* each is the only tick of its call and so the last: it may see
   writes up to the later of its time and `now`. Rule 8.4's "Writes are
   taken up as at any tick" is read the same way.

9. **"The values a delay holds carry no sample time from then on" (rule
   8.5).** *Chosen:* the values in the delay when the rebase's tick is
   about to run lose their sample times, for good; a value it takes in at
   the rebase's tick or after carries its own. The other reading: nothing
   a delay gives ever carries a sample time again.

10. **Which blocks "hold" a sample time.** Rule 8.5: "every sample time a
    block remembers or holds is forgotten", with a window, an estimator and
    a delay named. *Chosen:* those three and no others; no other block in
    Appendix A keeps one.

11. **Range of `max_ahead`.** Not in Appendix A's ranges. *Chosen:* any
    whole number of nanoseconds, zero included; `none` is not accepted. It
    need not be a whole number of periods.

12. **Writes done with but not standing.** Rule 6.8: "the engine takes the
    writes waiting that the tick may see. They are done with." *Chosen:*
    all of them, the ones that lose to a later time included; none is kept
    to stand later.

13. **"An engine need keep ... no more than one for each tick still to
    come" (rule 6.8).** *Chosen:* not relied on; every waiting write is
    kept until a tick may see it or `max_ahead` throws it away. (See the
    report: the statement is false when two writes fall between a tick's
    time and half a period after it.)

14. **`rebase()` followed by a restore of a state saved before any tick.**
    Rule 8.3 makes that restore "a reset"; rule 8.5 "A reset after a
    `rebase` is a reset, and the next call is not a gap". *Chosen:* the
    next call runs tick 0 and is not a gap.

15. **Section 6's opening against rule 6.8.** "every tick reads its inputs
    as they stood at its own time" is not so for the last tick of a call,
    which may see what was sampled after its time. *Chosen:* 6.8.

### The first 32 entries against the revised text

- Settled as chosen: 1, 2, 4, 5, 8, 9, 11, 13, 30 (30 is now named in the
  preamble as known to be wrong and still to be amended).
- Settled otherwise, and `impl.py` changed: 6 and 7 (the latest time
  stands; an older write never does), 17 (a delay's held values lose their
  sample times), 21 (`info` is `None` after a call that ran no tick, by the
  interface), 28 (`max_ahead` is back, with a new meaning), 32 (the order
  of writing now decides only between equal times).
- Partly settled: 3 (a negative time is allowed, "64 bits, signed"; whether
  `2.0` is a whole number is still open), 16 (ahead is now bounded by
  `max_ahead`; a write stamped far in the past is still accepted).
- Still open, choice unchanged: 10, 12, 14, 15, 18, 19, 20, 22, 23, 24, 25,
  26, 27, 29, 31.

## Third round

What the third revision of Amendment 1 (writes thrown away and counted,
`max_waiting`, the half-period floors, "nothing stands from the moment" of
a restore or `rebase`, rule 8.5's closing paragraph) still leaves open,
and what `impl.py` now does. Most likely to make two implementations
disagree first.

1. **What starts the count of writes thrown away again, besides a call
   that ran a tick.** Rule 6.10: "how many writes have been thrown away
   (rule 8) since the last call that ran a tick". Nothing says what a
   reset, a restore or a `rebase` does to the count, and after a reset
   there is no such call.
   *Chosen:* a reset sets it to zero, and so does restoring a state saved
   before any tick (rule 8.3: "is a reset"). Any other restore, and a
   `rebase`, leave it: a write thrown away before a `rebase` is reported by
   the rebase's call. Writes thrown away before the first call ever are
   reported by it.

2. **Which writes are "thrown away" for the count.** Rule 6.8 uses the
   words for three things (stamped too far ahead; "thrown away as it is
   made"; over `max_waiting`) and says "done with" of the rest.
   *Chosen:* only those three are counted. Not counted: a write a tick saw
   that lost to a later time; the writes waiting at a reset, a restore or
   a `rebase` ("done with"); a refused write.

3. **`max_waiting`: is the write just made one of those that may be thrown
   away?** "When one more is written, the waiting write with the earliest
   time is thrown away, the earlier written of two with the same time."
   *Chosen:* the new write waits first, and then the earliest of them all
   goes, the new one itself if it is the earliest (one with the same time
   as an older one survives it). The other reading throws away the
   earliest of those already waiting and always keeps the new one.

4. **A write "earlier than that of what stands" is judged when it is made,
   and against what stands only.** *Chosen:* thrown away, without an
   error, if its time is earlier than the time of what stands on that
   input at that moment, whatever either state is; a write with the same
   time waits. It is not judged against writes still waiting. It is thrown
   away before `max_waiting` is looked at, and throws nothing else out.
   With nothing standing (before tick 0, after a reset, and from the
   moment of a restore or `rebase`) no write is thrown away this way.

5. **"How many writes still wait".** *Chosen:* the number waiting on all
   inputs together, after the call's last tick has run.

6. **"`rebase` before any tick has run ... does away with the writes
   waiting, and nothing else ... So does restoring a state saved before
   any tick had run" (rule 8.5) against "is a reset" (rule 8.3).** A
   restore into an engine that has run ticks has to put every block back,
   so it does more than that.
   *Chosen:* restoring such a state is a full reset (blocks, tick number,
   what stands, the waiting writes, the count of entry 1, `info`).
   `rebase` before any tick does away with the waiting writes only, and
   leaves the count.

7. **`max_age` and `max_ahead` "not less than half a period" with an odd
   period.** *Chosen:* compared exactly, as twice the length against the
   period: with a period of 3 ns, 2 ns is accepted and 1 ns refused. A
   length equal to half a period is accepted. `max_ahead` has no `none`.

8. **`since_<port>` "not less than zero" (rule 7.9.6).** *Chosen:* a
   difference below zero is given as zero, `good`. (This line was changed
   in the copy of `impl.py` I was handed.)

9. **What a saved state holds.** Rule 8.5: "A state saved between a
   `rebase` and the call that follows it is as one saved before the
   `rebase`", and nothing stands from the moment of a restore.
   *Chosen:* a saved state carries neither the waiting writes, nor a
   pending rebase, nor the count of entry 1; what stood is saved and
   ignored by `restore`. `engine.info` is not touched by `save`, `restore`
   or `rebase`.

10. **Range of `max_waiting`.** "1024 unless given and at least 1".
    *Chosen:* a whole number (an `int`, not a `bool`), at least 1, with no
    upper limit. It is for each input on its own.

11. **The host's instruction against rule 6.8.** Section 6: "never write a
    time earlier than one already written to the same input: it is thrown
    away". Rule 6.8 throws away only a time earlier than what *stands*.
    *Chosen:* the rule. (See the report for the case.)

### The "Revised text" entries against the third revision

- Settled as chosen: 2, 3, 4, 5, 6, 8, 9, 13, 14, 15.
- Settled otherwise, and `impl.py` changed: 1 and 11 (`max_ahead` under
  half a period is refused, so the clash cannot arise), 7 (an age below
  zero is usable as chosen, but `since_<port>` is not less than zero).
- Still open, choice unchanged: 10, 12 (now also: such writes are not
  counted as thrown away, entry 2 above).

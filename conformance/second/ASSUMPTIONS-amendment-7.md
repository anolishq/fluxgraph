<!-- markdownlint-disable MD029 -- entries keep one numbering -->
# Assumptions made in adding `rate_limit` and `pid` (Amendment 7)

Every place where rules 7.4.9 to 7.4.11 and 7.7.5 to 7.7.11, the two rows
of the table in 8.6 and the entries of Appendix A left a choice or could
be read two ways, and what `impl.py` does. The text is `spec.md` as it
stood after rules 7.7.6 and 7.7.9 were changed (the integral's addition
is cut short at a limit). Quotations are from `spec.md`. Each example was
run on `impl.py`, at a period of 1 s.

## `rate_limit`

1. **The arithmetic of the reach.** Rule 7.4.9: "by at most `up` times the
   period where the input is above it ... An input within that reach is
   taken as it is, and the comparison is exact."
   *Chosen:* in doubles: the input is within reach where
   `input - held <= up * period` (and `held - input <= down * period`
   below); otherwise the output is `held + up * period` (or
   `held - down * period`). Another engine may test
   `input <= held + up * period`; the two can differ by a rounding where
   the numbers are not exact in binary, and then `limited` differs with
   them. Where they are exact the two agree, and an input exactly at the
   reach gives the same output either way.

2. **`limited` is "true when the output is not the input".** *Chosen:*
   compared as doubles, exactly. On a first input it is false.

3. **Before any usable input.** Rule 7.4.11 sends an unusable input to a
   deadband's rules 3 and 4, which speak of what it holds. *Chosen:* with
   nothing held, `y` and `limited` both take the input's state, and
   nothing is counted towards `ride_through`.

4. **While it rides through.** *Chosen:* `y` is the held value,
   `uncertain`; `limited` has the input's state and no value, as rule 11
   says, so the two outputs differ in state on such a tick. A fallback on
   `limited` then gives its value; one on `y` does not apply.

5. **`up` of zero, and `down`.** *Chosen:* `up: 0` is accepted ("not
   negative") and the output never rises; `down` left out is `up`, zero
   among it, and then the output never moves after its first input. `up`
   is required: the table gives it no value in brackets.

6. **At a gap.** The table puts it with a deadband. *Chosen:* the count of
   unusable ticks goes up by the ticks passed over; within `ride_through`
   it holds, and at the tick that runs it moves by one period's worth
   from what it held ("the reach is of one period whatever went before");
   otherwise, and where nobody knows, it forgets. A gap that passed over
   none changes nothing.

7. **On a loop that holds a model block.** Rule 7.8.8 holds delays,
   windows and low-passes against the loop's `settle`, and has them turn
   what they took in as `uncertain` to `good` once the loop has settled.
   A `rate_limit` is not named. *Chosen:* it is not held against
   `settle`, and it follows its own rules on the loop; since its output
   takes its state from the input at the tick, there is nothing for it to
   turn. The same for a `pid`.

## `pid`

8. **The order of the sum, and the output at a limit.** Rule 7.7.5:
   "`kp·error + integral + derivative`". Rule 7.7.6: "the integral
   becomes what puts that output at `max`".
   *Chosen:* in doubles, `kp * error + integral + derivative` from left
   to right; the integral that puts the output at `max` is
   `max - kp * error - derivative`. Where the addition is cut to that,
   the output before limiting is taken to be `max` itself and `y` is
   `max`, and not the sum worked again from the new integral, which could
   be a rounding away from it.

9. **"Or stays as it is if that is less than it has."** *Chosen:* where
   the integral that would put the output at `max` is less than or equal
   to what it has, the integral does not change; the addition still
   counts as cut short, so `limited` is true (in that case the output
   before limiting is at or above `max` anyway). Likewise at `min`.

10. **An addition of exactly zero** (an error of zero, or `ki` of zero) is
    never cut: rule 6 cuts "where the addition is more than zero" or less.
    So a `pid` with no `ki` is `limited` only where the output before
    limiting is past a limit.

11. **`limited` exactly at a limit.** *Chosen:* an output before limiting
    that is exactly `max` with the addition made whole is not `limited`;
    one that was cut to `max` is. Run: `kp` 1, `ki` 1, `max` 3.5, error 1:
    at tick 2 the integral is cut to 2.5, `y` is 3.5 and `limited` is
    true; at tick 3 with an error of 0.5 the whole addition gives exactly
    3.5, and `limited` is false.

12. **What "the tick before" is for the derivative.** Rule 7.7.7: "On the
    first tick where both inputs are usable, and on the first such tick
    after one where they were not, after a reset or after a gap, there is
    no tick before: `f` is zero".
    *Chosen:* a tick where either input is unusable, a usable true
    `reset`, and a gap of either kind each put the derivative at its
    start: on the next tick with both usable `f` is zero, and the
    filter's old value is not kept. A gap that passed over no tick is the
    exception: by rule 8.6 "a block does nothing but add one to `gaps`,
    whatever the table says", so the derivative goes on from the tick
    before, though the row for `pid` says it "starts again". With `kd` of
    zero nothing is kept at all.

13. **`integral` on a tick with an unusable input.** Rule 7.7.9:
    "`uncertain` on a tick where `y` is, and otherwise `good`, on a tick
    with an unusable input too". *Chosen:* as written, also where `reset`
    is `uncertain` and true on such a tick: `y` is then unusable and not
    `uncertain`, so `integral` is a `good` zero. Run: a `bad` measurement
    and a `good` true `reset` → `y` is `bad`, `integral` is `good` 0.
    The other reading carries the reset's doubt to `integral`.

14. **A reset on a tick with an unusable input.** Rule 7.7.10 has no
    condition on the other inputs. *Chosen:* it resets all the same.

15. **`doubtful`.** Rule 7.7.11: "the ticks on which either input was not
    `good`". *Chosen:* `setpoint` and `measurement` only; the state of
    `reset` is not counted. A tick with both not `good` counts once. A
    tick a gap passed over counts.

16. **`filter`.** "`filter` is required with a `kd` that is not zero and
    refused without one." *Chosen:* `kd` is tested as `kd != 0` on the
    number given; `filter` with `kd: 0` written out is refused like
    `filter` with no `kd`. It is a length that only scales a value, like
    a low-pass's `tau`: any length with a unit, not a whole number of
    periods, and a bare number is refused.

17. **`min` and `max`.** *Chosen:* either may be given alone; given
    together, `min` equal to `max` is refused ("`min` less than `max`").
    Both are finite numbers of any sign. `kp` is required.

18. **A sum that is not finite.** *Chosen:* rule 3.6: `y` is `bad`, and so
    is `integral` if the integral itself is not finite; the block's state
    is not put right.

19. **What a `pid` and a `rate_limit` are to the rules already there.**
    Their ports are all direct (Appendix A's default), so a `pid` that
    reads a model block's output and drives it is a loop through the
    model's deferred input, and needs the model's `settle`; a `pid` and a
    `rate_limit` that read each other with nothing deferred between are a
    loop of direct inputs, and refused. For a loop's doubt a `pid` uses
    every input it has, `reset` among them (rule 7.8.8), and its `y` with
    no value on a port the loop is connected to is a doubt. Both give
    their outputs the time of the tick, so neither may feed an
    estimator's measurement (rule 7.9.3). A fallback may be given for any
    of their outputs, and applies to that one alone.

## After the amendment grew

The text gained a `rate_limit`'s `initial`, a `pid`'s `applied` (rule
7.7.12), and a word on the state of `integral`. Of the entries above:

- **Entry 1 is settled, as chosen**: "the input less the value held,
  either way round, is compared with the reach, exactly."
- **Entry 8 is settled in part, as chosen**: rule 7.7.6 now says "and `y`
  is `max`" where the addition is cut. `impl.py` gives `max` itself in
  both cases of a cut, also where the integral stays as it is.
- **Entry 13 is settled, the other way**: `integral` is `uncertain` "where
  `reset` is `uncertain` and true", on a tick with an unusable input too.
  `impl.py` changed. Run: a `bad` measurement and an `uncertain` true
  `reset` → `y` is `bad` and `integral` is `uncertain` 0.
- **Entry 3** now has a second half: see 20.

What the new text left to choose:

20. **What "holding `initial` and nothing else" is.** Rule 7.4.11:
    "Holding `initial` and nothing else it does not ride through: its
    output takes the input's state."
    *Chosen:* the block is in that state from the start, after a reset of
    the engine, and after it has forgotten, until its next usable input;
    in it an unusable input gives the input's state and counts nothing
    towards `ride_through`, and a gap of either kind changes nothing.
    Once it has given a value on a usable input it rides through on that
    value as before, also where that value equals `initial`.

21. **`initial` after a gap.** The table of 8.6 says a `rate_limit`
    "forgets" past `ride_through` and where nobody knows. *Chosen:*
    forgetting at a gap is the forgetting of rule 11: it holds `initial`
    again, and its next input is limited from that. Run: `up` 2,
    `initial` 0, `ride_through` 3 s; it has moved to 4; four ticks are
    passed over; an input of 10 gives 2.

22. **`initial`'s range.** Appendix A gives it "(none)" and no range.
    *Chosen:* any finite number; a boolean or text is refused.

23. **"What it was before this one."** Rule 7.7.12: "from the next tick
    the integral is what it was before this one."
    *Chosen:* what it was before this tick's addition, and after this
    tick's reset if there was one: a tick with a true `reset` whose
    addition is taken back leaves an integral of zero, not the integral
    from before the reset. Run: integral 2; a true `reset` and an
    `applied` of 0 at one tick: that tick gives 1, and the next starts
    from 0 and gives 1.

24. **"A tick whose addition was made, whole or cut short."** *Chosen:*
    any tick with both inputs usable and an addition that is not zero.
    An addition cut to nothing (the integral stayed as it was) counts,
    and taking it back changes nothing. An addition of exactly zero is
    neither more nor less than zero and is never taken back. On a tick
    with an unusable input nothing was added and `applied` is not looked
    at.

25. **Which `y` `applied` is compared with.** *Chosen:* the value `y` had
    at that tick after limiting, as a double, exactly; not the value a
    fallback put in its place (there is no addition on a tick where `y`
    has none), and not if `y` was not finite. An `uncertain` `applied` is
    usable and is used; its doubt goes nowhere, since `applied` is read
    in the second phase and what the tick gave is not changed.

26. **`applied` and the rules already there.** *Chosen:* it is a deferred
    input like a model block's: the PID's outputs at a tick do not depend
    on it, a loop through it compiles (a `rate_limit` after the PID read
    back by it), and it may be given a constant, which then takes every
    addition back that goes away from it. For a loop that holds a model
    block the PID "counts as using every input it has, in either phase"
    (rule 7.8.8), so an `applied` read from outside the loop that is not
    `good` is the loop's doubt. `doubtful` does not count it (rule 11
    names the two inputs).

27. **The integral's state on the tick after an addition was taken
    back.** Nothing is said. *Chosen:* nothing is remembered of it:
    `integral` is `good` if the inputs are, and `limited` is not set by a
    taking back, at that tick or the next. So a PID held back by a rate
    limit through `applied` shows `limited` false throughout. Run: `ki`
    1, an error of 1, a `rate_limit` of 0.25 a tick after it read back as
    `applied`: `y` is 1 and `limited` false on ticks 0 to 3 while the
    ramp climbs, and the integral goes on from tick 4. Section 7.11 says
    of a limit `applied` is *not* connected to that "`limited` is false";
    it is false with it connected as well, and a graph that wants to know
    compares `y` with what was applied.

## After `applied_within` was added

Entry 25 is settled as chosen ("An `applied` that is `uncertain` is used
as a `good` one is"), and entry 27 as chosen ("`limited` says nothing of
an addition taken back").

28. **The arithmetic of "by more than `applied_within`".** Rule 7.7.12:
    "less than `y` by more than `applied_within` ... and the comparison
    is exact". *Chosen:* in doubles, `y - applied > applied_within` for an
    addition more than zero and `applied - y > applied_within` for one
    less than zero. Off by exactly `applied_within` is not more, and the
    addition is kept. Another engine may test
    `applied < y - applied_within`; the two can differ by a rounding
    where the numbers are not exact in binary. Run, `applied_within` 0.5:
    a readback low by 0.5 keeps the addition, and one low by 0.75 takes
    it back.

29. **`applied_within` with `applied` not connected.** Nothing says.
    *Chosen:* accepted, and it does nothing. Its range is "not negative"
    and finite; zero written out is accepted.

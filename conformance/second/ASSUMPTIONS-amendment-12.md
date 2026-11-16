<!-- markdownlint-disable MD029 -- entries keep one numbering -->
# Assumptions made in bringing `impl.py` up to Amendment 12

Every place where "A controller that is not acting" (rules 7.4.14 and
7.7.15, and the two rows of Appendix A) left a choice, could be read two
ways, or sits oddly with another rule, and what `impl.py` does. Entries 1
to 12 were written before the vectors were run. Quotations are from
`docs/semantics_spec_v2.md`.

## Both blocks

1. **When a block follows.** "at a tick where `follow` is true, and at one
   where `follow` is not usable". *Chosen:* a usable `follow`, `good` or
   `uncertain`, is taken by its value; an `uncertain` true follows and an
   `uncertain` false acts, and neither makes anything `uncertain`. Only a
   `follow` that is not usable does ("`uncertain` in place of `good`").

2. **"`uncertain` in place of `good`."** *Chosen:* with `follow` not
   usable, a `good` `track` gives `uncertain` outputs and an `uncertain`
   `track` gives `uncertain`; with `track` not usable the outputs have
   `track`'s state and no value, whatever `follow` is.

3. **`follow` given, `track` not.** "is given only where `track` is: the
   graph is refused otherwise". *Chosen:* refused where the port `follow`
   is connected and `track` is not; either may be a constant. `track`
   with no `follow` is as before.

## A rate limit (rule 7.4.14)

4. **"Holds that value as one it took from an input at that tick."**
   *Chosen:* exactly as if a usable input had been taken at that tick:
   the count of unusable ticks in a row is zero, the block is no longer
   on `initial` alone, and at the next tick it acts it limits from that
   value, or with an unusable input rides through on it for
   `ride_through`.

5. **Following with `track` not usable.** "the block holds what it held".
   *Chosen:* nothing in the block changes at all: not the value, not
   whether it is one it took from an input, and not the count of unusable
   ticks. So such a tick is neither a usable tick nor an unusable one for
   rules 3 and 4, and a block that was riding through before a stretch of
   them has as much `ride_through` left after it.

6. **A catch-up tick of a rate limit that acts by the call.** "does
   nothing, as rule 12 says, and `follow` is not looked at". *Chosen:*
   rule 12 whole: `limited` there is of the input and what it holds, and
   `y` is held by the engine.

## A PID (rule 7.7.15)

7. **`integral`'s state.** "`integral` and the counts are as at any other
   tick", and rule 7.7.9: "`uncertain` on a tick where `y` is, or where
   `reset` is `uncertain` and true, and otherwise `good`". *Chosen:* on a
   tick where it follows, `integral` is `uncertain` where `y` is
   (`track` `uncertain`, or `follow` not usable with `track` usable) or
   the reset is `uncertain` and true, and otherwise `good`: with `track`
   not usable, and with a setpoint or measurement not usable, too.

8. **`limited` with `track` not usable.** "they have no value and the
   state of `track`." *Chosen:* both `y` and `limited`.

9. **Waiting to track.** "waits to track (rule 14) from that tick, a tick
   of a reset among them". *Chosen:* every tick it follows leaves it
   waiting, whatever else happens at that tick; it then stops waiting by
   rule 14 at the first tick it does not follow with both inputs usable
   (for one that acts by the call, the first such that is the last of its
   call), and takes `track` there if `track` is usable.

10. **The derivative while it follows.** "Its derivative goes on as rule
    7 says, and starts again at a tick where either is not usable."
    *Chosen:* at a tick it follows with both inputs usable, rule 7 runs:
    a new sample is taken and filtered; with either unusable nothing is
    remembered. Its value is not given to anybody at such a tick.

11. **A PID that acts by the call, at a catch-up tick.** "The PID follows
    ... a catch-up tick among them." *Chosen:* at a catch-up tick with
    `follow` true it follows: it waits to track, and what it works out
    for `y` is `track`; the engine then puts the held `y` in its place
    (rule 6.13), and `limited` and `integral`, which are not held, are
    those of following.

12. **`doubtful` and `follow`.** *Chosen:* the counts are of the setpoint
    and the measurement as before; `follow` and `track` are not counted.

## After the vectors were run

One vector and one comparison graph disagree, both on the same point,
and I have not changed `impl.py` for it.

13. **Disagreement: `pid-follow`, call 4, and every difference in the
    comparison graph "follow: a pid and a rate limit told they are not
    acting": the state of `integral` while the PID follows.** At call 4
    `follow` is `bad` and `track` is a `good` 7, so `y` is `uncertain` 7.
    The vector gives `integral` as `good` 5; `impl.py` gives `uncertain`
    5. The comparison shows the other half: on a tick where it follows
    and its setpoint or measurement is `uncertain`, the reference gives
    `integral` as `uncertain` and `impl.py`, with `y` `good`, gives
    `good`.
    - The text for `impl.py`: rule 7.7.15, "`integral` and the counts are
      as at any other tick", and rule 7.7.9, "`integral` is the integral,
      a number: `uncertain` on a tick where `y` is, or where `reset` is
      `uncertain` and true, and otherwise `good`". At call 4 `y` is
      `uncertain`, so by rule 9 as written `integral` is.
    - The text for the vector: "as at any other tick" can be read as "by
      what it would be were the block not following", that is by the
      states of the setpoint and the measurement. Rule 7.7.9 was written
      when `y`'s state was always the worse of those two, and "where `y`
      is" was a short way of saying so.

    *Verdict:* the text supports both, and by its letter mine. I think
    the vector's is the better rule: nothing doubtful went into the
    integral on a tick it follows, and `track`'s or `follow`'s state has
    nothing to do with it. Rule 7.7.15 should say so in words, for
    instance: "`integral` has the state it would have were the PID not
    following: `uncertain` where its setpoint or its measurement is, or
    `reset` is `uncertain` and true, and otherwise `good`; the states of
    `track` and `follow` do not reach it." Under that sentence `impl.py`
    is a one-line change and agrees with all 504 vectors (tried, and put
    back). A third reading, `integral` always `good` while it follows
    but for an `uncertain` reset, also agrees with all 504: no vector
    has an `uncertain` setpoint or measurement on a tick it follows.

14. **Not pinned: an `uncertain` true `follow`** (entry 1). Making its
    outputs `uncertain` changes no vector.

15. **Pinned: a rate limit following with `track` not usable** (entry 5).
    Counting such a tick towards `ride_through` fails `rate-limit-follow`.

## After rules 7.4.14 and 7.7.15 were revised

Entry 13 (the state of a following PID's `integral`) is settled, the
vector's way: "its state is what rule 9 gives it at a tick where the PID
does not follow: by the setpoint, the measurement and a reset, and not by
`track`, `follow` or the state of `y`." `impl.py` changed. Entry 11 is
settled as chosen. Entry 5 is settled the other way, and see 16.

16. **Disagreement, and mine was the misreading: `rate-limit-follow`,
    call 4.** "With `track` not usable ... the block holds what it held;
    such a tick passes as any other does for `ride_through`, which is
    counted from the last tick the block took a value at." I first read
    "passes as any other does" as "is an unusable tick like any other":
    past `ride_through` the block forgets at that tick. With the default
    `ride_through` of zero it then forgot at the first such tick, and at
    call 4 took its input as it was (10) where the vector moves from the
    8 it held (9). *Verdict:* the text supports the vector. "The block
    holds what it held" has no condition, and a block that forgot at such
    a tick would not be holding it. `impl.py` now counts the tick and
    forgets nothing at it; the count is judged at the next tick the block
    acts on an unusable input. The sentence still invites my first
    reading, and would be exact as: "it forgets nothing at such a tick,
    however many there are; the tick counts towards `ride_through` when
    the block next acts on an unusable input".

17. **What that gives, and whether it is the worse choice.** After any
    number of following ticks with no `track`, a block that acts again on
    a usable input limits from the value it last followed to, however old;
    one that acts again on an unusable input has, past `ride_through`,
    forgotten, and its next usable input is taken from `initial` or as it
    is. I think holding is the better choice of the two for the first
    case: the last place the actuator was known to be is a better start
    than a jump. The two cases are not alike, though, and an hour-old
    value limited from as if it were current is a thing given up that
    section 7.11 should list.

18. **A PID that acts by the call, following at a catch-up tick: is its
    integral set there?** "At a tick where it follows, both its inputs
    and `track` are usable, and there is no reset, its integral is set".
    *Chosen:* at every such tick, a catch-up tick among them: the rule
    names no exception, and setting is not acting. The other reading
    holds that a by-call PID changes its integral only at the last tick
    of a call.

19. **Which derivative, while it follows.** "`track` less the first sum of
    rule 5, as rule 14 sets it". *Chosen:* `kp·error` and the derivative
    as worked at that tick, after rule 7 has run for it.

20. **A reset while it follows.** *Chosen:* at that tick the integral is
    zero and `track` does not set it; at the next following tick with no
    reset, `track` sets it again. So a reset held true while it follows
    keeps the integral at zero, and one pulse of it is undone a tick
    later.

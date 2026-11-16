<!-- markdownlint-disable MD029 -- entries keep one numbering -->
# Assumptions made in bringing `impl.py` up to Amendment 13

Every place where "An estimator between samples" (section 7.9, the
estimator rows of the table in section 8 and of Appendix A) left a
choice, could be read two ways, or sits oddly with another rule, and what
`impl.py` does. Entries 1 to 24 were written before the vectors were run.
Quotations are from `docs/semantics_spec_v2.md`.

## Places (rule 7.9.2)

1. **The rounding of a sample's place.** "the tick's place less the time
   from the sample to the tick, in sixteenths of a period, to the nearest
   whole number; exactly a half goes to the later place." *Chosen:* in
   whole numbers, exactly. With `back` the tick's time less the sample
   time in nanoseconds (below zero for a sample stamped after the tick)
   and `P` the period in nanoseconds, the place is
   `16·k + floor((P - 32·back) / (2·P))`. That is `16·k` less
   `back·16/P` rounded to the nearest whole number with a half rounded
   towards the later place. For `state_space`:
   `16·(k + floor((P - 2·back) / (2·P)))`. No double takes part.

2. **A sample stamped after the tick.** The last tick of a call may see a
   write up to the call's `now`, so `back` can be below zero and the place
   after the tick's. *Chosen:* the rule as written: such a measurement is
   considered at its place, the state is carried there and stands after
   the tick. What is given at that tick is then the state as it stands,
   not carried back (rule 8 carries "on ... to the tick" and has no word
   for a state that stands past it).

3. **A value with no sample time** has the tick's place: a constant, an
   input on its `initial`, a block's output.

4. **Places after a rebase.** Tick `k` is at `16·k` throughout, with the
   tick numbers the engine gives (a rebase with a length skips numbers,
   one without does not). So "counted from tick 0" is by tick number and
   not by time across a rebase.

## The steps (rule 7.9.2)

5. **How the five steps are worked out.** *Chosen:* `Ad`, `Bd` and `N` for
   16, 8, 4, 2 and 1 sixteenths each by the exact routine of amendments 4
   and 5, with the length `period·size/16` as an exact fraction of a
   nanosecond, rounded to doubles once. The whole-period step is the
   model's own. The step of 8 is not the square root of the step of 16,
   nor the step of 16 the square of it: each is worked on its own.

6. **The order over a stretch.** *Chosen:* whole-period steps first, then
   8, 4, 2, 1 as the binary digits of the rest, largest first. A stretch
   of 21 sixteenths is 16, 4, 1.

7. **Whole-period steps, how many at once.** "What is specified is the
   result and not that whole periods are stepped one by one." *Chosen:*
   up to 32 in a stretch are stepped one by one; more are compounded by
   squaring (two steps `x → F·x + g`, `P → F·P·Fᵀ + M` are one of the
   same form). The two differ in the last places; no rule says where the
   one ends and the other begins.

8. **A stretch.** *Chosen:* the way from the place the state stands at to
   the place it is carried to is cut at every place strictly between the
   two that some model input has a value from; each piece is stepped as
   in 6 on its own, so a cut at 21 of 32 gives 16, 4, 1 and then 8, 2, 1,
   and not one whole period.

9. **A model input with no value over a stretch.** "the state is not
   stepped over it: it stays, and the covariance is `P + N` for each
   step." *Chosen:* `N` of each step that would have been taken, added in
   the same order; many whole periods are added by the same compounding.

## Model inputs (rule 7.9.2)

10. **When a new value takes effect.** *Chosen:* at a tick's second
    phase, a usable model input whose value differs (as a double) from
    the last one it was given gets a new entry, from the latest of its
    sample's place, the place the state stands at after that tick's
    measurements, and the place of its last entry. Nothing it gives at
    that tick has used it; every carry after that, the next tick's
    outputs among them, uses it from that place. A value equal to the
    last is not a new one, and keeps the old place, whatever its sample
    time.

11. **Two values from one place.** Where the latest of the three is the
    place of the last entry, *chosen:* the new value replaces the old one
    at that place.

12. **A sample older than the state.** It has its value "from ... the
    place the state stands at": the time between the sample and the
    state is stepped on the old value and is not done again.

13. **A sample place after the tick, for a model input.** *Chosen:* the
    value is from that later place, as written; until then the old one
    is in force.

14. **What is kept.** "What was in force before the place the state
    stands at is not kept." *Chosen:* whenever the state comes to stand
    at a place, each input keeps its last entry from that place or
    before, with its own place, and every later one.

## Lag, and measurements (rules 7.9.2, 7.9.3)

15. **`lag` in the graph file.** Appendix A: "`lag` (2 periods)"; rule 2:
    "a whole number of periods". *Chosen:* written as a length of time,
    like `settle` and every other counted length (`lag: 2s` at a period
    of 1 s), a whole number of periods, zero allowed. The other reading
    is a bare whole number.

16. **Lag at a tick.** *Chosen:* before any measurement the state is
    carried to `16·(k - lag)` if it stands before that, and stands there.

17. **Which sample time a port remembers.** "later than the sample time
    last considered or passed by on that port". *Chosen:* one time per
    port: that of the last measurement that was due, whether it was
    considered (used or refused) or passed by as late. A measurement that
    was not due leaves it alone.

18. **The order at one tick.** *Chosen:* all the measurements due at the
    tick are found first, from what the ports read at that tick; then
    they are taken by place, and by declared order within a place. Each
    is judged late or not against where the state stands when its turn
    comes.

19. **"The first measurement due after the start, a reset or a rebase,
    on any port."** *Chosen:* one flag for the estimator. It is spent by
    the first measurement due, whether or not that one's place was before
    the state's; the second due is judged as any other.

20. **Late and the other counts.** A late measurement is not considered:
    it has no innovation, does not touch the run of refusals, is not
    among the `over` kept for the consistency test, does not end "no
    measurement has been used since", and leaves `since_<port>` alone.

## Rule 7.9.7, 7.9.8, 7.9.9

21. **"At the tick before, a model input was `uncertain` or not
    usable."** *Chosen:* judged at each tick's second phase from the
    states the inputs then have, and it makes the next tick `uncertain`,
    one that has never been usable among them at every tick.

22. **A stall.** *Chosen:* nothing is done to the state; the tick that
    runs is `uncertain`; and at it the lag carries the state to `lag`
    behind, over the ticks passed over, on the model inputs it last had.

23. **A rebase, in order.** *Chosen:* (a) the sample times the ports
    remember are forgotten, and `since_<port>` is `not_ready`; (b) the
    state is carried to the place of the tick before the one that runs,
    `16·(g - 1)`, if it stands before that; (c) each variance grows by
    its `p0`; (d) each model input that has had a value has its latest
    one from the place the state now stands at, and nothing else; (e) the
    next measurement due is the first. With a length, `g` is the last
    tick's number and the ticks due; with none, one more than the last
    tick's. The counts of refusals and of late ones, the run of refusals
    and what the consistency test keeps are not touched.

24. **A state that stands after the tick before the rebase's.** Carrying
    back is not defined. *Chosen:* it stays where it stands.

## After the vectors were run

No vector and no comparison disagreed (522 of 522; 2,637,511 comparisons),
and nothing above was changed. I then tried thirteen of the choices the
other way against the vectors.

Pinned by a vector: the rounding for a discrete model (`estimator`); the
cut of a stretch at a model input's place (`estimator-between-samples`,
`estimator-in-a-loop`); the sample time a port remembers when one is late,
the first-measurement flag, and the lag (`estimator-late-sample`); the
order of carrying and `p0` at a rebase
(`estimator-rebase-with-length-order`).

**Not pinned**, each passing all 522 the other way:

25. Entry 1, for a model in continuous time: exactly half a sixteenth
    going to the earlier place.
26. Entry 6: the sub-steps taken 1, 2, 4, 8 in place of 8, 4, 2, 1. (They
    differ only in rounding, inside the vectors' tolerance.)
27. Entry 7: whole periods all one by one, or all compounded.
28. Entry 10: a value equal to the last one taken as a new one from its
    own place.
29. Entry 12: a model input whose sample is older than the state keeping
    its own place (the stretch before the state is never stepped, so it
    shows only through entry 11's replacement).
30. Entry 23 (d): model inputs keeping their places across a rebase.

## What I think is wrong, unclear, or at odds with another rule

31. **Rule 7.9.3 has four lines twice.** "new sample. Only the path the
    time comes by is followed. A formula's `sample_of` is its author's
    word that its value is as new as that input, whatever else the
    formula reads." follows itself.

32. **A sample stamped after the tick** (entry 2). Rule 8 says what is
    given is "carried on from where they stand to the tick". A
    measurement the last tick of a call sees from after its own time
    (rule 6.8) leaves the state standing up to half a period past the
    tick, and there is nothing to carry. `impl.py` gives the state as it
    stands, which is a state for a later time than the tick's under the
    tick's name. The text should say so, or say that such a sample has
    the tick's place.

33. **The first measurement, "considered where the state stands".** After
    the start, a reset or a rebase, a first sample of any age is taken as
    if it were of the place the state stands at. Run: no measurement for
    five ticks, then one sampled at 1 s and seen at tick 5: it is set
    against the state at 3 s. With a model that moves, that is a
    measurement of where the plant was two seconds before, used as of
    now, and the estimator is `good` on it. At the start the variance is
    `p0` and little is lost; after a rebase with a length the state has
    been carried far and the same is done. As estimation practice I would
    count it late like any other, or make its tick `uncertain`.

34. **A late measurement is thrown away, not used.** The text owns to it
    (Open, "Sensors with different delays"). With two sensors of
    different delay on one state the slower is late whenever the faster
    has been considered since, so in steady running it is never used at
    all and its tick is `uncertain` every time: the estimator is
    `uncertain` on most ticks for having been given a second sensor.
    Section 7.11 should say that plainly.

35. **A model input is held forward from its sample, never backward.** A
    value sampled at 2.25 s is in force from 2.25 s. For an input that is
    a command the actuator took at that moment this is right. For one
    that is a measured disturbance sampled every period, the stretch
    between two samples runs on the older one: a zero-order hold a sample
    late on average by half a period. That is no worse than before the
    amendment, and I note it only because the summary says "on each model
    input from the time its value is from", which a reader may take for
    more than a hold.

36. **`lag` has no range in Appendix A** and its form in the graph file
    is given only as "(2 periods)". The vectors agree with a length of
    time; zero is my choice.

## After section 7.9 was revised

Entries 31 (the lines twice), 32 (a sample after the tick), 33 (the first
measurement taken as newer than it is) and 34 (a slower sensor) are taken
up in the text. `impl.py` changed for 33 alone: a first measurement whose
place is before the state's is considered where the state stands and
makes its tick `uncertain`. Entry 25 (exactly half a sixteenth, for a
model in continuous time) is now pinned by a vector, as chosen.

37. **"Its place being before that."** *Chosen:* the tick is `uncertain`
    for the first measurement only where its place is strictly before the
    place the state stands at; one exactly there, or after, leaves it
    `good`. The clause does not last past its tick. The measurement is
    considered in full all the same: it has an innovation, may be used or
    refused, and ends "no measurement has been used since" if used.

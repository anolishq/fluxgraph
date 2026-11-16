<!-- markdownlint-disable MD029 -- entries keep one numbering -->
# Assumptions made in bringing `impl.py` up to Amendment 2

Every place where the text amended by "doubt through memory" (the head of
section 7, 7.3 to 7.8, 7.10, 7.11, the table of 8.6 and Appendix A) did not
say what to do, could be read two ways, or disagreed with another passage,
and what `impl.py` does. The ones most likely to make two honest
implementations disagree come first. Rule numbers are those of
`proposal.md`. Quotations are from `proposal.md`.

Part A is the guesses. Part B is what I believe the text gets wrong, each
with a small example run on `impl.py`.

## Part A. Where the text had to be guessed

### The loop rule (7.8.8)

1. **Which outputs count for "gave an output that was not usable".** Rule
   7.8.8: "the loop's **doubt** is the latest tick at which a block in it
   used a value that was not `good`, read from outside the loop, or gave an
   output that was not usable, whether or not a fallback then stood in for
   it."
   - Reading A: any output port of a block on the loop, read or not.
   - Reading B: only an output that another block of the loop reads.

   *Chosen:* A, the words as written. It is the reading with the worse
   consequences: a `window` on the loop gives `slope` as `bad` whenever it
   holds one sample; an `estimator` on the loop gives `innovation_<port>`
   as `not_ready` on every tick with no new measurement (rule 7.9.6); a
   `hysteresis` gives `not_ready` while undecided. Under A each is the
   loop's doubt on that tick although nothing in the loop reads the port.
   Under B none is. The text has to say which.

2. **What a block on a loop "uses".** Rule 7.8.8: "Every block but a
   formula uses every input it has; a formula uses what rule D says." Rule
   D: "a latch that is set does not use `set`; `all_good` reads states and
   not values". Rule 7.6.3: "A `reset` that is unusable, or usable and
   false, is not used." Rule 7.7.4: "An unusable `reset`, or one that is
   usable and false, is not used." These disagree for a latch, an
   integrator and an `all_good` on a loop.
   - Reading A: 7.8.8 as written. For the loop's doubt every block but a
     formula uses every input, whatever its own rule says.
   - Reading B: the block's own rule decides, on a loop as off it.

   *Chosen:* A. So a latch on a loop whose `reset` comes from outside and
   is `uncertain` and false on every tick keeps the loop in doubt for
   ever, though rule 7.6.3 says that `reset` "is not used".

3. **A doubt at tick `k` while an earlier doubt has not settled.** Rule
   7.8.8: "the loop's doubt is the latest tick at which ...", and "each
   model in it is `uncertain` for `settle` after the loop's doubt". The
   head of section 7: "it is so on the `settle` ticks after `d`: ticks
   `d + 1` to `d + settle`. What it is at tick `d` itself is given by rule
   D and the block's own rule." A doubt can arise in the first phase of
   tick `k` (a formula on the loop uses an uncertain value from outside)
   before or after a model on the loop gives its output, by block id. If
   "the latest tick" is then `k`, tick `k` is not one of `k + 1` to
   `k + settle`, and a doubt at `k - 1` is forgotten at tick `k`.
   - Reading A: at tick `k` a model (and a delay) on the loop looks at the
     latest doubt at a tick before `k`. A doubt at `k` itself changes
     nothing at `k`, whatever the order of the blocks.
   - Reading B: literally the latest, as it stands when the block gives
     its output. The result then turns on block ids.

   *Chosen:* A. The same is done for a model block off a loop, where it
   cannot matter (its doubt comes from the second phase).

4. **What "holds a model" means, and what a loop is.** Rule 7.8.8: "The
   blocks of a graph that can each reach every other through inputs,
   direct or deferred, are a **loop**. ... A loop that holds a model is
   treated as one block". Rule 4.9: "A block hosts a model (section 7.8),
   and so does an estimator".
   *Chosen:* a loop is a strongly connected set of blocks, the largest
   one: two cycles that share a block are one loop, and a block that only
   reads from the loop, or only feeds it, is not on it. "Holds a model"
   means holds a model block (`thermal_mass`, `state_space`). An estimator
   is not counted: it has no `settle` to be given. The other reading takes
   an estimator for a model here, and then every graph with an estimator on
   a loop is refused, since "every model in it is given `settle`".

5. **"is given `settle`".** Rule 7.8.8: "every model in it is given
   `settle`, and they are all given the same. A model's own time constant
   is not the loop's. The graph is refused otherwise".
   *Chosen:* the setting has to be written on every model block of the
   loop. A `thermal_mass` that would take its default (three time
   constants) is refused on a loop. "The same" is compared in ticks. The
   other reading accepts a default that happens to equal the others.

6. **Which values a delay on a loop gives as `good`, and when that is
   judged.** Rule 7.8.8: "a delay in it gives a value it took in as
   `uncertain` as `good`, once the loop is no longer within `settle` of its
   doubt".
   *Chosen:* it is judged at the tick the delay gives the value, not the
   tick it took it in, with "within `settle`" as in entry 3. Any
   `uncertain` value it gives is turned, a `good` one made `uncertain` by a
   gap (section 8.6) among them; with the delays of a loop no longer than
   `settle` that case cannot arise, because the gap is itself the loop's
   doubt. The value and the sample time are kept. An unusable value is
   given as it is (and is a doubt, by the same rule).

7. **"the `ticks` of the delays in the loop add up to more than
   `settle`".** *Chosen:* the plain sum over every delay on the loop, also
   when two delays sit on different branches and no value passes through
   both. A loop with one delay and `settle: 0s` is refused.

8. **When a deferred read is a doubt, and what "not `good`" covers.**
   *Chosen:* a model on a loop that reads a value from outside through a
   deferred input uses it in the second phase of tick `k`, and the doubt is
   tick `k` (as rule 7.8.6 says of a model's own doubt). "Not `good`"
   covers `uncertain`, `not_ready` and `bad`. An input given a constant is
   not a value from outside. An input from outside is one written by the
   host or by a block that is not on this loop, another loop's among them.

9. **A model on a loop and its own counters.** Rule 7.8.8: "each model in
   it is `uncertain` for `settle` after the loop's doubt, in place of its
   own in rule 6". *Chosen:* only the state of the outputs changes.
   `elapsed` and `doubtful` are still the block's own, by rule 7.8.6, so a
   model on a loop that steps on an `uncertain` value passed to it by
   another block of the loop counts that tick in `doubtful` while "an
   `uncertain` value that passes from one block of the loop to another
   starts nothing".

10. **The loop's doubt and a save.** Section 8: "Counters are part of what
    a save holds". Nothing says that a loop's doubt is. *Chosen:* it is
    saved and restored with the blocks' states, and a reset forgets it.

### Rule D against the blocks' own rules

11. **Rule D and the estimator.** Rule D: "A block's output is never
    better than `uncertain` on a tick where a value the block used to give
    that output at that tick is `uncertain`. Each block's rule says what it
    uses." Rule 7.9.5: "A state's outputs are `uncertain` on a tick where
    any model input is unusable at that tick, or where the state's sigma is
    more than its `sigma_max` ... Otherwise they are `good`." With
    `use_uncertain: true` an `uncertain` measurement is used at this tick
    and 7.9.5 still gives `good`. Rule 7.9 does not say what the estimator
    uses.
    *Chosen:* 7.9.5 as it stands; the estimator is unchanged. Section 7.9
    is listed as still to be amended, and "the covariance ... stands in for
    a doubt". The other reading makes every state's outputs `uncertain` on
    a tick where an `uncertain` measurement was used.

12. **Rule D and a formula with two deciders.** Rule 7.1.2: "Its state is
    `good` if one of the operands that decided it is `good`". Rule D: "A
    formula does not use an operand that did not decide". In `a or b` with
    `a` `uncertain` and true and `b` `good` and true, both decided; by
    7.1.2 the result is `good`, and by rule D it cannot be if `a` was used.
    *Chosen:* 7.1.2 gives the state, and where a `good` operand decided, an
    `uncertain` one that also decided is not used. This matters only for
    the loop's doubt (entry 2): such an `a`, read from outside the loop,
    starts nothing. With no decider both operands are used; `when` uses its
    condition and, if the condition is usable, the branch it took.

13. **Rule D and the outputs that are "always `good`".** Rule 7.3.7:
    "`count`, the number of usable samples the window holds, is always
    `good`", and the counters "always `good`". `count` goes up by one for
    an `uncertain` sample. *Chosen:* these read states and not values, as
    rule D says of `all_good`, and stay `good`.

14. **The head of section 7 on `ride_through`.** "A tolerance the graph's
    author declared (a window's `min_good`, a `ride_through`, a total's
    `max_missed`) ... Within it an output is `good`." Rule 7.4.3: "its
    output is the held value, `uncertain`, if the last usable input was no
    more than `ride_through` ago". Rule 7.8.6: "For a model ... riding
    through is a doubt". The same head lists `ride_through` under finite
    memory too.
    *Chosen:* 7.4.3 and 7.8.6. A deadband, a low-pass and a model are
    `uncertain` while they ride through. Only `min_good` and `max_missed`
    behave as the sentence says.

### Counters

15. **A model's `doubtful` at tick `k`.** The head of section 7:
    "`elapsed` counts whole ticks, the present one among them ... and
    `doubtful` counts those of them on which ...". Rule 7.8.6: "`doubtful`,
    which counts the ticks on which it stepped on an `uncertain` or a held
    value or did not step." The step of tick `k` is in the second phase,
    after the outputs of tick `k` are given, and by rule 4.4 an output
    "does not depend on" a deferred input at that tick.
    *Chosen:* at tick `k`, `elapsed` is `k + 1` periods and `doubtful`
    counts the steps of ticks 0 to `k - 1`. The step of tick `k` shows in
    `doubtful` at tick `k + 1`. This is so for a direct input too, for one
    rule. The other reading looks at the inputs of tick `k` in the first
    phase to count the step that has not yet been taken.

16. **A gap and a model's `doubtful`.** Section 8.6: "The tick before the
    gap's is a doubt (rule 7.8.6)". Rule 7.8.6 counts "the ticks on which
    it stepped on an `uncertain` or a held value or did not step".
    *Chosen:* the gap sets the doubt and does not add to `doubtful`: the
    tick before the gap's is not a tick on which any of those happened
    (or, if one did, it is counted already). `elapsed` goes on by one
    period per tick run, whatever the length of the gap.

17. **`held_for`: the tick the timer stops, and the ticks it holds.** Rule
    7.6.1: "`elapsed` and `doubtful` count from the tick the timer started,
    and are zero while it is not running; `doubtful` is of its input."
    *Chosen:* the counters are as the timer stands after the tick's input
    has been dealt with: both are zero on the tick it stops, and `elapsed`
    is one period on the tick it starts. An unusable tick that the timer
    runs through under `hold` is one where the input was not `good`, and is
    counted in `doubtful`.

18. **`since_true` and `held_for` at a gap, against "a rebase does not set
    them to zero".** Section 8.6: "`since_true` | The clock is set to the
    gap's tick", "`held_for` | The timer stops", and "Counters are part of
    what a save holds, and a rebase does not set them to zero." Rule 7.6.2:
    "`elapsed` and `doubtful` count from the tick the clock was last set".
    *Chosen:* the block's rule: at a gap `since_true` counts from the gap's
    tick (`elapsed` is one period there, `doubtful` is of that tick alone),
    and `held_for` counts from wherever its timer next starts. The sentence
    about a rebase is taken to mean that nothing else sets a counter to
    zero.

19. **`latch`: what clearing is, and `doubtful` on the tick it is
    cleared.** Rule 7.6.3: "`elapsed` counts from the tick it was last
    cleared, or from the first tick. `doubtful` counts those of them on
    which it was not set when the tick began and `set` was not `good`."
    *Chosen:* every tick with a usable, true `reset` clears, set or not,
    and `elapsed` is one period on it. On that tick `doubtful` starts from
    zero and then counts the tick itself if the latch was not set when it
    began and `set` was not `good`, although `set` is not looked at on
    such a tick.

20. **`hysteresis`: what a change is.** Rule 7.5.4: "count from the tick
    its value last changed, a change from undecided among them, or from the
    first tick if it has not". *Chosen:* an input at or beyond the
    threshold of the side it is already on is not a change. With `initial`
    given, a first input on that side is not one either. On the tick it
    changes `elapsed` is one period and `doubtful` counts that tick's
    input.

21. **`integrate`: the counts at a reset and while `bad`.** Rule 7.7.4: "A
    usable, true `reset` returns the total and all four counts to zero
    before that tick's addition." *Chosen:* `gaps` goes to zero with the
    rest, also when the reset comes on the gap's own tick (the gap is
    counted "before the tick runs", section 8.6, and then cleared). All
    four counts and the total go on while the total is `bad`. `doubtful`
    counts a tick whose input is `uncertain` whether or not the total is
    `bad`. `gaps` is a count and not a time.

### The rest

22. **A gap and a low-pass's doubt.** Rule 7.4.7: "Forgetting (rule 4)
    clears it." Section 8.6: "`deadband`, `lowpass` | Forgets what it held;
    the next usable input is a first input". Rule 7.4.7 names only the
    forgetting of rule 4.
    *Chosen:* a gap clears the doubt as well. The other reading keeps it,
    and a low-pass that took an `uncertain` input one tick before a gap is
    `uncertain` for `settle` after it, on a value that holds nothing from
    before the gap.

23. **A low-pass at the tick of its doubt.** Rule 7.4.8: "its output is
    `uncertain` if the input is, and for `settle` after its doubt."
    *Chosen:* `uncertain` at tick `d` by the input, and on ticks `d + 1` to
    `d + settle`: `k - d <= settle`. With `settle: 0s` it is `uncertain`
    only on a tick where its input is.

24. **A model block off a loop: "With `settle`".** Rule 7.8.6: "With
    `settle`, its outputs are `uncertain` for `settle` after its doubt ...
    `settle` is three of the model's slowest time constant, rounded up to
    whole ticks, unless given." and "A model whose memory does not fade has
    no such constant. With no `settle` given, its outputs are `good`".
    *Chosen:* a `thermal_mass` always has a `settle` (given, or its
    default). A `state_space` has one only if it is given; without one a
    doubt, a gap's among them, never shows in the state of its outputs.
    The words "stepped on an `uncertain` value" are taken to cover a direct
    input as well as a deferred one.

25. **A window that is `good` on few samples.** Rules 7.3.2 to 7.3.5.
    *Chosen:* the three cases are tried in the order 3, 5, 4 by counts
    alone. Under `only_new` the earlier condition that `n` ticks have run
    is gone with the old rule 7.3.7, so a window is `good` from the first
    tick on which it holds as many `good` samples as are needed. The oldest
    tick of the window is still time zero for `slope`, whichever samples
    the statistics are of.

26. **`min_good` with `only_new`.** Rule 7.3.8: "`min_good` has to be
    given". *Chosen:* the key has to be present; `min_good: 1` written out
    is accepted.

27. **`since_true` with `assume_false`.** Rule 7.6.2: "with `assume_false`
    an unusable input counts as not true, and the output is `uncertain`".
    *Chosen:* `uncertain` on the tick the input is unusable and on no
    other; with `unknown` the clock and the counters go on as with
    `assume_false`, and only the output differs.

28. **`latch`: `reset` true and `set` unusable.** Rule 7.6.3, first case:
    "The output is false, with the state of `reset`." *Chosen:* as
    written, so the output is `good` and false on a tick where `set` is
    `bad`.

## Part B. What I believe the text gets wrong

1. **The example at the end of 7.8 is not what the rules give.** "A plant
   driven through a controller by a setpoint that is `uncertain` on every
   tick is `uncertain` on every tick."
   - On tick 0 a plant with a deferred input gives its initial state, with
     no doubt yet: `good` (rules 7.8.1, 7.8.5, 7.8.8). Run: a `state_space`
     plant, a delay and a formula `sp - d` in one loop, `settle: 2s`, `sp`
     `uncertain` on ticks 0 to 4 → the plant is `good`, `uncertain`,
     `uncertain`, `uncertain`, `uncertain`.
   - A `state_space` plant that is not on a loop and has no `settle` is
     `good` on every tick (rule 7.8.6, second bullet). Run: `A: [[0.5]]`,
     `B: [1]`, `C: [1]`, `u` `uncertain` and 1 on ticks 0 to 2 → `y` is
     `good` 0, `good` 1, `good` 1.5, with `doubtful` 0, 1, 2.
   - With `settle: 0s` the same holds on a loop or off one: there are no
     ticks `d + 1` to `d + 0`. Run: the same plant with `settle: 0s` →
     `good` on ticks 0 to 3.

   The second and third are a value called `good` that rests on something
   doubtful taken in one tick before, which the head of section 7 says a
   block with finite memory does not do, and 7.11 does not list them.

2. **A `good` sample makes a slope worse (rules 7.3.5 and 7.3.6).** A
   window of 4 ticks with `min_good: 0.25` (one needed). Inputs per tick:
   `uncertain` 1, `uncertain` 2, `uncertain` 3, `uncertain` 4 → at tick 3,
   `mean` is `uncertain` 2.5 and `slope` is `uncertain` 1. Change only the
   first sample to `good` 1 → at tick 3, `mean` is `good` 1 and `slope` is
   `bad`: there is one `good` sample, the statistics are "of its `good`
   samples alone", and "A slope needs two of the samples the statistics are
   of". Better data gives a worse answer, and the `good` mean of 1 ignores
   three later samples that say 2, 3 and 4. More generally the value of
   every statistic jumps when the number of `good` samples crosses the
   number needed (run: 4 ticks, `min_good: 0.5`, inputs `good` 1,
   `uncertain` 10, `good` 3 → `mean` is `uncertain` 5.5 at tick 1 and
   `good` 2 at tick 2).

3. **The idiom 7.11 recommends hides a `bad` input.** "To set only on a
   `good` true, give the latch `b and ok`, where `ok` is an `all_good` of
   `b`." With `b` `bad`, `ok` is `good` and false, it decides the `and`
   (rule 7.1.2), and the latch is given a `good` false. Run: `b` per tick
   `good` false, `bad`, `bad`, `uncertain` true, `good` true → the latch's
   `y` is `good` false on ticks 0 to 3 and `good` true on tick 4, and its
   `doubtful` is 0 throughout. Without the idiom ticks 1 and 2 give `bad`
   and `doubtful` counts them. The section opens with "A problem at this
   tick is never hidden", and here the stricter thing the text tells the
   author to write hides one, and silences the counter that 7.11 offers
   in its place.

4. **The head of section 7 says an output is `good` within a
   `ride_through`.** See entry 14 of part A. Run: a `deadband` with
   `ride_through: 1s`, inputs `uncertain` 0, `good` 0.5, `bad` → tick 2
   is `uncertain` 0 by rule 7.4.3, where "Within it an output is `good`"
   says `good`.

5. **Rule 7.8.8 against rules 7.6.3 and 7.7.4 on what is used.** See entry
   2 of part A. "Every block but a formula uses every input it has" and "A
   `reset` that is unusable, or usable and false, is not used" cannot both
   hold for a latch or an integrator on a loop.

6. **Rule D against rule 7.1.2.** See entry 12 of part A: in `a or b` an
   `uncertain` operand that decided is, by rule D's own list, used, and the
   result is `good`.

7. **"gave an output that was not usable" (rule 7.8.8) with an estimator
   or a window on the loop.** See entry 1 of part A. As written, an
   estimator on a loop with a model block makes the loop's doubt every
   tick on which `innovation_<port>` is `not_ready`, which is every tick
   without a new measurement, so every model on that loop is `uncertain`
   for good.

8. **The introduction still describes the removed rule.** The second
   bullet under "What they found" reads: "It is now a taint on memory with
   a stated end (section 7), and an uncertain value carries the tick of
   what caused it, so that taint going round a loop runs out." Amendment 2
   says "An `uncertain` value no longer carries the tick of its cause."

9. **7.11 leaves out two things given up.** A `held_for` with
   `on_bad: hold` is `good` and true on the first usable tick after it ran
   through unusable ones (run: `time: 2s`, `hold_limit: 1s`, inputs
   `good` true, `good` true, `bad`, `good` true → tick 3 is `good` true),
   and a model with no `settle`, or with `settle: 0s`, is `good` one tick
   after stepping on an `uncertain` value (entry 1 above). Each has a
   counter, as the others in the list do.

## Round two

The text was revised after the report above. This part goes through the
28 entries of part A and the 9 of part B against `proposal.md` as it now
reads, and then lists what the revised text leaves open or gets wrong.
Quotations are from the revised `proposal.md`.

One thing changed in `impl.py`: an unusable output is a loop's doubt only
if a block of the loop reads that port (entry 1). Everything else the
revision says was already what `impl.py` did.

### Part A against the revised text

| Entry | Now | How |
| --- | --- | --- |
| 1. Which unusable outputs are a loop's doubt | Settled, the other way | "gave an output that was not usable to a block of the loop that reads it ... An output no block of the loop reads starts nothing". `impl.py` changed to this. See R1 below for what "reads" leaves open |
| 2. What a block on a loop uses | Settled, as chosen | "every other block counts as using every input it has, in either phase, whatever its own rule says of them" |
| 3. A doubt at tick `k` | Settled, as chosen | "a doubt at tick `k` is seen from tick `k + 1`. At tick `k` itself the loop is judged by its latest doubt before `k`" |
| 4. What a loop is; "holds a model" | Open | Unchanged. Whether an estimator on a loop is a model there is still not said |
| 5. "is given `settle`" | Settled, as chosen | "has `settle` written in the graph, and they are all the same number of ticks" |
| 6. Which values a delay gives as `good`, and when | Open | Unchanged: judged at the tick it gives, any `uncertain` value |
| 7. Delays "add up" | Open | Unchanged: the plain sum |
| 8. Deferred reads; "not `good`" | Settled in part | "in either phase" settles the deferred read. That a constant is not from outside, and that another loop's block is, are still not said |
| 9. A model on a loop keeps its counters | Settled, as chosen | "Its counters are its own" |
| 10. The loop's doubt and a save | Settled, as chosen | "Counters, and the doubt of a loop, are part of what a save holds ... A reset does" |
| 11. Rule D and the estimator | Open | Rule D's list now names what `all_good`, `count` and the counters use, and still not the estimator. 7.9.5 kept |
| 12. Rule D and two deciders | Settled, as chosen | "an `uncertain` operand beside a `good` one that decides by itself" is not used |
| 13. `count` and the counters | Settled, as chosen | "a window's `count` and the counters read states and not values, and are always `good`" |
| 14. `ride_through` as a tolerance | Settled, as chosen | "A `ride_through` is not one: a block riding through says `uncertain` while it does" |
| 15. A model's `doubtful` at tick `k` | Open | Unchanged: the step of tick `k` is counted from tick `k + 1` |
| 16. A gap and `doubtful` | Settled, as chosen | "A gap adds nothing to a model's `doubtful`" |
| 17. `held_for` counters on the tick it stops; held ticks | Open | Unchanged. 7.11 now says "`doubtful` says how much of the run it did not see", which agrees with counting the held ticks |
| 18. `since_true` and `held_for` at a gap | Open | "a rebase does not set them to zero" still stands beside "The clock is set to the gap's tick" and "The timer stops" |
| 19. `latch`: clearing, and `doubtful` on that tick | Open | Unchanged |
| 20. `hysteresis`: what a change is | Open | Unchanged |
| 21. `integrate`: `gaps` at a reset; counts while `bad` | Open | Unchanged |
| 22. A gap and a low-pass's doubt | Settled, as chosen | "Forgets what it held, and a low-pass its doubt" |
| 23. A low-pass at the tick of its doubt | Open | Unchanged; I see one reading only |
| 24. A model off a loop, "With `settle`" | Settled in part | 7.11 now lists "A model with no `settle`, or a `settle` of zero". That stepping on an `uncertain` direct input counts is still not said |
| 25. A window `good` on few samples | Settled in part | 7.11 now lists the jump and the `bad` slope. `good` from the first tick under `only_new` is still by inference |
| 26. `min_good` with `only_new` | Open | Unchanged |
| 27. `since_true` with `assume_false` | Open | Unchanged |
| 28. `latch`: `reset` true and `set` unusable | Open | Unchanged |

Open after round two: 4, 6, 7, 11, 15, 17, 18, 19, 20, 21, 23, 26, 27,
28, and the remainders of 8, 24 and 25.

### Part B against the revised text

| Finding | Now |
| --- | --- |
| 1. The closing example of 7.8 | Settled: "`uncertain` on every tick after the first: what it gives at a tick is its state from the tick before". The no-`settle` and `settle: 0s` cases are now in 7.11. The sentence is still not true of a plant with no `settle` off a loop, but 7.11 says so |
| 2. A `good` sample makes a slope worse | Kept, and now listed in 7.11 as given up. See R2 for what it does on a loop |
| 3. The idiom hides a `bad` input | Kept, and now said in 7.11, with the remedy ("reads `ok` as well") |
| 4. The head of section 7 on `ride_through` | Settled |
| 5. 7.8.8 against 7.6.3 and 7.7.4 | Settled: "whatever its own rule says of them" |
| 6. Rule D against 7.1.2 | Settled |
| 7. An estimator's `innovation_<port>` on a loop | Settled, unless a block of the loop reads that port |
| 8. The introduction | Settled |
| 9. Two things 7.11 left out | Settled: both are listed |

### New in round two

R1. **"a block of the loop that reads it": is reading the connection, or
    the use?** Rule 7.8.8: "gave an output that was not usable to a block
    of the loop that reads it ... For this, a formula uses what rule D
    says".
    - Reading A: a port is read if a block of the loop has an input
      connected to it, whatever that block does with it on the tick.
    - Reading B: for a formula, only if rule D says it used it on that
      tick.

    *Chosen:* A. "Uses" is defined for values "read from outside the
    loop", and "reads" is not qualified. Run: a `state_space` plant
    (`settle: 2s`), a delay of the plant's output (`initial: 0`), a
    formula `f2 = 1 / d` and a controller `when(en, a, 1)` with `a` from
    `f2` and `en` from outside, `good` and false on every tick. `f2` is
    `bad` on ticks 0 and 1 (it divides by zero) and the controller never
    takes that branch: its output is `good` 1 on every tick. Under A the
    plant is `good`, `uncertain`, `uncertain`, `uncertain`, `good` on
    ticks 0 to 4; under B it is `good` throughout.

R2. **A window on a loop can keep the loop in doubt for ever, with no
    input from outside at all.** This follows from rules 7.3.5, 7.3.6 and
    7.8.8 together, and I believe it is not meant. A `state_space` plant
    (`A: [[0.5]]`, `B: [1]`, `C: [1]`, `settle: 2s`), a window of the
    plant's output (`window: 2s`, `min_good: 0.5`, so one needed) and a
    controller `1 - m + 0 * s` reading the window's `mean` and `slope`.
    Nothing is read from outside.
    - Tick 0: one sample, `slope` is `bad`, the controller is `bad`: a
      doubt, and the plant misses a step.
    - Tick 1: the plant is `uncertain`. The window holds a `good` 0 and an
      `uncertain` 0: one `good` sample is enough, so it is `good`, of that
      sample alone, and `slope` is `bad` again: a doubt.
    - Ticks 2 and 3: two `uncertain` samples, `slope` usable.
    - Tick 4: the plant is `good` again, and the window holds an
      `uncertain` sample and a `good` one: `slope` is `bad`: a doubt.

    Run over 16 ticks, plant state / controller state: good/bad,
    uncertain/bad, uncertain/uncertain, uncertain/uncertain, and the same
    four again, for ever. Every time the loop recovers, the first `good`
    sample makes the window `good` on one sample, takes its slope away,
    and starts the next doubt. With the slope not read by the loop the
    same graph is `good` on every tick.

R3. **The new last-but-one item of 7.11 is not true of a loop that passes
    through a model.** "An unusable value that gets into a loop through a
    delay goes round for good, with or without a model, unless a block of
    the loop has a fallback or rides through." Rule 7.8.5: "A model never
    gives up its state. Its outputs are always usable". A model on the
    loop does not pass an unusable value on, with no fallback and no
    `ride_through`. Run: the plant above, a delay of its output
    (`initial: 0`) and a controller `sp - d`; `sp` is `good` 1 except on
    tick 2, where it is `bad`. Per tick, plant / delay / controller:
    - 0: `good` 0 / `good` 0 / `good` 1
    - 1: `good` 1 / `good` 0 / `good` 1
    - 2: `good` 1.5 / `good` 1 / `bad`
    - 3: `uncertain` 1.5 / `good` 1.5 / `good` -0.5
    - 4: `uncertain` 0.25 / `uncertain` 1.5 / `uncertain` -0.5
    - 5: `good` -0.375 / `good` 0.25 / `good` 0.75

    Nothing goes round. The item holds only for a cycle of the loop that
    does not pass through a model's output, or for a loop with no model.

## Round three

The text was revised again. This part says what the revision settles of
round two's R1 to R3 and of the entries still open, and then lists every
place the revised text leaves a choice or, as I read it, gets something
wrong. Each example was run on `impl.py`. Quotations are from the revised
`proposal.md`.

### R1 to R3 of round two

- **R1** (is "reads" the connection or the use): settled, as chosen. "on a
  port that a block of the loop is connected to ... whether or not that
  block used it."
- **R2** (a window on a loop keeps it in doubt for ever): settled, by two
  changes together. Rule 7.3.6 now gives a slope "of its usable samples
  ... `uncertain`" where there are fewer than two `good` ones, and rule
  7.8.8 has a window on a settled loop count an earlier `uncertain` sample
  as `good`. Run, the same graph as R2, plant state / controller state per
  tick: good/bad, uncertain/uncertain, uncertain/uncertain, then good/good
  from tick 3 on.
- **R3** (an unusable value "goes round for good, with or without a
  model"): settled. 7.11 now says it of a loop with no model block, and "A
  model block on the cycle ends both, since its outputs are always
  usable."

### Earlier entries the revision settles

- Part A entry 4 (an estimator on a loop): settled. "a loop that holds a
  model block and an estimator is refused until section 7.9 is amended".
  A loop with an estimator and no model block is not a loop of rule 7.8.8
  and is accepted.
- Entry 7 (delays "add up"): the sum now also takes "the lengths of its
  windows and the `settle`s of its low-passes, all in ticks". Still the
  plain sum over the loop.
- Entry 11 (rule D and the estimator): settled as chosen. Rule D names the
  estimator as an exception, and 7.11 lists it.
- Entry 15 (a model's `doubtful` at tick `k`): settled as chosen. "at tick
  `k` `doubtful` counts the steps of the ticks before `k`, one tick behind
  `elapsed`."
- Entry 18 (`since_true` and `held_for` at a gap): settled as chosen. "a
  rebase does not set them to zero beyond what the table says."
- Entry 21 (`integrate`, `gaps` at a reset): settled the other way. "A gap
  whose tick is the tick of the reset is counted." `impl.py` changed.
- Entry 24 (a model with no `settle`): unchanged, and 7.11 lists it.

Still open, text unchanged: 6 (in part, see T2), 8 (a constant; another
loop's block), 17, 19, 20, 23, 25 (`good` from the first tick under
`only_new`), 26, 27, 28.

### What the revised text leaves to choose

T1. **`gaps` of a `held_for` whose timer is not running.** The head of
    section 7: "`gaps` ... the gaps (section 8) whose tick is the one
    `elapsed` counts from, or a later one." Rule 7.6.1: `elapsed` and
    `doubtful` "are zero while it is not running". With no timer running
    there is no tick that `elapsed` counts from.
    - Reading A: `gaps` is zero while the timer is not running.
    - Reading B: it keeps counting gaps since the timer last stopped, or
      since the first tick.

    *Chosen:* A. Since a gap stops the timer, a `held_for`'s `gaps` is then
    1 for a run that began on a gap's tick and 0 otherwise. Run: `time:
    1s`, `on_bad: reset`, input true at 0 s and 1 s, a stall to 10 s, then
    11 s and 12 s. With the input true throughout, (`y`, `elapsed`, `gaps`)
    per tick is (false, 1, 0), (false, 2, 0), (false, 1, 1), (false, 2,
    1), (true, 3, 1). With the input false at the gap's tick and true
    after, `gaps` is 0 on every tick: nothing on the block says there was
    a gap, although the timer it stopped had been running.

T2. **Is "counts as `good`" judged tick by tick, or once?** Rule 7.8.8: "a
    delay, a window or a low-pass in it counts what it took in as
    `uncertain`, at an earlier tick, as `good`, at any tick where the loop
    is not within `settle` of its doubt."
    - Reading A: tick by tick. A sample that was counted `good` while the
      loop was settled is `uncertain` again if the loop has a new doubt
      while the window still holds it; a low-pass's own doubt is ignored
      at a settled tick and not erased.
    - Reading B: once the loop has settled, the sample is `good` for as
      long as it is held, and the low-pass's doubt is gone.

    *Chosen:* A, for "at any tick where". Run: a `state_space` plant
    (`settle: 3s`), a window of its output (`window: 3s`, `min_good: 0.6`,
    two needed) and a controller `sp + 0 * m`; `sp` is `uncertain` at
    ticks 1 and 5. The plant is `uncertain` on ticks 1 to 4 and `good` at
    tick 5, where the window, holding samples of ticks 3, 4 (`uncertain`
    when taken) and 5, is `good`. At tick 6 the loop is within `settle` of
    tick 5 and the window holds 4, 5 and 6: under A it has one `good`
    sample and is `uncertain` (mean 1.854..., of all three); under B it
    has two and is `good`, with a mean of two samples. The same question
    stands for a low-pass on a loop whose input is `good` while the loop
    is in doubt again; I did not build a graph for that one.

T3. **The slope with fewer usable samples than are needed.** Rule 7.3.3:
    "With fewer usable samples than are needed, every output but `count`
    takes the worst state among its ticks that hold none." Rule 7.3.6:
    "Where the window holds fewer than two `good` samples and at least two
    usable ones, its slope is of its usable samples and is `uncertain`,
    whatever rule 5 says of the rest." Rule 6 sets aside rule 5 and does
    not mention rule 3.
    *Chosen:* rule 3 governs. Run: 4 ticks, `min_good: 0.75` (three
    needed), inputs `good` 1, `good` 2, `good` 3 → `slope` is `not_ready`,
    `not_ready`, `good` 1. The other reading gives a slope at tick 1 from
    two samples, in a window whose mean is `not_ready`.

T4. **A low-pass's default `settle` on a loop.** Rule 7.8.8: "the
    `settle`s of its low-passes, all in ticks". *Chosen:* the `settle` it
    has, given or not: a low-pass with `tau: 1s` and no `settle` counts 3
    ticks at a period of 1 s, and is refused on a loop whose `settle` is
    `2s`. The other reading counts only a `settle` that is written, as the
    model blocks' has to be.

T5. **`gaps` where a count starts again at the gap's tick.** Section 8.6:
    "Where a block's count starts again at the gap's tick, as
    `since_true`'s does, or at a later tick, as `held_for`'s does, `gaps`
    starts again with it, at one if the gap's tick is the tick it counts
    from." *Chosen:* the same is done for a hysteresis that changes, and a
    latch that is cleared, on a gap's tick (`gaps` is 1 there), and both
    start again at 0 when the change or the clearing comes at a later
    tick. A model's `gaps` counts every gap since the first tick.

### What I believe the revised text gets wrong or leaves unsaid

W1. **A window on a loop is the loop's doubt at every start and after
    every gap, by its own filling.** A window with more than one sample
    needed gives `not_ready` until it holds that many (rule 7.3.3), and a
    gap empties it (section 8.6). On a loop that is "an output that was
    not usable on a port that a block of the loop is connected to", so the
    loop is in doubt for `needed - 1` ticks at the start, and the model
    that reads through it misses those steps. Run, the graph of T2 with
    `sp` `good` throughout except as said: at tick 0 the window's `mean`
    is `not_ready`, and the plant is `uncertain` on ticks 1 to 3 on that
    account alone. This may be meant; the text does not say so, and the
    row for a window in 8.6 gives no hint that a gap costs such a loop
    `settle` and then the window's filling.

W2. **Section 6 says more than the blocks do.** "each block that counts
    gives `gaps`. A total or a detector that ran across one is `good`, and
    says so only there." A `held_for` whose timer was stopped by a gap and
    starts again a tick later says nothing of it anywhere: `gaps` is 0
    (run under T1). That follows from "`gaps` starts again with it", and
    the sentence in section 6 reads as if `gaps` always showed a gap.

## Round four

The text was tightened on T1 to T5, W1 and W2 of round three. Quotations
are from the revised `proposal.md`; each example was run on `impl.py`.

### T1 to T5, W1, W2

| Entry | Settled? | Code changed? |
| --- | --- | --- |
| T1. `gaps` of a `held_for` that is not running | Yes, as chosen: "where `elapsed` is zero because nothing is being counted, as for a `held_for` whose timer is not running, `gaps` is zero too" | No |
| T2. "counts as `good`": tick by tick, or once | Yes, the other way: "becomes `good`, and stays so: a later doubt of the loop does not turn it back" | Yes: delay, window and low-pass, below |
| T3. The slope with fewer usable samples than needed | Yes, as chosen: "Rule 3 comes first" | No |
| T4. A low-pass's default `settle` on a loop | Yes, as chosen: "written or not" | No |
| T5. `gaps` where a count starts again at the gap's tick | Yes, as chosen: "as that of a hysteresis that changes or a latch that is cleared on that tick does" | No |
| W1. A window still filling is the loop's doubt | Yes: the text now says so, "a loop with such a window in it is in doubt from the start, and again after every gap" | No |
| W2. Section 6 on `gaps` | Yes: "A timer the gap stopped shows nothing of it once it starts again: the call's report is the only word of that" | No |

What changed in `impl.py` for T2 (rule 7.8.8). At every tick where the loop
is not within `settle` of its doubt, before the block takes anything in:

- a delay turns every `uncertain` value it holds to `good`, not only the
  one it gives at that tick;
- a window turns every `uncertain` sample it holds to `good`, in what it
  keeps;
- a low-pass clears its doubt.

Run, the graph of T2 (plant with `settle: 3s`, a window of 3 ticks with
two needed, `sp` `uncertain` at ticks 1 and 5): at tick 6 the window is now
`good`, with a mean of 1.8125, the samples of ticks 4 and 5; in round three
it was `uncertain`, with a mean of all three.

### What the new wording leaves to choose

F1. **When a held value "becomes `good`".** Rule 7.8.8: "at a tick where
    the loop is not within `settle` of its doubt, what a delay, a window
    or a low-pass in it took in as `uncertain` at an earlier tick becomes
    `good`".
    *Chosen:* at each such tick, in the first phase, before the block
    takes in that tick's own value; so a delay of two ticks turns the
    value it will give a tick later as well as the one it gives now. Run:
    a plant (`settle: 2s`), a delay of two ticks and a controller
    `sp - d`, `sp` `uncertain` at ticks 1 and 4. At tick 4 the loop has
    settled and the delay holds 1.5 and 1.75, both taken in as
    `uncertain`. At tick 5 the loop is within `settle` of tick 4, and the
    delay gives the 1.75 as `good`. The other reading turns only what is
    given at a settled tick, and gives that 1.75 as `uncertain`. "and
    stays so" reads to me as the first; the sentence "A delay gives such a
    value as `good`" could be read as the second.

F2. **A value a gap made `uncertain` in a delay on a loop** (part A, entry
    6) is still not covered by "took in as `uncertain`". *Chosen:* it is
    turned like any other. It cannot be seen: the gap is the loop's doubt,
    and the delays of a loop are no longer than its `settle`, so such a
    value is given before the loop settles.

### What I believe the new wording gets wrong or leaves unsaid

G1. **"A window on the loop that is still filling" is not every window.**
    The new item says "a loop with such a window in it is in doubt from
    the start, and again after every gap". That holds only where more than
    one sample is needed and a block of the loop is connected to a port
    that the filling makes unusable. Run: a plant (`settle: 2s`), a window
    of its output of 2 ticks and a controller `1 - m` on its `mean`, with
    ticks at 0 to 4 s, a stall to 20 s, then 21 to 24 s. Plant state /
    mean state per tick:
    - `min_good: 1` (two needed): good/not_ready, uncertain/uncertain,
      uncertain/uncertain, good/good, good/good, then at the gap
      uncertain/not_ready, uncertain/uncertain, uncertain/uncertain,
      good/good, good/good. In doubt from the start: the plant is
      `uncertain` on ticks 1 and 2 with nothing wrong anywhere.
    - `min_good: 0.5` (one needed): good/good on ticks 0 to 4, then
      uncertain/uncertain on the gap's tick and the next, by the gap
      alone, and good/good after. Never in doubt from filling.

    The text is right for the first and reads as if it were so for both.
    It also does not say that the first case costs one tick more than
    `settle` after a gap (three `uncertain` ticks against two): the
    filling window is a doubt at the gap's tick itself, one tick later
    than the gap's own doubt.

Still open, text unchanged since round two: part A entries 8 (a constant;
another loop's block), 17, 19, 20, 23, 25 (`good` from the first tick
under `only_new`), 26, 27, 28.

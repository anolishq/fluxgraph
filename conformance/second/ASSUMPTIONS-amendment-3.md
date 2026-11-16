<!-- markdownlint-disable MD029 -- entries keep one numbering -->
# Assumptions made in bringing `impl.py` up to Amendment 3

Every place where the text amended by "Gaps" (rules 6.5, 6.9, 6.10 and
6.11, the Counters paragraph of section 7, 7.6.2, 7.8.4, 7.8.6, 7.11,
section 8 rules 3 to 6 with its table, and the `delay` entry of Appendix
A) did not say what to do, could be read two ways, or disagreed with
another passage, and what `impl.py` does. The ones most likely to make two
honest implementations disagree come first. Rule numbers are those of
`proposal.md`. Quotations are from `proposal.md`.

Part A is the guesses. Part B is what I believe the text gets wrong, each
with a small example run on `impl.py`. In the examples the period is 1 s.

## Part A. Where the text had to be guessed

1. **A gap that passed over no tick: the table against the rule it
   illustrates.** Rule 8.6: "Each block does to what it remembers what
   that many ticks would have done, had each been run with nothing usable
   on any of its inputs." Rule 8.5: "if none would have been due, none is
   passed over and the next tick runs." So a `rebase` with a length under
   one and a half periods tells every block that 0 ticks were passed
   over, and by the rule nothing would have been done. The table's column
   for `n` ticks says, with no condition on `n`: "`held_for` | With
   `reset` the timer stops", and "Model block | ... The tick before the
   one that runs is a doubt".
   - Reading A: the table as written. At any gap a `held_for` with
     `reset` stops, and a model has a doubt, whatever `n` is.
   - Reading B: the rule. With `n` of 0 neither happens.

   *Chosen:* A, for those two cells; every other cell is in terms of `n`
   and does nothing at 0 (a delay moves on no place, a deadband holds,
   `held_for` with `hold` runs on). See B3 for what A then gives.

2. **A model after a gap of no known length: what becomes of the last
   usable values.** Rule 7.8.4: "After a gap of no known length it does
   not, until the input is usable again." Rule 7.8.5: "Where its outputs
   read a direct input that is unusable, they are worked out on that
   input's last usable value". The sentence "a model keeps the last usable
   value of each input" was taken out of the paragraph after the table.
   - Reading A: the last usable values are kept. Only the ride-through of
     the step is stopped: the count of unusable ticks is put past
     `ride_through`, and one usable tick puts it right.
   - Reading B: the last usable values are forgotten, so that a direct
     input that is unusable after such a gap is worked out "on zero", as
     for one that "has had none".

   *Chosen:* A. Run: a `state_space` with `A: [[0.5]]`, `B: [1]`,
   `C: [1]`, `D: 1`; `u` is `good` 3 at tick 0; `rebase()`; a call with
   nothing written → `y` is `uncertain` 6 (the state 3, and the last `u`
   of 3). Under B it is `uncertain` 3.

3. **A `restore` after a `rebase` that gave a length.** Rule 8.5: "A
   second `rebase` before the call does away with what was written since
   the first, and its length, or its having none, is the one that counts."
   Nothing is said of a `restore` that follows a `rebase(length)` before
   the call.
   *Chosen:* the restore puts things back to "nobody knows"; the length
   went with the rebase it was given to. A `rebase(length)` after a
   `restore` is the usual case and gives the restore that length. The
   other reading keeps the earlier length.

4. **`since_true` after a gap of no known length, with `on_bad:
   unknown`.** Rule 7.6.2: "After a gap of no known length (rule 8.6) the
   input was last true longer ago than `time`: the output is true until
   the clock is next set, and the counts start at the gap's tick." The same
   rule: "with `unknown` the output takes the input's state."
   *Chosen:* "the output is true" gives the value, and the state is still
   the block's rule: with an unusable input it is `uncertain` and true
   under `assume_false`, and takes the input's state, with no value, under
   `unknown`. Run: `time: 3s`, `on_bad: unknown`, input `good` and true at
   tick 0, `rebase()`, a call with nothing written → `not_ready`. The
   other reading gives a true there.

5. **`since_true` after a gap of no known length: two clocks.** The same
   sentence. The value needs "longer ago than `time`", and the counts
   need a tick to count from. *Chosen:* the block remembers that the
   input was last true too long ago, until a usable true sets the clock;
   `elapsed` counts from the gap's tick, `doubtful` starts at zero there
   and `gaps` at one. So for the first `time` after such a gap the output
   is true while `elapsed` is no more than `time`.

6. **The ticks a model's inputs were unusable across a gap.** Rule
   7.8.4: "counted as in rule 7.4.3, ticks a gap passed over among them."
   *Chosen:* the count of every input goes up by `n`, whatever it was
   before, so an input that was usable at the last tick run has been
   unusable for `n` ticks at the gap, and for `n + 1` at the tick that
   runs if it is unusable there. A usable input at the tick that runs sets
   the count to zero and the model steps on it.

7. **`held_for` with `hold`: what the stretch is measured against.** The
   table: "the unusable stretch grows by `n`: within `hold_limit` the
   timer runs on and `doubtful` goes up by `n`, and past it the timer
   stops". *Chosen:* the stretch is the unusable ticks in a row before the
   gap plus `n`; it runs on if that is no more than `hold_limit`, and the
   tick that runs then adds one more if its input is unusable. A timer
   that runs on across a gap counts it in `gaps`; before this amendment a
   gap always stopped the timer, so `gaps` could only be 0 or 1.

8. **A deadband or a low-pass across a gap.** The table: "If the last
   tick passed over is within `ride_through` of its last usable input, it
   holds what it held". *Chosen:* the count of unusable ticks in a row
   goes up by `n`; it holds if that is no more than `ride_through`, and
   forgets otherwise. A low-pass that holds takes the count into the `m`
   of rule 7.4.5 on its next usable input. With `n` of 0 it holds,
   whatever `ride_through` is. A block that holds nothing does nothing.

9. **What is refused as a length.** Rule 6.11: "a `rebase` whose length
   is not a whole number of nanoseconds, is less than zero, or does not
   fit in 64 bits, signed." *Chosen:* as for a time: a Python `int` and
   not a `bool`; `2.0` is refused. It is refused before any tick has run
   too, where a `rebase` otherwise only does away with the writes waiting.
   Zero is accepted, and is not "no length": it is a gap that passed over
   none.

10. **What a call reports at a rebase that passed over none.** Rule 6.10:
    "whether it was a gap, and if so how many ticks it passed over, or
    that nobody knows". *Chosen:* a gap, with 0 passed over; `None` only
    where no length was given. Every block's `gaps` goes up by one.

11. **A window told that nobody knows.** The table: "None of its ticks
    holds a sample". *Chosen:* they count as `not_ready` in rule 7.3.3, as
    a tick "from before a gap" does. Told `n`, the samples it holds stay
    and keep their states; under `only_new` the sample time it last took
    is kept at a stall and forgotten at a rebase (rule 8.5), with or
    without a length.

12. **A delay at a rebase with a length.** The table has it move on `n`
    places; rule 8.5 has "the values a delay holds at that moment lose
    their sample times". *Chosen:* both: it moves on, and what is left has
    no sample time.

13. **The numbers of ticks after a gap of no known length.** Rule 6.5:
    "Tick `k` is `k` periods after tick 0." Rule 8.5: "the tick that runs
    is numbered one more than the last tick run". *Chosen:* after any
    rebase the tick that runs is the one the later ticks are counted from,
    by number and by time, and 6.5 holds only up to the first rebase.

## Part B. What I believe the text gets wrong

1. **The estimator does not do "what that many ticks would have done".**
   Rule 8.6 says each block does that; the table says "`estimator` | Each
   state's variance grows by its `p0`" and, for a gap of no known length,
   "The same". A tick with nothing usable grows each variance by `q` times
   the period (rule 7.9.2). Run: `A: [[1]]`, `q` 1, `p0` 4, no
   measurement, `max_catch_up` 1, tick 0 and then one call:
   - at 2 s (1 passed over): the variance is 9;
   - at 3 s (2 passed over): 9;
   - at 500 s (499 passed over): 9;
   - with `max_catch_up` 100 and a call at 50 s, 50 ticks run and none is
     passed over: 54.

   So an estimator is more sure of itself after eight minutes nobody saw
   than after fifty seconds that were run, and a gap of one tick costs it
   the same as a gap of any length. The row was not touched by this
   amendment, and no longer agrees with the rule above it.

2. **"Nobody knows" is "more than anything the block counts" for every
   block but the total.** Rule 8.6: "Where nobody knows the number, it is
   more than anything the block counts, and nothing is added to a count
   but one to `gaps`." That is how a timer stops, a `since_true` goes
   true, a model does not ride through and a delay empties. A total's
   `max_missed` is a thing it counts against, and the table says only
   "The total is unchanged". Run: `integrate` of a constant 1 with
   `max_missed: 2s`, tick 0, then:
   - a stall of an hour → the total is `bad`, `missed` 3599, `gaps` 1;
   - `rebase` with a length of an hour → the same;
   - `rebase()` → the total is `good` 2, `missed` 0, `gaps` 1.

   A host that does not say how long gets a `good` total out of the very
   gap that, said, makes it `bad`. Section 6 owns to "nothing missed"; it
   does not say that `max_missed` is passed by.

3. **A gap that passed over nothing stops one timer and not the other.**
   See entry 1 of part A. Run: `held_for`, `time: 1s`, input `good` and
   true at ticks 0, 1, 2; `rebase(1s)` (one tick would have been due, so
   none is passed over); the input written true again; a call. With
   `on_bad: reset` the output is `good` false and `elapsed` is 1: the
   timer stopped and started. With `on_bad: hold`, `hold_limit: 1s`, the
   output is `good` true and `elapsed` is 4. No tick went unseen, and
   `reset` and `hold` differ only in what an unusable input does. A
   `thermal_mass` with `settle: 2s` through the same `rebase(1s)` is
   `uncertain` for two ticks. If that is meant (the clock stepped, and the
   inputs were cleared), the rule in bold does not give it; if the rule is
   meant, the two cells need "if `n` is more than zero".

4. **7.11: "Every other block ... is `good` on the far side."** "A gap
   makes only a model with `settle` `uncertain`. Every other block does
   what the ticks nobody saw would have done to it, and is `good` on the
   far side." Not so for a window or a delay, by the same amendment. Run,
   one tick passed over (calls at 0, 1, 2 s with a `good` 1 written, then
   at 4, 5, 6 s):
   - a window of 3 ticks with the default `min_good` gives `mean` as
     `not_ready`, `not_ready`, `good` 1;
   - a delay of 2 ticks gives `good` 1, `not_ready`, `good` 1.

   The next item of 7.11 says so of a delay; the sentence before it should
   not say "every other block".

5. **The limit on catching up now turns on a tick for a delay.** Section
   6 says of the limit: "Just under it the ticks are run on what stood;
   just over it they are passed over. The two agree once the inputs have
   grown too old to use". They do not agree for a delay or a window fed by
   an input with `max_age: none`, or by a constant: run on what stood, a
   delay goes on giving values; passed over, it gives `not_ready` for
   each of those ticks, and by 7.11 a running value kept through it is
   `not_ready` for good. Run: a formula `p + 1` and a delay with
   `initial: 0`, `max_catch_up` 1; calls at 0 s and 1 s give 1 and 2; a
   call at 3 s (one passed over) gives `not_ready`, and so does every
   call after it. With `max_catch_up` 2 the same calls give 1, 2, 4.

## Round two

The text was revised on the findings and on several of the assumptions
above. Quotations are from the revised `proposal.md`; each example was run
on `impl.py`, with a period of 1 s.

### Part A against the revised text

| Entry | Settled? | Code changed? |
| --- | --- | --- |
| 1. A gap that passed over no tick | Yes, the other way: "a block does nothing but add one to `gaps`, whatever the table says: no timer stops and no model has a doubt" | Yes: `held_for` with `reset`, the model block and a loop's doubt. See R1 for the estimator |
| 2. A model's last usable values after an unknown gap | Yes, as chosen: "It keeps the value for rule 5" | No |
| 3. A `restore` after a `rebase` with a length | Yes, as chosen: "A restore puts back \"nobody knows\", whatever `rebase` said before it" | No |
| 4. `since_true`, `on_bad: unknown`, after an unknown gap | Yes, as chosen: "the output's value is true, with the state the rule above gives it" | No |
| 5. `since_true`: two clocks | Open: unchanged. The value is true and `elapsed` counts from the gap's tick | No |
| 6. The ticks a model's inputs were unusable across a gap | Open: unchanged | No |
| 7. `held_for` with `hold`: the stretch | Open: unchanged | No |
| 8. A deadband or low-pass across a gap | Open: unchanged | No |
| 9. What is refused as a length | In part: "A length of zero is a length." What a whole number is, is as for a time | No |
| 10. A rebase that passed over none reports a gap, with 0 | Yes, as chosen, by the new sentence of 8.6 | No |
| 11. A window told that nobody knows | Open: unchanged | No |
| 12. A delay at a rebase with a length | Yes, as chosen: "a delay both moves on and loses the sample times of what it still holds" | No |
| 13. Tick numbers after a rebase | Yes, as chosen: "Until a rebase, tick `k` is `k` periods after tick 0" | No |

### Part B against the revised text

| Finding | Now | Code changed? |
| --- | --- | --- |
| 1. The estimator and the length of a gap | Kept, and said: "This is not what `n` ticks would have done, and stands until section 7.9 is amended" | No, but see R1 |
| 2. "Nobody knows" and `max_missed` | Settled: "`bad` likewise after a gap of no known length (rule 8.6), which is more than any `max_missed`" | Yes: an `integrate` with `max_missed` is `bad` after such a gap, until a reset |
| 3. A gap that passed over nothing | Settled, by the rule: nothing but one to `gaps` | Yes, as entry 1 |
| 4. 7.11, "every other block is `good`" | Settled: a window short of samples and a delay with nothing to give are named | No |
| 5. Running against passing over, for a delay | Settled: "A block that reads only constants, or an input with no maximum age, would have gone on working through ticks that were run, and does not through ticks passed over" | No |

### What the new wording leaves to choose

R1. **The estimator where none was passed over.** Rule 8.6: "Where the
    number is zero ... a block does nothing but add one to `gaps`,
    whatever the table says". The table: "`estimator` | Each state's
    variance grows by its `p0`, whatever `n` is."
    - Reading A: the sentence of the rule, which says it overrides the
      table: at a gap that passed over none the variance does not grow.
    - Reading B: the row, "whatever `n` is": it grows by `p0` at every
      gap.

    *Chosen:* A. Run: `A: [[1]]`, `q` 1, `p0` 4, no measurement; tick 0
    gives a sigma of 2; then `rebase(0)` and a call → the variance is 5
    (one period of `q`) under A, and 9 under B. With `rebase(2s)` (one
    passed over), and with `rebase()`, it is 9 either way.

R2. **A reset at the tick of a gap of no known length.** Rule 7.7.2:
    "`bad` likewise after a gap of no known length ... until a reset".
    Rule 7.7.4: a usable, true `reset` "returns the total and all four
    counts to zero before that tick's addition".
    *Chosen:* a reset on the gap's own tick ends it: the block is told of
    the gap before the tick runs, and the reset comes in the tick. Run:
    `max_missed: 2s`, a constant 1, `rebase()`, and a true `reset` at the
    call → `good` 1, `gaps` 1. The other reading holds the total `bad`
    for that tick.

R3. **What a rebase forgets where none was passed over.** Rule 8.6: "a
    block does nothing but add one to `gaps`". Rule 8.5: "every sample
    time a block remembers or holds is forgotten", before the tick of any
    rebase.
    *Chosen:* 8.5 is of the rebase and not of the gap, and still holds: a
    window with `only_new` and an estimator forget the sample times they
    remember, and a delay's values lose theirs, at `rebase(0)` as at any
    other. Run: a window with `only_new` takes a sample stamped 100 s;
    `rebase(0)`; a sample stamped 50 s is written; the call → `count` is
    2: the first sample is still held, and the second, stamped earlier, is
    taken as new. Under the other reading the block does nothing, the
    sample time stays, and `count` is 1.

### What I believe the new wording gets wrong

W1. **"as after a rebase whose length is under half a period".** Rule
    8.6 gives that as the case where the number is zero. By rule 8.5 a
    length from half a period to just under one and a half is one tick
    due: "The last of them is the tick that runs, and the rest are passed
    over", so none is passed over there either. Run: `rebase(1s)` then a
    call → the report says a gap with 0 passed over, and tick 2 runs after
    tick 1. The rule is right ("Where the number is zero"); the example
    names only half of the cases, and a reader who takes it for the
    definition stops a timer at `rebase(1s)` that the rule does not.

W2. **A total that is `bad` on a count of zero.** Rule 7.7.2 now makes
    the total `bad` after a gap of no known length, "which is more than
    any `max_missed`", while by rule 8.6 "nothing is added to a count but
    one to `gaps`". Run: `max_missed: 2s`, a constant 1, tick 0,
    `rebase()`, a call → the total is `bad`, `missed` is 0, `gaps` is 1,
    and so on every tick until a reset. A graph that tests `missed`
    against a limit of its own sees nothing, and the only sign of why the
    total is `bad` is `gaps`, which a gap of known length raises as well.
    The text says "`missed` says what it lacks" in the same rule; here it
    does not.

## Round three

The text was revised after an independent review. Quotations are from the
revised `proposal.md`; each example was run on `impl.py`, with a period of
1 s.

### R1 to R3, W1, W2 of round two

| Entry | Settled? | Code changed? |
| --- | --- | --- |
| R1. The estimator where none was passed over | Yes, the other way: "Each state's variance grows by its `p0`, whatever `n` is, zero among it", and rule 8.5: "an estimator's variance grows (rule 6) at every rebase" | Yes: it grows at every gap |
| R2. A reset at the tick of a gap of no known length | Yes, as chosen: "a reset at the gap's own tick ends that as any reset does" | No |
| R3. What a rebase forgets where none was passed over | Yes, as chosen, and further: "What rule 5 says of a rebase holds all the same: nothing stands, every sample time is forgotten, a window with `only_new` is emptied and an estimator's variance grows" | Yes: a window with `only_new` is now emptied at every rebase |
| W1. "under half a period" | Yes: now "under a period and a half" | No |
| W2. A total `bad` on a count of zero | Kept, and said: "though `missed` cannot say so and only `gaps` shows it" | No |

### What else changed in `impl.py`

- **Rule 8.6, the Model row.** "For each of those ticks, in order, it
  steps on the last usable value of every input while each is within
  `ride_through` (rule 7.8.4), and takes no step from the first tick where
  one is not." In round two it took none of those steps. Now, told `n`,
  it goes through the `n` ticks in order: every input's count of unusable
  ticks goes up by one, and it steps on the held values if every input
  has had a usable value and is within `ride_through`. `doubtful` and
  `elapsed` go up by `n` as before. Told nobody knows, it takes no step.
- **Rule 8.5.** "a window with `only_new` keeps no sample from before a
  rebase": it is emptied at a rebase with a length, with a length of zero
  and with none. At a stall it keeps what it holds. A window without
  `only_new` is not touched by this.

The Counters paragraph, 7.3.3, the window item of 7.8.8 and the two items
of 7.11 say what `impl.py` already did.

Still open from part A, text unchanged: 5 (`since_true`, two clocks), 7
(`held_for` with `hold`, the stretch), 8 (a deadband or low-pass across a
gap), 9 (what a whole number is, for a length), 11 (see T1). Entry 6 (the
ticks a model's inputs were unusable across a gap) is settled as chosen by
the new Model row.

### What the new wording leaves to choose

T1. **What the ticks of a window count as, told that nobody knows.** Rule
    7.3.3 used to say that a tick "from before a gap" counts as
    `not_ready`; it now says "A tick from before the graph started, or one
    a gap passed over (rule 8.6), holds none and counts as `not_ready`."
    After a gap of no known length the table says "None of its ticks holds
    a sample", and those ticks are neither from before the graph started
    nor ticks a gap is known to have passed over.
    *Chosen:* they count as `not_ready`, as before. Run: a window of 4
    ticks with two needed, filled with `good` samples; `rebase()`; a
    `good` sample written; the call → `mean` is `not_ready` and `count`
    is 1. The other reading has no state to give, since rule 3 asks for
    "the worst state among its ticks that hold none".

T2. **A model's inputs given a constant, for a tick passed over.** Rule
    8.6: "had each been run with nothing usable on any of its inputs",
    and the Model row: "the last usable value of every input while each is
    within `ride_through`". A constant is `good` on every tick that runs
    (rule 4.7).
    *Chosen:* a constant is an input like any other here: for a tick
    passed over it is held, and counts against `ride_through`. Since every
    input's count goes up together and a constant's starts at zero, it is
    never the one that stops the stepping, so I could find no graph where
    the two readings differ; I note it because the text does not say.

### What I believe the new wording gets wrong

V1. **Rule 7.8.6 still says a tick passed over is a step not taken.** "A
    tick a gap passed over is a step not taken, and is counted." The Model
    row of 8.6 now has the model step on held values for those ticks
    while it is within `ride_through`. Run: a `thermal_mass` (`power`
    from an input, `ambient` 20, `thermal_mass` 10, `heat_transfer` 1,
    `initial` 20, `ride_through: 10s`), `power` `good` 10 at tick 0, then
    one call at 6 s:
    - `max_catch_up` 1 (five passed over): `temp` is `uncertain`
      24.5118..., `doubtful` 5, `elapsed` 7;
    - `max_catch_up` 100 (all six ticks run, on the 10 that stood): `temp`
      is `good` 24.5118..., `doubtful` 0, `elapsed` 7.

    The state is the same to the last digit: five steps were taken across
    the gap. They are steps on a held value, which rule 7.8.6 counts in
    `doubtful` already, so the count is right; the words "a step not
    taken" are not, and with `ride_through` of zero they are.

V2. **The same input, held, is `good` when run and `uncertain` when passed
    over.** From the run under V1: the two calls differ only in
    `max_catch_up`, the model takes the same steps on the same value, and
    one answer is `good` with `doubtful` 0 while the other is `uncertain`
    with `doubtful` 5. That is the text as it stands (a value that stands
    with no maximum age is usable on a tick that runs, and nothing is
    usable on a tick passed over), and section 6 says so of blocks in
    general. Written bad at 1 s instead, so that it is held either way,
    the two agree: `uncertain` 24.5118..., `doubtful` 5 in both. I record
    it because the Model row was rewritten to make passing over and
    running agree, and for an input that merely stands they still do not
    agree in state.

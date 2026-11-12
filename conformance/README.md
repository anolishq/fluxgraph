# Conformance for the version 2 semantics (proposal)

Tests of [the version 2 proposal](../docs/semantics_spec_v2.md), third
revision as amended, not of the library. Nothing here is built or run by
the library's presets.

The third revision did not pass review, and is being amended a section at
a time. Everything here follows the text as amended so far. The rules still
to be amended are tested as they stand, wrong or not: a vector says what
the text says, not what it should say.

| Path | What it is |
| --- | --- |
| `vectors/` | One YAML file per case: a graph, the calls a host makes to it with what it writes before each, and the state and value expected of each output. |
| `reference.py`, `formula.py` | A small Python reading of the proposal: the engine and blocks, and the formula language. Stdlib only. Not the library, and shares no code with it. |
| `second/` | A second reading, written from the proposal's text alone, without sight of the reference, the vectors or any earlier draft, and kept up to each amendment the same way. `ASSUMPTIONS.md` lists what the third revision's text did not settle, and `ASSUMPTIONS-amendment-1.md` what the first amendment's did not. |
| `run.py` | Runs the vectors against the reference, or with `--second` against the second reading. Needs PyYAML. |
| `mutate.py` | Breaks the reference one rule at a time and checks that a vector notices. |
| `compare.py` | Runs the two readings side by side on random inputs and call times and compares every output after every call. |

```bash
python3 conformance/run.py            # 294 vectors: ALL AGREE
python3 conformance/run.py --second   # 294 vectors: ALL AGREE
python3 conformance/mutate.py         # 528 breakages: 528 noticed; every vector failed by one
python3 conformance/compare.py        # 1874474 comparisons, 0 differences
```

The format of a vector is described at the top of `run.py`.

## How the vectors were made

The expected values in a vector were worked out by hand from the rule it
names, with small numbers and mostly a one-second period, and written down
before the reference was run. The reference then had to agree. Working them
changed the proposal in four places:

- A deadband that kept its sample on an uncertain input gave it as `good`.
  Rule 7.4.2 now makes the output uncertain when the input is.
- An estimator's sensitivity was to be taken by a numerical difference.
  A value worked by hand could not match that to nine places, and neither
  could two implementations. A model now states its sensitivity.
- "A total past `max_missed` goes on adding" could not be seen by any
  output, and was removed.
- What had been written and not taken up when a state is restored was not
  spoken for. It is dropped.

A vector is kept only if a broken reference fails it. `mutate.py` holds the
breakages, each named for the rule it breaks, and lists any vector that no
breakage fails. Review of the second revision found fifteen breakages of
stated rules that its vectors let through. Each of those that still names a
rule of this revision is in `mutate.py` now, with a vector that fails it.

## The second reading

The hand-worked values and the reference have one author, so agreement
between them shows less than it seems. `second/impl.py` was written from
the proposal's text as it stood, by a reader who had seen nothing else, with
its own formula parser. As first written:

- It agreed with 145 of the 151 vectors that existed then. Five of the six
  it refused because the text gave a state-space model's states no names:
  it called them `x1` on, the reference `x0` on. The sixth was a refusal
  whose wording a vector had pinned too closely.
- With the names made the same, it was run beside the reference on 846,283
  random comparisons and differed on 10,085.
  - At a period of 1 s, 10 differences, all one rule: whether a delay's
    initial value, not yet given, comes into doubt at a gap.
  - At a period of 0.1 s, the rest, from that rule and one other cause: a
    tick exactly half a period after a call fell on either side of "due",
    because that test had no slack and a tenth is not exact in binary. Once
    two readings disagree on how many ticks ran, everything after differs.
- Writing it turned up 106 places where the text did not say what to do
  (`second/ASSUMPTIONS.md`, kept as first written).

What was done about it:

- The proposal now names the states, gives the due test the slack the
  other time comparisons have, and says a delay's initial value is not
  changed by a gap.
- One of its assumptions showed a rule that both readings had read alike
  and that was wrong: an estimator stepped its model on this tick's inputs
  where a model block steps on the last tick's. Rule 7.9.2 was changed.
- Eight further sentences state what the text had left to the reader.
- The second reading was changed in four places to follow the proposal as
  changed: the names, the slack, the delay and the estimator's inputs. The
  reference was changed in four: the slack, the estimator's inputs, and two
  rules the second reading had chosen and the proposal then took, the
  sample time of a value a fallback puts in and a restore of a state saved
  before any tick.

`compare.py` was itself checked by running it against broken copies of the
reference.

## Amendment 1: time and the host interface

Review of the third revision reproduced seven faults in its time rules.
The amendment was written, the second reading was brought up to it from
the amended text alone, and the amendment was reviewed by itself.

- As first written, the second reading agreed with the reference on all
  163 vectors and on 862,031 random comparisons. The comparison now runs
  with the host's clock near 100 s and near 1.7e9 s, with rebases, clocks
  that start again, and several writes before a call.
- That agreement showed the text was clear. The review showed its central
  rule was wrong. A write was taken up at the first tick at or after its
  time, and the one written last stood. With a host loop at one period and
  20 ms of jitter, sampling a millisecond before each call, the call saw
  its own sample on 1,061 of 2,000 calls, and 516 samples were never seen.
  A write stamped 100 s ahead came `good` 100 s later. An old sample that
  arrived late displaced a newer one.
- The rule was rewritten: the last tick of a call may see what the host has
  in hand, the write with the latest time stands, and one stamped further
  ahead than `max_ahead` is thrown away at the call. On the same loop the
  call sees its own sample 2,000 times of 2,000.
- The breakages the review found the vectors had let through are in
  `mutate.py`, each with a vector that fails it, where the rule they break
  is still a rule.
- One case is kept as a vector with its true and unwelcome result: a host
  that stalls and then hands over only its latest sample still gets a
  latched trip and eight times the energy
  (`stall-host-keeps-only-latest.yaml`). The engine cannot see what it was
  never given, and the text now says what a host has to do.
- The second form was reviewed in its turn, and its core held: no way was
  found to take one sample twice or to bring an old one back. What the
  review asked for was added. A call reports how many writes were thrown
  away and how many wait; `max_ahead` and a maximum age under half a period
  are refused; a write earlier than what stands is thrown away as it is
  made, and `max_waiting` bounds the rest. Counting the writes thrown away
  showed a fault nobody had reported: after a rebase to a lower clock, new
  writes were judged against what stood on the old one. Nothing stands now
  from the moment of the rebase.
- Brought up to that from the text alone, the second reading agreed with
  the reference on all 182 vectors and on 1,086,235 random comparisons, as
  first written. The comparison now also runs at a period of 37 ms, at
  times on any nanosecond, with calls and writes that must be refused, two
  rebases in a row, and restores of a state saved before any tick.
- Two things the review found are left for later amendments and named at
  the head of the proposal: a window with `only_new` under a host slower
  than the period, and a pause short of `max_catch_up` being run as
  ordinary ticks.

## Amendment 2: doubt through memory

Review of the third revision showed that the tick an `uncertain` value
carried, meant to let doubt run out round a loop, also let it run out
down a chain. The amendment takes that out. A block is never `good` on a
tick where a value it used is `uncertain`; a block with a declared finite
memory is `uncertain` for that long after; a block whose memory has no end
reports what is in front of it and gives counters; and a loop that holds a
model block is one block with one `settle`.

- 99 of the 334 breakages quoted reference code the amendment rewrote.
  They were replaced, and the vectors whose expectations changed were
  worked again by hand: 30 of the 182 are changed.
- Writing the breakages found two faults in the amendment before anyone
  else read it. A value that went unusable inside a loop and was covered
  by a fallback started no doubt, and came out `good` a tick later. A
  model with `settle` was `good` on the gap's own tick and `uncertain`
  only from the tick after.
- As first written from the amended text, the second reading agreed with
  the reference on all 204 vectors that existed then, and differed on 1 of
  1,495,096 random comparisons. That one was a slip of its own: a delay's
  initial value was told from a taken-in one by the identity of an object
  that a reset replaced. Writing it turned up 28 places where the text
  left a choice and 9 where it was wrong or disagreed with itself. All
  nine were taken up, and the second reading, brought up to the result
  from the text alone, agreed on all 205 vectors and all 1,495,096
  comparisons as written.
- An independent review then reproduced what agreement between two
  readings could not show.
  - The reference crashed on an estimator in a loop with a model block:
    no vector and no comparison graph had one.
  - On a loop, only delays were held against the loop's `settle`. With a
    window of 6 s on a loop with a `settle` of 1 s, the plant was `good`
    for five ticks while it stepped on an `uncertain` value each tick.
  - An estimator that was `uncertain` on every tick, on a loop, left the
    plant `good` on every tick.
  - After an hour's stall a hysteresis, a latch and `since_true` were
    `good`, and nothing a graph could read said there had been a gap.
  - A window on a loop whose slope the loop read kept the loop in doubt
    for ever, with nothing from outside: a window that was `good` on one
    good sample gave a `bad` slope, which was the loop's next doubt.
  - Twelve rules the amendment states were pinned by no vector. Each was
    shown by a broken copy of the reference that passed every vector and
    differed from the reference on a small graph.
- What was done about it. Delay ticks, window lengths and low-pass
  settles on a loop are all held against its `settle`, and the graph is
  refused if they add up to more. What they took in as `uncertain`
  becomes `good` once the loop has settled. An estimator on such a loop
  is refused. Every block that gives `elapsed` gives `gaps`. A slope with
  fewer than two good samples is of the usable ones, and `uncertain`. The
  twelve rules have vectors and breakages. What is left is deliberate and
  is listed in section 7.11 of the proposal.
- The second reading took two more rounds from the text alone. In the
  first of them it read "counts as `good`" tick by tick where the
  reference made the change once: they agreed on all 221 vectors and
  differed on 8,946 of 1,688,065 comparisons, every one in the one graph
  with a window and a low-pass on a loop. The text was made to say which
  is meant, and two vectors were added that the tick-by-tick reading
  fails (`loop-delay-stays-good`, `loop-window-stays-good`). Brought up
  to that, it agreed on all 223 vectors there were then and on all
  1,688,065 comparisons, as written.
- The review's second pass reran its eleven findings and found each closed
  or listed in section 7.11, and found no new way to a `good` that should
  not be one. It broke the reference 25 more ways; two got past every
  vector, both the rule that what a window or a low-pass on a settled loop
  takes in at the tick itself is as its own rule says. Each now has a
  vector and a breakage.
- Of the 225 vectors, 45 are new with this amendment, and two were taken
  out with the rules they tested (`integrate-tolerance`,
  `cause-through-delay`). One of the 45 was wrong as I first worked it: a
  latch whose `set` is a formula of an `uncertain` value is `uncertain`,
  and I had it `good`.
- The places the second reading still had to choose are in
  `second/ASSUMPTIONS-amendment-2.md`. None of them is a difference from
  the reference.

## Amendment 3: gaps

A block was not told how long a gap was, so a total counted one period
for a stall of any length. The amendment makes a gap ticks nobody saw.
The tick a stall runs keeps its own number, each block does to what it
remembers what that many ticks with nothing usable to read would have
done, and a host that knows how long a restored graph was away says so.

- 24 vectors are new and 6 of the earlier 225 are changed. One was taken
  out and replaced (`gap-since-true`, by `since-true-after-gaps`).
- As first written from the amended text, the second reading agreed with
  the reference on all 236 vectors there were then and on all 1,687,650
  random comparisons. The comparison now gives some rebases a length:
  none, zero, under half a period, a period and a half, a few periods,
  four hundred.
- Writing it turned up 13 places where the text left a choice and 5 where
  it was wrong. Three changed a rule.
  - A total with `max_missed` was `bad` after an hour's stall and `good`
    after a restore of no stated length. Nobody knowing is more than any
    `max_missed`, and it is now `bad` there until a reset.
  - A rebase that passed over no tick stopped a timer with `reset` and
    not one with `hold`, and gave a model a doubt. A gap that passes over
    no tick now does nothing to what a block remembers.
  - The estimator did not do what the ticks would have done, and the text
    did not say so. It says so now.
- An independent review then compared a stall of N ticks against running
  N ticks with every input `bad`, block by block: 744,000 comparisons over
  20 blocks, and 224,640 over chains and loops. State and counters were
  the same but for what the text states, and one thing it did not: a model
  with `ride_through` took no step for the ticks passed over, where a run
  would have stepped on what it held. It now steps for those within
  `ride_through`.
- The review reproduced a fault the amendment had opened. A rebase forgets
  sample times, and a host then writes what it holds with the time of the
  rebase's call. A window with `only_new` that kept its samples across a
  rebase counted one sample again each time, and an estimator at a rebase
  that passed over no tick used one sample four times and went `good`. A
  window with `only_new` now keeps nothing from before a rebase, and an
  estimator's variance grows at every one.
- Twelve rules of the amendment were pinned by no vector, each shown by a
  broken copy of the reference that passed every vector. Each has a
  vector and a breakage now.
- Brought up to the result from the text alone, the second reading agreed
  on all 245 vectors there were then and all 1,687,650 comparisons, as
  written.
- The review's second pass reran its findings and found them closed, and
  ran a stall against a run again: nothing differs now but what the text
  states. It found the text claiming more than is so for the estimator:
  the variance growth at a rebase does not stop a sample written again
  from sharpening the estimate where the variance had already grown well
  past `p0`. The text now says that, and lists it. Four clauses of the new
  rules were unpinned, and each has a vector and a breakage now.
- One thing the review confirmed is left as it is, and listed in section
  7.11 of the proposal: a delay gives `not_ready` for a tick nobody saw,
  so a formula that keeps a running value through a delay, the integral
  of the `loop-delay` vector among them, reads `not_ready` for good after
  one tick is passed over.

## Amendment 4: models

Review of the third revision showed two masses that were each stable at a
period, joined, reaching 10⁹⁷ and saying `good`, and one mass at two and a
half of its time constants a tick giving 42.05 where the answer is 0.67.
The amendment makes every model linear and steps it exactly, as the
solution of its equation with its inputs held, and refuses a loop of two
model blocks.

- Both failures were written down as they stood before any text was, and
  are vectors now (`model-long-period`, `thermal-rc2`,
  `refused-loop-two-models`).
- The expected values of the new vectors are not worked by hand in round
  numbers: an exponential does not come out round. Each is from the closed
  form of its model's equation, written in the vector's header, and
  computed from that form and from nothing in the reference. For
  `thermal-rc2-uneven` that is by the eigenvectors of its matrix, which
  is not how either reading steps.
- 50 vectors are new, 3 of the earlier 248 are changed, and 4 were taken
  out with the rules they tested (sub-steps, the stability limit, and
  two models on one loop).
- As first written from the amended text, the second reading agreed with
  the reference on all 274 vectors there were then and on all 1,874,474
  random comparisons. It works its exponentials in a hundred decimal
  digits, where the reference uses doubles, so the two are not one method
  twice.
- That agreement was inside the range the vectors and the comparison
  cover. An independent review went outside it, with its own arithmetic
  of 120 digits as the answer, and found what agreement could not:
  - every named model's matrices are right, and match the 1.x model's own
    derivative to 1.7e-14;
  - the reference's exponential lost accuracy in proportion to how fast
    the model was against the period. A sensor of 1 mJ/K on a tank of
    1 MJ/K at a period of an hour was 3e-8 out, and a spring of 10⁶ rad/s
    at 1 s was 7e-4 out. Of 3,000 random models over twelve decades, 263
    missed one part in 10⁹. The second reading had every one right;
  - the default `settle` lost a slow rate beside a fast one in a
    subtraction, and at the extreme said a model did not decay.
- The text had promised one part in 10⁹ with no condition, which ordinary
  double arithmetic cannot keep. It now promises it up to a bound, the
  largest row of `A` summed and multiplied by the period being 100,000 at
  most, and a graph past the bound is refused. The reference's
  exponential was changed to square fewer times. Measured against 120
  digits over 1,500 random models up to the bound, its worst error is
  5e-10.
- The second reading, brought up to that from the text alone over four
  more rounds, found the two-state formula for `settle` still losing a
  slow rate in the determinant, and a `dc_motor` whose two constants
  differed in sign having or not having a `settle` by the last bit of a
  product. A named model's determinant is now taken from its settings,
  with nothing subtracted, and a motor's constants are not negative.
- The review's second pass could not find a model inside the bound whose
  step was more than 9.7e-11 out, and found two things the promise still
  got wrong. A large `B` cost `Ad` its accuracy, in both readings at the
  extreme, since both took the two from one exponential: with `B` at
  10¹²⁰ both gave an `Ad` of 1 for a state that decays to 0.368. `B` is
  kept out of the exponential now. And the promise is of one step: two
  engines that agree on every step are a part in 10⁹ apart after a few
  hundred ticks of an oscillator with no damping at the bound, which the
  text now says. Nine clauses of the new rules were unpinned, the settle
  formula that does not cancel among them, and each has a vector and a
  breakage.
- As last written the second reading agrees on all 294 vectors and all
  1,874,474 comparisons.
- Four rules were pinned by no vector: the estimator's `F·P·Fᵀ` (every
  estimator vector had one state), a default `settle` that is not a whole
  number of ticks, and the default for two of the named models. Each has
  a vector and a breakage now. Each named model has a breakage for every
  coefficient of its matrices, and the vectors were given settings that
  tell one from another: no mass, inductance or gain is left at 1.

## What this does not cover

- **A fault both readings share.** `compare.py` only compares them. The
  estimator's inputs, above, were one, and the first form of amendment 1's
  take-up rule was another.
- **A place neither the vectors nor the comparison goes.** Two readings
  agreeing says nothing of it. The reference's exponential was wrong for
  stiff models while 1.87 million comparisons agreed.
- **How long a `settle` of millions of ticks is, to the tick.** Two
  vectors pin that a model with a slow rate beside a fast one has a
  settle at all; none runs one to its end.
- **Drift over many ticks.** No vector runs an oscillator for hundreds of
  ticks at the bound, where two engines within the promise differ by more
  than the vectors' tolerance.
- **A threshold on a computed value.** Values are compared to one part in
  10⁹, and two implementations that agree to that can still fall on either
  side of a comparison, a deadband or a hysteresis.
- **Tie-breaking by block id** (rule 5.2). The order among blocks that do
  not depend on each other does not change any output, so no vector can see
  it.
- **Units** (section 10), which both readings ignore.
- **Refusing a saved state from a different graph** (rule 8.2). The vector
  format has one graph per file.
- **That a save holds a loop's doubt.** A restore is always followed by a
  gap, which sets the doubt itself, so no output can show it either.
- **A window on a settled loop turned back by a later doubt.** The vector
  `loop-window-stays-good` pins it and the tick-by-tick second reading
  failed it, but no entry in `mutate.py` breaks it: the reference has no
  single piece to replace.
- **What a host may not do.** A write to a name that is not an input, a
  write of the wrong type: the proposal does not say, and the two readings
  were not compared on it.
- **Stability of blocks together** (section 7.8, open).
- **The library.** Nothing here runs FluxGraph. A runner for the library
  comes with the rebuilt core.

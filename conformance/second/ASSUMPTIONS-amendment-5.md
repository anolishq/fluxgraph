<!-- markdownlint-disable MD029 -- entries keep one numbering -->
# Assumptions made in bringing `impl.py` up to Amendment 5

Every place where the text amended by "The estimator" (section 7.9, the
estimator row of the table in 8.6, and its row and entry in Appendix A)
did not say what to do, could be read two ways, or disagreed with another
passage, and what `impl.py` does. The ones most likely to make two honest
implementations disagree come first. Rule numbers are those of
`proposal.md`. Quotations are from `proposal.md`.

Part A is the guesses. Part B is what I believe the text gets wrong, each
with a small example run on `impl.py`. Unless it says otherwise an example
is a random walk: `state_space` with `A: [[1]]`, `B: [0]`, `C: [1]`, `q` 1,
`p0` 4, one measurement `z` of `y` with `r` 1, period 1 s, starting at 0.
Its predict adds 1 to the variance, and a measurement of a state of
variance `P` has a gain of `P / (P + 1)`.

## How the process noise is worked out

Rule 7.9.2 gives `N` as the integral of `exp(A·s)·Q·exp(Aᵀ·s)` over the
period and not a method. `N(t)`, that integral up to `t`, obeys
`dN/dt = A·N + N·Aᵀ + Q` from zero. Written with `N`'s entries in one
column, that is a linear model `dv/dt = K·v + (Q's entries)` with
`K = A⊗1 + 1⊗A`, and `impl.py` steps it exactly with the routine it uses
for a model's `Bd` (amendment 4): the integral of `exp(K·s)` over the
period, times `Q`'s entries, in decimal arithmetic at 100 digits, rounded
to doubles once, at compile. The two halves of the result that should be
equal are averaged, so that `N` is symmetric to the last bit. I did not
use the usual pairing of `-A` and `Aᵀ` in one exponential: for a model
with a fast state and a slow one it subtracts numbers of very different
sizes, and 100 digits are not enough at the bound of rule 7.8.7. For
`state_space`, `N` is `q` times the period on the diagonal, as the rule
says.

Checked against closed forms worked by hand, at periods of 0.7 s, 1 s and
25 s, each to one part in 10⁹ and in fact to about 10⁻¹⁵: one state that
decays (`q·(exp(2aT) - 1) / (2a)`) and one that does not (`q·T`); two
integrators in a row (`[[q0·T + q1·T³/3, q1·T²/2], [q1·T²/2, q1·T]]`);
three, with noise on the last (`T⁵/20`, `T⁴/8`, `T³/6`, `T³/3`, `T²/2`,
`T`, times `q`); a rotation, with noise on one state (it turns with the
state) and on both alike (it does not); two decays at rates 1 and 100; and
a decay that drives an integrator, where all three entries are different
sums of exponentials. Through the engine: two integrators over two
predicts and a measurement, which shows the off-diagonal entry in the
second state's estimate.

## Part A. Where the text had to be guessed

1. **How many are refused before one is taken.** Rule 7.9.5: "when a port
   has refused more than that many in a row, the measurement is not
   refused."
   - Reading A: the port has to have refused `max_refused + 1` in a row
     already; the next one that falls outside the gate is used. With
     `max_refused: 1`: two refused, the third used.
   - Reading B: the measurement that would be the `max_refused + 1`-th
     refusal in a row is the one used. With `max_refused: 1`: one
     refused, the second used; with `max_refused: 0` nothing is ever
     refused and a gate does nothing.

   *Chosen:* A, the words as they stand ("has refused more than"), and
   because B makes `max_refused: 0`, which the ranges allow, a gate that
   never acts. Run, `gate: 3`, `max_refused: 1`, `z` 0 then 100 on every
   tick: `refused_z` is 0, 1, 2, 2 on ticks 0 to 3 and the state is 88.64
   at tick 3. Under B it is 0, 1, 1 and the state moves at tick 2.

2. **At a rebase with a length: `p0` before the predictions, or after.**
   Rule 7.9.9: "Told that `n` ticks were passed over, it predicts `n`
   times more ... At a rebase, whatever its length, each state's variance
   grows by its `p0` as well". For a model whose `Ad` is not 1 the order
   matters.
   - Reading A: the predictions for the ticks passed over, then `p0`,
     then the predict of the tick that runs: the ticks nobody saw came
     before the rebase.
   - Reading B: `p0` first, then all the predictions.

   *Chosen:* A. Run: a `linear` model `dx/dt = -0.5·x`, `q` 1, `p0` 4;
   tick 0; `rebase(2s)` (one passed over); a call → the variance is
   2.8775 under A, and would be 1.9473 under B.

3. **Told that nobody knows: `p0` once, or twice.** The same rule: "Told
   that nobody knows, each state's variance grows by its `p0`. At a
   rebase, whatever its length, each state's variance grows by its `p0`
   as well". A gap of no known length is always a rebase.
   *Chosen:* once: "as well" is read as "in that case too". Run: tick 0,
   `rebase()`, a call → the variance is 4 + 4 + 1 = 9. Read as two
   growths it is 13.

4. **Rule 7.9.3, how the sentence groups.** "it is **considered** if its
   sample time is later than the sample time last considered on that
   port, and it is `good`, or it is `uncertain` and the port gives
   `r_uncertain`."
   - Reading A: later, and (`good`, or `uncertain` with `r_uncertain`).
   - Reading B: (later and `good`), or (`uncertain` with `r_uncertain`):
     an `uncertain` measurement that stands is considered on every tick.

   *Chosen:* A. Run: `r_uncertain: 4`, an `uncertain` 5 written once →
   `nis_z` is `good` at tick 0 and `not_ready` at ticks 1 and 2. Also: a
   measurement that is not considered (an `uncertain` one on a port with
   no `r_uncertain`, or an unusable one) does not move the sample time
   last considered, so the same sample written again as `good` is
   considered.

5. **When a port is inconsistent, between measurements.** Rule 7.9.6:
   "Once a port has `over` of them, it is **inconsistent** while their
   mean is more than `limit`", and rule 7.9.7: "a port is inconsistent at
   this tick".
   *Chosen:* it is judged on every tick from what the port keeps, whether
   or not a measurement was considered at that tick; so an estimator
   whose measurements stop while a port is inconsistent is `uncertain`
   until `over` more have come. The normalised innovation squared that is
   kept for a measurement taken by rule 5 is "the one worked before the
   variance grew". A rebase, like any gap, empties nothing.

6. **A run of refusals and the ticks between.** "in a row" (rule 7.9.5).
   *Chosen:* in a row among the measurements considered on that port. A
   tick with nothing considered, a gap, and a refusal on another port do
   not end a run; only a measurement that is used does, and a reset.
   `refused_<port>` counts every refusal since the last reset and is not
   set back by a run's end.

7. **What a measurement taken by rule 5 does to the tick.** Rule 7.9.7
   lists "a measurement was refused at this tick". One that is "not
   refused" under rule 5 is used. *Chosen:* that tick is `good`, unless
   something else in the list is so. See B1.

8. **What rule 7.9.7's first item is at a gap.** "this tick is the one a
   gap ran (rule 8.6), unless the gap passed over no tick". *Chosen:* the
   tick is `uncertain` after a stall, after a rebase with a length that
   passed over one tick or more, and after a rebase with no length; it is
   not, on that account, after a rebase that passed over none, though the
   variance has grown by `p0` there.

9. **The predictions for ticks passed over, where an input has never
   been usable.** Rule 7.9.9: "each as rule 2, on the model inputs it last
   had". *Chosen:* as rule 2 has it: the state stays and the covariance is
   `P + N`, `n` times.

10. **What is refused in `measure` and `consistency`.** *Chosen:* `of`
    names an output of the model, so for `state_space` and a default
    `linear` it is `y` and not `x0`; `r` is more than zero and
    `r_uncertain`, if given, a finite number not less than `r`, the same
    allowed; `consistency` is the text `none`, or a map with both `over`
    and `limit` and nothing else; `max_refused` with no `gate` is refused
    and `gate` with no `max_refused` is refused. `use_uncertain` is gone
    and is refused as unknown. A measurement of an output whose row of `D`
    is not all zero is refused (rule 7.9.4); one whose row of `C` is all
    zero is accepted, and measures nothing.

11. **`N` that is more than a double holds.** Rule 7.9.2: "`N` is exact as
    `Ad` is, on the same terms (rule 7.8.7)". *Chosen:* the same refusal:
    an estimator whose `N` has an entry more than a double holds is
    refused, also where its `Ad` fits. `N` grows as the square: with
    `A: [[5]]` a period of `50s` is accepted and `100s` refused, where a
    model block of the same `A` is accepted at `100s`.

12. **The outputs that are always `good`.** *Chosen:* `innovation_<port>`
    and `nis_<port>` are `good` on a tick where the measurement was
    considered, whatever the state of the estimate and whether the
    measurement was `uncertain` or refused; `sigma_max` makes only its own
    state's two outputs `uncertain`, and everything else in rule 7.9.7
    makes every state's.

## Part B. What I believe the text gets wrong

1. **An estimator is `good` on the tick it gives in to a measurement it
   has been refusing.** Rule 7.9.5 takes the measurement after
   `max_refused`, widening the variance by `p0`; rule 7.9.7 makes a tick
   `uncertain` where a measurement "was refused" or an `uncertain` one
   "was used", and this is neither. Run, `gate: 3`, `max_refused: 1`,
   `consistency: none`, the truth 0 and a sensor stuck at 100 from tick 1,
   state and value and sigma per tick:
   - tick 0: `good` 0, 0.89
   - ticks 1 and 2: `uncertain` 0 (refused)
   - tick 3: **`good` 88.64**, sigma 0.94
   - ticks 4 and 5: `uncertain` 88.64 (refused again)
   - tick 6: `good` 98.72, sigma 0.94; tick 7: `good` 99.56

   At tick 3 the estimate has moved 88 in one tick on a measurement that
   it had twice judged an outlier, and says `good` with a sigma under 1.
   If the sensor is right and the model wrong, that is the rule working;
   if the sensor is stuck, the estimator has followed it and vouches for
   it. It cannot tell which, and that is exactly when it should say
   `uncertain`. With `consistency` (`over: 3`, `limit: 2`) the same run is
   `uncertain` from tick 1 on, so the test covers it where it is given;
   with `none`, which the text allows, nothing does. I think the tick of
   a measurement taken by rule 5 should be `uncertain` by rule 7 in its
   own right.

2. **"Nothing else changes" at a refusal, and two things do.** Rule
   7.9.5: "the measurement is **refused**: counted, and nothing else
   changes." By rule 7.9.3 its sample time becomes the last considered on
   the port, and by rule 7.9.6 its normalised innovation squared is kept
   ("refused ones among them"). Run: `gate: 3`, `max_refused: 9`,
   `consistency` with `over: 1`, `limit: 5`; a refused 100 at tick 1, and
   nothing written at tick 2 → tick 2 is `uncertain`: the refusal of tick
   1 changed what the port keeps. The words should be "the state and the
   covariance do not change".

3. **A gap costs an estimator one step for each tick passed over, and
   the text sets no end to it.** Rule 7.9.9: "it predicts `n` times
   more". `impl.py` does that as `n` predictions, one after another: a
   stall of 100,000 ticks takes 0.23 s and one of 1,000,000 takes 2.2 s,
   for one state. At a period of 10 ms a host that was stopped for a day
   passes over 8.6 million. The result has a closed form (the model's
   step and `N`, compounded), and an engine may use it, but the text says
   "`n` times ... each as rule 2", and two engines that compound
   differently will differ in the last digits after a long gap. The text
   should say that the result is that of `n` predictions and need not be
   reached by making them; the same is true of the model block's row in
   8.6.

4. **After a long gap the estimate rests on an input nobody saw, and is
   `good` a tick later.** This is in 7.11 in general words ("`good` on
   the tick after ... model input"); the size of it at a gap is worth a
   number. Run: `x' = x + u`, `u` a `good` 2 at tick 0, a stall that
   passes over 1,000 ticks → at the tick that runs the state is 2,002,
   `uncertain`, with a sigma of 31.7; one tick later it is **`good`**
   2,004, sigma 31.7. The sigma has grown by the process noise of a
   thousand steps and by nothing for the thousand values of `u` that were
   assumed. A model block in the same place stops stepping after
   `ride_through` (rule 7.8.4); the estimator has no such limit, and
   "Model inputs with noise of their own" is Open. Until it is closed, an
   estimator that has predicted across a gap on held inputs is `good`
   with a sigma that knows nothing of them.

5. **The figures in "What the consistency test is for" cannot be
   checked.** "refused 3,509 of 3,600 measurements, ended 3.6 degrees out
   ... never more than 1.6 out ... a third of its ticks ... under a
   thirtieth ... 22 ticks in 3,600." They depend on a model, a noise and a
   sequence of random numbers that the text does not give, so no second
   implementation can reproduce them, and a reader cannot tell whether
   they are of this rule or of an earlier draft of it. I have not tried.

## Round two

The text was revised on the five findings and on entries 1, 2, 3, 6 and
11 of part A. Quotations are from the revised `proposal.md`; each example
was run on `impl.py`.

### Part A against the revised text

| Entry | Settled? | Code changed? |
| --- | --- | --- |
| 1. How many are refused before one is taken | Yes, the other way: "is the most a port refuses in a row: a measurement over the gate that would be one more is not refused ... With `max_refused` of 1 a port refuses one and takes the next; with 0 it refuses none." | Yes: a measurement over the gate is used once the run is as long as `max_refused` (it was one longer) |
| 2. At a rebase with a length, `p0` before or after | Yes, as chosen: "after the predictions for the ticks passed over and before the one for the tick that runs" | No |
| 3. Nobody knows: `p0` once or twice | Yes, as chosen: "once" | No |
| 4. How rule 7.9.3's sentence groups | Open: unchanged | No |
| 5. When a port is inconsistent, between measurements | Open: unchanged | No |
| 6. A run of refusals and the ticks between | Yes, as chosen: "a tick with none, a gap, and what another port does leave it as it was, and a measurement that is used ends it" | No |
| 7. What a measurement taken by rule 5 does to the tick | Yes, the other way: `uncertain` (finding 1) | Yes |
| 8. Rule 7.9.7's first item at a gap | Open: unchanged | No |
| 9. Predictions across a gap where an input was never usable | Open: unchanged | No |
| 10. What is refused in `measure` and `consistency` | Open: unchanged | No |
| 11. `N` more than a double holds | Yes, as chosen: "A graph whose `N` holds more than a double does is refused" | No |
| 12. The outputs that are always `good` | Open: unchanged | No |

### Part B against the revised text

| Finding | Now | Code changed? |
| --- | --- | --- |
| 1. `good` on the tick it gives in | Settled: "or one over the gate was used at this tick by rule 5" makes the tick `uncertain` | Yes |
| 2. "Nothing else changes" at a refusal | Settled: "the state and the covariance do not change. It is still the measurement last considered on its port, and its normalised innovation squared is kept" | No |
| 3. A gap costs one step for each tick passed over | Settled: "What is specified is the result of `n` predictions and not that they are made one by one; the same goes for a model block's steps" | Yes: see below |
| 4. `good` a tick after a long gap on an input nobody saw | Kept, and now listed in 7.11 | No |
| 5. The figures of the consistency example | Settled in part: the plant and the estimator are now given. See V1 | No |

What changed in `impl.py` for finding 3. An estimator told that more than
32 ticks were passed over no longer makes the predictions one by one. One
prediction is `x → F·x + g`, `P → F·P·Fᵀ + M`; two of them in a row are
another map of the same form; `n` of them are reached by squaring, in
about `log₂ n` products. Up to 32 they are still made one by one. A model
block no longer walks through the ticks either: it takes as many steps as
`ride_through` leaves it, and adds `n` to its counts. Run: a random walk
across a stall of a million ticks → the variance is 4 + 1,000,001. Made
one by one in round one, those predictions took 2.2 s. Against closed forms after 6,
41, 500 and 1,000 predictions (a decay driven by a constant input; two
integrators): to one part in 10⁹.

### What the new wording leaves to choose

U1. **Where compounding and stepping part.** "What is specified is the
    result of `n` predictions and not that they are made one by one".
    Compounded, the result differs from `n` single predictions by
    rounding, and how it is compounded is each engine's own. *Chosen:* as
    above. For a model that decays or holds, the two agree far inside one
    part in 10⁹. For one that grows, a long gap multiplies whatever the
    last digits were: both then run to values past any use, and to `bad`
    by rule 3.6 when they pass a double, perhaps a tick apart. I have no
    graph where two sound ways differ by more than the comparison allows
    while the values are still of a size to matter; I note that the text
    now leaves the arithmetic free where before it fixed it.

### What I believe the new wording gets wrong

V1. **The example says "`good` throughout", and by this text it is
    `uncertain` on nearly every tick.** "With its model's heat loss a
    fifth too low and a gate of three sigmas, the estimator refused 3,509
    of 3,600 measurements, ended 3.6 degrees out and said `good`
    throughout." By rule 7.9.7 a tick with a refusal is `uncertain`. And
    a gate alone cannot be written any more: `max_refused` is required
    with it. I ran the example as the text now gives it (a mass of 100
    J/K losing 1 W/K, a square wave of 60 W with a period of ten minutes
    starting high, noise of 0.2 from Python's generator, `q` 0.001, `r`
    0.04, `p0` 1, ambient 20, the estimator's `heat_transfer` 0.8), with
    `max_refused` of 100,000 to stand for no limit. Two seeds:
    - refused 3,518 and 3,501 of 3,600; ended 3.41 out; `good` on 82 and
      99 ticks and **`uncertain` on 3,518 and 3,501**.

    The count and the error agree with the text's; "said `good`
    throughout" was true of the rule before this amendment and is not of
    this one. The rest of the paragraph holds as the rules now stand:
    - with `max_refused: 5`: never more than 1.43 out (the text: 1.6);
      `good` and more than three of its sigmas out on 1,204 and 1,178
      ticks, a third;
    - with `consistency` over 20 and a limit of 2: that falls to 79 and
      87 ticks, about a fortieth ("under a thirtieth");
    - with the model right, the test makes 8 and 4 more ticks `uncertain`
      (13 against 5, 8 against 4), where the text says 22. That figure
      depends on the noise drawn, and I would not hold the text to it.

    The first sentence should say "and was `uncertain` on all but a
    hundred ticks", or the example should be told as what a gate did
    before this amendment.

Still open, text unchanged: entries 4, 5, 8, 9, 10 and 12 of part A.

## Round three

The text was revised after an independent review. Quotations are from
the revised `proposal.md`; each example was run on `impl.py`.

### The two things the review found, on `impl.py`

- **`impl.py` had the first, and it is fixed.** `x' = x`, `q` 0, `p0`
  10¹⁶, `r` 1, two hundred measurements of a truth of 10 with noise of 1:
  after the first sample the sigma was exactly 0.0 and the estimate stayed
  at 11.288, the first sample, for all two hundred. With the covariance
  worked as rule 7.9.4 now has it the sigma is `1 / √n` (1, 0.7071, ...,
  0.0707) and the estimate is the mean of the samples so far (10.056
  after 200).
- **And the second.** An estimator on a restored state with nothing
  written afterwards was `uncertain` on the tick the restore ran and
  `good` from the next, for ever. It is now `uncertain` until a
  measurement is used.

### What the text now settles, and what changed in `impl.py`

| Passage | What it settles | Code changed? |
| --- | --- | --- |
| Rule 7.9.4: "`P = (1 - g·c)·P·(1 - g·c)ᵀ + g·v·gᵀ`" | The form the covariance is updated in | Yes: that form, in place of `P - g·(c·P)` |
| Rule 7.9.7: "a gap of no known length has gone by (rule 9) and no measurement has been used since" | One more way to be `uncertain`, which lasts | Yes: kept in the block's state, and so in a save; set at a gap of no known length, ended by a measurement that is used |
| Rule 7.9.3: "its port is connected to an input, or to a delay or a formula that takes its sample time, through any number of those, from an input ... One connected to any other block is refused" | Where a measurement may be read from | Yes: checked when the graph is compiled |
| The worked paragraph | V1 of round two: it now says "under the third revision's rule it said `good` throughout, and under rule 7 it is `uncertain` on every tick it refuses", and its counts are given as ranges that my two runs fall in | No |

Still open from part A, text unchanged: 4, 5, 8, 9, 10 and 12.

### What the new wording leaves to choose

W1. **A measurement port given a constant.** "its port is connected to an
    input, or to a delay or a formula ... One connected to any other
    block is refused". A constant is neither an input nor a block.
    *Chosen:* accepted. It has no sample time (rule 4.7) and is never
    considered, so it does no harm; the refusal the text gives is of
    blocks. Run: `z: 3` compiles, and `nis_z` is `not_ready`. The other
    reading refuses it as not "connected to an input".

W2. **What "a formula that takes its sample time" is, and how far the
    chain is followed.** *Chosen:* a formula takes a sample time from the
    input its `sample_of` names, or from its one signal input where it has
    exactly one (rule 3.7); a formula of two signals with no `sample_of`,
    or of constants alone, gives the time of the tick and is refused. The
    chain is followed back through that input of each formula, and the
    input of each delay, until an input from outside is reached; any other
    block on the way, an estimator's own output among them, is refused,
    and so is a chain that comes round to a delay it has passed (it never
    reaches an input). The formula's other inputs may be anything: see
    X1.

W3. **Which measurement ends "no measurement has been used since".**
    *Chosen:* one used on any port of the estimator, at the gap's own
    tick or later, a measurement taken by rule 5 among them. One that is
    refused does not. Run: `gate: 3`, `max_refused: 5`; `rebase()`; a 100
    refused at the tick that runs and nothing written after → the next
    tick is still `uncertain`.

### What I believe the new wording gets wrong

X1. **The rule looks at where the time comes from, and not the value.**
    A formula with `sample_of` takes its time from one input and may take
    its value from anything. Run: a low-pass of an input `n`
    (`tau: 5s`), and a formula `b + 0 * a` with `a` an input `m`, `b` the
    low-pass and `sample_of: a`; the estimator's measurement is the
    formula. It compiles. With `m` written on every tick, the estimator
    takes the low-pass's output as a new, independent sample on every
    tick (`nis_z` is `good` at ticks 0 to 3), which is what the rule says
    it refuses a low-pass for: its output is one sample smeared over many
    ticks, and its errors are not independent. The rule stops the mistake
    of every tick counting as a new sample by accident; it does not stop
    a graph that says so on purpose. I think that is as far as a compile
    check can go, and the text should say that `sample_of` is the
    author's word that the value is as new as that input.

X2. **A fallback on a formula in the chain is a new sample on every
    tick.** Rule 3.7: "so does a value a fallback puts in (section 7.10),
    whatever the block": a fallback's value has the time of the tick, and
    is `uncertain`. A formula of one input is allowed in the chain. Run:
    a formula `a * 1` of an input `m` with `fallback: {y: 7}`, and an
    estimator of `x' = x`, `q` 0, `p0` 4, measuring it with `r` 1 and
    `r_uncertain` 4. `m` is never written. Per tick, `nis_z`, the state
    and value, and the sigma:
    - tick 0: considered, `uncertain` 3.5, sigma 1.414
    - tick 1: considered, `uncertain` 4.667, sigma 1.155
    - tick 5: considered, `uncertain` 6.0, sigma 0.756

    The constant 7 is taken as six independent measurements, and the
    sigma falls as if they were. Each tick is `uncertain` while it lasts,
    because the fallback's value is; but when the input comes back the
    estimator is `good` with a state pulled to 7 and a sigma that six
    samples of nothing made small. The compile check should refuse a
    block with a fallback on the output a measurement comes by, or rule
    3.7 should give a fallback's value no sample time.

## Round four

The text was revised on X1, X2, W1 and W3 of round three. Quotations are
from the revised `proposal.md`; each example was run on `impl.py`.

| Entry | Settled? | Code changed? |
| --- | --- | --- |
| W1. A measurement port given a constant | Yes, the other way: "One connected to any other block, or to a constant, is refused" | Yes: refused at compile |
| W2. How far the chain is followed | Yes, as chosen: "Only the path the time comes by is followed." | No |
| W3. Which measurement ends "no measurement has been used since" | Yes, as chosen: "on any port, at the gap's own tick or after it ... A refused measurement does not" | No |
| X1. The rule looks at the time and not the value | Kept, and said: "A formula's `sample_of` is its author's word that its value is as new as that input, whatever else the formula reads." | No |
| X2. A fallback in the chain is a new sample on every tick | Yes: rule 3.7 now says a value a fallback puts in carries no sample time, "it is not a sample of anything" | Yes: a fallback's value has no sample time, for every block and every reader |

**X2, run through to the tick where the input returns.** The same graph:
a formula `a * 1` of an input `m` with `fallback: {y: 7}`; an estimator of
`x' = x`, `q` 0, `p0` 4, measuring it with `r` 1 and `r_uncertain` 4. `m`
is not written on ticks 0 to 5 and is a `good` 3 at tick 6.
- Before this round: the 7 was considered on each of ticks 0 to 5; at
  tick 5 the estimate was `uncertain` 6.0 with a sigma of 0.756.
- Now: on ticks 0 to 5 `nis_z` is `not_ready`, the estimate is `good` 0
  and its sigma is 2: the fallback is never considered. At tick 6 the 3
  is the first measurement: `nis_z` is 1.8, the estimate is `good` 2.4
  and its sigma 0.894. Nothing of the 7 is in it.

The rule 3.7 change reaches a window with `only_new` as well. Run: an
input with `max_age: 2s`, written once; a formula of it with a fallback
of 7; one window of 4 ticks with `only_new` and one without. At tick 4
the input has been too old for two ticks and the formula gives 7,
`uncertain`. The window with `only_new` holds no sample at all (`count`
0, `mean` `not_ready`): before this round it took the 7 as a new sample
on each of those ticks. The window without `only_new` holds all four
(`count` 4), as before. A delay passes a fallback's value on with no
sample time, as it took it.

### What is still open or wrong

Nothing new. One consequence, which follows from the text and which I
think is meant: a formula with a fallback that feeds an estimator or a
window with `only_new` is now, for them, simply absent while the fallback
stands. The fallback still reaches every reader that does not compare
sample times (rule 7.10).

Still open from part A, text unchanged: 4 (how rule 7.9.3's first
sentence groups), 5 (inconsistency judged between measurements), 8 (rule
7.9.7's first item at a gap), 9 (predictions across a gap where an input
was never usable), 10 (what is refused in `measure` and `consistency`) and
12 (the outputs that are always `good`); and U1 of round two (the
arithmetic of a long gap).

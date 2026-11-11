<!-- markdownlint-disable MD029 -- entries keep one numbering across sections -->
# Assumptions made in implementing the proposal

Each entry gives the rule concerned, the words at issue, and what `impl.py`
does. Entries are numbered in one sequence.

## The ten most likely to make two honest implementations disagree

1. **Rules 3.8 and 7.2 — the cause of an uncertain input from outside.**
   "Where a rule in this document makes a value uncertain and names no
   cause, the cause is the tick it happens at." An input written
   `uncertain` by the host, and one standing on its `initial` value, are
   uncertain at every tick they are read, and the text does not say whether
   "the tick it happens at" is the tick that took the write up or each tick
   it is read. I give the cause as **the tick at which it is read**, every
   tick. With the other reading a low-pass fed a steadily uncertain input
   turns `good` after `settle` ticks (rule 7.4.8).

2. **Rules 7.8.1 and 7.8.6 — which tick a model's doubt is, and when it
   shows.** "any tick at which it stepped on a held value or did not step"
   and "uncertain ... while the tick's number less the doubt is less than
   `settle`". The step made in the second phase of tick `k` produces the
   state of tick `k + 1`. I record the doubt as `k`, the tick whose second
   phase it happened in. The output of tick `k` was already given and is
   not affected, so the doubt is first seen at `k + 1` and lasts
   `settle - 1` output ticks; with `settle` of one period it is never seen.
   An implementation that records `k + 1`, or that marks the output of tick
   `k`, differs by one tick. The same applies to "the cause of any
   uncertain input it has stepped on": it shows from the next tick.

3. **Rule 7.9.2 — which tick's inputs the estimator predicts on, and in
   which phase.** "On every tick after tick 0 it steps the model one period
   on its model inputs" and Appendix A "Its inputs are all direct." I do
   predict, correct and output all in the first phase of tick `k`, and the
   predict step from `k - 1` to `k` uses the model inputs **as read at tick
   `k`**. A model block (rule 7.8.1) steps from `k` to `k + 1` on the
   inputs of tick `k`, so the same model hosted the two ways sees its
   inputs one tick apart. "that input's last usable value" includes the
   value of the present tick if it is usable, and is recorded at tick 0
   too, although tick 0 does not predict.

4. **Rule 6.2 and Appendix A — which lengths are "counted", and what
   `settle` is written as.** "Every length of time a block counts (a
   window, a timer, a limit) is a whole number of periods" with only
   maximum age, `max_ahead`, `tau` and `per` named as exempt. I treat
   `window`, `time`, `hold_limit`, `ride_through`, `settle` and
   `max_missed` as counted: each is written as a length of time (`"3s"`)
   and refused if not a whole number of periods. `settle` is described
   both as a number of ticks ("for `settle` ticks") and by a default that
   is a time ("three `tau`"); I take a given `settle` as a length of time.
   `max_missed` is compared with `missed` "in seconds"; I still require
   whole periods and compare tick counts. A bare number for any of these
   is refused (rule 9.3), including `0`.

5. **Rule 7.9.6 and Appendix A — the names of a `state_space` model's
   states.** The estimator's outputs are "one per state, by the state's
   name" and `q`, `p0`, `measure.of` and `sigma_max` are keyed by state
   name, but `state_space` gives its states no names. I name them `x1`,
   `x2`, … `xn`. (`thermal_mass` has the one state `temp`.) The hosted
   model's own output (`y`) is not an output of the estimator.

6. **Rules 6.4, 6.5, 6.10 — the floating-point form of the time tests.**
   The text gives the comparisons in words only. I compute the time of
   tick `k` as `t_anchor + (k - k_anchor) * period` (a product, not a
   running sum), where the anchor is tick 0 or the last gap's tick; a tick
   is due when `t_k <= now + 0.5 * period` (no slack: rule 6.10 lists only
   three comparisons); too old is `t - sampled > max_age + slack`; too far
   ahead is `sampled - t > max_ahead + slack`; run too long is
   `t - t_origin > max_age + slack`; `slack = period * 1e-6`. The period,
   maximum age and `max_ahead` are the nearest doubles to the decimal
   written. At a period that is not exact in binary another arrangement of
   the same arithmetic can put a tick or an age on the other side.

7. **Rules 7.7.2 to 7.7.5 — what an integrator's reset returns to zero,
   and which state wins.** "A usable, true `reset` returns the total and
   every count to zero". `missed` is defined as a time, not listed among
   the counts of rule 3, but rule 4 says "`bad` once `missed` is more than
   that, until a reset". I zero `missed` on a reset, and the reset also
   ends the `uncertain` of a gap (section 8 table). The tick of the reset
   counts as a tick run. Order of states: `bad` by `max_missed` wins over
   `uncertain` by a gap or by `tolerance`. `missed` is computed as the
   number of missed ticks times the period, not a running sum. With
   `tolerance` 0, an unusable input at tick 0 gives an `uncertain` total
   of 0.

8. **Rule 3.8 — the cause of an uncertain output where no rule names
   one, and in particular a formula's.** "the latest cause among the
   block's direct inputs that are uncertain at that tick, or the tick
   itself if none is." I apply this to the block as a whole: a formula's
   uncertain output takes the latest cause among **all** its uncertain
   inputs, including one in the branch of `when` that was not chosen or an
   operand that did not decide an `or`. The same default is used for
   `window`, `hysteresis`, `held_for`, `since_true`, `latch`, `integrate`
   and `estimator` outputs (so an uncertain latch output caused by an old
   event carries the present tick as its cause when its inputs are now
   `good`). Rules that "name no cause" explicitly (ride-through in 7.4.3,
   an unusable direct input in 7.8.5, a fallback) give the tick.

9. **Section 8 table — what a gap leaves alone.** The table says what each
   block does and is silent on the rest of its memory. I keep: a window's
   "sample time of the last sample the window took" (rule 7.3.7), so the
   same sample rewritten after a gap is still not new; an estimator's
   "sample time last considered" and last used per port, its refusal
   counts, and its inputs' last usable values; a model block's last usable
   input values and its count of unusable ticks in a row; a low-pass's
   doubt (cleared anyway by the next first input); a deadband's nothing. A
   `delay` makes "every `good` value it holds" uncertain **including
   initial values it has not yet given out**. The estimator still predicts
   one period at a gap's tick, however long the gap was, after its
   variances grow by `p0`. `since_true` then processes the gap tick's
   input normally (a usable true input sets the clock to the same tick).

10. **Rules 8.3 and 8.4 — restore.** (a) Restoring a state saved before
    any tick had run: "Its number is one more than the last tick's" has no
    last tick. I make the next call run tick 0 as a first call, with no
    block told of a gap. (b) "After a restore the next call is a gap
    whatever its `now`, and may carry any `now`": I still refuse a `now`
    that is not finite, and do not compare it with the last call's. (c)
    Writes made before the restore and not taken up are dropped at the
    restore (both those made to this engine and any in the saved state: a
    save does not hold them). (d) Restoring twice, or saving after a
    restore and before a tick, keeps "the next call is a gap" only in the
    engine that was restored; the saved object does not record it, and
    every restore sets it. (e) "the same graph" is open in the text: I
    compare the JSON text of the graph dict as given, so key order and `2`
    against `2.0` matter.

## The rest

### Section 3

11. **Rule 3.2 / 3.7 — sample time of an unusable signal.** "A signal that
    is not usable carries no value at all." I also give it no sample time
    and no cause. A formula whose `sample_of` input is unusable but whose
    output is usable (`when(ok, x, 20)`) therefore has no sample time, and
    so can never be a new sample to a window with `only_new` or to an
    estimator.
12. **Rule 3.6 against rule 7.8.5.** "A block output that would be [not
    finite] is `bad`, whatever the block" against "A model never gives up
    its state. Its outputs are always usable." I let 3.6 win: a model or
    estimator output that is not finite is `bad` (and can be replaced by a
    fallback).
13. **Rule 3.6 — booleans.** Applied to number outputs only.
14. **Rule 3.7 — "A formula with exactly one signal input".** I count
    ports connected to a signal, not distinct signals: a formula with two
    ports wired to the same signal has two signal inputs and carries the
    time of the tick.
15. **Rule 3.7 — a usable input with no sample time through a formula or
    delay.** An input on its `initial` value, a constant, and a delay's
    initial value have none; a formula or delay passing one on has none
    either.
16. **Rule 3.8 — the cause of an input on its initial value.** As entry 1:
    the tick it is read at.
17. **Rule 3.5 — type of a constant.** An int or float constant is a
    `number`, a bool is a `boolean`; a bool given to a number port is
    refused and so is a number given to a boolean port. Integers become
    doubles.

### Sections 4 and 5

18. **Rule 4.4 — blocks whose inputs are all direct.** Not observable, but
    stated for clarity: `window`, `deadband`, `lowpass`, `hysteresis`,
    `held_for`, `since_true`, `latch`, `integrate` and `estimator` take
    their input into their memory in the first phase, because their output
    at a tick depends on that tick's input. Only `delay` and the model
    blocks do anything in the second phase.
19. **Rule 4.8 — an unconnected `reset`.** "The block type says what that
    means"; for `latch` and `integrate` it is not said outright. I treat
    it as never true.
20. **Rule 5.2 — "Ties are broken by block id".** By ordinary string
    comparison of ids (code points). It has no effect on any output.
21. **Rule 5.3 — a block reading its own output through a direct input**
    is a loop of one block and refused.
22. **Rule 5.4 — "can reach its own input through any chain of inputs".**
    I test whether the delay block is reachable from itself following
    block-to-block connections of any kind, including the delay reading
    its own output directly.
23. **Appendix A, `delay` — "Its type is its input's".** A delay in a loop
    needs its type before its input's type is known. I take the type from
    `initial` when one is given, then refuse if the input turns out to be
    of the other type. A delay may read a constant.

### Section 6

24. **Rule 6.2 — "within 10⁻⁹ of a whole number".** I take "within" as
    inclusive (`abs(v - round(v)) <= 1e-9`), and compute the number being
    rounded in doubles: `min_good * n`, `3.0 * tau / period`.
25. **Rule 6.2 — the exact test.** Done in exact rational arithmetic on the
    decimal text and unit of both lengths.
26. **Rule 6.1 — a period of zero** (`0s`) is refused. Not stated.
27. **Rule 6.7 — `max_catch_up`.** No range is given. I require a whole
    number (not a bool, not `100.0`) of at least 1.
28. **Rule 6.7 — "would run more ticks than that".** A call that would run
    exactly `max_catch_up` ticks runs them; one more is a gap.
29. **Rule 6.6 — several writes to one input before a tick.** "What stands
    is the latest write": only the last one counts; earlier ones are
    never seen, even by `only_new` or an estimator.
30. **Rule 6.6 — a call that runs no tick.** Writes made before it wait
    for the next call that runs one. Such a call still moves "the last
    call's `now`" for rule 6.9; a refused call does not.
31. **Rule 6.9 — after a reset.** "the next call runs tick 0 again, at
    whatever `now` it is given": the `now` may be earlier than before the
    reset.
32. **Rule 6.3 — the type of `now`.** A bool or non-number is refused
    (`ValueError`), like a `now` that is not finite.
33. **Rule 6.6 — a write the interface does not allow.** Not in the
    proposal at all. `write` raises (`KeyError` for an unknown input,
    `ValueError` otherwise) and changes nothing when: the state is not one
    of the four; a usable value is of the wrong type for the input (a bool
    for a number input or the reverse; an int is accepted for a number);
    a usable value has no sample time or one that is not finite. For
    `not_ready` and `bad` the value and sample time given are ignored.

### Section 7.1 and the formula grammar

34. **Rule 7.1.2 — the value when no operand decides.** With both operands
    usable an undecided `or` is false and an undecided `and` is true, with
    the worst state. Both operands are always evaluated.
35. **Rule 7.1.2 — one operand decides and the other is unusable.** The
    result is decided, with the state rule 2 gives (`bad or true` is a
    `good` true if the true is `good`).
36. **Rule 7.1.3 — a chosen branch that is unusable.** "the worse of that
    branch's state and the condition's": the result is unusable with the
    branch's state.
37. **Rule 7.1.4 — "the logarithm ... of a negative number".** `ln(0)` is
    `bad` as "a result that is not finite". `sqrt(-0.0)` is not negative
    and gives `-0.0`. Division by `-0.0` is a division by zero.
38. **Rule 7.1.4 — "`pow` is C's".** I use Python's `math.pow`, which
    follows C99 for special cases (`pow(x, 0)` is 1 and `pow(1, y)` is 1),
    and take its domain and range errors as `bad`.
39. **Rule 7.1.1 — `not` and unary minus** take the state of their
    operand; `min`, `max` and comparisons take the worst state.
40. **Grammar — a number followed at once by a letter, underscore or
    point** (`2x`, `1e`, `1.`, `1.5.2`) is refused. `.5` is refused.
    `1e5` and `1E+5` are numbers.
41. **Grammar — `not` under a tighter operator.** `1 + not a` and
    `a == not b` are refused, as the grammar has `not` above `compare`.
42. **Grammar — function names.** A function name not followed by `(`, or
    with the wrong number of arguments, is refused.
43. **Appendix A — "every input of the block must be used".** An input
    port whose name is not a formula name (`a-b`, `2x`, `and`, `min`)
    cannot be used and so the block is refused.
44. **Appendix A — "A formula is one line".** Any character that is not a
    space, tab or part of a token, including a newline, is refused.
45. **Appendix A — types.** `==` and `!=` accept two booleans. `min`,
    `max`, `abs` and the others take numbers only.
46. **Appendix A — `all_good` and `formula` with no input** are refused
    ("take one or more inputs").
47. **Appendix A — `sample_of` naming a port given a constant** is
    refused.

### Section 7.2

48. **Rule 7.2.1 — an initial value past the maximum age.** Read as: with
    an initial value the input is `uncertain` until the graph has run for
    more than the maximum age and `bad` after; without one, `not_ready`
    then `bad`. With `max_age: none` neither ever ends.
49. **Rule 7.2.4 — "the tick that takes it up".** The test uses that
    tick's time, which at a gap is the call's `now`. A refused write stays
    `bad` even when later ticks reach its sample time.
50. **Rule 7.2.3 — order.** A value that is not finite is `bad` whatever
    its sample time; a boolean cannot be not finite.
51. **Section 7.2 — ranges.** `max_age` and `max_ahead` may be `0s`.
    `max_ahead` cannot be `none`. An input's `initial` must be finite and
    of the input's type. `unit` is accepted and ignored, whatever it is.
    An input's `type` other than `number` or `boolean` is refused.

### Section 7.3 and `window`

52. **Rule 7.3.3 — "the worst state among its ticks that hold none".** A
    tick with an unusable input holds none and counts with that input's
    state, also under `only_new`; only a tick whose input was usable but
    not new counts as `not_ready`.
53. **Rule 7.3.7 — "`n` ticks have run since the graph started or since a
    gap".** Counting the present tick: at tick `k` after a start at 0,
    `k + 1 >= n`.
54. **Rule 7.3.7 — the first sample.** With no sample taken yet, any
    usable input that has a sample time is new.
55. **Rule 7.3.5 — slope with fewer samples than needed.** Rule 3 gives
    its state, not rule 5.
56. **Appendix A — the statistics.** Mean is a left-to-right sum over the
    samples, oldest first, divided by their number. Slope is
    `Σ(t - t̄)(v - v̄) / Σ(t - t̄)²` with `t` the tick's offset from the
    oldest tick of the window times the period (the oldest tick of the
    window whether or not it holds a sample, and even if it is before
    tick 0).
57. **Rule 7.3.6 — `count`** is given as a double.

### Section 7.4

58. **Rule 7.4.2 — a held sample that was uncertain.** "It is `good` if
    the sample it holds and the input are both `good`": a deadband holding
    a sample taken from an uncertain input stays `uncertain`, with that
    sample's cause, until it takes a `good` one.
59. **Rule 7.4.1 — `step` of 0.** Every usable input has "moved by `step`
    or more" and is taken.
60. **Rules 7.4.3 and 7.4.4 — before any usable input.** With nothing
    held, an unusable input gives the input's state and does not count
    towards anything.
61. **Rule 7.4.4 — the tick the ride-through runs out.** On unusable tick
    `m` with `m` periods more than `ride_through`, the block forgets and
    that tick's output takes the input's state.
62. **Rule 7.4.5 — `aᵐ`.** Computed as `a ** m` with
    `a = exp(-period / tau)`, not as `exp(-m * period / tau)`.
63. **Rule 7.4.7 — the order within a tick.** On a first input the doubt
    is cleared, then the input's own cause is counted if it is uncertain.
    On a later input with `m` above 1 the tick is a doubt, and then the
    input's cause if uncertain; the doubt is the latest of all.
64. **Rule 7.4.8 — literally.** An uncertain input whose cause is
    `settle` or more ticks old gives a `good` output; `settle` of `0s`
    never gives `uncertain` on a usable input. During ride-through the
    output is `uncertain` with the tick as cause, whatever `settle` is.
65. **Rule 7.4.8 — a low-pass state that is not finite** gives `bad` by
    rule 3.6 and is kept ("The block's state is not put right for it").

### Section 7.5

66. **Rule 7.5.3 — "it switches".** A usable input at or beyond a
    threshold sets the direction and the sureness even when the block was
    already that way; that is how it becomes sure again.
67. **Rule 7.5.2 — undecided with an unusable input.** It becomes not
    sure, and the output takes the input's state.
68. **Rule 7.5.1 — `initial`** is a boolean.

### Section 7.6

69. **Rule 7.6.1 — `hold`.** An unusable tick within the limit counts as
    an input that was not `good`, so the output stays `uncertain` for the
    rest of that run of the timer ("`good` if every input since it started
    was `good`"). The count of unusable ticks restarts at any usable
    input. "longer than the limit" is `m` periods more than `hold_limit`.
70. **Rule 7.6.1 — `time` of `0s`** is allowed: the output is true from
    the tick after the input became true.
71. **Rule 7.6.2 — "Its clock starts at the first tick".** Tick 0 (or the
    block's first tick after a reset), unless the input is true then.
72. **Rule 7.6.2 — `unknown`.** The unusable tick is still recorded as a
    tick where the input was not `good`.
73. **Rule 7.6.2 — "at or after the later of the clock and the tick `time`
    ticks back".** Inclusive of tick `k - n`.
74. **Rule 7.6.3 — the third clause.** It is tried only if the first two
    do not apply, so after a true `reset` the latch keeps the sureness the
    reset gave even if `set` is not `good` on that tick.
75. **Rule 7.6.3 — a `reset` given the constant `true`** is allowed.

### Section 7.8 and the models

76. **Rule 7.8.4 — an input that has never been usable.** It has no last
    usable value, so the model does not step, whatever `ride_through` is.
77. **Rule 7.8.5 — no limit on age.** A direct input that is unusable is
    replaced in the output by its last usable value however old; that
    value is the one recorded up to the previous tick.
78. **Rule 7.8.5 — order of the three cases.** Unusable direct input
    (`uncertain`, cause the tick), else uncertain direct input (its
    cause), else rule 6. A doubt is not combined with an input's cause.
79. **Rule 7.8.6 — "any uncertain input it has stepped on".** Counted only
    on ticks where the model steps; a tick where it does not step is a
    doubt anyway.
80. **Rule 7.8.6 — default `settle`.** `3.0 * tau / period` in doubles,
    rounded up per rule 6.2.
81. **Rule 7.8.7 — the stability test.** `period / substeps >
    2.785 * (thermal_mass / heat_transfer)` in doubles, with no slack.
82. **Appendix A — `state_space` and `substeps`.** "`substeps` does not
    apply to it": the setting is accepted, checked for range, and
    ignored (one step per tick, sensitivity `A`).
83. **Appendix A — `state_space` shapes.** `A` must have at least one
    row; `B`, `C` and `initial` must have length `n`; `D` is a number.
84. **Appendix A — `thermal_mass` `initial`** is required (it has no
    bracketed default). RK4 is `k1..k4` with `d/2` and `d/6` as written
    in the usual form.
85. **Appendix A — `u` is direct "when `D` is not zero"**: tested as
    `D != 0` on the number given.

### Section 7.9

86. **Rule 7.9.2 — tick 0.** "every tick after tick 0" is tested on the
    tick's number, so a restore's gap tick predicts.
87. **Rule 7.9.2 — sub-steps.** The estimator's `substeps` steps the
    hosted model that many times per tick and the stability test of rule
    7.8.7 is applied to it.
88. **Rule 7.9.3 — "the sample time last considered".** Updated when a
    measurement is considered, whether it is then used or refused.
89. **Rule 7.9.4 — arithmetic.** `g` and "row `i` of `P`" are taken from
    `P` before the update; `P` is not symmetrised. A spread or variance
    below zero from round-off gives a NaN square root: the gate then does
    not refuse, and the sigma output is `bad`.
90. **Rule 7.9.5 — what makes a state uncertain.** Only an unusable model
    input on that tick and `sigma_max`. An uncertain model input, an
    unusable or uncertain measurement, a gap and a refusal do not.
    `sigma_<state>` shares the state's state.
91. **Rule 7.9.6 — `refused_<port>` and `since_<port>`.** The count is a
    double. `since` is the tick's time less the sample time last used and
    can be negative for a sample stamped ahead.
92. **Appendix A — the estimator's settings.** `q` and `p0` must name
    every state and no other; `sigma_max` may name some; its range is not
    given, so any finite number. `measure` entries take `of` and `r` only;
    a measurement port with the name of a model input, and two outputs
    that would share a name, are refused. `model` must not carry
    `ride_through`, `settle` or `substeps`.
93. **Rule 7.9.6 — fallbacks.** An `innovation_<port>` with a fallback
    gives the fallback on every tick with no considered measurement.

### Section 7.10

94. **Sample time of a substituted value.** Not stated; I give the time of
    the tick, for every block type including `formula` and `delay`.
95. **A delay reading an output with a fallback** stores the substituted
    value ("Every reader of that output sees the substituted value").

### Sections 8 and 9

96. **Rule 8.1 — reset** also drops writes not yet taken up.
97. **Rule 8.4 — "For rule 7.2.1 the graph has run since the gap's
    tick".** The gap tick itself has run for zero.
98. **Rule 9.1 — `inputs` and `blocks` missing or null** are empty. A
    block's `in`, `settings`, `out` or `fallback` that is missing or null
    is empty; one that is not a map is refused.
99. **Rule 9.2 — a published name equal to an input's name** is refused
    as a signal with two writers.
100. **Rule 9.2 — block ids with points.** If two `<block id>.<port>`
     strings coincide the graph is refused.
101. **Rule 9.2 — looking a name up.** Inputs, then published names, then
     `<block id>.<port>`; the three cannot overlap after the checks above.
     A published signal can be read by its published name.
102. **Rule 9.3 — lengths of time.** No sign, no space, no exponent;
     `1.s` and `.5s` are refused.
103. **Rule 9.4 — "written without a point".** `ticks`, `substeps` and
     `max_catch_up` must arrive as Python ints; `2.0` is refused.
104. **Rule 9.5 — "a setting of the wrong type".** A bool where a number
     is wanted is refused; `on_bad` must be text; `only_new`,
     `use_uncertain` and a hysteresis `initial` must be bools.
105. **Rule 9.5 — an unknown port in `in`** for `formula` and `all_good`
     cannot occur; any text is a port name.
106. **Interface — `tick` outputs.** Only published signals are returned,
     numbers as floats; inputs from outside are not.

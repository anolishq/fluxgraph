# Assumptions made in building the C++ core

<!-- markdownlint-disable MD029 -- the entries keep one numbering across headings -->
The first slice of the C++ core (`include/fluxgraph/v2`, `src/v2`) was
written from `docs/semantics_spec_v2.md` as amended seven times, without
sight of `reference.py`, `formula.py` or `second/impl.py`. It has `formula`,
`all_good`, `delay`, `window` and `integrate`, and the whole of sections 6
and 8. A second slice, written the same way from the text as amended
eight times, adds eight block types, a third the models and the loop
rule, a fourth the estimator, a fifth the ninth amendment's commands, and
a sixth the tenth's derivative and slope between samples, a seventh
the eleventh's smaller faults, and an eighth the twelfth's `follow`; each
has a section of its own.

This lists each place where the text left a choice or could be read two
ways, with the reading taken. A choice the second reading already
recorded, where the core reads it the same way, is not repeated: see the
last section. Rule numbers are those of the text as it stands.

## What the text does not say, and a 64-bit engine has to

1. **Rule 6.11, the last tick there is.** "A call that would run a tick
   whose number ... does not fit in 64 bits, signed" is refused. Once tick
   2⁶³ - 1 has run, every later call that would run a tick is refused, and
   so is the call after any `rebase`, with or without a length, and after
   a restore of a state saved there: each would run a tick numbered one
   more. Only a reset gets the engine going again. A call at which no tick
   is due is still accepted and runs none. The text says what a host does
   after a `rebase` whose length is too long (rule 8.5) and nothing of an
   engine that has simply run out.
2. **Rule 6.11, a tick whose time does not fit.** A tick is due up to half
   a period before its time, so one can be due whose time is past the
   largest time. The call is refused, and so is every later call on that
   clock: the tick stays due. A `rebase` moves the ticks and ends it.
3. **Rule 6.11, a call that would run several ticks.** If the time of any
   of them does not fit, the whole call is refused and none runs. At a
   stall one tick would run, the last that was due; the call is refused
   if that tick's time or number does not fit, though the ticks before it
   would only have been passed over.
4. **Rule 6.2, "an age is how far apart two times are".** Read as: every
   comparison of an age, of how far ahead a write is stamped, and of how
   long the graph has run is made on the true difference, which can be as
   much as 2⁶⁴ - 1 ns and does not fit a signed 64-bit number. The core
   takes each difference unsigned, where it does fit.
5. **Counters in seconds.** `elapsed`, `missed` and `doubtful` are "numbers,
   in seconds": the count of ticks, as a double, times the period in
   seconds as a double. Past 2⁵³ ticks the count is no longer exact as a
   double. `gaps` likewise.
6. **Memory.** Appendix A: "an engine may refuse a graph it has not the
   memory for". The core refuses a `delay` of more than 2²⁴ ticks and a
   `window` of more than 2²⁴ periods, each naming the block and the limit.
7. **A formula's depth.** The text gives no limit. The core refuses a
   formula whose brackets, calls and prefix operators nest more than 200
   deep, so that reading one cannot run out of stack. A chain of
   operators of one level (`a + a + a + ...`) has no limit.

## The interface

8. **The graph is handed over as a value, not a file.** The core takes a
   `Setting`: a whole number, a number, a boolean, text, a list, or a map
   whose keys are text and keep their order. Everything section 9 says of
   a graph is judged by the core on that value (rule 9.7). What cannot be
   written as one is refused by whoever builds it and not by the core: a
   key that is not text, a value that is none of the six (a YAML `null`),
   and a whole number that does not fit in 64 bits, which the Python
   adapter passes as the nearest number, so that it is refused wherever a
   whole number is wanted and taken as a number elsewhere.
9. **Rule 9.4, whole numbers and numbers.** Where a whole number is wanted
   (`ticks`, `max_catch_up`, `max_waiting`) a number written with a point
   is refused. Where a number is wanted (`min_good`, an `initial`, a
   fallback, a constant on a port) a whole number is taken as that number.
10. **Rule 6.11, which refusals are the core's.** A write to a name that is
    not an input, a usable write with no value, a value of the other type,
    a state that is not one of the four, a call earlier than the last, a
    call whose tick does not fit, and a `rebase` of a length below zero
    are refused by the core. A time or a length that is not a whole
    number, or does not fit in 64 bits, cannot be passed to the core at
    all: the driver and the adapter refuse those.
11. **Rule 6.7, a write that is not usable.** It may be handed a value,
    which is not looked at.
12. **A call that runs no tick** "gives nothing else". The core's
    `outputs()` then still reads as the last tick run left it, and the
    driver gives none of it.
13. **Rule 8.2, a saved state** is a string of bytes: a mark, a number that
    stands for the graph, the number of the last tick run, and each
    block's memory in evaluation order. A state that names another graph,
    or is cut short, or holds what the core never writes, is refused and
    changes nothing.
14. **A block type of the catalogue that is not built** is refused with an
    error code of its own (`block_type_not_built`), apart from a type that
    is in no catalogue, which is an ordinary refusal (rule 9.5).

## Rules read one way of two

15. **Appendix A, `integrate`: the ratio of the period to `per`.** Settled
    by the eighth amendment: "worked once, exactly, and then taken as a
    double". The core now does that for every length that only scales a
    value (`per`, `tau`, `filter`): the ratio of two exact lengths, rounded
    once to the nearest double, ties to even. Before the amendment it
    divided two doubles, which is the same wherever both are exact in a
    double and can differ in the last place elsewhere.
16. **Appendix A, formula numbers: "A number too large for a double is
    refused."** One too small for a double, `1e-999`, is not refused: it
    is the nearest double, zero.
17. **Rule 7.3.8, a window with `only_new` on a tick whose input is not
    usable.** The text says a tick with a value that is not new "counts as
    `not_ready`". A tick whose input is `bad` holds none either, and I
    count it as `bad`, as a window without `only_new` does (rule 7.3.3).
18. **Rule 3.5, types round a loop.** A delay's type is its input's and a
    formula's is worked from its inputs', so in a loop neither is known
    first. The core takes a delay's type from its `initial` where it has
    one, and the type of an operation from the operation where its
    operands' are not known yet (`p + x` is a number whatever `p` is),
    goes round until nothing more is learned, and then checks every
    connection. Rule 5.4 puts a delay with an initial value on every loop
    the slice can make, so this always ends with every type known.
19. **`min` and `max` of two equal numbers** give the first. That decides
    the sign of a zero.
20. **Section 9, an input's `unit`** has to be text. It is not checked
    against anything (section 10). An input's `type` has to be `number`
    or `boolean`.
21. **Rule 9.5, a block with no `type`** is refused. A `formula` and an
    `all_good` with no input are refused (Appendix A: "one or more").
22. **A map with one key twice** cannot be written in YAML and can be built
    in C++. Two inputs of one name, and one port connected twice, are
    refused. Of a setting given twice the second is refused as unknown.
23. **Rule 7.3, the arithmetic of a window.** Mean: the plain sum over the
    count. Median of an even number: the sum of the middle two over 2.
    Slope: the sum of products of deviations from the means over the sum
    of squared deviations in time, with time in seconds from the oldest
    tick of the window. Another arrangement differs in the last places.
24. **The order of published outputs** is the order of the blocks in the
    graph and, within a block, of its `out`.
25. **A value crossing the driver** is written as the shortest decimal that
    reads back to the same double. A value that is not a number crosses
    as `nan`, without its sign or payload; the core reads any such value
    as `bad` (rule 7.2.3).

## The second slice: the blocks that hold, the timers, the latch and the PID

`deadband`, `lowpass`, `rate_limit`, `hysteresis`, `held_for`,
`since_true`, `latch` and `pid` were written from sections 7.4 to 7.7, the
head of section 7, section 8's table and Appendix A, as amended eight
times. All 79 vectors they opened agreed as first written, and so did
every probe against the two readings, so nothing here is a disagreement:
each is a place where the words allowed another answer.

26. **Rule 7.4.5, `aᵐ`.** Worked as `pow(a, m)` with `a = exp(-ratio)`,
    and as `a` itself where `m` is 1. `exp(-m · period / tau)` is the same
    number and can differ in the last place. The text gives the formula
    and not the arithmetic, as Appendix A now does for `integrate`.
27. **Rule 7.7.6, the arithmetic of the output and of a cut addition.**
    Settled since by rule 7.7.5, which gives the order: `kp·error` and the
    derivative first, then the integral with its addition made. The core
    first worked `kp·error + (integral + addition) + derivative`, which
    differs in the last place, and now follows the rule.
28. **Rule 7.7.12, "what it was before this one" on the tick of a
    reset.** The integral before this tick's addition, which on a reset's
    tick is zero and not what it held before the reset. Both readings take
    it so (the second records it); the text still does not say.
29. **Rule 7.7.7, `kd` of zero.** No `filter` is given, so there is no
    `a`: the core keeps no `f` and the derivative is zero. Nothing can
    show whether `f` is kept.
30. **Rules 7.7.8 and 7.7.9, a tick with an input that is not usable.**
    `limited` "is a boolean with the state of `y`", so it has no value
    either. `integral` is `good` with its value, and `uncertain` where
    `reset` is `uncertain` and true. A reset on such a tick still returns
    the integral and the counts to zero.
31. **Rule 7.7.12, an addition of nothing.** With `ki` or the error at
    zero the addition is neither more nor less than zero, and is neither
    cut short nor taken back. An addition cut short to nothing is "made",
    and taking it back changes nothing.
32. **Rule 7.4.7 and 7.4.8, `settle` across a gap.** The doubt is kept as
    a tick's number, and "the `settle` ticks after `d`" are ticks by
    number, so the ticks a stall or a rebase with a length passed over
    are among them.
33. **Section 8's table, "within `ride_through` of its last usable
    input".** The unusable ticks in a row before the gap and the ticks
    passed over, together, are no more than `ride_through`. A low-pass
    that holds across a gap decays over all of them on the input that
    comes back.
34. **Rule 7.4.11, "holding `initial` and nothing else".** That is so
    from the start and again after it has forgotten, until its first
    usable input. A gap adds nothing to a block in that state.
35. **Rule 7.6.1, the counters on the tick the timer stops.** They are
    zero on that tick already, `gaps` with them, and a gap while the
    timer is not running is counted nowhere unless the timer starts on
    the gap's own tick.
36. **Rule 7.5.4, a hysteresis with `initial`.** It is never undecided,
    so its first usable input is a change only if it goes to the other
    side. Until then the counts are from the first tick.
37. **Rule 7.6.2, `on_bad: unknown` after a gap of no known length.**
    "The output's value is true, with the state the rule above gives it":
    with an unusable input that state is the input's, and there is no
    value.
38. **Appendix A, ranges.** "Not negative" is read on the number: `-0.0`
    is taken. A `settle` or a `ride_through` of `0s` is taken. `step`,
    `up`, `rise`, `fall`, `kp` and `initial` may be written as whole
    numbers. A hysteresis's `initial` is a boolean and a rate limit's a
    finite number.
39. **Appendix A, `lowpass`: "`settle` (three `tau`)".** Three times
    `tau` over the period, rounded up, worked exactly from what the graph
    writes and not in doubles (rule 6.3: "there is no tolerance"). `tau`
    need not be a whole number of nanoseconds.

Read the same way as the second reading records them: the reach of a rate
limit is the rate times the period in seconds, worked once in doubles; an
output exactly at `max` with its addition whole is not `limited`; a gap
that passed over no tick does not start a PID's derivative again; a
`held_for` holding across a gap measures the stretch from before the gap;
`gaps` starts at one where a count starts again on the gap's own tick; a
`reset` that is true clears a latch whatever `set` is.

## The third slice: models, the exact step and the loop rule

The eight model types, the step of rule 7.8.7 and the whole of rule 7.8.8
were written from section 4.9, section 7.8, the head of section 7, section
8's table and Appendix A. Every vector they opened agreed as first
written, but for the wording of one refusal, and so did five probes of
the loop rule and of gaps against the two readings. Each entry is a place
where the words allowed another answer; the ones marked **(guess)** are
where I could not tell from the text which was meant.

40. **Rule 7.8.7, how the step is worked.** "How it does so is its own
    affair." Scaling and squaring of the series for `exp(X)` and for
    `(exp(X) - I) / X`, with `X = A · period / 2ˢ` of row sum at most a
    half, in arithmetic of twice a double's digits, and rounded to doubles
    once at the end. `Bd` is the integral times `B`, both still in the
    wide arithmetic. Measured against 150-digit decimal arithmetic the
    worst entry is out by 1.1 parts in 10¹⁶, at the bound as inside it.
    The same steps in plain doubles are out by 2 parts in 10¹¹ in `Ad` and
    by 6 parts in 10⁹ in a `Bd` at the bound, which is past the promise:
    the rule's "in ordinary double arithmetic ... loses accuracy in
    proportion to that number" is right, and the promise is not kept by
    every ordinary method.
41. **Rule 7.8.7, the bound.** The row sums of `A` in doubles, the largest
    times the period in seconds as a double, refused where that is not at
    most 100,000: one that is not a number is refused too. `state_space`
    has no bound. "Not finite" is judged on `Ad` and `Bd` as doubles.
42. **Rule 7.8.6, the arithmetic of a default `settle`.** `r` is three,
    times minus one over the rate, over the period in seconds, in doubles
    in that order, and `settle` is `ceil(r - 10⁻⁹)`. For one state the rate
    is `A`'s entry. For two, `h` is half the sum of `A`'s diagonal as the
    core holds it and `d` is from the settings. Where `h²` is more than
    `d` and `h` is not below zero there is no constant; settings in their
    ranges cannot reach that.
43. **Appendix A, which settings of a named model are required.** Those
    with no value in brackets: `initial` of a `thermal_mass` and
    `initial_a`, `initial_b` of a `thermal_rc2` among them. **(guess)**:
    the table gives 1.x's other initial values a default of zero and
    these none.
44. **Rule 7.8.4, an input that has never been usable.** There is no last
    usable value to step on, so the model does not step, whatever its
    `ride_through`. Its outputs, where they read it, are on zero (rule
    7.8.5).
45. **Rule 7.8.4, "until the input is usable again" after a gap of no
    known length.** Kept for each input by itself: an input that comes
    back is ridden through again when it next drops out, though another
    has not come back yet. **(guess)**
46. **Section 8's table, a model block's steps at a known gap.** A tick
    passed over has "nothing usable on any of its inputs", an input given
    a constant among them: each input rides on its last value while the
    unusable ticks in a row before the gap and the ticks passed over so
    far are within `ride_through`. Up to 64 such steps are taken one by
    one; more are reached by squaring the step, which is the same to
    within rounding ("what is specified is the result", rule 7.9.9).
47. **Rule 7.8.6, which ticks are doubts.** A tick on which any input,
    direct or deferred, is uncertain is a step on an uncertain value, and
    a doubt. A direct input that is uncertain makes the outputs uncertain
    on that tick as well (rule D).
48. **Rule 7.8.8, what a loop is.** The blocks that can each reach every
    other by connections of either kind, worked over blocks alone:
    inputs from outside and constants are on no loop. A loop that holds
    no model block is found and nothing is kept of it (rule 5.6).
49. **Rule 7.8.8, "used a value that was not good, read from outside the
    loop".** The value is what the block read: a value a fallback put in
    for a block outside the loop is uncertain, and starts a doubt. It is
    looked at once in the tick, after the first phase, for direct and
    deferred inputs alike. A formula's use is worked from the top of the
    formula down by rules 7.1.1 to 7.1.3: an operation uses both
    operands; an `and` or an `or` that is decided uses its good deciders,
    or all its deciders where none is good; a `when` uses its condition
    and, where that is usable, the branch it took.
50. **Rule 7.8.8, "gave an output that was not usable".** As the block
    gave it, before any fallback, and after rule 3.6: an output that came
    out not finite is one. The model block's own outputs count like any
    other's.
51. **Rule 7.8.8, when what was uncertain becomes good.** Before the
    first phase of every tick at which the loop is not within `settle` of
    its doubt, a tick with no doubt yet among them, the delays, windows
    and low-passes of the loop are told, and change what they hold for
    good. So a value taken in as uncertain at tick `k` is given as
    uncertain only if the loop is in doubt at every tick from `k + 1` to
    the tick it is given.
52. **Rule 7.8.8, the model on a loop.** Its own doubt is kept and saved
    and not looked at: only the loop's makes it uncertain, and a direct
    input from outside that is uncertain or unusable at the tick itself
    (rule 7.8.5).
53. **Section 8's table, a loop at a gap.** "The tick before the one that
    runs is a doubt, its loop's if it is on one": set for every loop that
    holds a model block, at a stall and at a rebase alike, unless the gap
    passed over no tick.
54. **Rule 8.2, "each loop's doubt" in a saved state.** It is saved and
    put back. It cannot show: a restore is a gap of no known length, and
    that gap makes the tick before the one that runs the loop's doubt,
    which is later than any that was saved. The same is so of a model
    block's own doubt. Only a state saved before any tick is restored
    without a gap, and it has no doubt.
55. **Rule 7.8.8, the sum held against `settle`.** A delay's `ticks`, a
    window's length in periods, and a low-pass's `settle` in ticks,
    written or its default of three time constants rounded up.
56. **Appendix A, `linear`.** `D` and `initial` left out are zeros. A row
    of the wrong length is refused naming the setting and the row. The
    names of inputs and of states may be those of model outputs; only an
    output's may not. `state_space` takes `B` and `C` as lists of numbers
    and `D` as one number.

Read the same way as the second reading records them: a doubt at tick `k`
does not shorten an earlier doubt that has not run out; a model on a loop
keeps its own counters; a block of the loop that "is connected to" an
output counts whether or not it used it; the arithmetic of `r` and of the
bound; which eigenvalue gives `settle`.

## The fourth slice: the estimator

The estimator, its process noise and the check that a measurement
carries a sample's time were written from section 7.9, rule 3.7, section
8 and Appendix A. Every estimator vector agreed once one fault of mine was
out (a prediction skipped where the tick was already in doubt), and so
did two probes against the two readings. Entries marked **(guess)** are
where the text did not say.

57. **Rule 7.9.2, how `N` is worked.** As `Ad` is: on a small step, the
    series whose `k`-th layer is `L(k) = A·L(k-1) + L(k-1)·Aᵀ` over `k!`,
    from `L(0) = Q`; then doubled, `N ← N + E·N·Eᵀ`, all in arithmetic of
    twice a double's digits and rounded once. A variance of `N` read off
    the core is within 2.5 parts in 10¹⁶ of 150-digit arithmetic up to the
    stiffness bound. For `state_space` it is `q` times the period in
    seconds as a double.
58. **Rule 7.9.2 and 7.9.4, the arithmetic of the covariance.** In plain
    doubles, as written: `(Ad·P)·Adᵀ + N`; the gain as `P·cᵀ` over `s`;
    `((1 - g·c)·P)·(1 - g·c)ᵀ`, and `g·v·gᵀ` added to that. `P` is not
    made symmetric afterwards. The text gives the forms and not the
    order; another order differs in the last place.
59. **Rule 7.9.2, "as they were at the tick before".** The value then, or
    the last usable value where it was not usable then, is in either case
    the last usable value as of that tick, and one number is kept for each
    input. "Never been usable by then" is by the tick before.
60. **Rule 7.9.3, tick 0.** There is no prediction at tick 0 and there is
    a correction: a measurement written before the first call is
    considered at it.
61. **Rule 7.9.3, an uncertain measurement on a port with no
    `r_uncertain`.** It is not considered, so it does not become the
    sample last considered: the same sample written again as `good`,
    with the same time, is then considered. **(guess)**
62. **Rule 7.9.5, giving in.** The measurement that would be one more
    than `max_refused` is not counted in `refused_<port>`, ends the run,
    and makes the tick uncertain as "one over the gate used". Its
    innovation is unchanged by the growth; its normalised innovation
    squared, in the output and in what the port keeps, is the one from
    before.
63. **Rule 7.9.6, when a port is judged.** On every tick once it holds
    `over` of them, a tick with no measurement among them: it "keeps its
    last word". The mean is the plain sum over `over`.
64. **Rule 7.9.7, the sigma clause.** It makes that state's two outputs
    uncertain and no other state's. Every other clause is of the block.
65. **Rule 7.9.7, "this tick is the one a gap ran, unless the gap passed
    over no tick".** A gap of no known length is not one that passed over
    no tick: its tick is uncertain.
66. **Rule 7.9.8, `since_<port>`.** The tick's time less the sample's, as
    a true difference in nanoseconds, over 10⁹ as a double; zero where
    the sample is stamped after the tick.
67. **Rule 7.9.9, many predictions.** Up to 64 are made one by one. More
    are gathered by doubling the step: `(M, v, S)` twice is
    `(M·M, M·v + v, M·S·Mᵀ + S)`. With a model input never usable the
    state stays and `N` is added that many times, past 64 as one product.
68. **Rule 7.9.8, names.** Two outputs of one name are refused, as the
    rule says. Two inputs of one name, a measurement port named as a
    model input is, are refused too. **(guess)**: the rule speaks of
    outputs only.
69. **Appendix A, `q`, `p0` and `sigma_max`.** `q` and `p0` have to name
    every state, and `sigma_max` any of them; a name that is no state's
    is refused. `q` is not negative, `p0` is more than zero, `gate` is not
    negative, `r` is more than zero. A model's `settle` or `ride_through`
    inside `model` is refused as unknown there: "that model's own
    settings (not the model settings above)".
70. **Rule 7.9.3, the way the time comes.** From the port, back through
    a delay to what the delay reads, and through a formula to the input
    whose sample time it takes, until an input from outside. Refused
    where the way reaches a block that gives the time of the tick, a
    formula that does, a constant, or comes back on itself. A fallback on
    the way is not looked at: its value has no sample time and is never
    considered.
71. **Rule 7.9.4, a model with a direct input.** Accepted where no
    measurement is of an output that reads it. The estimator's model
    inputs are deferred whatever the model's `D` is.
72. **Section 9, an `in` key that is empty.** Until this slice the core
    refused any input port with an empty name. The text has no such
    rule: rule 9.2 is of names a block's settings give, and `all_good`
    takes its inputs "under any names". The compiler no longer refuses
    it, and an estimator's empty measurement port is refused by rule 9.2
    naming `measure`.

Read the same way as the second reading records them: at a rebase with a
length the variance grows after the predictions and once; a port is
inconsistent between measurements; a run of refusals is of measurements
considered and not of ticks; a measurement taken by rule 5 makes its tick
uncertain; a constant on a measurement port is refused; any measurement
used ends "no measurement has been used since".

## The fifth slice: commands, acting by the call, and `track`

The ninth amendment (rules 6.13, 7.4.12, 7.4.13, 7.7.13, 7.7.14, 9.8) was
written from its text. All 47 vectors it added agreed once one fault of
mine was out (a PID did not wait to track from the start), and so did the
three new graphs of `compare.py`. Entries marked **(guess)** are where the
text did not say.

73. **Rule 6.13, where a held output is put back.** As soon as its block
    has given it, in the first phase, so that every block after it in the
    order reads what was held, and every block in the second phase. What
    the block worked out for it at the catch-up tick is dropped, its
    state for rule 7.8.8 with it.
74. **Rule 6.13, "feeds".** Worked over blocks when the graph is compiled:
    the block that gives a command, and every block one of whose outputs
    a feeding block reads, on any port and through any type of block. A
    `pid` whose `integral` alone is read by a feeding block feeds.
75. **Rule 6.13, a rate limit "along a chain ... that passes through no
    `pid`, the one that gives the command among them".** Read as: start
    from each block that gives a command and is not a `pid`, and go back
    through what each reads, never through a `pid`; a `rate_limit` reached
    so acts by the call. One that feeds two commands, one way through a
    `pid` and one way not, acts by the call.
76. **Rule 6.13, `m`.** The ticks the call ran, or `act_for` if less: 1
    at the first call and at a gap. A block that does not act by the
    call acts for one period at every tick, the last of a long call
    among them.
77. **Rule 7.4.12, "a catch-up tick is one with a usable input for rules
    3 and 4".** The count of unusable ticks in a row goes back to none,
    as a usable input makes it; it is not merely left where it was. Only
    where the block holds a value it took from an input. **(guess)**
78. **Rule 7.4.12, `limited` at a catch-up tick.** With a usable input,
    whether the input is other than the value held, `initial` alone
    among them; false where nothing is held. `track` is not looked at
    there. It is of that tick, beside a `y` held from the call before.
79. **Rule 7.4.12 and 7.7.13, the arithmetic of `m` periods.** In the
    order the text gives: `up` times the period, and that times `m`;
    `ki·error·period`, and that times `m`.
80. **Rule 7.4.13, `track`.** Looked at only on a tick with a usable
    input on which the block acts, where it holds nothing or `initial`
    alone. It then stands in for both, and the input is limited from it.
    Having taken the input, the block holds a value it took, and `track`
    is not looked at again until it has forgotten.
81. **Rule 7.7.14, waiting to track.** Kept as one flag beside what the
    PID already remembers. It is not the same as "the derivative has no
    tick before": after a reset on a tick with an input lost the
    derivative starts again and the PID does not wait, and at a catch-up
    tick with both inputs usable a PID that acts by the call has a tick
    before and still waits. The flag is not saved and the saved layout is
    unchanged: a state is restored into a gap of no known length, which
    makes the PID wait (rule 8.6), and a state saved before any tick is
    the start, where it waits too.
82. **Rule 7.7.14, the tick it stops waiting.** With `track` usable the
    integral is `track` less the first sum of rule 5, and that is also
    "what it was before this tick's addition" for rules 6 and 12. With
    `track` not usable it stops waiting all the same and the integral is
    left: it does not go on waiting for a readback.
83. **Rule 7.7.13, a catch-up tick with an input not usable, or a
    reset.** As at any tick: the PID waits to track from the one, and the
    other returns the integral to zero and ends the waiting.
84. **Rule 9.8, an entry of `commands` that is not text** is refused as
    a name that is not a published one. `act_for` with no command is read
    and checked and does nothing.
85. **Rule 8.2, what is held.** Not saved. After a reset or a restore the
    first tick is the last of its call, so nothing held is read before it
    is given again.

## The sixth slice: a derivative and a slope between samples

The tenth amendment (rules 7.7.7 and 7.3.6, sections 8.5 and 8.6, and
Appendix A's `window`) was written from its text. The six vectors that
differed before it agreed as first written, and so did `compare.py`.

86. **Rule 8.2, what is saved.** Neither saved layout changed. A PID now
    remembers the time of the measurement it last took, and a window a
    time for each sample, and neither is saved: a state is restored into
    a rebase, which forgets every sample time (rule 8.5), so the PID has
    nothing remembered and every sample of the window is at its tick's
    time before either is next read. A PID's saved "there is a
    measurement remembered", its value and `f` are for the same reason
    never read back to any effect; they stay in the layout.
87. **Rule 7.7.7, the arithmetic.** `dt` is the difference of the two
    times as a whole number of nanoseconds, made a double once and
    divided by 10⁹. `s` is the rise over `dt`. `a` is `exp(-dt / filter)`
    with `filter` the nearest double, in seconds, to the length the graph
    writes. `f` is `a·f + (1 - a)·s` with `1 - a` worked from `a`.
    `exp(-dt · (1 / filter))`, `f + (1 - a)·(s - f)`, or `-expm1` for
    `1 - a` are the same to within rounding and would pass every vector.
88. **Rule 7.7.7, a tick with an input not usable.** Nothing is
    remembered after it, and `f` is put to zero there. The text puts `f`
    to zero at the next tick with both usable; nothing can show the
    difference.
89. **Rules 7.7.7 and 8.6, a stall.** The derivative starts again at a
    stall as at a rebase: the table's row and the paragraph after it say
    so, though a stall is on one clock and forgets no other sample time.
90. **Appendix A, a window's times.** A sample keeps its sample time
    where it carried one when it was taken. One that carried none, and
    every sample after a rebase, is at its tick's time: the time of the
    tick that runs, less a period for each tick it is back from it,
    worked at every tick. A time is never kept as one number where it is
    a tick's: the tick's time less so many periods need not fit in 64
    bits, and only differences of times are ever taken, in 128 bits by
    hand.
91. **Rule 7.3.6, "has one time".** Judged on the times themselves: every
    sample the slope would be of is no time at all from the first. Not
    on the sum of squares coming out at nothing, which rounding can
    leave a little over.
92. **Appendix A, the least-squares sums.** As written: times from the
    earliest tick's sample among those the slope is of; the two means as
    sums in tick order over their number; then the two sums in tick
    order, and one over the other. Taking times from any other origin is
    the same slope to within rounding and would pass every vector, and so
    would the sums in another order.
93. **Rule 7.3.6, which samples.** Where the window is `good` on two or
    more `good` samples the slope is of those, and `bad` where they have
    one time, as the rule says. Where it is of the usable samples and
    they have one time it is `bad` too.

## The seventh slice: a reason, a total past `max_missed`, and model blocks on one loop

The eleventh amendment (rules 3.8, 7.7.2 and 7.8.8) was written from its
text. The eight vectors that differed before it agreed as first written,
and so did `compare.py`.

94. **Rule 3.8, the room for a reason.** A `Value` has a `reason`, a
    16-bit whole number, which is 0 wherever the core makes a value. It
    lies where the padding was, so a value is 24 bytes as before. It is
    not saved and not handed to a host, as the rule allows, and a write
    cannot carry one: no saved layout and no line of the driver changed.
95. **Rule 7.7.2, a total past `max_missed`.** One state, `uncertain`,
    with the value, whatever the input is at the tick: a tick with an
    unusable input past `max_missed` is `uncertain` and not `good`.
96. **Rule 7.8.8, "joined in a ring directly or through formulas
    alone".** Worked among the model blocks of one loop. One takes
    another's output where a way leads from one of its inputs, direct or
    deferred, back to an output of the other through blocks of type
    `formula` and no other: an `all_good` on the way is another block. A
    ring is two or more that each come to the other by such takings, in
    one step or several. One that comes back to itself, straight or
    through formulas, and to no other, is no ring. **(guess)** for
    "through formulas": the rule says of one that takes its own output
    only that it is no ring, and I take a plant with a formula for its
    controller as that.
97. **Rule 7.8.8, "the same `settle`".** Compared as whole ticks. The
    refusal for a `settle` not written names the first model block
    without one; the refusal for two that differ names the first model
    block of the loop and the first that differs from it.
98. **Rule 7.8.8, what else is as it was.** The memory of the loop's
    delays, windows and low-passes is held against the one `settle`; a
    loop that holds a model block and an estimator is refused; the
    loop's doubt is one, and every model block on it is told of it.

## The eighth slice: `follow` on a rate limit and a PID

99. **Rules 7.4.14 and 7.7.15, "need not be connected".** A block whose
    `follow` is left unconnected never follows: it is not a `follow` the
    block cannot use. One given a constant (rule 4.7) is connected. The
    refusal is judged by what the block's `in` names, so a `track` given
    a constant is a `track` that is given.
100. **Rule 7.4.14, "counts towards `ride_through`".** The block keeps
     one count, of ticks since it last took a value: unusable ticks in a
     row, as before, and ticks it followed with no `track`. Such a tick
     adds one whatever the input is, and the block does not forget at it
     however large the count. At the next tick with an unusable input
     where it does not follow, it rides through if the count is less
     than `ride_through` in ticks and forgets otherwise. A block that
     holds `initial` alone, or nothing, counts nothing.
101. **Rules 7.4.12 and 7.4.14 together.** Rule 14 counts from "the last
     tick the block took a value at"; rule 12 makes a catch-up tick one
     with a usable input, which "ends a run of unusable ticks". The count
     is one, so a catch-up tick of a rate limit that acts by the call
     ends the ticks followed with no `track` as well. Both readings do
     the same; no vector in the suite says so.
102. **Rule 7.4.14 and a gap.** "It forgets nothing at such a tick" is of
     a tick. A gap of known length adds the ticks passed over to the
     same count and forgets where that is past `ride_through`, as it did
     (rule 8.6), whether or not the block was following before it.
103. **Rule 7.4.14, the states.** With `track` usable and `follow` not,
     `y` and `limited` are `uncertain`, an `uncertain` `track` among
     them. With `track` not usable they have the state of `track`
     whatever `follow` is. The input's state plays no part.
104. **Rule 7.7.15, the state of `y`.** The state of `track`, or
     `uncertain` where `follow` is not usable, and nothing else: not the
     setpoint's or the measurement's, and not `uncertain` for a reset
     that is `uncertain` and true. `limited` is the same.
105. **Rule 7.7.15, the state of `integral`.** With both inputs usable,
     the worse of their two states, and `uncertain` where `reset` is
     `uncertain` and true; with either not usable, `good` but for such a
     reset. That is rule 9 with what rule 8 would have given `y`.
106. **Rule 7.7.15, a reset while it follows.** All of rule 10 at that
     tick: the integral and the counts to zero and the derivative to its
     start, so the measurement of that tick is the first it remembers.
     The integral is not set from `track` at that tick, and the PID
     waits to track after it.
107. **Rule 7.7.15, by the call.** At a catch-up tick a PID that follows
     does all that it does at any tick it follows: the integral is set
     there, the counts count and the derivative runs. The periods it
     would act for at the last tick of a call are not used: it adds
     nothing.
108. **What is held, and what is saved.** Nothing new in either block.
     The PID's flag that it waits to track is set at every tick it
     follows and is not saved, as before: a restore sets it. The rate
     limit's count of unusable ticks is the count of entry 100, saved
     where it was. A saved state of either block is as long as it was
     and means what it did, but for that count.

## Recorded already, and read the same way

These are in `conformance/second/ASSUMPTIONS*.md`; the core takes the same
reading of each, and its agreement with both Python readings on the
vectors, in `compare.py --cpp` and in the probes described in the report
says so:

- `rebase` before any tick does away with the writes waiting and nothing
  else, so an input's `initial` still stands in afterwards (rules 7.2.1
  and 8.5);
- restoring a state saved before any tick is a reset, and sets the count
  of writes thrown away to zero (rules 8.3 and 6.8);
- with `max_waiting` reached, the write just made is among those that may
  be thrown away (rule 6.8);
- "the same graph" is the same description, key order and all (rule 8.2);
- a delay "can reach its own input" when it is on a cycle of connections
  of either kind, itself alone included (rule 5.4), and a block that reads
  its own output directly is a loop of one (rule 5.3);
- ties in the order are broken by comparing ids as strings (rule 5.2);
- a formula with one signal input is counted by port (rule 3.7), and a
  formula whose `sample_of` input has no sample time at a tick gives its
  output none;
- `ln(0)` is `bad`, as a result that is not finite (rule 7.1.4);
- `window` and `max_missed` are counted lengths, whole periods, and
  `max_missed` is compared in ticks (rule 6.3);
- `inputs` or `blocks` left out is none of them (section 9);
- a published name that is an input's is a signal with two writers.

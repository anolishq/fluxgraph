# Assumptions made in building the C++ core

<!-- markdownlint-disable MD029 -- the entries keep one numbering across headings -->
The first slice of the C++ core (`include/fluxgraph/v2`, `src/v2`) was
written from `docs/semantics_spec_v2.md` as amended seven times, without
sight of `reference.py`, `formula.py` or `second/impl.py`. It has `formula`,
`all_good`, `delay`, `window` and `integrate`, and the whole of sections 6
and 8. A second slice, written the same way from the text as amended
eight times, adds eight block types; its entries are in a section of
their own.

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
    The output before limiting is worked as
    `kp·error + (integral + addition) + derivative`, in that order. Cut
    short at `max`, the integral becomes `max - kp·error - derivative`, or
    stays if that is less, and `y` is `max` itself and not the sum worked
    again, which need not come back to `max` exactly. Another order
    differs in the last place, and decides on which side of a limit an
    output within rounding of it falls.
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

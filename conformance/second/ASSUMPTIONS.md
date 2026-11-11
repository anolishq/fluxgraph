<!-- markdownlint-disable MD029 -- entries keep one numbering across sections -->
# Assumptions made in implementing the proposal

Each entry gives the place, the words at issue, why they do not settle the
matter, and what `impl.py` does. Entries are grouped by section of the
proposal, not ranked.

## Section 3 — values

1. **3.6**, "No usable value is not finite. A block output that would be is
   `bad`, whatever the block." Not said whether the block's *state* is
   also protected. I check outputs only. An `integrate` total that
   overflows stays infinite inside the block and reads `bad` until a
   reset; a `lowpass` or `kalman1` likewise.
2. **3.6 with 7.10.** Not said in which order the finite check and a
   fallback apply. I make the output `bad` first, then substitute the
   fallback, so a non-finite output with a fallback reads `uncertain`
   with the fallback value.
3. **3.7 / 7.2**, "it is either **new**, written since the tick before".
   When one call runs several ticks, the tick before the last one is a
   missed tick, which ran after the host wrote; read literally the write
   is then not "since the tick before". I take an input as new at the
   first tick that is not missed after the write (so new at the last tick
   of a catch-up call, and new at tick 0 if written before the first
   call). A write followed by a call that runs no tick stays new for the
   next tick that runs.
4. **7.2**, "An input is new at a tick if it was written". Not said
   whether a write of `not_ready` or `bad`, or a write that rule 7.2.4
   turns `bad`, counts as new. I count every write as new, whatever its
   state.
5. **7.2**, never-written input with an `initial`. Not said whether it is
   new. I say never new (it was not written).

## Section 4, 5 — blocks, order, loops

6. **4.4**, two phases. For every block type whose inputs are all direct I
   do the state update in the first phase, when the block gives its
   output, because the output "at a tick depends on that input at the same
   tick" and nothing else can observe the difference. Only `delay` does
   anything in the second phase.
7. **4.7**, "a number, or `true` or `false`". A constant that is not
   finite (YAML `.inf`, `.nan`) is not addressed. I refuse it at compile.
8. **4.7 / 9.2**. A string in `in` is always a signal name; the strings
   `"true"`/`"false"` are not constants. Only a Python bool is a boolean
   constant, and only an int/float (not bool) a number constant.
9. **5.2**, "Ties are broken by block id". Not said how ids compare. I
   compare them as Python strings (code-point order) and pick, at each
   step, the smallest id among the blocks whose direct dependencies are
   all placed. No output depends on this.
10. **5.4**, "A delay on a loop has an initial value. Without one ... the
    graph is refused." Not said whether *every* delay on a loop needs one
    or one per loop, nor what "on a loop" is. I refuse any delay without
    `initial` that can reach its own input through any chain of inputs,
    direct or deferred. That refuses loops that would in fact not stay
    `not_ready` (for example one passing through `all_good`, or through a
    block with a fallback).
11. **5.3**, "names the blocks on it". I name one loop (the blocks of one
    cycle), not every block caught behind it.
12. **3.5 / Appendix A delay**, "Its type is its input's". On a loop the
    input's type depends on the delay's own. I take a delay's type from
    its `initial` when it has one (bool → boolean, number → number), else
    from its input; and then refuse a delay whose input is of the other
    type than its `initial` (reported against `initial`).

## Section 6 — time

13. **6.3**, "it does not go backwards" and **6.4**, "A call with a `now`
    earlier than the last one is refused". "The last one" taken as the
    last *call*, including a call that ran no tick. An equal `now` is
    accepted (and runs nothing). A `now` that is NaN or infinite is not
    addressed; I refuse it (ValueError).
14. **6.4**, "every tick not yet run whose time is no more than half a
    period after `now`". I compute it in floats exactly as written:
    `t0 + k*period <= now + period/2`, with `t0` the first call's `now`.
    A tick lying exactly half a period ahead is run. Two implementations
    that form the tick time differently (`t0 + k*period` against repeated
    addition) can disagree at that boundary.
15. **6.5**, "The call says how many ticks it ran." and outputs. The
    interface returns the outputs of the last tick only; nothing is said
    about outputs of missed ticks and I do not keep them.
16. **6.6**, "the time it was sampled". A sample time that is NaN is not
    addressed; I refuse the write (ValueError). An infinite one is
    accepted (+inf then reads as a sample from the future, `bad`; -inf as
    too old if there is a maximum age, otherwise usable).
17. **6.6**, write validation generally. Not addressed: a write to a name
    that is not an input (I raise KeyError), an unknown state string
    (ValueError), a usable write whose value is `None` or of the other
    type (TypeError; an int is accepted for a number input, a bool is
    not). For `not_ready`/`bad` writes the value and the sample time are
    ignored and dropped.
18. **6.6**, "Its age is the tick's time less its sample time". Computed
    in floats, `max(tick_time - sampled, 0.0) > max_age`, with tick time
    `t0 + k*period`. Not exact arithmetic; a vector with an age exactly
    at the maximum needs times exact in binary.
19. **7.2.4**, "its sample time is more than one period after the tick's
    time". Computed as `sampled > tick_time + period`. A sample exactly
    one period ahead is usable.
20. **7.2.4** applied to booleans. "if the value written is not finite"
    cannot apply to a boolean; the age and future tests I apply to both
    types.
21. **7.2.2**, "until the graph has run for longer than the input's
    maximum age". "Has run for" taken as the tick index times the period
    (exact rational comparison with the maximum age): at tick `k` the
    input is `bad` when `k × period > max_age`. Because of 8.4 ("Time
    does not pass while a graph is not running") this is not wall time
    since tick 0.
22. **7.2.1 with 7.2.2**. In a missed tick an input with an `initial`
    that was never written is `bad` ("the first of these that applies"),
    not `uncertain` with its initial. Stated by the ordering, noted
    because 7.8 says the initial value "is what lets a plant model start".
23. **7.2**, "A write of `not_ready` does not grow old". Nothing is said
    of a write of `bad`; it too stands until written over.
24. **7.2**, "In a missed tick nothing is new." This sentence is in the
    paragraph on inputs. I apply it to external inputs only. A block with
    no signal inputs ("A block output is new at a tick if the block has
    no signal inputs") is still new in a missed tick, and a delay still
    gives the newness its input had at its own tick.
25. **7.2**, "A block output is new ... if any of its inputs is new."
    Applied whatever the output's state (a `not_ready` output can be
    new), to connected inputs only, and unchanged by a fallback. For
    `delay` before its history exists and without an `initial`, the
    `not_ready` output is not new (the text says only that "its initial
    value is not new").

## Section 7.1 and the formula grammar

26. **7.1.1 against 7.1.4**, "The result of an operation takes the worst
    state among its operands" and "A division by zero ... is `bad`". When
    the dividend is unusable and the divisor is a usable zero, which wins
    is not said. I apply 7.1.4 only when every operand is usable:
    `not_ready / 0` is `not_ready`, not `bad`.
27. **7.1.2**, "If any usable operand of an `or` is true". `a or b or c`
    is evaluated as nested two-operand operations (grouping from the
    left). I believe this gives the same state as treating it as one
    operation of three operands, but the text does not say which it is.
28. **7.1.2**, "When no operand decides, rule 1 applies." Then the value,
    if the worst state is usable, is the ordinary two-valued result.
29. **7.1.3**, "takes the value of the branch it chose, with the worse of
    that branch's state and the condition's". If the chosen branch is not
    usable the result has that branch's state and no value.
30. **7.1.4**, "the logarithm or square root of a negative number, and
    any result that is not finite". `ln(0)` is `bad` (not finite).
    `pow` follows C `pow` via `math.pow`; a domain error (negative base
    with a fractional exponent, zero to a negative power) or overflow is
    `bad`; `pow(0, 0)` is 1. `exp` overflow is `bad`. Underflow to zero
    is a usable zero.
31. **7.1.6**, "`==` and `!=` compare exactly." For numbers this is IEEE
    equality (so `0.0 == -0.0`). Unary minus of zero gives `-0.0`, which
    is returned as such.
32. **Appendix A, Operators**, "from loosest to tightest: `or`; `and`;
    `not`; the comparisons ...; unary minus". Read as a grammar:
    `not` takes a `not`-expression or a comparison as its operand
    (`not a < b` is `not (a < b)`; `not not a` is accepted); a comparison's
    operands are additive expressions, so `a == not b` is refused without
    brackets; unary minus takes a unary or a primary (`--a`, `a - -b`,
    `a * -b` accepted; `-a * b` is `(-a) * b`). None of these is stated.
33. **Appendix A, Operators**, "Comparisons do not chain". Read as
    covering every pair of comparison operators at one level, so
    `a < b == c` is refused as well; `(a < b) == c` is accepted.
34. **Appendix A, Numbers**, "Nothing else". A number directly followed by
    a letter, digit, underscore or point (`2x`, `1e`, `1.`, `1.2.3`) is
    refused rather than split into two tokens. A literal too large for a
    double (`1e999`) is refused at compile.
35. **Appendix A, Names**, "a letter". ASCII letters only.
36. **Appendix A**, "Spaces between tokens mean nothing. A formula is one
    line." I accept the space and the tab between tokens and refuse every
    other character, including a newline anywhere in `expr`. An empty
    formula is refused.
37. **Appendix A, Functions**. A function name must be followed by a
    bracketed argument list of exactly the listed length; a name that is
    not a function followed by `(` is refused. Function arguments are
    full expressions (`or` level).
38. **Appendix A**, "`and`, `or`, `not`, `true`, `false` and the function
    names are not input names." A formula block with an input port of
    such a name, or of a name outside the name grammar, is refused (in
    practice through "every input of the block must be used").
    `all_good`'s port names are not restricted at all.
39. **Appendix A**, "`formula` and `all_good` take one or more inputs". A
    block of either type with no inputs is refused, so a formula of
    constants only (`1 + 2`) cannot be written without a dummy input.
40. **Appendix A, Types**, numbers into `==`. An input given an integer
    constant is a number; all numbers are doubles.

## Section 7.3 and `window`

41. **7.3.3**, "fewer usable samples than `min_good × n`". Compared in
    floats as written: `count < min_good * n`. With `min_good: 0.7` and
    `n = 10` the product is 7.000000000000001, and seven samples are too
    few.
42. **7.3.3**, "takes the worst state among its ticks that hold none". I
    read "ticks that hold none" as the window's ticks holding no usable
    sample, and their state as the input's state at each (or `not_ready`
    for ticks before the start).
43. **7.3.4**, "`good` if every one of its `n` ticks holds a `good`
    sample". A tick from before the graph started holds no sample, so a
    window that passes `min_good` while still filling is `uncertain`.
44. **7.3.5**, "With one it is `bad`". Applies only once rule 3 is passed;
    below `min_good` the slope takes rule 3's state like the others.
45. **Appendix A window**, "`slope` is the least-squares slope of value
    against time, per second, taking the oldest tick of the window as
    time zero". Time of slot `i` (0 = oldest tick of the window, whether
    or not it holds a sample) is `i × period` seconds; only usable
    samples enter the fit. Ordinary least squares with intercept.
46. **7.3.6**, `count` is given as a number (a double), and counts from
    tick 0 on, including while filling.
47. **Appendix A**, "`window` at least one period". And being a counted
    length (6.2) it is a whole number of periods.

## Section 7.4 — deadband, lowpass

48. **7.4.2**, "if the last usable input was no more than `ride_through`
    ago". Measured in ticks: at the `m`-th consecutive unusable tick the
    last usable input was `m` periods ago; held while `m × period <=
    ride_through`.
49. **7.4.2**, "the block keeps what it holds", and **7.4.4**, "The first
    usable input is taken as it is." After a gap longer than
    `ride_through` the block still holds its old value, and the next
    usable input is *not* a first input: a lowpass filters on from the
    old `y`, a deadband compares with the old value. Only the first
    usable input ever (or since a reset/restore of fresh state) is taken
    as it is. During a ride-through a lowpass does not move.
50. **Appendix A deadband**, "has moved by `step` or more". Computed as
    `abs(x - held) >= step` in floats. With `step: 0` every input is
    taken.
51. **6.2 and `ride_through`**. It is counted, so it must be a whole
    number of periods. Its default "(0)" is zero ticks. A time setting
    must be a string with a unit; a bare number, even `0`, is refused as
    the wrong type (9.3).

## Section 7.5 — hysteresis

52. **7.5.2 against 7.5.3**, "Until its input has been at or beyond one of
    the thresholds, its output is `not_ready`" and "With an unusable
    input ... its output takes the input's state." Before the first
    threshold crossing, with a `bad` input, I give `not_ready` (rule 2
    first). Also before the first crossing a usable input between the
    thresholds gives `not_ready`, not the input's state.
53. **7.5.1**. `rise` is tested first, but with `rise > fall` enforced the
    two cannot both hold.

## Section 7.6 — timers and latch

54. **7.6.1**, "the output is `good` if every input since it started was
    `good`, and `uncertain` if not". Under `hold`, an unusable input that
    the timer ran through counts as an input that was not `good`, so the
    output stays `uncertain` for the rest of that run even after usable
    `good` inputs return.
55. **7.6.1 hold**, "for at most `hold_limit`" / "When the unusable
    stretch grows longer than the limit". The stretch at its `m`-th
    consecutive unusable tick is taken as `m` periods long (as in entry
    48). With `hold_limit` of `h` ticks the timer runs through `h`
    unusable ticks and stops on tick `h + 1`. `hold_limit: 0s` therefore
    holds through nothing. The other reading (first unusable tick "counts
    as no time at all", by analogy with the input becoming true) would
    hold one tick longer.
56. **7.6.1 hold**, "While it runs the output is `uncertain`, and true
    once the time has run out." Before the time has run out the value is
    false.
57. **7.6.1**, usable true input after the timer was stopped by an
    unusable one: the timer starts afresh on that tick, with no time
    counted.
58. **7.6.1**, `hold_limit` given with `on_bad: reset` is refused
    ("refused without it" read as: without `on_bad: hold`).
59. **7.6.2**, "Its clock starts at the first tick". Taken as tick 0 of
    the graph. After a restore the saved clock is kept.
60. **7.6.2**, "True when its input has not been true for longer than
    `time`." With the Appendix: true on a tick more than `n` ticks after
    the clock was last set. So at the start of a run with the input never
    true it becomes true at tick `n + 1`.
61. **7.6.2 `assume_false`**, "the output is `uncertain`". Only on the
    unusable tick itself. Once a usable input returns the output takes
    that input's state again, `good` included, although the clock ran
    through ticks that were only assumed false. Under `unknown`, "The
    clock is not touched" I read as: it is not restarted, and goes on
    counting ticks.
62. **7.6.3**, latch on a tick where `reset` is usable and true: "clears
    it, on that tick, and wins over `set`". The latch is not set on that
    tick even if `set` is true; the output is then false with the state
    of `set` (or `set`'s state alone if `set` is unusable). The same
    output is given when `reset` is true and the latch was not set.
63. **7.6.3**, "False until its input `set` is first true". A `set` that
    is usable and true sets it whether `good` or `uncertain`; the output
    is `good` either way ("Once set, its output is `good`").

## Section 7.7 — integrate

64. **7.7.2**, "the period, added up". I keep a count of unusable ticks
    and give `count × period`, not a running float sum; these differ in
    the last bits. `missed > max_missed` is compared in whole ticks.
65. **7.7.4 and 6.2**. `max_missed` is treated as a counted length ("a
    limit"), so it must be a whole number of periods. `per` and `tau` may
    be any length, but more than zero.
66. **7.7.3**, "every input it has added was `good`". Since the last
    reset. Before anything is added the total is 0 and `good`; on tick 0
    with an unusable input it is 0 and `uncertain`.
67. **7.7.4**, "the total is `bad` once `missed` is more than that". Until
    a reset brings `missed` back to zero. While `bad`, the block still
    adds usable inputs.
68. **7.7.5**, the reset tick. "before that tick's addition": on the same
    tick a usable `x` is then added, or an unusable `x` adds one period to
    `missed`.
69. **Appendix A**, "adds `x × period / per`". Evaluated in that order in
    doubles, with `period` and `per` in seconds.

## Section 7.9 and Appendix B — kalman1

70. **7.9.4**, "gone longer than that without a correction", "the
    measurement it last corrected on". The first usable, new measurement
    (Appendix B: "`x = z`, `var = r`; nothing else happens") is counted as
    a correction for both tests. `k - last_correction > max_coast` in
    ticks; `max_coast` is a counted length and must be whole periods.
71. **7.9 / Appendix B**, the `model` input. An unusable `model` has no
    effect on the output state: the outputs can be `good` while `model`
    is `bad`. 7.8 ("does not advance ... Its outputs take the worst
    state among its inputs") is taken not to apply, since 7.9 and
    Appendix B give the rules. An unusable `z` likewise only delays the
    correction.
72. **Appendix B**, "process noise `q` per second": `q × period` with the
    period in seconds, as written. `tau` may be any length; `q` and `r`
    are plain numbers.
73. **Appendix B**, inputs "direct" by the Appendix A default ("An input
    is required and direct unless the table says otherwise"), though that
    sentence is under Appendix A's table.
74. **7.9.1**, both `x` and `sigma` are `not_ready` before the first
    measurement, and share one state afterwards.

## Section 7.10 and `fallback`

75. **7.10**, "a value to give when that output is not usable". The
    block's own state is not affected by its fallback; the newness of the
    output is unchanged. A fallback on an output that is never unusable
    (`count`, `missed`, `all_good.y`) is accepted and never used.
76. **Appendix A**, "a constant of that port's type". An int is accepted
    for a number port; a bool for a number port, or a number for a
    boolean port, is refused.

## Section 7.8

77. **7.8**. No block implemented here falls under it (every catalogue
    type has its own rule), so it is not implemented.

## `delay`

78. **Appendix A**, "its output is its input at tick `k - ticks`, state
    included, as that input was then". What the delay stores is what any
    reader saw: after an upstream fallback, and `bad` for an external
    input in a missed tick. A constant may be the input.
79. **Appendix A**, "`ticks` a whole number". A float with a whole value
    (`2.0`) is accepted; a bool is not.
80. **Appendix A**, "`initial` ... finite". `initial` may be a boolean.

## Section 8 — reset, save, restore

81. **8.1**, "its initial state". Reset also forgets every write to an
    external input (they are "never written" again) and the last `now`,
    so a call after a reset may carry any `now`.
82. **8.2**. The saved state holds the tick index, every block's state,
    and the external inputs as last written, with their sample times and
    whether each is still waiting to be new. It does not hold the time of
    tick 0 or the last `now`.
83. **8.4**, "the next call runs the tick after the last one saved, at the
    `now` it is given". The time of that tick is the call's `now`, later
    ticks follow at whole periods from it, and exactly one tick runs in
    that call. The check against a `now` earlier than the last call's is
    dropped across a restore. Input ages are still the tick's time less
    the saved sample time, so saved writes may read as old (or, with an
    earlier clock, as from the future) straight after a restore.
84. **8.3 and its Open note**, "a graph that is not the same". Same means
    the same graph dict: equal after serialising with sorted mapping
    keys. The order of blocks in the list and the spelling of values
    (`1` against `1.0`, `"1s"` against `"1000ms"`) matter; the order of
    keys does not. Anything that is not an object from `save()` is
    refused with ValueError.
85. **8.2**, restoring into an engine that has already run. Allowed; it
    replaces everything, including writes made since.

## Section 9 — the graph file

86. **9**, `period`. Required; a length of time as in 9.3, more than
    zero. Missing or zero is refused.
87. **9**, `blocks` missing or empty. Accepted (a graph that computes
    nothing); `tick` then returns an empty dict.
88. **9.1**, input declarations. A declaration that is `None` (YAML
    `name:`) is read as `{}`. `type` must be `number` or `boolean`.
    `initial` must be a constant of the input's type and finite.
    `max_age` is any length of time, zero allowed. `unit` is accepted
    and ignored, whatever it is.
89. **9.2**, "a port left out is not published, and another block can
    still read it as `<block id>.<port>`". I let `<block id>.<port>` name
    every output port, published or not.
90. **9.2 / 9.4**, "a signal with two writers". Refused: a published name
    equal to an input's name; two ports (of one block or two) published
    under one name; a published name or an input name equal to some
    block's `<block id>.<port>` (except a port published under its own
    dotted name).
91. **9.4**, "a block with no id". An id must be a non-empty string; an
    integer id from YAML is refused.
92. **9.4**, `in`, `out`, `settings`, `fallback` missing or `None` are
    read as empty. A value in `in` that is `None`, a list or a mapping
    is refused. A value in `out` must be a non-empty string.
93. **9.4**, "a setting of the wrong type". A number setting (`step`,
    `rise`, `fall`, `min_good`, `q`, `r`) must be an int or float, not a
    bool or a string, and finite. A time setting must be a string in the
    form of 9.3. `on_bad` must be one of the block's strings.
94. **9.3**, "a number and a unit with nothing between them". No sign, no
    exponent, no surrounding space; `1.` and `.5s` are refused. Lengths
    are held as exact rationals for the whole-periods test, so `0.3s` at
    a period of `0.1s` is three periods.
95. **Appendix A**, which settings are required. Every setting with no
    bracketed default is required: `expr`, `window`, `step`, `tau`,
    `rise`, `fall`, `time`, `on_bad`, and for `kalman1` all four.
    `max_missed`, `initial` and `hold_limit` show "(none)" or are
    conditional.
96. **Appendix A**, "`step`, `ride_through`, `time`, `hold_limit` and
    `max_missed` not negative". The time grammar has no sign, so for the
    times this cannot fail. `time: 0s` is allowed: `held_for` is then
    true from the tick after its input becomes true.
97. **9.4**, the order in which faults are looked for is my own (9.5 says
    it is not specified).

## Interface

98. **`tick` return value**. A number output is returned as a float, a
    boolean as a bool, and `None` whenever the state is not usable.
    Outputs are those of published names only.

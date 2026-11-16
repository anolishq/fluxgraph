# A third reading: where the text left a choice

Written while building a third engine from `docs/semantics_spec_v2.md`
as it stood at commit `c1e1651`, called `spec.md` below, and from nothing
else: no vector and no other implementation. Every line that starts with
`>` is copied from that text. The engine itself (`impl.py`, with its
`selftest.py`) is not kept; what it found is in
[README.md](README.md#a-third-reading). Entry 5, entry 9 and the first,
second, third and fifth items of list (a) have since been mended in the
text, and entry 13 stated.

"Rides on it" says whether two careful implementers would plausibly give
different outputs: **high** (different states or values in ordinary
graphs), **medium** (different in a corner a test vector could reach),
**low** (last-place rounding inside the 10⁻⁹ tolerance, or a refusal on an
odd graph).

## Interface: what was built, and what is refused at run time

- `Engine(graph)`, `write`, `tick`, `save`, `restore`, `reset`, `rebase`,
  `info`, `CompileError`: as the task brief gives them. No operation was
  added: the text names no host operation beyond these.
- `engine.info` after a call that ran a tick has the keys `ran` (ticks
  run), `gap` (bool), `passed_over` (a whole number; `None` for "nobody
  knows"; 0 when not a gap), `tick`, `time`, `thrown_away`, `waiting`,
  `outputs`. After a call that ran no tick it is `{'ran': 0}` (entry 4).
- `ValueError` is raised, and nothing changes, for everything rule 6.11
  lists: a `now` earlier than the last accepted call's; a write to a name
  that is not an input; a usable write with no value or a value of the
  other type; a state that is not one of the four; a write time or `now`
  that is not a whole number or does not fit in 64 bits; a call that would
  run a tick whose number or time does not fit; a `rebase` length that is
  not whole, is negative, or does not fit. Also `ValueError`: a write with
  `at=None` (entry 1), and a `restore` of a state from another graph
  (rule 8.2).

## The entries

### Host, time and writes

**1. A write with no time (rules 6.7, 6.11).**

> Every write carries one.

The brief's interface allows `at=None`. Readings: (a) refuse it; (b) take
it as the call's `now` to come; (c) take it as "the time of the last
tick". The text has no default, so (a): `ValueError`. Rides on it: high
for any harness that passes `None`; none otherwise.

**2. A value given with a `bad` or `not_ready` write (rule 6.7).**

> a state, a value if
> the state is usable, and a **time**

Readings: refuse a value that should not be there, or ignore it. Rule
6.11 lists what is refused and this is not in it, so the value is
ignored. Rides on it: low.

**3. What "of the input's type" means for a number (rules 6.11, 7.2.3).**

> a usable write with no value, or one whose value is not of the
> input's type

and

> `bad`, if the value that stands is not finite.

A written NaN or infinity must be accepted (or rule 7.2.3 has nothing to
do), so it is: it stands, and reads `bad`. A Python `int` is taken as a
number; a `bool` is not a number and a number is not a boolean. An `int`
too large for a double is taken as infinity (so it stands and reads
`bad`). Rides on it: medium (a harness that writes `1` for `true`).

**4. What a call that ran no tick gives (rules 6.6, 6.10).**

> If
> none is due the call runs no tick, says so, and gives nothing else.

Taken literally: `tick` returns `(0, None)` and `info` is `{'ran': 0}`;
the time and number of the last tick run are not repeated. Writes thrown
away at such a call (stamped ahead) are added to the count the next call
that runs a tick reports. Rides on it: medium for a harness that reads
`info['time']` after every call.

**5. The count of writes thrown away across a restore that is a reset
(rules 6.8, 8.3).**

> a reset sets it to zero, and a restore or a
> rebase does not.

and

> Restoring a state saved before any tick had run is a reset, and neither.

The two pull apart for one case. Taken: such a restore does everything a
reset does except zero the count ("stays the engine's own", rule 8.2).
Rides on it: medium, on one number in one corner.

**6. Which ticks of a stall must fit in 64 bits (rule 6.11).**

> a call that would run a tick whose number or whose time does not fit
> in 64 bits, signed.

At a stall only the last due tick "runs"; the ticks passed over are
earlier and smaller, so only the tick that runs is checked. For a
catch-up within `max_catch_up` every tick is checked. Rides on it: low.

**7. A rebase's length is counted from the last tick run, whatever came
between (rule 8.5).**

> `rebase` takes a
> length, counted from the time of the last tick run.

After a restore "the last tick run" is taken as the tick before the saved
"next tick"; after a stall it is the tick the stall ran. The tick a
rebase runs is numbered `last + max(1, due)` and passes over
`max(0, due - 1)`, `due` being the length over the period rounded half up.
Rides on it: low (the text nearly says it).

**8. Whether a block may read a published signal by its published name
(rules 9.1, 9.2).**

> A graph that reads a signal
> which is neither an input nor a block's output is refused.

and

> any output, published or not, can be read by another block
> as `<block id>.<port>`.

Readings: (a) a block's output is read only as `<block id>.<port>`;
(b) also by the name `out` publishes it under. A published name is "a
signal name", and rule 4.2 says "a signal is connected by naming it", so
(b). A name is resolved as `<block id>.<port>` first, then as an input,
then as a published name. Rides on it: high for compile (one reading
refuses graphs the other runs).

**9. Which names are "of the form `<block id>.<port>`" (rule 9.2).**

> No input and no published
> signal may have a name of the form `<block id>.<port>` for a block and
> port of the graph.

"Port" could be output ports only (the only ones that can be read that
way) or any port. Taken: any port, input or output, of an existing block;
the block id is the text before the first dot. An input named
`room.temp` is accepted when no block is `room`. Rides on it: low.

**10. Keys that may be left out of the graph file (section 9).**

> **Proposed.** The shape, not the final keys:

`period` is required. `inputs`, `blocks`, `commands` and a block's `in`,
`settings`, `out` and `fallback` may be left out or null and are then
empty. An input's entry must be a map (a null entry has "no maximum
age"). Rides on it: low.

**11. An input's `unit` (rule 9.1, section 10).**

> The graph file of section 9 has no
> key for a port's unit or for the strict policy

`unit` is accepted on an input if it is text, and nothing is checked: no
port can declare one, so no connection can join two declared units. See
list (b).

**12. Writing `none` for a setting whose default is "(none)" (Appendix A).**

> A setting with a value in brackets may be left out and takes that value.

`none` is accepted as a written value only where the text writes it:
`max_age: none` and `consistency: none`. `initial: none`,
`sample_of: none`, `gate: none`, `min: none` and the like are refused (as
a value of the wrong type, or a name that is not an input). The other
reading accepts them as "left out". Rides on it: medium for compile.

**13. What "a setting that is a whole number" covers (rule 9.4).**

> A setting that is a whole number is written without a point: `2`, not
> `2.0`.

Readings: (a) settings whose type is a whole number (`ticks`, `over`,
`max_refused`, `max_catch_up`, `max_waiting`, `act_for`) are refused when
they arrive as a float; (b) any setting whose value happens to be whole
must be written without a point, so `kp: 2.0` is refused. Taken: (a). A
number setting accepts `2` and `2.0` alike. Rides on it: medium for
compile.

**14. Which settings are counted lengths, and which "any length"
(rules 6.2, 6.3).**

> Every length of time a block counts (a window, a timer, a limit) is a
> whole number of periods, and a graph where one is not is refused.

and

> A setting that only scales a value (`tau`, `per`) is not a
> time the engine keeps

Counted (whole periods, not negative, fits 64 bits as nanoseconds):
`window`, `ride_through`, `settle`, `time`, `hold_limit`, `max_missed`,
`lag`. Any length more than zero, not necessarily whole nanoseconds:
`tau` (low-pass and `first_order_process`), `per`, `filter`. Kept times
(whole nanoseconds, 64 bits): `period`, `max_age`, `max_ahead`.
`max_missed` is the doubtful one: it is "a limit" and is compared with
`missed`, which is a count of ticks times the period, so it is taken as
counted; a reader who takes it as a plain number of seconds, or as any
length, accepts graphs this refuses. Rides on it: medium for compile.

**15. How a delay's type is found on a loop (Appendix A, `delay`).**

> On a loop, where its input's type waits on its own, its
> type is its initial value's, which rule 5.4 sees that it has.

Types are worked out block by block; when no block can be typed from its
inputs, the delay with the least id that has an initial value takes its
type from it, and the working goes on. Afterwards every delay's input
type must equal its output type and its initial value's type. Rides on
it: low (it changes only which fault a bad graph is refused for).

**16. Port names of `all_good` and `formula` (rule 9.2, Appendix A).**

> `formula` and `all_good` take one or
> more inputs, `all_good` under any names and `formula` under names its
> grammar allows.

`all_good`: any text that is not empty, dots included. `formula`: the
grammar's names, not a reserved word or function name. Rides on it: low.

**17. Limits of this engine (Appendix A).**

> an engine may refuse a graph
> it has not the memory for, a long window among them

and

> An engine reads a formula nested at least 100 deep, counting each
> bracket, function and operator that is inside another, and may refuse
> one nested deeper than it can read.

A delay's `ticks` or a window's length over 10,000,000 is refused. A
formula with brackets, functions or unary operators nested more than
1,000 deep, or whose tree is deeper than 8,000, is refused. Rides on it:
none inside those limits.

### Values and formulas

**18. The sample time of a formula's output when the input it takes it
from carries none (rule 3.7).**

> A `formula` output carries the sample time of the input its
> `sample_of` setting names. A formula with exactly one signal input
> and no `sample_of` carries that input's.

When that input has no sample time (it is not usable but the formula's
result is, or it is an input's `initial`, or a fallback's value, or a
delay's `initial`), readings: (a) the output carries none; (b) it carries
the tick's time. Taken: (a), "that input's", which is none. Consumers then
do what they do with no sample time: a window with `only_new` takes no
sample, an estimator's measurement is never due, a PID's derivative and a
plain window's slope use the tick's time. Rides on it: high wherever an
`initial` or a fallback passes through a formula to one of those blocks.

**19. What a formula "uses" when an operand is not usable (rule D,
rule 7.8.8).**

> For this, a formula
> uses what rule D says, and every other block counts as using every
> input it has, in either phase, whatever its own rule says of them.

Rule D speaks only of `uncertain` operands. Taken, for every state: an
arithmetic operation, comparison or function uses all its operands; a
decided `and`/`or` uses the deciding operands, and only the `good` ones
when one of them is `good`; an undecided one uses both; `when` uses its
condition and, if the condition is usable, the branch taken. An input is
used when any part of the tree that reached the result used it. So
`a or b` with `a` true and `good` does not use a `bad` `b`, and that `b`
read from outside a loop starts no doubt. Rides on it: medium (loop
doubt only).

**20. Arithmetic details of the formula functions (rule 7.1.4,
Appendix A).**

> `pow` is C's.

`pow` is Python's `math.pow`, which is C's with its domain and range
errors raised; every raised error and every result that is not finite is
`bad` (so `pow(0, -1)` and `ln(0)` are `bad`, as "any result that is not
finite"). `min(a, b)` gives `b` if `b < a`, else `a`; `max` likewise;
which zero comes back from `min(0, -0)` is not specified. Rides on it:
low.

**21. Number tokens at the edges (Appendix A).**

> **Numbers:** digits, an optional point and more digits, an optional
> exponent (`e` or `E`, an optional sign, digits).

`1.` and `.5` are refused. In `2e` or `2e+` the `e` is not an exponent
and starts a name, which then makes the formula a syntax error; `2e3x` is
a number followed by a name, likewise refused. Rides on it: low.

**22. The value of `and`/`or` when no operand decides (rule 7.1.2).**

> When no operand decides, rule 1
> applies.

Rule 1 gives the state. The value, when both are usable, is true for
`and` and false for `or`. Rides on it: none; noted because the text gives
only the state.

### Inputs

**23. An input with an `initial` goes from `uncertain` straight to `bad`
(rule 7.2.1).**

> otherwise `not_ready`, until the graph has run for more than the
> maximum age, and `bad` from then on.

With `initial` and no rebase the first bullet holds up to the maximum
age, and "otherwise" then gives `bad` at once: such an input is never
`not_ready`. Rides on it: low (the text supports it).

### Windows

**24. The order of a window's sums (rule 3.6, Appendix A `window`).**

> a statistic is worked as a plain sum in double arithmetic.

The order is given only for the slope. `mean` is summed from the earliest
tick's sample to the latest, from zero, then divided by the count.
`median` of an even number is `(a + b) / 2`, which overflows as the
text's own example needs. Rides on it: low (last place).

**25. A slope whose sum of squares rounds to nothing (rule 7.3.6).**

> That is judged on the times, and not on a sum of squares that
> rounding may leave a little over nothing.

The other way round is not covered: times that differ but whose sum of
`(t - t̄)²` is exactly zero in doubles (times a nanosecond apart at a
large offset cannot do it, since times are taken from the earliest
sample, but denormal-scale differences are not excluded by the text).
Taken: `bad`, as a division by zero would be under rule 3.6. Rides on it:
low.

**26. What an `only_new` window remembers of "the last sample the window
took" (rule 7.3.8).**

> its sample time is later than that of the last sample the window
> took.

That time is kept when the sample leaves the window, and across a stall
(which empties nothing but the ticks passed over). A reset or a rebase
forgets it.
Rides on it: low.

**27. Which samples a slope is of, case by case (rule 7.3.6).**

> Where the window holds fewer than two `good` samples and at least two
> usable ones, its slope is of its usable samples and is `uncertain`,
> whatever rule 5 says of the rest.

Worked out as: fewer usable than needed, the others' state; else if the
window is `good` by rule 5 and holds two or more `good` samples, the
`good` ones, `good`; else if it holds two or more usable, the usable
ones, `uncertain`; else `bad`. Then `bad` if all of the chosen samples
have one time. Rides on it: medium (the text gives the cases in pieces
and they have to be put in an order).

### Blocks that hold a value

**28. How "moved by `step` or more" is worked (rule 7.4.1, Appendix A).**

> **`deadband`.** The comparison with `step` is exact.

Taken as `abs(x - held) >= step` with the subtraction in doubles; an
implementation that compares in exact arithmetic differs when the
subtraction rounds. Rides on it: low.

**29. How `a` is worked for a low-pass (rule 7.4.5).**

> where `a = exp(-period / tau)`

The ratio is worked exactly from the two lengths as written, then taken
as a double, then `exp` of its negation (as the text says of
`integrate`'s ratio). The other reading divides two doubles of seconds.
`1 - aᵐ` is one less the double `aᵐ`. Rides on it: low (last place).

**30. Ride-through counts across a gap (rules 7.4.3, 8.6).**

> If the last tick passed over is within `ride_through` of its last usable input, it holds what it held

The `n` ticks are added to the run of unusable ticks, and an unusable
input at the tick that runs is the next of the same run. A block holding
nothing counts no run. Rides on it: low.

**31. The reach of a rate limit (rules 7.4.9, 7.4.12).**

> `up` times the period, and that times `m`

`up * period` with the period as the double nearest its seconds, then
`* m` for a block that acts by the call. Where the input is out of reach
the output is `held + reach` in doubles, which rounding may put a last
place past where exact arithmetic would. Rides on it: low.

**32. A rate limit whose `y` would not be finite (rules 3.6, 7.4.10).**

> `limited` is a boolean with that
> state: true when the output is not the input.

If `held + reach` overflows, `y` is `bad` by rule 3.6 and `limited` is
given `bad` with it, since it has "that state". The same is done for a
PID: `limited` is "a boolean with the state of `y`", so a `y` made `bad`
by rule 3.6 makes `limited` `bad` and no addition is judged against
`applied`. The other reading leaves `limited` with the input's state.
Rides on it: low (needs values near 10³⁰⁸).

**33. A rate limit that follows with `track` not usable while it holds
nothing it took from an input (rule 7.4.14).**

> The tick counts towards `ride_through`, which is counted from the last tick the
> block took a value at

Such ticks are counted, and the count is used only once the block holds a
value it took; holding `initial` alone it does not ride through whatever
the count (rule 7.4.11). Rides on it: low.

### Timers and latches

**34. `held_for` holding on an unusable input before the time has run out
(rule 7.6.1).**

> While it runs on an unusable input
> the output is `uncertain`, and true once the time has run out.

Before the time has run out the output is `uncertain` and false (it has
a value). Rides on it: medium (one could read "no value until true").

**35. A usable true `reset` on a latch that is not set (rule 7.6.3).**

> `elapsed` counts from the tick it was last cleared, or from the first
> tick.

Taken: it is "cleared" all the same, so `elapsed`, `doubtful` and `gaps`
start again at that tick. On the clearing tick `doubtful` counts the tick
only if the latch was not set when the tick began and `set` was not
`good`. Rides on it: medium (a reset held true keeps `elapsed` at one
period under this reading).

**36. "The first tick" (rules 7.5.4, 7.6.2, 7.6.3, 7.7.3, 7.8.6).**

> or from the first tick if it has not

Taken as tick 0 (after a reset, the new tick 0), not the first tick after
a restore or a rebase. Rides on it: low.

### Integrators and the PID

**37. A PID's addition, and its sum (rules 7.7.5, 7.7.6, 7.7.13).**

> the addition is `ki·error·period`,
> and that times `m`

`(ki * error) * period`, the period the double nearest its seconds, and
for a PID that acts by the call that product times `m` (a PID that does
not act by the call does not multiply by 1, which is the same number).
The output before limiting is `(kp·error + derivative) + integral`. With
`kd` of zero the derivative term is a plain `+0.0` and `f` is not kept.
Rides on it: low (last place; the text fixes the order of the sum).

**38. The PID's derivative arithmetic (rule 7.7.7).**

> with
> `a = exp(-dt / filter)` and `1 - a` worked as one less that `a`

`dt` is the difference in nanoseconds divided by 10⁹ as one division;
`filter` is the double nearest its seconds, worked exactly from what the
graph writes; `s` is `(measurement - remembered) / dt`. Rides on it: low.

**39. What the take-back of rule 7.7.12 compares, and takes back.**

> Where `applied` is usable at a tick whose addition was made, whole
> or cut short, and is less than `y` by more than `applied_within`
> with the addition more than zero

`y` is the block's own `y` of that tick after limiting. "The addition"
is the amount `ki·error·period·m` before any cutting short, so an
addition cut short to nothing (the integral "stays as it is") still
counts as made, and is tested by its sign. Taken back means the integral
becomes what it was after any reset or `track` setting of that tick and
before the addition. An addition of exactly zero (`ki` or the error zero,
or a catch-up tick) is not judged. Rides on it: medium.

**40. A PID that acts by the call, an input lost at a catch-up tick
(rule 7.7.14).**

> The PID **waits to track** from the start, from
> a tick where either input is not usable

Taken to include a catch-up tick: an input unusable at one makes it wait,
and it then tracks at the last tick of that or a later call. Rides on
it: medium.

**41. The integral's state at a tick where `y` is `bad` by rule 3.6
(rule 7.7.9).**

> `integral` is the integral, a number: `uncertain` on a tick where `y` is

`bad` is not `uncertain`, so `integral` keeps the state its inputs give
it (and is itself `bad` only if it is not finite). Rides on it: low.

### Models

**42. A named model's matrices are doubles, worked in a stated order
(Appendix A, rule 7.8.7).**

> **The named models** are each `linear` with its matrices written out
> from a few physical settings.

Readings: (a) each entry of `A` and `B` is worked in double arithmetic
from the settings and the step is exact for those doubles (so the named
model equals the `linear` that spells out the same doubles); (b) the
entries are exact rationals of the settings and only `Ad`, `Bd` are
rounded. Taken: (a), with these forms: `thermal_mass`
`A = [-h/C]`, `B = [1/C, h/C]`; `thermal_rc2`
`A = [[-(ha + c)/ma, c/ma], [c/mb, -(hb + c)/mb]]`,
`B = [[1/ma, ha/ma], [0, hb/mb]]`; `first_order_process` `A = [-1/tau]`,
`B = [gain/tau]` with `tau` the double nearest its seconds;
`second_order_process` `A = [[0, 1], [-(w·w), -((2·zeta)·w)]]`,
`B = [[0], [(w·w)·gain]]`; `mass_spring_damper`
`A = [[0, 1], [-k/m, -c/m]]`, `B = [[0], [1/m]]`; `dc_motor`
`A = [[-R/L, -Ke/L], [Kt/J, -f/J]]`, `B = [[1/L, 0], [0, -1/J]]`,
`C = [[0, 1], [1, 0], [Kt, 0]]`. Rides on it: low for values (parts in
10¹⁶, times up to 10⁵ in an exponent: still under 10⁻⁹), medium for the
bound and the default `settle`, which sit on these doubles.

**43. How `Ad`, `Bd` and `N` are worked (rules 7.8.7, 7.9.2).**

> How it does so is its own affair: what is specified is the result, to
> within rounding

`A`, `B` and `q` are taken as the exact values of their doubles, the
period as the exact rational the graph writes. `exp(A·h)`, the integral
of `exp(A·s)`, and the integral of `exp(A·s)·Q·exp(Aᵀ·s)` are summed as
Taylor series in decimal arithmetic of 120 digits for `h` the length
halved until the row-sum norm of `A·h` is at most 1/4, then doubled back
(`Φ(2h) = Φ(h) + E·Φ(h)`, `N(2h) = N(h) + E·N(h)·Eᵀ`, `E ← E·E`), and
each entry is rounded once to a double. `Bd` is that integral times `B`,
rounded once. For a model whose `exp(A·s)` passes through values many
orders larger than its final entries (strongly non-normal `A` at the
bound), 120 digits may not be enough; no check is made. Rides on it: low
within the bound for ordinary models.

**44. The bound, in doubles (rule 7.8.7).**

> The sum is of `A`
> alone, in double arithmetic, and a graph within rounding of the bound, or
> of what a double holds, may be taken either way.

Row sums of absolute values in order, the largest times the double
nearest the period in seconds, refused when not `<= 100000.0`. Rides on
it: none beyond what the text allows.

**45. A named model's default `settle`, in doubles (rule 7.8.6).**

> with `r` three of the constant over the period, it is the least
> whole number not less than `r - 10⁻⁹`.

`r = 3.0 * (-1.0 / λ) / period`, `λ` the largest real part: `A`'s one
entry for a model of one state; for two, `h = (A₀₀ + A₁₁) / 2.0`, `d` as
Appendix A gives it in doubles, `λ = h` where `h·h <= d`, else
`d / (h - sqrt(h·h - d))`. No constant (so no `settle`) where `λ >= 0`,
which includes a `d` of zero. `settle` is not less than zero. Rides on
it: medium where `r` is near a whole number, as the text says.

**46. The order of a model's step and output sums (rule 7.8.7).**

> `x' = Ad·x + Bd·u`

Each new state is the row of `Ad` times `x` summed left to right from
zero, plus the row of `Bd` times `u` summed likewise. Each output is the
row of `C` times `x` plus the row of `D` times `u`, the same way. Rides
on it: low (last place; an undamped model drifts apart as the text
says).

**47. A model input after a gap of no known length (rule 7.8.4).**

> After a gap of no known length it does not, until the input is usable
> again: that is so of each input by itself.

Each input, a constant among them, is marked; a marked input that is
unusable is not ridden through whatever its count, and the mark goes when
the input is next usable (for a constant, at the tick the gap runs, so
the step of that tick is taken). The last usable value is kept for rule
7.8.5. Rides on it: medium.

**48. When a model's "last usable value" of a direct input is taken
(rule 7.8.5).**

> they are worked out on that input's last usable value,
> or on zero if it has had none

It is taken in the second phase with every other input, so in the first
phase of a tick it is the value of an earlier tick. Rides on it: none.

**49. `state_space` with `settle`, and its `N` (Appendix A, rule 7.9.2).**

> For `state_space` it is `q` times the period on each
> state's own variance.

`state_space` and `linear` take `settle` and `ride_through` when given.
`N`'s diagonal is `q` (as the shortest decimal of its double) times the
period in seconds, worked exactly and rounded once. Rides on it: low.

### Loops (rule 7.8.8)

**50. Where the ring check looks.**

> no model blocks in it are joined in a ring directly or through
> formulas alone

It is made over every model block of the graph (a ring is a loop, so
this is the same thing). Block X "takes" model Y's output when any input
of X, direct or deferred, is connected to an output of Y, or to an output
of a formula from which Y is reached through formulas only. A ring is a
strongly connected set of two or more model blocks in that relation.
`all_good` is not a formula and breaks a ring, as any other block does.
Rides on it: medium for compile.

**51. What sets a loop's doubt.**

> the loop's **doubt** is the latest tick at which a block in it used a
> value that was not `good`, read from outside the loop, or gave an
> output that was not usable on a port that a block of the loop is
> connected to

"From outside" is taken as: an input of the graph, or an output of a
block not in the loop (a constant is always `good`). The value is the one
the block reads, a fallback's or a held command's among them. "Gave an
output that was not usable" is judged before any fallback, on outputs of
blocks of the loop only, and for an output that is held (rule 6.13) at a
catch-up tick by what it was at the tick it is held from. Rides on it:
medium.

**52. When what a delay, window or low-pass holds is made `good`.**

> at a tick where the loop is not within `settle` of its doubt, before
> any block gives its outputs, and at a tick before any doubt too

"Within `settle` of its doubt" at tick `k` is `k <= doubt + settle`
(a doubt is always before `k` when this is judged). With a `settle` of
zero that is never so, and the values are made `good` at every tick. At
the tick run by a gap that passed over a tick, or whose length nobody
knows, the loop's doubt is the tick before, so nothing is made `good`
there unless `settle` is zero. Rides on it: medium.

### The estimator

**53. Places are numbered by tick number (rule 7.9.2).**

> a
> whole number of sixteenths of a period, counted from tick 0, so that tick
> `k` is at `16·k`.

Kept as `16·k` across stalls and rebases alike; after a rebase the tick
that runs has its new number and time, and a sample's place is worked
from that tick. A place is `floor(16·k - 16·(t - ts)/period + 1/2)`
exactly; for `state_space`, `16·floor(k - (t - ts)/period + 1/2)`. Rides
on it: none.

**54. Model inputs: which value a new one is compared with, and its
place.**

> At a tick's second phase a model input that is usable,
> and whose value is not the one it last had, has that value from the
> latest of three places

"The one it last had" is the newest value given to it, even one in force
only from a later place. A value from the same place as the newest
replaces it. A constant, or a block's output with the tick's time, has
the tick's place as its sample's place. Rides on it: medium.

**55. "At the tick before" (rule 7.9.7).**

> at the tick before, a model input was `uncertain` or not usable

The tick before is the last tick that was run; the flag is part of what
a save holds. After a gap that passed over no tick it is the tick run
before the gap. After a gap that passed over ticks the gap's own clause
covers it. Rides on it: medium.

**56. The measurements due at a tick are found first, then taken
(rule 7.9.3).**

> The measurements due at a
> tick are taken in the order of their places, and those of one place in
> the order they are declared.

Whether each is due is judged before any is considered (a port has one
value per tick, so nothing one port does changes whether another's is
due). A late one that is passed by still becomes "the sample time last
considered or passed by" of its port. Rides on it: none.

**57. The measurement that gives in to the gate (rule 7.9.5).**

> each
> state's variance grows by its `p0`, `s` is worked again, and the
> measurement is used.

The innovation is the one already worked (the state has not moved); the
gain uses the grown `P` and the new `s`; the grown `P` is what the update
form is applied to; `nis_<port>` and the consistency record keep the
value from before. It ends the run and counts as a measurement used for
`since_<port>` and for the clause on a gap of no known length. Rides on
it: medium.

**58. The update's arithmetic (rule 7.9.4).**

> `P = (1 - g·c)·P·(1 - g·c)ᵀ + g·v·gᵀ`

`(I - g·c)` is formed, then `((I - g·c)·P)·(I - g·c)ᵀ`, each product a
left-to-right sum, then `g[i]·v·g[j]` added entry by entry. `P` is not
made symmetric afterwards. `P = Ad·P·Adᵀ + N` is `((Ad·P)·Adᵀ) + N`.
`s = c·(P·cᵀ) + v`. Rides on it: low (last place).

**59. A sigma of a variance that rounding has put below zero
(rules 7.9.8, 3.6).**

> one per state, by the state's name, and `sigma_<state>`, the square
> root of its variance

Not finite, so `bad` by rule 3.6; the state's own output keeps its state.
The `sigma_max` clause is judged on the sigma given at the tick (carried
to the tick), and makes both the state and its sigma `uncertain`. Rides
on it: low.

**60. `since_<port>` is in seconds (rule 7.9.8).**

> `since_<port>`: the time from the sample time of the measurement last
> used to the tick, and not less than zero

The difference in nanoseconds, not below zero, divided by 10⁹. Rides on
it: high if another reader gives nanoseconds or ticks; the counters of
section 7 are "numbers, in seconds", which is why seconds.

**61. `q`, `p0` and `sigma_max` (Appendix A).**

> `q` and `p0` are maps from each state's name to a number

Every state must be in `q` and in `p0`; a name that is not a state is
refused in all three. Rides on it: low.

**62. What a rebase leaves an estimator (rules 7.9.9, 8.5).**

> each model input has the value it
> last had from the place the state stands at, and the next
> measurement due is the first (rule 3).

Forgotten: every port's "sample time last considered or passed by" and
"last used". Kept: the counts `refused_<port>` and `late_<port>`, each
port's run of refusals, what each port keeps for the consistency test,
and the flag of entry 55. The variance grows after the state is carried.
Rides on it: medium.

### Commands

**63. A block that acts by the call, at a catch-up tick, for rule 7.8.8
(rule 6.13).**

> The `y` of a block that acts by
> the call is held as a command is.

Its held `y` is treated in every way as a held command: value, state,
sample time, and its usability "then, before any fallback" for a loop's
doubt. At a gap `m` is 1 (one tick ran). Rides on it: low.

### Save, restore, reset

**64. "The same graph" (rule 8.2, and its Open item).**

> A state saved from one graph is
> refused by a graph that is not the same.

The same when the graph structure given to `Engine` serialises to the
same JSON text, key order included. A graph that differs only in the
order of keys is "not the same". Rides on it: low.

**65. What a save holds beyond what the text lists (rule 8.2).**

> **A saved state holds** what the blocks remember, their counters,
> each loop's doubt and the number of the next tick.

"What the blocks remember" is taken to include: a low-pass's and a
model's doubt and run counts, a model input's mark of entry 47, a window
with `only_new`'s last sample time, a PID's remembered measurement and
`f` (which the gap of the restore then forgets), an estimator's state,
covariance, places, counts, runs and flags. It also holds whether any
tick had run. It does not hold whether there has been a rebase since the
last reset: the restore's own rebase makes that so. Rides on it: low.

**66. A `rebase` before any tick has run, and the "last call"
(rule 8.5, 6.11).**

> does away with the writes waiting, and nothing else

The writes are not counted as thrown away. Nothing else changes, the
last accepted `now` among it (there is none: no tick has run, so no call
has been accepted). Rides on it: none.

## (a) Things in the text believed to be wrong or at odds

1. **Rule 7.7.14 against rule 7.7.15.** Rule 14 says of the first sum at
   the tick a PID stops waiting:

   > `kp·error` and the derivative, which is zero there but for a PID
   > that acts by the call.

   Rule 15 says a following PID's

   > derivative goes on as rule 7 says

   and that it waits to track from every tick it follows. So a PID that
   does not act by the call, released from following with both inputs
   usable throughout, stops waiting with a derivative that is not zero.
   The implementation uses the derivative as it is (the formula of rule
   14), not zero.

2. **The Memory paragraph of section 7 against the catalogue.** Section 7
   says a block with memory with no end

   > gives **counters** that a graph can
   > test

   and section 7.4 says a deadband holds its sample for a time "which has
   no end" and a rate limit "holds the last value it gave, which has no
   end"; Appendix A gives neither `elapsed`, `doubtful` nor `gaps`. The
   implementation follows the catalogue.

3. **Section 7.11 against rule 7.9.7.** Section 7.11 says

   > **A gap makes only a model with `settle`, an estimator on the gap's own
   > tick, and a total it takes past `max_missed`, `uncertain`.**

   but rule 7.9.7 keeps an estimator `uncertain` after a gap of no known
   length until a measurement is used, which can be many ticks; and a
   loop's doubt (rule 8.6's table) makes every model block of the loop
   `uncertain`, not only "a model with `settle`" by its own doubt. Also a
   `held_for` with `hold` and a `since_true` with `assume_false` are
   `uncertain` at the gap's tick if their input is unusable there, though
   that is the tick's doing. The implementation follows the rules.

4. **Rule 6.10 against rule 6.8 on the count of writes thrown away.**
   Rule 6.10 reports

   > how many
   > writes have been thrown away (rule 8) since the last call that ran a
   > tick

   so the count is zeroed by every call that runs a tick, and rule 6.8's
   "a reset sets it to zero, and a restore or a rebase does not" then
   only says something about writes thrown away between the last tick and
   the restore or rebase. Not a contradiction, but the two sentences
   describe one number two ways and a reader could keep two counters.
   The implementation keeps one.

5. **Rule 8.5 against rule 7.2.1 on "the time of the rebase's call".**
   Rule 8.5 tells a host to write again every input with no maximum age

   > **with the time of the rebase's call**

   but a host makes the `rebase` call before it knows the `now` of the
   `tick` call to come unless it reads the clock once for both; section 6
   says "with the time of the call to come (rule 8.5)". The two are the
   same only if "the rebase's call" means the tick call that follows.
   Read so.

Nothing was found where a rule's own worked figure fails: the figures
that could be run agree (list in `selftest.py`).

## (b) What could not be implemented, and why

1. **Units (section 10).** The text says itself that the graph file has
   no key for a port's unit or for the strict policy, and the registry of
   units is "a fixed built-in list" that is not given. An input's `unit`
   is accepted as text and never checked.
2. **Reasons (rule 3.8).** Not carried. The rule allows that: "What an
   engine hands its host, and what a save holds, need not carry it".
3. **The vectors of section 11, `conformance/`, `semantics_spec.md`,
   `semantics_v2_history.md`, the derived-signals RFC.** Not read, as
   instructed; none was needed to build anything, but the "behaviour is
   what the vectors pin down" (Appendix A) and no vector was seen.
4. **The worked figures of section 7.9** (3,500 of 3,600 refused, "never
   more than 1.6 out", "between a thirtieth and a fiftieth") depend on
   noise the text does not give ("The counts move with the noise drawn"),
   and on an ambient temperature, a starting temperature and a phase of
   the square wave it does not state. `selftest.py` checks their shape
   with one seed and loose bounds only. The `consistency` figures were
   not checked.
5. **Exactness past ordinary models (entry 43).** The promise of a part
   in 10¹⁶ "everywhere up to the bound" is met by 120-digit arithmetic
   for the models tried (a rotation at the bound among them, checked
   against `cos` and `sin`), not proved for every `A` within the bound.

Everything else is implemented: all 22 block types of Appendix A, every
host operation, the formula language, gaps of both kinds, commands and
acting by the call, loops with a model, and the estimator.

## (c) Terms used before, or without, definition

- **rebase**, **gap**, **stall**: used from rules 6.5, 6.6 and 6.9;
  defined in section 8.
- **fallback**: used in rule 3.7; defined in section 7.10.
- **published** output, **command**: rule 6.13 uses "published outputs";
  publishing is rule 9.2's `out`.
- **`ride_through`**, **`settle`**, **`doubtful`**, **`gaps`**: used in
  section 6's "What this still leaves out" and section 7's opening;
  defined with each block.
- **host**: never defined (whatever calls the engine).
- **"the first tick"**: never defined; taken as tick 0 (entry 36).
- **"done with"** (of a write): used as a term in rule 6.8; means
  removed from those waiting, without being counted as thrown away.
- **"holds"** a sample, of a window's tick: used in rule 7.3.3 before
  rule 7.3.8 says what makes a tick hold none under `only_new`.
- **"a run"** of unusable ticks (rule 7.4.12), **"stretch"** (rule
  7.6.1): used as terms, clear from context.
- **"takes"** a value "from an input", of a rate limit (rule 7.4.13): the
  text relies on it for `ride_through` and `track`; taken as "the value
  it holds was set at a tick with a usable input, or by following a
  usable `track`".
- **"model block"** against **"model"**: rule 4.9 says a model is not a
  block, section 7.8 uses "model block" for the block that hosts one, and
  rule 7.8.8 relies on an estimator not being one.
- **"sensitivity"** (rule 4.9): defined and never used again.
- **"the strict policy"**, **"the registry"** (section 10): 1.x terms,
  not defined here.
- **"C's `pow`"**: relies on the C standard.
- **The type of each setting**: rule 4.3 says each setting has "a type,
  whether it is required, and its range", and Appendix A gives ranges and
  defaults but not always the type (a hysteresis's `initial` is taken as
  a boolean, a delay's as either, a rate limit's as a number, a model's
  as a number or a list of numbers by its entry).
- **`D (0)`** for `state_space` against **`D (zeros)`** for `linear`:
  taken as one number and a matrix.

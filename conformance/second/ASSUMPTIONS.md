# Assumptions made implementing `semantics_spec_v2.md` from its text

Each entry: where, the question, the readings, the one chosen and why.
"Spec" is `semantics_spec_v2.md`; "interface" is `interface.md`.
Entries marked **[diverge]** are the ones I think most likely to make two
independent implementations give different outputs or different refusals.

## A. Values, states, usability (sections 3, 7 preamble)

**A1. 7 preamble / 3.2 — can a block output be `good` and not finite?**
"An input is usable at a tick when its state is `good` and its value is
finite" implies a `good` non-finite value can exist, but 7.1.4 makes
non-finite results `bad` only for stateless blocks. A window mean, a total
or a Kalman state can overflow. Readings: (a) leave it `good` with `inf`,
and let each reader find it unusable; (b) make every non-finite block output
`bad`. Chose (b), in one place for all block types, so "usable" and "good"
coincide inside the graph. This contradicts "both always `good`" (7.4) and
"always `good`" (7.3.2, 7.3.3, `all_good`) only for a total that overflows.

**A2. 9.2 — is a constant input usable, and what state has it?** Not
stated. Chose: `good`, with the number as its value, at every tick including
the first. A non-finite constant (`inf`, `nan`) is a compile error (treated
as "out of range", 9.3) rather than a permanently unusable input.

**A3. 3.4 — what counts as true?** "A boolean is 1 or 0" says what blocks
produce, not what they accept. Readings: true is exactly 1; true is any
non-zero; true is > 0 or >= 0.5. Chose non-zero, everywhere a truth value is
read (`and`, `or`, `not`, `when`, `held_for`, `since_true`, `latch`). 
**[diverge]** for inputs such as 0.5 or -1.

**A4. 3.1 — value reported with a state that is not good.** Interface says
`None`. Internally nothing is carried either (a delay of a `bad` sample
replays `bad` with no number).

## B. External inputs (6.4, 6.5, 7.7)

**B1. 7.7 — host wrote `not_ready`, long ago. `not_ready` or `bad`?
[diverge]** Both bullets apply: "`not_ready` ... if the host wrote it as
`not_ready`" and "`bad` ... if it was sampled longer ago than its maximum
age". Readings: (a) the bullets are tried in the order listed, so the
written state wins and age is only checked for a `good` write; (b) worst
state wins, so it turns `bad` once stale. Chose (a): the third bullet's
"otherwise `good`" reads as a cascade, and a `not_ready` write has no
sample to be old. Same for a `bad` write (it is `bad` either way).

**B2. 6.4 — "longer ago than" at the boundary.** Age exactly equal to
`max_age` is still good (strictly "longer"). The age at tick `k` is
`age given to write() + (k - tick it was written for) × period`; the
comparison allows a relative slack of 1e-9 so that `0.1 + 0.1 + 0.1` does
not exceed `0.3`. The size of the slack is my own.

**B3. 6.4 — negative age (sampled after the tick's time).** Not excluded
by the interface. Accepted; it is simply not old. NaN age raises
`ValueError`.

**B4. 7.7 — `write("good", value=None)` or a non-number.** Not stated.
Raises `ValueError`. A `good` write of `inf`/`nan` is accepted and reads
`bad` (7.7 says so). A value passed with a state that is not good is
discarded.

**B5. `write` to a name that is not a declared input.** Not stated. Raises
`KeyError`. An unknown state string raises `ValueError`. Neither is a
`CompileError`, since the graph already compiled.

**B6. 6.4 — two writes to one input between ticks.** "the latest value
written": the later call wins, even if its sample time (age) is older.

**B7. `max_age` range.** Zero is accepted (only a value sampled exactly at
the tick's time is good); negative is a compile error. Absent means no
limit (interface). `max_age` need not be a whole number of periods.

**B8. 9 — shape of `inputs`.** The spec shows a list of
`{signal, unit, max_age}`; the interface a dict `name -> {max_age}`. I
accept both. Keys accepted in a declaration: `max_age`, `unit`, `signal`;
any other is an unknown key (9.3). `unit` is accepted and ignored, though
9.1 says `inputs` lists each signal "with its unit" — I do not require it
(units are out of scope). A declaration of `None` is treated as `{}`.

**B9. `tick()` result.** Only block outputs published through `out`
appear; external inputs are not echoed.

## C. Graph file and compile-time refusals (4, 5, 6, 9)

**C1. 9.3 — order of checks and which error is reported.** Not stated; a
graph with two faults gets whichever my compiler meets first: top-level
keys, period, inputs, then each block in listed order (id, duplicate id,
unknown key, type, settings unknown/missing/type/range, inputs, outputs,
fallback), then duplicate signals, then unresolved reads, then loops. Only
one fault is reported. Message wording is my own throughout.

**C2. `period`.** Required; a missing or non-positive period is a compile
error. Not stated in the spec.

**C3. Lengths of time.** Accepted: a number (seconds), or a string of
digits with optional decimal part and exponent, optional spaces, and one of
`ms`, `s`, `m`, `h` (`"2.5s"`, `"1 s"`). A bare numeric string (`"5"`), a
negative string and other units (`min`, `us`, `d`) are refused. Parsed
exactly as decimal fractions, a float through its shortest decimal form
(`0.1` is one tenth). All time comparisons between ticks and settings are
then exact rational arithmetic, which is how I met the "rounding in the
last bits" instruction.

**C4. 6.2 — which settings must be a whole number of periods.** The spec
says only a window. So `time` (`held_for`, `since_true`), `ride_through`,
`max_age`, `per` and `tau` may be any length. A window of zero is refused.

**C5. 9.3 — "a setting of the wrong type".** Types are not given in
Appendix A. Chose: `ticks` an integer (a float `2.0` and a bool are
refused); `initial`, `step`, `min_good`, `q`, `r` numbers (bool refused);
`window`, `ride_through`, `time`, `per`, `tau` lengths of time; `expr`
and `on_bad` text. An optional setting given as `None` is refused as the
wrong type rather than read as "left out".

**C6. 9.3 — "out of range". [diverge]** No range is given for any setting
(4.3 says a type declares one). Mine: `ticks >= 1`; `window > 0`;
`0 < min_good <= 1`; `step >= 0`; `ride_through >= 0`; `time >= 0`;
`per > 0`; `tau > 0`; `q >= 0`; `r > 0`; `on_bad` one of `reset`, `hold`;
fallback and `initial` finite. Doubtful ones: `ticks = 0` (would be a
same-tick read, against the declaration); `min_good = 0` (would make a
window with no samples `good` with no statistics to give); `r = 0` (can
divide 0 by 0 when `q = 0`); `step = 0` allowed (every usable input taken).

**C7. 6.3 — "A model with a stability limit is checked against the
period".** Does `kalman1` have one? Its `a = 1 - period / tau` is a
forward-Euler step, unstable when `|a| >= 1`. Readings: no check; refuse
`period > tau` (`a < 0`, oscillating); refuse `period >= 2·tau` (unstable).
Chose the last, the smallest refusal that 6.3 seems to ask for.

**C8. 4.3 — which inputs are required.** Appendix A has no column for it.
Chose: `x`, `set` and `z` required; `kalman1.model` optional, and when not
connected it is treated as unusable on every tick (7.5.3). `formula` and
`all_good` need none. An unconnected required input, and a port the type
does not have, are compile errors.

**C9. Appendix A `formula` — "any, named in the formula".** A name in the
formula with no entry in `in` is a compile error. An entry in `in` that the
formula never names: readings are (a) allowed and ignored, (b) allowed and
its state counts toward 7.1.1 "worst state among its inputs", (c) refused
as an unknown port. Chose (c), which avoids choosing between (a) and (b).

**C10. `all_good` with no inputs.** Compiles; gives 1 (every input of none
is usable).

**C11. 9.1/9.2 and interface — resolving a name in `in`.** A number is a
constant; a string is always a signal name, even `"3"`. A bool is refused.
A name is looked up among external inputs, published names, and
`<block id>.<port>` for every output port of every block. The interface
offers `<id>.<port>` "for an output that was not published"; I also allow
it for one that was. A block id or a signal name may contain dots; lookup
is by whole string.

**C12. 4.5/9.3 — "a duplicate signal".** Refused: two blocks publishing
one name; one block publishing two ports under one name; a block publishing
the name of an external input; a published name that equals another
port's `<id>.<port>` spelling; the list form of `inputs` naming a signal
twice; two blocks with one id. Not refused: a signal nobody reads, a block
with no `out`.

**C13. 9.2 — unknown port in `out` or `fallback`.** Compile error (not
listed in 9.3, taken as an unknown key). A published name must be a
non-empty string.

**C14. 5.3 — what the loop error names.** I report every group of blocks
that are mutually reachable through same-tick reads (strongly connected
components), ids sorted, groups separated by `;`. Blocks that merely read
from a loop are not named. A block reading its own output in the same tick
is a loop of one. A reading that names "one cycle" could list fewer blocks
when two loops share a block.

**C15. 5.3 — which inputs read the previous tick.** Only `delay.x`. "or a
block type that says so": no other type in Appendix A says so, so a loop
through `total`, `deadband`, `latch` or `kalman1` is refused even though
each has state.

**C16. 5.2 — "ties are broken by block id".** Among blocks whose
same-tick dependencies are all evaluated, the smallest id (plain string
comparison, so `"10" < "9"`) goes next. Order cannot change outputs here;
it is exposed as `Engine.order`.

**C17. Unknown block type, missing `id` or `type`, non-string id.**
Compile errors; not listed in 9.3.

## D. Formula (7.1, Appendix A)

**D1. Grammar. [diverge]** The spec lists operators without spelling,
precedence or associativity ("Formulas" is Open in section 4). Chose:
comparisons spelled `< <= > >= == !=` (`=` and `<>` refused); precedence
loosest to tightest `or`, `and`, `not`, comparison, `+ -`, `* /`, unary
minus; binary operators left-associative; `a < b < c` parses as
`(a < b) < c`, not as a chain; no unary plus; no `true`/`false`; numbers
are decimal with optional exponent; names are `[A-Za-z_][A-Za-z0-9_]*`;
`and or not abs min max when` cannot be input names.

**D2. Arity.** `abs` one, `min`/`max` exactly two, `when` exactly three;
anything else is a compile error.

**D3. 7.1.1 against 7.1.2/7.1.3 — where states combine.** 7.1.1 says the
output takes "the worst state among its inputs"; rules 2 and 3 say some
inputs do not count. Chose: states are worked out for each sub-expression
in turn, so `(a or b) + c` with `a` true, `b` bad, `c` good is good. The
other reading (worst over all inputs unless the whole formula is one
`or`/`and`/`when`) gives `bad`.

**D4. 7.1.4 inside an expression.** A sub-expression that divides by zero
or overflows is `bad` as an operand, so `when(c, a, 1/0)` with `c` true is
`good`, and `(1/0) or 1` is `good` 1. Zero divided by zero is `bad`.

**D5. 7.1.2 — `not`.** Not mentioned by rule 2; takes its operand's state.
With more than two operands, `a or b or c` is decided by any true one
regardless of position (follows from applying the binary rule in turn).

**D6. Equality.** `==` and `!=` compare doubles exactly, no tolerance.

**D7. `min`/`max`/`abs` states.** Worst state of the arguments (7.1.1); a
`bad` argument that would not have been the minimum still makes it `bad`.

## E. Delay (4.2, Appendix A)

**E1. What a delay replays.** Its input as the engine saw it at the
earlier tick, after that source's fallback, state included; for an external
input, the state it had then (so staleness judged at tick `k - ticks`, not
re-judged now).

**E2. A delay's fallback** applies to its output like any block's, so a
replayed `bad` sample can be substituted.

## F. Window (7.2 rules 1 to 4, Appendix A)

**F1. 7.2.3 against 7.2.4 — slope when the window has too few usable
samples. [diverge]** At the first tick of a 4-tick window, rule 3 gives
`not_ready` for "its outputs", rule 4 gives `bad` for a slope with fewer
than two samples. Readings: (a) rule 3 first, for all six outputs, and
rule 4 only when the window otherwise qualifies as good; (b) rule 4
always wins for slope; (c) worst of the two. Chose (a). Under (a) rule 4
only shows when `min_good × n < 2`.

**F2. 7.2.2 — "the fraction of its ticks that must hold a usable
sample".** The window is not good when `usable < min_good × n`, compared
exactly (no rounding of `min_good × n` to a whole number of ticks; with
`n = 4`, `min_good = 0.6` needs 3). `n` is always the full window length,
including ticks from before the graph started.

**F3. 7.2.3 — "worst state among its ticks that were not usable".** Bad
over not_ready, over the unusable ticks still inside the window plus one
`not_ready` if the window reaches back before tick 0.

**F4. Appendix A — slope.** Ordinary least squares over the usable samples
only, against `tick index × period`, so a gap leaves the remaining points
at their true times. Two usable samples are always at different times here.

**F5. Arithmetic details.** Mean by exact-rounded summation (`fsum`), then
divide; median of an even count is `(a + b) / 2`; `min`, `max`, `spread`
direct. An implementation summing left to right may differ in the last bit.

**F6. First tick.** The window at tick 0 holds tick 0 and `n - 1` ticks
that count as `not_ready`; with `n = 1` it is good immediately.

## G. Deadband (7.2 rules 5 and 6)

**G1. 7.2.5 — "moved by its step or more": moved from what, and to
what?** From the held output (not from the previous input), and the output
then becomes the input itself (not a multiple of the step). `|x - held| >=
step`, compared in doubles with no tolerance, so `0.3 - 0.1 >= 0.2` is
false. **[diverge]** on the tolerance.

**G2. 7.2.6 — "no longer ago than `ride_through`".** Time since the last
tick whose input was usable (whether or not it moved the output),
`<= ride_through`, exact. With `ride_through` equal to one period the first
unusable tick is ridden through.

**G3. 7.2.6 — after the ride-through runs out.** The held value is kept;
when the input is usable again it is compared with that held value by rule
5, not "taken as it is". "Its first usable input" means the first ever (or
since reset).

**G4. Before any usable input**, the output takes the input's state.

## H. Timers (7.3, Appendix A)

**H1. `held_for` — input usable and false.** Not stated outright: the
timer stops and the output is `good` 0.

**H2. `held_for` — "more than `time` after".** Strict: with `time` 2 s and
period 1 s, true from the fourth true tick (3 s after the start). With
`time` 0, false on the tick the input becomes true and true on the next.

**H3. `held_for`, `hold`, timer running, input unusable.** Output `good`,
0 or 1 by the clock. When the input comes back true the timer carries on
from its original start; when it comes back false the timer stops.

**H4. `held_for`, `reset`.** After an unusable tick the timer restarts
from the tick the input is next true.

**H5. `since_true` wording.** "True when its input has not been true for
longer than a stated time" read as: (tick time − clock) > `time`, strict.
So it is false on the first tick, and it goes true when the input has
never been true once `time` has passed since tick 0. An input that is
`good` and false, or unusable, leaves the clock alone.

**H6. `latch`.** True on the same tick its input is first true (not one
tick later). Nothing in the catalogue clears it except reset/restore.

## I. Total (7.4, Appendix A)

**I1. Which tick's addition the output includes.** The output at a tick
includes that tick's addition (first tick with `x = 2`, period 30 s, `per`
1 m gives 1, not 0). Starts from 0.

**I2. Order of arithmetic.** `x × period / per` evaluated left to right in
doubles; `missed` is `count × period` computed exactly then converted.

**I3. `per` as a length of time.** "`per` (1 s)" read as a duration
setting, default one second.

## J. Kalman (7.5, Appendix A)

**J1. `tau`** is a length of time (`"4s"` or a number); `q` and `r` plain
numbers.

**J2. First usable `z` tick.** Outputs `x = z`, `sigma = sqrt(r)` and are
`good` on that same tick. Before it, both outputs `not_ready` whatever the
input states (never `bad`, by 7.5.1), and no prediction is run.

**J3. 7.5.3 — "as if nothing were known about it".** Taken to mean exactly
the appendix formula (`var + q·period`, `x` unchanged), nothing larger.

## K. Fallback (7.6)

**K1. Who sees the substituted value.** Readings: only the published
signal; or every reader. Chose every reader: other blocks inside the graph
(including a delay capturing it) see the fallback, `good`. **[diverge]**

**K2. "for one output".** The map may name several outputs of one block,
each independently. A fallback may be given for an unpublished port.

**K3. Outputs that are always `good`** may carry a fallback; it never
fires (except through A1).

## L. Save, restore, reset (section 8)

**L1. 8.3 — "the same graph" (Open in the spec).** Chose: same period,
inputs with their maximum ages, and blocks with id, type, settings (after
defaults and unit conversion), `in`, `out` and `fallback`; order of blocks
in the file and spelling of durations (`"60s"` or `"1m"`) do not matter.

**L2. How refusal is signalled.** A `RestoreError` (a `ValueError`); the
engine is left unchanged.

**L3. What a snapshot holds.** Tick count, every block's state, and the
latest write to each input with its age, so a value written and not yet
ticked survives. The snapshot is a deep copy, and may be restored more
than once.

**L4. `reset()`** also forgets everything written to inputs (they read
`not_ready` again) and returns the tick time to 0.

**L5. 8.1 — reset or restore of one block** is not exposed; the interface
has only whole-graph calls.

## M. Things I was unsure the document settles

**M1. 7.2.1 against the Appendix on what a window spans.** "the last
stretch of time, its `window` setting" could include `n + 1` ticks (both
ends of a closed interval); the appendix settles it: "that tick and the
`n - 1` before it". I followed the appendix.

**M2. 7.3.1 "has been true for longer than" against the appendix "the
timer starts on the tick its input becomes true".** Consistent as far as I
can tell; noted because the first true tick counts as time zero, not as one
period of being true.

**M3. 4.2 "a stated initial value until then" against the appendix
"`not_ready` if no initial value is given".** The appendix makes the
initial value optional; followed the appendix.

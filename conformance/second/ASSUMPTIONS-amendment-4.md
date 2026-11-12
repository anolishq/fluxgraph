<!-- markdownlint-disable MD029 -- entries keep one numbering -->
# Assumptions made in bringing `impl.py` up to Amendment 4

Every place where the text amended by "Models" (rule 4.9, rules 7.8.6 to
7.8.8, rule 7.9.2 and the model entries of Appendix A) did not say what to
do, could be read two ways, or disagreed with another passage, and what
`impl.py` does. The ones most likely to make two honest implementations
disagree come first. Rule numbers are those of `proposal.md`. Quotations
are from `proposal.md`.

Part A is the guesses. Part B is what I believe the text gets wrong, each
with a small example run on `impl.py`.

## How the step is worked out

Rule 7.8.7 gives the result and not the method. `impl.py` forms the matrix
`[[A, B], [0, 0]]` times the period, whose exponential is
`[[Ad, Bd], [0, 1]]`, so `Bd` needs no inverse of `A` and a model with an
`A` that has none (a free mass) is no special case. The exponential is
worked out in decimal arithmetic at 100 digits (`decimal`, from the
standard library): the matrix is halved until the largest sum of a row's
absolute values is at most 0.5, the series is summed until a term is under
10⁻¹⁰⁵, and the result is squared once for each halving. The period is
the whole number of nanoseconds over 10⁹, exactly; the settings enter as
the doubles they are. `Ad` and `Bd` are then rounded to doubles, once, at
compile; a step at run time is `Ad·x + Bd·u` in doubles.

## Part A. Where the text had to be guessed

1. **Which eigenvalue gives `settle`, and when a state "does not decay".**
   Rule 7.8.6: "That constant is one over the least rate at which its
   state decays: minus one over the largest real part among the
   eigenvalues of its `A`", and "A named model with a state that does not
   decay ... has no such constant".
   *Chosen:* the largest real part, taken from `A` as the settings give
   it. A model has no constant where that real part is zero or more, and
   then no `settle` unless one is given. So a `mass_spring_damper` with
   `stiffness: 0` (an eigenvalue of zero: its position stays), a
   `thermal_rc2` with both `heat_transfer`s zero, and a `dc_motor` with no
   `resistance` and no `friction` have none. `settle` is three of the
   constant over the period, rounded up by rule 6.3. The other reading
   takes the slowest of the eigenvalues that do decay, and gives the free
   mass a `settle` from its damping.

2. **Whether a `linear` block may have no inputs, or no outputs.**
   Appendix A: "`B` a list of `n` rows, one number per input; `C` a list
   of rows, one per output, of `n` numbers".
   *Chosen:* both are accepted: `B: [[], []]` is two states and no input,
   `C: []` no output (the block then gives only `elapsed`, `doubtful` and
   `gaps`). `A` has at least one row. `A`, `B` and `C` are required;
   `D` and `initial` are zeros if left out. The other reading refuses a
   model with nothing to read or nothing to give.

3. **A step whose matrix is too large for a double.** Rule 7.8.7: "no
   step is too long for it". For a model that grows, `exp(A·period)` can
   pass the largest double.
   *Chosen:* the graph is accepted, `Ad` holds an infinity, and the state
   and outputs are then not finite and `bad` by rule 3.6. The other
   reading refuses the graph. See B2.

4. **The estimator's model.** Appendix A: "`model` is a map with `type`,
   a model's type, and that model's own settings". Rule 7.9.2: "`F` is the
   model's `Ad`".
   *Chosen:* any of the eight model types, `linear` among them, with the
   settings of that type and neither `ride_through` nor `settle`. The
   estimator's outputs are the model's states by name, not its outputs:
   a `dc_motor` in an estimator gives `current` and `speed` and no
   `torque`, and a `linear` model's `C` and `D` are checked and then not
   used. `substeps` is no longer a setting of the estimator and is refused
   as unknown.

5. **Which blocks count against "one model block and no more".** Rule
   7.8.8: "it holds one model block and no more. Two model blocks that
   read each other are a tick apart".
   *Chosen:* any two model blocks on one loop, also where a formula or a
   delay stands between them and neither reads the other directly. A
   model block that feeds another with no way back is not a loop. An
   estimator with a model block on a loop was refused already.

6. **Names of a `linear` block.** Appendix A: "The names in each list are
   distinct, and an output is not named as a model output is."
   *Chosen:* the three lists are separate: an output may bear the name of
   an input or of a state, an input may be called `elapsed`. A name is
   text; nothing else is asked of it. A list of names has to be as long as
   the matrix it names.

7. **`tau` of a `first_order_process`.** "`tau` is written as a length of
   time, and is more than zero." *Chosen:* as a low-pass's `tau`: a number
   and a unit, any length at all (rule 6.3), and a bare number is
   refused.

8. **What has no range said.** *Chosen:* `gain`, `back_emf`,
   `torque_constant` and every `initial` are any finite number, zero and
   below among them. `thermal_mass`'s `initial`, `thermal_rc2`'s
   `initial_a` and `initial_b`, and a `dc_motor`'s `back_emf` and
   `torque_constant`, which have no value in brackets, are required.

9. **`settle` of a `state_space` or `linear` block on a loop.** They have
   none of their own (rule 7.8.6), and rule 7.8.8 asks for one "written in
   the graph" on a loop. *Chosen:* off a loop they are `good` after a
   doubt; on one they are refused without `settle`, like any other.

## Part B. What I believe the text gets wrong

1. **The example after rule 7.8.8 cannot be checked, and does not say
   what it is.** "Joined by a conductance of three times their loss and
   run at half their time constant, the two blocks reach 10¹⁹ and say
   `good`; the one block gives the true answer at any period." The two
   blocks are refused by the rule the example follows, so no
   implementation of this text can run them. The one block can be run:
   `thermal_rc2`, masses 10, losses 1, `coupling` 3, from 50 and 30,
   ambient 20, period `5s` → at tick 79 both are `good` 20.0, and ticks 1
   to 4 match the closed form `20 + 20·exp(-0.1 t) ± 10·exp(-0.7 t)`.
   For the two blocks the text gives neither the wiring nor how long they
   run. By hand, and not on `impl.py`:
   - two `thermal_mass` blocks, each given `power` as `3·(other - own)`
     by a formula: the difference of the two is multiplied by -1.754 a
     tick, and is 1.1·10²⁰ at tick 78. This must be the case meant;
   - two blocks that each hold the conductance in their own equation
     (`d T/dt = (-T - 3·(T - other)) / 10`, the other held): the factors
     are 0.784 and -0.513, and the pair settles. Split this way the
     network is sound.

   So "can be unstable so split" is true of one way of splitting and not
   of the other, and the figure belongs to a number of ticks the text
   leaves out.

2. **"No step is too long for it" is not so for a model that grows.** A
   `linear` block with `A: [[5]]`, `B: [[1]]`, `C: [[1]]`, input 0 and
   state 0, period `200s`: `exp(1000)` is not a double. Run: tick 0 is
   `good` 0, and ticks 1 and 2 are `bad`: the state is infinity times
   zero. At a period of `100s` the same block is `good` 0 on every tick.
   The true answer is 0 at any period. The text should say what a graph
   whose `Ad` or `Bd` is not finite is: refused, I would think (entry 3 of
   part A).

3. **A `linear` block and the named model it spells out differ in
   state.** The amendments list says the six models "are each a named
   case of it", and rule 7.8.6 gives a named model a `settle` from its
   `A` and `linear` none. Run: a `thermal_mass` (10, 1, from 20, ambient
   20) and a `linear` block with `A: [[-0.1]]`, `B: [[0.1, 0.1]]`,
   `C: [[1]]`, the power 5 and `uncertain` at tick 1 only → the values
   are the same to the last digit (20, 20.4758..., 20.9063..., 21.2959...)
   and the states are `good`, `good`, `uncertain`, `uncertain` for the
   named one and `good` throughout for `linear`. The engine has the `A`
   of both and could give `linear` the same constant; as written, moving
   a model from its name to its matrices takes its doubt away without a
   word. If that is meant, the sentence in the amendments list should not
   say "a named case of it" without saying so.

4. **Rule 7.8.6 says "its slowest time constant" of a model that
   swings.** For an underdamped model the largest real part is that of a
   complex pair, and the "time constant" is that of the envelope. Run: a
   `second_order_process` with `omega_n: 2`, `zeta: 0.25` at a period of
   1 s is `uncertain` for 6 ticks after a missed step (three times 2 s),
   whatever its period of swing. This is what the formula gives and I
   think it is meant; the words "the least rate at which its state
   decays" fit it, and "time constant" does only loosely.

## Round two

The text was revised on the four findings and on entries 1 to 3 of part A.
Quotations are from the revised `proposal.md`; each example was run on
`impl.py`.

### Part A against the revised text

| Entry | Settled? | Code changed? |
| --- | --- | --- |
| 1. Which eigenvalue gives `settle`; "does not decay" | Yes, as chosen: "the largest real part among all the eigenvalues of its `A`", and no constant "where that largest real part is zero or more" | No |
| 2. A `linear` block with no input or no output | Yes, the other way: "There is at least one state, one input and one output." | Yes: both are refused |
| 3. A step too large for a double | Yes, the other way: "A model that grows so fast that `Ad` or `Bd` is not finite at the graph's period is refused." | Yes: refused at compile, for a model block and for an estimator's model |
| 4. The estimator's model | Open: unchanged | No |
| 5. Which blocks count against "one model block" | Open: unchanged | No |
| 6. Names of a `linear` block | Yes, as chosen: "the three lists do not have to differ from each other" | No |
| 7. `tau` of a `first_order_process` | Open: unchanged | No |
| 8. What has no range said | Open: unchanged | No |
| 9. `linear` or `state_space` on a loop | Open: unchanged | No |

### Part B against the revised text

| Finding | Now | Code changed? |
| --- | --- | --- |
| 1. The example after rule 7.8.8 | Settled: the wiring ("formulas that give each a power of 3 W for each degree the other is above it"), the period and the length ("within eighty ticks") are given, and agree with my arithmetic: a factor of -1.754 a tick, past 10¹⁹ at tick 78 | No |
| 2. "No step is too long" for a model that grows | Settled: "no step is too long for a model that does not grow", and the refusal above | Yes, as entry 3 |
| 3. A `linear` block and the named model it spells out | Kept, and said: "in that alone a named model differs from the `linear` that spells it out" | No |
| 4. "Time constant" of a model that swings | Settled: "For a model that swings as it decays that is the constant of the envelope." | No |

### What the new wording leaves to choose

R1. **"Not finite" where?** Rule 7.8.7: "A model that grows so fast that
    `Ad` or `Bd` is not finite at the graph's period is refused." The true
    `Ad` is always finite; what is not is its nearest double.
    *Chosen:* `Ad` and `Bd` are worked out exactly and rounded to doubles,
    and the graph is refused if any of them is then an infinity. So the
    line is the largest double, about 1.8·10³⁰⁸: with `A: [[5]]` and
    `B: [[1]]` a period of `141s` is accepted (`Ad` is 1.5·10³⁰⁶) and
    `200s` is refused; at `141s` with `B: [[1e10]]` it is refused for `Bd`
    alone. An implementation that works the exponential out in doubles
    can overflow on the way to a result that would have fitted, and refuse
    a little earlier; the two then differ only on graphs within a few
    powers of two of the line.

### What I believe the new wording still leaves unsaid

W1. **A model that is accepted can still pass the largest double two
    ticks on.** The refusal looks at one step. Run: `linear`, `A: [[5]]`,
    `B: [[1]]`, `C: [[1]]`, `u` a constant 1, period `100s` → tick 0 is
    `good` 0, tick 1 is `good` 2.8·10²¹⁶, and ticks 2 and 3 are `bad`
    (rule 3.6). That is the right answer for a state that has left the
    doubles, and I do not think the graph should be refused for it; I
    note it because "is refused" may be read as a promise that an accepted
    model stays finite, and it is not one.

## Round three

The text was revised after an independent numerical review. Quotations
are from the revised `proposal.md`; each example was run on `impl.py`.

### What the text now settles

| Point | Settled? | Code changed? |
| --- | --- | --- |
| R1 of round two, "not finite" where | Yes: "an entry of `Ad` or `Bd` at the graph's period is more than a double holds" | Yes, slightly: the exact entry is compared with the largest double before it is rounded, in place of testing the rounded double for an infinity |
| W1 of round two, an accepted model that grows | Yes: "One that is accepted and grows can still pass that some ticks on, and its outputs are then `bad` (rule 3.6)." | No |
| How the largest real part is worked for two states | Yes: `h` where `h²` is no more than `d`, otherwise `d / (h - √(h² - d))` with `h` less than zero | Yes: the test is now `h·h <= d` as the text has it (it was `h·h - d < 0`, which gave `d / h` and not `h` for two eigenvalues the same) |
| `thermal_rc2`, `coupling` | Yes: "`coupling` and the two `heat_transfer`s not negative" | Yes: zero is accepted |
| Rule 11.5, values near zero | Yes: "of the value, or of 1 where the value is smaller than 1". `selftest.py` already compared that way | No |
| The bound on how fast a model may be | New; see below | Yes |

### The bound, exactly as `impl.py` has it

Rule 7.8.7: "The bound is on the largest sum of the absolute values along
a row of `A`, times the period, which may be 100,000 at most."

- The number is worked out **exactly, in rational arithmetic**: each entry
  of `A` is the double the graph gave (for a named model, the double its
  settings were worked into, such as `-heat_transfer / thermal_mass`),
  taken as the exact fraction it is; the absolute values along each row
  are added as fractions; the largest row's sum is multiplied by the
  period as the fraction `period in nanoseconds / 10⁹`. Nothing is
  rounded.
- The graph is refused where that number is **more than 100,000**. At
  100,000 exactly it is accepted.
- It is tried before `Ad` and `Bd` are worked out, for every model in
  continuous time: `linear`, the six named models, and the model of an
  estimator. `B`, `C` and `D` do not count. A `state_space` block is in
  discrete time and has no such bound.

Run: `A: [[-5]]` at a period of `20000s` is accepted (100,000 exactly) and
at `20000000000001ns` is refused. A row of `-3` and `2` counts as 5:
accepted at `20000s`, refused at `20001s`.

### What the new wording leaves to choose

T1. **The arithmetic of the bound.** The text gives the quantity and not
    how it is rounded, and "two implementations must refuse the same
    graphs". Worked in doubles, the sum of a row, the period in seconds
    and their product are each rounded, and the answer near the line
    depends on the order.
    - Reading A (chosen): exactly, as above.
    - Reading B: in doubles, `max(sum(abs(row))) * period_seconds > 1e5`.

    Run: a `linear` block with `A: [[-33333.333333333336]]` (the double
    nearest 100,000 / 3) at a period of `3s`. Exactly, the product is
    100,000 and 7.3·10⁻¹² more: refused. In doubles,
    `33333.333333333336 * 3.0` is `100000.0`: accepted. A second case:
    a row of `1e5` and `1e-12` at `1s` sums to `100000.0` in doubles
    (accepted) and to 10⁻¹² more exactly (refused). The text should say
    which, and if doubles, in what order and with the period as which
    double.

T2. **How `d` is worked out, for `settle`.** Rule 7.8.6: "with `h` half
    the sum of `A`'s diagonal and `d` its determinant". *Chosen:* in
    doubles, `h = (a00 + a11) / 2`, `d = a00·a11 - a01·a10`, the test
    `h·h <= d`, and `√(h·h - d)`, in that order of operations. See V1.

T3. **"More than a double holds".** *Chosen:* the exact entry's absolute
    value against the largest double, 1.7976931348623157·10³⁰⁸; an entry
    equal to it is accepted. A negative entry counts by its size. An
    implementation in doubles overflows somewhere on the way and may
    refuse earlier (round two, R1); that is unchanged.

### What I believe the new wording gets wrong

V1. **The formula for two states guards one subtraction and leaves the
    other.** "worked that way round so that a slow rate beside a fast one
    is not lost in the subtraction." The slow rate is lost a step
    earlier, in the determinant, where two nearly equal products are
    subtracted. Run: `thermal_rc2`, both masses 1, `coupling` 1, both
    `heat_transfer`s 10⁻¹², period `1s`. The slow rate is 10⁻¹² a second
    exactly (the two temperatures decay together), so the constant is
    10¹² s and `settle` 3·10¹² ticks. `impl.py`, working `d` as
    `a00·a11 - a01·a10` in doubles, gets a constant of 9.99911·10¹¹ and a
    `settle` of 2,999,733,321,963 ticks: one part in 10⁴ out, 267 million
    ticks short. With losses of 10⁻⁹ it is 246 ticks out of 3·10⁹. Two
    implementations that work `d` in the same order agree with each other
    and not with the model; two that do not (a compiler that fuses the
    multiply and subtract, say) can differ by ticks, and `settle` decides
    a state, which is compared exactly. The determinant of a named model
    can be had without the subtraction: for `thermal_rc2` it is
    `(ha·hb + k·(ha + hb)) / (ca·cb)`, a sum of products that are not
    negative. The text should give `d` for each named model in that form,
    or say in what arithmetic it is worked.

V2. **A model refused by the bound is not always one "that has settled
    long before a tick".** The text says of a refused model that it "has
    a state that has settled long before a tick ... or has its states in
    units far apart". The bound is on the size of `A` and not on how fast
    anything decays. Run: `linear`, `A: [[0, 200000], [0, 0]]`,
    `B: [[0], [1]]`, `C: [[1, 0]]`, period `1s`: refused, and its `Ad` is
    `[[1, 200000], [0, 1]]`, exact in doubles, with nothing settling at
    all. That is the "units far apart" case if the two states are read as
    such, but so is any integrator with a large gain, and the cure the
    text names (rescale) is the only one; the first half of the sentence
    does not apply. I note it so that the reason given matches every
    graph the rule refuses.

## Round four

The text was revised on T1, T3, V1 and V2 of round three. Quotations are
from the revised `proposal.md`; each example was run on `impl.py`.

| Entry | Settled? | Code changed? |
| --- | --- | --- |
| T1. The arithmetic of the bound | Yes, the other way, and the edge is let go: "The sum is of `A` alone, in double arithmetic, and a graph within rounding of the bound, or of what a double holds, may be taken either way." | Yes: the sum is now in doubles (each row's absolute values added from first to last, the largest, times the period in seconds as a double), refused where more than 100,000 |
| T2. How `d` is worked out for `settle` | Yes: "`d` is taken from the model's settings, as its entry in Appendix A gives it, and not from `A`'s entries", with a formula in each of the four entries | Yes: `thermal_rc2`, `second_order_process`, `mass_spring_damper` and `dc_motor` each give their determinant from their settings. `h` is still half the sum of `A`'s diagonal |
| T3. "More than a double holds" | Yes: within rounding of it, either way | No: `impl.py` still compares the exact entry |
| V1. The determinant loses the slow rate | Yes, for `thermal_rc2`: its determinant is now a sum of terms that are not negative. Run: both masses 1, `coupling` 1, losses of 10⁻¹² → the constant is 10¹² s and `settle` 3,000,000,000,000 ticks (it was 2,999,733,321,963) | Yes, as T2 |
| V2. What a model refused by the bound is | Yes: "a state far faster than the period ... or has entries that are large for the units its states are in" | No |

At the edge, as `impl.py` now has it: `A: [[-33333.333333333336]]` at
`3s` is accepted (it was refused); `A: [[-5]]` at `20000s` is accepted
and at `20000001ms` refused.

### What is still open, or wrong

X1. **A `dc_motor`'s determinant still has a subtraction, and there it
    decides whether there is a `settle` at all.** "`A`'s determinant is
    `(resistance·friction + back_emf·torque_constant) / (inductance·inertia)`."
    With `back_emf` and `torque_constant` of opposite signs, which the
    ranges allow, the two products cancel. Rule 7.8.6 owns that "the last
    ticks of a `settle` of millions still depend on rounding"; this is
    more than the last ticks. Run, `inductance` and `inertia` 1,
    `torque_constant` 1, period `1s`:
    - `resistance: 0.1`, `friction: 0.3`, `back_emf: -0.03`: in doubles
      `0.1·0.3 + -0.03` is exactly 0, so the largest real part is zero and
      the model has **no** `settle`: `good` the tick after a doubt. The
      three doubles, multiplied and added exactly, give 1.7·10⁻¹⁸: a model
      that does decay, with a `settle` of about 10¹⁸ ticks: `uncertain`
      for good. An engine whose compiler fuses the multiply and the add
      gets the second.
    - `resistance: 3`, `friction: 0.1`, `back_emf: -0.3`: 5.6·10⁻¹⁷ in
      doubles and 2.8·10⁻¹⁷ exactly: a `settle` of 1.7·10¹⁷ ticks against
      half that.

    These are models on the edge of not decaying, where no answer is a
    good one; but the state after a doubt is compared exactly, and here
    it turns on how a product is rounded. The text could say that a
    `dc_motor` whose two products differ in sign is given no `settle`, or
    say "within rounding, either way" of this as it now does of the
    bound.

X2. **The order of the double sum is still mine.** "in double
    arithmetic" does not say in what order a row is added or which double
    the period is. *Chosen:* each row from its first entry to its last,
    then the largest, times `period in nanoseconds / 10⁹` rounded to a
    double. With the edge now free either way this cannot make two
    implementations disagree on anything the text holds them to; I record
    it for completeness.

Still open from round one, text unchanged: 4 (the estimator's model), 5
(which blocks count against one model block on a loop), 7 (`tau` as a
length), 8 (what has no range said), 9 (`linear` or `state_space` on a
loop).

## Round five

**X1 is settled.** The `dc_motor` entry now reads "`resistance`,
`friction`, `back_emf` and `torque_constant` not negative, so that
nothing in the determinant is subtracted." With all four not negative,
`resistance·friction + back_emf·torque_constant` is a sum of two products
that are not negative, and no rounding can turn a model that decays into
one that does not.

What changed in `impl.py`: `back_emf` and `torque_constant` of a
`dc_motor` are refused where less than zero (they were any finite number).
Zero is accepted for both. This is so for a `dc_motor` block and for a
`dc_motor` as an estimator's model. Nothing else changed.

Run: the two graphs of X1 (`back_emf: -0.03` and `-0.3`) are now refused.
With `resistance: 0`, `friction: 0` and both constants 1 the model has no
`settle` (a pair of eigenvalues on the imaginary axis), and with both
constants 0 as well, none either (the determinant is zero).

One consequence, which I think is meant: no named model can now have an
eigenvalue with a real part above zero, so the refusal of rule 7.8.7 for a
model that "grows so fast" can only be met by a `linear` block. A motor
wired to run backwards (a generator's sign convention, say) has to be
written as `linear`. Section 12 says the ranges are "wider in places"
than 1.x's; whether 1.x allowed a negative constant I cannot tell from
this text.

Still open, text unchanged: entries 4, 5, 7, 8 and 9 of part A (of entry
8, only `gain` and the initial values are now without a stated range), and
X2 of round four (the order of the double sum, which the text lets go
either way at the edge).

## Round six

Rule 7.8.7 now says: "The promise does not depend on the size of `B`:
`Bd` is the integral of `exp(A·s)` over the period, times `B`."

**`impl.py` did not keep that promise, and now does.** It read `Ad` and
`Bd` off one exponential of `[[A, B], [0, 0]]` times the period. A large
`B` set how far that matrix was halved, and at 100 digits the `A` in it
was lost: with `A: [[-1]]`, `B: [[1e120]]` at `1s` it gave an `Ad` of 1.0
where `exp(-1)` is 0.368 (with `B` of `1e80` and below it was right). The
closed forms of round one had no `B` larger than 10⁶, so they did not
show it; and the "How the step is worked out" paragraph at the head of
this file, which says "`Bd` needs no inverse of `A`", is right about that
and silent about this.

What changed: `B` is out of the exponential. With `T` the period,
`impl.py` takes the exponential of `[[A·T, 1], [0, 0]]`, which is
`[[Ad, G], [0, 1]]` with `G` the integral of `exp(A·T·s)` for `s` from
zero to one, and gives `Bd` as `T·G·B`, the product worked in the same
100-digit arithmetic before it is rounded to doubles. The matrix that is
halved now depends on `A·T` alone, whose rows the bound holds to 100,000.
An entry of `Ad` or `Bd` that is more than a double holds is refused as
before.

Run, `dx/dt = -x + b·u` at `1s`: `Ad` is 0.36787944117144233 and `Bd` is
`b` times 0.6321205588285577 for `b` of 1, 10⁹, 10⁸⁰ and 10¹²⁰.

### What the new wording leaves open

S1. **"A resonance of 50 Hz is within it at a period of 1 s" holds only
    with little damping.** The row of a `second_order_process` is
    `omega_n²` and `2·zeta·omega_n`, and of a `mass_spring_damper`
    `stiffness / mass` and `damping / mass`; the text names the first of
    each. Run: `omega_n` of 314.159... (50 Hz) at `1s` is accepted with
    `zeta` 0 (the sum is 98,696), 0.2 and 0.25 (98,853); it passes
    100,000 at a `zeta` of about 2.08. So a heavily overdamped 50 Hz
    process is refused at 1 s. The sentence is true as an example and
    should not be read as the rule: the rule is the sum.

S2. **The drift the text describes is between two engines, and no vector
    of mine can show it.** "two engines that agree on every step drift
    apart in an oscillator with no damping by about one part in 10⁹ in a
    few hundred ticks at the bound". Against a closed form, `impl.py`'s
    undamped spring at 2 rad/s and a period of 250 ms (far inside the
    bound) is within 1.6·10⁻¹² after 400 ticks (round one). I have not
    run an oscillator at the bound for hundreds of ticks against a closed
    form; the text's figure is of two engines in doubles and I have only
    one.

Still open, text unchanged: entries 4, 5, 7, 8 (in part) and 9 of part A.

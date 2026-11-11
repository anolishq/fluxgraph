# FluxGraph semantics, version 2 (proposal)

**Status:** proposal, second revision. Not in force.
[semantics_spec.md](semantics_spec.md) stays the normative contract for
FluxGraph 1.x until this is accepted, at which point this document replaces
it and the library becomes 2.0.

Each section is marked **Proposed** (a position to argue with) or **Open**
(a question with what would settle it). Nothing here is implemented in the
library.

The first revision was tested for clarity and then reviewed for whether its
rules were right. The review found three faults, and this revision answers
them:

- **`good` meant too much.** A window with holes, a timer running through a
  dead input, a total that had missed time and a value from a fallback all
  came out plainly `good`. There is now a fourth state, `uncertain`.
- **Time was a count of ticks.** A host that stalled left the graph's time
  behind for good, and a block could not tell a new sample from an old one
  still standing. The host now passes the time, the engine catches up, and
  an input says whether it is new.
- **Nothing dynamic was specified.** No low-pass, no hysteresis, no rule for
  what a block with state does with an unusable input, and no decision on
  whether a model reads its inputs from this tick or the last.

## 1. Why a second version

FluxGraph 1.x is a simulation library: physics models, then transforms
between signals, then rules. It is to become the signal-graph engine for
two uses:

- **Simulation**, as now: a plant model driven by actuator signals.
- **Signal processing on a live machine**: filters, transfer functions,
  estimators and detectors over measured signals, for the Anolis runtime
  (its derived-signals RFC, `docs/rfcs/derived-signals.md` in the anolis
  repository).

One engine for both lets one model serve as a simulator's plant and as an
estimator's predictor.

The second use was tried on 1.x as it stands. Ten signal-processing blocks
were written as 1.x models, with the library unchanged, and replayed against
test vectors. All of them ran and matched at every tick, so the lifecycle,
the namespace and the store carry a block graph already. What 1.x does not
give a block:

| Measured on 1.x | Answered in |
| --- | --- |
| A signal is one number, so a value's state had to ride in a second signal | 3 |
| A signal nobody has written reads as 0.0 | 3 |
| Models run in declared order, and the compiler sees their outputs and not their inputs. Two models that read each other's output compile and run, each a tick behind the other | 4, 5 |
| Only a model can read two signals, so nothing could be a transform | 4 |
| A model is not told the period when it is built, or the time when it runs | 6 |
| A model's spec has parameters and no ports | 4, 9 |

## 2. Scope

Version 2 breaks the 1.x graph format, the C++ interfaces for models and
transforms, and the server protocol. Nothing in 1.x is kept for
compatibility. The maths of the existing models and transforms carries over.

Not goals of 2.0: blocks at different rates, a variable step, parallel
evaluation, implicit solvers, vector values.

## 3. Values

**Proposed.**

1. A signal carries a **value** and a **state**. The state is one of:
   - `good`: the value is usable, and nothing is known against it.
   - `uncertain`: the value is usable, and something it rests on was
     degraded. It came from a fallback, it was held through a gap, it is a
     statistic of a window with holes, or it was given as uncertain.
   - `not_ready`: there is no value yet. A window is still filling, a filter
     has not started, an input has never been written.
   - `bad`: there is no usable value. An input was unusable, or the
     computation failed.
2. A value is **usable** when its state is `good` or `uncertain`. A signal
   that is not usable carries no value at all.
3. The states have an order, worst first: `bad`, `not_ready`, `uncertain`,
   `good`. "The worst state" of several is the first of them in that order.
4. A signal nobody has written is `not_ready`. There is no default value.
5. Every signal and every port has a **type**: `number`, a double, or
   `boolean`. Connecting a signal to a port of the other type is refused. A
   third type, a vector of numbers of fixed length, is reserved and not
   defined here.
6. No usable value is not finite. A block output that would be is `bad`,
   whatever the block.
7. A signal written from outside the graph also carries the **time it was
   sampled**, and at each tick it is either **new**, written since the tick
   before, or not. A block can see both.

**Open.**

- **Other value types.** Integers, strings and enumerations exist on the
  machines this will run on. Settled by: listing the blocks that would need
  one, and whether a number and a lookup outside the graph would do.
- **Vectors.** A state-space model, a covariance and anything in the
  frequency domain need them. Reserved in rule 5 so that adding them does
  not break the format. Settled by: the design of the estimator block
  (section 7.9).

## 4. Blocks

**Proposed.**

1. There is one kind of computing element, a **block**. A block has a type,
   named **input ports**, named **output ports**, **settings**, and state of
   its own.
2. A 1.x transform is a block with one input and one output. A 1.x model is
   a block with several. Edges are gone: a signal is connected by naming it
   as an input.
3. A block type declares, to the compiler:
   - its input and output ports, the type of each, and which inputs are
     required;
   - for each input, whether it is **direct** or **deferred** (rule 4);
   - its settings, each with a type, whether it is required, and its range.
4. A tick has two phases. In the first every block gives its outputs. In
   the second every block updates its state.
   - A **direct** input is read in the first phase: the block's output at a
     tick depends on that input at the same tick.
   - A **deferred** input is read only in the second phase. The block's
     output at a tick does not depend on it at that tick, only on what the
     block's state already holds.

   A delay has one deferred input. So does a model whose output is its
   state: two thermal masses that each take the other's temperature are two
   blocks with deferred inputs, and compile.
5. A block reads only its own inputs and writes only its own outputs. It has
   no access to the rest of the store.
6. Every output port is written by exactly one block. A signal written from
   outside the graph is written by nothing inside it.
7. An input port may be given a constant in place of a signal: a number, or
   `true` or `false`. It is `good`, with that value, on every tick, and is
   never new.
8. An input that is not required may be left unconnected. The block type
   says what that means.

**Open.**

- **Rules and commands.** In 1.x a rule tests one signal against a number
  and emits a device command. No graph file in this repository or in the
  simulator provider has a rule, though the provider has the code to run
  the commands one would emit. Proposed for removal; a condition is a block
  whose output is a boolean, and acting on it is the host's business.
  Settled by: the simulator provider's maintainers agreeing to drop that
  path.
- **Whether a 1.x model's inputs become direct or deferred.** 1.x updates
  every model from the values before the tick, which is deferred. Edges
  then reach a model one tick late, which nobody chose. Each model type has
  to be given one or the other on purpose, and a graph that relied on the
  accident will change. Settled by: going through the model types one at a
  time against their analytical validation.

## 5. Order and loops

**Proposed.**

1. The compiler sorts all blocks into one evaluation order for the first
   phase. A block gives its outputs after every block whose output it reads
   through a direct input.
2. Ties are broken by block id, so the order is the same on every compile.
3. A loop of direct inputs is a compile error that names the blocks on it.
   A loop that passes through a deferred input is accepted.
4. A delay on a loop has an initial value. Without one the loop would be
   `not_ready` for ever, and the graph is refused.
5. Nothing reads a value a tick late by accident. That lag exists only
   where a block type declares an input deferred.

## 6. Time

**Proposed.** One fixed period, tied to the host's clock.

1. A graph has one **period**, fixed when it is compiled. Every block runs
   once per tick.
2. Every length of time in a setting is a whole number of periods, and a
   graph where one is not is refused. Inside a block, time is counted in
   ticks. The exception is an input's maximum age (rule 6), which is
   compared with sample times and may be any length.
3. The host passes the time to every tick: `tick(now)`. The clock is the
   host's; it is in seconds, it does not go backwards, and it is the clock
   sample times are given on. The first call runs tick 0, and the time of
   tick 0 is that `now`. Tick `k` is at the time of tick 0 plus `k` periods.
4. A call runs, in order, every tick not yet run whose time is not after
   `now`. If there is none, the call does nothing. A call with a `now`
   earlier than the last one is refused.
5. When one call runs more than one tick, all but the last are **missed**.
   In a missed tick every external input is `bad`: nothing was sampled for
   it. The last tick uses what the host has written. The call says how many
   ticks it ran.
6. The host writes an external input at any moment: a state, a value, and
   the time it was sampled. At a tick that is not missed the input is the
   latest thing written, even if an earlier write carried a later sample
   time. Its age is the tick's time less its sample time, and not less than
   zero. Section 7.2 says what state it has.

So a host that stalls for a minute does not leave the graph a minute behind.
On its next call the graph runs the ticks it missed, with nothing to read.
Windows get holes, timers and totals follow their rules for unusable
inputs, and the graph's time is the host's again.

What this still leaves out:

- **Jitter inside a period.** A tick is treated as exactly one period after
  the last. A host whose call comes late by less than a period is not
  noticed.
- **Sample time is not tick time.** A block may use an input's sample time,
  and the blocks of the first catalogue do not: a value sampled just after
  the previous tick is treated the same as one sampled just before this
  one.
- **Different rates.** Everything runs at one period.

**Open.**

- **How far the engine catches up.** After a stall of an hour at a period of
  a second, 3,600 missed ticks run in one call. Settled by: a limit past
  which the engine resets instead, and who sets it.
- **What the period should be on a real machine**, and what maximum age is
  reasonable, when inputs are polled at about half a second with jitter and
  each device is read at its own moment. Settled by: measuring input age and
  the spread between devices on recorded data.

## 7. States through a graph

**Proposed.** The default is that a problem is never hidden. An input is
**usable** at a tick when its state is `good` or `uncertain` (section 3).

### 7.1 Formulas

A formula is the one block with no state.

1. The result of an operation takes the worst state among its operands.
2. **Logic is three-valued.** If any usable operand of an `or` is true, the
   result is true; if any usable operand of an `and` is false, the result is
   false. Its state is `good` if one of the operands that decided it is
   `good`, and `uncertain` otherwise. When no operand decides, rule 1
   applies.
3. **A choice**, `when(condition, a, b)`, takes the state of the condition
   if that is not usable. Otherwise it takes the value of the branch it
   chose, with the worse of that branch's state and the condition's. The
   other branch is not looked at.
4. A division by zero, the logarithm or square root of a negative number,
   and any result that is not finite, is `bad`.
5. These rules apply to each operation in turn, not once to the formula as
   a whole. In `(a or b) and c` with `a` true and `b` bad, the `or` is
   `good` and so, with `c` good, is the whole.
6. `==` and `!=` compare exactly.

### 7.2 Inputs from outside

At a tick, an external input is the first of these that applies:

1. `bad`, in a missed tick (section 6).
2. If nothing has been written to it:
   - `uncertain`, with its declared initial value, if it declares one;
   - otherwise `not_ready`, until the graph has run for longer than the
     input's maximum age, and `bad` from then on. An input with no maximum
     age stays `not_ready`.
3. `not_ready` or `bad`, if that is what the host last wrote.
4. `bad`, if the value written is not finite, or its age is more than the
   input's maximum age.
5. `uncertain` or `good`, as the host last wrote, with that value.

A value written and not written again stands, and grows older. An age
exactly equal to the maximum is still usable. A write of `not_ready` does
not grow old: it has no sample.

An input is **new** at a tick if it was written since the tick before. In a
missed tick nothing is new.

A block output is new at a tick if the block has no signal inputs, or if any
of its inputs is new. Every block of Appendix A follows that; a block type
may say otherwise.

### 7.3 Windows

1. **A window is the usable samples of its last `n` ticks**, where `n` is
   its `window` setting in periods. Its statistics are of those samples and
   no others.
2. A window has a setting, `min_good`: the fraction of its `n` ticks that
   must hold a usable sample. It is 1 unless given.
3. When a window holds fewer usable samples than `min_good × n`, every
   output but `count` takes the worst state among its ticks that hold none.
   A tick from before the graph started counts as `not_ready`.
4. Otherwise its outputs are `good` if every one of its `n` ticks holds a
   `good` sample, and `uncertain` if not.
5. A slope needs two usable samples. With one it is `bad`, while the other
   statistics are as rule 4 says.
6. `count`, the number of usable samples the window holds, is always `good`.

A window with a hole in it does not report `good`. It reports nothing at
all, or with `min_good` below 1 it reports `uncertain`.

### 7.4 Blocks that hold a value

A deadband and a low-pass each keep one value.

1. With a usable input the block updates, and its output takes the input's
   state.
2. With an unusable input the block keeps what it holds. Its output is:
   - the held value, `uncertain`, if the last usable input was no more than
     `ride_through` ago and the block is holding something;
   - otherwise the input's state.
3. `ride_through` is zero unless given, so that the output stops being
   usable on the same tick as the input.
4. The first usable input is taken as it is.

### 7.5 Hysteresis

A hysteresis block turns a number into a boolean with two thresholds.

1. It goes true when its input is at or above `rise`, and false when its
   input is at or below `fall`. Between the two it stays as it was.
2. Until its input has been at or beyond one of the thresholds, its output
   is `not_ready`.
3. With a usable input its output takes the input's state. With an unusable
   input it keeps what it was, and its output takes the input's state.

### 7.6 Timers and latches

Each takes a boolean.

1. **Held for.** True when its input has been true for longer than `time`.
   The tick on which the input becomes true counts as no time at all. A
   usable input that is false stops the timer, and the output is false,
   with the input's state. While the timer runs on usable inputs, the
   output is `good` if every input since it started was `good`, and
   `uncertain` if not. Required `on_bad`:
   - `reset`: an unusable input stops the timer, and the output takes the
     input's state.
   - `hold`: an unusable input leaves the timer running, for at most
     `hold_limit`, a required setting. While it runs the output is
     `uncertain`, and true once the time has run out. When the unusable
     stretch grows longer than the limit, or if the timer was not running,
     the timer stops and the output takes the input's state.
2. **Since true.** True when its input has not been true for longer than
   `time`. Its clock starts at the first tick and restarts on every tick
   where the input is usable and true. With a usable input the output takes
   the input's state. Required `on_bad`:
   - `assume_false`: an unusable input counts as not true, and the output
     is `uncertain`.
   - `unknown`: the output takes the input's state. The clock is not
     touched.
3. **Latch.** False until its input `set` is first true, then true.
   - Once set, its output is `good` and true whatever `set` then does.
   - Not yet set, its output is false with the state of `set` if that is
     usable, and takes the state of `set` if it is not.
   - It has an input `reset` that need not be connected. A usable, true
     `reset` clears it, on that tick, and wins over `set`. An unusable
     `reset` does nothing.

### 7.7 Integrators

1. An integrator adds its input, times the period, on every tick where the
   input is usable. The value at a tick includes that tick's addition.
2. `missed` is the time it has not integrated: the period, added up over
   every tick where the input was unusable. It is always `good`.
3. The total is `good` while `missed` is zero and every input it has added
   was `good`. It is `uncertain` otherwise.
4. With `max_missed` set, the total is `bad` once `missed` is more than
   that.
5. It has an input `reset` that need not be connected. A usable, true
   `reset` returns the total and `missed` to zero, and the total to `good`,
   before that tick's addition. An unusable `reset` does nothing.

A total that has missed time says so in its state as well as in `missed`.

### 7.8 Other blocks with state

A block with state for which this section gives no rule, which includes the
models carried over from 1.x, does not advance on a tick where any of its
inputs is unusable. Its outputs take the worst state among its inputs.

An input with an initial value (section 7.2) is what lets a plant model
start before everything that feeds it has been written.

### 7.9 Estimators

No estimator is in the first catalogue. These rules bind one when it comes,
and a small fixture (Appendix B) exercises them.

1. An estimator is `not_ready` until its first usable, new measurement.
2. It corrects only on a tick where a measurement is usable and new. A
   measurement still standing from an earlier tick is not used twice.
3. On any other tick it predicts and does not correct.
4. It has a required setting, `max_coast`. Its outputs are `uncertain` when
   it has gone longer than that without a correction, and when the
   measurement it last corrected on was `uncertain`. Otherwise they are
   `good`.

**Open.** The estimator itself: a linear state-space model with predict and
correct, an innovation gate so that one wild measurement is refused, the
innovation as an output, and noise given on inputs. It needs vector values,
and the means to take a FluxGraph model as its predictor. Settled by: its
own design, after this proposal.

### 7.10 Fallbacks

A block may name, for any of its outputs, a value to give when that output
is not usable. The substituted value is `uncertain`. Each applies to the
output it names and to no other. Every reader of that output sees the
substituted value, inside the graph as well as outside it.

**Open.**

- **Whether `not_ready` and `bad` are ever treated differently by a block's
  policy.** Here they are alike in what they do to a block's state and
  distinct only in what the block reports. Settled by: a case where an
  author would want them to differ.
- **Whether a consumer needs to know why a value is `uncertain` or `bad`.**
  A stale input, a faulted sensor, a failed computation and a bad input
  upstream all arrive as `bad`. Settled by: what each consumer in Anolis
  would do differently if it could tell.

## 8. State, reset and restore

**Proposed.**

1. A graph can be reset to its initial state. After a reset the next call
   runs tick 0 again.
2. A graph can write its state out and take it back, so that a host can
   save a running graph and restore it.
3. A state saved from one graph is refused by a graph that is not the same.
4. Time does not pass while a graph is not running. After a restore the
   next call runs the tick after the last one saved, at the `now` it is
   given, and the ticks in between are not caught up.

**Open.** What "the same graph" means: the same text, or the same blocks,
settings and period, and in either case the same layout of state in the
library that wrote it. And whether the gap across a restore should instead
be run as missed ticks, which is what a window or an integrator would want
and what a model of a plant that was also switched off would not.

## 9. The graph file

**Proposed.** The shape, not the final keys:

```yaml
period: 2.5s

inputs:
  heater/pad_c: { type: number, unit: degC, max_age: 10s }
  heater/relay: { type: boolean, max_age: 10s }
  room/ambient_c: { type: number, unit: degC, initial: 20 }

blocks:
  - id: pad
    type: window
    in: { x: heater/pad_c }
    settings: { window: 7.5s }
    out: { median: heater/pad_filtered_c }
```

1. `inputs` lists every signal written from outside, with its type and,
   where it has them, its unit, its maximum age and its initial value. A
   type left out is `number`. A graph that reads a signal which is neither
   an input nor a block's output is refused.
2. A block's `in` maps each input port to a signal or to a constant. Its
   `out` maps output ports to signal names; a port left out is not
   published, and another block can still read it as `<block id>.<port>`.
3. These are compile errors: an unknown key, at the top of the graph or in
   a block or an input; an unknown block type; a block with no id, or with
   another block's id; an unknown port in `in`, `out` or `fallback`; a
   required input left unconnected; a signal connected to a port of the
   other type; an unknown setting; a setting of the wrong type or out of
   range; a missing required setting; a length of time that is not a whole
   number of periods; and a signal with two writers. 1.x ignores an unknown
   top-level key.
4. A graph with several faults is refused for one of them. Which one, and
   the wording, are not specified. The refusal names the thing at fault.

## 10. Units

**Proposed.** As in 1.x, moved from signals to ports: an input or an output
port may declare a unit, a connection between two declared units that differ
is a compile error, and the strict policy requires every port to declare
one. An external input declares its unit in `inputs`. 1.x also checks the
unit given with every write; a version 2 write carries none.

**Open.** The registry is a fixed built-in list. A live machine has units
it does not hold. Settled by: whether a graph may declare its own units,
and what a declared unit has to say.

## 11. Conformance

**Proposed.** The rules above are tested by vectors, not by reading.

1. A test vector is a graph, the calls the host makes (each with its `now`
   and what it wrote first), and the expected state and value of every
   output after each call.
2. Every numbered rule in sections 3 to 9 has at least one vector that fails
   if the rule is broken, except where no output can show the rule. A
   vector is accepted only after a deliberately broken implementation has
   been shown to fail it.
3. Expected values are worked out independently of the implementation under
   test.
4. A second implementation, written from this document alone, passes the
   same vectors.
5. Values are compared to within one part in 10⁹. Where a rule turns on
   exact equality (rule 7.1.6, the step of a deadband), a vector uses values
   that are exact in binary.

`conformance/` holds the vectors, two readings of this proposal, and the
checks that run them.

## 12. What happens to 1.x

| 1.x | 2.0 |
| --- | --- |
| `IModel`, `ITransform` | One block interface, with direct and deferred inputs |
| Edges | Gone; a signal is named as an input |
| `tick(dt)` | `tick(now)`; the period is fixed at compile |
| Models run first, then edges | One sorted order, two phases |
| Signal: a number and a unit | A typed value, a state, and for inputs a sample time |
| Unwritten signal reads 0.0 | Unwritten signal is `not_ready`, unless its input declares an initial value |
| Rules and commands | Open (section 4) |
| Unknown keys ignored by the loaders | Refused |
| Thermal, process, mechanical and motor models; the transforms | Kept as block types |
| Delay in seconds | Delay in ticks; lengths of time are whole periods |
| Noise from the standard library's generator | A generator this document will have to name, so that a vector can cover it |
| Units, namespace, loaders, diagram tool | Kept, adapted to ports |
| The server protocol | Changes with the above |

## 13. Order of work

1. This document is argued to agreement, section by section.
2. The core is rebuilt against the conformance vectors: store, compiler,
   engine, block interface.
3. The existing models and transforms move across as block types, each
   given direct or deferred inputs on purpose and each keeping its
   analytical validation.
4. The loaders, the server and the simulator provider follow.
5. The estimator block is designed (section 7.9).

## Appendix A. A first catalogue

**Proposed.** Enough block types to test the rules above and to be useful.
Names, ports and settings are placeholders for argument; the behaviour is
what the vectors pin down.

| Type | Inputs | Settings | Outputs |
| --- | --- | --- | --- |
| `formula` | any, named in the formula | `expr` | `y` |
| `all_good` | any | none | `y`: boolean |
| `delay` | `x`, deferred | `ticks` (1), `initial` (none) | `y` |
| `window` | `x`: number | `window`, `min_good` (1) | `mean`, `median`, `min`, `max`, `spread`, `slope`, `count` |
| `deadband` | `x`: number | `step`, `ride_through` (0) | `y` |
| `lowpass` | `x`: number | `tau`, `ride_through` (0) | `y` |
| `hysteresis` | `x`: number | `rise`, `fall` | `y`: boolean |
| `held_for` | `x`: boolean | `time`, `on_bad`, `hold_limit` | `y`: boolean |
| `since_true` | `x`: boolean | `time`, `on_bad` | `y`: boolean |
| `latch` | `set`: boolean; `reset`: boolean, optional | none | `y`: boolean |
| `integrate` | `x`: number; `reset`: boolean, optional | `per` (1 s), `max_missed` (none) | `y`, `missed` |

A setting with a value in brackets may be left out and takes that value. An
input is required and direct unless the table says otherwise. An output is a
number unless the table says otherwise. `formula` and `all_good` take one or
more inputs under any names.

Ranges, outside which a graph is refused: `ticks` a whole number, at least
1; `window` at least one period; `min_good` more than 0 and at most 1;
`step`, `ride_through`, `time`, `hold_limit` and `max_missed` not negative;
`per` and `tau` more than zero; `rise` more than `fall`; `initial` and any
fallback finite; `on_bad` one of the choices its block gives. `hold_limit`
is required with `on_bad: hold` and refused without it.

- **`formula`.** Section 7.1 governs states.
  - **Numbers:** digits, an optional point and more digits, an optional
    exponent (`e` or `E`, an optional sign, digits). Nothing else: no sign
    of its own, no hexadecimal, no separators.
  - **Booleans:** `true` and `false`.
  - **Names:** a letter or underscore, then letters, digits and underscores.
    `and`, `or`, `not`, `true`, `false` and the function names are not
    input names.
  - **Operators**, from loosest to tightest: `or`; `and`; `not`; the
    comparisons `< <= > >= == !=`; `+` and `-`; `*` and `/`; unary minus.
    Operators of one level group from the left. Brackets group. Comparisons
    do not chain: `a < b < c` is refused.
  - **Functions:** `abs(a)`, `min(a, b)`, `max(a, b)`, `exp(a)`, `ln(a)`,
    `sqrt(a)`, `pow(a, b)` and `when(condition, a, b)`.
  - **Types:** arithmetic and the functions take numbers and give a number.
    `< <= > >=` take numbers and give a boolean. `==` and `!=` take two of
    one type and give a boolean. `and`, `or` and `not` take booleans and
    give a boolean. `when` takes a boolean and two of one type, and gives
    that type. Anything else is refused. The type of `y` is the type of the
    formula.
  - A name the formula uses must be one of the block's inputs, and every
    input of the block must be used by the formula. Either fault is refused.
  - Spaces between tokens mean nothing. A formula is one line.
- **`all_good`.** True when every input is `good`, else false. Always
  `good`.
- **`delay`.** At tick `k` its output is its input at tick `k - ticks`, state
  included, as that input was then. Before that tick exists, its output is
  `initial` and `good`, or `not_ready` if no initial value is given. Its
  type is its input's.
- **`window`.** `window` is `n` periods. At a tick the window is that tick
  and the `n - 1` before it. `median` of an even number of samples is the
  mean of the middle two. `spread` is `max - min`. `slope` is the
  least-squares slope of value against time, per second, taking the oldest
  tick of the window as time zero. Section 7.3 governs states.
- **`deadband`.** Keeps its output until its input has moved by `step` or
  more from the value it is holding, and then takes the input as it is. The
  comparison is exact. Section 7.4 governs states.
- **`lowpass`.** One pole. With `a = exp(-period / tau)`, on a usable input
  `y = a·y + (1 - a)·x`; the first usable input sets `y = x`. Section 7.4
  governs states.
- **`hysteresis`.** Section 7.5.
- **`held_for`.** Section 7.6 rule 1. With `time` of `n` periods, the output
  is true on a tick when the timer started more than `n` ticks before it.
- **`since_true`.** Section 7.6 rule 2. With `time` of `n` periods, the
  output is true on a tick more than `n` ticks after the clock was last
  set.
- **`latch`.** Section 7.6 rule 3.
- **`integrate`.** Section 7.7. On a usable tick it adds `x × period / per`.
  `missed` is in seconds.

A block may carry `fallback`, a map from an output port to a constant of
that port's type (section 7.10).

## Appendix B. A fixture for the estimator rules

Not part of the catalogue. `kalman1` exists so that section 7.9 has
something to run against, and it is not a filter to use: it has no gate
against a wild measurement, and the uncertainty it reports is a function of
its settings alone.

| Type | Inputs | Settings | Outputs |
| --- | --- | --- | --- |
| `kalman1` | `z`: number; `model`: number | `tau`, `q`, `r`, `max_coast` | `x`, `sigma` |

One state, relaxing toward `model` with time constant `tau` and corrected by
`z`. With `a = exp(-period / tau)`, process noise `q` per second and
measurement variance `r`:

- on the first tick where `z` is usable and new: `x = z`, `var = r`; nothing
  else happens on that tick;
- on each later tick, first predict: with `model` usable,
  `x = a·x + (1 - a)·model` and `var = a²·var + q·period`; otherwise `x` is
  unchanged and `var = var + q·period`;
- then, with `z` usable and new, correct: `k = var / (var + r)`,
  `x = x + k·(z - x)`, `var = var·(1 - k)`.

`sigma` is the square root of `var`. `tau` and `r` are more than zero, and
`q` and `max_coast` not negative.

# FluxGraph semantics, version 2 (proposal)

**Status:** proposal, third revision. Not in force.
[semantics_spec.md](semantics_spec.md) stays the normative contract for
FluxGraph 1.x until this is accepted, at which point this document replaces
it and the library becomes 2.0.

Each section is marked **Proposed** (a position to argue with) or **Open**
(a question with what would settle it). Nothing here is implemented in the
library.

The second revision was reviewed twice, as a contract with a host and as
signal processing. Both reviews found it not fit to build on. What they
found, and what this revision does about it:

- **A host a little slower than the period lost data it had in hand.** A
  tick the host had not called for saw every input as `bad`. A loop at
  2.503 s against a period of 2.5 s then spoiled a thirty-minute window for
  most of eight hours. Time is now the fixed timestep that games and
  simulators use (section 6): in a catch-up tick an input is whatever
  stands, judged by its age.
- **`uncertain` was not one idea.** It washed out through a latch, a
  hysteresis and a low-pass, and stuck for ever on a total. It is now a
  taint on memory with a stated end (section 7), and an uncertain value
  carries the tick of what caused it, so that taint going round a loop
  runs out.
- **A sample was new when it was written, not when it was taken.** A host
  that republishes what it holds made an estimator correct on one sample
  many times. A signal now carries its sample time, and a block that needs
  to know whether a sample is new compares sample times (section 3).
- **One unusable tick killed a loop for good**, and the rule for models
  was not implemented by anything. A model is now a thing with a state that
  a block hosts (section 7.8). It never gives up its state.
- **The estimator rules would not have survived an estimator.** One is now
  specified (section 7.9), hosting a model as its predictor.
- **Restore gave `good` values from memory a day old.** A restore is now a
  gap (section 8), and every block says what a gap does to it.

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
     degraded.
   - `not_ready`: there is no value yet.
   - `bad`: there is no usable value.
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
   whatever the block. The block's state is not put right for it.
7. A signal may carry a **sample time**: the time, on the host's clock,
   that its value was taken.
   - An input from outside carries the sample time it was written with.
   - A `formula` output carries the sample time of the input its
     `sample_of` setting names. A formula with exactly one signal input
     and no `sample_of` carries that input's.
   - A `delay` output carries the sample time of what it gives.
   - Every other block output carries the time of the tick, and so does a
     value a fallback puts in (section 7.10), whatever the block.
   - A signal that is not usable carries none.

   A block that must not use one sample twice remembers the sample time it
   last used, and uses a value only when its sample time is later. There is
   no other notion of a sample being new.
8. An `uncertain` value carries its **cause**: the number of the tick at
   which the thing that made it uncertain happened.
   - Where a rule in this document makes a value uncertain and names no
     cause, the cause is the tick it happens at. An input that stands
     `uncertain`, or is on its initial value, is uncertain anew at every
     tick it is read: its cause is each tick's own.
   - Otherwise the cause of an uncertain block output is the latest cause
     among the block's direct inputs that are uncertain at that tick, or
     the tick itself if none is.

   The cause is what lets a block whose memory fades say when a doubt has
   faded with it (sections 7.4, 7.8). It is not given to the host.

**Open.**

- **Other value types.** Integers, strings and enumerations exist on the
  machines this will run on. Settled by: listing the blocks that would need
  one, and whether a number and a lookup outside the graph would do.
- **Vectors.** Kept out of this revision by giving the estimator one output
  per state (section 7.9). Settled by: the first block that cannot be
  written that way.

## 4. Blocks

**Proposed.**

1. There is one kind of computing element, a **block**. A block has a type,
   named **input ports**, named **output ports**, **settings**, and state of
   its own.
2. A 1.x transform is a block with one input and one output. Edges are
   gone: a signal is connected by naming it as an input.
3. A block declares, to the compiler:
   - its input and output ports, the type of each, and which inputs are
     required;
   - for each input, whether it is **direct** or **deferred** (rule 4).
     This is declared by the block as it is configured, not by its type: a
     state-space model's input is direct only when its `D` is not zero;
   - its settings, each with a type, whether it is required, and its range.
4. A tick has two phases. In the first every block gives its outputs. In
   the second every block updates its state.
   - A **direct** input is read in the first phase: the block's output at a
     tick depends on that input at the same tick.
   - A **deferred** input is read only in the second phase. The block's
     output at a tick does not depend on it at that tick, only on what the
     block's state already holds.
5. A block reads only its own inputs and writes only its own outputs. It has
   no access to the rest of the store.
6. Every output port is written by exactly one block. A signal written from
   outside the graph is written by nothing inside it.
7. An input port may be given a constant in place of a signal: a finite
   number, or `true` or `false`. It is `good`, with that value, on every
   tick, and has no sample time.
8. An input that is not required may be left unconnected. The block type
   says what that means.
9. A **model** is not a block. It is a state, a rule that steps the state
   over a length of time given its inputs, a rule that gives its outputs
   from its state and inputs, and the **sensitivity** of the stepped state
   to the state it was stepped from. A block hosts a model (section 7.8),
   and so does an estimator (section 7.9). A 1.x model becomes a model in
   this sense.

**Open.**

- **Rules and commands.** In 1.x a rule tests one signal against a number
  and emits a device command. No graph file in this repository or in the
  simulator provider has a rule. Proposed for removal; a condition is a
  block whose output is a boolean, and acting on it is the host's business.
  Settled by: the simulator provider's maintainers agreeing to drop that
  path.

## 5. Order and loops

**Proposed.**

1. The compiler sorts all blocks into one evaluation order for the first
   phase. A block gives its outputs after every block whose output it reads
   through a direct input.
2. Ties are broken by block id, so the order is the same on every compile.
3. A loop of direct inputs is a compile error that names the blocks on it.
   A loop that passes through a deferred input is accepted.
4. Every delay that can reach its own input through any chain of inputs,
   direct or deferred, has an initial value. Without one the graph is
   refused.
5. Nothing reads a value a tick late by accident. That lag exists only
   where a block declares an input deferred.
6. A loop made of a formula and a delay has no memory that fades. One
   unusable value in it stays in it, and so does one uncertain value. This
   is true of what such a loop computes and is not put right by any rule.
   A running total, a filter and a model each have a block with a rule for
   it.

## 6. Time

**Proposed.** A fixed timestep. The host says what time it is; the engine
runs as many ticks of one fixed length as fit; every tick reads its inputs
as they stand.

1. A graph has one **period**, fixed when it is compiled. Every block runs
   once per tick.
2. Every length of time a block counts (a window, a timer, a limit) is a
   whole number of periods, and a graph where one is not is refused. The
   test is exact, on the numbers as written: `0.3s` is three periods of
   `0.1s`, and `900.0000001ms` is not three periods of `300ms`. Inside a
   block, time is counted in ticks. Where a rule rounds a number of ticks
   or of samples up to a whole number, a value within 10⁻⁹ of a whole
   number is that number. Two kinds of length are not counted and
   may be any length: an input's maximum age and how far ahead it may be
   stamped, and a setting that only scales a value (`tau`, `per`).
3. The host passes the time to every call: `tick(now)`. The clock is the
   host's. It is in seconds, it is a finite number, and it does not go
   backwards. It is the clock sample times are given on.
4. The first call runs tick 0, and the time of tick 0 is that `now`. Tick
   `k` is at the time of tick 0 plus `k` periods.
5. A call runs, in order, every tick not yet run whose time is no more than
   half a period after `now`, with the slack of rule 10. If none is due the
   call does nothing, and says it ran no tick.
6. The host writes an input at any moment: a state, a value, and the time
   it was sampled. Everything written since the last tick that ran is taken
   up together, at the **last** tick of the next call that runs one. The
   ticks of that call before the last are **catch-up** ticks. They see what
   stood before those writes.
7. A graph has a setting, `max_catch_up`, 100 unless given. When a call
   would run more ticks than that, it is a **gap** (section 8): one tick is
   run, numbered one more than the last, and its time is `now`. Later ticks
   are at whole periods from it.
8. A call gives the number of ticks it ran and the outputs of the last. The
   outputs of catch-up ticks are not given.
9. A call with a `now` that is not finite, or is earlier than the last
   call's, is refused and changes nothing. One with the same `now` is
   accepted.
10. Four comparisons of times allow a **slack** of one millionth of a
    period, so that a period that is not exact in binary does not put a
    value on the wrong side: a tick's time against half a period after
    `now` (rule 5), an age against a maximum age, a sample time against how
    far ahead it may be, and how long the graph has run against a maximum
    age (section 7.2). In each, "more than" means more than by over the
    slack.

So a host whose loop is a little slow or a little fast runs, now and then,
two ticks in a call or none. Nothing is lost: the extra tick sees the same
inputs, a period older. Counted times and totals stay true to the host's
clock. A host that stalls for a minute runs the ticks it missed on its next
call, on inputs that grow old and turn `bad` through their maximum age,
which is the true reason.

What this still leaves out:

- **The host's clock.** If it steps, the engine sees the step. A host
  should pass a clock that does not.
- **Sampling.** An input is read once per tick. A signal that changes
  faster than that is aliased: a relay cycling every 10 s and read every
  2.5 s reports a duty cycle that depends on phase. An input has to be
  slower than the period, or be a count the device keeps.
- **Different rates.** Everything runs at one period.

**Open.**

- **What the period should be on a real machine**, and what maximum age is
  reasonable, when inputs are polled at about half a second with jitter and
  each device is read at its own moment. Settled by: measuring input age and
  the spread between devices on recorded data.

## 7. States through a graph

**Proposed.** The default is that a problem is never hidden, and that a
value resting on a doubtful memory says so for as long as it does.

**The rule for memory.** A block's output is `uncertain` while any memory
it rests on took in something that was not `good`, until that memory is
flushed. Each block below says what its memory is and when it is flushed.
A block is free to give something worse than `uncertain`.

### 7.1 Formulas

A formula has no memory.

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
4. Among usable operands, a division by zero, the logarithm or square root
   of a negative number, a power with no real value, and any result that is
   not finite, is `bad`. With an unusable operand rule 1 applies instead.
5. These rules apply to each operation in turn, not once to the formula as
   a whole.
6. `==` and `!=` compare exactly.
7. A number written in a formula is `good`. A formula that replaces a
   value with a constant, `when(ok, x, 20)`, gives a `good` 20: the author
   said so. A fallback (section 7.10) is the way to say it with doubt.

### 7.2 Inputs from outside

An input declares its type, a **maximum age**, and optionally a unit, an
initial value and how far **ahead** it may be stamped. The maximum age is
required: a length of time, or `none`. `max_ahead` is one period unless
given.

At a tick whose time is `t`, an input is the first of these that applies.
"What stands" is the latest write the engine has taken up (rule 6.6).

1. If nothing stands:
   - `uncertain`, with its declared initial value and no sample time, if
     it declares one and the graph has run for no more than the maximum
     age;
   - otherwise `not_ready`, until the graph has run for more than the
     maximum age, and `bad` from then on.

   The graph has run for `t` less the time of tick 0.
2. `not_ready` or `bad`, if that is the state that stands.
3. `bad`, if the value that stands is not finite.
4. `bad`, if what stands was **refused**. It is refused at the tick that
   takes it up if its sample time is more than `max_ahead` after that
   tick's time, and it stays refused until something else is written.
5. `bad`, if its age, `t` less its sample time, is more than the maximum
   age.
6. `uncertain` or `good`, as it stands, with that value and sample time.

A value written and not written again stands, and grows older. A write of
`not_ready` or of `bad` does not grow old. A sample stamped ahead by no
more than `max_ahead` has an age below zero, which is not more than any
maximum.

### 7.3 Windows

A window's memory is the samples it holds. A sample leaves after `n` ticks,
and its doubt with it.

1. **A window is the usable samples of its last `n` ticks**, where `n` is
   its `window` setting in periods. Its statistics are of those samples and
   no others.
2. A window has a setting, `min_good`: the fraction of its `n` ticks that
   must hold a usable sample. It is 1 unless given. The number of samples
   needed is `min_good × n` rounded up to a whole number (rule 6.2), and
   at least 1.
3. When a window holds fewer usable samples than that, every output but
   `count` takes the worst state among its ticks that hold none. A tick
   from before the graph started, or from before a gap, holds none and
   counts as `not_ready`.
4. Otherwise its outputs are `good` if every one of its `n` ticks holds a
   `good` sample, and `uncertain` if not.
5. A slope needs two usable samples. With one it is `bad`, while the other
   statistics are as rule 4 says.
6. `count`, the number of usable samples the window holds, is always `good`.
7. With `only_new: true` a tick holds a sample only if the input is usable
   and its sample time is later than that of the last sample the window
   took. A value still standing from an earlier tick is not another sample,
   and neither is one with no sample time. A tick that holds none for that
   reason counts as `not_ready` in rule 3. Rule 4 then reads: `good` if
   every sample it holds is `good` and `n` ticks have run since the graph
   started or since a gap, and `uncertain` if not.

A window fed a value that has stopped being written reports no spread and
no slope, and reports them as `good`, until the input's maximum age ends
it. `only_new` is for the window that must not.

### 7.4 Blocks that hold a value

**Deadband.** Its memory is the one sample it holds.

1. The first usable input is taken as it is. After that the block keeps the
   sample it holds until the input has moved by `step` or more from it, and
   then takes the input.
2. With a usable input, its output is the value it holds. It is `good` if
   the sample it holds and the input are both `good`. Otherwise it is
   `uncertain`, with the later of their causes: the choice to keep or to
   take rested on that input.
3. With an unusable input, its output is the held value, `uncertain`, if
   the last usable input was no more than `ride_through` ago. On the `m`-th
   unusable tick in a row the last usable input was `m` periods ago.
4. Past `ride_through` it forgets what it held. Its output takes the input's
   state, and the next usable input is a first input.

**Low-pass.** Its memory fades, with time constant `tau`.

<!-- markdownlint-disable MD029 -- the rules of 7.4 keep one numbering -->
5. The first usable input sets `y = x`. After that, on a usable input,
   `y = aᵐ·y + (1 - aᵐ)·x`, where `a = exp(-period / tau)` and `m` is the
   number of ticks since its last usable input. `m` is 1 unless it has
   ridden through unusable ticks; the ticks it missed decay too.
6. With an unusable input, rules 3 and 4 apply to it as to a deadband.
7. It keeps the tick of its latest **doubt**: the latest of the cause of
   any uncertain input it has taken, and the tick of any usable input it
   took with `m` above 1. A first input clears any earlier doubt before its
   own is counted.
8. With a usable input its output is `uncertain`, with the doubt as its
   cause, for `settle` ticks from the doubt: while the tick's number less
   the doubt is less than `settle`. Otherwise it is `good`. `settle` is
   three time constants, rounded up to whole ticks, unless given.
<!-- markdownlint-enable MD029 -->

### 7.5 Hysteresis

Its memory is which way it last switched.

1. It goes true when its input is at or above `rise`, and false when its
   input is at or below `fall`. Between the two it stays as it was. It
   starts as its `initial` setting says, or undecided if there is none.
2. With an unusable input it stays as it was, its output takes the input's
   state, and it is no longer **sure**: a crossing may have gone by.
3. With a usable input at or beyond a threshold, it switches, and it is
   sure if that input is `good` and not sure if it is `uncertain`.
4. With a usable input its output is `not_ready` while it is undecided.
   Otherwise it is `good` if it is sure and the input is `good`, and
   `uncertain` if not.

It starts sure. So after a stretch without its input, its output is
`uncertain` until a `good` input next reaches a threshold.

### 7.6 Timers and latches

Each takes a boolean.

1. **Held for.** True when its input has been true for longer than `time`.
   The tick on which the input becomes true counts as no time at all. Its
   memory is the run of true inputs, and ends with the run. A usable input
   that is false stops the timer, and the output is false, with the input's
   state. While the timer runs on usable inputs, the output is `good` if
   every input since it started was `good`, and `uncertain` if not.
   Required `on_bad`:
   - `reset`: an unusable input stops the timer, and the output takes the
     input's state.
   - `hold`: an unusable input leaves the timer running, for at most
     `hold_limit`, a required setting. While it runs the output is
     `uncertain`, and true once the time has run out. When the unusable
     stretch grows longer than the limit, or if the timer was not running,
     the timer stops and the output takes the input's state. The stretch
     at its `m`-th unusable tick in a row is `m` periods long.
2. **Since true.** True when its input has not been true for longer than
   `time`. Its clock starts at the first tick and restarts on every tick
   where the input is usable and true. Its memory is the ticks since its
   clock was set, or the last `time` of them if that is fewer.
   - Its output is true when the tick's number less the clock's is more
     than `time`, counted in ticks.
   - It keeps the latest tick at which its input was not `good`. Its output
     is `good` if there is no such tick at or after the later of the clock
     and the tick `time` ticks back, and `uncertain` otherwise.
   - Required `on_bad`. With `assume_false` an unusable input counts as not
     true, and the two rules above give the output. With `unknown` the
     output takes the input's state on a tick where the input is unusable.
3. **Latch.** False until its input `set` is first usable and true, then
   true. It has an input `reset` that need not be connected. Its memory is
   whether it is set, and whether it is **sure** of that. It starts not
   set, and sure. At each tick, the first of these that applies:
   - `reset` is usable and true: it is cleared, and it is sure if `reset`
     is `good` and not sure if it is `uncertain`. This wins over `set`.
   - `set` is usable and true: it is set. If it was not set, or if `set`
     is `good`, it is sure if `set` is `good` and not sure if it is
     `uncertain`.
   - it is not set and `set` is not `good`: it is no longer sure. A true
     may have gone by.

   Set, its output is true: `good` if sure, `uncertain` if not. Not set,
   its output takes the state of `set` if that is unusable; otherwise it is
   false, `good` if sure and `uncertain` if not.

### 7.7 Integrators

Its memory does not fade. A doubt is weighed against how long it has run.

1. An integrator adds its input, times the period, on every tick where the
   input is usable. The value at a tick includes that tick's addition, so a
   constant 1 from tick 0 gives `k + 1` periods at tick `k`.
2. `missed` is the time it has not integrated: the period, added up over
   every tick where the input was unusable. It is always `good`.
3. It counts, since its last reset: the ticks it has run, the ticks it
   missed, and the ticks on which it added an `uncertain` input. The total
   is `uncertain` when the missed and the uncertain ticks together are more
   than `tolerance` times the ticks it has run, and `good` otherwise.
   `tolerance` is 0 unless given.
4. With `max_missed` set, the total is `bad` once `missed` is more than
   that, until a reset.
5. It has an input `reset` that need not be connected. A usable, true
   `reset` returns the total, `missed` and every count to zero before that
   tick's addition. An unusable `reset` does nothing.

### 7.8 Models

A model block hosts a model (rule 4.9). Its memory is the model's state.

1. **The value at a tick is the state at that tick.** At tick `k` the
   block's outputs are the model's outputs for its state at tick `k`, and
   tick 0 gives the initial state. In the second phase the state is stepped
   one period, from the inputs of tick `k`, to give the state at tick
   `k + 1`. 1.x gave the stepped state on the same tick; every 1.x response
   is therefore one tick later here, and matches the time it is labelled
   with.
2. An input is direct if the model's outputs read it, and deferred if only
   its step does. A model whose outputs are its state has no direct input.
3. With every input usable the model steps.
4. With an input unusable, the model steps on that input's last usable
   value if that was no more than `ride_through` ago, counted as in rule
   7.4.3. Otherwise it does not step.
5. **A model never gives up its state.** Its outputs are always usable,
   unless rule 3.6 makes one `bad`.
   Where its outputs read a direct input that is unusable, they are worked
   out on that input's last usable value, or on zero if it has had none,
   and are `uncertain`. Where they read a direct input that is `uncertain`,
   they are `uncertain` with its cause. Otherwise rule 6 gives their state.
6. It keeps the tick of its latest **doubt**: the latest of the cause of
   any uncertain input it has stepped on, and any tick at which it stepped
   on a held value or did not step. Its outputs are `uncertain`, with the
   doubt as their cause, for `settle` ticks from the doubt, as in rule
   7.4.8, and `good` otherwise. A doubt from the second phase of tick `k`
   is tick `k`, and first shows in the outputs of tick `k + 1`. `settle` is three of the model's slowest
   time constant, rounded up to whole ticks, unless given. A model whose
   memory does not fade has no such constant: with no `settle` given, a
   doubt lasts for the rest of the run.
7. A model says the longest step it is stable at. A graph whose period,
   divided by the block's `substeps` setting, is longer than that is
   refused. With `substeps` of `n` the state is stepped `n` times per tick,
   each of one `n`-th of a period, on the same inputs.

So two thermal masses that each take the other's temperature are two
blocks with deferred inputs, and compile. One bad sample to one of them
makes it miss a step and both `uncertain` for a while. Neither goes `bad`,
and neither waits for the other.

**Open.**

- **Stability of blocks together.** Rule 7 is per block. Two blocks that
  are each stable at a period can be unstable coupled. Settled by: whether
  the compiler can bound it, or whether it is the author's to check.
- **Which integration each model uses.** 1.x offers forward Euler and
  fourth-order Runge-Kutta per model. The two examples in Appendix A fix
  one each. Settled by: going through the 1.x models against their
  analytical validation.

### 7.9 The estimator

An estimator hosts a model as its predictor and corrects it from
measurements. It is an extended Kalman filter with one restriction: each
measurement reads one state.

1. It starts from the model's initial state, with the variance its `p0`
   gives each state and no covariance between states, and gives outputs
   from tick 0.
2. **Predict.** On every tick after tick 0 it steps the model one period,
   from the tick before to this one, and the covariance with it:
   `P = F·P·Fᵀ`, plus `q` times the period on each state's own variance.
   `F` is the model's sensitivity over the period, at the state before the
   step. The step is on the model inputs **as they were at the tick
   before**, as a model block's is (rule 7.8.1): for each, its value then,
   or if it was unusable then, the last usable value it had had. If some
   model input had never been usable by then, it does not step the model on
   this tick: the state stays, and each state's variance still grows by
   `q` times the period.
3. **Correct.** Then, on every tick, for each measurement in the order they
   are declared: it is **considered** if it is `good` and its sample time
   is later than the sample time last considered on that port. A
   measurement with no sample time is never considered. With
   `use_uncertain: true` an `uncertain` measurement is considered too.
4. A considered measurement of state `i`, with variance `r`, has the
   innovation `z - xᵢ` and the spread `s = Pᵢᵢ + r`. If `gate` is given and
   the innovation is more than `gate` times the square root of `s` either
   way, it is **refused**: counted, and nothing changes. Otherwise it is
   **used**: with `g` the `i`-th column of `P` over `s`, `x = x + g·(z -
   xᵢ)` and `P = P - g·(row i of P)`.
5. A state's outputs are `uncertain` on a tick where any model input is
   unusable at that tick, or where the state's sigma is more than its `sigma_max`, if
   one is given. Otherwise they are `good`. The covariance is the
   estimator's own account of its memory, and stands in for a doubt.
6. Outputs, each a number:
   - one per state, by the state's name, and `sigma_<state>`, the square
     root of its variance;
   - `innovation_<port>`: on a tick where the measurement was considered,
     its innovation, `good`; on any other tick `not_ready`;
   - `refused_<port>`: how many have been refused, `good`;
   - `since_<port>`: the time from the sample time of the measurement last
     used to the tick, `good`; `not_ready` until one has been used.

An estimator with a stable model and little process noise stays confident
through a long stretch without measurements, and is right to if the model
is right. `since_<port>` is there for the graph that wants to act on the
stretch itself.

**Open.**

- **A measurement that reads more than one state**, and model inputs with
  noise of their own. Both need matrix settings and neither needs a vector
  signal. Settled by: the first graph that needs one.

### 7.10 Fallbacks

A block may name, for any of its outputs, a value to give when that output
is not usable. The substituted value is `uncertain`, and its cause is the
tick. Each applies to the output it names and to no other. Every reader of
that output sees the substituted value, inside the graph as well as outside
it. An output made `bad` by rule 3.6 is replaced like any other.

**Open.**

- **Whether a consumer needs to know why a value is `uncertain` or `bad`.**
  Settled by: what each consumer in Anolis would do differently if it could
  tell.

## 8. Reset, save, restore and gaps

**Proposed.**

1. A graph can be reset to its initial state. After a reset the next call
   runs tick 0 again, at whatever `now` it is given, and nothing stands on
   any input.
2. A graph can write its state out and take it back, so that a host can
   save a running graph and restore it. A state saved from one graph is
   refused by a graph that is not the same.
3. A **gap** is time the graph did not see: a restore, or a call that would
   run more than `max_catch_up` ticks. After a restore the next call is a
   gap whatever its `now`, and may carry any `now`. Restoring a state saved
   before any tick had run is a reset, and not a gap.
4. At a gap one tick runs. Its number is one more than the last tick's, its
   time is the call's `now`, and later ticks are at whole periods from it.
   Before it runs:
   - nothing stands on any input any longer. After a restore, what had
     been written before it and not yet taken up is dropped too. What the
     host wrote since the last tick, or since the restore, is taken up as
     usual. For rule 7.2.1 the graph has run since the gap's tick;
   - every block is told, and does what this table says.

| Block | At a gap |
| --- | --- |
| `formula`, `all_good` | Nothing: no memory |
| `delay` | Every `good` value it has taken in and not yet given becomes `uncertain`, with the gap's tick as its cause. An initial value it has yet to give is not changed |
| `window` | Emptied; the ticks before the gap hold no sample |
| `deadband`, `lowpass` | Forgets what it held; the next usable input is a first input |
| `hysteresis` | Stays as it was, and is no longer sure |
| `held_for` | The timer stops |
| `since_true` | The clock is set to the gap's tick, and the gap's tick counts as one where the input was not `good`, whatever the input then is |
| `latch` | If not set, no longer sure. If set, unchanged |
| `integrate` | The total is `uncertain` until its next reset |
| Model block | The gap's tick is a doubt (rule 7.8.6) |
| `estimator` | Each state's variance grows by its `p0` |

Nothing else changes at a gap. A window with `only_new` keeps the sample
time it last took, an estimator keeps its state, its counts and the sample
times it last considered and used, and a model keeps the last usable value
of each input.

**Open.** What "the same graph" means: the same text, or the same blocks,
settings and period, and in either case the same layout of state in the
library that wrote it.

## 9. The graph file

**Proposed.** The shape, not the final keys:

```yaml
period: 2.5s
max_catch_up: 100

inputs:
  heater/pad_c: { type: number, unit: degC, max_age: 10s }
  heater/relay: { type: boolean, max_age: 10s }
  room/ambient_c: { type: number, unit: degC, max_age: none, initial: 20 }

blocks:
  - id: pad
    type: window
    in: { x: heater/pad_c }
    settings: { window: 7.5s }
    out: { median: heater/pad_filtered_c }
```

1. `inputs` lists every signal written from outside, with its type, its
   maximum age and, where it has them, its unit, `max_ahead` and initial
   value. A type left out is `number`. A graph that reads a signal which is
   neither an input nor a block's output is refused.
2. A block's `in` maps each input port to a signal, named as text, or to a
   constant. Its `out` maps output ports to signal names, which are text; a
   port left out is not published, and any output, published or not, can be
   read by another block as `<block id>.<port>`. A block id is text. No
   input and no published signal may have a name of the form
   `<block id>.<port>` for a block and port of the graph.
3. A length of time is written as a number and a unit with nothing between
   them: `ms`, `s`, `m` or `h`. The number is digits, with an optional
   point and more digits. A number without a unit is refused.
4. A setting that is a whole number is written without a point: `2`, not
   `2.0`.
5. These are compile errors: an unknown key, at the top of the graph or in
   a block or an input; an unknown block type; a block with no id, or with
   another block's id; an unknown port in `in`, `out` or `fallback`; a
   required input left unconnected; a signal connected to a port of the
   other type; an unknown setting; a setting of the wrong type or out of
   range; a missing required setting; an input with no maximum age; a
   counted length of time that is not a whole number of periods; and a
   signal with two writers. 1.x ignores an unknown top-level key.
6. A graph with several faults is refused for one of them. Which one, and
   the wording, are not specified. The refusal names the thing at fault.
7. What a name or a value is, is judged after the file is read. A reader
   that takes `on` for `true` will see a boolean where a name was meant,
   and the graph is then refused by rule 2.

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
4. A second implementation, written from this document as it stands and
   nothing else, passes the same vectors.
5. Values are compared to within one part in 10⁹. Where a rule turns on
   exact equality, a vector uses values that are exact in binary.
6. The two implementations are also run side by side on random inputs and
   call times, at a period that is exact in binary and at one that is not,
   with saves, restores and resets among the calls.

`conformance/` holds the vectors, two readings of this proposal, and the
checks that run them.

## 12. What happens to 1.x

| 1.x | 2.0 |
| --- | --- |
| `IModel` | A model, hosted by a block or by an estimator |
| `ITransform` | A block |
| Edges | Gone; a signal is named as an input |
| `tick(dt)` | `tick(now)`; the period is fixed at compile |
| Models run first, then edges | One sorted order, two phases |
| A model's output is its state after the step | Its state at the tick (rule 7.8.1) |
| Signal: a number and a unit | A typed value, a state, a sample time |
| Unwritten signal reads 0.0 | Unwritten signal is `not_ready`, unless its input declares an initial value |
| Stability limit checked per model | Kept, per block, with sub-steps (rule 7.8.7) |
| Rules and commands | Open (section 4) |
| Unknown keys ignored by the loaders | Refused |
| Thermal, process, mechanical and motor models | Kept as models |
| The transforms | Kept as block types |
| Delay in seconds | Delay in ticks; lengths of time are whole periods |
| Noise from the standard library's generator | A generator this document will have to name, so that a vector can cover it |
| Units, namespace, loaders, diagram tool | Kept, adapted to ports |
| The server protocol | Changes with the above |

## 13. Order of work

1. This document is argued to agreement, section by section.
2. The core is rebuilt against the conformance vectors: store, compiler,
   engine, block and model interfaces.
3. The existing models move across as models, each keeping its analytical
   validation, and the transforms as block types.
4. The loaders, the server and the simulator provider follow.

## Appendix A. A first catalogue

**Proposed.** Enough block types to test the rules above and to be useful.
Names, ports and settings are placeholders for argument; the behaviour is
what the vectors pin down.

| Type | Inputs | Settings | Outputs |
| --- | --- | --- | --- |
| `formula` | any, named in the formula | `expr`, `sample_of` (none) | `y` |
| `all_good` | any | none | `y`: boolean |
| `delay` | `x`, deferred | `ticks` (1), `initial` (none) | `y` |
| `window` | `x`: number | `window`, `min_good` (1), `only_new` (false) | `mean`, `median`, `min`, `max`, `spread`, `slope`, `count` |
| `deadband` | `x`: number | `step`, `ride_through` (0) | `y` |
| `lowpass` | `x`: number | `tau`, `ride_through` (0), `settle` (three `tau`) | `y` |
| `hysteresis` | `x`: number | `rise`, `fall`, `initial` (none) | `y`: boolean |
| `held_for` | `x`: boolean | `time`, `on_bad`, `hold_limit` | `y`: boolean |
| `since_true` | `x`: boolean | `time`, `on_bad` | `y`: boolean |
| `latch` | `set`: boolean; `reset`: boolean, optional | none | `y`: boolean |
| `integrate` | `x`: number; `reset`: boolean, optional | `per` (1 s), `max_missed` (none), `tolerance` (0) | `y`, `missed` |
| `thermal_mass` | `power`, `ambient`: number, deferred | `thermal_mass`, `heat_transfer`, `initial`, and the model settings | `temp` |
| `state_space` | `u`: number | `A`, `B`, `C`, `D` (0), `initial` (zeros), and the model settings | `y` |
| `estimator` | the model's inputs, and one per measurement | `model`, `q`, `p0`, `measure`, `gate` (none), `sigma_max` (none), `use_uncertain` (false), `substeps` (1) | see 7.9.6 |

A setting with a value in brackets may be left out and takes that value.
`settle` is written as a length of time, like any other counted length. An
input is required and direct unless the table or the block's rule says
otherwise. An output is a number unless the table says otherwise. `formula`
and `all_good` take one or more inputs under any names. The **model
settings** are `ride_through` (0), `settle` (rule 7.8.6) and `substeps` (1).

Ranges, outside which a graph is refused: `ticks` and `substeps` a whole
number, at least 1; `window` at least one period; `min_good` more than 0 and
at most 1; `step`, `ride_through`, `settle`, `time`, `hold_limit`,
`max_missed`, `tolerance`, `q` and `gate` not negative; `per`, `tau`,
`thermal_mass`, `heat_transfer`, `p0` and `r` more than zero; `rise` more
than `fall`; every number, `initial` and fallback finite; `on_bad` one of
the choices its block gives. `hold_limit` is required with `on_bad: hold`
and refused without it.

- **`formula`.** Section 7.1 governs states.
  - **Numbers:** digits, an optional point and more digits, an optional
    exponent (`e` or `E`, an optional sign, digits). Nothing else: no sign
    of its own, no hexadecimal, no separators. A number too large for a
    double is refused.
  - **Booleans:** `true` and `false`.
  - **Names:** a letter or underscore, then letters, digits and underscores,
    all ASCII. `and`, `or`, `not`, `true`, `false` and the function names
    are not input names.
  - **Operators**, from loosest to tightest: `or`; `and`; `not`; the
    comparisons `< <= > >= == !=`; `+` and `-`; `*` and `/`; unary minus.
    Operators of one level group from the left. Brackets group. Comparisons
    do not chain: `a < b < c` is refused. As a grammar:

    ```text
    or      = and { "or" and }
    and     = not { "and" not }
    not     = "not" not | compare
    compare = sum [ ("<" | "<=" | ">" | ">=" | "==" | "!=") sum ]
    sum     = product { ("+" | "-") product }
    product = unary { ("*" | "/") unary }
    unary   = "-" unary | primary
    primary = number | "true" | "false" | name | "(" or ")"
            | function "(" or { "," or } ")"
    ```

  - **Functions:** `abs(a)`, `min(a, b)`, `max(a, b)`, `exp(a)`, `ln(a)`,
    `sqrt(a)`, `pow(a, b)` and `when(condition, a, b)`. `pow` is C's.
  - **Types:** arithmetic and the functions take numbers and give a number.
    `< <= > >=` take numbers and give a boolean. `==` and `!=` take two of
    one type and give a boolean. `and`, `or` and `not` take booleans and
    give a boolean. `when` takes a boolean and two of one type, and gives
    that type. Anything else is refused. The type of `y` is the type of the
    formula.
  - A name the formula uses must be one of the block's inputs, and every
    input of the block must be used by the formula. Either fault is refused.
  - Spaces and tabs between tokens mean nothing. A formula is one line, and
    not empty.
  - `sample_of` names one of the block's inputs that is a signal (rule
    3.7). With more than one signal input and no `sample_of`, and with no
    signal input at all, `y` carries the time of the tick.
- **`all_good`.** True when every input is `good`, else false. Always
  `good`.
- **`delay`.** At tick `k` its output is its input at tick `k - ticks`:
  value, state, sample time and cause, as a reader of that input saw them
  then. Before that tick exists, its output is `initial` and `good`, with
  no sample time, or `not_ready` if no initial value is given. Its type is
  its input's, and an initial value of the other type is refused. An
  initial value is `good` because it is the author's statement of where a
  loop starts, where an input's initial value stands in for a measurement.
- **`window`.** `window` is `n` periods. At a tick the window is that tick
  and the `n - 1` before it. `median` of an even number of samples is the
  mean of the middle two. `spread` is `max - min`. `slope` is the
  least-squares slope of value against time, per second, taking the oldest
  tick of the window as time zero. Section 7.3 governs states.
- **`deadband`.** The comparison with `step` is exact. Section 7.4.
- **`lowpass`.** Section 7.4.
- **`hysteresis`.** Section 7.5.
- **`held_for`.** Section 7.6 rule 1. With `time` of `n` periods, the output
  is true on a tick when the timer started more than `n` ticks before it:
  from the `n + 1`-th tick after the one the input became true on.
- **`since_true`.** Section 7.6 rule 2.
- **`latch`.** Section 7.6 rule 3.
- **`integrate`.** Section 7.7. On a usable tick it adds `x × period / per`.
  `missed` is in seconds.
- **`thermal_mass`.** One state, `temp`, starting at `initial`.
  `d temp / dt = (power - heat_transfer × (temp - ambient)) / thermal_mass`,
  stepped by the classical fourth-order Runge-Kutta rule with its inputs
  held over the step. Its slowest time constant is `thermal_mass /
  heat_transfer`, and the longest step it is stable at is 2.785 of them.
  Its output is its state, so both inputs are deferred. Its sensitivity
  over a step of length `d` is `1 + z + z²/2 + z³/6 + z⁴/24`, with
  `z = -d × heat_transfer / thermal_mass`; over a period of several
  sub-steps, that to the power of their number.
- **`state_space`.** Discrete, one input and one output. `A` is a list of
  `n` rows of `n` numbers, `B` and `C` lists of `n`. Its step is
  `x = A·x + B·u` and its output `y = C·x + D·u`. `u` is direct when `D` is
  not zero and deferred when it is. Its states are named `x0`, `x1` and so
  on, in the order of `B`. It has no slowest time constant and is stable at
  any step, and `substeps` does not apply to it. Its sensitivity is `A`.
- **`estimator`.** Section 7.9.
  - `model` is a map with `type`, a model's type, and that model's own
    settings (not the model settings above).
  - `q` and `p0` are maps from each state's name to a number: `q` a
    variance per second, `p0` a variance.
  - `measure` maps each measurement port to `of`, a state's name, and `r`,
    a variance. Its order is the order of rule 7.9.3.
  - `sigma_max` maps states' names to numbers. A state left out has none.
  - Its inputs are all direct.

A block may carry `fallback`, a map from an output port to a constant of
that port's type (section 7.10).

**Open.** The catalogue is short of what a first real graph needs: a clamp,
a rate limit, a derivative, an edge detector, an off-delay, a moving sum, a
lookup, a selector, a difference of a device's counter, a PID and a
second-order section. None can be put together from the blocks above
without a loop through a delay, and a formula cannot read the period. Each
is a block with `output` and `update` and scalar settings, and none needs a
rule this document does not have. Settled by: writing them, each with its
vectors.

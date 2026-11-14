# FluxGraph semantics, version 2 (proposal)

**Status:** proposal, third revision, with eight amendments. Not in force.
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
  taint on memory with a stated end (section 7). This revision first gave
  an uncertain value the tick of what caused it; the second amendment
  takes that out, and gives a loop a doubt of its own (rule 7.8.8).
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

The third revision was reviewed in its turn, and was found sound in its
structure and wrong in particular rules. It is being amended a section at a
time. **Amendments so far:**

1. *Time and the host interface* (sections 6, 7.2 and 8). Times are whole
   nanoseconds, so that no comparison of times needs a tolerance. Every
   write carries a time. What stands on an input is the write with the
   latest time among those a tick may see, and a tick the host did not call
   for may see only what had been sampled by its own time. A call says
   whether it was a gap. A restore, or a clock that has stepped, forgets
   every remembered time.

2. *Doubt through memory* (sections 3 and 7, and the table of section 8).
   An `uncertain` value no longer carries the tick of its cause. A block is
   never `good` on a tick where a value it used is `uncertain`; a block
   with declared, finite memory is `uncertain` for that long after it took
   in something doubtful; a window's tolerance covers an uncertain sample
   as it covers a missing one; a block whose memory has no end takes its
   state from what it reads now and gives counters a graph can test; and a feedback loop
   that holds a model is treated as one block. What that gives up is listed
   at the end of section 7.

3. *Gaps* (section 8, and rules 6.9 and 6.10). A gap is ticks nobody saw,
   and a block is told how many. The tick a stall runs keeps its own
   number, and each block does to what it remembers what that many ticks
   with nothing usable to read would have done: a total adds them to what
   it has missed, a counter to what was doubtful, a window holds no sample
   for them, a delay moves on. A host that knows how long a restored graph
   was away says so. Where nobody knows, the gap is longer than anything a
   block counts.

4. *Models* (rule 4.9, section 7.8 and Appendix A). Every model is
   linear, and is stepped exactly: its step over a period is the solution
   of its equation with its inputs held, worked out when the graph is
   compiled. There is no step a model is unstable at, and no sub-steps.
   One general block, `linear`, takes the matrices of any linear model,
   and the six models 1.x has in continuous time are each a named case of
   it. A loop holds one model block and no more: two that read each other
   are a tick apart, which can make a sound network unstable, and are
   written as one.

5. *The estimator* (section 7.9). Its process noise is discretised
   exactly, as its model is, and its model inputs are deferred. A
   measurement is of any output of the model that reads no input
   directly. A refused measurement makes
   its tick `uncertain`, and a run of them longer than the author allows
   widens the variance and takes the next: a gate can no longer lock an
   estimator out. Its author states a test of whether its innovations are
   as large as it expects, or says there is none. An `uncertain`
   measurement is used with a variance of its own, and makes its tick
   `uncertain`, or is not used at all. At a gap of known length it
   predicts across it.

6. *The whole text, read cold* (throughout). An input's `initial` stands
   in until the first rebase and not after it, and after a rebase a host
   writes again only the inputs that have no maximum age: an old sample
   is not made new. Rounding up to whole ticks is exact and has no
   tolerance, but for a named model's `settle`. Every time and length
   fits in 64 bits, and a call that would take a tick past that is
   refused. A block id and the names a block is given hold no dot, and an
   estimator's outputs have a name each. A model block's outputs are
   judged together. The summaries that had drifted from the rules they
   summarise are put right, and section 7.11 lists more of what is given
   up.

7. *A rate limit and a PID* (sections 7.4 and 7.7, the table of section
   8, and Appendix A). A controller written as a formula and a delay
   stopped for good at its first gap. A `rate_limit` holds its last output
   and moves it towards its input by no more than a stated rate. A `pid`
   reads a setpoint and a measurement: its derivative is of the
   measurement, through a filter; its integral stops going into an output
   limit and still comes out of it; and with an input it cannot use it
   gives no value, keeps its integral, and starts its derivative again. It
   may be told what was applied to the actuator, so that a limit after it
   does not wind its integral up. A clamp is a formula, and gets no block.

8. *What building it in C++ asked* (rules 6.11, 7.3.8 and Appendix A). A
   first slice of the core was written in C++ from this text, and agreed
   with every vector it could run. It asked for what a reading in whole
   numbers of any size never has to: what a call does once the last tick
   number has been run, and that a call is refused whole if any tick it
   would run does not fit. It also wanted the order of an `integrate`'s
   arithmetic, a delay's type on a loop, what a `bad` input is to a window
   that takes only new samples, and how deep a formula may nest. The
   second slice asked for the order of a PID's sum, which three
   implementations had taken three ways, and how a low-pass raises its
   decay to a power.

Nothing is left on the list of what is known to be wrong as it stands.
What each amendment gives up is at the end of section 7, and for time
and the host at the end of section 6; what is still open is under each
section.

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
compatibility. The maths of the existing models carries over, a tick later
(rule 7.8.1) and stepped exactly (rule 7.8.7). Section 12 says what becomes
of each transform.

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
   whatever the block. The block's state is not put right for it. An
   output whose working passes through a value that is not finite may be
   `bad` though its true value is finite, as the mean of two samples of
   10³⁰⁸ is: a statistic is worked as a plain sum in double arithmetic.
7. A signal may carry a **sample time**: the time, on the host's clock,
   that its value was taken.
   - An input from outside carries the time it was written with.
   - A `formula` output carries the sample time of the input its
     `sample_of` setting names. A formula with exactly one signal input
     and no `sample_of` carries that input's. Inputs are counted by port:
     one signal connected to two ports is two.
   - A `delay` output carries the sample time of what it gives.
   - Every other block output carries the time of the tick.
   - A signal that is not usable carries none, and neither does a value a
     fallback puts in (section 7.10), whatever the block: it is not a
     sample of anything.

   A block that must not use one sample twice remembers the sample time it
   last used, and uses a value only when its sample time is later. There is
   no other notion of a sample being new.

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
   over one period given its inputs, and a rule that gives its outputs
   from its state and inputs. Both rules are linear (rule 7.8.7), so the
   **sensitivity** of the stepped state to the state it was stepped from
   is the step's own matrix. A block hosts a model (section 7.8), and so
   does an estimator (section 7.9). A 1.x model becomes a model in this
   sense.

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
6. A loop that holds no model, a formula and a delay say, has no memory
   that fades. One unusable value in it stays in it, and so does one
   uncertain value. This is true of what such a loop computes and is not
   put right by any rule. A running total and a filter each have a block
   with a rule for it, and a loop that holds a model has rule 7.8.8.

## 6. Time and the host

**Proposed.** A fixed timestep. The host says what time it is; the engine
runs as many ticks of one fixed length as fit. A tick the host did not call
for reads its inputs as they stood at its own time, and the tick it did
call for reads what the host has in hand.

1. A graph has one **period**, more than zero and fixed when it is
   compiled. Every block runs once per tick.
2. **A time is a whole number of nanoseconds.** That is so for the clock
   the host passes, for the time a write carries, and for every length of
   time the engine keeps: the period, a counted length, a maximum age and
   `max_ahead`. One of those that is not a whole number of nanoseconds, or
   does not fit in 64 bits, signed, is refused. No comparison of times has
   a tolerance, because none needs one. A sum or a difference of times is
   the true one: an age is how far apart two times are, however far that
   is, and an engine whose whole numbers are 64 bits wide sees that none
   wraps.
3. Every length of time a block counts (a window, a timer, a limit) is a
   whole number of periods, and a graph where one is not is refused. Inside
   a block, time is counted in ticks. Where a rule rounds a number of ticks
   or of samples up to a whole number, the number is worked exactly from
   what the graph file gives, and there is no tolerance: a `min_good` of
   0.7 over ten ticks needs seven, and one of 0.7000000001 needs eight. A
   decimal is read as a double and then taken as the shortest decimal
   that reads back as that double, so one written with more digits than a
   double keeps is the nearest it does keep. A named model's
   `settle` is the one number that is not exact, and rule 7.8.6 says how
   it is rounded. An input's maximum age is not counted, and may
   be any whole number of nanoseconds. A setting that only scales a value
   (`tau`, `per`) is not a time the engine keeps: it is written as a length
   and may be any length at all.
4. The host passes the time to every call: `tick(now)`. The clock is the
   host's, and it does not go backwards. It should be one that does not
   step: the engine cannot tell a step from a stall. `now` is read after
   the last sample the host means the call to see, since a sample stamped
   after `now` waits for the next tick.
5. The first call runs tick 0, and the time of tick 0 is that `now`. Until
   a rebase, tick `k` is `k` periods after tick 0. A stall (section 8)
   passes over ticks, which keep their numbers and their times and are
   never run. A rebase puts the tick it runs at the call's `now`, on the
   clock the host then passes, and later ticks at whole periods from it.
6. A call runs, in order, every tick not yet run whose time is no more than
   half a period after `now`. A tick exactly half a period after is run. If
   none is due the call runs no tick, says so, and gives nothing else. The
   first call after a rebase is the exception: it always runs one tick
   (rule 8.5).
7. **Writes.** The host writes an input at any moment: a state, a value if
   the state is usable, and a **time**. For a usable value the time is when
   it was sampled. For `bad` or `not_ready` it is when that became so: when
   the read failed. Every write carries one. A time may be any whole
   number that fits in 64 bits, signed.
8. **Which writes a tick may see.** A write waits until a tick may see it.
   - The **last** tick a call runs may see every write whose time is not
     after the later of that tick's time and the call's `now`. A sample
     the host has in hand when it calls is seen by that call.
   - A tick before the last, a **catch-up** tick, may see a write whose
     time is not after the tick's own.

   **What stands.** At a tick, for each input, the engine takes the writes
   waiting that the tick may see. They are done with. Among them, and what
   stood before, the one with the latest time stands from this tick on. Of
   two with the same time, the one written later stands. A write with an
   earlier time than what stands never stands.

   **Stamped ahead.** An input has a setting, `max_ahead`, one period
   unless given and not less than half a period. At every call that is not
   refused, before any tick runs and whether or not one does, a waiting
   write whose time is more than `max_ahead` after `now` is **thrown
   away**: it is done with, and never stands. That is so for a write of
   `bad` or `not_ready` as for any other, and at the call after a rebase as
   at any other.

   **Thrown away at the write.** A write whose time is earlier than that of
   what stands can never stand, and is thrown away as it is made.

   **How many may wait.** A graph has a setting, `max_waiting`, 1024 unless
   given and at least 1: the most writes that may wait on one input. When
   one more is written, the one with the earliest time among those waiting
   and the new one is thrown away, the earlier written of two with the
   same time. This is a limit on memory and not a choice of what matters:
   the earliest is the one due soonest. A host does not reach it unless it
   writes that many times between two calls.

   A write is judged against what stands as it is made, and against
   nothing else. The count of writes thrown away (rule 10) is of these
   three ways and no other; a reset sets it to zero, and a restore or a
   rebase does not.

   So:
   - a host a little early or a little late sees, at each call, the sample
     it has just taken;
   - an old sample that arrives late does not displace a newer one;
   - a sample stamped a little ahead waits for its time, and one stamped
     far ahead, by a clock that is wrong, is thrown away at the next call.

   The time a write carries is what a tick goes by, whatever its state: a
   failed read with a later time displaces a value, and a value with a
   later time displaces a failed read. A write with the same time as what
   stands and a different value stands in its place; a block that compares
   sample times (rule 3.7) does not take it for a new sample.
9. A graph has a setting, `max_catch_up`, 100 unless given and at least
   1. When a call
   would run more ticks than that, it is a **gap** (section 8): the last
   of them runs, and the rest are passed over. Catching up is for a host
   that is late by a tick or two. It runs each tick on what stood at that
   tick's time, judged by its age, and an input's maximum age is what
   keeps a long pause from being run on old values.
10. A call that ran a tick gives: the number of ticks it ran; whether it
    was a gap, and if so how many ticks it passed over, or that nobody
    knows; the number and the time of the last tick it ran; how many
    writes have been thrown away (rule 8) since the last call that ran a
    tick; how many writes still wait; and that tick's outputs. The outputs
    of the ticks before the last are not given.
11. These are refused, and change nothing:
    - a call with a `now` earlier than that of the last call that was not
      refused, whether or not that call ran a tick. One with the same `now`
      is accepted. After a reset, a restore or a rebase there is no last
      call, and the next may carry any `now`;
    - a write to a name that is not an input of the graph;
    - a usable write with no value, or one whose value is not of the
      input's type; and a write whose state is not one of the four;
    - a write or a call whose time is not a whole number, or does not fit
      in 64 bits, signed;
    - a call that would run a tick whose number or whose time does not fit
      in 64 bits, signed. It is refused whole: where a call would catch up
      over several ticks and one of them does not fit, none is run. Once
      the tick with the largest number that fits has run, every call that
      would run a tick is refused, after a rebase or a restore too, until
      a reset. A tick that is due and whose time does not fit stays due,
      and the calls refused, until a rebase or a reset;
    - a `rebase` whose length is not a whole number of nanoseconds, is
      less than zero, or does not fit in 64 bits, signed.
12. Calls and writes are made one at a time. A host with several threads
    sees to that itself.

So a host whose loop is a little slow or a little fast runs, now and then,
two ticks in a call or none. The extra tick reads what had been sampled by
its own time. Short of a stall, counted times and totals stay true to the
host's clock.

**What the host has to do** for that to hold:

- **Write every sample, with its time, as it is taken.** A tick thread that
  stalls for eight seconds while samples go on being written runs its
  catch-up ticks on those samples. A host that keeps only its latest sample
  and hands that over before the call runs them on what stood before the
  stall: the engine cannot see what it was never given.
- **Give the inputs of one scan one time, and write them before the same
  call.** A loop that reads several devices in turn has no one moment. It
  picks one, the end of the scan say, and stamps every sample of the scan
  with it; they then come to stand at the same tick. Stamped each at its
  own moment, two inputs a few milliseconds apart come to stand a tick
  apart at a catch-up tick whose time falls between the two stamps. That
  tick pairs the new sample of one with the old sample of the other, a
  block with memory acts on it, a latch on their difference say, and the
  host is not given that tick's outputs. The last tick of a call sees
  both. Nothing here lets a host commit several writes as one, beyond
  giving them one time.
- **Read `now` after sampling** (rule 4), and write each input's samples in
  the order they were taken. One with a time earlier than what stands is
  thrown away; one that is only out of order with a write still waiting
  may stand for a tick before the later one does.
- **After a gap** (section 8), look to whatever it counts on: a gap and
  its length are reported to the host, and each block that counts gives
  `gaps` and adds the ticks passed over to what it missed or doubted. A
  total or a detector that ran across one is `good`. A timer the gap
  stopped shows nothing of it once it starts again at a later tick: the
  call's report is the only word of that.
- **Say how long, after a restore.** A host that restores a state knows,
  from a clock of its own, how long the graph was away. Passed to `rebase`,
  that makes the restore a gap of that length. Without it nobody knows,
  and a total restored after a day shows one gap and nothing missed.
- **After a restore or a stepped clock, call `rebase` and then write.**
  `rebase` does away with every write waiting, and counts none of them as
  thrown away. Then write again each input that has no maximum age, with
  the time of the call to come (rule 8.5). An input with a maximum age is
  written when it is next sampled.

What this still leaves out:

- **More than one write per tick.** An input is read once per tick. Of
  several writes between two ticks, one is seen. A host that writes faster
  than the period loses the rest, and a signal that changes faster than the
  period is aliased: a relay cycling every 10 s and read every 2.5 s reports
  a duty cycle that depends on phase. An input has to be slower than the
  period, or be a count the device keeps.
- **Phase.** Ticks stay where the first call put them. A host that calls
  half a period off them runs no tick on some calls and two on others, for
  good. Nothing here moves the ticks to where the host now is, short of a
  rebase, which clears the inputs as well.
- **The limit on catching up is in ticks**, so it is a second at a period
  of 10 ms and four minutes at 2.5 s. Just under it the ticks are run on
  what stood; just over it they are passed over. For a block whose
  inputs have grown too old to use the two agree, and they differ by what
  stood until then. A block that reads only constants, or an input with no
  maximum age, would have gone on working through ticks that were run,
  and does not through ticks passed over: a model so fed steps as `good`
  through the one, and through the other steps on held values within its
  `ride_through`, or not at all, counted as `doubtful`.
- **What a catch-up tick gave.** A call gives the outputs of its last tick
  and of no other. What a tick before it did is seen only in what it left
  in a block's memory.
- **Which input a write was thrown away on.** The counts are for the whole
  graph, and a write gives nothing back. A device whose clock is a few
  seconds behind has every sample read as too old, and looks like one that
  has stopped.
- **A period that is not a whole number of nanoseconds**, such as a
  sixtieth of a second, cannot be written.
- **Different rates.** Everything runs at one period.

**Open.**

- **What the period should be on a real machine**, and what maximum age is
  reasonable, when inputs are polled at about half a second with jitter and
  each device is read at its own moment. Settled by: measuring input age and
  the spread between devices on recorded data.

## 7. States through a graph

**Proposed.** A problem at this tick is never hidden. A problem in the
past is remembered for as long as a block says it remembers, and no longer.

**Rule D.** A block's output is never better than `uncertain` on a tick
where a value the block used to give that output at that tick is
`uncertain`. Each block's rule says what it uses. A formula does not use an
operand that did not decide, an `uncertain` operand beside a `good` one
that decides by itself, or a branch it did not take (rules 7.1.2 and
7.1.3); a latch that is set does not use `set`; `all_good`, a window's
`count` and the counters read states and not values, and are always `good`.
A value a block took in at an earlier tick is not one it uses at this
tick: what the block remembers of it is the block's own rule. There is
one exception to what the next paragraph says of memory, named where it is
made: a delay, window or
low-pass on a loop that holds a model block, once the loop has settled
(rule 7.8.8).

**Memory.** A block that keeps something from one tick to the next says
how long that memory is.

- **Finite memory**: a window's `n` ticks, a low-pass's or a model's
  `settle`. The block is `uncertain` for that long after it took in
  something doubtful, and no longer.
- **Memory with no end**: which way a hysteresis last switched, whether a
  latch is set, a running total, how long a timer has run. The block
  takes its state from what it reads now, and gives
  **counters** that a graph can test: how long it has been going
  (`elapsed`), how much of that time its input was not `good`
  (`doubtful`), and how many gaps there were in it (`gaps`). `good` does
  not vouch for history older than a block's declared memory.
- **A tolerance** the graph's author declared (a window's `min_good`, a
  total's `max_missed`) is the author's statement of what is acceptable.
  Within it an output is `good`. A `ride_through` is not one: a block
  riding through says `uncertain` while it does, but for a model block
  with no `settle` (rule 7.8.6), whose `doubtful` counts the ticks.

**Settle.** Where a block is `uncertain` "for `settle` after a doubt" at
tick `d`, it is so on the `settle` ticks after `d`: ticks `d + 1` to
`d + settle`. What it is at tick `d` itself is given by rule D and the
block's own rule.

**Counters.** `elapsed` and `doubtful` are numbers, in seconds, and always
`good`. `elapsed` counts whole ticks, the present one among them, since
the event the block names, and `doubtful` counts those of them that the block's own rule names: for
most, the ticks on which its input was not `good`. So `doubtful` is never more than
`elapsed`, and the first tick counted gives an `elapsed` of one period. A
tick a gap passed over (section 8) is a tick, and one on which no input
was `good`: `elapsed` counts it, and `doubtful` does wherever it would
have counted a tick with its input unusable. A gap of no known length has
no ticks to count.
`gaps` is a number, a count, and always `good`: the gaps (section 8) whose
tick is the one `elapsed` counts from, or a later one. Every block that
gives `elapsed` gives `gaps`, and where `elapsed` is zero because nothing
is being counted, as for a `held_for` whose timer is not running, `gaps`
is zero too.

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

An input declares its type and a **maximum age**, and optionally a unit, an
initial value and `max_ahead` (rule 6.8). The maximum age is required: a
length of time not less than half a period, or `none`. A tick may run half
a period after the call that brought its sample, and a shorter maximum age
would call that sample too old.

At a tick whose time is `t`, an input is the first of these that applies.
"What stands" is as rule 6.8 says.

1. If nothing stands:
   - `uncertain`, with its declared initial value and no sample time, if
     it declares one, the graph has run for no more than the maximum age,
     and there has been no rebase since the engine was made or last reset.
     An initial value stands in for the first measurement and for nothing
     later: after a rebase an input with nothing written has no value;
   - otherwise `not_ready`, until the graph has run for more than the
     maximum age, and `bad` from then on.

   The graph has run for `t` less the time of tick 0 as the first call
   gave it, or less the time of the last rebase's tick (section 8). A stall
   does not change it.
2. `not_ready` or `bad`, if that is the state that stands.
3. `bad`, if the value that stands is not finite.
4. `bad`, if its age, `t` less its time, is more than the maximum age. The
   age of a sample stamped after the tick is below zero, which is not more
   than any maximum.
5. `uncertain` or `good`, as it stands, with that value and that time as
   its sample time.

A value written and not written again stands, and grows older. A write of
`not_ready` or of `bad` does not grow old. An age exactly equal to the
maximum is usable.

### 7.3 Windows

A window's memory is its `n` ticks. A sample leaves after `n` ticks, and
its doubt with it.

1. **A window looks at the samples of its last `n` ticks**, where `n` is
   its `window` setting in periods.
2. A window has a setting, `min_good`: the fraction of its `n` ticks that
   must hold a `good` sample for it to be `good`. It is 1 unless given.
   The number **needed** is `min_good × n` rounded up to a whole number
   (rule 6.3), and at least 1.
3. With fewer usable samples than are needed, every output but `count`
   takes the worst state among its ticks that hold none. A tick from before
   the graph started, one a gap passed over (rule 8.6), or one whose sample
   a rebase took out of a window with `only_new` (rule 8.5), holds none
   and counts as `not_ready`. After a gap of no known length that is every
   tick before the one that runs.
4. With as many usable samples as are needed, but fewer `good` ones, its
   outputs are `uncertain`, and its statistics are of its usable samples.
5. With as many `good` samples as are needed, its outputs are `good`, and
   its statistics are of its `good` samples alone. An `uncertain` sample
   within the tolerance is left out, as a missing one is.
6. A slope needs two samples. Where the window holds fewer than two `good`
   samples and at least two usable ones, its slope is of its usable
   samples and is `uncertain`, whatever rule 5 says of the rest. With one
   usable sample the slope is `bad`. The other statistics are as rules 4
   and 5 say. Rule 3 comes first: with fewer usable samples than are
   needed the slope takes the state the other statistics take.
7. `count`, the number of usable samples the window holds, is always `good`.
8. With `only_new: true` a tick holds a sample only if the input is usable
   and its sample time is later than that of the last sample the window
   took. A value still standing from an earlier tick is not another sample,
   and neither is one with no sample time. A tick that holds none for that
   reason counts as `not_ready` in rule 3; a tick whose input is not
   usable counts as that input's state, as in any window. `min_good` has to be given: a
   tick the host did not call for holds no new sample, and at 1 that one
   hole would spoil the window for its whole length.

A window fed a value that has stopped being written reports no spread and
no slope, and reports them as `good`, until the input's maximum age ends
it. `only_new` is for the window that must not.

### 7.4 Blocks that hold a value

**Deadband.** It holds one sample for as long as the input stays within
`step` of it, which has no end.

1. The first usable input is taken as it is. After that the block keeps the
   value it holds until the input has moved by `step` or more from it, and
   then takes the input.
2. With a usable input, its output is the value it holds, with **the state
   of the input at this tick**. The value is within `step` of that input,
   which is what a deadband promises. Whether the sample it holds was once
   `uncertain` is not kept.
3. With an unusable input, its output is the held value, `uncertain`, if
   the last usable input was no more than `ride_through` ago. On the `m`-th
   unusable tick in a row the last usable input was `m` periods ago.
4. Past `ride_through` it forgets what it held. Its output takes the input's
   state, and the next usable input is a first input.

**Low-pass.** Its memory fades, with time constant `tau`, and is counted as
`settle`: three time constants, rounded up to whole ticks, unless given.

<!-- markdownlint-disable MD029 -- the rules of 7.4 keep one numbering -->
5. The first usable input sets `y = x`. After that, on a usable input,
   `y = aᵐ·y + (1 - aᵐ)·x`, where `a = exp(-period / tau)` and `m` is the
   number of ticks since its last usable input. `m` is 1 unless it has
   ridden through unusable ticks; the ticks it missed decay too. `aᵐ` is
   `a` raised to the power `m` as C's `pow` gives it, and `a` itself
   where `m` is 1.
6. With an unusable input, rules 3 and 4 apply to it as to a deadband.
7. Its **doubt** is the latest tick at which it took an `uncertain` input,
   a first input among them. Forgetting (rule 4) clears it. Riding through
   is not a doubt: the missed ticks are decayed on the input that comes
   back, and nothing held is left in the value.
8. With a usable input its output is `uncertain` if the input is, and for
   `settle` after its doubt. Otherwise it is `good`.

**Rate limit.** It holds the last value it gave, which has no end.

9. The first usable input is taken as it is. After that, on a usable
   input, its output moves from the value it holds towards the input: by
   at most `up` times the period where the input is above it, and by at
   most `down` times the period where it is below. An input within that
   reach is taken as it is: the input less the value held, either way
   round, is compared with the reach, exactly. `up` and `down`
   are per second, and `down` is `up` unless given. The reach is of one
   period whatever went before: after riding through, the output still
   moves by no more than one period's worth in a tick. With `initial`
   given, the block holds that value from the start, and its first input
   is limited from it like any other.
10. With a usable input its output takes the state of the input at this
    tick, as a deadband's does (rule 2). `limited` is a boolean with that
    state: true when the output is not the input.
11. With an unusable input, rules 3 and 4 apply to its output as to a
    deadband's, and `limited` takes the input's state: there is nothing to
    compare. Having forgotten, it holds `initial` again if it was given
    one, and otherwise takes its next usable input as it is, however far
    that is from where it was. Holding `initial` and nothing else it does
    not ride through: its output takes the input's state.
<!-- markdownlint-enable MD029 -->

### 7.5 Hysteresis

Its memory is which side it is on, and has no end.

1. It goes true when its input is at or above `rise`, and false when its
   input is at or below `fall`. Between the two it stays as it was. It
   starts as its `initial` setting says, or undecided if there is none.
2. With an unusable input it stays as it was, and its output takes the
   input's state.
3. With a usable input its output is `not_ready` while it is undecided, and
   otherwise takes the input's state.
4. `elapsed` and `doubtful` count from the tick its value last changed, a
   change from undecided among them, or from the first tick if it has not;
   `doubtful` is of its input.

A hysteresis that sat through an hour without its input is `good` when the
input comes back between the thresholds, and `doubtful` says an hour. A
graph that must not act on that tests it.

### 7.6 Timers and latches

Each takes a boolean. None of them remembers a doubt.

1. **Held for.** True when its input has been true for longer than `time`.
   The tick on which the input becomes true counts as no time at all. A
   usable input that is false stops the timer. With a usable input the
   output takes the input's state. Required `on_bad`:
   - `reset`: an unusable input stops the timer, and the output takes the
     input's state.
   - `hold`: an unusable input leaves the timer running, for at most
     `hold_limit`, a required setting. While it runs on an unusable input
     the output is `uncertain`, and true once the time has run out. When
     the unusable stretch grows longer than the limit, or if the timer was
     not running, the timer stops and the output takes the input's state.
     The stretch at its `m`-th unusable tick in a row is `m` periods long.

   `elapsed` and `doubtful` count from the tick the timer started, and are
   zero while it is not running; `doubtful` is of its input.
2. **Since true.** True when its input has not been true for longer than
   `time`. Its clock starts at the first tick and is set again on every
   tick where the input is usable and true. Its output is true when the
   tick's number less the clock's is more than `time`, counted in ticks.
   With a usable input the output takes the input's state. Required
   `on_bad`: with `assume_false` an unusable input counts as not true, and
   the output is `uncertain`; with `unknown` the output takes the input's
   state.

   `elapsed` and `doubtful` count from the tick the clock was last set;
   `doubtful` is of its input. After a gap of no known length (rule 8.6)
   the input was last true longer ago than `time`: until the clock is next
   set the output's value is true, with the state the rule above gives it,
   and the counts start at the gap's tick.
3. **Latch.** False until its input `set` is first usable and true, then
   true. It has an input `reset` that need not be connected. At a tick, the
   first of these that applies:
   - `reset` is usable and true: it is cleared. The output is false, with
     the state of `reset`.
   - it is set: the output is true and `good`. `set` is not used.
   - `set` is usable and true: it is set. The output is true, with the
     state of `set`.
   - `set` is usable and false: the output is false, with the state of
     `set`.
   - `set` is unusable: the output takes the state of `set`.

   A `reset` that is unusable, or usable and false, is not used.

   `elapsed` counts from the tick it was last cleared, or from the first
   tick. `doubtful` counts those of them on which it was not set when the
   tick began and `set` was not `good`.

### 7.7 Integrators

A running total has no end. It reports what it has, and counts what it
lacks.

1. An integrator adds its input, times the period, on every tick where the
   input is usable. The value at a tick includes that tick's addition, so a
   constant 1 from tick 0 gives `k + 1` periods at tick `k`.
2. The total is the first of these that applies: `bad`, once `missed` is
   more than `max_missed`, if that is given, until a reset, and `bad`
   likewise after a gap of no known length (rule 8.6), which is more than
   any `max_missed`, though `missed` cannot say so and only `gaps` shows
   it; a reset at the gap's own tick ends that as any reset does; `uncertain`, on
   a tick where its input is `uncertain`, or where `reset` is `uncertain`
   and true; `good`. On a tick where its input is unusable the total is
   `good`: it has a value, and `missed` says what it lacks.
3. It gives four counts, each a number and always `good`:
   - `missed`: the time it has not integrated, the period added up over
     every tick where the input was unusable;
   - `doubtful`: the time over which it added an `uncertain` input;
   - `elapsed`: the time it has run, the present tick counted;
   - `gaps`: how many gaps (section 8) there have been.

   All four count from its last reset, or from the first tick. A gap whose
   tick is the tick of the reset is counted.
4. It has an input `reset` that need not be connected. A usable, true
   `reset` returns the total and all four counts to zero before that tick's
   addition. An unusable `reset`, or one that is usable and false, is not
   used.

**The PID.** A controller's integral is a running total, and has no end.

<!-- markdownlint-disable MD029 -- the rules of 7.7 keep one numbering -->
5. A `pid` reads `setpoint` and `measurement`, and its **error** is the
   first less the second. On a tick where both are usable, its output
   before limiting is `kp·error + integral + derivative`, and its output
   `y` is that held within `min` and `max`, where they are given. The sum
   is worked in one order, since another differs in the last place and
   can fall on the other side of a limit: `kp·error` and the derivative
   are added first, and to that the integral with this tick's addition
   already made. The test of rule 6 is of that same sum. Where an
   addition is cut short at `max`, the integral becomes `max` less the
   first of those two, and `y` is `max` itself.
6. **The integral** starts at zero. On a tick where both inputs are
   usable, `ki·error·period` is added to it, `ki` being per second, and
   the value at a tick includes that tick's addition, as a total's does
   (rule 1). **An addition that would put the output before limiting
   above `max` is cut short**: where the addition is more than zero and,
   with it made, that output would be above `max`, the integral becomes
   what puts that output at `max`, or stays as it is if that is less than
   it has, and `y` is `max`. Likewise below `min`, for an addition less
   than zero. So the
   integral stops going into a limit, takes the output to the limit and
   not short of it, and still comes out of one: an addition towards the
   other limit is made whole.
7. **The derivative** is of the measurement and not of the error, so that
   a step of the setpoint gives none. With `s` the measurement less the
   measurement of the tick before, over the period, the block keeps
   `f = a·f + (1 - a)·s` from tick to tick, with
   `a = exp(-period / filter)`, and the derivative is `-kd·f`. `filter` is
   written as a length, and is given when `kd` is not zero and only then.
   On the first tick where both inputs are usable, and on the first such
   tick after one where they were not, after a reset or after a gap, there
   is no tick before: `f` is zero, and the derivative with it. Every tick
   is taken as a new measurement, so `filter` is chosen no shorter than
   the time between samples: a measurement that stands for several ticks
   and then moves gives a derivative of spikes.
8. With both inputs usable, `y` takes the worse of their two states, and
   is `uncertain` as well on a tick where `reset` is `uncertain` and true.
   With either unusable, `y` takes the worst state of the two and has no
   value: **a controller does not drive on a value it did not see**, and a
   fallback (section 7.10) or the host says what the actuator gets, or a
   block after it that rides through, a `rate_limit` or a `deadband` with
   a `step` of zero, holds its last output for that long. The integral is
   kept, and nothing is added to it.
9. `limited` is a boolean with the state of `y`: true when the output
   before limiting was above `max` or below `min`, or the addition was
   cut short. `integral` is the
   integral, a number: `uncertain` on a tick where `y` is, or where
   `reset` is `uncertain` and true, and otherwise `good`, on a tick with
   an unusable input too, as a total is (rule 2).
10. It has an input `reset` that need not be connected. A usable, true
    `reset` returns the integral and the counts to zero and the derivative
    to its start, before that tick's addition. An unusable `reset`, or one
    that is usable and false, is not used.
11. It gives `elapsed`, `doubtful` and `gaps`, which count from its last
    reset, or from the first tick. `doubtful` counts the ticks on which
    either input was not `good`. A gap whose tick is the tick of the reset
    is counted.
12. **What was applied.** It has an input `applied`, a number, deferred,
    that need not be connected: the value that reached the actuator, from
    whatever follows the PID. Rule 6 sees the PID's own `min` and `max`
    and no limit after it, and against a rate limit that follows it the
    integral winds up. Where `applied` is usable at a tick whose addition
    was made, whole or cut short, and is less than `y` by more than
    `applied_within` with the addition more than zero, or more than `y` by
    more than `applied_within` with the addition less than zero, **the
    addition is taken back**: from the next tick the integral is what it
    was before this tick's addition, which on the tick of a reset is
    zero. What this tick gave is not changed. An `applied`
    that is `uncertain` is used as a `good` one is, and one that is not
    usable is not used. `applied_within` is zero unless given, and the
    comparison is exact, of `y` less `applied`, or the other way round,
    with `applied_within`. A PID whose `applied` is not connected may be
    given one, which does nothing. At zero, `applied` is for the output
    of a block
    that gives `y` on unchanged when it is not limiting, wired straight
    in. **A readback that is off by anything, a formula's rounding
    included, needs an `applied_within` larger than it is off by.**
    Without one, a readback that is always a little low takes every
    rising addition back, and the integral never grows; one a little high
    takes back every falling one. A rate limit read back this way still
    takes the PID's first output whole unless it has an `initial` (rule
    7.4.9).
    `limited` says nothing of an addition taken back: a graph that has to
    know compares `y` with what was applied.
<!-- markdownlint-enable MD029 -->

A PID with a limit and an error that stays one way sits at the limit with
its integral where it was when it got there, and comes off the limit as
soon as the error has turned far enough to bring the output inside it. One with no `max` and no `min` has nothing to stop
its integral, and `limited` is false.

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
   7.4.3, ticks a gap passed over among them. Otherwise it does not step.
   After a gap of no known length it does not, until the input is usable
   again. It keeps the value for rule 5.
5. **A model never gives up its state.** Its outputs are always usable,
   unless rule 3.6 makes one `bad`. Where its outputs read a direct input
   that is unusable, they are worked out on that input's last usable value,
   or on zero if it has had none, and are `uncertain`. Where they read a
   direct input that is `uncertain`, rule D makes them so. A model block's
   outputs are judged together: on such a tick every output of the block
   is `uncertain`, one that reads no input among them.
6. Its **doubt** is the latest tick at which it stepped on an `uncertain`
   value, stepped on a held value (rule 4), or did not step. For a model,
   unlike a low-pass, riding through is a doubt: the held value has gone
   into its state. A doubt from the second phase of tick `k` is tick `k`.
   - With `settle`, its outputs are `uncertain` for `settle` after its
     doubt, and otherwise `good`. For a named model in continuous time
     `settle` is three of its slowest time constant, rounded up to whole
     ticks, unless given. This number is worked in double arithmetic and
     is not exact (rule 6.3): with `r` three of the constant over the
     period, it is the least whole number not less than `r - 10⁻⁹`. Where
     rounding could put `r` on either side of that, a graph may be taken
     either way, and its author writes `settle`. That constant is one over the least rate at
     which its state decays: minus one over the largest real part among
     all the eigenvalues of its `A`. For a model that swings as it decays
     that is the constant of the envelope. A named model has one state or
     two. For two, with `h` half the sum of `A`'s diagonal and `d` its
     determinant: where `h²` is no more than `d` the largest real part is
     `h`; otherwise, with `h` less than zero, it is `d / (h - √(h² - d))`.
     Both are worked so that a slow rate beside a fast one is not lost in
     a subtraction, and `d` is taken from the model's settings, as its
     entry in Appendix A gives it, and not from `A`'s entries. Where the
     two rates are many orders apart the last ticks of a `settle` of
     millions still depend on rounding.
   - A named model with any state that does not decay, where that
     largest real part is zero or more, such as a mass on a spring with no
     damping, has no such constant. Neither `linear` nor `state_space` is
     given one, and in that alone a named model differs from the `linear`
     that spells it out. With no `settle` given, such a model's outputs
     are `good`, and its counters say what it has been through.

   It gives `elapsed`, which counts from the first tick; `doubtful`,
   which counts the ticks on which it stepped on an `uncertain` or a held
   value or did not step; and `gaps`. The step of tick `k` is taken in the
   second phase, so at tick `k` `doubtful` counts the steps of the ticks
   before `k`, one tick behind `elapsed`. A tick a gap passed over is a
   step on a held value or a step not taken (rule 8.6), and is counted.
7. **Every model is linear, and is stepped exactly.** A model in
   continuous time is `dx/dt = A·x + B·u`, with outputs `y = C·x + D·u`,
   where `x` is its states, `u` its inputs and `y` its outputs. Its step
   over one period is the solution of that equation with every input held
   at its value for the whole period:
   `x' = Ad·x + Bd·u`, where `Ad = exp(A·period)` and `Bd` is the integral
   of `exp(A·s)·B` for `s` from zero to the period. `Ad` and `Bd` depend on
   the model and the period and on nothing else, so the engine works them
   out when the graph is compiled. How it does so is its own affair: what
   is specified is the result, to within rounding, and the vectors compare
   to one part in 10⁹ (rule 11.5). That is a promise of `Ad` and of `Bd`,
   which is of one step: over many ticks a state that does not decay
   carries each step's rounding forward, and two engines that agree on
   every step drift apart in an oscillator with no damping by about one
   part in 10⁹ in a few hundred ticks at the bound below, and far more
   slowly well inside it. The promise does not depend on the size of `B`:
   `Bd` is the integral of `exp(A·s)` over the period, times `B`. **It is
   promised up to a bound on how fast the model is against the period,
   and a graph past it is refused.**
   The bound is on the largest sum of the absolute values along a row of
   `A`, times the period, which may be 100,000 at most. In ordinary
   double arithmetic the exponential of a matrix loses accuracy in
   proportion to that number, and past the bound an engine cannot keep the
   promise without arithmetic of more digits. A model refused for it has a
   state far faster than the period, which is not a state at that period
   and is left out; or has entries that are large for the units its states
   are in, since the sum depends on them, and is rescaled. A named model's
   units are fixed, so one that is refused for them is written as `linear`.
   For the two named models of the second order the row holds the square
   of the rate (`omega_n²`, or `stiffness / mass`), so the bound falls on
   that: a resonance of 50 Hz with little damping is within it at a period
   of 1 s and past it at 2.5 s. The sum is of
   `A` alone, in double arithmetic, and a graph within rounding of the
   bound, or of what a double holds, may be taken either way. So a model's answer does not depend on the period
   beyond what holding its inputs costs, no step is unstable, and there are no sub-steps: a step is too long
   only for the arithmetic, at the bound above. A model that grows so
   fast that an entry of `Ad` or `Bd` at the graph's period is more than a
   double holds is refused. One that is accepted and grows can still pass
   that some ticks on, and its outputs are then `bad` (rule 3.6).
   A model in discrete time (`state_space`) gives `Ad` and `Bd`
   themselves, and they mean what they mean at whatever period the graph
   has.
8. **A loop.** The blocks of a graph that can each reach every other
   through inputs, direct or deferred, are a **loop**. A block that reads
   its own output is one by itself. A loop that holds a model block is
   treated as one block with fading memory, and `settle` is its author's
   statement of how long that memory is, along every path in it:
   - it holds one model block and no more. Two model blocks that read
     each other are a tick apart, and a network that is sound can be
     unstable so split, however exactly each is stepped. The graph is
     refused, and the error names them and says to write them as one
     model: `linear` takes any number of states;
   - the model block has `settle` written in the graph. A model's own time
     constant is not the loop's. The graph is refused otherwise;
   - what else remembers in it is held against that `settle`: the graph is
     refused if the `ticks` of its delays, the lengths of its windows and
     the `settle`s of its low-passes, written or not, all in ticks, add up
     to more than it. An estimator hosts a model but is not a model block, and a loop
     that holds a model block and an estimator is refused (section 7.9,
     Open);
   - the loop's **doubt** is the latest tick at which a block in it used a
     value that was not `good`, read from outside the loop, or gave an
     output that was not usable on a port that a block of the loop is
     connected to, whether or not a fallback then stood in for it, and
     whether or not that block used it. An output no block of the loop is
     connected to starts nothing, and nor does an `uncertain` value that
     passes from one block of the loop to another. For this, a formula
     uses what rule D says, and every other block counts as using every
     input it has, in either phase, whatever its own rule says of them. A
     model in the loop that steps on a held value or does not step has
     been given such a value, so its tick is the loop's doubt already;
   - a doubt at tick `k` is seen from tick `k + 1`. At tick `k` itself the
     loop is judged by its latest doubt before `k`, so an earlier doubt
     that has not run out is not forgotten for a tick;
   - the model in it is `uncertain` for `settle` after the loop's doubt,
     in place of its own in rule 6, and otherwise as rule 5 says. Its
     counters are its own;
   - at a tick where the loop is not within `settle` of its doubt, what a
     delay, a window or a low-pass in it took in as `uncertain` at an
     earlier tick becomes `good`, and stays so: a later doubt of the loop
     does not turn it back. That is every such value the block holds, and
     not only the one it gives at that tick. A delay gives such a value as `good`; a window
     holds such a sample as a `good` one from then on; a low-pass's doubt
     is cleared. What each takes in at the tick itself is as its own rule
     says. This is so for a reader outside the loop too;
   - a window on the loop that needs more than one sample gives
     `not_ready` while it has fewer, which is an output that is not usable.
     If a block of the loop is connected to it, the loop is in doubt from
     the start, and after a gap that left the window short, until `settle`
     after the last tick on which it was short;
   - the other blocks in it follow their own rules.

So two thermal masses that each take the other's temperature are refused
as two blocks, and are one `thermal_rc2` or one `linear` block. Take two
of 10 J/K losing 1 W/K each, with formulas that give each a power of 3 W
for each degree the other is above it, at a period of 5 s. The pair's
difference is multiplied by about -1.75 a tick, however exactly each is
stepped, and within eighty ticks they pass 10¹⁹ and say `good`; the one
block gives the true answer at any period. A plant driven
through a controller by a setpoint that is `uncertain` on every tick is
`uncertain` on every tick after the first: what it gives at a tick is its
state from the tick before.

**Open.**

- **A model that is not linear.** The catalogue has none, and 1.x had
  none. One whose equation is not linear has no exact step, and would
  bring back a rule for how it is stepped and how far that can be
  trusted. Settled by: the first model that needs it.
- **A loop of two model blocks that is sound.** Two plants with a
  controller between them, say. Refused now, and could be allowed where
  the compiler can show the pair stable. Settled by: the first graph that
  needs one.
- **A model and a controller together.** A loop of one model and a
  formula is a sampled controller, and can be unstable as a real one can.
  That is the graph's behaviour and not a fault of the step, and nothing
  here checks it.

### 7.9 The estimator

An estimator hosts a model as its predictor and corrects it from
measurements. It is a Kalman filter over a linear model (rule 7.8.7), and
each measurement reads one output of the model.

1. It starts from the model's initial state, with the variance its `p0`
   gives each state and no covariance between states, and gives outputs
   from tick 0.
2. **Predict.** Its model inputs are deferred. On every tick after tick 0
   it steps the model one period, from the tick before to this one, on
   the model inputs **as they were at the tick before**, as a model
   block's step is (rule 7.8.1): for each, its value then, or if it was
   unusable then, the last usable value it had had. The covariance goes
   with it: `P = Ad·P·Adᵀ + N`. `N` is what process noise has added by the
   end of the step. For a model in continuous time it is the integral of
   `exp(A·s)·Q·exp(Aᵀ·s)` for `s` from zero to the period, where `Q` has
   each state's `q` on its diagonal and nothing off it: `q` is a variance
   per second, and `N` is exact as `Ad` is, on the same terms (rule
   7.8.7). For `state_space` it is `q` times the period on each state's
   own variance. If some model input had never been usable by then, it
   does not step the state on this tick: the state stays and the
   covariance is `P + N`.
3. **Correct.** Then, on every tick, for each measurement in the order they
   are declared: it is **considered** if its sample time is later than
   the sample time last considered on that port, and it is either `good`,
   or `uncertain` on a port that gives `r_uncertain`. A measurement with no
   sample time is never considered. Its variance is the port's `r` if it
   is `good` and `r_uncertain` if it is `uncertain`. **A measurement
   carries the time of a sample**: its port is connected to an input, or
   to a delay or a formula that takes its sample time, through any number
   of those, from an input (rule 3.7). One connected to any other block,
   or to a constant, is refused when the graph is compiled: such a block
   gives its output the time of the tick, and every tick would count as a
   new sample. Only the path the time comes by is followed. A formula's
   `sample_of` is its author's word that its value is as new as that
   input, whatever else the formula reads.
4. A considered measurement `z` of the output whose row of the model's
   `C` is `c`, with variance `v`, has the innovation `z - c·x`, the spread
   `s = c·P·cᵀ + v`, and the **normalised innovation squared**, the
   innovation squared over `s`. With no gate it is **used**: with
   `g = P·cᵀ / s`, `x = x + g·(z - c·x)` and
   `P = (1 - g·c)·P·(1 - g·c)ᵀ + g·v·gᵀ`. That is `P - g·(c·P)`, worked in
   the form that rounding cannot bring to nothing: with a `p0` of 10¹⁶
   beside an `r` of 1 the short form leaves a variance of exactly zero
   after one measurement, and the estimator never moves again. The form
   keeps `P` symmetric and positive at any ratio. It is not exact at an
   extreme one: with a `p0` more than about 10¹² times an `r`, the
   variances of the first few measurements are out by more than the
   vectors' tolerance, and come right as more are used. A
   measurement may be of an output that reads no input directly; one that
   does is refused when the graph is compiled.
5. **The gate.** If `gate` is given and the innovation is more than `gate`
   times the square root of `s` either way, the measurement is **over the
   gate**, and is **refused**: counted, and the state and the covariance
   do not change. It is still the measurement last considered on its
   port, and its normalised innovation squared is kept (rule 6). A run is
   of measurements considered on one port: a tick with none, a gap, and
   what another port does leave it as it was, and a measurement that is
   used ends it. `max_refused` is required with `gate`, and is the most a
   port refuses in a row: a measurement over the gate that would be one
   more is not refused. It has disagreed for too long to be an outlier:
   each state's variance grows by its `p0`, `s` is worked again, and the
   measurement is used. Its normalised innovation squared is the one
   worked before the variance grew. With `max_refused` of 1 a port
   refuses one and takes the next; with 0 it refuses none.
6. **Consistency.** `consistency` is required: either `none`, or `over`, a
   whole number of measurements, and `limit`. With `over` and `limit`,
   each port keeps the normalised innovation squared of its last `over`
   considered measurements, refused ones among them. Once a port has
   `over` of them, it is **inconsistent** while their mean is more than
   `limit`. An estimator whose model and noise are right has a mean of 1.
   A reset empties what a port keeps; a gap does not.
7. **When it is `good`.** A state's outputs are `uncertain` on a tick
   where any of these is so, and otherwise `good`:
   - the step to this tick (rule 2) was on a model input that was
     `uncertain` or unusable at the tick before, or was not taken, or
     this tick is the one a gap ran (rule 8.6), unless the gap passed
     over no tick;
   - a measurement was refused at this tick, or one over the gate was
     used at this tick by rule 5: it has given in to what it was refusing,
     and cannot tell a sensor that is right from one that is stuck;
   - an `uncertain` measurement was used at this tick;
   - a port is inconsistent at this tick;
   - a gap of no known length has gone by (rule 9) and no measurement has
     been used since, on any port, at the gap's own tick or after it: it
     does not know where it is until one tells it. A refused measurement
     does not;
   - the state's sigma is more than its `sigma_max`, if one is given.

   The covariance is the estimator's own account of its memory, and
   stands in for a doubt: none of these lasts past its tick but the
   last three, which last as long as they are so.
8. Outputs, each a number:
   - one per state, by the state's name, and `sigma_<state>`, the square
     root of its variance;
   - `innovation_<port>` and `nis_<port>`: on a tick where the measurement
     was considered, its innovation and its normalised innovation squared,
     `good`; on any other tick `not_ready`;
   - `refused_<port>`: how many have been refused, `good`;
   - `since_<port>`: the time from the sample time of the measurement last
     used to the tick, and not less than zero, `good`; `not_ready` until one
     has been used.

   Each output has a name of its own. A graph where two would have one
   name, as with states named `x` and `sigma_x`, is refused.
9. **At a gap** (rule 8.6). Told that `n` ticks were passed over, it
   predicts `n` times more, each as rule 2, on the model inputs it last
   had: that is what those ticks would have done. What is specified is
   the result of `n` predictions and not that they are made one by one;
   the same goes for a model block's steps in rule 8.6. At a rebase,
   whether or not anybody knows its length, each state's variance grows
   by its `p0`, once in all, after the predictions for the ticks passed
   over, where their number is known, and before the one for the tick
   that runs: it compares sample times, and cannot tell
   a measurement from before the rebase from the same one written again
   (rule 8.5). A graph whose `N` holds more than a double does is
   refused, as for `Ad` (rule 7.8.7).

An estimator with a stable model and little process noise stays confident
through a long stretch without measurements, and is right to if the model
is right. `since_<port>` is there for the graph that wants to act on the
stretch itself.

What the consistency test is for. Take a mass of 100 J/K losing 1 W/K,
heated by a square wave of 60 W with a period of ten minutes, measured
each second with noise of 0.2, and an estimator of it with `q` of 0.001,
`r` of 0.04 and `p0` of 1, whose model has the heat loss a fifth too low.
Over an hour, with a gate of three sigmas and nothing to end a run of
refusals, it refuses about 3,500 of 3,600 measurements and ends more
than 3 degrees out; under the third revision's rule it said `good`
throughout, and under rule 7 it is `uncertain` on every tick it refuses.
With `max_refused` of 5 it is never more than 1.6 out; it is then `good`
and more than three of its own sigmas out on about a third of its ticks,
because a sigma knows only the noise it was told of. With `consistency`
over 20 and a limit of 2 that falls to between a thirtieth and a
fiftieth, and with the model right the test costs twenty ticks or
fewer. The counts move with the noise drawn.

**Open.**

- **Model inputs with noise of their own**, and process noise that is not
  one number per state. Both need matrix settings and neither needs a
  vector signal. Settled by: the first graph that needs one.
- **The model's outputs, estimated.** The estimator gives its states. A
  graph that wants an output that is not a state, a motor's torque say,
  works it from them in a formula.
- **An estimator on a loop with a model block** is refused (rule 7.8.8).
  Its model inputs are deferred, so a loop through them alone compiles;
  what its being `uncertain` means for a loop's doubt is not worked out.

### 7.10 Fallbacks

A block may name, for any of its outputs, a value to give when that output
is not usable. The substituted value is `uncertain`. Each applies to the
output it names and to no other. Every reader of that output sees the
substituted value, inside the graph as well as outside it. An output made
`bad` by rule 3.6 is replaced like any other.

### 7.11 What this gives up

Each of these is a value called `good` that rests on something the block
no longer remembers. Each is deliberate, and most have a counter, or a way
to write the stricter thing.

- **A latch set by an `uncertain` true is `good` and true from the next
  tick.** To set only on a `good` true, give the latch `b and ok`, where
  `ok` is an `all_good` of `b`. That latch says `good` and false while `b`
  is unusable, since a `good` false decides an `and`: a graph that has to
  see `b` drop out reads `ok` as well.
- **An `uncertain` true on `reset` clears a latch**, which is `good` and
  false from the next tick, with nothing to say so. For a latch that holds
  a trip, give it `r and ok` likewise.
- **A hysteresis that sat through an hour without its input** is `good`
  when the input comes back between the thresholds. `doubtful` says an
  hour.
- **A total is `good` on a tick where its input is `bad`**, a little low.
  `missed` says by how much time.
- **A deadband holding a sample that was `uncertain` when taken** is `good`
  once its input is.
- **`held_for` with `on_bad: reset`** never fires on an input that drops
  out now and then, and says `good` and false.
- **`held_for` with `on_bad: hold`** is `good` and true on the first tick
  its input is back, though the time ran out while it held. `doubtful`
  says how much of the run it did not see.
- **A model with no `settle`, or a `settle` of zero**, is `good` on a
  state it stepped to on an `uncertain` value one tick before. `doubtful`
  counts those steps.
- **A good window's statistics are of its `good` samples alone**, so they
  can move when the count of `good` samples crosses what `min_good` asks.
- **A block with no fading memory is `good` on the tick after it took in
  an `uncertain` value**, with that value in it: a total with an
  `uncertain` thousand added, a timer started or a clock set by an
  `uncertain` true, a hysteresis switched by an `uncertain` input.
  `doubtful` counts the tick. A low-pass with a `settle` of zero is the
  same, and has no counter.
- **A model block with no `settle` is `good` while it rides through**, on
  steps taken from a held value. `doubtful` counts them.
- **A latch that is set is `good` and true while `set` is `bad`**, and its
  `doubtful` does not count those ticks: it counts only while the latch is
  not set.
- **An `uncertain` true on a total's `reset` sets it and its counts to
  zero.** The total is `uncertain` on that tick and `good` from the next,
  with nothing to say it was reset on doubt. Give it `r and ok`, as for a
  latch. A PID's `reset` is the same.
- **An `uncertain` measurement on a port with no `r_uncertain` is passed
  by**, and the estimator stays `good`. `since_<port>` shows how long it
  has gone without one.
- **A formula's logic and its choices are `good` beside an operand that is
  not.** `a or b` with `a` true and `good` is `good` whatever `b` is, and
  `when(ok, x, 20)` is a `good` 20: the problem is not in what the formula
  used, and a graph that has to see it reads `all_good`.
- **A gap makes only a model with `settle`, and an estimator on the
  gap's own tick, `uncertain`.** Every other
  block does what the ticks nobody saw would have done to it. A window
  short of samples and a delay with nothing to give are `not_ready`, a
  total past `max_missed` is `bad`, and the rest are `good` on the far
  side. A hysteresis, a latch, a total within `max_missed` and a model
  with no `settle` are `good` across an hour's stall; `doubtful`, `missed`
  and `gaps` say an hour and one gap.
- **`since_true` is `good` and true after a long gap**, with either
  `on_bad`: nobody saw its input, and a tick nobody saw does not set its
  clock. An alarm on "nothing for ten minutes" fires after a ten-minute
  stall. `doubtful` says how much of the quiet nobody saw, and after a gap
  of no known length only `gaps` does.
- **A delay gives `not_ready` for a tick nobody saw.** A formula that
  keeps a running value through a delay reads `not_ready` after any gap as
  long as its delay, and goes on reading it. A total is an `integrate`,
  which keeps its value and counts what it missed.
- **A loop's `settle` is its author's word for every path in it.** A total
  kept by a formula and a delay on a loop with a model block is `good`
  once the loop has settled, with an `uncertain` addition still in it. A
  delay, window or low-pass on such a loop gives `good` to readers outside
  the loop on the same terms.
- **A loop of formulas and delays with no model block has no `settle`**
  (rule 5.6). One `uncertain` value taken in leaves it `uncertain` for as
  long as that value goes round, which for a running total or a peak hold
  is for good; one unusable value, or the `not_ready` a delay gives after
  a gap, goes round for good unless a block of the loop has a fallback or
  rides through. A model block on the cycle ends both, since its outputs
  are always usable.
- **The estimator takes a measurement written again after a rebase as a
  new one**: where its variance had already grown well past `p0`, the one
  sample sharpens it twice.
- **An estimator is `good` on the tick after a refusal, or after an
  `uncertain` measurement or model input**, with whatever that did to it
  still in its state. Its covariance is its account of that, and is right
  only as far as its model and its noise are. With `consistency: none`
  nothing checks them, and an estimator with a wrong model is `good` with
  a sigma that is too small.
- **`good` from an estimator means that nothing in rule 7.9.7 is so, and
  not that the estimate is right.** Its sigma is as honest as its `q` and
  `r`. A `q` of zero says the model is exact: the gain falls to nothing,
  the sigma with it, and the estimator stops listening and stays `good`.
- **`max_refused` chooses between two failures.** Large, and after a real
  step change the estimator is `uncertain` and wrong for that many
  measurements; small, and a sensor that has stuck is followed within that
  many. The consistency test needs `over` measurements before it can
  speak, sees only innovations that are too large, and keeps its last
  word through a stretch with no measurement.
- **One sample read on two ports is used twice.** Sample times are kept
  for each port, so two measurements connected to one input, or to it and
  a delay of it, each take the one sample. So does a formula whose
  `sample_of` names an input that is newer than the value it gives.
- **A sample's time is its host's word.** A host that writes an old value
  with a new time, as it has to after a rebase (rule 8.5), hands the
  estimator a new measurement, and after a gap of no known length that is
  what ends its being `uncertain`.
- **No test of innovations sees a sensor that reads steadily high or
  low.** An estimator whose sensor is a degree out is a degree out, and
  `good`, with or without a consistency test.
- **An estimator follows a sensor that has stuck**, once it has refused it
  `max_refused` times: it is `uncertain` on the tick it gives in, and
  then `good` and as wrong as the sensor. A consistency test catches the
  jump and not what follows.
- **An estimator goes on predicting on the model inputs it last had**,
  through a stretch without them and across a gap of any known length,
  where a model block stops after `ride_through`. A tick after a stall of
  a thousand ticks it is `good` on a thousand steps of an input nobody
  saw, with a sigma that has grown by its process noise alone.
- **A PID keeps its integral across a gap of any length**, a restore
  among them, and is `good` on the far side with whatever it had wound to.
  `gaps` says there was one.
- **A PID is `good` on the tick after an `uncertain` error went into its
  integral.** `doubtful` counts the tick. Its derivative's filter fades,
  and is treated as the integral is and not as a low-pass.
- **A rate limit with no `initial` does not limit its first move**, or
  its first after it has forgotten: past `ride_through`, or after a gap
  that long, its next usable input is taken as it is.
- **A limit after a PID that `applied` is not connected to is not seen by
  it.** Its integral winds up against it, and `limited` is false.
- **A PID whose `applied` reads low by more than `applied_within` never
  integrates upwards**, and is `good` with a standing error; one that
  reads high never integrates downwards. A shortfall inside
  `applied_within` is not seen, and the integral winds up by that much.
- **An `uncertain` `applied` decides what the integral keeps**, and the
  integral is `good` on the next tick.
- **A PID's derivative is zero on the tick an input comes back**, and its
  output steps by what the derivative was giving. With `kd` of zero there
  is no step.
- **A rate limit holding a value it moved to on an `uncertain` input** is
  `good` once its input is, as a deadband is.
- **Only a window has a tolerance for doubtful samples.** One `uncertain`
  sample in every `settle` ticks keeps a low-pass, and any low-pass or
  model after it, `uncertain` for good. That includes the value another
  low-pass gives while it rides through.

**Open.**

- **Whether a consumer needs to know why a value is `uncertain` or `bad`.**
  Settled by: what each consumer in Anolis would do differently if it could
  tell.

## 8. Reset, save, restore and gaps

**Proposed.**

1. A graph can be reset to its initial state. After a reset the next call
   runs tick 0 again, at whatever `now` it is given. Nothing stands on any
   input, and every write still waiting is done with.
2. A graph can write its state out and take it back, so that a host can
   save a running graph and restore it. A state saved from one graph is
   refused by a graph that is not the same. A saved state holds what the
   blocks remember, their counters, each loop's doubt and the number of
   the next tick. It does not hold what stands on an input, the writes
   waiting, the clock, a `rebase` not yet followed by its call, or the
   count of writes thrown away, which stays the engine's own.
3. A **gap** is ticks nobody saw: they were due, and were not run. One
   tick runs at a gap, and the ticks before it are **passed over**. There
   are two kinds.
   - A **stall**: a call that would run more than `max_catch_up` ticks. The
     clock is the same clock, and the ticks stay where they were.
   - A **rebase**: the first call after a restore, or after the host has
     said that its clock has stepped (`rebase`). The clock may be another
     clock altogether, and the call may carry any `now`.

   Restoring a state saved before any tick had run is a reset, and neither.
4. At a stall, one tick runs: the last one that was due, under its own
   number and at its own time. The due ticks before it are passed over:
   one fewer than were due. It is the last tick of its call, and may see
   what such a tick may (rule 6.8). What stood goes on standing, as old as
   it is.
5. At a rebase, one tick runs, at the call's `now`, and later ticks are at
   whole periods from it. **The host may say how long the graph was
   away**: `rebase` takes a length, counted from the time of the last tick
   run. The ticks that would have been due in that time, by rule 6.6, are
   that length divided by the period and rounded to the nearest whole
   number, a half rounding up. The last of them is the tick that runs, and
   the rest are passed over; if none would have been due, none is passed
   over and the next tick runs. With no length, nobody knows how many were
   passed over, and the tick that runs is numbered one more than the last
   tick run. A length of zero is a length. A restore puts back "nobody
   knows", whatever `rebase` said before it. Before it runs:
   - nothing stands on any input, and that is so from the moment the state
     was restored or the host said its clock had stepped: every write then
     waiting was done with, and what the host writes after that waits as
     usual, judged against nothing from the old clock. For rule 7.2.1 the graph has
     run since this tick. **After a rebase a host writes again every input
     that has no maximum age**, the ones it writes only on change, **with
     the time of the rebase's call**: such a value is as true as when it
     was set. An input with a maximum age is written when it is next
     sampled, on the clock the host now passes, and has no value until
     then: an old sample written with a new time would be a new one. An
     input's `initial` does not come back (rule 7.2.1);
   - every sample time a block remembers or holds is forgotten. A window
     with `only_new` takes the next usable sample, and an estimator
     considers the next measurement, as if they had seen none; an estimator
     has used none, so its `since_<port>` is `not_ready`; and the values a
     delay holds at that moment lose their sample times. A block that
     compares sample times cannot tell a sample from before the rebase
     from the same one written again after it, whatever length the host
     gave. So a window with `only_new` keeps no sample from before a
     rebase, and an estimator's variance grows (rule 7.9.9) at every rebase.
     That growth is a stand-in and not a bound: a value written again
     after a rebase is taken as a new measurement all the same.

   `rebase` before any tick has run, since the engine was made or last
   reset, does away with the writes waiting, and nothing else: the next
   call runs tick 0 and is not a gap. Restoring a state saved before any
   tick had run is a reset (rule 3). A `rebase` whose length would give the tick
   it runs a number past 64 bits is accepted, and every call after it is
   refused (rule 6.11) until the host calls `rebase` again with a length
   that does not. A second `rebase` before the call does away
   with what was written since the first, and its length, or its having
   none, is the one that counts. A reset after a `rebase` is a
   reset, and the next call is not a gap. A state saved between a `rebase`
   and the call that follows it is as one saved before the `rebase`.
6. At either kind, before the tick runs, every block is told how many
   ticks were passed over, or that nobody knows. **Each block does to what
   it remembers what that many ticks would have done, had each been run
   with nothing usable on any of its inputs.** The ticks are not run: no
   output is given for them, and a block does this from the number alone.
   Where nobody knows the number, it is more than anything the block
   counts, and nothing is added to a count but one to `gaps`. Where the
   number is zero, as after a rebase whose length is under a period and a
   half, a block does nothing but add one to `gaps`, whatever the table
   says: no timer stops and no model has a doubt. What rule 5 says of a
   rebase holds all the same: nothing stands, every sample time is
   forgotten, a window with `only_new` is emptied and an estimator's
   variance grows. The call says it was a gap, and how many (rule 6.10).

| Block | Told that `n` ticks were passed over | Told that nobody knows |
| --- | --- | --- |
| `formula`, `all_good` | Nothing: no memory | The same |
| `delay` | It moves on `n` places, taking in `not_ready` for each, so that what it gives is still its input of `ticks` ago | Everything it holds is `not_ready`, an initial value not yet given among them |
| `window` | Those `n` ticks hold no sample, and count as `not_ready` | None of its ticks holds a sample |
| `deadband`, `lowpass`, `rate_limit` | If the last tick passed over is within `ride_through` of its last usable input, it holds what it held, and a low-pass decays over the ticks it missed (rule 7.4.5). Otherwise it forgets, a low-pass its doubt too | It forgets |
| `hysteresis` | Stays as it was. `doubtful` goes up by `n` | Stays as it was |
| `held_for` | With `reset` the timer stops. With `hold` the unusable stretch grows by `n`: within `hold_limit` the timer runs on and `doubtful` goes up by `n`, and past it the timer stops | The timer stops |
| `since_true` | The clock is not set, with either `on_bad`. `doubtful` goes up by `n` | The input was last true longer ago than `time` (rule 7.6.2), and its counts start again at the gap's tick |
| `latch` | Unchanged. `doubtful` goes up by `n` if it is not set | Unchanged |
| `pid` | The integral is unchanged, and the derivative starts again (rule 7.7.7). `doubtful` goes up by `n` | The integral is unchanged, and the derivative starts again |
| `integrate` | The total is unchanged. `missed` and `elapsed` go up by `n` | The total is unchanged. With `max_missed` given it is `bad` until a reset: what it missed is more than that |
| Model block | For each of those ticks, in order, it steps on the last usable value of every input while each is within `ride_through` (rule 7.8.4), and takes no step from the first tick where one is not. `doubtful` goes up by `n`. The tick before the one that runs is a doubt (rule 7.8.6), its loop's if it is on one: with `settle` it is `uncertain` from the tick that runs | The same doubt. It takes no step, and does not ride through (rule 7.8.4) |
| `estimator` | It predicts `n` times more on the model inputs it last had (rule 7.9.9) | Each state's variance grows by its `p0` |

`elapsed`, which counts ticks, takes in the `n` passed over with no more
said. Every block that gives `gaps` adds one to it at a gap of either
kind. Where a block's count starts again at the tick the gap runs, as
that of a `since_true` told nobody knows does, and as that of a
hysteresis that changes or a latch that is cleared on that tick does, or
at a later tick, as `held_for`'s does, `gaps` starts again with it, at one
if that tick is the tick it counts from. Counters, and the doubt of a
loop, are part of what a save holds, and a rebase does not set them to
zero beyond what the table says. A reset does.

This is each block's own reckoning and not a run of the graph. A latch
fed by a formula that would have been true on a tick nobody saw is not
set by it, and a fallback gives nothing for one.

Nothing else changes at a gap. An estimator keeps its state and its
counts, and a model keeps the last usable value of each input for rule
7.8.5. At a stall, which is on one clock, a block keeps the sample times
it remembers. At a rebase with a length a delay both moves on and loses
the sample times of what it still holds.

**Open.**

- **What "the same graph" means**: the same text, or the same blocks,
  settings and period, and in either case the same layout of state in the
  library that wrote it.
- **A restore that is not a gap.** A graph saved, restored and given the
  same writes does not go on as it would have: its windows with `only_new`
  are empty and its estimators less sure. A simulator that wants to go
  back to a saved moment and run on exactly needs a save that also holds
  what stands, the writes waiting and the clock, and a restore for which
  the host vouches that the clock is the same and no time has passed.
  Settled by: the first use in simulation that needs it.

## 9. The graph file

**Proposed.** The shape, not the final keys:

```yaml
period: 2.5s
max_catch_up: 100
max_waiting: 1024

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
   maximum age and, where it has them, its unit, initial value and
   `max_ahead`. A type left out is `number`. A graph that reads a signal which is
   neither an input nor a block's output is refused.
2. A block id, and a name a block's settings give to a port, a state or
   an output, is not empty and holds no dot. The name of an input and a
   published name are not empty. A block's `in` maps each
   input port to a signal, named as text and not empty, or to a
   constant. Its `out` maps output ports to signal names, which are text; a
   port left out is not published, and any output, published or not, can be
   read by another block as `<block id>.<port>`. A block id is text. No
   input and no published signal may have a name of the form
   `<block id>.<port>` for a block and port of the graph.
3. A length of time is written as a number and a unit with nothing between
   them: `ns`, `us`, `ms`, `s`, `m` or `h`. The number is digits, with an
   optional point and more digits. A number without a unit is refused. So
   is a length the engine keeps as a time (rule 6.2) that is not a whole
   number of nanoseconds.
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

This section is a statement of intent. The graph file of section 9 has no
key for a port's unit or for the strict policy, which is 1.x's name for
refusing a graph with a port that declares none; neither reading in
`conformance/` checks a unit; and no vector covers it.

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
5. Values are compared to within one part in 10⁹ of the value, or of 1
   where the value is smaller than 1. Where a rule turns on
   exact equality, a vector uses values that are exact in binary.
6. The two implementations are also run side by side on random inputs and
   call times, at clock values small and large, with stalls, saves,
   restores, rebases and resets among the calls.

`conformance/` holds the vectors, two readings of this proposal, and the
checks that run them.

## 12. What happens to 1.x

| 1.x | 2.0 |
| --- | --- |
| `IModel` | A model, hosted by a block or by an estimator |
| `ITransform` | A block |
| Edges | Gone; a signal is named as an input |
| `tick(dt)` | `tick(now)`, in whole nanoseconds; the period is fixed at compile |
| Models run first, then edges | One sorted order, two phases |
| A model's output is its state after the step | Its state at the tick (rule 7.8.1) |
| Signal: a number and a unit | A typed value, a state, a sample time |
| Unwritten signal reads 0.0 | Unwritten signal is `not_ready`, unless its input declares an initial value |
| Stability limit checked per model | Gone: a model is stepped exactly, and no step is unstable. One too fast for the arithmetic at the graph's period is refused (rule 7.8.7) |
| Rules and commands | Open (section 4) |
| Unknown keys ignored by the loaders | Refused |
| Thermal, process, mechanical and motor models | Kept as models, each a case of `linear` (Appendix A) |
| Model settings named with their units (`tau_s`, `resistance_ohm`) | Named without; a length of time is written with its unit |
| Model settings' ranges | Wider in places: a `thermal_rc2` node may lose nothing to the ambient, and a `dc_motor` may have no resistance, back emf or torque |
| The transforms | `delay` is kept, in ticks. `first_order_lag` is `lowpass`, and `moving_average` is a `window`'s `mean`. `linear` (scale and offset) and `unit_convert` are each a `formula`. `deadband` is another block under the same name: 1.x gives zero inside a threshold, which is a `formula`. `saturation` is a `formula`, `min(max(x, lo), hi)`, and `rate_limiter` is `rate_limit`. `noise` is not in the catalogue yet |
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
| `hysteresis` | `x`: number | `rise`, `fall`, `initial` (none) | `y`: boolean; `elapsed`, `doubtful`, `gaps` |
| `held_for` | `x`: boolean | `time`, `on_bad`, `hold_limit` | `y`: boolean; `elapsed`, `doubtful`, `gaps` |
| `since_true` | `x`: boolean | `time`, `on_bad` | `y`: boolean; `elapsed`, `doubtful`, `gaps` |
| `latch` | `set`: boolean; `reset`: boolean, optional | none | `y`: boolean; `elapsed`, `doubtful`, `gaps` |
| `integrate` | `x`: number; `reset`: boolean, optional | `per` (`1s`), `max_missed` (none) | `y`, `missed`, `doubtful`, `elapsed`, `gaps` |
| `rate_limit` | `x`: number | `up`, `down` (`up`), `ride_through` (0), `initial` (none) | `y`; `limited`: boolean |
| `pid` | `setpoint`, `measurement`: number; `reset`: boolean, optional; `applied`: number, optional, deferred | `kp`, `ki` (0), `kd` (0), `filter`, `min` (none), `max` (none), `applied_within` (0) | `y`, `integral`; `limited`: boolean; `elapsed`, `doubtful`, `gaps` |
| `linear` | one per column of `B`, named by `inputs` | `A`, `B`, `C`, `D` (zeros), `initial` (zeros), `inputs`, `states`, `outputs`, and the model settings | one per row of `C`, named by `outputs`; and the model outputs |
| `thermal_mass` | `power`, `ambient` | `thermal_mass`, `heat_transfer`, `initial`, and the model settings | `temp`; and the model outputs |
| `thermal_rc2` | `power`, `ambient` | `thermal_mass_a`, `thermal_mass_b`, `heat_transfer_a`, `heat_transfer_b`, `coupling`, `initial_a`, `initial_b`, and the model settings | `temp_a`, `temp_b`; and the model outputs |
| `first_order_process` | `u` | `tau`, `gain` (1), `initial` (0), and the model settings | `y`; and the model outputs |
| `second_order_process` | `u` | `omega_n`, `zeta`, `gain` (1), `initial` (0), `initial_rate` (0), and the model settings | `y`, `rate`; and the model outputs |
| `mass_spring_damper` | `force` | `mass`, `damping`, `stiffness`, `initial_position` (0), `initial_velocity` (0), and the model settings | `position`, `velocity`; and the model outputs |
| `dc_motor` | `voltage`, `load_torque` | `resistance`, `inductance`, `back_emf`, `torque_constant`, `inertia`, `friction`, `initial_current` (0), `initial_speed` (0), and the model settings | `speed`, `current`, `torque`; and the model outputs |
| `state_space` | `u` | `A`, `B`, `C`, `D` (0), `initial` (zeros), and the model settings | `y`; and the model outputs |
| `estimator` | the model's inputs, deferred, and one per measurement | `model`, `q`, `p0`, `measure`, `consistency`, `gate` (none), `max_refused`, `sigma_max` (none) | see 7.9.8 |

A setting with a value in brackets may be left out and takes that value.
`settle` is written as a length of time, like any other counted length. An
input is required and direct unless the table or the block's rule says
otherwise. An output is a number unless the table says otherwise. `formula`
and `all_good` take one or more inputs, `all_good` under any names and
`formula` under names its grammar allows. The **model
settings** are `ride_through` (0) and `settle` (rule 7.8.6), and the
**model outputs** are `elapsed`, `doubtful` and `gaps`. A model block's
input is a number, and is deferred unless the model's outputs read it
(rule 7.8.2).

Ranges, outside which a graph is refused: `ticks` a whole number, at least
1; `window` at least one period; `min_good` more than 0 and at most 1;
`step`, `ride_through`, `settle`, `time`, `hold_limit`, `max_missed`, `q`,
`gate` and a state's `sigma_max` not negative; `ticks`, `over`,
`max_refused`, `max_catch_up` and `max_waiting` at most 2,147,483,647,
which is a width and not a size: an engine may refuse a graph it has not
the memory for, a long window among them, and a count it works out, a
low-pass's `settle` say, that does not fit in 64 bits;
`measure` at least one port; `up`, `down` and `applied_within` not
negative; `per`, `tau`,
`filter`, `p0` and `r` more than zero; `min` less than `max` where both
are given; a
model's settings as its entry below says; `rise` more
than `fall`; every number, `initial` and fallback finite; `on_bad` one of
the choices its block gives. `filter` is required with a `kd` that is not
zero and refused without one. `hold_limit` is required with `on_bad: hold`
and refused without it. `min_good` is required with `only_new: true`.

- **`formula`.** Section 7.1 governs states.
  - **Numbers:** digits, an optional point and more digits, an optional
    exponent (`e` or `E`, an optional sign, digits). Nothing else: no sign
    of its own, no hexadecimal, no separators. A number too large for a
    double is refused, and one too small for a double is zero.
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
  - An engine reads a formula nested at least 100 deep, counting each
    bracket, function and operator that is inside another, and may refuse
    one nested deeper than it can read.
  - `sample_of` names one of the block's inputs that is a signal (rule
    3.7). With more than one signal input and no `sample_of`, and with no
    signal input at all, `y` carries the time of the tick.
- **`all_good`.** True when every input is `good`, else false. Always
  `good`.
- **`delay`.** At tick `k` its output is its input at tick `k - ticks`:
  value, state and sample time, as a reader of that input saw them then
  (but see rule 7.8.8 for a delay in a loop that holds a model). For a
  tick a gap passed over it is `not_ready` (rule 8.6). Before tick 0, its output is `initial` and `good`, with
  no sample time, or `not_ready` if no initial value is given. Its type is
  its input's, and an initial value of the other type is refused. On a
  loop, where its input's type waits on its own, its type is its initial
  value's, which rule 5.4 sees that it has. An
  initial value is `good` because it is the author's statement of where a
  loop starts, where an input's initial value stands in for a measurement.
- **`window`.** Rule 7.8.8 has more for one in a loop that holds a model
  block. `window` is `n` periods. At a tick the window is that tick
  and the `n - 1` before it. `median` of an even number of samples is the
  mean of the middle two. `spread` is `max - min`. `slope` is the
  least-squares slope of value against time, per second, taking the oldest
  tick of the window as time zero. Section 7.3 governs states.
- **`deadband`.** The comparison with `step` is exact. Section 7.4.
- **`lowpass`.** Section 7.4, and rule 7.8.8 for one in a loop that holds
  a model block.
- **`hysteresis`.** Section 7.5.
- **`held_for`.** Section 7.6 rule 1. With `time` of `n` periods, the output
  is true on a tick when the timer started more than `n` ticks before it:
  from the `n + 1`-th tick after the one the input became true on.
- **`since_true`.** Section 7.6 rule 2.
- **`latch`.** Section 7.6 rule 3.
- **`integrate`.** Section 7.7. On a usable tick it adds `x` times the
  ratio of the period to `per`. The ratio is worked once, exactly, and
  then taken as a double, so that at a period of 100 ms and a `per` of
  300 ms an input of 3 adds exactly 1. `missed` is in seconds.
- **`rate_limit`.** Section 7.4 rules 9 to 11.
- **`pid`.** Section 7.7 rules 5 to 12. `kp`, `ki` and `kd` are any finite
  numbers: `ki` per second, `kd` in seconds.
- **`linear`.** Any linear model in continuous time (rule 7.8.7):
  `dx/dt = A·x + B·u`, `y = C·x + D·u`. `A` is a list of `n` rows of `n`
  numbers; `B` a list of `n` rows, one number per input; `C` a list of
  rows, one per output, of `n` numbers; `D`, if given, a row per output of
  one number per input. `initial` is a number per state. `inputs`,
  `states` and `outputs` are lists of names; left out, a single one is
  `u`, `x0` or `y`, and several are `u0`, `u1`, `x0`, `x1`, `y0`, `y1` and
  so on. There is at least one state, one input and one output. The
  names in each list are distinct, the three lists do not have to differ
  from each other, and an output is not named
  as a model output is. An input is direct if any output reads it, which
  is where its column of `D` is not all zero. The matrices are in the
  units of seconds. A graph is refused where the sizes do not agree.
- **The named models** are each `linear` with its matrices written out
  from a few physical settings. Each lists its states in the order of
  `A`'s rows and its inputs in the order of `B`'s columns. An output is a
  state unless it says otherwise, so every input is deferred.
  - **`thermal_mass`.** State `temp`, from `initial`. Inputs `power`,
    `ambient`. `d temp/dt = (power - heat_transfer·(temp - ambient)) /
    thermal_mass`. `thermal_mass` and `heat_transfer` more than zero.
  - **`thermal_rc2`.** Two masses joined by a conductance, the first
    heated. States `temp_a`, `temp_b`, from `initial_a`, `initial_b`.
    Inputs `power`, `ambient`.
    `d temp_a/dt = (power - heat_transfer_a·(temp_a - ambient) -
    coupling·(temp_a - temp_b)) / thermal_mass_a`, and
    `d temp_b/dt = (-heat_transfer_b·(temp_b - ambient) +
    coupling·(temp_a - temp_b)) / thermal_mass_b`. The masses more than
    zero; `coupling` and the two `heat_transfer`s not negative. `A`'s
    determinant is `(heat_transfer_a·heat_transfer_b +
    coupling·(heat_transfer_a + heat_transfer_b)) / (thermal_mass_a·thermal_mass_b)`.
  - **`first_order_process`.** State `y`. Input `u`.
    `dy/dt = (gain·u - y) / tau`. `tau` is written as a length of time, and
    is more than zero.
  - **`second_order_process`.** States `y`, `rate`, from `initial`,
    `initial_rate`. Input `u`. `dy/dt = rate`, and
    `d rate/dt = omega_n²·(gain·u - y) - 2·zeta·omega_n·rate`. `omega_n` is
    in radians a second and more than zero; `zeta` is not negative. `A`'s
    determinant is `omega_n²`.
  - **`mass_spring_damper`.** States `position`, `velocity`. Input
    `force`. `d position/dt = velocity`, and `d velocity/dt = (force -
    damping·velocity - stiffness·position) / mass`. `mass` more than zero;
    `damping` and `stiffness` not negative. `A`'s determinant is
    `stiffness / mass`.
  - **`dc_motor`.** States `current`, `speed`. Inputs `voltage`,
    `load_torque`. `d current/dt = (voltage - resistance·current -
    back_emf·speed) / inductance`, and `d speed/dt =
    (torque_constant·current - friction·speed - load_torque) / inertia`.
    Outputs `speed`, `current`, and `torque`, which is
    `torque_constant·current`. `inductance` and `inertia` more than zero;
    `resistance`, `friction`, `back_emf` and `torque_constant` not
    negative, so that nothing in the determinant is subtracted. `A`'s determinant is
    `(resistance·friction + back_emf·torque_constant) / (inductance·inertia)`.
- **`state_space`.** Discrete, one input and one output, as 1.x has it. `A`
  is a list of `n` rows of `n` numbers, `B` and `C` lists of `n`. Its step
  is `x = A·x + B·u` and its output `y = C·x + D·u`, at whatever period the
  graph has. `u` is direct when `D` is not zero and deferred when it is.
  Its states are named `x0`, `x1` and so on, in the order of `B`.
- **`estimator`.** Section 7.9.
  - `model` is a map with `type`, a model's type, and that model's own
    settings (not the model settings above).
  - `q` and `p0` are maps from each state's name to a number: `q` a
    variance per second, `p0` a variance.
  - `measure` maps each measurement port to `of`, the name of one of the
    model's outputs, `r`, a variance, and if wanted `r_uncertain`, a
    variance not less than `r`. Its order is the order of rule 7.9.3.
  - `consistency` is `none`, or a map with `over`, a whole number at least
    1, and `limit`, more than zero.
  - `max_refused` is a whole number, not negative, given with `gate` and
    refused without it.
  - `sigma_max` maps states' names to numbers. A state left out has none.
  - Its model inputs are deferred and its measurements direct.

A block may carry `fallback`, a map from an output port to a constant of
that port's type (section 7.10).

**Open.** The catalogue is short of what a first real graph needs: a
derivative, an edge detector, an off-delay, a moving sum, a lookup, a
selector, a difference of a device's counter and a second-order section.
None can be put together from the blocks above without a loop through a
delay, and a formula cannot read the period. A clamp can, and is a
formula: `min(max(x, lo), hi)`. Each
is a block with scalar settings, and none needs a rule this document does
not have. Settled by: writing them, each with its
vectors.

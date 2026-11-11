# FluxGraph semantics, version 2 (proposal)

**Status:** proposal. Not in force. [semantics_spec.md](semantics_spec.md)
stays the normative contract for FluxGraph 1.x until this is accepted, at
which point this document replaces it and the library becomes 2.0.

Each section is marked **Proposed** (a position to argue with) or **Open**
(a question with what would settle it). Nothing here is implemented in the
library.

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
give a block is the list this proposal answers:

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
compatibility. The maths of the existing models and transforms carries over
unchanged.

Not goals of 2.0: blocks at different rates, a variable step, parallel
evaluation, implicit solvers.

## 3. Values

**Proposed.**

1. A signal carries a **value** and a **state**. The state is one of:
   - `good`: the value is usable.
   - `not_ready`: there is no value yet. A window is still filling, a filter
     has not started, an input has never been written.
   - `bad`: an input this value depends on was not usable.
2. A value whose state is not `good` is never read as a number. A block that
   is handed one decides what to do by the rules in section 7.
3. A signal nobody has written is `not_ready`. There is no default value.
4. A value is a `double`. A boolean is 1 or 0.
5. A signal written from outside the graph also carries the **time it was
   sampled**. The engine does not use it to compute; it uses it to decide
   whether the value is still usable (section 6).

**Open.**

- **Other value types.** Integers, strings and enumerations exist on the
  machines this will run on. Settled by: listing the blocks that would need
  one, and whether a number and a lookup outside the graph would do.
- **A value that came from a fallback.** Section 7 lets a block substitute a
  stated value for an output that is not good. Whether that output is then
  `good`, or a fourth state, decides whether a consumer can tell. Settled
  by: what each consumer in Anolis would do differently if it could.

## 4. Blocks

**Proposed.**

1. There is one kind of computing element, a **block**. A block has a type,
   named **input ports**, named **output ports**, **settings**, and state of
   its own.
2. A 1.x transform is a block with one input and one output. A 1.x model is
   a block with several. Edges are gone: a signal is connected by naming it
   as an input. A delay is a block that gives its input from an earlier
   tick, and a stated initial value until then.
3. A block type declares, to the compiler:
   - its input and output ports, and which inputs are required;
   - its settings, each with a type, whether it is required, and its range;
   - whether it may break a loop (section 5);
   - for each input, whether it reads that input in the same tick or only
     from the previous one.
4. A block reads only its own inputs and writes only its own outputs. It has
   no access to the rest of the store.
5. Every output port is written by exactly one block. A signal written from
   outside the graph is written by nothing inside it.

**Open.**

- **Rules and commands.** In 1.x a rule tests one signal against a number
  and emits a device command. No graph file in this repository or in the
  simulator provider has a rule, though the provider has the code to run
  the commands one would emit. Proposed for removal; a condition is a block
  whose output is a boolean, and acting on it is the host's business.
  Settled by: the simulator provider's maintainers agreeing to drop that
  path.
- **Formulas.** Arithmetic, comparison and three-valued logic over a block's
  inputs is one block type, with a small expression language. The core has
  no dependencies, so the parser would be FluxGraph's own. Settled by: a
  grammar short enough to specify here, and a decision on whether it
  belongs in the core or beside the loaders.

## 5. Order and loops

**Proposed.**

1. The compiler sorts all blocks into one evaluation order from their
   declared ports. A block is evaluated after every block whose output it
   reads in the same tick.
2. Ties are broken by block id, so the order is the same on every compile.
3. A dependency loop is a compile error that names the blocks on the loop,
   unless every loop passes through an input that is declared to read the
   previous tick (a delay, or a block type that says so).
4. Nothing reads a value "one tick late" by accident. In 1.x a model reads
   an edge's output a tick late because edges run after models; in 2.0 that
   lag exists only where a block declares it.

## 6. Time

**Proposed.** One fixed period, written so that it can grow.

1. A graph has one **period**, fixed when it is compiled. Every block runs
   once per tick, and tick `k` is at time `k × period`.
2. A block is given the period when it is built, and the tick's time when it
   runs. A window of ten seconds is a number of ticks worked out once, at
   build, and the compiler refuses a window that is not a whole number of
   periods.
3. The host does not pass a step size to `tick`. A model with a stability
   limit is checked against the period at compile.
4. **Inputs from outside.** The host writes a value, its state and the time
   it was sampled, at any moment between ticks. At a tick, each external
   input is the latest value written. An input declares a **maximum age**;
   if the latest value was sampled longer ago than that, the input is `bad`
   for this tick.
5. The host's clock and the graph's ticks are the host's to line up. The
   engine promises only that a tick uses what was written before it began.

What this leaves out, on purpose, and what it keeps open for later:

- **Jitter.** A block treats each tick as exactly one period after the
  last. If the host ticks late, a filter's time constant is wrong by that
  much. The host is responsible for ticking on time, and for saying so when
  it cannot.
- **Sample time is not tick time.** A value sampled just after the previous
  tick is treated the same as one sampled just before this one. The sample
  time is carried so that a later version can resample instead.
- **Different rates.** Everything runs at one period. A slow block is a
  block that keeps a counter.

**Open.**

- **What the period should be on a real machine**, and what maximum age is
  reasonable, when inputs are polled at about half a second with jitter and
  each device is read at its own moment. Settled by: measuring input age and
  the spread between devices on recorded data.
- **Whether the engine should detect a late tick** and mark outputs
  accordingly, or leave that entirely to the host.

## 7. Inputs that are not good

**Proposed.** The default is that a problem is never hidden. An input is
**usable** at a tick when its state is `good` and its value is finite.

### 7.1 Blocks with no state

1. The output of a formula, a gain or a comparison takes the worst state
   among its inputs: `bad` over `not_ready` over `good`.
2. **Logic is three-valued.** One true operand decides an `or` and one false
   operand decides an `and`, whatever the others are. Otherwise an operand
   that is not good makes the result not good, by rule 1.
3. **A choice** between two values on a condition takes the state of the
   condition if that is not good, and otherwise the state and value of the
   branch it chose. The other branch is not looked at.
4. A division by zero, and any result that is not finite, is `bad`.

### 7.2 Windows and holders

A window gives statistics of recent samples. A holder keeps one value.

1. **A window is the usable samples of the last stretch of time**, its
   `window` setting. Its statistics are of those samples and no others: an
   unusable sample is left out, and a sample older than the window is gone.
2. A window has a setting, `min_good`: the fraction of its ticks that must
   hold a usable sample for its outputs to be `good`. It is 1 unless given.
3. When a window holds fewer usable samples than that, its outputs take the
   worst state among its ticks that were not usable. A tick from before the
   graph started counts as `not_ready`.
4. A slope needs two samples at different times. With fewer it is `bad`.
5. **A holder** keeps its output until its input has moved by its step or
   more. Its first usable input is taken as it is.
6. A holder has a setting, `ride_through`, a length of time, zero unless
   given. While its input is unusable:
   - if the last usable input was no longer ago than `ride_through`, and the
     holder is holding a value, the output is that value and `good`;
   - otherwise the output takes the input's state.

   Either way it keeps what it held.

So a window that requires every sample stops being `good` on the tick an
unusable sample arrives and stays so until that sample has left it. A holder
with `ride_through` left at zero stops being `good` on the same tick as its
input. Each reports through a gap only as far as its author said it may.

A window does not need a policy for unusable samples. An earlier draft gave
it one, with the choices "skip" and "reset". Worked by hand, the two came to
the same thing once the window was defined by time and not by a count of
samples, and `min_good` says what the policy was reaching for. OPC UA's
historical aggregates take the same approach, with a required percentage of
good data per interval.

### 7.3 Timers

1. **Held for.** True once its input has been true for longer than a stated
   time. Required `on_bad`:
   - `reset`: an unusable input stops the timer, and the output takes the
     input's state.
   - `hold`: an unusable input leaves the timer running. The output is
     `good`, and true once the time has run out, even while the input is
     still unusable. If the timer was not running, the output takes the
     input's state.
2. **Since true.** True when its input has not been true for longer than a
   stated time. An unusable input counts as not true. The output is always
   `good`, and the clock starts at the first tick.
3. **Latch.** False until its input is first true, then true. An unusable
   input does not set it. The output is always `good`.

### 7.4 Running totals

A total adds its input, times the period, on every tick where the input is
usable. It has two outputs, both always `good`: the total, and the time it
has missed, which is the period added up over every tick where the input
was unusable. A total does not hide a gap and does not stop being a number
because of one.

### 7.5 Estimators

1. An estimator is `not_ready` until its first usable measurement.
2. After that it is `good`. On a tick with no usable measurement it predicts
   and does not correct, and its reported uncertainty grows.
3. A model input that is unusable is left out of the prediction for that
   tick, and the uncertainty grows as if nothing were known about it.

### 7.6 Fallbacks

A block may name, for one output, a value to give when that output is not
good. The substituted value is `good`. It applies to the named output only.

### 7.7 Inputs from outside

At a tick, an external input is:

- `not_ready` if nothing has been written to it, or if the host wrote it as
  `not_ready`;
- `bad` if the host wrote it as `bad`, if its value is not finite, or if it
  was sampled longer ago than its maximum age;
- otherwise `good`, with the value last written.

A value written and not written again stands, and grows older.

**Open.**

- **Whether `not_ready` and `bad` are ever treated differently by a block's
  policy.** Here they are alike in what they do to a block's state and
  distinct only in what the block reports. Settled by: a case where an
  author would want them to differ.
- **Whether a substituted value should be distinguishable from a computed
  one** (section 3).

## 8. State, reset and restore

**Proposed.**

1. Every block can be reset to its initial state.
2. Every block can write its state out and take it back, so that a host can
   save a running graph and restore it. An estimator's state is the reason:
   a restart should not have to mean starting cold.
3. The engine saves and restores a whole graph at a tick boundary. A state
   saved from one graph is refused by a graph that is not the same.

**Open.** Whether a block declares that its state should survive a restart
of the host, or the host decides for the whole graph. And what "the same
graph" means: identical text, or the same blocks and settings.

## 9. The graph file

**Proposed.** The shape, not the final keys:

```yaml
period: 2.5s

inputs:
  - signal: heater/pad_c
    unit: degC
    max_age: 10s

blocks:
  - id: pad
    type: window
    in: { x: heater/pad_c }
    settings: { window: 7.5s }
    out: { median: heater/pad_filtered_c }
```

1. `inputs` lists every signal written from outside, with its unit and its
   maximum age. A graph that reads a signal which is neither an input nor a
   block's output does not compile.
2. A block's `in` maps each input port to a signal or to a constant. Its
   `out` maps output ports to signal names; a port left out is not
   published and can still be read by another block.
3. An unknown key, an unknown setting, a setting of the wrong type or out of
   range, a missing required setting and a duplicate signal are compile
   errors. 1.x ignores an unknown top-level key.

## 10. Units

**Proposed.** As in 1.x, moved from signals to ports: an input or an output
port may declare a unit, a connection between two declared units that differ
is a compile error, and the strict policy requires every port to declare
one.

**Open.** The registry is a fixed built-in list. A live machine has units
it does not hold. Settled by: whether a graph may declare
its own units, and what a declared unit has to say.

## 11. Conformance

**Proposed.** The rules above are tested by vectors, not by reading.

1. A test vector is a graph, the inputs at each tick (value, state and
   sample time), and the expected state and value of every output at every
   tick.
2. Every numbered rule in sections 3 to 7 has at least one vector that fails if the rule is broken. A
   vector is accepted only after a deliberately broken implementation has
   been shown to fail it.
3. Expected values are worked out independently of the implementation under
   test.
4. A second implementation passes the same vectors. The vectors are the
   contract between them.

A first set exists beside this proposal, in `conformance/`: vectors with
expected values worked out by hand from the rules above, a small Python
reference that has to agree with them, and a list of deliberate breakages of
that reference, each of which a vector has to notice. Writing the expected
values by hand found a fault in the reference, and changed section 7.2.

## 12. What happens to 1.x

| 1.x | 2.0 |
| --- | --- |
| `IModel`, `ITransform` | One block interface |
| Edges | Gone; a signal is named as an input |
| `tick(dt)` | `tick()`; the period is fixed at compile |
| Models run first, then edges | One sorted order |
| Signal: a number and a unit | A number, a state, and for inputs a sample time |
| Unwritten signal reads 0.0 | Unwritten signal is `not_ready` |
| Rules and commands | Removed, pending section 4 |
| Unknown keys ignored by the loaders | Refused |
| Thermal, process, mechanical and motor models; the transforms | Kept as block types, the maths unchanged |
| Units, namespace, loaders, diagram tool | Kept, adapted to ports |
| The server protocol | Changes with the above |

## 13. Order of work

1. This document is argued to agreement, section by section.
2. The conformance vectors are written for sections 3 to 7.
3. The core is rebuilt against them: store, compiler, engine, block
   interface.
4. The existing models and transforms move across as block types, each
   keeping its analytical validation.
5. The loaders, the server and the simulator provider follow.

## Appendix A. A first catalogue

**Proposed.** Enough block types to test the rules above. Names, ports and
settings are placeholders for argument; the behaviour is what the vectors
pin down. Times are in seconds unless a setting says otherwise.

| Type | Inputs | Settings | Outputs |
| --- | --- | --- | --- |
| `formula` | any, named in the formula | `expr` | `y` |
| `all_good` | any | none | `y` |
| `delay` | `x`, read from the previous tick | `ticks` (1), `initial` (none) | `y` |
| `window` | `x` | `window`, `min_good` (1) | `mean`, `median`, `min`, `max`, `spread`, `slope` |
| `deadband` | `x` | `step`, `ride_through` (0) | `y` |
| `held_for` | `x` | `time`, `on_bad` | `y` |
| `since_true` | `x` | `time` | `y` |
| `latch` | `set` | none | `y` |
| `total` | `x` | `per` (1 s) | `y`, `missed` |
| `kalman1` | `z`, `model` | `tau`, `q`, `r` | `x`, `sigma` |

A setting with a value in brackets may be left out and takes that value.

- **`formula`.** Numbers, the block's input names, `+ - * /`, unary minus,
  the six comparisons, `and`, `or`, `not`, `abs(a)`, `min(a, b)`,
  `max(a, b)` and `when(condition, a, b)`. A comparison or a logical
  operator gives 1 or 0. Section 7.1 governs states.
- **`all_good`.** 1 when every input is usable, else 0. Always `good`.
- **`delay`.** At tick `k` its output is its input at tick `k - ticks`, state
  included. Before that tick exists, its output is `initial` and `good`, or
  `not_ready` if no initial value is given.
- **`window`.** `window` is a whole number of periods, `n`. At a tick the
  window is that tick and the `n - 1` before it. `median` of an even number
  of samples is the mean of the middle two. `spread` is `max - min`. `slope`
  is the least-squares slope of value against tick time, per second.
  Section 7.2 rules 1 to 4 govern states.
- **`deadband`.** Section 7.2 rules 5 and 6.
- **`held_for`.** Section 7.3 rule 1. The timer starts on the tick its input
  becomes true, and the output is true on a tick whose time is more than
  `time` after that.
- **`since_true`.** Section 7.3 rule 2. Its clock is set to the tick's time on
  the first tick and on every tick where the input is true.
- **`latch`.** Section 7.3 rule 3.
- **`total`.** Section 7.4. On a usable tick it adds `x × period / per`.
  `missed` is in seconds.
- **`kalman1`.** One state, relaxing toward `model` with time constant `tau`
  and corrected by `z`. With `a = 1 - period / tau`, process noise `q` per
  second and measurement variance `r`:
  - first usable `z`: `x = z`, `var = r`; nothing else happens on that tick;
  - on each later tick, first predict: with `model` usable,
    `x = a·x + (1 - a)·model` and `var = a²·var + q·period`; otherwise `x`
    is unchanged and `var = var + q·period`;
  - then, with `z` usable, correct: `k = var / (var + r)`,
    `x = x + k·(z - x)`, `var = var·(1 - k)`.

  `sigma` is the square root of `var`. Section 7.5 governs states.

A block may carry `fallback`, a map from an output port to a number
(section 7.6).

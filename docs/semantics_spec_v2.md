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
   as an input.
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

**Proposed.** The default is that a problem is never hidden.

1. **A block with no state** (a formula, a gain, a comparison): its output
   takes the worst state among its inputs, `bad` over `not_ready` over
   `good`.
2. **Logic is three-valued.** One true operand decides an `or` and one false
   operand decides an `and`, whatever the others are. Otherwise an operand
   that is not good makes the result not good.
3. **A block with state has no default.** Each such block type has a
   required setting, `on_bad`, and a graph that leaves it out does not
   compile. The choices a type may offer:
   - `skip`: the bad sample is ignored and the state is left as it was.
   - `reset`: the state is cleared, and the block starts again.
   - `hold`: time-based state keeps running through the bad stretch.
4. **What the output is while the input is not good** is part of each block
   type's definition, not left to the implementation. The starting table:

   | Block | Input not good, and | Output |
   | --- | --- | --- |
   | Window statistic | `skip` | Statistic of the samples it has, `not_ready` until full |
   | Window statistic | `reset` | `not_ready` until the window refills |
   | Timer on a condition | `reset` | The input's state |
   | Timer on a condition | `hold` | `good`; true once the time has run out |
   | Running total | `skip` | The total so far, `good` |
   | Deadband, median | (not yet decided) | See Open |
   | Estimator | A missing measurement | Predicts without correcting; `good`, with a wider uncertainty |

5. **A fallback is explicit.** A block may name a value to give when an
   output is not good. It applies to one named output, not to the whole
   block.
6. **A value that is not a number.** An input whose state is `good` and
   whose value is not finite is treated as `bad`.

**Open.**

- **Blocks that hold a last good value** (a median, a deadband, a
  sample-and-hold). Reporting the old value as `good` through any length of
  bad input hides the problem; reporting `bad` at once loses the point of
  the block. Proposed: they take `on_bad` like any other stateful block,
  with `hold` limited by a stated time. Settled by: the rule table completed
  for every block type in the first catalogue, each row with a test vector.
- **Whether `not_ready` and `bad` should ever be treated differently** by a
  stateful block's policy, or always alike.

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
    type: median
    in: { x: heater/pad_c }
    settings: { samples: 3, on_bad: skip }
    out: { y: heater/pad_filtered_c }
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
2. Every row of the table in section 7, and every numbered rule in sections
   3 to 6, has at least one vector that fails if the rule is broken. A
   vector is accepted only after a deliberately broken implementation has
   been shown to fail it.
3. Expected values are worked out independently of the implementation under
   test.
4. A second implementation passes the same vectors. The vectors are the
   contract between them.

The format already exists as a prototype: tab-separated inputs and expected
outputs per tick, written by a Python reference and replayed by a C++
runner. On the experiment described in section 1 it caught sixteen of
sixteen deliberate breakages once two missing vectors were added.

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

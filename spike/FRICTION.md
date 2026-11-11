# Friction log

What came of writing the ten signal blocks against FluxGraph's public
interface as it stands. `README.md` has the question and the method.

## Result

It works. With nothing changed under `include/` or `src/`, the ten blocks run
as FluxGraph models and match the test vectors at every tick, by state and by
value:

```text
vector          ticks outputs compared  state differs  value differs  largest difference
all_good           60       1       60              0              0                   0
cases            1700      17    28900              0              0            6.04e-14
deadband           60       1       60              0              0                   0
expr_divide        60       1       60              0              0                   0
held_hold          80       1       80              0              0                   0
held_reset         80       1       80              0              0                   0
integrate          60       1       60              0              0                   0
kalman1            60       2      120              0              0                   0
latch              80       1       80              0              0                   0
median             60       1       60              0              0                   0
since_true         80       1       80              0              0                   0
window_reset       60       3      180              0              0            3.55e-15
window_skip        60       3      180              0              0            7.11e-15
ALL THE SAME
```

`build/spike/spike_runner spike/vectors`, GCC 14.2.0, Release. The `cases`
vector is the nine cases of the anolis exercise as 22 blocks; one run of its
1,700 ticks takes 0.08 s of wall time, reading the files included.

The comparison was checked by breaking `blocks.cpp` sixteen ways, one at a
time. The runner failed on fourteen. The two it missed (a not-ready input to
`all_good`, and a division by zero) had no vector; `all_good` and
`expr_divide` were added and all sixteen now fail.

What that result does and does not show: the engine's lifecycle (compile,
load, tick), its namespace and its store carry a block graph without
complaint. Every block had to be a model, and the list below is what the
model interface does not give a block.

## Entries

Each: what a block needs, what the interface offers, the workaround used
here, and the smallest change to the library that would remove it.

### 1. A signal is one number

- **Needed.** A value on a wire is good, not ready or bad, and a block reads
  the state with the value.
- **Offered.** `Signal` is a `double` and a unit string.
- **Workaround.** Every wire is two signals, `x` and `x#state`, the second
  holding 0, 1 or 2 as a double. The namespace is twice the size, a state
  can be written without its value, and nothing stops a block reading one
  and not the other.
- **Change.** A signal carries its state. Later, its time.

### 2. A signal nobody has written reads as 0.0

- **Needed.** A block must be able to tell "no value yet" from zero.
- **Offered.** `SignalStore::read_value` returns `0.0` for an unwritten or
  invalid id.
- **Workaround.** `NOT_READY` is encoded as 0, so that an unwritten state
  signal happens to mean the right thing. The encoding is chosen to fit a
  default, which is backwards.
- **Change.** Reading an unwritten signal gives the not-ready state. Follows
  from 1.

### 3. The compiler neither orders models nor sees their inputs

- **Needed.** Blocks evaluated in dependency order, and a loop refused unless
  it passes through a delay.
- **Offered.** Models run in the order the spec lists them. `IModel` tells
  the compiler its outputs (`output_signal_ids`) and not its inputs, so the
  compiler cannot order models, and its cycle check covers edges only.
- **Workaround.** The vector files list the blocks already in dependency
  order, worked out by the Python engine.
- **Measured.** Two blocks that read each other's output compile and run
  with no error. Each sees the other's value from the previous tick.
- **Change.** A block declares its inputs as well as its outputs, and all
  blocks are sorted and loop-checked together. This is the largest change,
  and it is to the compiler and the engine, not to any block.

### 4. Only a model can do what a block does

- **Needed.** One kind of computing element with named inputs and outputs.
- **Offered.** Two kinds. An edge has one source, one target and an
  `ITransform` that maps a `double` to a `double`. A model sees the whole
  store. Edges run after all models, so a model reads an edge's output a
  tick late.
- **Workaround.** All ten blocks are models, including the two with one
  input (`median`, `deadband`). None of FluxGraph's nine transforms could
  be reused: a transform cannot see a state.
- **Change.** One block abstraction. A transform becomes a block with one
  input and one output; a model becomes a block with several.

### 5. A model does not know the period, or the time

- **Needed.** A window's length in samples, and the time of a tick.
- **Offered.** `tick(dt, store)`. The compiler takes an `expected_dt` and
  does not pass it to the factories.
- **Workaround.** `window_stats` works out its sample count on its first
  tick. Every block counts its own ticks and multiplies by `dt` to get the
  time.
- **Change.** A block is given the period when it is built and the tick's
  time when it runs.

### 6. Inputs and outputs are not part of a model's spec

- **Needed.** A spec that says which signals a block reads and writes.
- **Offered.** `ModelSpec` is an id, a type and a parameter map. Each
  built-in model names its signals through parameters of its own
  (`temp_signal`, `power_signal`).
- **Workaround.** A convention inside the parameter map: `in.<name>`,
  `p.<setting>`, `fallback`. Output paths are the block id and the port
  name. Everything travels as a string.
- **Change.** A block spec with input and output ports beside its settings.
  This is what makes 3 possible.

### 7. Units are carried and not used

- **Needed here.** Nothing; the vectors have no units.
- **Offered.** Unit contracts per signal, checked on write.
- **Workaround.** Every wire is written as dimensionless, state signals
  included.
- **Change.** None forced by this spike. Units on block ports is a design
  question for the anolis RFC, not a defect found here.

### 8. Parts of the interface a block has no use for

- `compute_stability_limit`: every block returns infinity. The engine calls
  it for every model on every tick.
- `reset` and `describe`: implemented as empty and as the id.
- Rules and commands: unused.
- The factory registry is one per process and refuses a second registration
  of a type, so the blocks register as `blk_<type>` once at start.

None of these blocked anything.

## What a change would touch

Lines under `include/` and `src/` at `1fee595`, counted with `wc -l`:

| Part | Lines | What happens to it |
| --- | --- | --- |
| Engine, compiler and its sort, graph spec, signal store, the two interfaces | 1,550 | Redesigned: entries 1 to 6 all land here |
| Models, transforms and their registration | 2,663 | Kept, and re-expressed as blocks: the maths does not change, the way each reads and writes does |
| Loaders, units, namespace, parameter helpers, dimensional checks | 1,625 | Kept; the loaders gain the new spec shape |
| Everything | 6,095 | |

So about a quarter of the library is the part that has to change shape, and
it is the part that defines what the library is.

## Not tested here

- Anything about time beyond a fixed period: jitter, a late sample, two
  rates.
- A formula parser. Each formula is a C++ function here.
- Bad-input rules beyond the ones the Python engine chose. The vectors are
  that engine's behaviour, and a wrong rule there is a wrong expectation
  here.
- arm64. This ran on x86-64 only.

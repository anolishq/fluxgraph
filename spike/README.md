# Spike: signal blocks on FluxGraph as it is

Experimental branch `spike/signal-blocks`. Not for merge. Nothing under
`spike/` is built by the presets CI uses, and the library is unchanged.

## The question

Anolis's derived-signals RFC (`docs/rfcs/derived-signals.md` in the anolis
repository, open decision O11) asks whether its engine should be new code,
FluxGraph extended, or a core both share. This spike measures the middle
option before anyone argues it:

> Written against FluxGraph's public interface as it stands, where does a
> graph of signal-processing blocks fit, and where does the design resist?

## Method

1. **The blocks.** The ten block types from the RFC's Python spike
   (`tools/derived-signals/engine.py` in anolis): `median`, `expr`,
   `all_good`, `since_true`, `latch`, `held_for`, `window_stats`, `deadband`,
   `kalman1`, `integrate`. Each is written here as a FluxGraph `IModel` or
   `ITransform`, registered through `GraphCompiler`, and wired with a
   `GraphSpec`. No file under `include/` or `src/` changes.
2. **The target behaviour.** Test vectors written by the Python spike: input
   samples per tick, each good, not ready or bad, and the expected value and
   state of every published signal per tick. The vectors are synthetic, so
   they need no recorded data.
3. **The comparison.** A runner here feeds a vector to the engine one tick at
   a time and compares every output at every tick, by state and by value.
4. **The friction log.** Every place the current design forced a workaround
   is recorded in `FRICTION.md` as it is met: what was wanted, what the
   interface offers, what the workaround was, and what a change to the
   library would have to be.

A formula block needs an expression parser, which has nothing to do with
FluxGraph's design. Here each formula is a small C++ function registered by
name.

## What counts as an answer

- The blocks that fit unchanged, the ones that fit with a workaround, and
  the ones that do not fit.
- For each workaround, the smallest change to the library that removes it.
- A count of what in `include/` and `src/` those changes touch, set against
  what stays as it is.

That count goes back to the RFC as the evidence for O11.

## Baseline

`spike/signal-blocks` at `1fee595` (main, 2026-11-10), GCC 14.2.0:

```bash
cmake --preset ci-linux-release
cmake --build --preset ci-linux-release --parallel
ctest --preset ci-linux-release
```

288 of 288 tests pass. The build takes about 16 s on the development
machine.

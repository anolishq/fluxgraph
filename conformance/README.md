# Conformance for the version 2 semantics (proposal)

Tests of [the version 2 proposal](../docs/semantics_spec_v2.md), not of the
library. Nothing here is built or run by the library's presets.

| Path | What it is |
| --- | --- |
| `vectors/` | One YAML file per case: a graph, what is written to its inputs at each tick, and the state and value expected of each output. |
| `reference.py` | A small Python reading of the proposal. Stdlib only. Not the library, and shares no code with it. |
| `second/` | A second reading, written from the proposal's text alone, without sight of the reference or the vectors. `ASSUMPTIONS.md` lists what the text did not settle. |
| `run.py` | Runs the vectors against the reference, or with `--second` against the second reading. Needs PyYAML. |
| `mutate.py` | Breaks the reference one rule at a time and checks that a vector notices. |
| `compare.py` | Runs the two readings side by side on random inputs and compares every output at every tick. |

```bash
python3 conformance/run.py            # every vector agrees with the reference
python3 conformance/run.py --second   # and with the second reading
python3 conformance/mutate.py         # every breakage is noticed
python3 conformance/compare.py        # the two readings never differ
```

## How the vectors were made

The expected values in a vector were worked out by hand from the rule it
names, with small numbers and a one-second period, and written down before
the reference was run. The reference then had to agree. Where it did not,
one of the two was wrong:

- A delay fed straight from an external input came out one tick short in
  the reference. The vector was right.
- Working window cases by hand showed that the proposal's "skip" and
  "reset" policies for a window came to the same thing once a window was
  defined by time. Section 7.2 was rewritten around `min_good`.

A vector is kept only if a broken reference fails it. `mutate.py` holds the
breakages, each named for the rule it breaks. A breakage that no vector
would notice means a missing vector: four were added that way.

## The second reading

The hand-worked values and the reference have one author, so agreement
between them shows less than it seems. `second/impl.py` was written from the
proposal and nothing else. As first written:

- it agreed with all 35 vectors that existed then;
- run beside the reference on 290,000 random comparisons, with inputs that
  were missing, bad, not ready, not finite and stale, it never differed;
- writing it turned up 72 places where the text did not say what to do.

Those 72 went back into the proposal as stated rules, and each new rule got
a vector: fifteen more. Against those fifteen the second reading, still as
first written, differed on one, a chained comparison, which it had assumed
was allowed and the proposal now refuses. Three lines of it were then
changed to follow the proposal where it had guessed otherwise: that one,
`kalman1`'s `model` input being required, and the period allowed for a
`kalman1`.

`compare.py` was itself checked by running it against six broken copies of
the reference. It reported differences every time.

The format of a vector is described at the top of `run.py`.

## What this does not cover

- **Tie-breaking by block id** (section 5.2). The order among blocks that do
  not depend on each other does not change any output, so no vector can see
  it.
- **Units** (section 10), which the reference ignores.
- **Timing of the host**: late ticks, and sample times that differ between
  inputs beyond what a maximum age catches.
- **The library.** Nothing here runs FluxGraph. A runner for the library
  comes with the rebuilt core.

- **Refusing a saved state from a different graph** (section 8.3). The
  vector format has one graph per file.
- **Two writes to one input between ticks.** A vector writes once per tick.

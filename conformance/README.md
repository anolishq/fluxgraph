# Conformance for the version 2 semantics (proposal)

Tests of [the version 2 proposal](../docs/semantics_spec_v2.md), not of the
library. Nothing here is built or run by the library's presets.

| Path | What it is |
| --- | --- |
| `vectors/` | One YAML file per case: a graph, what is written to its inputs at each tick, and the state and value expected of each output. |
| `reference.py` | A small Python reading of the proposal. Stdlib only. Not the library, and shares no code with it. |
| `run.py` | Runs the vectors against the reference. Needs PyYAML. |
| `mutate.py` | Breaks the reference one rule at a time and checks that a vector notices. |

```bash
python3 conformance/run.py       # every vector agrees
python3 conformance/mutate.py    # every breakage is noticed
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

The hand-worked values and the reference have the same author. A second
implementation written from the proposal alone is the check on that.

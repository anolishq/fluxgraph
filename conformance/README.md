# Conformance for the version 2 semantics (proposal)

Tests of [the version 2 proposal](../docs/semantics_spec_v2.md), third
revision, not of the library. Nothing here is built or run by the library's
presets.

| Path | What it is |
| --- | --- |
| `vectors/` | One YAML file per case: a graph, the calls a host makes to it with what it writes before each, and the state and value expected of each output. |
| `reference.py`, `formula.py` | A small Python reading of the proposal: the engine and blocks, and the formula language. Stdlib only. Not the library, and shares no code with it. |
| `second/` | A second reading, written from the proposal's text alone, without sight of the reference, the vectors or any earlier draft. `ASSUMPTIONS.md` lists what the text did not settle. |
| `run.py` | Runs the vectors against the reference, or with `--second` against the second reading. Needs PyYAML. |
| `mutate.py` | Breaks the reference one rule at a time and checks that a vector notices. |
| `compare.py` | Runs the two readings side by side on random inputs and call times and compares every output after every call. |

```bash
python3 conformance/run.py            # 153 vectors: ALL AGREE
python3 conformance/run.py --second   # 153 vectors: ALL AGREE
python3 conformance/mutate.py         # 287 breakages: 287 noticed; every vector failed by one
python3 conformance/compare.py        # 888107 comparisons, 0 differences
```

The format of a vector is described at the top of `run.py`.

## How the vectors were made

The expected values in a vector were worked out by hand from the rule it
names, with small numbers and mostly a one-second period, and written down
before the reference was run. The reference then had to agree. Working them
changed the proposal in four places:

- A deadband that kept its sample on an uncertain input gave it as `good`.
  Rule 7.4.2 now makes the output uncertain when the input is.
- An estimator's sensitivity was to be taken by a numerical difference.
  A value worked by hand could not match that to nine places, and neither
  could two implementations. A model now states its sensitivity.
- "A total past `max_missed` goes on adding" could not be seen by any
  output, and was removed.
- What had been written and not taken up when a state is restored was not
  spoken for. It is dropped.

A vector is kept only if a broken reference fails it. `mutate.py` holds the
breakages, each named for the rule it breaks, and lists any vector that no
breakage fails. Review of the second revision found fifteen breakages of
stated rules that its vectors let through. Each of those that still names a
rule of this revision is in `mutate.py` now, with a vector that fails it.

## The second reading

The hand-worked values and the reference have one author, so agreement
between them shows less than it seems. `second/impl.py` was written from
the proposal's text as it stood, by a reader who had seen nothing else, with
its own formula parser. As first written:

- It agreed with 145 of the 151 vectors that existed then. Five of the six
  it refused because the text gave a state-space model's states no names:
  it called them `x1` on, the reference `x0` on. The sixth was a refusal
  whose wording a vector had pinned too closely.
- With the names made the same, it was run beside the reference on 846,283
  random comparisons and differed on 10,085.
  - At a period of 1 s, 10 differences, all one rule: whether a delay's
    initial value, not yet given, comes into doubt at a gap.
  - At a period of 0.1 s, the rest, from that rule and one other cause: a
    tick exactly half a period after a call fell on either side of "due",
    because that test had no slack and a tenth is not exact in binary. Once
    two readings disagree on how many ticks ran, everything after differs.
- Writing it turned up 106 places where the text did not say what to do
  (`second/ASSUMPTIONS.md`, kept as first written).

What was done about it:

- The proposal now names the states, gives the due test the slack the
  other time comparisons have, and says a delay's initial value is not
  changed by a gap.
- One of its assumptions showed a rule that both readings had read alike
  and that was wrong: an estimator stepped its model on this tick's inputs
  where a model block steps on the last tick's. Rule 7.9.2 was changed.
- Eight further sentences state what the text had left to the reader.
- The second reading was changed in four places to follow the proposal as
  changed: the names, the slack, the delay and the estimator's inputs. The
  reference was changed in four: the slack, the estimator's inputs, and two
  rules the second reading had chosen and the proposal then took, the
  sample time of a value a fallback puts in and a restore of a state saved
  before any tick.

`compare.py` was itself checked by running it against broken copies of the
reference.

## What this does not cover

- **A fault both readings share.** `compare.py` only compares them. The
  estimator's inputs, above, were one.
- **Tie-breaking by block id** (rule 5.2). The order among blocks that do
  not depend on each other does not change any output, so no vector can see
  it.
- **Units** (section 10), which both readings ignore.
- **Refusing a saved state from a different graph** (rule 8.2). The vector
  format has one graph per file.
- **That a restore puts the tick's number back.** Every block treats a
  restore as a gap, so no output can show it.
- **What a host may not do.** A write to a name that is not an input, a
  write of the wrong type: the proposal does not say, and the two readings
  were not compared on it.
- **Stability of blocks together** (section 7.8, open).
- **The library.** Nothing here runs FluxGraph. A runner for the library
  comes with the rebuilt core.

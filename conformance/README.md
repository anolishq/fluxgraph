# Conformance for the version 2 semantics (proposal)

Tests of [the version 2 proposal](../docs/semantics_spec_v2.md), second
revision, not of the library. Nothing here is built or run by the library's
presets.

| Path | What it is |
| --- | --- |
| `vectors/` | One YAML file per case: a graph, the calls a host makes to it with what it writes before each, and the state and value expected of each output. |
| `reference.py` | A small Python reading of the proposal. Stdlib only. Not the library, and shares no code with it. |
| `second/` | A second reading, written from the proposal's text alone, without sight of the reference or the vectors. `ASSUMPTIONS.md` lists what the text did not settle. |
| `run.py` | Runs the vectors against the reference, or with `--second` against the second reading. Needs PyYAML. |
| `mutate.py` | Breaks the reference one rule at a time and checks that a vector notices. |
| `compare.py` | Runs the two readings side by side on random inputs and compares every output after every call. |

```bash
python3 conformance/run.py            # every vector agrees with the reference
python3 conformance/run.py --second   # and with the second reading
python3 conformance/mutate.py         # every breakage is noticed
python3 conformance/compare.py        # the two readings never differ
```

The format of a vector is described at the top of `run.py`.

## How the vectors were made

The expected values in a vector were worked out by hand from the rule it
names, with small numbers and mostly a one-second period, and written down
before the reference was run. The reference then had to agree. Where it did
not, one of the two was wrong:

- A slope over a window with two holes was worked wrongly by hand. The
  reference was right.
- A sample stamped in the future never grew old, in the proposal as well as
  in the reference. Rule 7.2.4 now refuses one more than a period ahead.
- At a period of 0.1 s, a host calling exactly on time would run no tick
  on its fourth call and two on its fifth, one of them missed, because
  three periods of 0.1 come to more than 0.3. Rule 6.4 now gives each call to the
  tick nearest it.

A vector is kept only if a broken reference fails it. `mutate.py` holds the
breakages, each named for the rule it breaks, and also lists any vector
that no breakage fails. A breakage that no vector notices means a missing
or a weak vector. Seven vectors were added or tightened that way; in one
case the fault was in the reference, where a loop of direct inputs was
caught by the type check before the loop check ever ran.

## The second reading

The hand-worked values and the reference have one author, so agreement
between them shows less than it seems. `second/impl.py` was written from
the proposal and nothing else, with its own formula parser. As first
written:

- It agreed with 107 of the 109 vectors that existed then. The other two
  were faults in the vectors: each published a signal named `on`, which
  YAML reads as `true`. The second reading refused a signal name that is
  not text. The reference had let it through.
- Run beside the reference on 626,992 random comparisons, it differed on
  133, all from one rule: what a hysteresis gives for an unusable input
  before its input has met a threshold. The text said two things.
- Writing it turned up 98 places where the text did not say what to do
  (`second/ASSUMPTIONS.md`, kept as first written).

What was done with the 98:

- The proposal now states the ones where two honest readings could come
  apart. The hysteresis rule was rewritten. The number of samples a window
  needs is now rounded, so that 0.07 of a hundred ticks is seven. A length
  of time without a unit, a constant that is not finite, a number too large
  for a double and a signal name that is not text are refused. The formula
  grammar is given as a grammar.
- Six vectors cover what that added.
- Two places in the second reading were then changed to follow the
  proposal where it had chosen otherwise: the hysteresis rule and the
  rounding. The reference was changed in six places where the second
  reading had been the stricter and the proposal now agrees with it.

`compare.py` was itself checked by running it against 21 broken copies of
the reference. It reported differences every time.

## What this does not cover

- **Tie-breaking by block id** (rule 5.2). The order among blocks that do
  not depend on each other does not change any output, so no vector can see
  it.
- **Blocks with state and no rule of their own** (section 7.8). No block of
  the first catalogue falls under it. The models carried over from 1.x
  will.
- **Units** (section 10), which both readings ignore.
- **Refusing a saved state from a different graph** (rule 8.3). The vector
  format has one graph per file.
- **What a host may not do.** A write to a name that is not an input, a
  write of the wrong type, a time that is not a number: the proposal does
  not say, and the two readings were not compared on it.
- **The outputs of a missed tick.** A call gives the outputs of the last
  tick it ran.
- **The library.** Nothing here runs FluxGraph. A runner for the library
  comes with the rebuilt core.

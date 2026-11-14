# Assumptions made in bringing `impl.py` up to Amendment 8

Rule numbers and quotations are from `spec.md`. Each example was run on
`impl.py`.

## What each hunk needed

| Passage | Code changed? |
| --- | --- |
| Rule 6.11, refused whole; after the last tick number; a tick that stays due | No. The last tick a call would run is checked before anything changes, and the ticks before it are earlier and smaller, so if it fits they do. A rebase, with or without a length, and a restore leave the last number as it was, so the call after them is refused too |
| Rule 7.3.8, an unusable input under `only_new` counts as its state | No |
| Appendix A, a number too small for a double is zero | No |
| Appendix A, a formula nested at least 100 deep | Yes: one nested too deep is now refused when the graph is compiled. Before, a long one compiled or crashed, and could crash when it ran |
| Appendix A, a delay's type on a loop is its initial value's | No |
| Appendix A, `integrate`'s ratio worked once, exactly | Yes: it was `x * period / per` in doubles, which gave 1.0000000000000002 for the text's example |

## Where the text had to be guessed

1. **How deep this engine reads, and what counts.** "An engine reads a
   formula nested at least 100 deep, counting each bracket, function and
   operator that is inside another, and may refuse one nested deeper than
   it can read."
   *Chosen:* `impl.py` counts the depth of the tree of operators and
   functions it builds, in which a bracket adds nothing, and refuses a
   formula whose tree is more than 200 deep; it also refuses one whose
   brackets are too deep for Python to parse (some thousands). An
   operator that groups from the left counts the operators to its left
   as inside it: `a + a + a` is two deep. So a sum of 201 terms is the
   longest it takes without brackets, and a sum of 3,000 is refused. A
   formula counted as the text counts, brackets among it, at 100 deep has
   a tree of at most 100, and is read. Two engines with different depths
   differ on which long formulas they refuse, which the text allows.

2. **The ratio as a double.** "The ratio is worked once, exactly, and
   then taken as a double". *Chosen:* the period in whole nanoseconds
   over `per` as the exact length it is written as (it may be a fraction
   of a nanosecond, rule 6.3), rounded once to the nearest double; a
   tick adds `x` times that. With no `per` the ratio is the period over
   one second.

3. **A call that runs no tick, at the last tick number.** "every call
   that would run a tick is refused". *Chosen:* a call for which no tick
   is due is not refused and runs none, as before. After a rebase the
   next call always runs a tick, so it is refused whatever its `now`.

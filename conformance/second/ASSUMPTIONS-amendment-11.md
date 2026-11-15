<!-- markdownlint-disable MD029 -- entries keep one numbering -->
# Assumptions made in bringing `impl.py` up to Amendment 11

Every place where "Smaller faults" (rules 3.8, 7.7.2 and 7.8.8, the
`integrate` row of the table in section 8, and section 7.11) left a
choice or could be read two ways, and what `impl.py` does. Entries 1 to 8
were written before the vectors were run. Quotations are from
`docs/semantics_spec_v2.md`.

1. **Rule 3.8, the reason.** "In this revision every block gives 0 ...
   What an engine hands its host, and what a save holds, need not carry
   it while that is so." *Chosen:* nothing is implemented. A value in
   `impl.py` has no reason, and a write takes none.

2. **Rule 7.7.2, past `max_missed`.** *Chosen:* the total is `uncertain`,
   with its value, from the tick `missed` is first more than `max_missed`
   until a reset, on a tick with an unusable input too; it goes on adding
   every usable input. After a gap of no known length the same, where
   `max_missed` is given, with `missed` unchanged. The four counts stay
   `good`. No output of an `integrate` is `bad` now but by rule 3.6.

3. **Rule 7.8.8, "through formulas alone".** "One block takes another's
   output through formulas alone where it reads an output of a formula
   that reads the other's, or that reads a formula's that does, and so
   on; an input counts whether it is direct or deferred." *Chosen:* a
   chain of formulas of any length, each reading the next on any of its
   ports; the formulas need not themselves be on the loop (they always
   are, where the pair is mutual). A formula on the chain may read other
   things as well.

4. **Which pairs are looked at.** "no two model blocks in it". *Chosen:*
   every pair of model blocks on the same loop. Each direction is tested
   by itself: a pair is refused only where A takes B's so and B takes A's
   so. A pair with a delay, a `pid`, a `rate_limit` or any block that is
   not a formula on every path in one direction is accepted, whatever the
   other direction is.

5. **A model block that takes its own output**, directly or through
   formulas. It is one block and not a pair. *Chosen:* accepted, with
   `settle`, as before this amendment.

6. **"The same `settle`."** *Chosen:* written on every model block of the
   loop, and equal as whole numbers of ticks.

7. **An estimator.** "An estimator hosts a model but is not a model
   block". *Chosen:* it is no party to a pair, and a loop with a model
   block and an estimator is refused as before.

8. **"Every model block in it is `uncertain` for `settle` after the
   loop's doubt."** *Chosen:* each uses the loop's doubt in place of its
   own, as the one model block did; a model block on the loop that steps
   on an `uncertain` value passed to it by another block of the loop
   starts nothing, and its own `doubtful` counts that step all the same.

## After the vectors were run

No vector disagreed (497 of 497), so nothing above was changed. What I
think the text leaves unsaid or gets wrong, each run on `impl.py`:

9. **A ring of three model blocks, each taking the next directly, is
   accepted.** Rule 7.8.8 refuses a pair "that each take the other's
   output". Run: masses `a`, `b`, `c` with `a` reading `c`, `b` reading
   `a` and `c` reading `b`, each with `settle`: no two take each other's
   output, and the graph compiles. It is one physical network cut in
   three, each block a tick behind the one it reads, and it is the
   mistake the rule is written against. Section 7.11 owns to a pair
   through a delay; it does not own to this.

10. **A coupling through a block that changes nothing is accepted.** Run:
    a pair with a `deadband` of `step: 0` on the way in one direction
    compiles. Section 7.11 names "a rate limit that never limits"; the
    same goes for a deadband of zero, a low-pass, a window of one tick.
    This is as the text says, and I list it only as one more of the
    kind.

11. **A formula that does not use the other's value still makes a pair.**
    Run: `a` reads a formula `0 * t + 20` of `b`'s output and `b` reads
    `a`: refused. The rule goes by what is connected and not by what is
    used, which I think is right for a check made when the graph is
    compiled; the text says "reads" and so agrees.

12. **Rule 7.7.2 says "until a reset" of a state that `missed` alone
    already gives.** After a reset `missed` is zero, so the first clause
    needs no memory; only the gap of no known length does. Nothing is
    wrong; a reader implementing it may think two flags are needed where
    one is.

## After the first bullet of rule 7.8.8 was reworded

Entry 9 is settled: "no model blocks in it are joined in a ring directly
or through formulas alone: no two each take the other's output so, and no
three or more each take the next's and the last the first's." `impl.py`
now refuses any such ring. Entry 4 is replaced by 13.

13. **What a ring is.** *Chosen:* among the model blocks of one loop,
    draw an arrow from each to every other whose output it takes directly
    or through formulas alone; a ring is any closed walk along arrows
    through two or more different model blocks. It is found as: some
    model block can get back to itself along arrows. Rings that share a
    block, or a ring with other model blocks hanging off it, are refused
    for the ring.

14. **A model block that takes its own output.** The bullet lists "no
    two" and "no three or more", and not one. *Chosen:* one block that
    takes its own output, directly or through formulas, is no ring, and
    is accepted with `settle` (rule 7.8.8's opening says "A block that
    reads its own output is one [loop] by itself"). Its arrow to itself
    is left out when rings are looked for, so it does not make a ring of
    a pair it is otherwise not in.

15. **Which blocks the error names.** "the error names them". *Chosen:*
    every model block that lies on a ring with the first one found, in
    order of id. Where two rings share a block, it names the blocks of
    both.

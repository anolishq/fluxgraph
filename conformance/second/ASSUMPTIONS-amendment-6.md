<!-- markdownlint-disable MD029 -- entries keep one numbering -->
# Assumptions made in bringing `impl.py` up to Amendment 6

Amendment 6 ("the whole text, read cold") changes passages throughout.
This file says, hunk by hunk, whether `impl.py` already did what the text
now says; then every place the amended text left a choice or could be read
two ways, with the reading taken. Rule numbers are those of `spec.md`.
Quotations are from `spec.md`. Each example was run on `impl.py`.

## What each hunk needed

| Passage | Code changed? |
| --- | --- |
| Rule 3.6, a statistic is a plain sum in doubles | No: a window's mean was already a sum from the oldest sample to the newest, and one that is not finite is `bad` |
| Rule 3.7, inputs counted by port | No: a formula already counted the ports given a signal |
| Rule 6.1, a period more than zero | No |
| Rule 6.2, every length fits in 64 bits | Yes: the period, a counted length, a maximum age and `max_ahead` of 2⁶³ ns or more are refused |
| Rule 6.3, rounding with no tolerance; the decimal as written | Yes: a window's number needed and a low-pass's default `settle` are worked in exact fractions |
| Rule 6.9 and Appendix A, `max_catch_up` and `max_waiting` at most 2,147,483,647 | Yes |
| Rule 6.11, a tick's number or time past 64 bits | Yes: the call is refused before anything changes |
| Rule 7.2.1, an initial value and a rebase | Yes: no initial value after the first rebase, until a reset |
| Rule 7.3.3, a sample a rebase took out counts as `not_ready` | No |
| Rule 7.8.5, a model block's outputs judged together | No: one state was already given to every output |
| Rule 7.8.6, how a named model's `settle` is rounded | Yes: `ceil(r - 1e-9)` in doubles, in place of "within 1e-9 of a whole number is that number" |
| Rule 7.9.3, how the first sentence groups | No: as chosen in amendment 5 |
| Rule 7.9.8, each output has a name of its own | No: two outputs of one name were already refused |
| Rule 7.9.9, `p0` once in all | No |
| Rule 8.2, what a saved state holds | No: a restore already clears what stands and what waits, forgets the clock and a pending rebase, and leaves the count of writes thrown away alone |
| Rule 9.2, names | Yes: a block id, a `linear` block's `inputs`, `states` and `outputs`, and an estimator's measurement ports are refused if empty or with a dot; so is a signal named with no text |
| Appendix A, ranges | Yes: `sigma_max` not negative; `ticks`, `over`, `max_refused` at most 2,147,483,647; `measure` at least one port |
| The rest (summaries, section 6's advice to a host, 7.11, sections 10 and 12) | No: prose |

## Where the text had to be guessed

1. **"A decimal being the decimal as it is written" (rule 6.3), for an
   engine that is handed a double.** "the number is worked exactly from
   what the graph file gives, a decimal being the decimal as it is
   written". `impl.py` is given the graph already read, with `min_good` a
   double, and cannot see the text.
   *Chosen:* a double is taken for the shortest decimal that reads back as
   that double, and that decimal times the number of ticks is rounded up
   as an exact fraction. For a number written with no more digits than a
   double keeps, that is the number as written: 0.7 over ten ticks needs
   7, 0.7000000001 needs 8, and 0.1 over ten needs 1 (the double nearest
   0.1 is a little more than a tenth, and taken as itself it would need
   2). A number written with more digits than a double keeps cannot be
   told from its neighbour: `min_good: 0.30000000000000004` over ten ticks
   needs 4 here, and an engine that reads the file's text and sees
   0.3000000000000000400 gets the same, but one that is handed
   `0.1 + 0.2` worked out by a host gets 4 where the host meant 0.3. The
   text should say that an engine given a number and not the text takes
   the shortest decimal for it, or that the loader hands the text on.

2. **Which numbers are "rounded up to a whole number of ticks or of
   samples".** *Chosen:* two are exact: a window's number needed
   (`min_good` times its ticks) and a low-pass's default `settle` (three
   of `tau` over the period, `tau` being a length as written, so the
   fraction is exact). One is not: a named model's `settle` (rule 7.8.6).
   Run, at a period of 3 s: a low-pass with `tau: 1.0000000005s` has a
   `settle` of 2 ticks (exactly 1.0000000005, rounded up), and a
   `first_order_process` with the same `tau` has 1 (`r - 10⁻⁹` is under
   1). So a `first_order_process` and the low-pass that is the same
   filter can differ by a tick in how long they are `uncertain`. That
   follows from the text; I note it because the two blocks are otherwise
   the same equation.

3. **A named model's `settle`: the arithmetic of `r`.** Rule 7.8.6: "with
   `r` three of the constant over the period, it is the least whole number
   not less than `r - 10⁻⁹`." *Chosen:* in doubles, `3.0 * constant /
   period_in_seconds - 1e-9`, rounded up, with the constant as amendment 4
   has it and the period as nanoseconds over 10⁹ rounded to a double. The
   text lets a graph within rounding of the line go either way.

4. **What a call "would run", for rule 6.11.** "a call that would run a
   tick whose number or whose time does not fit in 64 bits, signed".
   *Chosen:* the last tick the call would run is worked out first, from
   the last tick run, `now`, and a pending rebase's length; if its number
   or its time is 2⁶³ or more the call is refused before anything
   changes: no write is thrown away for being stamped ahead, a pending
   rebase stays pending, and the call does not count as the last call for
   the rule on a `now` that goes backwards. A call that runs no tick is
   not refused. Run, period 1 s, tick 0 at 0: a call at 2⁶³ - 1 ns is
   refused (the tick due is at 9,223,372,037 s); a call at
   9,223,372,036 s runs that tick; after it a call at up to 0.5 s less
   one nanosecond later runs none, and from 0.5 s later is refused, for
   good. A rebase or a reset is the only way on.

5. **A rebase whose length takes the tick's number past 64 bits.** The
   length itself fits (rule 6.11's last item), and the number is the last
   tick run plus the ticks due. *Chosen:* the call after it is refused by
   the same rule; `rebase` itself is accepted, since it runs no tick. Run:
   period 1 ns, ticks 0 and 1, `rebase(2⁶³ - 1)`: the call is refused. A
   second `rebase` with a shorter length, or a reset, clears it.

6. **"No rebase since the engine was made or last reset" (rule 7.2.1).**
   *Chosen:* a rebase is the call that runs a rebase's tick. So `rebase`
   before any tick has run, which "does away with the writes waiting, and
   nothing else", is none, and the initial value still stands in; a
   restore is followed by one, so an initial value is gone after any
   restore of a state saved after a tick; restoring a state saved before
   any tick is a reset, and brings it back. A stall is not a rebase. A
   rebase with a length, zero among them, is one. This is not part of
   what a save holds and does not need to be: a restore sets it either
   way.

7. **An input with an initial value and no maximum age, after a rebase,
   that the host does not write.** By rule 7.2.1 it is `not_ready`,
   "until the graph has run for more than the maximum age", which with no
   maximum age is never. *Chosen:* as written: `not_ready` for good. Run:
   `initial: 20`, `max_age: none`; `uncertain` 20 at tick 0; after
   `rebase(0)` it is `not_ready` at the tick that runs and a thousand
   ticks later. Section 6 tells the host to write such an input again;
   one that does not gets nothing, and nothing says so but the state.

8. **Which names rule 9.2 covers.** "A block id, and a name a block's
   settings give to a port, a state or an output, is not empty and holds
   no dot."
   *Chosen:* a block id; the `inputs`, `states` and `outputs` of a
   `linear` block; the measurement ports of an estimator's `measure`. Not
   covered, and left as they were: the ports of a `formula` (its grammar
   allows neither a dot nor an empty name already, and a port the formula
   does not use is refused); the ports of an `all_good`, which Appendix A
   says take "any names" and which are given in `in` and not in settings;
   the names of inputs from outside; and the names of published signals,
   which rule 9.2 says "are text". Run: an `all_good` with ports named
   `p.q` and the empty text, published as the empty text, compiles and
   runs. I think an empty published name is not meant, and the text does
   not refuse it.

9. **"A signal, named as text and not empty".** *Chosen:* an input port
   given the empty text is refused, also where an input from outside is
   declared with that name.

10. **The ranges with a top of 2,147,483,647.** *Chosen:* for `ticks`,
    `over`, `max_refused`, `max_catch_up` and `max_waiting`, one more is
    refused and that number itself accepted. `impl.py` does not try a
    `delay` of that many ticks: it would hold that many values.

11. **`measure` at least one port; `sigma_max` not negative.** *Chosen:*
    an empty `measure` is refused; a `sigma_max` of zero is accepted and
    makes that state's outputs `uncertain` whenever its sigma is more than
    zero.

12. **Rule 6.2, "an engine whose whole numbers are 64 bits wide sees that
    none wraps".** *Chosen:* nothing to do: Python's whole numbers do not
    wrap. An age of nearly 2⁶⁴ ns (a write stamped -2⁶³ read at 2⁶³ - 2)
    is compared as that number: `bad` with any maximum age, usable with
    none.

## After two sentences were added

- **Entry 1 is settled, as chosen.** Rule 6.3 now says: "An engine handed
  a number and not its text takes the shortest decimal that reads back as
  that number." That is what `impl.py` did; no code changed. The case of a
  host that hands over `0.1 + 0.2` stands as the text now has it: it is
  0.30000000000000004, and over ten ticks needs 4.
- **Entry 8 is settled in part, the other way for two kinds of name.**
  Rule 9.2 now says: "The name of an input and a published name are not
  empty." `impl.py` now refuses an input from outside declared under the
  empty text, and an output published under it. Both may still hold a
  dot, so long as the name is not `<block id>.<port>` for a block and
  port of the graph, which was refused already. Run: an input named
  `room.temp` and an output published as `plant.out` compile; an output
  of block `b` published as `b.y` does not.
- **Still as chosen in entry 8, and not said:** the ports of an
  `all_good`, which take "any names", may be empty or hold a dot. Run: an
  `all_good` with ports named `p.q` and the empty text compiles. The new
  sentence is of inputs and published names, and a port is neither.

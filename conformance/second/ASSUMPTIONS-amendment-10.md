<!-- markdownlint-disable MD029 -- entries keep one numbering -->
# Assumptions made in bringing `impl.py` up to Amendment 10

Every place where "A derivative and a slope between samples" (rules 7.7.7
and 7.3.6, rule 8.5, the `pid` row of the table in section 8 and the
`window` entry of Appendix A) left a choice or could be read two ways, and
what `impl.py` does. Written before the vectors were run. Quotations are
from `docs/semantics_spec_v2.md`.

## The PID's derivative (rule 7.7.7)

1. **How `dt` is formed.** "the difference of the two times, in
   nanoseconds, divided by 10^9". *Chosen:* the two times are whole
   numbers; their difference is taken as whole numbers, exactly, and that
   one whole number is divided by the double `1e9`, once. Not each time
   made seconds and then subtracted.

2. **The rest of the arithmetic.** *Chosen:* in doubles, in this order:
   `s = (measurement - remembered) / dt`; `a = exp(-dt / filter)` with
   `filter` in seconds as a double (the length as written, over 10^9);
   `f = a * f + (1 - a) * s`. `a` is worked afresh at each new sample,
   also where `dt` is one period.

3. **What is remembered when nothing is taken.** "nothing is taken and
   `f` stands". *Chosen:* the measurement and time remembered stay those
   of the sample last taken; a value written again with the same time and
   another value is not taken, and the next new sample is differenced
   against the one remembered, not against that value.

4. **"With none remembered, `f` is zero."** *Chosen:* `f` is set to zero
   at that tick, whatever it was before (after an outage, a reset or a
   gap the old `f` is gone).

5. **A stall.** Rule 7.7.7: nothing is remembered "after a gap of either
   kind"; the paragraph after the table: "At a stall, which is on one
   clock, a block keeps the sample times it remembers." *Chosen:* rule
   7.7.7 and the `pid` row: a stall starts the derivative again.

6. **A measurement whose time goes back and forth between a sample time
   and a tick's.** An input on its `initial` has no sample time and takes
   the tick's; its first write may carry a time earlier than that tick.
   *Chosen:* the rule as written: it is "a value written with ... an
   earlier" time, and is not taken until a sample later than the tick
   remembered comes.

7. **With `kd` of zero** nothing is remembered at all; nothing shows it.

8. **A PID that acts by the call.** Rule 7.7.13 says "the derivative's
   filter runs" at a catch-up tick. *Chosen:* rule 7.7.7 at every tick: a
   sample that stands through the catch-up ticks is taken once.

## A window's slope (rule 7.3.6, rule 8.5, Appendix A)

9. **A tick's time.** "the samples a window holds are from then on at
   their ticks' times, a tick's time being whole periods before the tick
   that runs". *Chosen:* at every tick, with or without a rebase, the
   time of the tick `j` ticks before the present one is the present
   tick's time less `j` periods, in whole nanoseconds. Before any rebase
   that is the tick's own time; after one it is the time the text gives.
   It is not stored: it is worked from the present tick each time, so
   after a second rebase it is whole periods before the latest.

10. **How the times are made relative.** "it is taken in seconds from the
    time of the earliest tick's sample among those the slope is of, as a
    difference in nanoseconds divided by 10^9". *Chosen:* the reference is
    the time of the sample held at the earliest tick among the samples the
    slope is of (not the earliest time, where the two differ); each
    sample's time less that, as whole numbers, divided by the double
    `1e9`. A time may come out below zero.

11. **The least-squares arithmetic.** The text does not give it.
    *Chosen:* as before this amendment: the mean of the times and the
    mean of the values, each a plain sum from the oldest tick to the
    newest over the count; then the sum of `(t - tm) * (v - vm)` over the
    sum of `(t - tm) * (t - tm)`, in that order of ticks.

12. **"Where every sample it would be of has one time".** *Chosen:*
    tested on the whole-number times, exactly, of the samples the slope
    would be of (the `good` ones where there are two or more, else the
    usable ones); then the slope is `bad`. It does not fall back from
    `good` samples at one time to usable samples at several.

13. **Which sample time a rebase forgets.** *Chosen:* every sample the
    window holds at the rebase loses its sample time for good, and is at
    its tick's time from then on; samples taken after it carry their own.
    A window with `only_new` is emptied as before.

14. **A sample's time under `only_new`.** *Chosen:* its sample time, as in
    any window.

15. **A stall.** *Chosen:* samples keep their times; the ticks passed
    over hold none.

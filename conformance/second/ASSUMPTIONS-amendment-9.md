<!-- markdownlint-disable MD029 -- entries keep one numbering -->
# Assumptions made in bringing `impl.py` up to Amendment 9

Every place where the text of "Commands, and where the actuator is" (rules
6.13, 7.4.12, 7.4.13, 7.7.13, 7.7.14, 8.2, 9.8 and Appendix A) leaves a
choice or can be read two ways, and what `impl.py` does. This is the list
for the amendment as revised after its review; it was written before the
vectors were run against the revised text. Rule numbers and quotations
are from `docs/semantics_spec_v2.md`.

Settled by the revision, and dropped from the list: which outputs are
held ("Only `y` is held"); a held output and rule 7.8.8 ("usable where it
was, whatever its block works out"); what "holds a value" is for
`limited` ("`initial` alone among them"); a zero-tick gap and waiting to
track ("but where `n` is zero"); `track` and rule 7.8.8 ("an input like
any other ... at every tick"); `track` being direct. Two were settled the
other way from what I had chosen, and `impl.py` changed: a by-call rate
limit no longer forgets at a catch-up tick, and a reset at any tick ends
a PID's waiting to track.

## Commands and held outputs (rules 6.13, 9.8)

1. **What "feeds" reaches.** *Chosen:* the whole upstream of every
   command, through any block and any port, a deferred one and a `reset`,
   `track` or `applied` among them. Every `pid` in it acts by the call.

2. **"Along a chain of such reads that passes through no `pid`."**
   *Chosen:* a `rate_limit` acts by the call if there is some chain of
   reads from it to a block that gives a command on which no block after
   the rate limit is a `pid`, the block that gives the command among
   them. A rate limit read only by a `pid`, on any of its ports
   (`setpoint`, `measurement`, `applied`, `track`, `reset` by way of a
   formula), does not. One that reaches a command both through a `pid`
   and round it does. Another `rate_limit` on the chain does not stop
   it.

3. **What is stored, and when.** *Chosen:* at every tick that is the last
   of its call, each held output's value, state and sample time as
   readers saw them (after rule 3.6 and a fallback), and whether it was
   usable before any fallback. A reset of the engine forgets them; a save
   does not hold them (rule 8.2).

4. **A catch-up tick.** *Chosen:* any tick that is not the last tick its
   call runs. Tick 0, the tick a stall runs and the tick a rebase runs
   are each the last of a call that ran one tick, so `m` is 1 there.

5. **`m` and the arithmetic.** *Chosen:* in doubles,
   `(ki * error * period) * m` and `(up * period) * m`, with `m` the
   lesser of the ticks the call ran and `act_for`. A block that does not
   act by the call is not multiplied at all.

6. **`commands` and `act_for` in the graph file.** *Chosen:* `commands`
   is a list (anything else is refused) of text, each a name in some
   block's `out`; `null` or empty is no command. `act_for` is a whole
   number and not a boolean, from 1 to 2,147,483,647.

## A rate limit (rules 7.4.12, 7.4.13)

7. **"A catch-up tick is one with a usable input for rules 3 and 4,
   whatever it read."** *Chosen:* the count of unusable ticks in a row is
   set to zero at every catch-up tick, so an input that is unusable at
   the last tick of the call is the first such tick, however many
   catch-up ticks before it read nothing usable.

8. **`limited` at a catch-up tick with an unusable input.** "`limited`
   has the input's state". *Chosen:* that state, and no value.

9. **When `track` is read.** *Chosen:* at each tick with a usable input
   where the block holds no value it took from an input (for one that
   acts by the call, each such tick that is the last of its call), it
   takes `track`'s value as what it holds and limits the input from it
   at that same tick. From then `track` is not read until it has
   forgotten. `track` may be a constant.

## A PID (rules 7.7.13, 7.7.14)

10. **A catch-up tick is otherwise an ordinary tick.** *Chosen:* the
    addition is exactly zero, so nothing is cut short, `limited` is true
    only where the sum is past a limit, and `applied` takes nothing back.
    An unusable input at a catch-up tick starts the derivative again and
    makes it wait to track.

11. **Stopping the wait with no usable `track`.** *Chosen:* it stops
    waiting at the tick whether or not `track` is usable there; an
    unusable `track` is a chance missed.

12. **A reset on a tick with an unusable input.** "It stops waiting at the
    tick of a reset too, a catch-up tick among them, and whatever that
    tick reads", against "waits to track ... from a tick where either
    input is not usable". *Chosen:* the reset wins: after such a tick it
    is not waiting, and `track` is not taken when the input comes back.

13. **Which derivative.** *Chosen:* the derivative as worked at the tick
    it stops waiting, after the filter has run for it.

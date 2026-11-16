# FluxGraph semantics, version 2: how the proposal came to say what it says

[semantics_spec_v2.md](semantics_spec_v2.md) is the proposal. This is its
history up to the fourth revision: what the reviews of the second and
third revisions found, and the thirteen amendments made to the third, each
with what it changed and what was measured for it. The fourth revision is
the third with those amendments worked into its text. Rule and section
numbers here are the proposal's.

## The second revision, and what the third did about it

The second revision was reviewed twice, as a contract with a host and as
signal processing. Both reviews found it not fit to build on. What they
found, and what this revision does about it:

- **A host a little slower than the period lost data it had in hand.** A
  tick the host had not called for saw every input as `bad`. A loop at
  2.503 s against a period of 2.5 s then spoiled a thirty-minute window for
  most of eight hours. Time is now the fixed timestep that games and
  simulators use (section 6): in a catch-up tick an input is whatever
  stands, judged by its age.
- **`uncertain` was not one idea.** It washed out through a latch, a
  hysteresis and a low-pass, and stuck for ever on a total. It is now a
  taint on memory with a stated end (section 7). This revision first gave
  an uncertain value the tick of what caused it; the second amendment
  takes that out, and gives a loop a doubt of its own (rule 7.8.8).
- **A sample was new when it was written, not when it was taken.** A host
  that republishes what it holds made an estimator correct on one sample
  many times. A signal now carries its sample time, and a block that needs
  to know whether a sample is new compares sample times (section 3).
- **One unusable tick killed a loop for good**, and the rule for models
  was not implemented by anything. A model is now a thing with a state that
  a block hosts (section 7.8). It never gives up its state.
- **The estimator rules would not have survived an estimator.** One is now
  specified (section 7.9), hosting a model as its predictor.
- **Restore gave `good` values from memory a day old.** A restore is now a
  gap (section 8), and every block says what a gap does to it.

## The third revision, and its thirteen amendments

The third revision was reviewed in its turn, and was found sound in its
structure and wrong in particular rules. It was amended a section at a
time:

1. *Time and the host interface* (sections 6, 7.2 and 8). Times are whole
   nanoseconds, so that no comparison of times needs a tolerance. Every
   write carries a time. What stands on an input is the write with the
   latest time among those a tick may see, and a tick the host did not call
   for may see only what had been sampled by its own time. A call says
   whether it was a gap. A restore, or a clock that has stepped, forgets
   every remembered time.

2. *Doubt through memory* (sections 3 and 7, and the table of section 8).
   An `uncertain` value no longer carries the tick of its cause. A block is
   never `good` on a tick where a value it used is `uncertain`; a block
   with declared, finite memory is `uncertain` for that long after it took
   in something doubtful; a window's tolerance covers an uncertain sample
   as it covers a missing one; a block whose memory has no end takes its
   state from what it reads now and gives counters a graph can test; and a feedback loop
   that holds a model is treated as one block. What that gives up is listed
   at the end of section 7.

3. *Gaps* (section 8, and rules 6.9 and 6.10). A gap is ticks nobody saw,
   and a block is told how many. The tick a stall runs keeps its own
   number, and each block does to what it remembers what that many ticks
   with nothing usable to read would have done: a total adds them to what
   it has missed, a counter to what was doubtful, a window holds no sample
   for them, a delay moves on. A host that knows how long a restored graph
   was away says so. Where nobody knows, the gap is longer than anything a
   block counts.

4. *Models* (rule 4.9, section 7.8 and Appendix A). Every model is
   linear, and is stepped exactly: its step over a period is the solution
   of its equation with its inputs held, worked out when the graph is
   compiled. There is no step a model is unstable at, and no sub-steps.
   One general block, `linear`, takes the matrices of any linear model,
   and the six models 1.x has in continuous time are each a named case of
   it. Two model blocks that take each other's outputs are a tick apart,
   which can make a sound network unstable, and are written as one;
   amendment 11 says which pairs those are.

5. *The estimator* (section 7.9). Its process noise is discretised
   exactly, as its model is, and its model inputs are deferred. A
   measurement is of any output of the model that reads no input
   directly. A refused measurement makes
   its tick `uncertain`, and a run of them longer than the author allows
   widens the variance and takes the next: a gate can no longer lock an
   estimator out. Its author states a test of whether its innovations are
   as large as it expects, or says there is none. An `uncertain`
   measurement is used with a variance of its own, and makes its tick
   `uncertain`, or is not used at all. At a gap of known length it
   predicts across it.

6. *The whole text, read cold* (throughout). An input's `initial` stands
   in until the first rebase and not after it, and after a rebase a host
   writes again only the inputs that have no maximum age: an old sample
   is not made new. Rounding up to whole ticks is exact and has no
   tolerance, but for a named model's `settle`. Every time and length
   fits in 64 bits, and a call that would take a tick past that is
   refused. A block id and the names a block is given hold no dot, and an
   estimator's outputs have a name each. A model block's outputs are
   judged together. The summaries that had drifted from the rules they
   summarise are put right, and section 7.11 lists more of what is given
   up.

7. *A rate limit and a PID* (sections 7.4 and 7.7, the table of section
   8, and Appendix A). A controller written as a formula and a delay
   stopped for good at its first gap. A `rate_limit` holds its last output
   and moves it towards its input by no more than a stated rate. A `pid`
   reads a setpoint and a measurement: its derivative is of the
   measurement, through a filter; its integral stops going into an output
   limit and still comes out of it; and with an input it cannot use it
   gives no value, keeps its integral, and starts its derivative again. It
   may be told what was applied to the actuator, so that a limit after it
   does not wind its integral up. A clamp is a formula, and gets no block.

8. *What building it in C++ asked* (rules 6.11, 7.3.8 and Appendix A). A
   first slice of the core was written in C++ from this text, and agreed
   with every vector it could run. It asked for what a reading in whole
   numbers of any size never has to: what a call does once the last tick
   number has been run, and that a call is refused whole if any tick it
   would run does not fit. It also wanted the order of an `integrate`'s
   arithmetic, a delay's type on a loop, what a `bad` input is to a window
   that takes only new samples, and how deep a formula may nest. The
   second slice asked for the order of a PID's sum, which three
   implementations had taken three ways, and how a low-pass raises its
   decay to a power. The third slice, the models and the loop rule,
   showed that the exact step is not kept in ordinary double arithmetic at
   the stiffness bound: one of the two readings in `conformance/` was out
   by 2.8 parts in 10⁹ there, and had agreed with every vector. The
   fourth, the estimator, found the other reading taking a measurement
   from a delay of a constant, which rule 7.9.3 refuses.

9. *Commands, and where the actuator is* (rules 6.13, 7.4.12, 7.4.13,
   7.7.13 and 7.7.14, and sections 8 and 9). Five whole graphs were run
   through stalls, dropouts, restarts and stepped clocks, and a PID loop
   did not come through them. A controller ran every catch-up tick as if
   what it gave had reached the actuator: a call 99 ticks late took an
   integral from 0.3 to 10.2, where one 101 ticks late, a gap, left it at
   0.4. A graph now lists the outputs its host hands to an actuator. At a
   catch-up tick such a **command** is what the host was last given, for
   every block that reads it, and a `pid` or a `rate_limit` that feeds one
   acts once a call: for the ticks the call ran, and for no more than
   `act_for` of them. A graph that lists none, a simulation, runs as it
   did. And a rate limit given `initial` went back to it after an outage,
   wherever the actuator was: a `pid` and a `rate_limit` may be given
   `track`, where the actuator is, and start again from that.

10. *A derivative and a slope between samples* (rules 7.7.7 and 7.3.6,
    section 8 and Appendix A). Both were worked as if each tick held a
    sample one period after the last. A host whose loop is 3% slower than
    the period samples a little later each time and now and then runs two
    ticks on one sample: of a ramp of exactly 1 a second the PID's
    derivative read from 0.79 to 1.03 and a window's slope from 0.72 to
    1.03. Both are now over the times the samples carry. The derivative
    is between one sample and the next, with its filter over the time
    between them, and stands while a sample stands. A window places each
    sample at its own time. On that ramp both read 1. A value with no
    sample time, a block's output, has its tick's, and is worked as
    before.

11. *Smaller faults* (rules 3.8, 7.7.2 and 7.8.8, and section 2). A loop
    was allowed one model block, so two plants in cascade under one
    controller could not be written, and the refusal said of blocks in
    series that they read each other. What is refused now is what the
    rule was written against: model blocks joined in a ring directly or
    through formulas alone. A total past its
    `max_missed` had no value until a reset, and a restore or a stepped
    clock took a batch's total away where nothing was known to be
    missed: it keeps its value now, as `uncertain`. A value keeps room
    for a reason that nothing yet gives. And motion control is named as
    not a goal.

12. *A controller that is not acting* (rules 7.4.14 and 7.7.15, and
    Appendix A). The core was run inside a machine runtime, closing a
    speed loop on a simulated motor through the runtime's own automation.
    When the motor's reads failed the runtime stopped acting and set the
    duty to zero, as it should. The graph was told nothing: it ran on
    with the motor at rest, took its output to the limit of 1 and gave it
    as `good`, for nobody. A `pid` and a `rate_limit` now have an input
    `follow`. While it is true the block gives `track`, where the
    actuator is, and when it is false again starts from there.

13. *An estimator between samples* (section 7.9, the table of section 8
    and Appendix A). An estimator stepped a whole period at a time, on
    model inputs held from one tick to the next, and set each measurement
    against its state at the tick, whatever time the sample carried. With
    a model that was exactly right, a host 3% off the period had it call
    itself `uncertain` on 128 to 190 ticks of 2,400, over three runs of
    each, where 4 to 13 were due to chance, and samples 3 s old put its
    estimate of a state it did not measure ten times further out. Its
    state now stands where the last measurement was. Each measurement is
    met by a prediction to its own sample time, on each model input from
    the place its value is from, and what the estimator gives at a tick
    is carried on from there. The steps between are of sixteenths of a
    period, worked out when the graph is compiled as the period's is. On
    the same runs it is `uncertain` on 8 to 68 ticks, and with a `lag` of
    4 s the samples 3 s old leave its estimate as near as fresh ones do.
    The error of that estimate on a host off the period was not the
    fault and has not changed. A sample that arrives older than the
    state is passed by, counted, and makes its tick `uncertain`.

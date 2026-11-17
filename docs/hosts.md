# FluxGraph and its hosts

This page is about FluxGraph 2.0, which is being built
([semantics_spec_v2.md](semantics_spec_v2.md) is what it is built to). For
1.x as released, see [ARCHITECTURE.md](ARCHITECTURE.md).

## What the engine is

FluxGraph is an engine for a graph of signals. It is given three things and
gives three back.

| A host gives it | It gives back |
| --- | --- |
| A graph: blocks, and the signals between them | The graph's outputs at each tick, each with a state |
| Values for the graph's inputs, each with a state and the time it was taken | A report of each call: the ticks run, a gap, the writes thrown away |
| The time, at every call | Its state, to save and to restore |

That is all it knows. It does not know:

- **what it is used for.** Nothing in it tells a simulated value from a
  measured one;
- **who its host is.** The core has no dependency, and names no host
  anywhere;
- **devices, protocols or files.** A graph reaches it as a value built in
  code. The loaders that read one from JSON or YAML are libraries of their
  own, and opening the file is the host's;
- **the clock on the wall, or threads.** The host passes the time, and makes
  its calls one at a time (rule 6.12).

Section 6 of the specification is the whole of what a host has to do.

## What a host makes of it

What a graph is for is its host's business. There are three shapes.

### Generating

The host writes what acts on a system and reads what the system would
measure: a plant model driven by actuator values. Time is whatever the host
says it is, and may be simulated.

```text
actuator values ──> [ engine: a model of the plant ] ──> simulated measurements
```

This is what FluxGraph 1.x is for. The
[Anolis simulation provider](https://github.com/anolishq/anolis-provider-sim)
is a host of this kind, through `fluxgraph-server`.

### Processing

The host writes what was measured and reads what follows from it: filters,
totals, estimates, detectors.

```text
measured values ──> [ engine: filters, estimators, detectors ] ──> derived values
```

The first host of this kind is the Anolis runtime's derived-signals layer,
which is a proposal there and not yet built.

### Both, in two engines

One engine generates what stands in for a machine, and another processes
what comes out of it, as it would the real thing.

```text
commands ──> [ engine A: the plant ] ──> measurements
                                              │
                                  whatever carries them: a protocol,
                                  a driver, a process boundary
                                              │
                                              v
                              [ engine B: filters, estimators ] ──> derived values
```

**Neither engine knows of the other.** An engine knows the names of its own
inputs and nothing else. There is no registry of engines, and nothing one
can ask of another. What follows from that:

- The two may be different versions of FluxGraph, in different processes,
  on different machines.
- Each has its own period and its own clock.
- A graph file for one says nothing of the other.
- Engine B cannot tell engine A from hardware, which is the point: what is
  proved against the one holds for the other as far as the model is true.

One model can serve both, as the plant in A and as an estimator's
predictor in B. That is one definition written into two graphs, and not
one thing shared.

A plant and what acts on it can also be blocks of one graph in one engine:
a simulation with its controller inside it. Then nothing is between them
but the graph.

## What is not yet so

- **Generating is not yet tried on 2.0.** Every conformance vector is of a
  graph given values and times as a processing host gives them. No graph of
  a simulation host has been run on the version 2 core.
- **`noise` is not in the version 2 catalogue**, and a simulation wants it.
- **The server speaks the 1.x protocol.**
- **Rules and commands as 1.x has them** are open in section 4 of the
  specification, for a simulation host to settle.

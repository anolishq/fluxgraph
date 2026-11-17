# A host that simulates, on the version 2 core

A spike, not for merging. Every conformance vector is of a graph given
values and times as a host on a live machine gives them. This is the other
kind of host ([docs/hosts.md](../../docs/hosts.md), "Generating"): the
graphs the
[Anolis simulation provider](https://github.com/anolishq/anolis-provider-sim)
runs today, at its commit `71a51e6`, run on FluxGraph 1.x and on the
version 2 core.

## What is here

| File | What it is |
| --- | --- |
| `extrusion.v1.yaml` | The provider's `config/multi-provider-extrusion.yaml`, as it is: four thermal masses and fifteen edges |
| `physics.v1.yaml` | The provider's `examples/sim_mode/physics.yaml`, as it is |
| `extrusion.v2.yaml` | The first, written as a version 2 graph with a block for each mass |
| `extrusion-joined.v2.yaml` | The same, with the three masses that act on one another as one linear model |
| `run_v1.cpp` | Runs a 1.x graph on a script of writes and ticks |
| `compare.py` | Runs all three for 60 s and sets each against the equations integrated finely |

## To run it

```bash
cmake --preset ci-linux-release-v2
cmake --build build/ci-linux-release-v2 --target fluxgraph fluxgraph_v2_driver
V=build/ci-linux-release-v2/vcpkg_installed/x64-linux
g++ -std=c++20 -O2 -DFLUXGRAPH_YAML_ENABLED -Iinclude -I$V/include spike/sim-host/run_v1.cpp \
    build/ci-linux-release-v2/libfluxgraph.a $V/lib/libyaml-cpp.a -o build/ci-linux-release-v2/run_v1
python3 spike/sim-host/compare.py build/ci-linux-release-v2/run_v1 \
    build/ci-linux-release-v2/tools/fluxgraph_v2_driver/fluxgraph_v2_driver
```

## What it printed

The worst error of each engine on the four temperatures the provider hands
on as readings, in kelvin, against RK4 at a thousandth of the period. The
relays switch on a tick, at 5 s, 20 s and 40 s.

```text
 period  engine      a line is the state      tempctl0/tc1_temp   tempctl0/tc2_temp   tempctl1/tc1_temp   tempctl1/tc2_temp
   0.1s  1.x         at the tick                          0.066               0.066               0.666                 5.5
                       and after 5 s                     0.0452              0.0568               0.666               0.154
   0.1s  2.0         at the tick                       1.58e-12            3.55e-15              0.0614               0.278
                       and after 5 s                   1.58e-12            3.55e-15              0.0614               0.278
   0.1s  2.0 joined  at the tick                       1.58e-12            3.55e-15            4.15e-12            1.31e-12
                       and after 5 s                   1.58e-12            3.55e-15            4.15e-12            1.31e-12
   0.5s  1.x         at the tick                           0.33                0.33                3.43                27.5
                       and after 5 s                      0.225               0.284                3.43                1.25
   0.5s  2.0         at the tick                       7.89e-13                   0               0.311                1.61
                       and after 5 s                   7.89e-13                   0               0.311                1.61
   0.5s  2.0 joined  at the tick                       7.89e-13                   0            3.75e-12            1.11e-12
                       and after 5 s                   7.89e-13                   0            3.75e-12            1.11e-12
   1.0s  1.x         refused: refused: Engine: stability violation for model 'ThermalMass(id=material_output, C=10 J/K, h=25 W/K, T0=22 degC, method=forward_euler)' (dt=1.000000 exceeds limit=0.800000)
   1.0s  2.0         at the tick                       4.26e-13                   0               0.631                3.76
                       and after 5 s                   4.26e-13                   0               0.631                3.76
   1.0s  2.0 joined  at the tick                       4.26e-13                   0            1.65e-12            6.25e-13
                       and after 5 s                   4.26e-13                   0            1.65e-12            6.25e-13
1.x, after its first tick at 0.1 s: (21.934, 21.934, 21.648, 16.5), where every mass began at 22
```

## What it found

1. **The version 2 core runs a simulation host's graph.** The provider's
   graph, written as a version 2 file and read by the YAML loader,
   compiles and runs. The provider runs it at 10 Hz
   (`tick_rate_hz: 10.0`).

2. **A mass that nothing else acts on is exact**: 1.6e-12 K on the top
   half of the chamber over 60 s at any of the three periods, where 1.x,
   by forward Euler, is 0.045 K out at 0.1 s and 0.23 K at 0.5 s.

3. **Masses that act on one another, each in a block of its own, are not
   exact, and on one of the four are worse than 1.x.** A block holds what
   another gave at the tick for the whole period, and a model's inputs
   are deferred, so each link is a tick late as well. At 0.1 s the
   material's temperature is 0.28 K out, where 1.x after its start is
   0.15 K; the hotend's is 0.06 K, where 1.x is 0.67 K. The error grows
   with the period: 3.8 K at 1 s.

4. **Joined in one model, they are exact**: 4e-12 K at every period, 1 s
   among them. This is what section 7.8 of the text says of models that
   read one another, and a simulation host has to know it: what acts on
   itself within a period belongs in one model.

5. **1.x starts with a tick on an ambient of zero.** Its models run
   before its edges, and a signal nobody has written reads 0.0, so at
   its first tick every mass cools towards 0 degC: the material falls
   from 22 to 16.5 in a tenth of a second. The version 2 core has no
   such tick: a mass given no input holds its state and calls it
   `uncertain`.

6. **1.x refuses a period of 1 s** for this graph, for its stability
   limit of 0.8 s. The version 2 core has no such limit short of rule
   7.8.7's bound.

7. **1.x refuses the provider's own example.**
   `examples/sim_mode/physics.yaml` has two edges that write
   `chamber_thermal.ambient_temp`, and `run_v1` on `physics.v1.yaml`
   gives "Multiple writers for signal id 0". The check is in every
   release from v1.0.2, and the provider pins v1.0.6. The version 2 core
   refuses the same thing, saying which block and which name.

8. **Edges that are there so that a signal is taken have nothing to
   become.** Three of the 1.x graph's fifteen edges write to `sinks/...`
   so that 1.x will take an input nothing reads. A version 2 graph
   declares the input and reads it or not.

## What this is not

- **The provider is not moved.** It reaches FluxGraph through
  `fluxgraph-server` over gRPC, and the server speaks the 1.x protocol.
  Nothing here goes through either: both engines are driven in process.
- **One graph, one kind of model.** Four thermal masses. No other model,
  no noise, which the version 2 catalogue has not got, and no rule.
- **No units.** 1.x writes each signal with a unit and checks them, and
  nothing here does.
- **One run of each**, from one script of relay states, with the relays
  switching on ticks.
- The truth is the equations with the relays held over each period, as
  both engines are given them. A relay that switches between ticks is
  not looked at.

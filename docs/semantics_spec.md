# FluxGraph Semantics Specification

**Status:** Baseline semantics specification  
**Version:** 0.1.0  
**Last Updated:** October 27, 2026

## 1. Scope and Authority

This document is the normative semantic contract for FluxGraph runtime behavior.

1. If this document conflicts with README, architecture notes, examples, or API docs, this document is authoritative.
2. All public claims about execution behavior must be derivable from this document.
3. Any semantic change requires an update to this document before merge. No CI check enforces this.

## 2. Evaluated Execution Models and Selection

## Option A: Snapshot Staged Semantics

Definition: every edge reads from a fixed pre-tick snapshot and writes to next-state storage; no within-tick graph propagation.

Pros:

1. Very simple reasoning model.
2. Strong isolation between read and write phases.

Cons:

1. Hidden one-tick latency across edge chains.
2. Topological ordering has reduced semantic impact.
3. Difficult to align with user expectation for DAG dataflow.

## Option B: Immediate Topological Propagation Semantics

Definition: non-delay edges execute in deterministic topological order and read latest visible values; upstream edge writes are visible to downstream non-delay edges in the same tick.

Pros:

1. Natural DAG signal-flow semantics.
2. Non-delay edges add no temporal delay between each other within a tick. A signal written by an edge reaches models on the next tick, because models run before edges. A signal written by a non-delay edge, or by a delay edge declared later, reaches a delay edge on the next tick, because delay edges run first, in declaration order (Section 4).
3. Better alignment with scientific communication for causal graphs.

Cons:

1. Requires stricter compiler/runtime contracts (cycle policy, writer policy, deterministic ordering).

## Selected Model (Normative)

FluxGraph adopts **Immediate Topological Propagation Semantics**.

## 3. Time and Tick Model

We define a discrete tick index `k` with tick boundaries `t_k`.

1. `dt_k > 0` is required for every tick. `Engine::tick` and the server `--dt` check reject `dt <= 0`; a NaN `dt` passes both checks.
2. The state visible to application and providers before `tick(k)` is `S_k`.
3. `tick(k)` computes `S_{k+1}` and command set `C_{k+1}`.
4. No concurrent tick execution is permitted.
5. For publication-grade reproducibility, runs are expected to use constant `dt` unless explicitly documented otherwise.

## 4. Normative Tick Ordering

Each `tick(dt, store)` executes in this order:

1. **Input Boundary Freeze**
   - Provider/application writes completed before tick begin are considered part of `S_k`.
2. **Model Update Stage**
   - Models advance internal state by `dt` and write model outputs into store.
3. **Edge Propagation Stage**
   - Delay edges execute first, in declaration order. Non-delay edges then execute in deterministic topological order.
   - Edge output writes are immediately visible to downstream non-delay edges in the same stage. A delay edge whose source is written by a non-delay edge, or by a delay edge declared after it, reads that source's value from the previous tick.
4. **Rule Evaluation Stage**
   - Rules evaluate against post-model/post-edge state (`S_{k+1}`).
   - Matching rules emit commands for external execution.
5. **Tick Commit**
   - `S_{k+1}` and `C_{k+1}` become externally visible.

Determinism requirements:

1. Topological ordering tie-break must be stable and deterministic.
2. Command ordering must be deterministic for identical inputs and configuration.

## 5. Cycle and Algebraic Loop Policy

1. The directed graph induced by all **non-delay** edges must be acyclic.
2. A cycle is only legal if every feedback loop is broken by at least one explicit delay element.
3. Compile-time cycle diagnostics must identify at least one concrete loop path.
4. Cycles without explicit delay are compile-time errors.

## 6. Delay Semantics

Delays are declared explicitly as delay edges. Edge execution order adds one tick of lag where a delay edge reads the output of a non-delay edge, or of a delay edge declared after it (item 3).

1. Delay transform parameter `delay_sec` maps to integer ticks by:
   - `N = max(1, llround(delay_sec / dt))` when `delay_sec > 0`. `delay_sec <= 0` is accepted and passes the input through with no delay.
2. `dt` is the timestep passed to each `tick(dt, store)` call; `N` is recomputed on every tick.
3. For `k >= N`, delay output at tick `k` is the input value from tick `k-N`, counting ticks from load or reset. The lag is `N+1` ticks when the delay's source is written by a non-delay edge, or by a delay edge declared after it (Section 4).
4. The delay buffer starts empty, with no fill value: for `k < N` the delay outputs the input value from tick 0.
5. No `dt` tolerance check or buffer reinitialization is implemented. The buffer drops at most one sample per tick, so after `dt` increases the delay keeps its earlier tick count; after `dt` decreases the buffer grows and repeats its oldest sample until it holds `N` samples.

## 7. Signal Ownership and Write Authority

Each signal has exactly one owning writer class per tick. The compiler enforces this between edges and models; external writes are checked only as stated in rule 2:

1. **Model-owned (physics-owned):** written by the model stage.
2. **Edge-owned (derived):** written by the edge stage; the compiler rejects models and other edges as writers.
3. **External-owned (provider/application input):** writable by external update path only.

Rules:

1. Multi-writer targets are compile-time errors.
2. The server's `UpdateSignals` path rejects external writes to every edge target and to `thermal_mass` `temp_signal` with `PERMISSION_DENIED`. External writes to outputs of other model types are accepted, and `SignalStore::write` in library use performs no ownership check.
3. Engine internal stages must not overwrite signals owned by different stages.

## 8. Unit Semantics

Unit handling policy is strict and deterministic.

1. Under `DimensionalPolicy::strict`, edge sources, edge targets, signals bound to model signal parameters and rule condition signals must have a declared unit contract (`"dimensionless"` allowed). Under the default `DimensionalPolicy::permissive`, which the server uses, a signal may be undeclared; its first non-dimensionless write then sets its unit.
2. Writes must match declared unit policy exactly unless explicit conversion rules are defined.
3. Under `DimensionalPolicy::strict`, compile rejects incompatible unit contracts where inferable from graph specification. Under the default permissive policy, which the server uses, compile passes a warning to `CompilationOptions::warning_handler`, if one is set, and continues (the server sets none), except that an empty `signals[].unit` and duplicate `signals` entries with conflicting units are rejected under either policy.
4. Runtime unit mismatch is a hard error (not silent coercion).
5. Claims of dimensional analysis are only valid when compile/load/runtime unit contracts are all enforced.

## 9. Timestep and Stability Policy

1. `dt <= min(model_stability_limit)` is required unless a model explicitly documents unconditional stability.
2. Stability validation must run in active compile/load path for target runtime `dt`.
3. Server CLI `--dt` must be wired into runtime tick behavior and stability checks.
4. Violations are hard failures (load rejection), not warnings.

## 10. Non-goals in This Spec Version

1. Parallel edge execution semantics.
2. Adaptive timestep controller semantics.
3. Implicit solver algebraic-loop handling.
4. Automatic unit conversion ontology.

## 11. Conformance Snapshot (March 1, 2026)

This section records current implementation alignment against the normative contract.

1. Engine stage order now executes models before edges with immediate topological propagation: **conformant** with Section 4 baseline.
2. Rule conditions now support comparator expressions (`<`, `<=`, `>`, `>=`, `==`, `!=`) over scalar signal paths: **partial** for Section 4 (minimum subset implemented).
3. Stability validation is active in server load/compile path and enforced at runtime in `Engine::tick`: **conformant** with Section 9 baseline.
4. Server CLI `--dt` is wired into service runtime timestep and compile-time stability validation: **conformant** with Section 9.
5. External writes to edge targets and to `thermal_mass` `temp_signal` are rejected in server update flow; outputs of other model types are not protected: **partial** for Section 7 for server path.
6. Unit checks enforce declared/first-write consistency and runtime mismatches throw: **partial** for Section 8 (compile-time inferential checks remain limited).
7. Delay-mediated cycle acceptance is implemented via non-delay subgraph cycle policy: **partial** pending deeper delay-buffer semantics validation in complex mixed-order graphs.

Remaining gaps define follow-up hardening and expanded evidence work.

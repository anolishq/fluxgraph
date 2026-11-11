#!/usr/bin/env python3
"""Run the version 2 conformance vectors against the reference.

  python3 conformance/run.py [--second] [vector.yaml ...]

With no vectors named, runs every file in conformance/vectors/. Exits 1 if
the implementation disagrees with any vector. With --second, the
implementation is the one in second/ and not reference.py. Needs PyYAML.

A vector is a YAML file:

  rules: [7.2.2]             the rules of the proposal it tests
  period: 1s
  inputs: {x: {max_age: 5s}} as in section 9 of the proposal
  blocks: [...]              as in section 9 of the proposal
  calls:                     one row per call the host makes to tick(now)
    - {x: 1.0, y: not_ready}
  expect: compile_error      in place of calls, for a graph that must be refused
  error_mentions: [a, b]     words the refusal has to contain

A row of `calls` has these keys:

  now: 2.5      the time passed to the call, in seconds. Left out, it is one
                period after the call before, and 0 for the first.
  ran: 3        how many ticks the call must say it ran. Left out, 1.
  first: {...}  writes made before the row's own, for two writes between ticks.
  refused: true the call must be refused, and nothing else is checked.
  <input>       a write before the call: a number, true or false (written as
                good); `bad` or `not_ready`; or {v: 1.0, state: uncertain,
                at: 1.5}, where `at` is the time it was sampled. Without
                `at`, the sample time is the call's `now`. An input left out
                is not written.
  <output>      what a published output must be after the call: a number,
                true or false (it must be good); `bad` or `not_ready`; or
                {u: 1.0} for uncertain with that value.

A row with a single key starting with `$` is an operation on the engine:
{$save: name}, {$restore: name}, {$reset: true}.
"""

from __future__ import annotations

import sys
from pathlib import Path

import reference
import yaml

impl = reference  # the implementation under test; --second swaps it

HERE = Path(__file__).resolve().parent
TOLERANCE = 1e-9
ROW_KEYS = {"now", "ran", "first", "refused"}


def show(val):
    return f"{val.state} {val.v!r}" if val.v is not None else val.state


def write(engine, name, value, now):
    state, sampled = impl.GOOD, now
    if isinstance(value, dict):
        state, sampled, value = value.get("state", impl.GOOD), value.get("at", now), value.get("v")
    if value in (impl.BAD, impl.NOT_READY):
        state, value = value, None
    if value is not None and not isinstance(value, bool):
        value = float(value)
    engine.write(name, state, value, float(sampled))


def differs(have, want):
    """-> None, or how `have` differs from what the vector says."""
    state = impl.GOOD
    if isinstance(want, dict):
        state, want = impl.UNCERTAIN, want["u"]
    if want in (impl.BAD, impl.NOT_READY):
        return None if have.state == want else f"is {show(have)}, the vector says {want}"
    if have.state != state:
        return f"is {show(have)}, the vector says {state} {want!r}"
    if isinstance(want, bool) or isinstance(have.v, bool):
        same = isinstance(want, bool) and isinstance(have.v, bool) and want == have.v
    else:
        same = abs(have.v - float(want)) <= TOLERANCE * max(1.0, abs(float(want)))
    return None if same else f"is {show(have)}, the vector says {state} {want!r}"


def run(path):
    """-> (calls, comparisons, list of differences)."""
    doc = yaml.safe_load(path.read_text())
    graph = {k: doc[k] for k in ("period", "inputs", "blocks") if k in doc}
    for key in doc.get("graph_extra", {}):  # a vector may add a deliberately unknown key
        graph[key] = doc["graph_extra"][key]

    if doc.get("expect") == "compile_error":
        try:
            impl.Engine(graph)
        except impl.CompileError as exc:
            missing = [w for w in doc.get("error_mentions", []) if str(w) not in str(exc)]
            return 0, 1, [f"refused, but the message does not mention {missing}: {exc}"] if missing else []
        return 0, 1, ["the graph was accepted; it should have been refused"]

    engine = impl.Engine(graph)
    period = impl.seconds(doc["period"])
    saved, differences, compared, calls, now = {}, [], 0, 0, None
    for row in doc["calls"]:
        if any(str(k).startswith("$") for k in row):
            if "$save" in row:
                saved[row["$save"]] = engine.save()
            elif "$restore" in row:
                engine.restore(saved[row["$restore"]])
            elif "$reset" in row:
                engine.reset()
            continue
        now = float(row["now"]) if "now" in row else 0.0 if now is None else now + period
        where = f"call {calls} (now {now:g})"
        for name, value in row.get("first", {}).items():
            write(engine, name, value, now)
        for name, value in row.items():
            if name in engine.inputs:
                write(engine, name, value, now)
        compared += 1
        if row.get("refused"):
            try:
                engine.tick(now)
                differences.append(f"{where}: the call was accepted; it should have been refused")
            except impl.CompileError:
                raise
            except Exception:  # noqa: S110 - any refusal will do; its wording is not specified
                pass
            calls += 1
            continue
        ran, out = engine.tick(now)
        if ran != row.get("ran", 1):
            differences.append(f"{where}: ran {ran} tick(s), the vector says {row.get('ran', 1)}")
        for name, want in row.items():
            if name in engine.inputs or name in ROW_KEYS:
                continue
            compared += 1
            if out is None or name not in out:
                differences.append(f"{where}: {name} is not a published output of a tick that ran")
                continue
            difference = differs(out[name], want)
            if difference:
                differences.append(f"{where}: {name} {difference}")
        calls += 1
    return calls, compared, differences


def main():
    global impl
    args = sys.argv[1:]
    if "--second" in args:
        args.remove("--second")
        from second import adapter

        impl = adapter
    paths = [Path(p) for p in args] or sorted((HERE / "vectors").glob("*.yaml"))
    ok = True
    print(f"{'vector':36s} {'calls':>5s} {'compared':>8s}  result")
    for path in paths:
        try:
            calls, compared, differences = run(path)
        except Exception as exc:  # a vector that cannot run is a failure, with its reason
            calls, compared, differences = 0, 0, [f"{type(exc).__name__}: {exc}"]
        ok = ok and not differences
        print(f"{path.stem:36s} {calls:5d} {compared:8d}  {'agrees' if not differences else 'DIFFERS'}")
        for line in differences[:4]:
            print(f"    {line}")
    print(f"{len(paths)} vectors: " + ("ALL AGREE" if ok else "DIFFERENCES FOUND"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

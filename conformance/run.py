#!/usr/bin/env python3
"""Run the version 2 conformance vectors against the reference.

  python3 conformance/run.py [vector.yaml ...]

With no arguments, runs every file in conformance/vectors/. Exits 1 if the
reference disagrees with any vector. Needs PyYAML.

A vector is a YAML file:

  rules: [7.2.1]             the rules of the proposal it tests
  period: 1s
  inputs: {x: {max_age: 5s}} signals written from outside; max_age is optional
  blocks: [...]              as in section 9 of the proposal
  ticks:                     one row per tick; tick k is at k times the period
    - {x: 1.0, y: not_ready}
  expect: compile_error      in place of ticks, for a graph that must be refused
  error_mentions: [a, b]     words the refusal has to contain

In a tick row, a key that names an input is a write before that tick: a
number, `bad`, `not_ready`, or {v: 1.0, age: 3s} for a value sampled earlier.
An input that is left out of a row is not written, so its last value stands
and grows older. Every other key is the expected state and value of a
published output: a number, true, false, `bad` or `not_ready`.

A row with a single key starting with `$` is an operation on the engine:
{$save: name}, {$restore: name}, {$reset: true}.
"""

from __future__ import annotations

import sys
from pathlib import Path

import reference
import yaml

HERE = Path(__file__).resolve().parent
TOLERANCE = 1e-9


def show(val):
    return f"{val.v!r}" if val.state == reference.GOOD else val.state


def run(path):
    """-> (ticks, comparisons, list of differences)."""
    doc = yaml.safe_load(path.read_text())
    graph = {k: doc[k] for k in ("period", "inputs", "blocks") if k in doc}
    for key in doc.get("graph_extra", {}):  # a vector may add a deliberately unknown key
        graph[key] = doc["graph_extra"][key]

    if doc.get("expect") == "compile_error":
        try:
            reference.Engine(graph)
        except reference.CompileError as exc:
            missing = [w for w in doc.get("error_mentions", []) if str(w) not in str(exc)]
            return 0, 1, [f"refused, but the message does not mention {missing}: {exc}"] if missing else []
        return 0, 1, ["the graph was accepted; it should have been refused"]

    engine = reference.Engine(graph)
    saved, differences, compared, ticks = {}, [], 0, 0
    for row in doc["ticks"]:
        ops = [k for k in row if str(k).startswith("$")]
        if ops:
            if "$save" in row:
                saved[row["$save"]] = engine.save()
            elif "$restore" in row:
                engine.restore(saved[row["$restore"]])
            elif "$reset" in row:
                engine.reset()
            continue
        for name, value in row.items():
            if name not in engine.max_age:
                continue
            age = 0.0
            if isinstance(value, dict):
                age, value = reference.seconds(value.get("age", 0)), value["v"]
            if value in (reference.BAD, reference.NOT_READY):
                engine.write(name, value)
            else:
                engine.write(name, reference.GOOD, float(value), age)
        out = engine.tick()
        for name, want in row.items():
            if name in engine.max_age:
                continue
            compared += 1
            if name not in out:
                differences.append(f"tick {ticks}: {name} is not a published output")
                continue
            have = out[name]
            if want in (reference.BAD, reference.NOT_READY):
                if have.state != want:
                    differences.append(f"tick {ticks}: {name} is {show(have)}, the vector says {want}")
                continue
            want = float(want)
            if have.state != reference.GOOD:
                differences.append(f"tick {ticks}: {name} is {have.state}, the vector says {want!r}")
            elif abs(have.v - want) > TOLERANCE * max(1.0, abs(want)):
                differences.append(f"tick {ticks}: {name} is {have.v!r}, the vector says {want!r}")
        ticks += 1
    return ticks, compared, differences


def main():
    paths = [Path(p) for p in sys.argv[1:]] or sorted((HERE / "vectors").glob("*.yaml"))
    ok = True
    print(f"{'vector':34s} {'ticks':>5s} {'compared':>8s}  result")
    for path in paths:
        try:
            ticks, compared, differences = run(path)
        except Exception as exc:  # a vector that cannot run is a failure, with its reason
            ticks, compared, differences = 0, 0, [f"{type(exc).__name__}: {exc}"]
        ok = ok and not differences
        print(f"{path.stem:34s} {ticks:5d} {compared:8d}  {'agrees' if not differences else 'DIFFERS'}")
        for line in differences[:4]:
            print(f"    {line}")
    print("ALL AGREE" if ok else "DIFFERENCES FOUND")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run the version 2 conformance vectors against the reference.

  python3 conformance/run.py [--second | --cpp] [vector.yaml ...]

With no vectors named, runs every file in conformance/vectors/. Exits 1 if
the implementation disagrees with any vector. With --second, the
implementation is the one in second/ and not reference.py. With --cpp it is
the C++ core, through the driver FLUXGRAPH_V2_DRIVER names: a vector that
uses a block type the core has not built yet is skipped and counted, and
is not among those that agree. Needs PyYAML.

A vector is a YAML file:

  rules: [7.2.2]             the rules of the proposal it tests
  period: 1s
  max_catch_up: 3            optional, as in section 9
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
  gap: true     the call must say it was a gap. Left out, it must say it was not.
  tick: 7       the number of the last tick the call ran, if given.
  time: 7.5     the time of that tick, in seconds, if given.
  thrown: 2     how many writes the call says were thrown away, if given.
  waiting: 1    how many writes it says still wait, if given.
  <input>       a write before the call: a number, true or false (written as
                good); `bad` or `not_ready`; or {v: 1.0, state: uncertain,
                at: 1.5}, where `at` is the time the write carries. Without
                `at`, that is the call's `now`. An input left out is not
                written.
  <output>      what a published output must be after the call: a number,
                true or false (it must be good); `bad` or `not_ready`; or
                {u: 1.0} for uncertain with that value.

Times in a vector are in seconds, written as decimals. The runner passes
them to the engine as whole nanoseconds.

A row with a single key starting with `$` is an operation on the engine:
{$save: name}, {$restore: name}, {$reset: true}, {$rebase: true} or {$rebase: seconds},
{$write: [name, state, value, time]} for a write with no call after it,
{$refused_write: [name, state, value, time]} for a write that must be refused,
and {$refused_rebase: seconds} or {$refused_rebase_ns: nanoseconds} for a length that must be refused.
"""

from __future__ import annotations

import os
import sys
from fractions import Fraction
from pathlib import Path

import reference
import yaml

impl = reference  # the implementation under test; --second swaps it

HERE = Path(__file__).resolve().parent
TOLERANCE = 1e-9
ROW_KEYS = {"now", "ran", "first", "refused", "gap", "skipped", "tick", "time", "thrown", "waiting"}


def show(val):
    return f"{val.state} {val.v!r}" if val.v is not None else val.state


def ns(value):
    """A time a vector gives in seconds, as the whole nanoseconds the engine takes. Anything else goes through."""
    try:
        exact = Fraction(str(value)) * 10**9
    except (ValueError, ZeroDivisionError):
        return value
    return int(exact) if exact.denominator == 1 else float(exact)


def write(engine, name, value, now):
    state, at = impl.GOOD, now
    if isinstance(value, dict):
        state, at, value = value.get("state", impl.GOOD), ns(value["at"]) if "at" in value else now, value.get("v")
    if value in (impl.BAD, impl.NOT_READY):
        state, value = value, None
    if value is not None and not isinstance(value, bool):
        value = float(value)
    engine.write(name, state, value, at)


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
    graph = {k: doc[k] for k in ("period", "max_catch_up", "max_waiting", "inputs", "blocks") if k in doc}
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
    period = ns(impl.seconds(doc["period"]))
    saved, differences, compared, calls, now = {}, [], 0, 0, None
    for row in doc["calls"]:
        if any(str(k).startswith("$") for k in row):
            if "$save" in row:
                saved[row["$save"]] = engine.save()
            elif "$restore" in row:
                engine.restore(saved[row["$restore"]])
            elif "$reset" in row:
                engine.reset()
            elif "$rebase" in row:  # {$rebase: true}, or {$rebase: 90}: the host says it was away for 90 s
                engine.rebase(None if row["$rebase"] is True else ns(row["$rebase"]))
            elif "$write" in row:  # {$write: [name, state, value, time]}: a write with no call after it
                name, state, value, at = row["$write"]
                engine.write(name, state, value, ns(at))
            elif "$refused_rebase" in row or "$refused_rebase_ns" in row:  # a length that must be refused
                compared += 1
                given = row.get("$refused_rebase_ns")  # as it is, where it is not a whole number of nanoseconds
                try:
                    engine.rebase(ns(row["$refused_rebase"]) if given is None else given)
                    differences.append(f"after call {calls - 1}: the rebase {next(iter(row.values()))} was accepted")
                except Exception:  # noqa: S110 - any refusal will do; its wording is not specified
                    pass
            elif "$refused_write" in row:  # {$refused_write: [name, state, value, time]}: it must be refused
                compared += 1
                name, state, value, at = row["$refused_write"]
                try:
                    engine.write(name, state, value, ns(at) if at is not None else None)
                    differences.append(f"after call {calls - 1}: the write {row['$refused_write']} was accepted")
                except Exception:  # noqa: S110 - any refusal will do; its wording is not specified
                    pass
            continue
        now = ns(row["now"]) if "now" in row else 0 if now is None else now + period
        where = f"call {calls} (now {now / 1e9:g})" if isinstance(now, int) else f"call {calls} (now {now})"
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
        if not ran and engine.info is not None:
            differences.append(f"{where}: a call that ran no tick gave {engine.info}")
        if ran:  # what the call says of itself (6 rule 10)
            compared += 1
            info = engine.info
            if info["gap"] != row.get("gap", False):
                differences.append(f"{where}: gap is {info['gap']}, the vector says {row.get('gap', False)}")
            if "skipped" in row and info["skipped"] != (None if row["skipped"] == "unknown" else row["skipped"]):
                differences.append(f"{where}: skipped is {info['skipped']}, the vector says {row['skipped']}")
            if "tick" in row and info["tick"] != row["tick"]:
                differences.append(f"{where}: the last tick is {info['tick']}, the vector says {row['tick']}")
            if "time" in row and info["time"] != ns(row["time"]):
                differences.append(f"{where}: the last tick is at {info['time']} ns, the vector says {row['time']} s")
            for key in ("thrown", "waiting"):
                if key in row and info[key] != row[key]:
                    differences.append(f"{where}: {key} is {info[key]}, the vector says {row[key]}")
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
    if "--cpp" in args:
        args.remove("--cpp")
        from cpp import adapter

        adapter.start()
        impl = adapter
    not_built = getattr(impl, "NotBuilt", ())  # raised for a graph with a block type not built yet
    skipped = differ = 0
    paths = [Path(p) for p in args] or sorted((HERE / "vectors").glob("*.yaml"))
    ok = True
    print(f"{'vector':36s} {'calls':>5s} {'compared':>8s}  result")
    for path in paths:
        try:
            calls, compared, differences = run(path)
        except not_built:
            skipped += 1
            print(f"{path.stem:36s} {'-':>5s} {'-':>8s}  skipped")
            continue
        except Exception as exc:  # a vector that cannot run is a failure, with its reason
            calls, compared, differences = 0, 0, [f"{type(exc).__name__}: {exc}"]
        ok = ok and not differences
        differ += bool(differences)
        print(f"{path.stem:36s} {calls:5d} {compared:8d}  {'agrees' if not differences else 'DIFFERS'}")
        for line in differences[: int(os.environ.get("SHOW", 4))]:
            print(f"    {line}")
    if not_built:
        agree = len(paths) - skipped - differ
        print(
            f"{len(paths)} vectors: {agree} agree, {skipped} skipped (block types not built)"
            + (f", {differ} DIFFER" if differ else "")
        )
    else:
        print(f"{len(paths)} vectors: " + ("ALL AGREE" if ok else "DIFFERENCES FOUND"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

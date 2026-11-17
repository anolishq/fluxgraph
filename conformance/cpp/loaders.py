#!/usr/bin/env python3
"""Check the C++ core's loaders of JSON and YAML (include/fluxgraph/v2/load.hpp).

  FLUXGRAPH_V2_DRIVER=build/v2/tools/fluxgraph_v2_driver/fluxgraph_v2_driver python3 conformance/cpp/loaders.py

The driver has to be of a build with FLUXGRAPH_JSON_ENABLED and FLUXGRAPH_YAML_ENABLED.

Two things are checked.

The graph of every file of conformance/vectors, which is the text under the keys a graph has (the rest of a
vector is the calls made of it, and is not a graph file), is read by the YAML loader and set against what PyYAML
makes of it, which is what the two Python readings are given; then PyYAML's reading is written out as JSON, read
by the JSON loader, and set against itself. A whole number and a number are not the same thing here, and neither are a
boolean and a number. PyYAML reads YAML 1.1 and the loader reads the core schema of YAML 1.2: where the two part
on a vector, the vector and the place are printed, and the check fails, since the vectors are then not the
graphs the readings were given.

Then each thing the loaders decide is shown on a text of a line or two: what is a boolean, a whole number, a
number and text; and what is refused, with a word the refusal has to hold.

Exits 1 if a vector is read otherwise, or a text is not read as said.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cpp import adapter  # noqa: E402

VECTORS = Path(__file__).resolve().parent.parent / "vectors"
GRAPH_KEYS = ("period", "max_catch_up", "max_waiting", "commands", "act_for", "inputs", "blocks")  # as run.py has
TOP_KEY = re.compile(r"^([A-Za-z_$][^:#\s]*):")


def graph_text(text):
    """-> the lines of a vector's file that are under a key a graph has, as they are written."""
    kept, keeping = [], False
    for line in text.splitlines(keepends=True):
        top = TOP_KEY.match(line)
        if top:
            keeping = top.group(1) in GRAPH_KEYS
        if keeping:
            kept.append(line)
    return "".join(kept)


class Refusal(Exception):
    """A loader refused the text."""


class Wrong(Exception):
    """A loader gave what no loader should: a map with one key twice."""


def _value(tokens, at):
    """-> the value that begins at tokens[at], and where the next begins."""
    kind = tokens[at]
    if kind == "i":
        return int(tokens[at + 1]), at + 2
    if kind == "f":
        return float(tokens[at + 1]), at + 2
    if kind == "b":
        return tokens[at + 1] == "1", at + 2
    if kind == "s":
        return unquote(tokens[at + 1][1:]), at + 2
    count, at = int(tokens[at + 1]), at + 2
    if kind == "l":
        items = []
        for _ in range(count):
            item, at = _value(tokens, at)
            items.append(item)
        return items, at
    pairs = {}
    for _ in range(count):
        key = unquote(tokens[at][1:])
        if key in pairs:
            raise Wrong(f"the loader gave the key {key!r} twice")
        pairs[key], at = _value(tokens, at + 1)
    return pairs, at


def load(form, text):
    """-> what the loader of `form` makes of `text`. Raises Refusal with the loader's message."""
    try:
        tokens = adapter.start().ask(f"load {form} {adapter._text(text)}")  # noqa: SLF001
    except adapter.Refused as refused:
        raise Refusal(str(refused)) from None
    value, at = _value(tokens, 0)
    assert at == len(tokens), "the driver's reply has more in it than one value"
    return value


def differences(ours, theirs, path=""):
    """-> where two readings of one text part, each as a line. A 2 is not a 2.0, and a true is not a 1."""
    where = path or "the whole of it"
    if type(ours) is not type(theirs):
        return [f"{where}: {ours!r}, a {type(ours).__name__}, against {theirs!r}, a {type(theirs).__name__}"]
    if isinstance(ours, dict):
        found = []
        if list(ours) != list(theirs):
            found.append(f"{where}: the keys {list(ours)} against {list(theirs)}")
        for key in ours:
            if key in theirs:
                found += differences(ours[key], theirs[key], f"{path}.{key}" if path else str(key))
        return found
    if isinstance(ours, list):
        if len(ours) != len(theirs):
            return [f"{where}: {len(ours)} items against {len(theirs)}"]
        return [line for i, (a, b) in enumerate(zip(ours, theirs)) for line in differences(a, b, f"{path}[{i}]")]
    same = ours == theirs or (isinstance(ours, float) and math.isnan(ours) and math.isnan(theirs))
    return [] if same else [f"{where}: {ours!r} against {theirs!r}"]


def vectors():
    """-> how many files were read, how many JSON cannot hold, and a line for each place a loader and PyYAML part."""
    parted = []
    not_json = 0
    paths = sorted(VECTORS.glob("*.yaml"))
    for path in paths:
        whole = yaml.safe_load(path.read_text())
        text = graph_text(path.read_text())
        theirs = {key: value for key, value in whole.items() if key in GRAPH_KEYS}
        forms = [("yaml", text)]
        try:
            forms.append(("json", json.dumps(theirs, allow_nan=False)))
        except (ValueError, TypeError):  # an infinity or a key that is not text: JSON has neither
            not_json += 1
        for form, given in forms:
            try:
                ours = load(form, given)
            except (Refusal, Wrong) as problem:
                parted.append(f"{path.name}, as {form}: {type(problem).__name__.lower()}: {problem}")
                continue
            parted += [f"{path.name}, as {form}: {line}" for line in differences(ours, theirs)]
    return len(paths), not_json, parted


REFUSED = object()
INF = float("inf")

# The format, the text, and what it is read as: a value, or REFUSED and a word its refusal holds.
DECIDED = [
    # What is a boolean, and what is not.
    ("yaml", "a: true", {"a": True}),
    ("yaml", "a: False", {"a": False}),
    ("yaml", "a: yes", {"a": "yes"}),
    ("yaml", "a: off", {"a": "off"}),
    ("yaml", "on: x", {"on": "x"}),
    # A whole number is written without a point or an exponent (rule 9.4).
    ("yaml", "a: 2", {"a": 2}),
    ("yaml", "a: 2.0", {"a": 2.0}),
    ("yaml", "a: 1e3", {"a": 1000.0}),
    ("yaml", "a: +3", {"a": 3}),
    ("yaml", "a: -.5", {"a": -0.5}),
    ("yaml", "a: 0x10", {"a": 16}),
    ("yaml", "a: 0o17", {"a": 15}),
    ("yaml", "a: .inf", {"a": INF}),
    ("yaml", "a: -.Inf", {"a": -INF}),
    # What 64 bits, signed, do not hold is the nearest number.
    ("yaml", "a: 9223372036854775807", {"a": 9223372036854775807}),
    ("yaml", "a: 9223372036854775808", {"a": 9223372036854775808.0}),
    ("yaml", "a: -9223372036854775808", {"a": -9223372036854775808}),
    ("json", '{"a": 18446744073709551616}', {"a": 18446744073709551616.0}),
    # Anything else that is plain is text (rule 9.3: a length of time is a number and a unit).
    ("yaml", "a: 2.5s", {"a": "2.5s"}),
    ("yaml", "a: none", {"a": "none"}),
    ("yaml", "a: 1_000", {"a": "1_000"}),
    ("yaml", "a: 1:30", {"a": "1:30"}),
    # A value in quotes, or a block, is text whatever it holds.
    ("yaml", 'a: "42"', {"a": "42"}),
    ("yaml", "a: 'true'", {"a": "true"}),
    ("yaml", "a: |\n  5\n", {"a": "5\n"}),
    ("yaml", "a: !!str 5", {"a": "5"}),
    ("yaml", '"2": x', {"2": "x"}),
    # Lists and maps, and the order of a map's keys.
    ("yaml", "b: [1, 2.0, x]\na: {k: v}", {"b": [1, 2.0, "x"], "a": {"k": "v"}}),
    ("json", '{"b": [1, 2.0, "x", true], "a": {"k": "v"}}', {"b": [1, 2.0, "x", True], "a": {"k": "v"}}),
    ("json", '{"a": 2, "b": 2.0, "c": 1e3, "d": "2"}', {"a": 2, "b": 2.0, "c": 1000.0, "d": "2"}),
    # Refused: a key twice in one map, and the refusal says which.
    ("yaml", "a: 1\na: 2", (REFUSED, "'a' is given twice")),
    ("yaml", "x:\n  k: 1\n  k: 2", (REFUSED, "'x.k' is given twice")),
    ("json", '{"a": 1, "a": 2}', (REFUSED, "'a' is given twice")),
    ("json", '{"x": [{"k": 1, "k": 2}]}', (REFUSED, "'x[0].k' is given twice")),
    # Refused: a null.
    ("yaml", "a: ~", (REFUSED, "'a' is null")),
    ("yaml", "a:", (REFUSED, "'a' is null")),
    ("yaml", "a: null", (REFUSED, "'a' is null")),
    ("yaml", "a: [1, ~]", (REFUSED, "'a[1]' is null")),
    ("yaml", "", (REFUSED, "is null")),
    ("json", '{"a": null}', (REFUSED, "'a' is null")),
    ("json", '{"a": [1, null]}', (REFUSED, "'a[1]' is null")),
    # Refused: a key that is not text.
    ("yaml", "true: 1", (REFUSED, "a boolean and not text")),
    ("yaml", "2: x", (REFUSED, "a whole number and not text")),
    ("yaml", "? [1, 2]\n: x", (REFUSED, "a key that is not text")),
    # Refused: a tag that is not !!str, and text that is not the format.
    ("yaml", "a: !!int 5", (REFUSED, "no tag but !!str")),
    ("yaml", "a: [1, 2", (REFUSED, "not YAML")),
    ("json", '{"a": [1, 2}', (REFUSED, "not JSON")),
    ("json", '{"a": 1} x', (REFUSED, "not JSON")),
]


def decided():
    """-> a line for each text that is not read as said."""
    wrong = []
    for form, text, expected in DECIDED:
        shown = f"{form} {text!r}"
        refused = isinstance(expected, tuple) and expected[0] is REFUSED
        try:
            ours = load(form, text)
        except Wrong as problem:
            wrong.append(f"{shown}: {problem}")
            continue
        except Refusal as refusal:
            if not refused:
                wrong.append(f"{shown}: refused ({refusal}), and should be {expected!r}")
            elif expected[1] not in str(refusal):
                wrong.append(f"{shown}: refused as {str(refusal)!r}, which does not hold {expected[1]!r}")
            continue
        if refused:
            wrong.append(f"{shown}: read as {ours!r}, and should be refused")
        else:
            wrong += [f"{shown}: {line}" for line in differences(ours, expected)]
    return wrong


def main():
    adapter.start()
    files, not_json, parted = vectors()
    for line in parted:
        print(line)
    print(
        f"the graphs of {files} vectors as YAML, and {files - not_json} of them as JSON ({not_json} hold what JSON "
        f"cannot): {len(parted)} places where a loader and PyYAML part"
    )
    wrong = decided()
    for line in wrong:
        print(line)
    print(f"{len(DECIDED)} texts: " + ("EACH READ AS SAID" if not wrong else f"{len(wrong)} NOT AS SAID"))
    sys.exit(1 if parted or wrong else 0)


if __name__ == "__main__":
    main()

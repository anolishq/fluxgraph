"""Gives the C++ core the names run.py, compare.py and contract.py expect.

The core is driven through `fluxgraph_v2_driver`, one process for every engine, found through the environment
variable FLUXGRAPH_V2_DRIVER. The line protocol is described at the top of tools/fluxgraph_v2_driver/main.cpp.

Two kinds of refusal are made here and not by the core, because what is refused cannot be handed to it:

- a time or a length that is not a whole number, or does not fit in 64 bits, signed (rule 6.11): the core's
  interface takes a 64-bit whole number;
- a value that is neither a number nor a boolean, and a graph with a key that is not text or a value that is
  none of a whole number, a number, a boolean, text, a list or a map.

A graph that names a block type of the catalogue the core has not built yet raises NotBuilt, which is neither a
refusal nor an agreement: the checks count such a graph as skipped.
"""

from __future__ import annotations

import collections
import os
import re
import subprocess
from urllib.parse import quote, unquote

GOOD, UNCERTAIN, NOT_READY, BAD = "good", "uncertain", "not_ready", "bad"
Val = collections.namedtuple("Val", "state v")
_DURATION = re.compile(r"^([0-9]+(?:\.[0-9]+)?)(ns|us|ms|s|m|h)$")
_UNIT = {"ns": 1e-9, "us": 1e-6, "ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
_INT64 = range(-(2**63), 2**63)
ENVIRONMENT = "FLUXGRAPH_V2_DRIVER"


class CompileError(Exception):
    """The graph was refused."""


class NotBuilt(Exception):
    """The graph names a block type the core has not built yet."""


class Refused(ValueError):
    """A write, a call, a rebase or a restore was refused."""


def seconds(text):
    m = _DURATION.match(str(text))
    return float(m.group(1)) * _UNIT[m.group(2)]


class _Driver:
    def __init__(self):
        path = os.environ.get(ENVIRONMENT)
        if not path:
            raise SystemExit(
                f"{ENVIRONMENT} is not set: it has to be the path of fluxgraph_v2_driver, which "
                "`cmake -DFLUXGRAPH_BUILD_V2=ON` builds under tools/fluxgraph_v2_driver/ in the build directory"
            )
        if not os.path.isfile(path):
            raise SystemExit(f"{ENVIRONMENT} is {path!r}, which is not a file")
        self.process = subprocess.Popen([path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        types = self.ask("types")  # how many are built, their names, how many are planned, their names
        count = int(types[0])
        self.built, self.planned = set(types[1 : 1 + count]), set(types[2 + count :])

    def ask(self, line):
        """-> the tokens of the reply, after its `ok`. Raises what a refusal stands for."""
        try:
            self.process.stdin.write(line + "\n")
            reply = self.process.stdout.readline()
        except (BrokenPipeError, ValueError):
            reply = ""
        if not reply:
            raise RuntimeError(f"the driver stopped (exit status {self.process.poll()}) at: {line[:200]}")
        tokens = reply.rstrip("\n").split(" ")
        if tokens[0] == "ok":
            return tokens[1:]
        message = unquote(tokens[2][1:])
        if tokens[1] == "graph":
            raise CompileError(message)
        if tokens[1] == "not_built":
            raise NotBuilt(message)
        raise Refused(f"{tokens[1]}: {message}")


_driver = None


def start():
    """Starts the driver, if it is not running. Exits with the reason if it cannot be."""
    global _driver
    if _driver is None:
        _driver = _Driver()
    return _driver


def _text(text):
    return "=" + quote(text, safe="/")


def _setting(value, tokens):
    """Appends the tokens of one value of a graph."""
    if isinstance(value, bool):
        tokens.append("b 1" if value else "b 0")
    elif isinstance(value, int):
        if value in _INT64:
            tokens.append(f"i {value}")
        else:  # a whole number the core's 64 bits do not hold goes as the nearest number
            try:
                tokens.append(f"f {float(value)!r}")
            except OverflowError:
                tokens.append("f inf" if value > 0 else "f -inf")
    elif isinstance(value, float):
        tokens.append(f"f {value!r}")
    elif isinstance(value, str):
        tokens.append("s " + _text(value))
    elif isinstance(value, (list, tuple)):
        tokens.append(f"l {len(value)}")
        for item in value:
            _setting(item, tokens)
    elif isinstance(value, dict):
        tokens.append(f"m {len(value)}")
        for key, item in value.items():
            if not isinstance(key, str):
                raise CompileError(f"the key {key!r} is not text")
            tokens.append(_text(key))
            _setting(item, tokens)
    else:
        raise CompileError(f"{value!r} is none of a whole number, a number, a boolean, text, a list or a map")


def _time(value, what):
    if isinstance(value, bool) or not isinstance(value, int) or value not in _INT64:
        raise Refused(f"{what} is {value!r}, and has to be a whole number of nanoseconds that fits in 64 bits")
    return value


class Engine:
    def __init__(self, graph):
        self._id = None
        driver = start()
        blocks = graph.get("blocks") if isinstance(graph, dict) else None
        for block in blocks if isinstance(blocks, list) else []:
            if isinstance(block, dict) and isinstance(block.get("type"), str) and block["type"] in driver.planned:
                raise NotBuilt(f"block type {block['type']!r} is not built yet")
        tokens = ["new"]
        _setting(graph, tokens)
        self._id = driver.ask(" ".join(tokens))[0]
        inputs = graph.get("inputs")
        self.inputs = set(inputs) if isinstance(inputs, dict) else set()
        self.info = None

    def __del__(self):
        if self._id is not None and _driver is not None and _driver.process.poll() is None:
            try:
                _driver.ask(f"free {self._id}")
            except Exception:  # noqa: BLE001, S110 - the interpreter may be shutting down
                pass

    def write(self, name, state, value=None, at=None):
        if not isinstance(name, str) or not isinstance(state, str):
            raise Refused(f"a write names an input and a state, and was given {name!r} and {state!r}")
        at = _time(at, "the time of a write")
        if value is None:
            shown = "-"
        elif isinstance(value, bool):
            shown = "b 1" if value else "b 0"
        elif isinstance(value, (int, float)):
            try:
                shown = f"n {float(value)!r}"
            except OverflowError:
                raise Refused(f"the value {value!r} is not a number a double holds") from None
        else:
            raise Refused(f"the value {value!r} is neither a number nor a boolean")
        _driver.ask(f"write {self._id} {_text(name)} {quote(state, safe='')} {shown} {at}")

    def tick(self, now):
        reply = _driver.ask(f"tick {self._id} {_time(now, 'the time of a call')}")
        ran = int(reply[0])
        if not ran:
            self.info = None
            return 0, None
        self.info = {
            "gap": reply[1] == "1",
            "skipped": None if reply[2] == "?" else int(reply[2]),
            "tick": int(reply[3]),
            "time": int(reply[4]),
            "thrown": int(reply[5]),
            "waiting": int(reply[6]),
        }
        out, at = {}, 8
        for _ in range(int(reply[7])):
            name, state, kind = unquote(reply[at][1:]), reply[at + 1], reply[at + 2]
            if kind == "-":
                out[name], at = Val(state, None), at + 3
            else:
                out[name], at = Val(state, reply[at + 3] == "1" if kind == "b" else float(reply[at + 3])), at + 4
        return ran, out

    def save(self):
        return _driver.ask(f"save {self._id}")[0]

    def restore(self, saved):
        _driver.ask(f"restore {self._id} {saved}")

    def rebase(self, away=None):
        _driver.ask(f"rebase {self._id}" if away is None else f"rebase {self._id} {_time(away, 'the length')}")

    def reset(self):
        _driver.ask(f"reset {self._id}")

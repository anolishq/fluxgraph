"""Gives the second implementation the names run.py and compare.py expect."""

from __future__ import annotations

import collections
import re

from . import impl

GOOD, NOT_READY, BAD = "good", "not_ready", "bad"
Val = collections.namedtuple("Val", "state v")
CompileError = impl.CompileError
_DURATION = re.compile(r"^(\d+(?:\.\d+)?)(ms|s|m|h)$")
_UNIT = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def seconds(text):
    if isinstance(text, (int, float)):
        return float(text)
    m = _DURATION.match(str(text))
    return float(m.group(1)) * _UNIT[m.group(2)]


class Engine:
    def __init__(self, graph):
        self._engine = impl.Engine(graph)
        self.max_age = self._engine.max_age

    def write(self, name, state, value=None, age=0.0):
        self._engine.write(name, state, value, age)

    def tick(self):
        return {name: Val(state, value) for name, (state, value) in self._engine.tick().items()}

    def save(self):
        return self._engine.save()

    def restore(self, saved):
        self._engine.restore(saved)

    def reset(self):
        self._engine.reset()

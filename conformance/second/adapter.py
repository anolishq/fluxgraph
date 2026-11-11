"""Gives the second implementation the names run.py and compare.py expect."""

from __future__ import annotations

import collections
import re

from . import impl

GOOD, UNCERTAIN, NOT_READY, BAD = "good", "uncertain", "not_ready", "bad"
Val = collections.namedtuple("Val", "state v")
CompileError = impl.CompileError
_DURATION = re.compile(r"^([0-9]+(?:\.[0-9]+)?)(ns|us|ms|s|m|h)$")
_UNIT = {"ns": 1e-9, "us": 1e-6, "ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}


def seconds(text):
    m = _DURATION.match(str(text))
    return float(m.group(1)) * _UNIT[m.group(2)]


class Engine:
    def __init__(self, graph):
        self._engine = impl.Engine(graph)
        self.inputs = self._engine.inputs

    @property
    def info(self):
        return self._engine.info

    def write(self, name, state, value=None, at=None):
        self._engine.write(name, state, value, at)

    def tick(self, now):
        ran, out = self._engine.tick(now)
        return ran, None if out is None else {name: Val(state, value) for name, (state, value) in out.items()}

    def save(self):
        return self._engine.save()

    def restore(self, saved):
        self._engine.restore(saved)

    def rebase(self):
        self._engine.rebase()

    def reset(self):
        self._engine.reset()

#!/usr/bin/env python3
"""Check the format of the C++ core's saved state, and that a state it should refuse is refused.

A saved state is what leaves the process, so its layout is checked here byte by byte against what
include/fluxgraph/v2/engine.hpp says of SavedState:

    u64  the mark: the eight bytes "FGSTATE2"
    u32  the format version
    u64  the graph's fingerprint
    u64  the number of the last tick run
    u32  how many loops, then for each a byte and a u64
    u32  how many blocks, then for each a u32 length and that many bytes

  FLUXGRAPH_V2_DRIVER=build/v2/tools/fluxgraph_v2_driver/fluxgraph_v2_driver python3 conformance/cpp/saved_state.py

Two engines of one graph are run side by side on the same writes and calls. A state saved from the first is
spoiled in one way at a time and offered to the second, which has to refuse it and then go on exactly as the first
does: a refused restore changes nothing. The state as saved is then taken, to show that the spoiling and not the
restore was what was refused. Exits 1 if a layout is not as said, a spoiled state is taken, or the engines part.
"""

from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cpp import adapter  # noqa: E402

SECOND = 1_000_000_000
MARK = b"FGSTATE2"
VERSION = 1

GRAPH = {
    "period": "1s",
    "inputs": {"x": {"max_age": "none"}},
    "blocks": [
        {"id": "d", "type": "delay", "in": {"x": "x"}, "settings": {"ticks": 2, "initial": 0}},
        {
            "id": "f",
            "type": "lowpass",
            "in": {"x": "d.y"},
            "settings": {"tau": "3s", "settle": "5s"},
            "out": {"y": "y"},
        },
        {"id": "i", "type": "integrate", "in": {"x": "x"}, "out": {"y": "total"}},
    ],
}
OTHER = {
    "period": "1s",
    "inputs": {"x": {"max_age": "none"}},
    "blocks": [{"id": "i", "type": "integrate", "in": {"x": "x"}, "out": {"y": "total"}}],
}


# An estimator of one state and one port, with no test of consistency: what it saves begins with the state, its
# variance, and the place the state stands at.
ESTIMATOR = {
    "period": "1s",
    "inputs": {"u": {"max_age": "none"}, "z": {"max_age": "none"}},
    "blocks": [
        {
            "id": "k",
            "type": "estimator",
            "in": {"u": "u", "z": "z"},
            "settings": {
                "model": {"type": "linear", "A": [[0]], "B": [[1]], "C": [[1]]},
                "q": {"x0": 1},
                "p0": {"x0": 1},
                "measure": {"z": {"of": "y", "r": 1}},
                "consistency": "none",
            },
            "out": {"x0": "x"},
        }
    ],
}


def estimate(engine, k):
    engine.write("u", "good", 2.0, k * SECOND)
    engine.write("z", "good", 0.5 * k, k * SECOND)
    return engine.tick(k * SECOND)


def step(engine, k):
    engine.write("x", "good", 1.5 * k + 1, k * SECOND)
    return engine.tick(k * SECOND)


def layout(state, blocks):
    """-> the offset and the length of each block's part. Raises AssertionError where the layout is not as said."""
    assert state[:8] == MARK, f"the state begins {state[:8]!r}, not {MARK!r}"
    (version,) = struct.unpack_from("<I", state, 8)
    assert version == VERSION, f"the format version is {version}, not {VERSION}"
    at = 8 + 4 + 8 + 8  # past the mark, the version, the fingerprint and the last tick
    (loops,) = struct.unpack_from("<I", state, at)
    at += 4 + 9 * loops
    (count,) = struct.unpack_from("<I", state, at)
    assert count == blocks, f"the state says {count} blocks, and the graph has {blocks}"
    at += 4
    parts = []
    for _ in range(count):
        (length,) = struct.unpack_from("<I", state, at)
        parts.append((at, length))
        at += 4 + length
    assert at == len(state), f"the parts end at byte {at}, and the state is {len(state)} long"
    return parts


def spoiled(state, parts):
    """-> each way a state is spoiled: a name, and the bytes."""
    first_at, first_length = parts[0]
    second_at, second_length = parts[1]

    def with_u32(at, value):
        return state[:at] + struct.pack("<I", value) + state[at + 4 :]

    yield "another mark", b"FGSTATE1" + state[8:]
    yield "another version", with_u32(8, VERSION + 1)
    yield "version zero", with_u32(8, 0)
    yield "another fingerprint", state[:12] + bytes([state[12] ^ 1]) + state[13:]
    yield "cut short by a byte", state[:-1]
    yield "cut short in the header", state[:10]
    yield "a byte too many", state + b"\x00"
    yield "one block too few", with_u32(first_at - 4, len(parts) - 1)
    yield "one block too many", with_u32(first_at - 4, len(parts) + 1)
    # The two lengths changed so that the whole is as long as before: only the boundary between two blocks moves.
    yield (
        "a block's part a byte longer than the block reads",
        with_u32(first_at, first_length + 1)[: second_at - 3] + with_u32(second_at, second_length - 1)[second_at - 3 :],
    )
    yield "a block's part longer than the state", with_u32(first_at, len(state))
    # The first block is the delay, and its part begins with the place of the value it gives next.
    yield (
        "a delay's place past the values it holds",
        state[: first_at + 4] + struct.pack("<Q", 99) + state[first_at + 12 :],
    )
    # One block's part alone is wrong, and every part after it is where its length says.
    end = first_at + 4 + first_length
    yield (
        "a byte in a block's part that the block does not read",
        with_u32(first_at, first_length + 1)[:end] + b"\x00" + state[end:],
    )
    yield (
        "a block's part a byte short of what the block reads",
        with_u32(first_at, first_length - 1)[: end - 1] + state[end:],
    )


def main():
    adapter.start()
    ok = True
    first, second = adapter.Engine(GRAPH), adapter.Engine(GRAPH)
    for k in range(4):
        assert step(first, k) == step(second, k)
    state = bytes.fromhex(first.save())
    try:
        parts = layout(state, len(GRAPH["blocks"]))
    except (AssertionError, struct.error) as problem:
        print(f"THE LAYOUT IS NOT AS SAID: {problem}")
        sys.exit(1)
    print(f"a state of {len(state)} bytes, its blocks' parts of {', '.join(str(n) for _, n in parts)} bytes")

    cases = list(spoiled(state, parts))
    other = adapter.Engine(OTHER)
    step(other, 0)
    cases.append(("a state of another graph", bytes.fromhex(other.save())))
    k = 4
    for name, bad in cases:
        try:
            second.restore(bad.hex())
        except adapter.Refused as refusal:
            shown = f"refused: {refusal}"
            refused = True
        else:
            shown, refused = "TAKEN", False
        # A refused restore changes nothing: the two engines go on as one.
        same = step(first, k) == step(second, k)
        k += 1
        ok = ok and refused and same
        print(f"{name:52s} {shown}{'' if same else '; AND THE ENGINE WAS CHANGED'}")

    # The state as saved is taken, and puts the second engine where the first was when it saved.
    third = adapter.Engine(GRAPH)
    for j in range(4):
        step(third, j)
    second.restore(state.hex())
    third.restore(state.hex())
    second.rebase(SECOND)
    third.rebase(SECOND)
    taken = step(second, 4) == step(third, 4)
    ok = ok and taken
    print(f"{'the state as saved':52s} {'taken' if taken else 'TAKEN, AND THE ENGINES PART'}")

    # An estimator judges more of what it reads back than any other block: a place within a period, how many
    # values a model input has from later places, and how many innovations a port keeps.
    one, two = adapter.Engine(ESTIMATOR), adapter.Engine(ESTIMATOR)
    for j in range(3):
        assert estimate(one, j) == estimate(two, j)
    saved = bytes.fromhex(one.save())
    ((at, length),) = layout(saved, 1)
    part = at + 4 + 8 + 8 + 8  # past the state, its variance and the tick of its place
    count = part + 8 + 1 + 8  # past the part, and a model input's flag and value in force
    kept = at + 4 + length - 4 - 8 - 8  # before a port's place among its innovations, and the four flags
    # One value more than a `lag` of two periods has room for, each written out in full, and the block's length
    # made to fit: all that is wrong with the state is how many there are.
    (had,) = struct.unpack_from("<Q", saved, count)
    values = b"".join(struct.pack("<dQQ", 0.0, 0, 0) for _ in range(4))
    longer = length - 24 * had + len(values)
    too_many = (
        saved[:at]
        + struct.pack("<I", longer)
        + saved[at + 4 : count]
        + struct.pack("<Q", 4)
        + values
        + saved[count + 8 + 24 * had :]
    )
    estimator_cases = [
        ("an estimator's place past the parts of a period", saved[:part] + struct.pack("<Q", 16) + saved[part + 8 :]),
        ("more values from later places than it has room for", too_many),
        ("more innovations kept than it keeps", saved[:kept] + struct.pack("<Q", 1) + saved[kept + 8 :]),
    ]
    j = 3
    for name, bad in estimator_cases:
        try:
            two.restore(bad.hex())
        except adapter.Refused as refusal:
            shown, refused = f"refused: {refusal}", True
        else:
            shown, refused = "TAKEN", False
        same = estimate(one, j) == estimate(two, j)
        j += 1
        ok = ok and refused and same
        print(f"{name:52s} {shown}{'' if same else '; AND THE ENGINE WAS CHANGED'}")

    total = len(cases) + len(estimator_cases)
    print(f"{total} spoiled states: " + ("EVERY ONE REFUSED, AND NOTHING CHANGED" if ok else "NOT AS SAID"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

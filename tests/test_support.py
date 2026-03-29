from __future__ import annotations

from pathlib import Path


def encode_varlen(value: int) -> bytes:
    if value < 0:
        raise ValueError("value must be >= 0")

    buffer = bytearray([value & 0x7F])
    value >>= 7
    while value:
        buffer.insert(0, 0x80 | (value & 0x7F))
        value >>= 7
    return bytes(buffer)


def make_midi_file(
    path: Path,
    *,
    ticks_per_quarter: int = 96,
    tracks: list[list[tuple[int, bytes]]],
) -> Path:
    chunks: list[bytes] = []
    for events in tracks:
        payload = bytearray()
        for delta, event_bytes in events:
            payload.extend(encode_varlen(delta))
            payload.extend(event_bytes)
        if not payload.endswith(b"\x00\xFF\x2F\x00"):
            payload.extend(b"\x00\xFF\x2F\x00")
        chunks.append(b"MTrk" + len(payload).to_bytes(4, "big") + bytes(payload))

    header = (
        b"MThd"
        + (6).to_bytes(4, "big")
        + (1 if len(tracks) > 1 else 0).to_bytes(2, "big")
        + len(tracks).to_bytes(2, "big")
        + ticks_per_quarter.to_bytes(2, "big")
    )
    path.write_bytes(header + b"".join(chunks))
    return path

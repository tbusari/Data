"""Minor-frame word extraction from TMoIP (Telemetry over IP) payloads.

The paper observed 232-byte LS-28 TMoIP payloads decomposing as 8 + 24 + 200
bytes, the 200 bytes being exactly one 100-word minor frame.  The header
sizes are parameters because they are a receiver configuration, not a
standard; the default reproduces the paper's capture.
"""
from __future__ import annotations

from .frame import FrameFormat, MinorFrame


def minor_frame_from_tmoip(payload: bytes, fmt: FrameFormat = FrameFormat(), header_bytes: int = 8,
                           timestamp_bytes: int = 24) -> MinorFrame:
    start = header_bytes + timestamp_bytes
    body = payload[start:start + fmt.minor_bytes]
    if len(body) != fmt.minor_bytes:
        raise ValueError(f"payload holds {len(body)} frame bytes, expected {fmt.minor_bytes}")
    return MinorFrame.from_bytes(body, fmt)


def tmoip_from_minor_frame(frame: MinorFrame, header: bytes = b"\x00" * 8, timestamp: bytes = b"\x00" * 24) -> bytes:
    return header + timestamp + frame.to_bytes()

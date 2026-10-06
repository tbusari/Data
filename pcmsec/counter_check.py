"""Frame-counter staircase test (the paper's configuration-skew check).

Given the sequence of 16-bit values the ground extracts from the word it
*believes* carries the counter, the test is  delta == +1 (mod 2**16)  between
consecutive frames.  A window of ``window`` consecutive passes is required
before the stream is declared consistent (the paper found 0.59% chance passes
on isolated frames and none over three consecutive frames).  Deltas of n+1
read as n dropped frames (the "odometer").
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CounterCheck:
    modulus: int = 1 << 16
    window: int = 3
    max_gap: int = 1 << 15          # deltas above this (16 s of frames) are treated as skew, not drops
    last: int | None = None
    consecutive_pass: int = 0
    passes: int = 0
    fails: int = 0
    dropped_frames: int = 0
    gaps: list[int] = field(default_factory=list)
    first_fail_index: int | None = None
    first_anomaly_index: int | None = None
    index: int = 0

    def feed(self, value: int) -> str:
        """Returns 'pass', 'gap' (dropped frames inferred) or 'fail'."""
        result = "pass"
        if self.last is not None:
            delta = (value - self.last) % self.modulus
            if delta == 1:
                self.passes += 1
                self.consecutive_pass += 1
            elif 1 < delta <= self.max_gap:
                # provisionally a dropout: the odometer records it, but consistency must be
                # re-earned with ``window`` consecutive +1 steps (skew looks identical on one frame)
                self.dropped_frames += delta - 1
                self.gaps.append(delta - 1)
                self.consecutive_pass = 0
                if self.first_anomaly_index is None:
                    self.first_anomaly_index = self.index
                result = "gap"
            else:
                self.fails += 1
                self.consecutive_pass = 0
                if self.first_anomaly_index is None:
                    self.first_anomaly_index = self.index
                if self.first_fail_index is None:
                    self.first_fail_index = self.index
                result = "fail"
        self.last = value
        self.index += 1
        return result

    @property
    def consistent(self) -> bool:
        return self.consecutive_pass >= self.window

    def summary(self) -> dict:
        return {"frames": self.index, "passes": self.passes, "fails": self.fails,
                "dropped_frames": self.dropped_frames, "gap_events": len(self.gaps),
                "first_fail_index": self.first_fail_index, "first_anomaly_index": self.first_anomaly_index,
                "consistent": self.consistent}

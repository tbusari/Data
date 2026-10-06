"""Configuration identity carried in the bitstream.

The paper's central risk is version skew between the frame definition
compiled into the chassis and the parameter database loaded on the ground.
A *configuration number* word identifies a version only against a registry;
a *configuration hash* identifies the content itself.  Both sides compute

    CFGH = Ascon-Hash256(canonical frame map)[:4]

from their own description of the frame (XidML on the air side, the exported
LDPS pair / TMATS on the ground side) and the encryptor transmits its CFGH in
the security channel once per major frame.  A mismatch is a mismatch of
content, not of file discipline.

The canonical form is intentionally small and vendor-neutral: anything that
changes the *meaning* of a word position changes the hash; cosmetic changes
(descriptions, colours, engineering-unit labels) do not.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from typing import Iterable

from . import ascon


@dataclass(frozen=True)
class Placement:
    name: str                 # parameter name as it appears in both databases
    word: int                 # minor-frame word index (16-bit words, sync = words 0-1)
    minor: int | None = None  # None = every minor frame (super/normal commutation); else SFID of the slot
    bits: int = 16
    msb_first: bool = True
    dtype: str = "u16"        # u16, s16, bits, ieee32-hi, ieee32-lo, ... (a label the converter understands)


@dataclass(frozen=True)
class FrameMap:
    bit_rate: int
    words_per_minor: int
    minors_per_major: int
    bits_per_word: int
    sync_pattern: int
    sfid_word: int
    placements: tuple[Placement, ...]

    def canonical(self) -> bytes:
        d = {
            "bit_rate": self.bit_rate,
            "words_per_minor": self.words_per_minor,
            "minors_per_major": self.minors_per_major,
            "bits_per_word": self.bits_per_word,
            "sync_pattern": self.sync_pattern,
            "sfid_word": self.sfid_word,
            "placements": sorted((asdict(p) for p in self.placements),
                                 key=lambda p: (p["word"], -1 if p["minor"] is None else p["minor"], p["name"])),
        }
        return json.dumps(d, sort_keys=True, separators=(",", ":")).encode()

    def digest(self) -> bytes:
        return ascon.hash256(self.canonical())

    def config_hash(self) -> int:
        """32-bit truncated digest, as transmitted in the security channel."""
        return int.from_bytes(self.digest()[:4], "big")

    def to_json(self) -> str:
        return json.dumps(json.loads(self.canonical()), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "FrameMap":
        d = json.loads(text)
        return cls(d["bit_rate"], d["words_per_minor"], d["minors_per_major"], d["bits_per_word"],
                   d["sync_pattern"], d["sfid_word"],
                   tuple(Placement(**p) for p in d["placements"]))


def diff(a: FrameMap, b: FrameMap) -> list[str]:
    """Human-readable list of what differs (for the pre-flight report)."""
    out = []
    for k in ("bit_rate", "words_per_minor", "minors_per_major", "bits_per_word", "sync_pattern", "sfid_word"):
        if getattr(a, k) != getattr(b, k):
            out.append(f"{k}: {getattr(a, k)} != {getattr(b, k)}")
    pa = {(p.name): p for p in a.placements}
    pb = {(p.name): p for p in b.placements}
    for n in sorted(set(pa) | set(pb)):
        if n not in pb:
            out.append(f"{n}: only in A (word {pa[n].word})")
        elif n not in pa:
            out.append(f"{n}: only in B (word {pb[n].word})")
        elif pa[n] != pb[n]:
            out.append(f"{n}: A word {pa[n].word}/minor {pa[n].minor} != B word {pb[n].word}/minor {pb[n].minor}")
    return out


def morgan_state_baseline(secure: bool = True) -> FrameMap:
    """The frame of the paper, re-expressed in 16-bit word indices, with the
    security words added when ``secure`` is True.  Video words are placed as
    two 16-bit words per instance; instrumentation words are illustrative."""
    pl: list[Placement] = [Placement("SFID", 2, None)]
    start = 5 if secure else 3
    if secure:
        pl += [Placement("FCNT_LO", 3, None), Placement("SEC_CHANNEL", 4, None)]
    # 30 video instances x 2 words
    w = start
    for i in range(30):
        cam = 1 if i < 15 else 2
        pl.append(Placement(f"VID{cam}_{i % 15:02d}_HI", w, None))
        pl.append(Placement(f"VID{cam}_{i % 15:02d}_LO", w + 1, None))
        w += 2
    pl.append(Placement("PRESSURE_SUBCOM", w, None)); w += 1
    names = ["TEMP4", "TEMP5", "TEMP13", "BARO_ALT", "GNSS_LAT_HI", "GNSS_LAT_LO", "GNSS_LON_HI",
             "GNSS_LON_LO", "GNSS_ALT_HI", "GNSS_ALT_LO", "GNSS_VN", "GNSS_VE", "GNSS_VD", "GNSS_TOW_HI",
             "GNSS_TOW_LO", "STATUS", "CHASSIS_COUNTER"]
    last_payload = 100 - (4 if secure else 0)
    for i, n in enumerate(names):
        pl.append(Placement(n, w + (i % max(1, last_payload - w)), 1 + i // max(1, last_payload - w)))
    if secure:
        for i in range(4):
            pl.append(Placement(f"TAG{i}", 96 + i, None))
    return FrameMap(3_276_800, 100, 32, 16, 0xFE6B2840, 2, tuple(pl))

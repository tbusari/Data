"""IRIG-106 Chapter 4 minor/major frame model and the security word layout.

The model is deliberately word-oriented: the ground segment (LS-28 frame
synchroniser + decommutator) operates on 16-bit words located by minor-frame
word index and SFID, and every security field is placed so that *the COTS
frame synchroniser and decommutator need no change*.

Baseline (as flown by the Morgan State vehicle, re-expressed in 16-bit words):

    word 0-1   32-bit frame synchronisation pattern      (clear)
    word 2     SFID, 0..31                                (clear)
    word 3     frame counter, low 16 bits                 (clear, authenticated)
    word 4     security channel word, subcommutated       (clear, authenticated)
    word 5..   payload (video, pressure, GNSS, ...)       (encrypted)
    tail       authentication tag words (profile A only)  (clear)

The "security channel" is one word per minor frame, indexed by SFID, i.e. a
64-byte record per major frame carrying the session identifier, the upper
32 bits of the frame counter, the configuration hash, a profile descriptor
and (profile B) the deferred tag of the previous major frame.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import struct

IRIG_SYNC_32 = 0xFE6B2840  # IRIG 106 Chapter 4, Appendix C recommended 32-bit pattern


@dataclass(frozen=True)
class FrameFormat:
    words_per_minor: int = 100          # transmitted words incl. sync and SFID
    minors_per_major: int = 32
    bits_per_word: int = 16
    major_rate_hz: float = 64.0
    sync_pattern: int = IRIG_SYNC_32
    sync_words: int = 2
    sfid_word: int = 2

    @property
    def minor_rate_hz(self) -> float:
        return self.major_rate_hz * self.minors_per_major

    @property
    def bit_rate(self) -> float:
        return self.minor_rate_hz * self.words_per_minor * self.bits_per_word

    @property
    def minor_bytes(self) -> int:
        return self.words_per_minor * self.bits_per_word // 8


@dataclass(frozen=True)
class SecurityLayout:
    """Which words of the minor frame the security layer owns."""
    counter_word: int = 3
    sec_word: int = 4
    tag_words: int = 4                 # 4 words = 64-bit tag (profile A); 0 for profile B
    payload_start: int = 5

    def payload_slice(self, fmt: FrameFormat) -> slice:
        return slice(self.payload_start, fmt.words_per_minor - self.tag_words)

    def tag_slice(self, fmt: FrameFormat) -> slice:
        return slice(fmt.words_per_minor - self.tag_words, fmt.words_per_minor)

    def payload_words(self, fmt: FrameFormat) -> int:
        return fmt.words_per_minor - self.tag_words - self.payload_start

    def overhead_words(self) -> int:
        """Words spent on security per minor frame (counter + sec channel + tag)."""
        return 2 + self.tag_words

    def overhead_fraction(self, fmt: FrameFormat) -> float:
        return self.overhead_words() / fmt.words_per_minor


# --------------------------------------------------------------------------- #
# Security channel record (64 bytes per major frame, 2 bytes per SFID slot)
# --------------------------------------------------------------------------- #

SEC_VERSION = 1
PROFILE_A = 0xA  # per-minor-frame Ascon-AEAD128, truncated tag in tail words
PROFILE_B = 0xB  # per-minor-frame AES-256-CTR, deferred AES-CMAC-64 tag per major frame

_SEC_STRUCT = struct.Struct(">8sIIBBH8s36s")  # 64 bytes
assert _SEC_STRUCT.size == 64


@dataclass
class SecRecord:
    session_id: bytes               # 8 bytes, random per power-up of the encryptor
    counter_hi: int                 # upper 32 bits of the 48-bit frame counter for this major frame
    config_hash: int                # 32-bit truncated Ascon-Hash256 of the canonical frame map
    profile: int                    # PROFILE_A or PROFILE_B
    tag_words: int                  # tag words in tail (profile A) -- lets the ground self-configure
    key_id: int                     # which pre-shared master key (0..65535)
    deferred_tag: bytes = b"\x00" * 8   # profile B: CMAC-64 of the *previous* major frame
    reserved: bytes = b"\x00" * 36

    def pack(self) -> bytes:
        return _SEC_STRUCT.pack(self.session_id, self.counter_hi, self.config_hash,
                                (SEC_VERSION << 4) | (self.profile & 0xF), self.tag_words,
                                self.key_id, self.deferred_tag, self.reserved)

    @classmethod
    def unpack(cls, b: bytes) -> "SecRecord":
        sid, hi, ch, vp, tw, kid, dt, rsv = _SEC_STRUCT.unpack(b)
        if vp >> 4 != SEC_VERSION:
            raise ValueError(f"unsupported security channel version {vp >> 4}")
        return cls(sid, hi, ch, vp & 0xF, tw, kid, dt, rsv)

    def words(self) -> list[int]:
        """The 32 sixteen-bit words, indexed by SFID."""
        b = self.pack()
        return [int.from_bytes(b[2 * i:2 * i + 2], "big") for i in range(32)]

    @classmethod
    def from_words(cls, words: list[int | None]) -> "SecRecord":
        if len(words) != 32 or any(w is None for w in words):
            raise ValueError("need all 32 security-channel words")
        return cls.unpack(b"".join(int(w).to_bytes(2, "big") for w in words))

    # Field-level access: the ground should not need all 32 slots to use the
    # ones it has.  Header = SFID slots 0..9, deferred tag = slots 10..13.
    HEADER_SLOTS = range(0, 10)
    TAG_SLOTS = range(10, 14)

    @classmethod
    def header_from_words(cls, words: list[int | None]) -> "SecRecord | None":
        if any(words[i] is None for i in cls.HEADER_SLOTS):
            return None
        b = b"".join(int(words[i]).to_bytes(2, "big") for i in cls.HEADER_SLOTS)
        sid, hi, ch, vp, tw, kid = struct.unpack(">8sIIBBH", b)
        if vp >> 4 != SEC_VERSION:
            raise ValueError(f"unsupported security channel version {vp >> 4}")
        return cls(sid, hi, ch, vp & 0xF, tw, kid)

    @classmethod
    def deferred_tag_from_words(cls, words: list[int | None]) -> bytes | None:
        if any(words[i] is None for i in cls.TAG_SLOTS):
            return None
        return b"".join(int(words[i]).to_bytes(2, "big") for i in cls.TAG_SLOTS)


# --------------------------------------------------------------------------- #
# Minor frame container
# --------------------------------------------------------------------------- #

@dataclass
class MinorFrame:
    words: list[int]                 # words_per_minor 16-bit values
    fmt: FrameFormat = field(default_factory=FrameFormat)

    def __post_init__(self):
        if len(self.words) != self.fmt.words_per_minor:
            raise ValueError("wrong number of words")

    # clear header -----------------------------------------------------------
    @property
    def sync(self) -> int:
        return (self.words[0] << 16) | self.words[1]

    @property
    def sfid(self) -> int:
        return self.words[self.fmt.sfid_word]

    def to_bytes(self) -> bytes:
        return b"".join(w.to_bytes(2, "big") for w in self.words)

    @classmethod
    def from_bytes(cls, b: bytes, fmt: FrameFormat = FrameFormat()) -> "MinorFrame":
        if len(b) != fmt.minor_bytes:
            raise ValueError(f"expected {fmt.minor_bytes} bytes, got {len(b)}")
        return cls([int.from_bytes(b[i:i + 2], "big") for i in range(0, len(b), 2)], fmt)

    def copy(self) -> "MinorFrame":
        return MinorFrame(list(self.words), self.fmt)


def words_to_bytes(words: list[int]) -> bytes:
    return b"".join(int(w).to_bytes(2, "big") for w in words)


def bytes_to_words(b: bytes) -> list[int]:
    if len(b) % 2:
        raise ValueError("odd byte count")
    return [int.from_bytes(b[i:i + 2], "big") for i in range(0, len(b), 2)]


def build_minor_frame(fmt: FrameFormat, sfid: int, payload: list[int], layout: SecurityLayout | None = None,
                      counter_lo: int = 0, sec_word: int = 0) -> MinorFrame:
    """Assemble a minor frame from its parts (payload length must match the layout)."""
    layout = layout or SecurityLayout()
    words = [0] * fmt.words_per_minor
    words[0] = fmt.sync_pattern >> 16
    words[1] = fmt.sync_pattern & 0xFFFF
    words[fmt.sfid_word] = sfid & 0xFFFF
    words[layout.counter_word] = counter_lo & 0xFFFF
    words[layout.sec_word] = sec_word & 0xFFFF
    ps = layout.payload_slice(fmt)
    if len(payload) != layout.payload_words(fmt):
        raise ValueError(f"payload must be {layout.payload_words(fmt)} words, got {len(payload)}")
    words[ps] = [p & 0xFFFF for p in payload]
    return MinorFrame(words, fmt)

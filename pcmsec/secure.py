"""Bump-in-the-wire encryptor and ground-side decryptor for a Chapter 4 PCM stream.

Hardware envelope (nothing in the RF chain changes):

    KAM-500 BCU/101 ──clock/data NRZ-L──► [encryptor] ──clock/data──► nanoTX (PCM/FM)
    LS-28 DRSM (bit sync, frame sync, decom) ──TMoIP──► [decryptor on the PC] ──► LDPS / IADS

The encryptor frame-synchronises on the clear sync pattern, reads the SFID,
and rewrites only the words it owns (counter, security channel, payload,
tag).  Every operation is *online*: the ciphertext of a word depends only on
earlier words of the same frame, so the device adds at most one word of
latency (4.9 us at 3.2768 Mb/s).

Two profiles share the frame layout and the security channel:

Profile A  per-minor-frame Ascon-AEAD128 (NIST SP 800-232), truncated tag in
           the tail words.  Each minor frame is independently decryptable
           and authenticated; a dropout of any length costs nothing beyond
           the frames that were lost.  Overhead: 2 + tag_words words.
Profile B  per-minor-frame AES-256-CTR with one deferred AES-CMAC tag per
           major frame, carried in the *next* major frame's security
           channel.  Overhead: 2 words.  Authentication granularity is one
           major frame (15.6 ms) and requires all 32 minor frames.

Nonce (16 bytes) = session_id(8) || frame_counter(6, big-endian 48-bit) || profile(1) || 0x00
Associated data   = the clear words 2..4 (SFID, counter-low, security word).  The sync
                    pattern is excluded: it is constant, and the frame synchroniser accepts
                    it with a few bit errors, so authenticating it would reject frames the
                    ground otherwise recovers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import struct

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import cmac

from . import ascon, keys
from .frame import (FrameFormat, SecurityLayout, SecRecord, MinorFrame, PROFILE_A, PROFILE_B,
                    words_to_bytes, bytes_to_words)

FC_BITS = 48
FC_MASK = (1 << FC_BITS) - 1


def make_nonce(session_id: bytes, fc: int, profile: int) -> bytes:
    return session_id + (fc & FC_MASK).to_bytes(6, "big") + bytes([profile & 0xFF, 0])


def _aes_ctr(key: bytes, nonce: bytes, data: bytes) -> bytes:
    # 16-byte initial counter block = nonce with the low 16 bits reserved for the block counter
    iv = nonce[:14] + b"\x00\x00"
    enc = Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor()
    return enc.update(data) + enc.finalize()


def _cmac64(key: bytes, data: bytes) -> bytes:
    c = cmac.CMAC(algorithms.AES(key))
    c.update(data)
    return c.finalize()[:8]


# --------------------------------------------------------------------------- #
# Encryptor
# --------------------------------------------------------------------------- #

@dataclass
class Encryptor:
    master_key: bytes
    key_id: int = 0
    profile: int = PROFILE_A
    fmt: FrameFormat = field(default_factory=FrameFormat)
    layout: SecurityLayout = field(default_factory=SecurityLayout)
    config_hash: int = 0
    session_id: bytes = field(default_factory=keys.new_session_id)
    fc: int = 0                            # 48-bit frame counter, fc & 31 == SFID by construction
    _started: bool = False
    _sec_words: list[int] = field(default_factory=list)
    _mf_bytes: bytearray = field(default_factory=bytearray)   # profile B: current major frame for CMAC
    _deferred_tag: bytes = b"\x00" * 8

    def __post_init__(self):
        if self.profile == PROFILE_A:
            self._key = keys.profile_a_key(self.master_key, self.session_id)
            if self.layout.tag_words < 2:
                raise ValueError("profile A needs at least 2 tag words (32-bit tag)")
        elif self.profile == PROFILE_B:
            self._ctr_key, self._mac_key = keys.profile_b_keys(self.master_key, self.session_id)
            if self.layout.tag_words != 0:
                raise ValueError("profile B carries no per-frame tag; set tag_words=0")
        else:
            raise ValueError("unknown profile")

    # -- security channel ----------------------------------------------------
    def _new_sec_record(self) -> list[int]:
        rec = SecRecord(self.session_id, (self.fc >> 16) & 0xFFFFFFFF, self.config_hash, self.profile,
                        self.layout.tag_words, self.key_id, self._deferred_tag)
        return rec.words()

    # -- main entry ----------------------------------------------------------
    def process(self, frame: MinorFrame) -> MinorFrame:
        """Return the secured copy of ``frame``.  Frames must arrive in stream order."""
        sfid = frame.sfid
        if not self._started:
            if sfid != 0:
                # wait for a major-frame boundary so fc & 31 == SFID; pass through untouched
                return frame.copy()
            self._started = True
        # keep fc aligned to the SFID without ever moving backwards (no nonce reuse)
        if (self.fc & 31) != sfid:
            self.fc = ((self.fc >> 5) + 1) << 5 | sfid
        if sfid == 0:
            self._sec_words = self._new_sec_record()
            self._mf_bytes = bytearray()

        out = frame.copy()
        out.words[self.layout.counter_word] = self.fc & 0xFFFF
        out.words[self.layout.sec_word] = self._sec_words[sfid]
        ad = words_to_bytes(out.words[self.fmt.sync_words:self.layout.payload_start])
        pt = words_to_bytes(frame.words[self.layout.payload_slice(self.fmt)])
        nonce = make_nonce(self.session_id, self.fc, self.profile)

        if self.profile == PROFILE_A:
            ct, tag = ascon.aead_encrypt(self._key, nonce, ad, pt, tag_bytes=2 * self.layout.tag_words)
            out.words[self.layout.payload_slice(self.fmt)] = bytes_to_words(ct)
            out.words[self.layout.tag_slice(self.fmt)] = bytes_to_words(tag)
        else:
            ct = _aes_ctr(self._ctr_key, nonce, pt)
            out.words[self.layout.payload_slice(self.fmt)] = bytes_to_words(ct)
            self._mf_bytes += out.to_bytes()
            if sfid == self.fmt.minors_per_major - 1:
                mf = (self.fc >> 5).to_bytes(6, "big")
                self._deferred_tag = _cmac64(self._mac_key, mf + bytes(self._mf_bytes))

        self.fc = (self.fc + 1) & FC_MASK
        return out


# --------------------------------------------------------------------------- #
# Decryptor
# --------------------------------------------------------------------------- #

@dataclass
class DecryptResult:
    status: str                 # ok | auth_fail | no_session | replay | sync_fail | sfid_fail | pending_auth
    sfid: int
    fc: int | None = None
    payload: list[int] | None = None
    note: str = ""


@dataclass
class MajorAuthResult:
    mf: int
    status: str                 # authenticated | auth_fail | incomplete | unverified


@dataclass
class Decryptor:
    master_keys: dict[int, bytes]
    fmt: FrameFormat = field(default_factory=FrameFormat)
    layout: SecurityLayout = field(default_factory=SecurityLayout)
    expected_config_hash: int | None = None
    replay_protect: bool = True
    epoch_search: int = 2                  # profile A: counter_hi candidates to try after an outage
    sync_tolerance_bits: int = 2           # as a frame synchroniser would accept

    session_id: bytes | None = None
    profile: int | None = None
    counter_hi: int | None = None
    config_hash: int | None = None
    config_match: bool | None = None
    last_fc: int = -1
    _sec_words: list[int | None] = field(default_factory=lambda: [None] * 32)
    _sec_mf: int | None = None             # (fcnt_lo >> 5) of the major frame being collected
    _pending: list[MinorFrame] = field(default_factory=list)
    _mf_frames: dict[int, dict[int, bytes]] = field(default_factory=dict)   # profile B: mf -> sfid -> bytes
    _deferred_tags: dict[int, bytes] = field(default_factory=dict)         # profile B: mf -> tag for mf
    _poisoned: set[int] = field(default_factory=set)                        # profile B: mf with conflicting frames
    _retry: list[MinorFrame] = field(default_factory=list)                 # profile A: frames awaiting an epoch update
    _late: list[DecryptResult] = field(default_factory=list)                # results produced while absorbing a header
    retry_depth: int = 64
    _sec_header_done: bool = False
    _sec_tag_done: bool = False
    stats: dict[str, int] = field(default_factory=dict)
    major_results: list[MajorAuthResult] = field(default_factory=list)

    def _count(self, k: str) -> None:
        self.stats[k] = self.stats.get(k, 0) + 1

    # -- security channel ----------------------------------------------------
    def _absorb_sec_word(self, frame: MinorFrame) -> None:
        sfid = frame.sfid
        lo = frame.words[self.layout.counter_word]
        mf_lo = lo >> 5
        if self._sec_mf != mf_lo:
            self._sec_words = [None] * 32
            self._sec_mf = mf_lo
            self._sec_header_done = False
            self._sec_tag_done = False
        self._sec_words[sfid] = frame.words[self.layout.sec_word]
        if not self._sec_header_done:
            try:
                rec = SecRecord.header_from_words(self._sec_words)
            except ValueError:
                rec = None
            if rec is not None:
                self._sec_header_done = True
                self._apply_header(rec)
        if not self._sec_tag_done and self.profile == PROFILE_B and self.counter_hi is not None:
            tag = SecRecord.deferred_tag_from_words(self._sec_words)
            if tag is not None:
                self._sec_tag_done = True
                if tag != b"\x00" * 8:
                    this_mf = ((self.counter_hi << 16) | (self._sec_mf << 5)) >> 5
                    self._deferred_tags[this_mf - 1] = tag
                    self._verify_major(this_mf - 1)

    def _apply_header(self, rec: SecRecord) -> None:
        if rec.key_id not in self.master_keys:
            self._count("unknown_key_id")
            return
        if self.session_id != rec.session_id or self.profile != rec.profile:
            self.session_id, self.profile = rec.session_id, rec.profile
            if rec.profile == PROFILE_A:
                self._key = keys.profile_a_key(self.master_keys[rec.key_id], rec.session_id)
            else:
                self._ctr_key, self._mac_key = keys.profile_b_keys(self.master_keys[rec.key_id], rec.session_id)
            self.last_fc = -1
            self._count("session_established")
        if rec.tag_words != self.layout.tag_words:
            self._count("layout_mismatch")
        # never let a (possibly replayed) header move the epoch below authenticated data
        floor = (self.last_fc >> 16) if self.last_fc >= 0 else 0
        self.counter_hi = max(rec.counter_hi, floor)
        self.config_hash = rec.config_hash
        if self._retry and self.profile == PROFILE_A:
            # frames that failed before this header (e.g. after an outage longer than the
            # epoch search) get one more attempt with the epoch the header announces
            pending, self._retry = self._retry, []
            for f in pending:
                r = self._try_profile_a(f)
                if r is None:
                    r = DecryptResult("auth_fail", f.sfid)
                    self._count("auth_fail")
                self._late.append(r)
        if self.expected_config_hash is not None:
            self.config_match = (rec.config_hash == self.expected_config_hash)

    def _verify_major(self, mf: int) -> None:
        tag = self._deferred_tags.get(mf)
        frames = self._mf_frames.get(mf)
        if tag is None or frames is None:
            return
        if mf in self._poisoned:
            self.major_results.append(MajorAuthResult(mf, "auth_fail"))
            self._count("major_auth_fail")
        elif len(frames) != self.fmt.minors_per_major:
            self.major_results.append(MajorAuthResult(mf, "incomplete"))
            self._count("major_incomplete")
        else:
            body = mf.to_bytes(6, "big") + b"".join(frames[s] for s in range(self.fmt.minors_per_major))
            ok = _cmac64(self._mac_key, body) == tag
            self.major_results.append(MajorAuthResult(mf, "authenticated" if ok else "auth_fail"))
            self._count("major_authenticated" if ok else "major_auth_fail")
            if ok:
                # profile B advances the replay window only on authenticated data
                self.last_fc = max(self.last_fc, (mf << 5) | (self.fmt.minors_per_major - 1))
        self._mf_frames.pop(mf, None)
        self._deferred_tags.pop(mf, None)
        self._poisoned.discard(mf)

    # -- per-frame decryption ------------------------------------------------
    WRAP_WINDOW = 1 << 12   # profile B: a backwards jump counts as a 2**16 wrap only near the wrap point

    def _candidates(self, lo: int) -> list[int]:
        assert self.counter_hi is not None
        base = [(self.counter_hi << 16) | lo]
        if self.last_fc >= 0 and lo < (self.last_fc & 0xFFFF):
            last_lo = self.last_fc & 0xFFFF
            if self.profile == PROFILE_A or (last_lo >= 0x10000 - self.WRAP_WINDOW and lo < self.WRAP_WINDOW):
                base = [((self.counter_hi + 1) << 16) | lo] + base
        if self.profile == PROFILE_A:
            for k in range(1, self.epoch_search + 1):
                base.append(((self.counter_hi + k) << 16) | lo)
        return base

    def _try_profile_a(self, frame: MinorFrame) -> DecryptResult | None:
        """Authenticate and decrypt one frame; None if no epoch candidate verifies."""
        sfid = frame.sfid
        lo = frame.words[self.layout.counter_word]
        ad = words_to_bytes(frame.words[self.fmt.sync_words:self.layout.payload_start])
        ct = words_to_bytes(frame.words[self.layout.payload_slice(self.fmt)])
        tag = words_to_bytes(frame.words[self.layout.tag_slice(self.fmt)])
        for fc in self._candidates(lo):
            pt = ascon.aead_decrypt(self._key, make_nonce(self.session_id, fc, PROFILE_A), ad, ct, tag)
            if pt is not None:
                if self.replay_protect and fc <= self.last_fc:
                    self._count("replay")
                    return DecryptResult("replay", sfid, fc)
                self.last_fc = fc
                self.counter_hi = fc >> 16
                self._count("ok")
                return DecryptResult("ok", sfid, fc, bytes_to_words(pt))
        return None

    def _decrypt(self, frame: MinorFrame) -> DecryptResult | None:
        sfid = frame.sfid
        if self.profile == PROFILE_A:
            r = self._try_profile_a(frame)
            if r is not None:
                return r
            # hold the frame until the next security-channel header; the oldest held frame
            # is condemned when the buffer is full (injected frames leave this way)
            if len(self._retry) >= self.retry_depth:
                old = self._retry.pop(0)
                self._count("auth_fail")
                self._late.append(DecryptResult("auth_fail", old.sfid))
            self._retry.append(frame)
            return None
        else:
            lo = frame.words[self.layout.counter_word]
            ct = words_to_bytes(frame.words[self.layout.payload_slice(self.fmt)])
            fc = self._candidates(lo)[0]
            if self.replay_protect and fc <= self.last_fc:
                self._count("replay")
                return DecryptResult("replay", sfid, fc)
            pt = _aes_ctr(self._ctr_key, make_nonce(self.session_id, fc, PROFILE_B), ct)
            slot = self._mf_frames.setdefault(fc >> 5, {})
            raw = frame.to_bytes()
            if sfid in slot and slot[sfid] != raw:
                self._poisoned.add(fc >> 5)      # two different frames claim the same position
            slot[sfid] = raw
            self._count("pending_auth")
            return DecryptResult("pending_auth", sfid, fc, bytes_to_words(pt),
                                 note="authenticity decided by the next major frame's deferred tag")

    def flush(self) -> list[MajorAuthResult]:
        """End of stream / end of session: report profile-B major frames whose deferred tag never arrived."""
        out = []
        for mf in sorted(self._mf_frames):
            r = MajorAuthResult(mf, "unverified")
            self.major_results.append(r)
            self._count("major_unverified")
            out.append(r)
        self._mf_frames.clear()
        for f in self._retry:
            self._count("auth_fail")
            self._late.append(DecryptResult("auth_fail", f.sfid))
        self._retry = []
        return out

    def drain(self) -> list[DecryptResult]:
        """Results produced outside feed() (retries, condemnations); call after flush()."""
        out, self._late = self._late, []
        return out

    def feed(self, frame: MinorFrame) -> list[DecryptResult]:
        """Feed one received minor frame; returns zero or more results (buffered frames may be released)."""
        if bin(frame.sync ^ self.fmt.sync_pattern).count("1") > self.sync_tolerance_bits:
            self._count("sync_fail")
            return [DecryptResult("sync_fail", -1)]
        if frame.sfid >= self.fmt.minors_per_major:
            # a corrupted SFID word; the LS-28 SFID tracker would also reject this frame
            self._count("sfid_fail")
            return [DecryptResult("sfid_fail", frame.sfid)]
        self._absorb_sec_word(frame)
        if self.session_id is None or self.counter_hi is None:
            # cold start: hold frames of this major frame until its security record completes
            self._pending.append(frame)
            if len(self._pending) > 2 * self.fmt.minors_per_major:
                dropped = self._pending.pop(0)
                self._count("no_session")
                return [DecryptResult("no_session", dropped.sfid)]
            return []
        results, self._late = self._late, []
        if self._pending:
            for f in self._pending:
                r = self._decrypt(f)
                if r is not None:
                    results.append(r)
            self._pending = []
        r = self._decrypt(frame)
        results += self._late          # retries triggered while absorbing this frame's header
        self._late = []
        if r is not None:
            results.append(r)
        return results

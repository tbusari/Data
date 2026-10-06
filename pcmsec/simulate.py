"""End-to-end simulation: source -> encryptor -> channel -> decryptor + checks.

    python -m pcmsec.simulate --seconds 5 --profile A --ber 1e-6 --out results/sim_A.json

The channel model is the ground-visible loss model of the paper: the link is
error-free until threshold, loses lock for whole intervals (dropouts), and
the frame synchroniser tolerates a small number of bit errors in the sync
pattern.  Adversarial events are added explicitly: injection of well-formed
frames by someone who knows the format but not the key, replay of an earlier
major frame, and a ground-side layout (configuration) skew of one word.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from dataclasses import dataclass, field

from .frame import FrameFormat, SecurityLayout, MinorFrame, build_minor_frame, PROFILE_A, PROFILE_B
from .secure import Encryptor, Decryptor
from .counter_check import CounterCheck
from .configid import morgan_state_baseline, FrameMap, Placement


# --------------------------------------------------------------------------- #
# Source model
# --------------------------------------------------------------------------- #

def synth_payload(rnd: random.Random, fc: int, n_words: int) -> list[int]:
    """60 video words (high entropy, H.264), 1 pressure word, the rest low-entropy instrumentation."""
    words = [rnd.getrandbits(16) for _ in range(60)]
    pressure = int(32768 + 8000 * math.sin(2 * math.pi * fc / 4096) + rnd.gauss(0, 5.2))
    words.append(max(0, min(65535, pressure)))
    sfid = fc & 31
    for i in range(n_words - 61):
        if sfid == 0:
            words.append(0)                               # instrumentation absent in minor frame 0 (paper)
        elif i % 7 == 0:
            words.append(int(2731 + rnd.gauss(0, 10)))    # thermocouple-like, slowly varying
        elif i % 7 == 1:
            words.append(fc & 0xFFFF)                     # chassis-native counter (paper's check word)
        else:
            words.append(0x0000 if i % 3 else 0x0001)     # status words: long runs of zeros
    return words[:n_words]


def transition_stats(frames: list[MinorFrame]) -> dict:
    """NRZ-L transition density and longest run over the serialized stream."""
    bits = []
    for f in frames:
        for w in f.words:
            bits.append(w)
    # work on bytes for speed
    data = b"".join(w.to_bytes(2, "big") for w in bits)
    n = len(data) * 8
    val = int.from_bytes(data, "big")
    transitions = bin(val ^ (val >> 1) & ((1 << (n - 1)) - 1)).count("1")
    s = bin(val)[2:].zfill(n)
    longest = max(len(r) for r in s.replace("1", " ").split()) if "0" in s else 0
    longest = max(longest, max((len(r) for r in s.replace("0", " ").split()), default=0))
    return {"bits": n, "transition_density": transitions / (n - 1), "longest_run": longest}


# --------------------------------------------------------------------------- #
# Channel model
# --------------------------------------------------------------------------- #

@dataclass
class ChannelConfig:
    ber: float = 0.0
    sync_tolerance_bits: int = 2
    dropouts: list[tuple[int, int]] = field(default_factory=list)   # (start_frame_index, n_frames)
    inject_after: int | None = None          # index after which the attacker inserts frames
    inject_count: int = 0
    replay_major_frame: int | None = None    # which earlier major frame to replay
    replay_at: int | None = None             # insert position


def apply_channel(frames: list[MinorFrame], cfg: ChannelConfig, rnd: random.Random, layout: SecurityLayout) -> tuple[list[MinorFrame], dict]:
    fmt = frames[0].fmt
    out: list[MinorFrame] = []
    lost_to_dropout = 0
    lost_to_sync = 0
    flipped_bits = 0
    drop = set()
    for start, n in cfg.dropouts:
        drop.update(range(start, start + n))
    injected = 0
    replayed = 0
    for i, f in enumerate(frames):
        if i in drop:
            lost_to_dropout += 1
            continue
        g = f.copy()
        if cfg.ber > 0:
            nbits = fmt.words_per_minor * 16
            k = sum(1 for _ in range(nbits) if rnd.random() < cfg.ber) if cfg.ber > 1e-3 else \
                (rnd.random() < nbits * cfg.ber) * 1  # Poisson-ish for small BER
            for _ in range(k):
                b = rnd.randrange(nbits)
                g.words[b // 16] ^= 1 << (15 - b % 16)
                flipped_bits += 1
            if bin(g.sync ^ fmt.sync_pattern).count("1") > cfg.sync_tolerance_bits:
                lost_to_sync += 1
                continue
        out.append(g)
        if cfg.inject_after is not None and i == cfg.inject_after:
            # attacker: valid sync, continuing SFID and counter, copies the security word, random payload+tag
            for j in range(cfg.inject_count):
                fake = g.copy()
                fake.words[fmt.sfid_word] = (g.sfid + 1 + j) % 32
                fake.words[layout.counter_word] = (g.words[layout.counter_word] + 1 + j) & 0xFFFF
                for w in range(layout.payload_start, fmt.words_per_minor):
                    fake.words[w] = rnd.getrandbits(16)
                out.append(fake)
                injected += 1
        if cfg.replay_at is not None and i == cfg.replay_at and cfg.replay_major_frame is not None:
            s = cfg.replay_major_frame * fmt.minors_per_major
            for r in frames[s:s + fmt.minors_per_major]:
                out.append(r.copy())
                replayed += 1
    return out, {"lost_to_dropout": lost_to_dropout, "lost_to_sync_corruption": lost_to_sync,
                 "flipped_bits": flipped_bits, "injected": injected, "replayed": replayed}


# --------------------------------------------------------------------------- #
# Scenario runner
# --------------------------------------------------------------------------- #

def skewed_map(base: FrameMap, words: int) -> FrameMap:
    """The ground's belief about the frame after a geometry-preserving relocation: every
    payload parameter moved by ``words`` (as a burst-placement reflow would do)."""
    moved = tuple(Placement(p.name, p.word + words, p.minor, p.bits, p.msb_first, p.dtype)
                  if 5 <= p.word < 96 else p for p in base.placements)
    return FrameMap(base.bit_rate, base.words_per_minor, base.minors_per_major, base.bits_per_word,
                    base.sync_pattern, base.sfid_word, moved)


def run(seconds: float, profile: str, ber: float, seed: int = 1, tag_words: int = 4,
        dropout_s: float = 1.0, ground_skew_words: int = 0, skew_mode: str = "payload",
        dropout_start_frac: float = 0.5) -> dict:
    rnd = random.Random(seed)
    fmt = FrameFormat()
    prof = PROFILE_A if profile.upper() == "A" else PROFILE_B
    layout = SecurityLayout(tag_words=tag_words if prof == PROFILE_A else 0)
    n_frames = int(seconds * fmt.minor_rate_hz)
    n_frames -= n_frames % fmt.minors_per_major
    master = bytes(range(32))
    air_map = morgan_state_baseline(secure=True)
    cfg_hash = air_map.config_hash()
    ground_hash = skewed_map(air_map, ground_skew_words).config_hash() if ground_skew_words else cfg_hash

    # source + encryptor
    src = [build_minor_frame(fmt, i % 32, synth_payload(rnd, i, layout.payload_words(fmt)), layout) for i in range(n_frames)]
    enc = Encryptor(master, key_id=1, profile=prof, fmt=fmt, layout=layout, config_hash=cfg_hash)
    t0 = time.perf_counter()
    tx = [enc.process(f) for f in src]
    t_enc = time.perf_counter() - t0

    # channel: one dropout of dropout_s seconds in the middle, attacker injects 64 frames,
    # replays major frame 2 near the end
    mid = int(n_frames * dropout_start_frac)
    mid -= mid % fmt.minors_per_major
    drop_n = int(dropout_s * fmt.minor_rate_hz)
    if mid + drop_n >= int(n_frames * 0.8):
        raise ValueError("dropout must end before the injection point (80% of the stream)")
    ch = ChannelConfig(ber=ber, dropouts=[(mid, drop_n)],
                       inject_after=int(n_frames * 0.8), inject_count=64,
                       replay_major_frame=2, replay_at=int(n_frames * 0.9))
    rx, chstats = apply_channel(tx, ch, rnd, layout)

    # ground: decryptor (possibly with a skewed layout), counter check, config hash
    if not ground_skew_words:
        g_layout = layout
    elif skew_mode == "payload":
        # geometry-preserving relocation: security words found, payload boundary wrong
        g_layout = SecurityLayout(counter_word=layout.counter_word, sec_word=layout.sec_word,
                                  tag_words=layout.tag_words, payload_start=layout.payload_start + ground_skew_words)
    else:
        # whole-layout shift: the ground reads every security word from the wrong slot
        g_layout = SecurityLayout(counter_word=layout.counter_word + ground_skew_words,
                                  sec_word=layout.sec_word + ground_skew_words,
                                  tag_words=layout.tag_words, payload_start=layout.payload_start + ground_skew_words)
    dec = Decryptor({1: master}, fmt, g_layout, expected_config_hash=ground_hash)
    cc = CounterCheck()
    t0 = time.perf_counter()
    results = []
    for f in rx:
        cc.feed(f.words[g_layout.counter_word])
        results += dec.feed(f)
    dec.flush()
    results += dec.drain()
    t_dec = time.perf_counter() - t0

    # payload exactness against the source, by frame counter
    by_fc = {}
    for i, f in enumerate(src):
        by_fc[i] = f.words[layout.payload_slice(fmt)]
    exact = sum(1 for r in results if r.payload is not None and r.status in ("ok", "pending_auth")
                and by_fc.get(r.fc) == r.payload)
    delivered = sum(1 for r in results if r.status in ("ok", "pending_auth"))
    # first genuine (bit-exact) frame recovered after the outage, by source index
    first_after_dropout = None
    for r in results:
        if r.payload is not None and r.fc is not None and r.fc >= mid + drop_n and by_fc.get(r.fc) == r.payload:
            first_after_dropout = r.fc
            break

    out = {
        "profile": profile.upper(), "seconds": seconds, "frames_source": n_frames, "ber": ber,
        "layout": {"counter_word": layout.counter_word, "sec_word": layout.sec_word,
                   "payload_words": layout.payload_words(fmt), "tag_words": layout.tag_words,
                   "overhead_words": layout.overhead_words(), "overhead_fraction": layout.overhead_fraction(fmt)},
        "channel": chstats | {"dropout_frames": drop_n, "dropout_seconds": dropout_s},
        "ground_skew_words": ground_skew_words, "skew_mode": skew_mode if ground_skew_words else None,
        "dropout_start_frame": mid,
        "non_genuine_frames_released": None,
        "decryptor": dec.stats,
        "delivered": delivered, "payload_exact": exact,
        "first_frame_decrypted_after_dropout": first_after_dropout,
        "frames_lost_beyond_dropout": (None if first_after_dropout is None else first_after_dropout - (mid + drop_n)),
        "config_hash_match": dec.config_match,
        "major_frame_auth": {k: sum(1 for m in dec.major_results if m.status == k)
                             for k in ("authenticated", "auth_fail", "incomplete", "unverified")},
        "counter_check": cc.summary(),
        "transition_stats": {"plaintext": transition_stats(src), "ciphertext": transition_stats(tx)},
        "timing_ms_per_frame": {"encrypt": 1e3 * t_enc / n_frames, "decrypt": 1e3 * t_dec / max(1, len(rx))},
    }
    out["non_genuine_frames_released"] = delivered - exact
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--profile", choices=["A", "B"], default="A")
    ap.add_argument("--ber", type=float, default=0.0)
    ap.add_argument("--tag-words", type=int, default=4)
    ap.add_argument("--dropout-s", type=float, default=1.0)
    ap.add_argument("--ground-skew-words", type=int, default=0)
    ap.add_argument("--skew-mode", choices=["payload", "layout"], default="payload")
    ap.add_argument("--dropout-start-frac", type=float, default=0.5)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    r = run(a.seconds, a.profile, a.ber, a.seed, a.tag_words, a.dropout_s, a.ground_skew_words, a.skew_mode,
            a.dropout_start_frac)
    s = json.dumps(r, indent=2)
    if a.out:
        with open(a.out, "w") as fh:
            fh.write(s + "\n")
    print(s)


if __name__ == "__main__":
    main()

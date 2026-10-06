import random
import pytest
from pcmsec.frame import FrameFormat, SecurityLayout, build_minor_frame, PROFILE_A, PROFILE_B
from pcmsec.secure import Encryptor, Decryptor, make_nonce

MK = bytes(range(32))


def _stream(fmt, layout, n, seed=0):
    rnd = random.Random(seed)
    k = layout.payload_words(fmt)
    return [build_minor_frame(fmt, i % 32, [rnd.getrandbits(16) for _ in range(k)], layout) for i in range(n)]


@pytest.mark.parametrize("profile,tag_words", [(PROFILE_A, 4), (PROFILE_A, 2), (PROFILE_B, 0)])
def test_roundtrip_and_counter(profile, tag_words):
    fmt, lay = FrameFormat(), SecurityLayout(tag_words=tag_words)
    src = _stream(fmt, lay, 96)
    enc = Encryptor(MK, 2, profile, fmt, lay, config_hash=0xABCD0123)
    dec = Decryptor({2: MK}, fmt, lay, expected_config_hash=0xABCD0123)
    tx = [enc.process(f) for f in src]
    # clear header preserved, counter word is the staircase
    assert all(t.sync == fmt.sync_pattern and t.sfid == s.sfid for t, s in zip(tx, src))
    assert [t.words[lay.counter_word] for t in tx] == list(range(96))
    out = []
    for t in tx:
        out += dec.feed(t)
    assert len(out) == 96
    for r, s in zip(out, src):
        assert r.status in ("ok", "pending_auth")
        assert r.payload == s.words[lay.payload_slice(fmt)]
    assert dec.config_match is True
    if profile == PROFILE_B:
        assert [m.status for m in dec.major_results] == ["authenticated", "authenticated"]


def test_nonce_unique_and_tag_rejects_forgery():
    fmt, lay = FrameFormat(), SecurityLayout(tag_words=4)
    src = _stream(fmt, lay, 64)
    enc = Encryptor(MK, 0, PROFILE_A, fmt, lay)
    tx = [enc.process(f) for f in src]
    nonces = {make_nonce(enc.session_id, i, PROFILE_A) for i in range(64)}
    assert len(nonces) == 64
    dec = Decryptor({0: MK}, fmt, lay)
    res = []
    for t in tx[:40]:
        res += dec.feed(t)
    forged = tx[40].copy()
    forged.words[50] ^= 0x8000
    assert dec.feed(forged) == []                      # held pending the next header, never released
    # replay of an already-accepted frame
    assert dec.feed(tx[10])[0].status == "replay"
    # the genuine frame still decrypts afterwards
    assert dec.feed(tx[40])[0].status == "ok"
    for t in tx[41:64]:
        dec.feed(t)
    dec.flush()
    assert [r.status for r in dec.drain()] == ["auth_fail"]   # the forgery is condemned, not delivered


def test_dropout_across_counter_wrap_profile_a():
    """A 65536-frame (32 s) counter wrap inside an outage must not stall decryption."""
    fmt, lay = FrameFormat(), SecurityLayout(tag_words=4)
    enc = Encryptor(MK, 0, PROFILE_A, fmt, lay)
    dec = Decryptor({0: MK}, fmt, lay)
    first = _stream(fmt, lay, 64, seed=1)
    for f in first:
        for r in dec.feed(enc.process(f)):
            assert r.status == "ok"
    # skip ahead ~1.3 counter wraps without transmitting anything
    enc.fc = 65536 + 40000 - (65536 + 40000) % 32
    later = _stream(fmt, lay, 64, seed=2)
    statuses = []
    for f in later:
        statuses += [r.status for r in dec.feed(enc.process(f))]
    assert statuses == ["ok"] * 64


def test_profile_b_detects_injection_and_incomplete():
    fmt, lay = FrameFormat(), SecurityLayout(tag_words=0)
    src = _stream(fmt, lay, 32 * 4)
    enc = Encryptor(MK, 0, PROFILE_B, fmt, lay)
    tx = [enc.process(f) for f in src]
    tx[40].words[60] ^= 1          # one flipped bit in major frame 1
    rx = tx[:70] + tx[71:]         # one lost frame in major frame 2
    dec = Decryptor({0: MK}, fmt, lay)
    for t in rx:
        dec.feed(t)
    st = {m.mf: m.status for m in dec.major_results}
    assert st[0] == "authenticated"
    assert st[1] == "auth_fail"
    assert st[2] == "incomplete"


def test_wrong_key_never_authenticates():
    fmt, lay = FrameFormat(), SecurityLayout(tag_words=4)
    src = _stream(fmt, lay, 64)
    enc = Encryptor(MK, 0, PROFILE_A, fmt, lay)
    dec = Decryptor({0: bytes(32)}, fmt, lay)
    out = []
    for f in src:
        out += dec.feed(enc.process(f))
    assert out and all(r.status == "auth_fail" for r in out)


def test_corrupted_sfid_is_rejected_not_crashed():
    fmt, lay = FrameFormat(), SecurityLayout(tag_words=4)
    enc = Encryptor(MK, 0, PROFILE_A, fmt, lay)
    dec = Decryptor({0: MK}, fmt, lay)
    for f in _stream(fmt, lay, 40):
        dec.feed(enc.process(f))
    bad = enc.process(_stream(fmt, lay, 1)[0])
    bad.words[fmt.sfid_word] = 0x8000
    assert dec.feed(bad)[0].status == "sfid_fail"


def test_sync_bit_errors_are_tolerated_like_the_frame_synchroniser():
    fmt, lay = FrameFormat(), SecurityLayout(tag_words=4)
    enc = Encryptor(MK, 0, PROFILE_A, fmt, lay)
    dec = Decryptor({0: MK}, fmt, lay)
    for f in _stream(fmt, lay, 40):
        dec.feed(enc.process(f))
    t = enc.process(_stream(fmt, lay, 1)[0])
    t.words[0] ^= 0x0001; t.words[1] ^= 0x8000       # two sync bit errors: accepted and authenticated
    assert dec.feed(t)[0].status == "ok"
    t2 = enc.process(_stream(fmt, lay, 1)[0])
    t2.words[0] ^= 0x0007                             # three: rejected before decryption
    assert dec.feed(t2)[0].status == "sync_fail"


def test_replayed_header_cannot_regress_epoch():
    """A replayed major frame from an earlier epoch must not drag the ground's epoch backwards."""
    fmt, lay = FrameFormat(), SecurityLayout(tag_words=4)
    enc = Encryptor(MK, 0, PROFILE_A, fmt, lay)
    dec = Decryptor({0: MK}, fmt, lay)
    early = [enc.process(f) for f in _stream(fmt, lay, 64, seed=1)]      # epoch 0
    for t in early:
        dec.feed(t)
    enc.fc = 3 << 16                                                     # jump to epoch 3 (> epoch_search)
    out = []
    for f in _stream(fmt, lay, 64, seed=2):
        out += dec.feed(enc.process(f))
    assert [r.status for r in out] == ["ok"] * 64                        # held frames recovered after the header
    for t in early:                                                      # replay epoch-0 frames
        for r in dec.feed(t):
            assert r.status in ("replay", "auth_fail")
    dec.flush(); rej = dec.drain()
    assert all(r.status == "auth_fail" for r in rej)
    assert dec.counter_hi == 3
    for f in _stream(fmt, lay, 32, seed=3):                              # genuine traffic continues
        assert all(r.status == "ok" for r in dec.feed(enc.process(f)))

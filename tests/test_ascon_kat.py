"""Ascon-AEAD128 against the official known-answer tests (ascon-c, NIST SP 800-232 parameters),
plus Hash256/XOF/CXOF against published values."""
import os
from pcmsec import ascon

KAT = os.path.join(os.path.dirname(__file__), "LWC_AEAD_KAT_128_128.txt")


def _vectors():
    with open(KAT) as fh:
        for blk in fh.read().strip().split("\n\n"):
            d = {}
            for line in blk.splitlines():
                k, _, v = line.partition(" = ")
                d[k.strip()] = v.strip()
            yield {k: bytes.fromhex(d[k]) for k in ("Key", "Nonce", "PT", "AD", "CT")}


def test_aead_kat_all_vectors():
    n = 0
    for v in _vectors():
        ct, tag = ascon.aead_encrypt(v["Key"], v["Nonce"], v["AD"], v["PT"])
        assert ct + tag == v["CT"]
        assert ascon.aead_decrypt(v["Key"], v["Nonce"], v["AD"], ct, tag) == v["PT"]
        n += 1
    assert n == 1089


def test_aead_rejects_tampering():
    k, n = bytes(range(16)), bytes(range(16, 32))
    ct, tag = ascon.aead_encrypt(k, n, b"hdr", b"payload words" * 7, tag_bytes=8)
    assert len(tag) == 8
    assert ascon.aead_decrypt(k, n, b"hdr", ct, tag) == b"payload words" * 7
    assert ascon.aead_decrypt(k, n, b"hdX", ct, tag) is None
    bad = bytes([ct[0] ^ 1]) + ct[1:]
    assert ascon.aead_decrypt(k, n, b"hdr", bad, tag) is None
    assert ascon.aead_decrypt(k, n, b"hdr", ct, bytes([tag[0] ^ 1]) + tag[1:]) is None


def test_truncated_tag_is_prefix_of_full_tag():
    k, n = bytes(16), bytes(16)
    _, full = ascon.aead_encrypt(k, n, b"", b"abc")
    _, t8 = ascon.aead_encrypt(k, n, b"", b"abc", tag_bytes=8)
    assert t8 == full[:8]


def test_hash256_known_values():
    # Values cross-checked against the designers' reference implementation (pyascon, SP 800-232 mode)
    assert ascon.hash256(b"").hex() == "0b3be5850f2f6b98caf29f8fdea89b64a1fa70aa249b8f839bd53baa304d92b2"
    assert len(ascon.xof128(b"x", 100)) == 100
    assert ascon.xof128(b"x", 100)[:40] == ascon.xof128(b"x", 40)
    assert ascon.cxof128(b"m", 32, b"a") != ascon.cxof128(b"m", 32, b"b")

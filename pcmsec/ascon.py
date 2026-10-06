"""
Ascon-AEAD128, Ascon-Hash256, Ascon-XOF128 and Ascon-CXOF128 as specified in
NIST SP 800-232 (August 2025), "Ascon-Based Lightweight Cryptography Standards
for Constrained Devices".

Pure Python, dependency free.  The implementation is independent but follows
the structure of the designers' public-domain reference (pyascon, CC0) and is
verified in ``tests/test_ascon_kat.py`` against the official known-answer
tests shipped with the ascon-c reference code (LWC_AEAD_KAT_128_128.txt).

Byte order: SP 800-232 loads each 64-bit state word little-endian from the
byte string (this differs from the pre-NIST Ascon v1.2 specification).

Why Ascon here: the sponge keeps a 320-bit state and needs no key schedule,
no multiplier (unlike GCM's GHASH) and no large tables, so a per-minor-frame
AEAD fits comfortably in the small FPGA/MCU "bump-in-the-wire" encryptor that
sits between the PCM encoder and the transmitter (see docs/SECURITY_DESIGN.md).
"""
from __future__ import annotations

MASK64 = 0xFFFFFFFFFFFFFFFF

# --------------------------------------------------------------------------- #
# Permutation
# --------------------------------------------------------------------------- #

_ROUND_CONSTANTS = [0xF0, 0xE1, 0xD2, 0xC3, 0xB4, 0xA5, 0x96, 0x87, 0x78, 0x69, 0x5A, 0x4B]


def _rotr(x: int, r: int) -> int:
    return ((x >> r) | (x << (64 - r))) & MASK64


def permutation(S: list[int], rounds: int) -> None:
    """Ascon-p[rounds] applied in place to the five 64-bit state words."""
    for r in range(12 - rounds, 12):
        # constant addition
        S[2] ^= _ROUND_CONSTANTS[r]
        # substitution layer (5-bit S-box applied bit-sliced across the words)
        S[0] ^= S[4]
        S[4] ^= S[3]
        S[2] ^= S[1]
        t0 = (~S[0] & MASK64) & S[1]
        t1 = (~S[1] & MASK64) & S[2]
        t2 = (~S[2] & MASK64) & S[3]
        t3 = (~S[3] & MASK64) & S[4]
        t4 = (~S[4] & MASK64) & S[0]
        S[0] ^= t1
        S[1] ^= t2
        S[2] ^= t3
        S[3] ^= t4
        S[4] ^= t0
        S[1] ^= S[0]
        S[0] ^= S[4]
        S[3] ^= S[2]
        S[2] = ~S[2] & MASK64
        # linear diffusion layer
        S[0] ^= _rotr(S[0], 19) ^ _rotr(S[0], 28)
        S[1] ^= _rotr(S[1], 61) ^ _rotr(S[1], 39)
        S[2] ^= _rotr(S[2], 1) ^ _rotr(S[2], 6)
        S[3] ^= _rotr(S[3], 10) ^ _rotr(S[3], 17)
        S[4] ^= _rotr(S[4], 7) ^ _rotr(S[4], 41)


def _le(b: bytes) -> int:
    return int.from_bytes(b, "little")


def _le_bytes(x: int, n: int = 8) -> bytes:
    return (x & MASK64).to_bytes(n, "little")


def _pad(data: bytes, rate: int) -> bytes:
    """10* padding to a multiple of ``rate`` bytes (always appends at least 0x01)."""
    return data + b"\x01" + b"\x00" * (rate - (len(data) % rate) - 1)


# --------------------------------------------------------------------------- #
# AEAD
# --------------------------------------------------------------------------- #

KEY_BYTES = 16
NONCE_BYTES = 16
TAG_BYTES = 16
_AEAD_RATE = 16  # bytes
_AEAD_IV = bytes([0x01, 0x00, 0x80 | 0x0C, 0x80, 0x00, 0x10, 0x00, 0x00])
# ^ version=1, a=12,b=8 encoded as (b<<4)+a=0x8C, taglen=128 LE16, rate=16 bytes


def _aead_init(key: bytes, nonce: bytes) -> list[int]:
    S = [_le(_AEAD_IV), _le(key[:8]), _le(key[8:]), _le(nonce[:8]), _le(nonce[8:])]
    permutation(S, 12)
    S[3] ^= _le(key[:8])
    S[4] ^= _le(key[8:])
    return S


def _aead_absorb_ad(S: list[int], ad: bytes) -> None:
    if ad:
        p = _pad(ad, _AEAD_RATE)
        for i in range(0, len(p), _AEAD_RATE):
            S[0] ^= _le(p[i:i + 8])
            S[1] ^= _le(p[i + 8:i + 16])
            permutation(S, 8)
    S[4] ^= 1 << 63  # domain separation


def _aead_finalize(S: list[int], key: bytes) -> bytes:
    S[2] ^= _le(key[:8])
    S[3] ^= _le(key[8:])
    permutation(S, 12)
    return _le_bytes(S[3] ^ _le(key[:8])) + _le_bytes(S[4] ^ _le(key[8:]))


def aead_encrypt(key: bytes, nonce: bytes, ad: bytes, plaintext: bytes, tag_bytes: int = TAG_BYTES) -> tuple[bytes, bytes]:
    """Ascon-AEAD128 encryption.  Returns (ciphertext, tag).

    ``tag_bytes`` may be shortened (SP 800-232 permits truncated tags; tags
    below 64 bits require a risk analysis).  Truncation is applied to the
    128-bit tag, as the standard specifies.
    """
    if len(key) != KEY_BYTES or len(nonce) != NONCE_BYTES:
        raise ValueError("Ascon-AEAD128 needs a 16-byte key and a 16-byte nonce")
    if not 4 <= tag_bytes <= TAG_BYTES:
        raise ValueError("tag length must be between 4 and 16 bytes")
    S = _aead_init(key, nonce)
    _aead_absorb_ad(S, ad)
    p = _pad(plaintext, _AEAD_RATE)
    last = len(plaintext) % _AEAD_RATE
    out = bytearray()
    nblocks = len(p) // _AEAD_RATE
    for i in range(nblocks):
        S[0] ^= _le(p[16 * i:16 * i + 8])
        S[1] ^= _le(p[16 * i + 8:16 * i + 16])
        block = _le_bytes(S[0]) + _le_bytes(S[1])
        if i < nblocks - 1:
            out += block
            permutation(S, 8)
        else:
            out += block[:last]
    tag = _aead_finalize(S, key)
    return bytes(out), tag[:tag_bytes]


def aead_decrypt(key: bytes, nonce: bytes, ad: bytes, ciphertext: bytes, tag: bytes) -> bytes | None:
    """Ascon-AEAD128 decryption.  Returns plaintext, or None if the tag fails."""
    if len(key) != KEY_BYTES or len(nonce) != NONCE_BYTES:
        raise ValueError("Ascon-AEAD128 needs a 16-byte key and a 16-byte nonce")
    if not 4 <= len(tag) <= TAG_BYTES:
        raise ValueError("tag length must be between 4 and 16 bytes")
    S = _aead_init(key, nonce)
    _aead_absorb_ad(S, ad)
    last = len(ciphertext) % _AEAD_RATE
    nfull = len(ciphertext) // _AEAD_RATE
    out = bytearray()
    for i in range(nfull):
        c0 = _le(ciphertext[16 * i:16 * i + 8])
        c1 = _le(ciphertext[16 * i + 8:16 * i + 16])
        out += _le_bytes(S[0] ^ c0) + _le_bytes(S[1] ^ c1)
        S[0], S[1] = c0, c1
        permutation(S, 8)
    # final (partial, possibly empty) block
    tail = ciphertext[16 * nfull:] + b"\x00" * (_AEAD_RATE - last)
    c0, c1 = _le(tail[:8]), _le(tail[8:])
    out += (_le_bytes(S[0] ^ c0) + _le_bytes(S[1] ^ c1))[:last]
    keep = _le(b"\x00" * last + b"\xff" * (_AEAD_RATE - last))
    padbits = _le(b"\x00" * last + b"\x01" + b"\x00" * (_AEAD_RATE - last - 1))
    S[0] = (S[0] & (keep & MASK64)) ^ c0 ^ (padbits & MASK64)
    S[1] = (S[1] & (keep >> 64)) ^ c1 ^ (padbits >> 64)
    expected = _aead_finalize(S, key)[:len(tag)]
    # constant-time compare
    diff = 0
    for a, b in zip(expected, tag):
        diff |= a ^ b
    return bytes(out) if diff == 0 else None


# --------------------------------------------------------------------------- #
# Hash / XOF / CXOF
# --------------------------------------------------------------------------- #

_HASH_RATE = 8


def _hash_iv(version: int, taglen_bits: int) -> int:
    return _le(bytes([version, 0x00, 0xCC]) + taglen_bits.to_bytes(2, "little") + bytes([_HASH_RATE, 0, 0]))


def _sponge(version: int, taglen_bits: int, customization: bytes | None, message: bytes, out_len: int) -> bytes:
    S = [_hash_iv(version, taglen_bits), 0, 0, 0, 0]
    permutation(S, 12)
    if customization is not None:
        z = (len(customization) * 8).to_bytes(8, "little") + _pad(customization, _HASH_RATE)
        for i in range(0, len(z), _HASH_RATE):
            S[0] ^= _le(z[i:i + 8])
            permutation(S, 12)
    m = _pad(message, _HASH_RATE)
    for i in range(0, len(m), _HASH_RATE):
        S[0] ^= _le(m[i:i + 8])
        permutation(S, 12)
    out = bytearray()
    while len(out) < out_len:
        out += _le_bytes(S[0])
        permutation(S, 12)
    return bytes(out[:out_len])


def hash256(message: bytes) -> bytes:
    """Ascon-Hash256: 256-bit digest, 128-bit security."""
    return _sponge(2, 256, None, message, 32)


def xof128(message: bytes, out_len: int) -> bytes:
    """Ascon-XOF128: arbitrary-length output."""
    return _sponge(3, 0, None, message, out_len)


def cxof128(message: bytes, out_len: int, customization: bytes) -> bytes:
    """Ascon-CXOF128: XOF with a customization string (<= 256 bytes); used here as a KDF."""
    if len(customization) > 256:
        raise ValueError("customization string must be at most 256 bytes")
    return _sponge(4, 0, customization, message, out_len)

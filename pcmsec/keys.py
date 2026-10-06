"""Key material for the secure PCM stream.

Hierarchy
---------
master key (32 bytes, pre-shared, loaded into the encryptor and the ground PC
before the flight; identified by ``key_id``)
  -> per-flight keys, derived from the master key and the random 8-byte
     ``session_id`` the encryptor draws at power-up, with Ascon-CXOF128 as the
     KDF (customization string separates the two profiles and the two roles).

The derived keys are what the frame-level ciphers use, so a session id that
is broadcast in the clear reveals nothing, and nonce uniqueness only has to
hold *within* a session (session_id || 48-bit frame counter never repeats).
"""
from __future__ import annotations

import os

from . import ascon

MASTER_KEY_BYTES = 32


def new_session_id() -> bytes:
    return os.urandom(8)


def derive_key(master_key: bytes, session_id: bytes, role: str, length: int) -> bytes:
    if len(master_key) != MASTER_KEY_BYTES:
        raise ValueError("master key must be 32 bytes")
    if len(session_id) != 8:
        raise ValueError("session id must be 8 bytes")
    return ascon.cxof128(master_key + session_id, length, b"PCMSEC/v1/" + role.encode())


def profile_a_key(master_key: bytes, session_id: bytes) -> bytes:
    """128-bit Ascon-AEAD128 key."""
    return derive_key(master_key, session_id, "A/aead", 16)


def profile_b_keys(master_key: bytes, session_id: bytes) -> tuple[bytes, bytes]:
    """(256-bit AES-CTR key, 256-bit AES-CMAC key)."""
    return (derive_key(master_key, session_id, "B/ctr", 32),
            derive_key(master_key, session_id, "B/cmac", 32))

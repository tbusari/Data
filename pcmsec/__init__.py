"""pcmsec: securing an IRIG-106 Chapter 4 PCM stream inside the PCM/FM hardware envelope.

Modules
-------
ascon         NIST SP 800-232 Ascon-AEAD128 / Hash256 / XOF128 / CXOF128 (pure Python)
frame         Chapter-4 minor/major frame model and the security word layout
keys          Per-flight key derivation and session identifiers
secure        Bump-in-the-wire encryptor and ground decryptor (profiles A and B)
configid      Configuration hash binding the chassis frame map to the ground parameter database
counter_check Frame-counter staircase test (configuration-skew detection, dropped-frame odometer)
tmoip         Word extraction from LS-28 TMoIP payloads
linkbudget    Free-space / equivalent-path-loss / margin arithmetic used in the paper
simulate      End-to-end simulator: stream -> encryptor -> channel (BER, dropouts, attacker) -> decryptor
"""
__version__ = "0.1.0"

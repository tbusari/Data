# Securing the PCM Stream Inside the PCM/FM Hardware Envelope

Design note accompanying the revised ITC manuscript (`paper/revised/main.tex`) and the
reference implementation (`pcmsec/`). Everything here is implementable without changing
the modulation, the transmitter, the receiver, or the ground decommutator.

## 1. What is fixed and what is free

| Element | Status | Consequence for the design |
|---|---|---|
| KAM-500 BCU/101 Chapter 4 encoder | fixed; programmable word map (DAS Studio) | security words must be *reserved* in the frame as spare parameters that a downstream device overwrites |
| nanoTX PCM/FM at 3.2768 Mb/s | fixed waveform; accepts clock + NRZ-L data | the secured stream must remain an NRZ-L bit stream at the same rate (no expansion) |
| Haigh-Farr wraparound, SAS-512-7 log-periodics | fixed | no change |
| LS-28 DRSM bit sync, frame sync, decom, TMoIP out | fixed COTS firmware | sync pattern and SFID must stay in the clear and in place; the decom must still locate words by index |
| LDPS10x / IADS | fixed COTS software | decryption must happen *before* these see the data, i.e. on the TMoIP path, or they will display ciphertext |
| MEM/113 onboard record | records at the chassis, upstream of the encryptor | the onboard record is plaintext; protect at rest separately if required |
| What is free | | a small device between BCU/101 and nanoTX; software between the LS-28 TMoIP output and LDPS/IADS; the frame map |

The two insertion points are the only places in the chain where the data exists as a clean
digital bit stream with a known frame structure and no vendor firmware in the way.

```
 sensors -> KAM-500 (BCU/101) --clk/data NRZ-L--> [ENCRYPTOR] --clk/data--> nanoTX --PCM/FM--> antenna
                                                       |
                                                 MEM/113 record (plaintext, upstream)

 antenna -> LS-28 DRSM (bit sync, frame sync, decom) --TMoIP/UDP--> [DECRYPTOR, PC] --TMoIP--> LDPS10x / IADS
```

## 2. Threat model (sized for a student range campaign)

Assets: the vehicle state (GNSS position and velocity beyond civilian-receiver thresholds,
which is why the PwrPak7 was chosen), two video channels, pressure and temperature data,
and the integrity of the ground record used for post-flight analysis and for any live
operational decision.

Adversary: anyone within RF range with a software-defined radio. Two capabilities are
realistic and cheap:

1. **Passive capture.** A 4 MHz-wide SDR plus open-source PCM/FM demodulation recovers the
   full stream; the frame format is described in this paper.
2. **Injection.** A transmitter presenting the published sync pattern and SFID sequence at
   2250.5 MHz will be locked and decommutated by the LS-28. The paper's own fault-injection
   result shows the ground accepts "plausible but wrong" values silently. A stronger signal
   than the vehicle's (easy near the ground station, especially after apogee) captures the
   receiver.

Out of scope: jamming (no cryptographic defence), physical access to the recovered vehicle
and its CompactFlash record, compromise of the ground PC, and traffic analysis (frame
timing and lock status remain observable).

Goals: confidentiality of payload words; per-frame or per-major-frame authenticity;
replay rejection; and, as before, detection of air/ground configuration skew. Non-goals:
hiding the existence or timing of the transmission.

## 3. Frame layout (16-bit word indices, 100 words per minor frame)

```
 word  0-1   sync pattern 0xFE6B2840       clear, not authenticated (frame-sync tolerance)
 word  2     SFID 0..31                    clear, authenticated
 word  3     FCNT_LO  (frame counter, low 16 bits)      clear, authenticated   <- the paper's check word
 word  4     SEC      (security channel, subcommutated)  clear, authenticated
 word  5..k  payload                                    encrypted
 word  k+1..99  TAG (profile A only; 2 or 4 words)      clear
```

The security channel (word 4 across the 32 minor frames of a major frame) is a 64-byte
record:

| SFID slots | bytes | field |
|---|---|---|
| 0-3 | 8 | session identifier (random, drawn by the encryptor at power-up) |
| 4-5 | 4 | FCNT_HI: upper 32 bits of the 48-bit frame counter for this major frame |
| 6-7 | 4 | CFGH: configuration hash (truncated Ascon-Hash256 of the canonical frame map) |
| 8 | 2 | version/profile, tag length in words |
| 9 | 2 | key identifier |
| 10-13 | 8 | deferred tag of the *previous* major frame (profile B only) |
| 14-31 | 36 | reserved (zero) |

The ground parses fields as soon as their own slots have arrived (slots 0-9 for the
header, 10-13 for the tag), so a lost minor frame costs only the field it carried.

The frame counter is 48 bits, owned by the encryptor, aligned so that `FCNT & 31 == SFID`.
Its low 16 bits are the paper's staircase check word; its upper 32 bits ride in the
security channel and change only at a major-frame boundary (65536 is a multiple of 32).
It never wraps in practice (2^48 frames at 2048/s is 4,000 years) and the encryptor never
moves it backwards, so nonces are never reused within a session.

## 4. Profiles

### Profile A: per-minor-frame Ascon-AEAD128 (recommended)

- Algorithm: Ascon-AEAD128, NIST SP 800-232 (August 2025), 128-bit key, 128-bit nonce.
- Nonce: `session_id(8) || FCNT(6) || 0x0A || 0x00`.
- Associated data: words 2-4 (SFID, FCNT_LO, SEC). Tampering with the clear header fails
  authentication even though the header is not encrypted. The sync pattern is deliberately
  excluded: it is constant, and the frame synchroniser accepts it with a few bit errors,
  so authenticating it would reject frames the ground otherwise recovers.
- Plaintext: the payload words. Ciphertext replaces them in place (same length).
- Tag: 128-bit tag truncated to 64 bits (4 words) or 32 bits (2 words), in the tail of the
  minor frame. SP 800-232 permits truncated tags; tags shorter than 64 bits call for a
  risk analysis. For a 2048 frame/s link a 32-bit tag gives a random forgery about once
  per 24 days of continuous injection, which is acceptable for a telemetry display but
  not for a record of evidence; 64 bits is the default.
- Properties: every minor frame is independently decryptable and authenticated. An outage
  of any length costs exactly the frames lost. Replay is rejected by requiring a strictly
  increasing authenticated frame counter. A counter wrap inside an outage is handled by
  trying the next one or two values of FCNT_HI; the tag disambiguates. A frame that
  verifies under no candidate is held (up to 64 frames) and retried when the next
  security-channel header announces the epoch, so an outage of *any* length costs only the
  frames that were lost; held frames that never verify (forgeries) are condemned when the
  buffer turns over or the stream ends, and are never released.
- Overhead: 2 + tag words = 4 % or 6 % of the frame.
- Why Ascon: the sponge needs no key schedule, no finite-field multiplier and no tables;
  the permutation is 320 bits of state and 12 rounds of bit-sliced logic. An unrolled
  Ascon-p[8] fits in a small FPGA at well above the 305 ns bit period; the whole encryptor
  is a frame synchroniser, a counter, and the permutation.

### Profile B: AES-256-CTR with a deferred per-major-frame AES-CMAC tag (low overhead)

- Encryption: AES-256-CTR (SP 800-38A), initial counter block `session_id(8) || FCNT(6) || 0x0000`.
- Authentication: AES-CMAC (SP 800-38B) truncated to 64 bits over the major-frame number
  and the 32 transmitted minor frames (headers and ciphertext). The tag is finished after
  the last word of the major frame and carried in the *next* major frame's security
  channel, so the encryptor adds no latency.
- Overhead: 2 words (2 %).
- Properties and limits, measured in `pcmsec/simulate.py`: data is released before it is
  authenticated and condemned 15.6 ms later; a lost minor frame makes its major frame
  "incomplete" (decryptable but not verifiable; the onboard record can complete it later);
  the major frame before an outage is never verified because its tag was in the lost
  frame; two different frames claiming the same (major frame, SFID) poison that major
  frame. Replay is detected only when the counter moves backwards outside a small wrap
  window. Profile B is the right choice only when the 4-6 % of profile A cannot be spared.

### Both profiles

- Keys: a 32-byte master key per `key_id`, pre-shared between encryptor and ground PC.
  Per-flight keys are derived with Ascon-CXOF128 from the master key and the session id,
  so the broadcast session id reveals nothing and nonce uniqueness need only hold within a
  session.
- Configuration hash: both sides compute `Ascon-Hash256(canonical frame map)[:4]` from their
  own description of the frame (XidML on the air side, exported LDPS pair or TMATS on the
  ground side). The hash identifies content, not a version number against a registry.
  `pcmsec/configid.py` defines the canonical form; adapters for XidML and TMATS are the
  obvious next step.
- Transition density: encrypted payload words are uniformly random, so the stream carries
  about 0.49 transitions per bit with longest runs around 40 bits, against 0.38 and runs
  of 559 bits for the plaintext (status words full of zeros). The IRIG randomizer is no
  longer needed for bit-synchroniser health on the payload; the clear words are too few
  to matter.

## 5. Ground software path

```
LS-28 TMoIP (UDP) --> pcmsec decryptor --> re-emit TMoIP with payload words in the clear --> LDPS10x / IADS
                           |
                           +--> counter staircase, configuration-hash comparison, per-frame / per-major-frame
                                authentication log, replay log  (pre-flight go/no-go and in-flight health)
```

The LS-28 stays untouched: it frame-syncs on the clear pattern, tracks the SFID, and ships
the 100 words per minor frame it always shipped. LDPS/IADS stay untouched: they receive
the same packet format with plaintext in the payload words. The decryptor is ~400 lines of
Python today and would be a few microseconds per frame in C.

## 6. Interaction with the paper's existing checks

| Failure class (paper, Sec. 4.4) | Structural LDPS validation | Counter staircase | Configuration hash | AEAD tag |
|---|---|---|---|---|
| (i) stale ground pair after airborne recompile | passes | fails within frames | mismatch, identifies which | fails if layout moved |
| (ii) chassis reprogramming skipped | passes | fails | mismatch | fails if layout moved |
| (iii) replay against wrong configuration files | passes | fails | mismatch | n/a (offline) |
| (iv) mixed pair | rejected at load | - | - | - |
| (v) post-export hand edits | passes | passes if geometry kept | **mismatch** (content changed) | passes |
| injected stream | passes | passes (attacker copies counter) | passes (attacker copies SEC) | **fails** |
| replayed stream | passes | fails (counter backwards) | passes | **replay** (counter not increasing) |
| conversion / physical identity errors | passes | passes | passes | passes -> staggered-stimulus procedure |

## 7. Export-control and range notes

AES and Ascon are published, unclassified algorithms; an encryptor built from them for a
university programme is commercial-grade protection, not a Type 1 device, and should be
described as such. The hardware already in the chain (transmitter, GNSS receiver beyond
CoCom limits) carries its own export classification independent of this layer. Range
safety does not depend on the telemetry link (the Mx210 recovery link is independent), so
encryption introduces no safety-of-flight dependency on key management. Confirm with the
range whether an encrypted downlink requires notification.

## 8. What the software demonstrates and what it does not

Demonstrated (`tests/`, `results/`): algorithm correctness against the official NIST/ascon-c
known-answer tests; round-trip exactness of both profiles; rejection of injected, tampered
and replayed frames; decryption resuming on the first frame after outages of 2 s and 34 s
(across a 16-bit counter wrap); zero decryption under a one-word ground skew, with the
configuration hash flagging a payload-only relocation that the counter staircase alone
would miss, and all three witnesses failing when the security words are misread; measured
overheads and transition-density gain.

The bit-error comparison is the decisive result for choosing between profiles. At a BER of
1e-5 (PCM/FM a few tenths of a dB above its cliff), 258 flipped bits cost profile A the
252 frames that carried them (1.5 % of received frames) and nothing else. The same bits
cost profile B 202 of 514 major frames (39 %), because one error anywhere condemns the 32
frames of its major frame, and 249 corrupted frames were released before the deferred tag
condemned them. Per-frame authentication is both the stronger property and the cheaper one
in delivered data whenever the link is near threshold; profile B is defensible only on a
link with margin to spare, which is the one case where its 2 % saving matters least.

Not demonstrated: the FPGA/MCU encryptor itself, its timing closure at 3.2768 Mb/s, and the
LS-28 TMoIP re-emission path. These are the next build items and are labelled as such in
the manuscript.

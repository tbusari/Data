# Rewrite Plan

Section-by-section guidance for the revision, keyed to `review/REVIEW.md`. The proposed
text is in `paper/revised/main.tex`; this file records *why* each change is made so the
students can accept, adapt or reject each one deliberately. Items marked **[VERIFY]**
depend on facts only the team can check (installed vendor options, DAS Studio exports,
range paperwork) and are rendered in red in the LaTeX via `\needsverify{}`.

## Framing

The original title and thesis are good and are kept. The revised thesis sharpens it:
*configuration consistency is a property to be verified in the bitstream*, and the
bitstream can carry three mutually independent witnesses: a liveness/consistency witness
(the counter staircase, already demonstrated), an identity witness (a content hash of the
frame map, replacing the proposed configuration number), and an authenticity witness (an
authentication tag, which also gives confidentiality). The paper becomes a layered
argument rather than a single trick, which is what ITC reviewers reward.

## Abstract

- Keep the structure; quote receive-side temperature results (0.26 C, sigma 0.27-0.51 C)
  rather than the unequilibrated transmit-side 0.6 C.
- Add one sentence on the security layer: fits inside PCM/FM hardware, reuses the counter as
  nonce, overhead 2-6 %, software-demonstrated.

## 1. Introduction

- Rewrite the opening paragraph in the paper's own voice; give the mission (50,000 ft,
  RP-1/LOX) in one sentence.
- Keep the radiosonde / LoRa / PCM-over-S-band positioning.
- Add a short paragraph positioning against the standard's own mechanisms (TMATS Ch. 9,
  Chapter 7 packet telemetry, Chapter 10/11 recording) so that "no mechanism binds the
  chassis configuration to the ground pair" is stated precisely: *no mechanism in the
  deployed toolchain*, and TMATS does not address deployment skew in any case.
- Add two sentences on why security belongs in a paper about configuration consistency:
  an injected stream is the adversarial version of the same failure (plausible data,
  wrong source), and the same frame word that detects skew is the nonce the cipher needs.
- State contributions as a numbered list (reviewers look for it).

## 2. System Architecture

- 2.1: restore the third integration decision (Mx210 kept off the telemetry chain) or say
  "two". Keep the table.
- 2.2 RF link: fix the encoder/transmitter attribution. **[VERIFY]** whether the loaned
  nanoTX carries SOQPSK-TG and LDPC options. Add the computed occupied bandwidth and the
  frequency-authorisation path **[VERIFY]**.
- 2.3 Ground: keep; add why orthogonal-linear diversity was preferred over a circular
  aperture (retains spatial-diversity gain against measured multipath).
- Reconcile the -1 dBi budget figure with the measured 0 to +5 dBi (conservative choice).

## 3. Telemetry Frame Design

- Adopt 16-bit word indexing throughout: 100 transmitted words = 2 sync + 1 SFID + 97 data.
- Fix the sync pattern statement (**[VERIFY]** the actual DAS Studio value: 0xFE6B2840 is
  the Appendix C 32-bit recommendation; 0xEB90 is 16 bits).
- Resolve the pressure-word rate (**[VERIFY]**: subcommutated at 512 Hz per sensor, or one
  sensor at 2048 Hz in the test configurations). The revised text states both possibilities
  and asks the team to delete one.
- Fix GOP / keyframe interval (**[VERIFY]** the VID/106 setting).
- Introduce the reserved security words here (counter at word 3, security channel at word 4,
  tag in the tail) as *spare parameters* in the DAS Studio map that a downstream device
  overwrites, so that the frame section already shows the final layout.

## 4. Verification Methodology

- Keep the matrix; add two rows: configuration identity (hash) and stream authenticity
  (injection/replay), with software-demonstrated results.
- 4.1: unify the margin definition (received power minus derived threshold); keep EPL.
- 4.4: keep the excellent analysis of skew classes; change "configuration-number word" to
  "configuration-hash word pair" and explain content identity vs registry identity.
- Add 4.6 "Stream security" describing the two profiles, the nonce construction and the
  simulation protocol (dropout, injection, replay, skew, BER).

## 5. Results

- 5.1 link: soften "confirming" to "consistent with"; keep ripple and decorrelation.
- 5.2 channels: lead with receive-side numbers; move transmit-side to "indicative"; frame
  the 824.65 C excursion with two named hypotheses and the test that separates them.
- 5.3 skew: keep as is (it is the paper's best result).
- 5.4 reacquisition: keep; add the counter-wrap remark (16 bits wraps at 32 s; the
  security channel carries the upper bits).
- 5.5 new: security simulation results table (overhead, delivered/exact frames, injected
  frames rejected, replays rejected, frames lost beyond dropout, transition density).

## 6. Lessons Learned

Keep all seven; add:
- "Identify configurations by content, not by number."
- "The word that detects skew is the word the cipher needs: design the two together."
- "Encryption is also a randomizer: payload transition density rose from 0.38 to 0.49 and
  the longest run fell from 559 to about 40 bits."

## 7. Conclusion

Keep the structure; add one paragraph on the security layer and its status (software
demonstrated; FPGA/MCU encryptor and TMoIP re-emission are the next build items).

## Bibliography additions

TMATS handbook RCC 124-22; IRIG 106-24R1 (current edition; update the 2022 citation);
Hoffman 2019 (Chapter 7 guide); Temple 2021 (LDPC flight results); Cook 2021 (commercial
encryption for telemetry); NIST SP 800-232 (Ascon); Cummins, Mitchell and Perrins 2024
(rate-compatible LDPC for aeronautical telemetry); Savchenko 2025 (authenticated encryption
for space telemetry, IAC 2025 / arXiv 2601.21657); CCSDS 355.0-B (SDLS) as the space-link
precedent for frame-counter-based anti-replay; NIST SP 800-38A/38B for profile B.

## What not to change

The measured results, the figures, the lessons-learned voice, and the acknowledgments.
The rewrite is a re-description and an extension, not a re-analysis.

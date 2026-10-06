# ITC Paper Review Package: COTS IRIG-106 PCM Telemetry, Configuration Consistency and Stream Security

Review and proposed rewrite of the Morgan State University / RIT student paper
*"Closing the Configuration Consistency Gap in a COTS IRIG-106 PCM Telemetry System"*
for the International Telemetering Conference, plus a reference implementation of the
security layer the rewrite proposes.

## Contents

| Path | What it is |
|---|---|
| `review/REVIEW.md` | Reviewer report: technical findings ordered by severity, editorial findings, recommendation |
| `review/REWRITE_PLAN.md` | Section-by-section rationale for the rewrite, with `[VERIFY]` items for the team |
| `paper/original/` | The submitted manuscript, untouched |
| `paper/revised/` | Proposed rewrite (`main.tex`, `references.bib`, figures). Red `\needsverify{}` text marks facts the team must confirm |
| `docs/SECURITY_DESIGN.md` | Threat model, frame layout, profiles A and B, ground software path, interaction with the paper's checks |
| `pcmsec/` | Python reference implementation (Ascon-AEAD128 per NIST SP 800-232, frame model, encryptor/decryptor, configuration hash, counter check, link budget, simulator) |
| `tests/` | pytest suite, including the 1089 official Ascon known-answer vectors |
| `results/` | Simulation outputs quoted in the revised manuscript (`tools/run_simulations.sh` regenerates them) |

## Quick start

```bash
pip install cryptography pytest
python -m pytest -q tests
python -m pcmsec.simulate --seconds 2 --profile A --ber 1e-6
python -c "from pcmsec.linkbudget import paper_numbers; print(paper_numbers())"
```

## Building the revised paper

```bash
cd paper/revised && pdflatex main && bibtex main && pdflatex main && pdflatex main
```

The revised source uses the same packages as the original plus `tikz` for the frame-layout
figure. No TeX distribution was available in the review environment, so the source was
checked for brace and environment balance (`tools/check_tex.py`) but not compiled; expect
to resolve minor spacing issues on first build.

## Status of the security layer

Software-verified: algorithm correctness against official test vectors, round-trip
exactness, rejection of forged/tampered/replayed frames, continuity across dropouts
including a 16-bit counter wrap, detection of ground-side layout skew, overhead and
transition-density figures. Not yet built: the FPGA/MCU encryptor between the BCU/101 and
the nanoTX, and the TMoIP re-emission path on the ground PC.

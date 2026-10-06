# Review: "Closing the Configuration Consistency Gap in a COTS IRIG-106 PCM Telemetry System"

Submission: ITC student paper, Morgan State University / RIT (Udenta, Joyner, Stewart; advisor Busari).
Reviewer role: technical and editorial pre-submission review, with a rewrite recommendation.
Companion material: `review/REWRITE_PLAN.md` (section-by-section plan), `paper/revised/` (proposed
rewrite), `pcmsec/` and `docs/SECURITY_DESIGN.md` (security layer the rewrite introduces).

---

## 1. Summary assessment

**Recommendation: accept with major revision.** The paper has a genuinely good central idea
and a real experimental demonstration of it: a frame-embedded counter exposes air/ground
configuration skew that receiver lock, SFID cycling and the toolchain's structural validation
all miss. The staged verification campaign is unusually disciplined for a student programme,
and the measured results (two-ray ripple, channel decorrelation, relock inside one log
interval, the 854-frame recorder fill) are concrete and reproducible.

The paper is held back by three things:

1. **Internal inconsistencies in the frame description** (98 vs 100 words, a 16-bit sync
   value labelled 32 bits, a pressure "subcommutated" word that is measured at the full
   minor-frame rate, a keyframe interval that does not match the stated GOP). An ITC
   reviewer who works with Chapter 4 will catch every one of these on a first read.
2. **Missing context that the ITC audience will expect**: TMATS (IRIG 106 Chapter 9) is the
   standard's own answer to the "ground must know what the air is sending" problem and is not
   mentioned; Chapter 7 packet telemetry, Chapter 10/11 recording semantics, LDPC
   (Appendix 2-D) and spectrum authorisation are likewise absent. The paper's argument is
   stronger, not weaker, once these are acknowledged, because the counter check guards the
   gap *between* those mechanisms.
3. **No security consideration at all** for a link that carries GNSS data explicitly chosen
   because it exceeds civilian-receiver export thresholds, plus two video channels, in the
   clear on a published frequency. The rewrite adds a security layer that fits inside the
   existing PCM/FM hardware and, importantly, reuses the paper's own counter as the
   cryptographic nonce, so the two ideas reinforce each other.

The core results do not need re-measurement. The paper needs to be re-described, re-framed
and extended.

---

## 2. Technical findings (ordered by severity)

### 2.1 Frame arithmetic does not close (must fix)

| Statement in paper | Problem |
|---|---|
| "98-word minor frames ... the 32-bit sync pattern and the 16-bit SFID bringing the 98-word frame to its 100-word transmitted total" (Sec. 3) | 98 + 2 (sync) + 1 (SFID) = 101, not 100. If the 98 includes the SFID, the sum is 100 only if the sync is counted as 2 words and SFID as 1: 97 data + 1 SFID + 2 sync. State one consistent accounting. |
| Figure 1 / frame map: "Minor frame (98 words)", word 0 = sync (32 bits), word 1 = SFID, words 2-97 | 96 data + 1 SFID + one 32-bit sync = 1584 bits, which at 2048 frames/s gives 3.244 Mb/s, not 3.2768 Mb/s. The figure and the text disagree with each other and with the measured bit rate (3.2766-3.2782 x 10^6 counts/s, Sec. 6.4, which supports 1600 bits/frame). |
| Frame map: "Sync word value 0xEB90, sync word length 32 bits" | 0xEB90 is the classic 16-bit pattern. The IRIG 106 Appendix C recommended 32-bit pattern is 0xFE6B2840. Either the length or the value is wrong. |
| TMoIP payload "8 + 24 + 200 bytes, exactly the 100 sixteen-bit transmitted words" | This is the correct, measured fact. Make it the anchor: 100 transmitted 16-bit words = 2 sync + 1 SFID + 97 data. |

**Fix:** adopt 16-bit word indexing throughout (sync = words 0-1, SFID = word 2, data = words
3-99), redraw the frame-map panel, and check the sync pattern against the DAS Studio export.

### 2.2 Pressure word rate (must fix or re-explain)

Section 3 says one word per minor frame (word 62) "is subcommutated among the pressure
sensors", which gives 512 Hz per transducer. Section 6.2 reports 2048.00 Hz per pressure
channel with "the verification captures ... exercising one sensor per run, accordingly
observed the full word rate on each channel". A subcommutated slot does not deliver the full
word rate to one sensor just because the others are idle; it delivers 512 Hz with three
idle slots. Either the test configurations differed from the flight configuration (then
the results do not verify the flight frame, and this must be said), or the word is not
subcommutated. The frame-map figure also says instrumentation "is not transmitted in minor
frame 0", which makes the pressure rate 1984 Hz, not 2048 Hz.

### 2.3 Link margin numbers are stated three ways (should fix)

- Sec. 2.3 and 4.1: threshold about -95 dBm, flight received power -83.2 dBm, margin about 12 dB.
- Sec. 6.1: "at least 7 dB over a conservative 13 dB single-symbol PCM/FM requirement" at EPL 120.6 dB.

At EPL 120.6 dB the received power is -80.6 dBm; with the paper's own noise figure and
bandwidth, a 13 dB Eb/N0 threshold is about -92 dBm, so the margin at that point is about
11-12 dB, not 7. The 7 dB appears to be 20 dB (measured Eb/N0) minus 13 dB, which is a
different quantity (measured Eb/N0 is saturated near the estimator ceiling, as the paper
notes). Pick one definition of margin and use it everywhere. `pcmsec/linkbudget.py`
reproduces every figure in Sec. 4.1 so the final numbers can be regenerated.

### 2.4 GOP and keyframe interval (minor)

"GOP ratio 1:15, 30 frames/s" gives a 0.500 s keyframe interval; the pass criterion says
0.533 s, which is 16 frames. State the GOP length the VID/106 actually uses.

### 2.5 "Three integration decisions merit discussion" lists two (minor, but visible)

Section 2.1 announces three and gives "First" and "Second". Either restore the third (the
Mx210 recovery altimeter kept off the telemetry chain is the obvious candidate, and it is
already in Lessons Learned) or say two.

### 2.6 Modulation statement is misattributed (should fix)

"the chassis outputs only PCM/FM without additional modulation hardware" conflates the
encoder with the transmitter. The BCU/101 outputs a baseband PCM clock/data stream; the
nanoTX performs the modulation, and the nanoTX product family is multi-waveform
(PCM/FM, SOQPSK-TG, and others, with an LDPC option, per Quasonix's public datasheets;
verify against the installed option set of the loaned unit). If the unit is PCM/FM-only,
say so as a procurement fact. If it is not, the choice of PCM/FM over SOQPSK-TG (about
half the occupied bandwidth at the same bit rate) and the choice not to enable LDPC
(8-9 dB of coding gain in Quasonix's published figures) are design decisions that need one
sentence each. Combined with the 12 dB vs 30 dB margin shortfall, LDPC is the single
largest lever available without touching the antenna and should at least be discussed.

### 2.7 Occupied bandwidth and spectrum authorisation (should add)

A 3.2768 Mb/s PCM/FM carrier at 2250.5 MHz occupies roughly 3.8 MHz (99% bandwidth about
1.16 x bit rate for PCM/FM with premodulation filtering). "Occupied RF bandwidth is not
reported here" will draw a question, because 2200-2290 MHz operation requires frequency
authorisation and the usual ITC reader will ask who coordinated it. One sentence on the
authorisation path and the measured or computed occupied bandwidth closes this.

### 2.8 TMATS, Chapter 7, Chapter 10/11 are the standard's answers to the stated problem (must add)

The paper argues that the toolchain offers "no mechanism binding the configuration running
in the chassis to the pair loaded in LDPS". The standard does offer mechanisms, and the
paper should position itself relative to them:

- **TMATS (Chapter 9, RCC 124-22 handbook):** a vendor-neutral description of the PCM format
  intended precisely for transfer from the instrumentation side to the ground side. If
  DAS Studio or LDPS can import/export TMATS, the file-pair problem shrinks to a single
  file; if they cannot, that is a finding worth stating. Either way the counter check still
  guards *deployment* skew, which TMATS does not.
- **Chapter 10/11 recording with embedded setup record:** a Chapter 10 recording carries its
  TMATS in the setup record, which addresses scenario (iii), replay against the wrong files.
  Whether the MEM/113 record is Chapter 10 should be stated (the paper mentions packet
  sequence numbers, which suggests it is).
- **Chapter 7 packet telemetry:** downlinking Chapter 11 packets inside the Chapter 4 frame
  would make the downlink and the onboard record the *same* data format, eliminating the
  content-aligned merge problem of Sec. 6.4. Hoffman's "Engineer's Guide to Chapter 7"
  (ITC 2019) is the reference.

### 2.9 Configuration identification by number vs by content (suggestion adopted in rewrite)

The paper's second refinement, "a configuration-number word per major frame", identifies a
version only against an external registry and reintroduces the file-discipline problem one
level up. Transmitting a truncated hash of the canonical frame map (computed independently
from the XidML on the air side and from the exported LDPS pair on the ground side) identifies
*content*. The rewrite proposes this and `pcmsec/configid.py` implements it.

### 2.10 Counter wrap (minor)

A 16-bit counter wraps every 32 s, which is shorter than the flight. For the skew check it
does not matter; for any use as a timestamp, odometer across long outages, or (as the
rewrite proposes) a cryptographic nonce, it does. The rewrite carries the upper 32 bits once
per major frame.

### 2.11 Unresolved anomalies should be framed, not left hanging

- The 83-sample, three-channel, 824.65 C excursion is explained as "electrical or
  configuration artifact" without a hypothesis. Common-mode on all three TDC/102 channels
  with two pinned at an identical value points at the cold-junction/reference path or an
  open-thermocouple detection pull-up; name the candidates and the test that would separate
  them.
- Transmit-side plateaus of 0.8-1.8 s are too short to equilibrate; the abstract's
  "better than 0.6 C" is driven by that unequilibrated transmit-side number. Quote the
  receive-side result (mean error 0.26 C or better, sigma 0.27-0.51 C) and label the
  transmit side as indicative.
- The ice point verifies offset and cold-junction compensation at one temperature only.
  A second point (boiling point or a dry-block) would verify slope; say this is planned.

### 2.12 Polarisation diversity (minor)

The cos^2 + sin^2 = 1 argument is correct for an ideal pre-detection combiner, but a
circularly polarised ground antenna would also remove roll fades at a fixed 3 dB cost and
with one receive chain. Say why the orthogonal-linear pair was preferred (it preserves the
diversity gain against the measured multipath, which the circular antenna would not). Also
reconcile the -1 dBi used in the link budget with the measured 0 to +5 dBi over broad
sectors; using the conservative figure is fine, but say so.

### 2.13 Slope fits (minor)

Fitting -21.4 and -18.3 dB/decade over 20-114 m (0.75 decade) with 11-12 dB of two-ray
ripple does not "confirm" the free-space exponent; it is consistent with it. Soften.

### 2.14 Security (addressed by the rewrite)

The link carries GNSS position and velocity beyond civilian-receiver thresholds, two video
channels and the full vehicle state, in the clear, on a published frequency, with a
receiver that will lock to any PCM/FM carrier presenting the sync pattern. Two threats are
realistic for a student range campaign: passive capture of the stream (any SDR with a 4 MHz
front end), and injection of a well-formed stream into the ground station, which the paper's
own fault-injection results show would decommutate "plausibly". Neither requires a
sophisticated adversary. Cook (ITC 2021) describes a commercial AES approach for ARTM
telemetry; the rewrite proposes a lighter scheme that fits inside the PCM/FM envelope and
reuses the paper's counter as the nonce. See `docs/SECURITY_DESIGN.md`.

---

## 3. Editorial findings

- **Voice.** The introduction opens in a different register from the rest of the paper
  ("tackling the complex and intricate task ... was imperative for live data
  visualization"). Rewrite in the voice of the rest of the paper.
- **Units.** "50,000ft" should be "50,000 ft (15.2 km)"; use `\si{}` consistently.
- **Hard-coded section references** ("\S2.2", "\S2.3") should be `\ref`.
- **Figure 1 carries two labels** (`fig:architecture`, `fig:frame`); split the figure or use
  one label and refer to panels.
- **Abstract numbers.** "better than 0.6 C" and "zero bit errors to 120.6 dB" are both
  weaker statements than the data support (see 2.11) or need the EPL qualifier.
- **The bibliography has a TODO comment** (vendor documentation entries). Resolve it;
  the paper leans on vendor datasheet figures for the threshold estimate.
- **AI disclosure** is present (good). Check the current ITC author kit for the required
  wording and placement; the kit on telemetry.org governs.
- **Length.** The archive is labelled "15pp". Check the ITC paper submission guide for
  the current page limit before adding the proposed security section; the rewrite
  compensates by tightening Sections 1-3.
- **Key words** should include "link security" or "authenticated encryption" if the
  security section is adopted.

---

## 4. What the rewrite does (see `review/REWRITE_PLAN.md`)

1. Fixes every item in Section 2 above with the data already in hand.
2. Re-frames the contribution as *verification in the bitstream* with three layers:
   structural (LDPS validation), identity (configuration hash), and liveness/consistency
   (counter staircase), positioned relative to TMATS, Chapter 7 and Chapter 10/11.
3. Adds a section on securing the stream within the PCM/FM hardware envelope, with a
   software demonstration, measured overheads, and simulated dropout/injection/replay
   behaviour from `pcmsec/simulate.py`. All claims that depend on vendor option sets the
   students must verify are marked `\needsverify{}` in the LaTeX and render in red.
4. Extends the bibliography with the references the ITC audience will expect (TMATS
   handbook, Chapter 7 guide, LDPC flight results, NIST SP 800-232, recent authenticated
   telemetry work).

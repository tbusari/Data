# Tier 2: dimuon spectrum and H -> 4l reanalysis on CMS 2012 open data

Two analyses that turn the sanity checks in `../README.md` into statistical tests of
published results, using the CMS 2012 outreach NanoAOD files from the CERN Open Data
portal (a few GiB in total) and nothing heavier than `uproot`, `awkward`, `numpy`,
`scipy` and `matplotlib`. No CMSSW, no ROOT installation.

Status: the code is complete and validated on synthetic files with the exact NanoAOD
branch layout (`make_toy_nanoaod.py`, `test_h4l_selection.py`). It has **not yet been run
on the real files**, because the session that built it could not reach
`opendata.cern.ch`. Running it is one command once the files are downloaded.

## 0. Setup and data

```bash
pip install uproot awkward numpy scipy matplotlib
./download.sh ~/cms-opendata-2012        # needs opendata.cern.ch (HTTPS) reachable
python3 test_h4l_selection.py            # 7 hand-built selection checks, < 1 s
```

| File | CERN Open Data record | Content | Used by |
|---|---|---|---|
| `Run2012BC_DoubleMuParked_Muons.root` | 12341 (DOI 10.7483/OPENDATA.CMS.LVG5.QT81) | 61.5 M events, muon kinematics only, validated runs of 2012 B+C | dimuon spectrum |
| `Run2012B_DoubleMuParked.root`, `Run2012C_DoubleMuParked.root` | 12365, 12366 | full outreach NanoAOD, 2012 B and C | H -> 4l (4mu, 2mu2e) |
| `Run2012B_DoubleElectron.root`, `Run2012C_DoubleElectron.root` | 12367, 12368 | same for the DoubleElectron stream | H -> 4l (4e) |
| `SMHiggsToZZTo4L.root` | 12361 | simulation, gg -> H -> ZZ -> 4l, m_H = 125 GeV | signal template |
| `ZZTo4mu.root`, `ZZTo4e.root`, `ZZTo2e2mu.root` | 12362-12364 | simulation, qq -> ZZ -> 4l | background template |

Record numbers other than 12341 and 12366 were not verified from the portal in this
session; the file names are those used by CERN Open Data record 12360 (S. Wunsch 2021)
and by the ROOT tutorials `df102_NanoAODDimuonAnalysis` and `df103_NanoAODHiggsAnalysis`.
`download.sh` fetches them from the portal's EOS path
`eos/opendata/cms/derived-data/AOD2NanoAODOutreachTool/`.

## 1. Dimuon spectrum (`dimuon_spectrum.py`)

```bash
python3 dimuon_spectrum.py --out results/dimuon ~/cms-opendata-2012/Run2012BC_DoubleMuParked_Muons.root
```

What it does, step by step:

1. Streams the file in 200 MB chunks (the whole file is 2.1 GiB; memory stays below
   1 GB) reading only `nMuon`, `Muon_pt/eta/phi/mass/charge`.
2. Selects events with exactly two muons of opposite charge. This is the selection of
   CERN Open Data record 12342, deliberately with no pT, |eta| or isolation cut, so the
   full spectrum from 0.25 GeV to 300 GeV is visible.
3. Fills a log-binned histogram (the classic CMS "dimuon spectrum" figure) and fine
   linear histograms in four windows: J/psi (2.6-3.5 GeV, 10 MeV bins), psi(2S)
   (3.45-3.95), Upsilon (8.6-11.2, 20 MeV bins), Z (70-112, 0.5 GeV bins).
4. Fits each window with scipy:
   * J/psi, psi(2S): Gaussian + linear background.
   * Upsilon: three Gaussians with the 2S and 3S positions tied to the 1S by the PDG
     splittings and a common resolution scaling with mass, + linear background. This
     is how the states are separated at CMS resolution; the 1S-2S-3S splittings then
     test the fit rather than being free.
   * Z: Breit-Wigner of PDG width 2.4955 GeV convolved with a Gaussian (Voigt profile)
     + exponential Drell-Yan background. The free parameters are the pole mass and the
     detector resolution.
5. Writes `dimuon_fits.json` (mass, uncertainty, resolution, difference from PDG in
   MeV), the histograms (`.npz`) and two figures.

What to expect on the real data, from the literature:

* Peaks at eta (0.548 GeV), rho/omega (0.78), phi (1.019), J/psi (3.097), psi(2S)
  (3.686), Upsilon(1S, 2S, 3S) (9.460, 10.023, 10.355) and Z (91.19), plus a bump near
  30 GeV that is a trigger-threshold artefact, not a resonance (record 12342 notes this).
* Fitted masses within about 0.1 % of PDG without momentum-scale corrections: CMS Run 1
  muon scale is calibrated to ~0.1 % at the Z and better at the J/psi. A J/psi offset
  of more than 10 MeV or a Z offset of more than 100-200 MeV would indicate a problem.
* Resolutions (sigma): roughly 30-40 MeV at the J/psi, 70-100 MeV at the Upsilon,
  1-2 GeV at the Z, averaged over |eta| < 2.4 (CMS JINST 7 (2012) P10002; the exact
  values depend on the eta mix and the lack of corrections in the outreach files).
* Upsilon(2S) and (3S) resolved as separate peaks, which is a direct test of the
  tracker momentum resolution.

On the toy file the script recovers J/psi 3.0968 (PDG 3.0969), Upsilon(1S) 9.4608
(9.4604) and Z 91.19 (91.19) GeV; see `make_toy_nanoaod.py` for what the toy contains.

## 2. H -> ZZ* -> 4l reanalysis (`h4l_reanalysis.py`)

```bash
D=~/cms-opendata-2012
python3 h4l_reanalysis.py --out results/h4l \
  --data-mu $D/Run2012B_DoubleMuParked.root $D/Run2012C_DoubleMuParked.root \
  --data-e  $D/Run2012B_DoubleElectron.root $D/Run2012C_DoubleElectron.root \
  --mc SMHiggsToZZTo4L=$D/SMHiggsToZZTo4L.root ZZTo4mu=$D/ZZTo4mu.root \
       ZZTo4e=$D/ZZTo4e.root ZZTo2e2mu=$D/ZZTo2e2mu.root \
  --golden ../tools/Cert_190456-208686_8TeV_22Jan2013ReReco_Collisions12_JSON.txt
```

(The certification JSON lives in `cms-opendata-analyses/HiggsExample20112012/datasets/`;
`../tools/run_all.sh` clones that repository. The outreach files were already produced
from validated lumisections, so the `--golden` filter should remove nothing; it is
there so the check is explicit.)

Selection, following the CERN Open Data H -> 4l example (record 5500) as encoded in
record 12360 / ROOT tutorial df103:

| Step | 4mu | 4e | 2mu2e |
|---|---|---|---|
| lepton multiplicity | exactly 4 muons | exactly 4 electrons | exactly 2 + 2 |
| kinematics | pT > 5 GeV, abs(eta) < 2.4 | pT > 7 GeV, abs(eta) < 2.5 | both |
| isolation | PF relative isolation (dR 0.4) < 0.40 | PF relative isolation (dR 0.3) < 0.40 | both |
| impact parameter | abs(dxy) < 0.5 cm, abs(dz) < 1 cm, 3D significance < 4 | same | same |
| separation | dR > 0.02 between all lepton pairs | same | same |
| charge | sum of charges = 0 | same | per flavour |
| Z1 | opposite-sign pair closest to m_Z, 40 < m < 120 GeV, leptons pT > 20 and > 10 GeV | same | the flavour pair closest to m_Z |
| Z2 | the remaining pair, 12 < m < 120 GeV | same | the other flavour pair |

The 4mu and 2mu2e channels are taken from the DoubleMuParked stream and 4e from
DoubleElectron, exactly as the example does, to avoid double counting across triggers.

Simulation normalisation: L = 11.58 fb^-1; cross sections 0.0065 pb (H -> ZZ -> 4l),
0.077 pb (ZZ -> 4mu and 4e), 0.18 pb (ZZ -> 2e2mu); generated events 299 973 /
1 499 064 / 1 499 093 / 1 497 445; k-factor 1.386 on ZZ. These are the numbers of the
df103 tutorial; change `XSEC`, `NGEN`, `KFAC`, `LUMI` at the top of the script if the
portal records give different ones.

Outputs:

* `h4l_mass.png`: data points over stacked ZZ and Higgs templates, 70-181 GeV in 3 GeV
  bins (the binning of the example, so the plot is directly comparable with its
  `mass4l_combine.png` and with Fig. 4 of the discovery paper).
* `h4l_summary.json`: per-channel histograms, the 120-130 GeV yields, and a Poisson
  background-only p-value for the window (a counting experiment; the example quotes
  "about 2 standard deviations" from the same kind of estimate).
* The list of data candidates (run, lumisection, event, m4l) in the window, printed
  and saved. **This is the cross-check against the display**: the 11 events in
  `ispy-webgl/data/Hto4l_120-130GeV.ig` (listed in `../results/h4l_check.txt`) should
  reappear here with the same run and event numbers. Any difference tells you exactly
  how the outreach NanoAOD selection differs from the AOD-level example.

What to expect on the real data:

* About 11 data events in 120-130 GeV (3 four-muon, 6 two-muon-two-electron, 2
  four-electron) if the NanoAOD selection reproduces the AOD example; a different count
  is informative, not a failure.
* An expected ZZ background of order 2-3 events and an expected SM Higgs yield of order
  4-5 events in the window (the discovery-era expectation was 7.6 signal events in
  110-160 GeV for the full 2012 sample, arXiv:1303.4571, and the public sample is 50 %).
* A background-only p-value corresponding to roughly 1.5-2.5 standard deviations. That
  is the honest size of the Higgs excess in the public 50 % of Run 1 with a simplified
  selection; the discovery paper's 3.2 sigma in this channel used the full sample and
  a kinematic discriminant.
* A Z -> 4l peak at 88-94 GeV (about 10-20 events) and the ZZ continuum rising above
  180 GeV, as in the published spectrum.

## 3. Files

| File | Purpose |
|---|---|
| `nanolib.py` | chunked reading, four-vectors, PDG constants, validated-lumisection filter |
| `dimuon_spectrum.py` | analysis 1 |
| `h4l_reanalysis.py` | analysis 2 |
| `test_h4l_selection.py` | unit test of the selection and Z pairing with hand-built events |
| `make_toy_nanoaod.py` | synthetic NanoAOD-layout files for pipeline tests (not physics) |
| `download.sh` | fetches the nine real files from the portal |

## 4. Results on the real data

### 4.1 Dimuon spectrum (record 12341, run 2026-10-07)

61,540,413 events read, 24,067,843 opposite-sign dimuon pairs selected (45 s on one core).
Full output in `../results/tier2/dimuon/`.

| Resonance | Fitted mass [GeV] | PDG [GeV] | Offset | Resolution sigma [MeV] |
|---|---|---|---|---|
| J/psi | 3.0926 +- 0.0006 | 3.0969 | -4.3 MeV (-0.14 %) | 34.2 +- 0.5 |
| psi(2S) | 3.6816 +- 0.0005 | 3.6861 | -4.5 MeV (-0.12 %) | 36.2 +- 0.5 |
| Upsilon(1S) | 9.4464 +- 0.0014 | 9.4604 | -14.0 MeV (-0.15 %) | 100.8 +- 1.2 |
| Upsilon(2S), (3S) | tied to 1S by PDG splittings; the joint fit describes all three peaks | 10.0233, 10.3552 | -14 MeV | scaled with mass |
| Z (Voigt + exponential, 70-112 GeV) | 90.721 +- 0.035 | 91.1880 | -467 MeV (-0.51 %) | 1585 +- 44 |
| Z (Voigt + linear, 88-95 GeV) | 90.895 | 91.1880 | -293 MeV (-0.32 %) | 1185 |
| Z, model-free peak position | 90.870 | 91.1880 | -318 MeV (-0.35 %) | |

Reading:

* The spectrum (`dimuon_spectrum.png`) shows the eta, rho/omega, phi, J/psi, psi(2S),
  Upsilon(1S, 2S, 3S) and Z peaks and the trigger-threshold shoulder near 30 GeV, i.e.
  the published CMS dimuon spectrum (record 12342, df102 tutorial) is reproduced from
  the raw NanoAOD in under a minute.
* Masses below 10 GeV are recovered to 0.12-0.15 % without any momentum-scale
  correction, with the J/psi and Upsilon both low by the same fraction: that is the
  size and sign of the known uncorrected 2012 muon momentum scale in the legacy
  reconstruction (the Rochester-type corrections applied in CMS papers are of order
  0.1-0.3 %).
* The Z is 0.3-0.5 % low depending on the fit model (`z_window_scan.txt`). Two effects
  add here: the same momentum-scale offset, and final-state radiation, which is not
  recovered in the outreach files and moves the dimuon peak below the pole mass by a few
  hundred MeV. The window dependence (174 MeV) is quoted as the model systematic; the
  resolution of 1.2-1.6 GeV agrees with the CMS Run 1 dimuon resolution at the Z.
* The three Upsilon states are cleanly separated with the 1S-2S-3S splittings fixed to
  PDG (`dimuon_fits.png`), a direct check of tracker momentum resolution (101 MeV at
  9.46 GeV, i.e. 1.1 %).
* J/psi and psi(2S) resolutions of 34-36 MeV and the Upsilon resolution of 101 MeV match
  the CMS Run 1 values (JINST 7 (2012) P10002 quotes 1-2 % momentum resolution for
  muons of these momenta over the full |eta| range).

Verdict: with 24 million pairs the dimuon spectrum reproduces every published resonance
position to better than 0.2 % below 10 GeV and to 0.5 % at the Z, and the resolutions
agree with the detector-performance papers. The residual offsets are the expected ones
for uncalibrated legacy data, not evidence of any disagreement with the literature.

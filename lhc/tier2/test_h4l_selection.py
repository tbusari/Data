#!/usr/bin/env python3
"""Hand-built events to check the H->4l selection and Z1/Z2 pairing (run: python3 test_h4l_selection.py)."""
import math
import awkward as ak
import numpy as np
from h4l_reanalysis import select
from nanolib import PDG, p4, mass_of


def lep(pt, eta, phi, q):
    return dict(pt=pt, eta=eta, phi=phi, charge=q)


def two_body_pts(m, phi0=0.0):
    """Resonance of mass m at rest -> two leptons back to back in the transverse plane."""
    p = m / 2
    return [(p, 0.0, phi0, +1), (p, 0.0, phi0 + math.pi, -1)]


def build(muons, electrons, run=1, lumi=1, event=1):
    """Build a one-event chunk with NanoAOD-style branches from lists of (pt, eta, phi, q)."""
    d = {'run': [run], 'luminosityBlock': [lumi], 'event': [event]}
    for pre, ls, iso in (('Muon', muons, 'pfRelIso04_all'), ('Electron', electrons, 'pfRelIso03_all')):
        d[f'n{pre}'] = [len(ls)]
        d[f'{pre}_pt'] = [[l[0] for l in ls]]; d[f'{pre}_eta'] = [[l[1] for l in ls]]
        d[f'{pre}_phi'] = [[l[2] for l in ls]]; d[f'{pre}_charge'] = [[l[3] for l in ls]]
        d[f'{pre}_mass'] = [[PDG['mu' if pre == 'Muon' else 'e']] * len(ls)]
        d[f'{pre}_{iso}'] = [[0.05] * len(ls)]
        d[f'{pre}_dxy'] = [[0.01] * len(ls)]; d[f'{pre}_dxyErr'] = [[0.01] * len(ls)]
        d[f'{pre}_dz'] = [[0.02] * len(ls)]; d[f'{pre}_dzErr'] = [[0.02] * len(ls)]
    return ak.Array(d)


# 1. clean 4mu event: Z1 (91 GeV, leptons 45.6 GeV) + Z2 (30 GeV, leptons 15 GeV), separated in phi
mu = two_body_pts(PDG['Z'], 0.0) + two_body_pts(30.0, 1.0)
m, ev = select(build(mu, []), '4mu')
assert len(m) == 1, 'clean 4mu event should pass'
# 2. same leptons split 2mu + 2e must pass the 2mu2e channel and fail 4mu
m2, _ = select(build(mu[:2], mu[2:]), '2mu2e'); assert len(m2) == 1
m3, _ = select(build(mu[:2], mu[2:]), '4mu'); assert len(m3) == 0
# 3. Z2 below 12 GeV must fail
m4, _ = select(build(two_body_pts(PDG['Z']) + two_body_pts(8.0, 1.0), []), '4mu'); assert len(m4) == 0
# 4. net charge != 0 must fail
bad = [lep(45, 0, 0, +1), lep(45, 0, 3.1, +1), lep(15, 0, 1, +1), lep(15, 0, 4.1, -1)]
bad = [(l['pt'], l['eta'], l['phi'], l['charge']) for l in bad]
m5, _ = select(build(bad, []), '4mu'); assert len(m5) == 0
# 5. pT 20/10 rule exists only in 2mu2e (skim.cxx). Four 15 GeV leptons: Z1 = 45 GeV pair made with a
#    rapidity gap (m^2 = 2 pt1 pt2 (cosh(deta) - cos(dphi))), Z2 = 30 GeV pair at rest.
soft = [(15.0, 0.0, 0.0, +1), (15.0, 1.92, math.pi, -1)] + two_body_pts(30.0, 1.0)
m6, _ = select(build(soft[:2], soft[2:]), '2mu2e'); assert len(m6) == 0, 'no pair has 20/10 GeV -> 2mu2e fails'
m6b, _ = select(build(soft, []), '4mu'); assert len(m6b) == 1, '4mu has no 20/10 cut -> passes'
# 6. isolation cut: iso 0.6 fails
ev = build(mu, []); ev['Muon_pfRelIso04_all'] = ak.Array([[0.6, 0.05, 0.05, 0.05]])
m7, _ = select(ev, '4mu'); assert len(m7) == 0
# 6b. an isolation value of -999 (missing in NanoAOD) must fail, as abs(iso) < 0.4 in skim.cxx
ev = build(mu, []); ev['Muon_pfRelIso04_all'] = ak.Array([[-999.0, 0.05, 0.05, 0.05]])
m7b, _ = select(ev, '4mu'); assert len(m7b) == 0
# 7. mass value sanity: with all leptons massless-ish and Z's at rest, m4l should be sqrt((91.19+30)^2 - |p|^2) with p=0 -> 121.19
assert abs(m[0] - (PDG['Z'] + 30.0)) < 0.2, m[0]
print('all 9 selection checks passed; m4l of the clean event = %.2f GeV' % m[0])

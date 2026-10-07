#!/usr/bin/env python3
"""H -> ZZ* -> 4l reanalysis on CMS 2012 open data (outreach NanoAOD).

Re-implements the selection of the CERN Open Data H->4l example (record 5500,
Jomhari, Geiser, Bin Anuar 2017) in the form used by record 12360 / ROOT tutorial df103:

(selection transcribed from that record's skim.cxx; z_mass = 91.2 GeV there)

  4mu   : exactly 4 muons (2 positive, 2 negative), pT>5,  |eta|<2.4, pfRelIso04<0.40
  4e    : exactly 4 electrons (2+, 2-),              pT>7,  |eta|<2.5, pfRelIso03<0.40
  2mu2e : exactly 2 muons + 2 electrons, net charge 0 per flavour, same per-lepton cuts,
          and either the muon pair or the electron pair has pT > 20 and > 10 GeV
  all leptons: |dxy|<0.5 cm, |dz|<1 cm, 3D impact-parameter significance < 4
  Z pairing: same flavour -> OS pair closest to 91.2 GeV is Z1, the other two are Z2;
             2mu2e -> the flavour pair closer to 91.2 GeV is Z1
  dR > 0.02 between the two leptons of each Z candidate
  40 < m(Z1) < 120, 12 < m(Z2) < 120 GeV

Simulation is normalised to L = 11.58 fb^-1 with the cross sections used by the example.
Outputs: histograms (npz), figure, JSON summary with yields in 120-130 GeV, Poisson
significance, and the (run, lumi, event) list of data candidates for cross-checking
against the 11 events in ispy-webgl's Hto4l_120-130GeV.ig.

usage: h4l_reanalysis.py --out DIR --data-mu F.root [...] --data-e F.root [...]
                         --mc NAME=F.root [...] [--golden Cert.json]
"""
import argparse
import json
import os

import awkward as ak
import numpy as np
from scipy.stats import poisson, norm

from nanolib import PDG, iterate, p4, mass_of, load_golden, golden_mask

ZMASS = 91.2   # value used by skim.cxx (record 12360)

LUMI = 11580.0                                  # pb^-1, 2012 open data (DoubleMuParked + DoubleElectron)
XSEC = {'SMHiggsToZZTo4L': 0.0065, 'ZZTo4mu': 0.077, 'ZZTo4e': 0.077, 'ZZTo2e2mu': 0.18}   # pb
NGEN = {'SMHiggsToZZTo4L': 299973, 'ZZTo4mu': 1499064, 'ZZTo4e': 1499093, 'ZZTo2e2mu': 1497445}
KFAC = {'SMHiggsToZZTo4L': 1.0, 'ZZTo4mu': 1.386, 'ZZTo4e': 1.386, 'ZZTo2e2mu': 1.386}
BINS = np.linspace(70, 181, 38)                 # 3 GeV bins as in the example
SIGNAL = (120.0, 130.0)

MU_BR = ['nMuon', 'Muon_pt', 'Muon_eta', 'Muon_phi', 'Muon_mass', 'Muon_charge',
         'Muon_pfRelIso04_all', 'Muon_dxy', 'Muon_dxyErr', 'Muon_dz', 'Muon_dzErr']
EL_BR = ['nElectron', 'Electron_pt', 'Electron_eta', 'Electron_phi', 'Electron_mass',
         'Electron_charge', 'Electron_pfRelIso03_all', 'Electron_dxy', 'Electron_dxyErr',
         'Electron_dz', 'Electron_dzErr']
EV_BR = ['run', 'luminosityBlock', 'event']


def good(ev, pre, pt_min, eta_max, iso):
    pt, eta = ev[f'{pre}_pt'], ev[f'{pre}_eta']
    dxy, dz = ev[f'{pre}_dxy'], ev[f'{pre}_dz']
    sip = np.sqrt(dxy ** 2 + dz ** 2) / np.sqrt(ev[f'{pre}_dxyErr'] ** 2 + ev[f'{pre}_dzErr'] ** 2)
    # abs() on the isolation as in skim.cxx: the files store -999 where no value exists
    return ((pt > pt_min) & (abs(eta) < eta_max) & (abs(ev[f'{pre}_{iso}']) < 0.40)
            & (abs(dxy) < 0.5) & (abs(dz) < 1.0) & (sip < 4))


def dr_ok(a, b):
    dphi = abs(a.phi - b.phi)
    dphi = ak.where(dphi > np.pi, 2 * np.pi - dphi, dphi)
    return np.sqrt((a.eta - b.eta) ** 2 + dphi ** 2) > 0.02


def z_pairs_same_flavour(l):
    """For 4 same-flavour leptons: Z1 = OS pair closest to ZMASS, Z2 = the other two.
    Returns (mZ1, mZ2, dR-ok flag for both pairs)."""
    idx = ak.local_index(l.pt)
    pairs = ak.combinations(ak.zip({'i': idx, 'q': l.charge, 'v': l.v4, 'eta': l.eta, 'phi': l.phi}), 2)
    os_ = pairs[pairs['0'].q != pairs['1'].q]
    m = mass_of(os_['0'].v, os_['1'].v)
    best = ak.argmin(abs(m - ZMASS), axis=1, keepdims=True)
    z1 = os_[best]
    mz1 = ak.firsts(m[best])
    i0, i1 = ak.firsts(z1['0'].i), ak.firsts(z1['1'].i)
    r = l[(idx != i0) & (idx != i1)]                      # the two leptons not in Z1
    mz2 = mass_of(r.v4[:, 0], r.v4[:, 1])
    ok = ak.firsts(dr_ok(z1['0'], z1['1'])) & dr_ok(r[:, 0], r[:, 1])
    return mz1, mz2, ok


def leptons(ev, pre, mass):
    return ak.zip({'pt': ev[f'{pre}_pt'], 'eta': ev[f'{pre}_eta'], 'phi': ev[f'{pre}_phi'],
                   'charge': ev[f'{pre}_charge'],
                   'v4': p4(ev[f'{pre}_pt'], ev[f'{pre}_eta'], ev[f'{pre}_phi'], mass)})


def select(chunk, channel):
    """Return (m4l array, selected events) for one chunk and channel in {'4mu','4e','2mu2e'}."""
    ev = chunk
    if channel in ('4mu', '4e'):
        pre, mass, ptmin, etamax, iso = (('Muon', PDG['mu'], 5, 2.4, 'pfRelIso04_all') if channel == '4mu'
                                         else ('Electron', PDG['e'], 7, 2.5, 'pfRelIso03_all'))
        q = ev[f'{pre}_charge']
        ev = ev[(ev[f'n{pre}'] == 4) & (ak.sum(q == 1, axis=1) == 2) & (ak.sum(q == -1, axis=1) == 2)]
        ev = ev[ak.all(good(ev, pre, ptmin, etamax, iso), axis=1)]
        if len(ev) == 0:
            return np.array([]), ev
        l = leptons(ev, pre, mass)
        mz1, mz2, ok = z_pairs_same_flavour(l)
        m4l = mass_of(l.v4[:, 0], l.v4[:, 1], l.v4[:, 2], l.v4[:, 3])
    else:
        ev = ev[(ev.nMuon == 2) & (ev.nElectron == 2)]
        ev = ev[ak.all(good(ev, 'Muon', 5, 2.4, 'pfRelIso04_all'), axis=1)
                & ak.all(good(ev, 'Electron', 7, 2.5, 'pfRelIso03_all'), axis=1)]
        ev = ev[(ak.sum(ev.Muon_charge, axis=1) == 0) & (ak.sum(ev.Electron_charge, axis=1) == 0)]
        if len(ev) == 0:
            return np.array([]), ev
        mu = leptons(ev, 'Muon', PDG['mu'])
        el = leptons(ev, 'Electron', PDG['e'])
        mu_pt = ak.sort(mu.pt, axis=1, ascending=False)
        el_pt = ak.sort(el.pt, axis=1, ascending=False)
        ptok = ((mu_pt[:, 0] > 20) & (mu_pt[:, 1] > 10)) | ((el_pt[:, 0] > 20) & (el_pt[:, 1] > 10))
        ok = ptok & dr_ok(mu[:, 0], mu[:, 1]) & dr_ok(el[:, 0], el[:, 1])
        mmm = mass_of(mu.v4[:, 0], mu.v4[:, 1])
        mee = mass_of(el.v4[:, 0], el.v4[:, 1])
        mu_is_z1 = abs(mmm - ZMASS) < abs(mee - ZMASS)
        mz1 = ak.where(mu_is_z1, mmm, mee)
        mz2 = ak.where(mu_is_z1, mee, mmm)
        m4l = mass_of(mu.v4[:, 0], mu.v4[:, 1], el.v4[:, 0], el.v4[:, 1])
    ok = ok & (mz1 > 40) & (mz1 < 120) & (mz2 > 12) & (mz2 < 120)
    return ak.to_numpy(m4l[ok]), ev[ok]


def run_sample(files, channels, golden=None, need=('mu', 'e')):
    br = list(EV_BR)
    if 'mu' in need:
        br += MU_BR
    if 'e' in need:
        br += EL_BR
    hist = {c: np.zeros(len(BINS) - 1) for c in channels}
    cands = {c: [] for c in channels}
    n_read = 0
    for chunk in iterate(files, br):
        n_read += len(chunk)
        if golden is not None:
            chunk = chunk[golden_mask(chunk.run, chunk.luminosityBlock, golden)]
        for c in channels:
            m, ev = select(chunk, c)
            hist[c] += np.histogram(m, BINS)[0]
            for mm, r, l, e in zip(m, ak.to_numpy(ev.run), ak.to_numpy(ev.luminosityBlock), ak.to_numpy(ev.event)):
                cands[c].append((int(r), int(l), int(e), float(mm)))
    return hist, cands, n_read


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--data-mu', nargs='*', default=[], help='DoubleMuParked NanoAOD (4mu and 2mu2e)')
    ap.add_argument('--data-e', nargs='*', default=[], help='DoubleElectron NanoAOD (4e)')
    ap.add_argument('--mc', nargs='*', default=[], help='NAME=file.root, NAME in ' + ', '.join(XSEC))
    ap.add_argument('--golden', help='validated-lumisection JSON (optional)')
    ap.add_argument('--lumi', type=float, default=LUMI)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    golden = load_golden(a.golden) if a.golden else None

    out = {'bins': BINS.tolist(), 'data': {}, 'mc': {}, 'candidates': {}}
    data_hist = {c: np.zeros(len(BINS) - 1) for c in ['4mu', '2mu2e', '4e']}
    if a.data_mu:
        h, c, n = run_sample(a.data_mu, ['4mu', '2mu2e'], golden)
        data_hist.update(h); out['candidates'].update(c); print(f'DoubleMuParked: {n:,} events read')
    if a.data_e:
        h, c, n = run_sample(a.data_e, ['4e'], golden)
        data_hist.update(h); out['candidates'].update(c); print(f'DoubleElectron: {n:,} events read')
    mc_hist = {}
    for spec in a.mc:
        name, path = spec.split('=', 1)
        h, _, n = run_sample([path], ['4mu', '2mu2e', '4e'])
        w = a.lumi * XSEC[name] / NGEN[name] * KFAC[name]
        mc_hist[name] = {c: v * w for c, v in h.items()}
        print(f'{name}: {n:,} events read, weight {w:.3e}')

    sig_bins = (BINS[:-1] >= SIGNAL[0]) & (BINS[:-1] < SIGNAL[1])
    tot_data = sum(data_hist.values())
    zero = np.zeros(len(BINS) - 1)
    bkg = sum((sum(h.values(), zero) for n, h in mc_hist.items() if n != 'SMHiggsToZZTo4L'), zero)
    higgs = sum(mc_hist['SMHiggsToZZTo4L'].values(), zero) if 'SMHiggsToZZTo4L' in mc_hist else zero
    n_obs = int(tot_data[sig_bins].sum()); b = float(bkg[sig_bins].sum()); s = float(higgs[sig_bins].sum())
    print(f'\nsignal window {SIGNAL[0]:.0f}-{SIGNAL[1]:.0f} GeV: observed {n_obs}, expected ZZ background {b:.2f}, expected SM Higgs {s:.2f}')
    for c in data_hist:
        print(f'  {c:6s} observed {int(data_hist[c][sig_bins].sum())}')
    if b > 0:
        p = poisson.sf(n_obs - 1, b)
        print(f'  Poisson p-value for background-only: {p:.3g}  ({norm.isf(p):.2f} sigma); '
              f'expected with S+B: {s + b:.2f}')
        out['significance'] = {'n_obs': n_obs, 'b': b, 's': s, 'p_value': p, 'z': norm.isf(p)}
    out['data'] = {c: v.tolist() for c, v in data_hist.items()}
    out['mc'] = {n: {c: v.tolist() for c, v in h.items()} for n, h in mc_hist.items()}
    out['candidates'] = {c: sorted(v) for c, v in out['candidates'].items()}
    print('\ndata candidates in signal window (run, lumi, event, m4l):')
    for c, v in out['candidates'].items():
        for r, l, e, m in v:
            if SIGNAL[0] <= m < SIGNAL[1]:
                print(f'  {c:6s} {r:6d} {l:5d} {e:11d} {m:8.2f}')
    json.dump(out, open(os.path.join(a.out, 'h4l_summary.json'), 'w'), indent=1)

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 5))
    x = 0.5 * (BINS[:-1] + BINS[1:])
    if mc_hist:
        ax.bar(x, bkg, width=3, color='#3b6ea8', label='ZZ (simulation)')
        ax.bar(x, higgs, width=3, bottom=bkg, color='#c0392b', label='SM Higgs m=125 GeV (simulation)')
    nz = tot_data > 0
    ax.errorbar(x[nz], tot_data[nz], np.sqrt(tot_data[nz]), fmt='o', color='k', ms=4, label='data 2012 (open data, 11.6 fb$^{-1}$)')
    ax.axvspan(*SIGNAL, color='grey', alpha=0.15)
    ax.set_xlabel('four-lepton invariant mass [GeV]'); ax.set_ylabel('events / 3 GeV')
    ax.set_xlim(70, 181); ax.legend(); ax.set_title('H -> ZZ* -> 4l, CMS 2012 open data reanalysis')
    fig.tight_layout(); fig.savefig(os.path.join(a.out, 'h4l_mass.png'), dpi=150)


if __name__ == '__main__':
    main()

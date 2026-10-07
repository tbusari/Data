#!/usr/bin/env python3
"""Dimuon invariant-mass spectrum from CMS 2012 open data and resonance fits.

Input: outreach NanoAOD with branches nMuon, Muon_pt/eta/phi/mass/charge
(e.g. Run2012BC_DoubleMuParked_Muons.root, CERN Open Data record 12341).

Selection (as in CERN Open Data record 12342 / ROOT tutorial df102):
  exactly two muons, opposite charge.  No pT, eta or isolation cut.

Outputs (in --out):
  dimuon_spectrum.npz     log-binned full spectrum + fine linear histograms per resonance
  dimuon_fits.json        fitted mass, resolution and PDG comparison per resonance
  dimuon_spectrum.png     full spectrum
  dimuon_fits.png         fitted windows

usage: dimuon_spectrum.py --out DIR FILE.root [FILE.root ...]
"""
import argparse
import json
import os

import awkward as ak
import numpy as np
from scipy.optimize import curve_fit
from scipy.special import voigt_profile

from nanolib import PDG, iterate, p4, mass_of

# resonance: (window lo, hi, nbins, background model, initial sigma)
WINDOWS = {
    'J/psi':  (2.6, 3.5, 90, 'lin', 0.035),
    'psi(2S)': (3.45, 3.95, 50, 'lin', 0.040),
    'Upsilon': (8.6, 11.2, 130, 'lin', 0.10),
    'Z':      (70.0, 112.0, 84, 'exp', 1.5),
}


def gauss(x, n, mu, sig):
    return n * np.exp(-0.5 * ((x - mu) / sig) ** 2) / (sig * np.sqrt(2 * np.pi))


def model_single(x, n, mu, sig, b0, b1):
    return gauss(x, n, mu, sig) + b0 + b1 * (x - x.mean())


def model_upsilon(x, n1, n2, n3, mu1, sig, b0, b1):
    # 2S and 3S positions tied to 1S by PDG splittings, common resolution scaled by mass
    d2 = PDG['Upsilon(2S)'] - PDG['Upsilon(1S)']
    d3 = PDG['Upsilon(3S)'] - PDG['Upsilon(1S)']
    return (gauss(x, n1, mu1, sig) + gauss(x, n2, mu1 + d2, sig * (mu1 + d2) / mu1)
            + gauss(x, n3, mu1 + d3, sig * (mu1 + d3) / mu1) + b0 + b1 * (x - x.mean()))


def model_z(x, n, mu, sig, b0, slope):
    # Breit-Wigner (PDG width) convolved with Gaussian resolution, plus exponential background
    return n * voigt_profile(x - mu, sig, PDG['Z_width'] / 2) + b0 * np.exp(-slope * (x - 70))


def fit_window(name, edges, counts):
    x = 0.5 * (edges[:-1] + edges[1:])
    w = edges[1] - edges[0]
    y = counts / w                                   # density per GeV
    err = np.sqrt(np.maximum(counts, 1)) / w
    lo, hi, _, bkg, sig0 = WINDOWS[name]
    if name == 'Upsilon':
        p0 = [y.max() * sig0 * 2, y.max() * sig0, y.max() * sig0 * 0.6, PDG['Upsilon(1S)'], sig0, y.min(), 0]
        popt, pcov = curve_fit(model_upsilon, x, y, p0=p0, sigma=err, maxfev=20000)
        perr = np.sqrt(np.diag(pcov))
        return {'Upsilon(1S)': (popt[3], perr[3], popt[4], perr[4]),
                'Upsilon(2S)': (popt[3] + PDG['Upsilon(2S)'] - PDG['Upsilon(1S)'], perr[3], None, None),
                'Upsilon(3S)': (popt[3] + PDG['Upsilon(3S)'] - PDG['Upsilon(1S)'], perr[3], None, None)}, model_upsilon(x, *popt)
    if name == 'Z':
        p0 = [counts.sum() * 0.9, PDG['Z'], sig0, max(y[0], 1e-3), 0.05]
        bounds = ([0, 85, 0.3, 0, -1], [np.inf, 97, 6, np.inf, 1])
        popt, pcov = curve_fit(model_z, x, y, p0=p0, sigma=err, bounds=bounds, maxfev=20000)
        perr = np.sqrt(np.diag(pcov))
        return {'Z': (popt[1], perr[1], abs(popt[2]), perr[2])}, model_z(x, *popt)
    mu0 = PDG[name]
    p0 = [y.max() * sig0 * 2.5, mu0, sig0, y.min(), 0]
    popt, pcov = curve_fit(model_single, x, y, p0=p0, sigma=err, maxfev=20000)
    perr = np.sqrt(np.diag(pcov))
    return {name: (popt[1], perr[1], abs(popt[2]), perr[2])}, model_single(x, *popt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--step', default='200 MB')
    ap.add_argument('files', nargs='+')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    log_edges = np.logspace(np.log10(0.25), np.log10(300), 30000 // 100 * 10 + 1)   # 3001 edges
    log_hist = np.zeros(len(log_edges) - 1)
    fine = {k: (np.linspace(v[0], v[1], v[2] + 1), np.zeros(v[2])) for k, v in WINDOWS.items()}
    n_tot = n_sel = 0
    branches = ['nMuon', 'Muon_pt', 'Muon_eta', 'Muon_phi', 'Muon_mass', 'Muon_charge']
    for chunk in iterate(a.files, branches, a.step):
        n_tot += len(chunk)
        ev = chunk[chunk.nMuon == 2]
        ev = ev[ev.Muon_charge[:, 0] != ev.Muon_charge[:, 1]]
        n_sel += len(ev)
        mu = p4(ev.Muon_pt, ev.Muon_eta, ev.Muon_phi, ev.Muon_mass)
        m = ak.to_numpy(mass_of(mu[:, 0], mu[:, 1]))
        log_hist += np.histogram(m, log_edges)[0]
        for k, (e, h) in fine.items():
            h += np.histogram(m, e)[0]
    print(f'events read: {n_tot:,}  selected opposite-sign dimuons: {n_sel:,}')

    results = {}
    curves = {}
    for name in WINDOWS:
        e, h = fine[name]
        try:
            r, curve = fit_window(name, e, h)
            curves[name] = curve
            results.update(r)
        except Exception as ex:  # fit failure is reported, not fatal
            print(f'fit failed for {name}: {ex}')
    print(f"\n{'resonance':12} {'fitted mass [GeV]':>22} {'PDG [GeV]':>10} {'diff [MeV]':>11} {'resolution [GeV]':>17}")
    table = {}
    for name, (mu, dmu, sig, dsig) in results.items():
        pdg = PDG[name]
        res = f'{sig:.4f} +- {dsig:.4f}' if sig is not None else 'tied to 1S'
        print(f'{name:12} {mu:12.4f} +- {dmu:.4f} {pdg:10.4f} {1000 * (mu - pdg):+11.1f} {res:>17}')
        table[name] = {'mass': mu, 'mass_err': dmu, 'pdg': pdg, 'diff_MeV': 1000 * (mu - pdg),
                       'resolution': sig, 'resolution_err': dsig}
    json.dump({'events_read': n_tot, 'dimuons_selected': n_sel, 'fits': table},
              open(os.path.join(a.out, 'dimuon_fits.json'), 'w'), indent=1)
    np.savez(os.path.join(a.out, 'dimuon_spectrum.npz'), log_edges=log_edges, log_hist=log_hist,
             **{f'{k}_edges': v[0] for k, v in fine.items()}, **{f'{k}_hist': v[1] for k, v in fine.items()})

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.step(log_edges[:-1], log_hist, where='post', lw=0.8, color='#1f4e79')
    ax.set_xscale('log'); ax.set_yscale('log')
    ax.set_xlabel('dimuon invariant mass [GeV]'); ax.set_ylabel('events / bin')
    for k in ['eta', 'rho/omega', 'phi', 'J/psi', 'psi(2S)', 'Upsilon(1S)', 'Z']:
        ax.axvline(PDG[k], color='grey', lw=0.5, ls=':')
        ax.text(PDG[k], log_hist.max() * 1.3, k, rotation=90, fontsize=7, ha='center', va='bottom')
    ax.set_title(f'CMS open data 2012, opposite-sign dimuons ({n_sel:,} pairs)')
    fig.tight_layout(); fig.savefig(os.path.join(a.out, 'dimuon_spectrum.png'), dpi=150)
    fig, axes = plt.subplots(1, len(WINDOWS), figsize=(4 * len(WINDOWS), 3.6))
    for ax, name in zip(axes, WINDOWS):
        e, h = fine[name]; x = 0.5 * (e[:-1] + e[1:]); w = e[1] - e[0]
        ax.errorbar(x, h / w, np.sqrt(h) / w, fmt='.', ms=3, color='k', lw=0.6)
        if name in curves:
            ax.plot(x, curves[name], color='#c0392b', lw=1.2)
        ax.set_title(name); ax.set_xlabel('m(mumu) [GeV]'); ax.set_ylabel('events / GeV')
    fig.tight_layout(); fig.savefig(os.path.join(a.out, 'dimuon_fits.png'), dpi=150)


if __name__ == '__main__':
    main()

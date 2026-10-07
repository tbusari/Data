#!/usr/bin/env python3
"""Generate toy files with the outreach-NanoAOD branch layout, for pipeline tests only.

Not physics: resonances are Gaussians at PDG masses with a pT-independent 1.2 % momentum
smearing, continuum is exponential, the 4l toys contain a ZZ-like continuum plus a
125 GeV peak.  Yields are chosen so the scripts exercise every code path.

usage: make_toy_nanoaod.py OUTDIR [--seed N]
"""
import argparse
import os

import awkward as ak
import numpy as np
import uproot

from nanolib import PDG

rng = np.random.default_rng(1)


def two_body(m, n):
    """Decay n resonances of mass m to two muons, mild boost; return (pt, eta, phi) arrays shape (n,2)."""
    pt_res = rng.exponential(6.0, n) + 2.0
    y = rng.normal(0, 1.2, n)
    phi_res = rng.uniform(-np.pi, np.pi, n)
    cos = rng.uniform(-1, 1, n); ph = rng.uniform(-np.pi, np.pi, n)
    p = np.sqrt(np.maximum(m ** 2 / 4 - PDG['mu'] ** 2, 0))
    p1 = np.stack([p * np.sqrt(1 - cos ** 2) * np.cos(ph), p * np.sqrt(1 - cos ** 2) * np.sin(ph), p * cos], 1)
    e1 = np.sqrt(p ** 2 + PDG['mu'] ** 2)
    out = []
    for sgn in (+1, -1):
        px, py, pz = (sgn * p1).T
        e = e1
        # boost: transverse then longitudinal
        mt = np.sqrt(m ** 2 + pt_res ** 2)
        bx = pt_res * np.cos(phi_res) / mt; by = pt_res * np.sin(phi_res) / mt
        g = mt / m; b2 = bx ** 2 + by ** 2
        bp = bx * px + by * py
        px2 = px + ((g - 1) * bp / np.where(b2 > 0, b2, 1) + g * e) * bx
        py2 = py + ((g - 1) * bp / np.where(b2 > 0, b2, 1) + g * e) * by
        e2 = g * (e + bp)
        pz2 = pz * np.cosh(y) + e2 * np.sinh(y)
        e3 = e2 * np.cosh(y) + pz * np.sinh(y)
        pt = np.hypot(px2, py2)
        out.append((pt, np.arcsinh(pz2 / pt), np.arctan2(py2, px2)))
    return out


def smear(pt):
    if isinstance(pt, ak.Array):
        counts = ak.num(pt)
        flat = ak.flatten(pt)
        return ak.unflatten(flat * rng.normal(1, 0.012, len(flat)), counts)
    return pt * rng.normal(1, 0.012, pt.shape)


def dimuon_file(path, n_cont=400000):
    comps = [(PDG['J/psi'], 120000), (PDG['psi(2S)'], 9000), (PDG['Upsilon(1S)'], 30000),
             (PDG['Upsilon(2S)'], 9000), (PDG['Upsilon(3S)'], 5000), (PDG['Z'], 60000),
             (PDG['phi'], 8000), (PDG['rho/omega'], 10000), (PDG['eta'], 3000)]
    pts, etas, phis, qs = [], [], [], []
    for m, n in comps:
        masses = np.full(n, m)
        if m == PDG['Z']:   # Breit-Wigner line shape for the Z
            masses = np.clip(m + 0.5 * PDG['Z_width'] * rng.standard_cauchy(n), 60, 130)
        (pt1, eta1, phi1), (pt2, eta2, phi2) = two_body(masses, n)
        pts.append(np.stack([smear(pt1), smear(pt2)], 1)); etas.append(np.stack([eta1, eta2], 1))
        phis.append(np.stack([phi1, phi2], 1)); qs.append(np.tile([1, -1], (n, 1)))
    mc = 0.3 + rng.exponential(3.0, n_cont) * (1 + 10 * rng.random(n_cont) ** 8)
    (pt1, eta1, phi1), (pt2, eta2, phi2) = two_body(mc, n_cont)
    pts.append(np.stack([smear(pt1), smear(pt2)], 1)); etas.append(np.stack([eta1, eta2], 1))
    phis.append(np.stack([phi1, phi2], 1)); qs.append(np.tile([1, -1], (n_cont, 1)))
    # some same-sign and 3-muon junk
    pt = np.concatenate(pts); eta = np.concatenate(etas); phi = np.concatenate(phis); q = np.concatenate(qs)
    n = len(pt); order = rng.permutation(n)
    pt, eta, phi, q = pt[order], eta[order], phi[order], q[order]
    ss = rng.random(n) < 0.05
    q[ss, 1] = q[ss, 0]
    write(path, dict(run=np.full(n, 199318, np.int32), luminosityBlock=np.full(n, 114, np.int32),
                     event=np.arange(n, dtype=np.int64)),
          {'Muon': dict(pt=pt, eta=eta, phi=phi, mass=np.full_like(pt, PDG['mu']),
                        charge=q.astype(np.int32))}, lepton_extras=False)


def four_lepton(n, mass_fn):
    """n events of X -> Z1 Z2 -> 4 leptons; returns per-lepton kinematics (n,4) and Z masses."""
    m4 = mass_fn(n)
    mz1 = np.clip(rng.normal(PDG['Z'], 3.0, n), 45, m4 - 15)
    mz2 = np.clip(m4 - mz1 - rng.exponential(10, n), 13, 115)
    # decay X at rest-ish to Z1 Z2 back to back, then each to leptons
    pts, etas, phis = [], [], []
    for mz in (mz1, mz2):
        (pt1, eta1, phi1), (pt2, eta2, phi2) = two_body(mz, n)
        pts += [pt1, pt2]; etas += [eta1, eta2]; phis += [phi1, phi2]
    return np.stack(pts, 1), np.stack(etas, 1), np.stack(phis, 1)


def lepton_block(pt, eta, phi, mass, charge):
    n = len(pt)
    return dict(pt=smear(pt), eta=eta, phi=phi, mass=np.full_like(pt, mass), charge=charge.astype(np.int32),
                dxy=rng.normal(0, 0.01, pt.shape), dxyErr=np.full_like(pt, 0.01),
                dz=rng.normal(0, 0.02, pt.shape), dzErr=np.full_like(pt, 0.02))


def h4l_file(path, n_zz, n_h, run, kind, mc=False):
    """kind in {'4mu','4e','2mu2e','mix'}; data files mix channels, MC files are one channel."""
    comps = []
    if n_zz:
        comps.append(four_lepton(n_zz, lambda k: 180 + rng.exponential(60, k) * (rng.random(k) < 0.8) + rng.uniform(-100, 0, k) * (rng.random(k) < 0.25)))
    if n_h:
        comps.append(four_lepton(n_h, lambda k: rng.normal(125.0, 1.8, k)))
    pt = np.concatenate([c[0] for c in comps]); eta = np.concatenate([c[1] for c in comps]); phi = np.concatenate([c[2] for c in comps])
    n = len(pt)
    kinds = np.full(n, kind) if kind != 'mix' else rng.choice(['4mu', '2mu2e', '4e'], n, p=[0.35, 0.45, 0.20])
    q = np.tile([1, -1, 1, -1], (n, 1))
    mu_pt, mu_eta, mu_phi, mu_q, el_pt, el_eta, el_phi, el_q = ([] for _ in range(8))
    for i in range(n):
        if kinds[i] == '4mu':
            mu_pt.append(pt[i]); mu_eta.append(eta[i]); mu_phi.append(phi[i]); mu_q.append(q[i])
            el_pt.append(np.empty(0)); el_eta.append(np.empty(0)); el_phi.append(np.empty(0)); el_q.append(np.empty(0, int))
        elif kinds[i] == '4e':
            el_pt.append(pt[i]); el_eta.append(eta[i]); el_phi.append(phi[i]); el_q.append(q[i])
            mu_pt.append(np.empty(0)); mu_eta.append(np.empty(0)); mu_phi.append(np.empty(0)); mu_q.append(np.empty(0, int))
        else:
            mu_pt.append(pt[i, :2]); mu_eta.append(eta[i, :2]); mu_phi.append(phi[i, :2]); mu_q.append(q[i, :2])
            el_pt.append(pt[i, 2:]); el_eta.append(eta[i, 2:]); el_phi.append(phi[i, 2:]); el_q.append(q[i, 2:])
    mu = {k: ak.Array(v) for k, v in dict(pt=mu_pt, eta=mu_eta, phi=mu_phi).items()}
    el = {k: ak.Array(v) for k, v in dict(pt=el_pt, eta=el_eta, phi=el_phi).items()}
    muon = dict(pt=smear(mu['pt']), eta=mu['eta'], phi=mu['phi'], mass=ak.full_like(mu['pt'], PDG['mu']),
                charge=ak.values_astype(ak.Array(mu_q), np.int32), pfRelIso04_all=abs(rng.normal(0.05, 0.08, 1)[0]) + 0 * mu['pt'],
                dxy=0.005 + 0 * mu['pt'], dxyErr=0.01 + 0 * mu['pt'], dz=0.01 + 0 * mu['pt'], dzErr=0.02 + 0 * mu['pt'])
    elec = dict(pt=smear(el['pt']), eta=el['eta'], phi=el['phi'], mass=ak.full_like(el['pt'], PDG['e']),
                charge=ak.values_astype(ak.Array(el_q), np.int32), pfRelIso03_all=0.05 + 0 * el['pt'],
                dxy=0.005 + 0 * el['pt'], dxyErr=0.01 + 0 * el['pt'], dz=0.01 + 0 * el['pt'], dzErr=0.02 + 0 * el['pt'])
    write(path, dict(run=np.full(n, run, np.int32), luminosityBlock=rng.integers(1, 1500, n).astype(np.int32),
                     event=np.arange(1, n + 1, dtype=np.int64)), {'Muon': muon, 'Electron': elec})


def write(path, scalars, blocks, lepton_extras=True):
    """Write NanoAOD-style flat branches: nMuon, Muon_pt, ... (uproot naming hooks)."""
    tree = dict(scalars)
    for pre, b in blocks.items():
        arr = {}
        for k, v in b.items():
            v = ak.Array(v)
            if isinstance(v.type.content, ak.types.RegularType):
                v = ak.from_regular(v, axis=1)
            arr[k] = ak.values_astype(v, np.int32 if k == 'charge' else np.float64)
        tree[pre] = ak.zip(arr)
    with uproot.recreate(path) as f:
        f.mktree('Events', {k: (v.dtype if isinstance(v, np.ndarray) else v.type.content) for k, v in tree.items()},
                 counter_name=lambda c: 'n' + c, field_name=lambda outer, inner: outer + '_' + inner)
        f['Events'].extend(tree)
    print('wrote', path)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('outdir'); a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    dimuon_file(os.path.join(a.outdir, 'toy_DoubleMuParked_Muons.root'))
    h4l_file(os.path.join(a.outdir, 'toy_Run2012C_DoubleMuParked.root'), 60, 8, 199318, 'mix')
    h4l_file(os.path.join(a.outdir, 'toy_Run2012C_DoubleElectron.root'), 15, 2, 202016, '4e')
    h4l_file(os.path.join(a.outdir, 'toy_SMHiggsToZZTo4L.root'), 0, 30000, 1, 'mix', mc=True)
    h4l_file(os.path.join(a.outdir, 'toy_ZZTo4mu.root'), 30000, 0, 1, '4mu', mc=True)
    h4l_file(os.path.join(a.outdir, 'toy_ZZTo4e.root'), 30000, 0, 1, '4e', mc=True)
    h4l_file(os.path.join(a.outdir, 'toy_ZZTo2e2mu.root'), 30000, 0, 1, '2mu2e', mc=True)

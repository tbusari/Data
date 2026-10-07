#!/usr/bin/env python3
"""Diagnostics for 2mu2e candidates: lepton kinematics of window candidates, and a dump of
specific (run, event) pairs.  usage: diag_2mu2e.py FILE.root [run:event ...]"""
import sys, awkward as ak, numpy as np
from nanolib import iterate, p4, mass_of, PDG
from h4l_reanalysis import select, MU_BR, EL_BR, EV_BR
f = sys.argv[1]; want = {tuple(int(x) for x in a.split(':')) for a in sys.argv[2:]}
rows = []; dumped = 0
for chunk in iterate([f], EV_BR + MU_BR + EL_BR):
    m, ev = select(chunk, '2mu2e')
    win = (m >= 120) & (m < 130); ev = ev[win]
    for i in range(len(ev)):
        e = ev[i]
        mu_pt = list(e.Muon_pt); el_pt = list(e.Electron_pt)
        def m2(pt, eta, phi):
            return np.sqrt(max(2 * pt[0] * pt[1] * (np.cosh(eta[0] - eta[1]) - np.cos(phi[0] - phi[1])), 0))
        mmm = m2(list(e.Muon_pt), list(e.Muon_eta), list(e.Muon_phi))
        mee = m2(list(e.Electron_pt), list(e.Electron_eta), list(e.Electron_phi))
        rows.append((float(mmm), float(mee), min(mu_pt), min(el_pt), max(list(e.Electron_pfRelIso03_all)), max(list(e.Muon_pfRelIso04_all))))
    if want:
        sel = chunk[[(int(r), int(x)) in want for r, x in zip(chunk.run, chunk.event)]]
        for i in range(len(sel)):
            e = sel[i]; dumped += 1
            print(f"\n=== run {e.run} event {e.event}: nMuon={e.nMuon} nElectron={e.nElectron}")
            for j in range(e.nMuon):
                print(f"  mu  pt {e.Muon_pt[j]:6.1f} eta {e.Muon_eta[j]:+5.2f} q {e.Muon_charge[j]:+d} iso04 {e.Muon_pfRelIso04_all[j]:.3f} dxy {e.Muon_dxy[j]:+.4f} dz {e.Muon_dz[j]:+.4f} sip3d {np.hypot(e.Muon_dxy[j], e.Muon_dz[j])/np.hypot(e.Muon_dxyErr[j], e.Muon_dzErr[j]):.2f}")
            for j in range(e.nElectron):
                print(f"  e   pt {e.Electron_pt[j]:6.1f} eta {e.Electron_eta[j]:+5.2f} q {e.Electron_charge[j]:+d} iso03 {e.Electron_pfRelIso03_all[j]:.3f} dxy {e.Electron_dxy[j]:+.4f} dz {e.Electron_dz[j]:+.4f} sip3d {np.hypot(e.Electron_dxy[j], e.Electron_dz[j])/np.hypot(e.Electron_dxyErr[j], e.Electron_dzErr[j]):.2f}")
r = np.array(rows)
print(f"\n2mu2e window candidates in {f.split('/')[-1]}: {len(r)}")
if len(r):
    print(f"  m(mumu) in 80-100 GeV: {((r[:,0]>80)&(r[:,0]<100)).sum()}   m(ee) in 80-100: {((r[:,1]>80)&(r[:,1]<100)).sum()}")
    print(f"  m(ee) < 20 GeV: {(r[:,1]<20).sum()}   min electron pT < 10 GeV: {(r[:,3]<10).sum()}   min electron pT < 20: {(r[:,3]<20).sum()}")
    print(f"  median m(mumu) {np.median(r[:,0]):.1f}, median m(ee) {np.median(r[:,1]):.1f}, median min e pT {np.median(r[:,3]):.1f}, median max e iso {np.median(r[:,4]):.3f}")
    print("  first 15 (m_mumu, m_ee, min mu pT, min e pT, max e iso, max mu iso):"); [print("   ", tuple(round(float(v),2) for v in x)) for x in r[:15]]

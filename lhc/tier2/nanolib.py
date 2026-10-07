"""Shared helpers for the CMS 2012 outreach-NanoAOD analyses (uproot + awkward)."""
import json
import numpy as np
import awkward as ak
import uproot

PDG = {  # GeV, PDG 2024
    'eta': 0.547862, 'rho/omega': 0.78266, 'phi': 1.019461,
    'J/psi': 3.096900, 'psi(2S)': 3.686097,
    'Upsilon(1S)': 9.46040, 'Upsilon(2S)': 10.02326, 'Upsilon(3S)': 10.3552,
    'Z': 91.1880, 'Z_width': 2.4955, 'mu': 0.1056584, 'e': 0.000510999,
}


def iterate(files, branches, step='200 MB', tree='Events'):
    """Yield awkward record chunks with the requested branches from one or more files."""
    paths = [f'{f}:{tree}' for f in files]
    for chunk in uproot.iterate(paths, branches, step_size=step, library='ak'):
        yield chunk


def branches_in(path, tree='Events'):
    with uproot.open(path) as f:
        return set(f[tree].keys())


def p4(pt, eta, phi, mass):
    px = pt * np.cos(phi)
    py = pt * np.sin(phi)
    pz = pt * np.sinh(eta)
    e = np.sqrt(px ** 2 + py ** 2 + pz ** 2 + mass ** 2)
    return ak.zip({'E': e, 'px': px, 'py': py, 'pz': pz})


def mass_of(*vs):
    e = sum(v.E for v in vs)
    px = sum(v.px for v in vs)
    py = sum(v.py for v in vs)
    pz = sum(v.pz for v in vs)
    m2 = e ** 2 - px ** 2 - py ** 2 - pz ** 2
    return np.sqrt(ak.where(m2 > 0, m2, 0))


def load_golden(path):
    g = json.load(open(path))
    return {int(r): [(a, b) for a, b in ranges] for r, ranges in g.items()}


def golden_mask(run, lumi, golden):
    run = ak.to_numpy(run)
    lumi = ak.to_numpy(lumi)
    ok = np.zeros(len(run), dtype=bool)
    for r in np.unique(run):
        sel = run == r
        for a, b in golden.get(int(r), []):
            ok[sel & (lumi >= a) & (lumi <= b)] = True
    return ok

#!/usr/bin/env python3
"""Systematic check of the Z pole fit: vary the fit window and background model.

Reads the fine Z histogram saved by dimuon_spectrum.py.  The fitted pole moves with the
window because the low-mass side carries final-state radiation that neither the Voigt
nor the smooth background describes; the spread is quoted as a model systematic.

usage: z_window_scan.py results/dimuon/dimuon_spectrum.npz
"""
import sys
import numpy as np
from scipy.optimize import curve_fit
from scipy.special import voigt_profile
from nanolib import PDG

d = np.load(sys.argv[1])
e, h = d['Z_edges'], d['Z_hist']
x = 0.5 * (e[:-1] + e[1:]); w = e[1] - e[0]


def voigt_exp(x, n, mu, sig, b0, slope):
    return n * voigt_profile(x - mu, sig, PDG['Z_width'] / 2) + b0 * np.exp(-slope * (x - 70))


def voigt_lin(x, n, mu, sig, b0, b1):
    return n * voigt_profile(x - mu, sig, PDG['Z_width'] / 2) + b0 + b1 * (x - 91)


print(f"{'window [GeV]':>13} {'background':>11} {'pole [GeV]':>11} {'sigma [GeV]':>12} {'pole - PDG [MeV]':>17}")
masses = []
for lo, hi in [(70, 112), (80, 100), (85, 97), (88, 95)]:
    m = (x >= lo) & (x < hi); y = h[m] / w; err = np.sqrt(np.maximum(h[m], 1)) / w
    for name, f, p0 in [('exponential', voigt_exp, [h[m].sum() * 0.9, 91.19, 1.5, max(y[0], 1e-3), 0.05]),
                        ('linear', voigt_lin, [h[m].sum() * 0.9, 91.19, 1.5, y.min(), 0])]:
        popt, _ = curve_fit(f, x[m], y, p0=p0, sigma=err, maxfev=20000)
        masses.append(popt[1])
        print(f"{lo:>6}-{hi:<6} {name:>11} {popt[1]:11.3f} {abs(popt[2]):12.3f} {1000 * (popt[1] - PDG['Z']):17.0f}")
i = np.argmax(h); a, b, c = h[i - 1], h[i], h[i + 1]
vertex = x[i] + 0.5 * w * (a - c) / (a - 2 * b + c)
print(f"\nmodel-free peak (parabola through the three highest bins): {vertex:.3f} GeV, {1000 * (vertex - PDG['Z']):.0f} MeV from PDG")
print(f"spread of fitted poles: {min(masses):.3f} to {max(masses):.3f} GeV ({1000 * (max(masses) - min(masses)):.0f} MeV)")

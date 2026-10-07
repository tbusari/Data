#!/usr/bin/env python3
"""Compare the 11 Hto4l_120-130GeV.ig events with the CMS Open Data H->4l example.

Reads the per-channel 2012 data histograms shipped with
github.com/cms-opendata-analyses/HiggsExample20112012 (rootfiles/DoubleMu12.root,
DoubleE12.root; 3 GeV bins from 70 GeV) and compares the 120-130 GeV bin contents with
the masses produced by h4l_check.py.  Requires ``uproot``.

usage: opendata_h4l_compare.py HiggsExample20112012/rootfiles Hto4l_120-130GeV.ig
"""
import collections
import itertools
import os
import sys

import uproot

from iglib import MZ_PDG, collection, four_vector, invariant_mass, iter_events, leptons

rootdir, igfile = sys.argv[1], sys.argv[2]
HISTS = {'4mu': ('DoubleMu12.root', 'demo/mass4mu_8TeV_low'),
         '2mu2e': ('DoubleMu12.root', 'demo/mass2mu2e_8TeV_low'),
         '4e': ('DoubleE12.root', 'demo/mass4e_8TeV_low')}
CHAN = {'mumumumu': '4mu', 'eemumu': '2mu2e', 'eeee': '4e'}


def pair_mass(a, b):
    return invariant_mass([four_vector(*a[1:4], a[5]), four_vector(*b[1:4], b[5])])


ours = collections.defaultdict(collections.Counter)
for _, ev in iter_events(igfile):
    leps = leptons(ev, min_pt=5.0)
    pairs = [(abs(pair_mass(leps[i], leps[j]) - MZ_PDG), i, j)
             for i, j in itertools.combinations(range(len(leps)), 2)
             if leps[i][0] == leps[j][0] and leps[i][4] * leps[j][4] < 0]
    for _, i, j in sorted(pairs):
        z2 = [(leps[k][1] + leps[l][1], k, l) for _, k, l in pairs if len({i, j, k, l}) == 4]
        if z2:
            _, k, l = max(z2)
            quad = [leps[x] for x in (i, j, k, l)]
            m4l = invariant_mass([four_vector(*q[1:4], q[5]) for q in quad])
            lo = 70 + 3 * int((m4l - 70) // 3)
            ours[CHAN[''.join(sorted(q[0] for q in quad))]][(lo, lo + 3)] += 1
            break

all_ok = True
for chan, (fn, key) in HISTS.items():
    h = uproot.open(os.path.join(rootdir, fn))[key]
    edges, vals = h.axis().edges(), h.values()
    theirs = {(int(edges[i]), int(edges[i + 1])): int(round(vals[i]))
              for i in range(len(vals)) if 120 <= edges[i] < 130 and vals[i] > 0}
    mine = dict(sorted(ours[chan].items()))
    ok = mine == theirs
    all_ok &= ok
    print(f'{chan:6s} ig file: {mine}   open-data histogram: {theirs}   -> {"MATCH" if ok else "DIFFER"}')
print('\nall channels match bin-by-bin:', all_ok)

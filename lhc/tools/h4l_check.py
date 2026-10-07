#!/usr/bin/env python3
"""Re-derive the H -> ZZ* -> 4l kinematics of the events in Hto4l_120-130GeV.ig.

Pairing follows the CMS convention (PLB 716 (2012) 30): Z1 is the opposite-sign,
same-flavour pair closest to m_Z; Z2 is the remaining OS-SF pair with the largest
scalar pT sum.  Leptons below 5 GeV are ignored.  No momentum-scale corrections or
FSR recovery are applied, so masses are "display quality" (see ispy-webgl README).

usage: h4l_check.py Hto4l_120-130GeV.ig
"""
import itertools
import sys

from iglib import MZ_PDG, collection, four_vector, invariant_mass, iter_events, leptons


def pair_mass(a, b):
    return invariant_mass([four_vector(*a[1:4], a[5]), four_vector(*b[1:4], b[5])])


print(f"{'run':>6} {'event':>11} {'chan':5} {'mZ1':>7} {'mZ2':>7} {'m4l':>8}  lepton pT [GeV]")
masses = {}
for _, ev in iter_events(sys.argv[1]):
    e = collection(ev, 'Event_V2')[0]
    leps = leptons(ev, min_pt=5.0)
    pairs = [(abs(pair_mass(leps[i], leps[j]) - MZ_PDG), i, j)
             for i, j in itertools.combinations(range(len(leps)), 2)
             if leps[i][0] == leps[j][0] and leps[i][4] * leps[j][4] < 0]
    best = None
    for _, i, j in sorted(pairs):                      # Z1 candidates, closest to m_Z first
        z2 = [(leps[k][1] + leps[l][1], k, l) for _, k, l in pairs if len({i, j, k, l}) == 4]
        if not z2:
            continue
        _, k, l = max(z2)
        quad = [leps[x] for x in (i, j, k, l)]
        best = (pair_mass(leps[i], leps[j]), pair_mass(leps[k], leps[l]),
                invariant_mass([four_vector(*q[1:4], q[5]) for q in quad]), quad)
        break
    if best is None:
        print(f"{e['run']:6d} {e['event']:11d} no OS-SF pairing")
        continue
    mz1, mz2, m4l, quad = best
    chan = ''.join(sorted(q[0] for q in quad))
    masses.setdefault(chan, []).append(m4l)
    print(f"{e['run']:6d} {e['event']:11d} {chan:5} {mz1:7.2f} {mz2:7.2f} {m4l:8.2f}  "
          + ' '.join(f'{q[1]:.1f}' for q in quad))

print('\nchannel counts:', {k: len(v) for k, v in masses.items()})
print('m4l min/max: %.2f / %.2f GeV' % (min(m for v in masses.values() for m in v),
                                        max(m for v in masses.values() for m in v)))

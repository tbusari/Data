#!/usr/bin/env python3
"""Inventory every event in a set of iSpy .ig files.

For each event print run / lumisection / event number / timestamp, object counts, PF MET,
and naive invariant masses of the two leading muons, electrons and photons.

usage: ig_inventory.py FILE.ig [FILE.ig ...]
"""
import collections
import sys

from iglib import collection, four_vector, invariant_mass, iter_events, M_E, M_MU

all_collections = collections.Counter()
for path in sys.argv[1:]:
    n = 0
    runs = set()
    print(f'\n##### {path}')
    for _, ev in iter_events(path):
        n += 1
        e = collection(ev, 'Event_V2')[0]
        runs.add(e['run'])
        all_collections.update(ev['Collections'].keys())
        mus = collection(ev, 'GlobalMuons_V1')
        els = collection(ev, 'GsfElectrons_V2')
        phs = collection(ev, 'Photons_V1')
        jets = collection(ev, 'PFJets_V1')
        met = collection(ev, 'PFMETs_V1')
        line = (f"run {e['run']:6d} ls {e['ls']:4d} evt {e['event']:11d} {e.get('time', '')[:20]:20s}"
                f" | mu={len(mus)} e={len(els)} g={len(phs)} pfjet={len(jets)}")
        if met:
            line += f" MET={met[0]['pt']:.1f}"
        if len(mus) >= 2:
            line += (f" m(mumu)={invariant_mass([four_vector(m['pt'], m['eta'], m['phi'], M_MU) for m in mus[:2]]):.2f}"
                     f"[q={mus[0]['charge']:+d}{mus[1]['charge']:+d}]")
        if len(els) >= 2:
            line += (f" m(ee)={invariant_mass([four_vector(x['pt'], x['eta'], x['phi'], M_E) for x in els[:2]]):.2f}"
                     f"[q={els[0]['charge']:+d}{els[1]['charge']:+d}]")
        if len(phs) >= 2:
            line += f" m(gg)={invariant_mass([four_vector(g['et'], g['eta'], g['phi']) for g in phs[:2]]):.2f}"
        print(line)
    print(f'{n} events, runs: {sorted(runs)}')

print('\n##### collections present (number of events containing each)')
for name, count in sorted(all_collections.items()):
    print(f'{count:4d}  {name}')

#!/usr/bin/env python3
"""Check that every event's (run, lumisection) is in the CMS 2012 validated-run JSON.

usage: cert_check.py Cert_190456-208686_8TeV_22Jan2013ReReco_Collisions12_JSON.txt FILE.ig [...]
"""
import collections
import json
import os
import sys

from iglib import collection, iter_events

golden = json.load(open(sys.argv[1]))
print(f"{'file':30} {'run':>6} {'LS':>5} {'n':>3}  certified")
bad = 0
for path in sys.argv[2:]:
    seen = collections.Counter()
    for _, ev in iter_events(path):
        e = collection(ev, 'Event_V2')[0]
        seen[(e['run'], e['ls'])] += 1
    for (run, ls), n in sorted(seen.items()):
        ok = any(a <= ls <= b for a, b in golden.get(str(run), []))
        bad += 0 if ok else n
        print(f"{os.path.basename(path):30} {run:6d} {ls:5d} {n:3d}  {'yes' if ok else 'NO'}")
print(f'\nuncertified events: {bad}')

#!/usr/bin/env python3
"""Compare the ispy-webgl Higgs sample with CERN Open Data record 5200.

Record 5200 ("Higgs candidate events from CMS 2011 and 2012 open data release selected in
the H->4l example") ships CSV lists of every candidate with the official mZ1, mZ2, M, and
the file Hto4l_120-130GeV.ig itself.

usage: record5200_compare.py CSV_DIR H4L_CHECK_TXT [IG_FROM_RECORD IG_FROM_ISPY]
  CSV_DIR        directory holding {4mu,2e2mu,4e}_{2011,2012}.csv from record 5200
  H4L_CHECK_TXT  output of h4l_check.py (lhc/results/h4l_check.txt)
  the two optional .ig paths are md5-compared
"""
import csv
import glob
import hashlib
import os
import re
import sys

csv_dir, check = sys.argv[1], sys.argv[2]
ig = {}
for line in open(check):
    m = re.match(r'\s*(\d+)\s+(\d+)\s+(\S+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)', line)
    if m:
        ig[(int(m.group(1)), int(m.group(2)))] = (m.group(3), float(m.group(4)), float(m.group(5)), float(m.group(6)))
print(f'events in ispy-webgl Hto4l_120-130GeV.ig: {len(ig)}')
if len(sys.argv) > 4:
    h = [hashlib.md5(open(p, 'rb').read()).hexdigest() for p in sys.argv[3:5]]
    print(f'md5 record 5200 file : {h[0]}\nmd5 ispy-webgl file  : {h[1]}  -> {"IDENTICAL" if h[0] == h[1] else "DIFFERENT"}')
print(f"\n{'run':>6} {'event':>11} {'chan':6} | {'official mZ1':>12} {'mZ2':>7} {'M':>8} | {'ig mZ1':>7} {'mZ2':>7} {'m4l':>8} | dM")
found = 0
for year in ('2012', '2011'):
    win = {}
    for f in sorted(glob.glob(os.path.join(csv_dir, f'*_{year}.csv'))):
        ch = os.path.basename(f).split('_')[0]
        rows = list(csv.DictReader(open(f)))
        win[ch] = sum(120 <= float(r['M']) < 130 for r in rows)
        for r in rows:
            key = (int(r['Run']), int(r['Event']))
            if key in ig:
                found += 1
                c, a, b, m4 = ig[key]
                print(f"{key[0]:6d} {key[1]:11d} {ch:6} | {float(r['mZ1']):12.2f} {float(r['mZ2']):7.2f} {float(r['M']):8.2f} "
                      f"| {a:7.2f} {b:7.2f} {m4:8.2f} | {m4 - float(r['M']):+5.2f}")
    print(f'{year}: record 5200 candidates with 120 <= M < 130 GeV: {win}, total {sum(win.values())}')
print(f'\nig events found in record 5200 lists: {found} of {len(ig)}')

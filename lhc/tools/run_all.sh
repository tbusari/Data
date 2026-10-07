#!/usr/bin/env bash
# Reproduce lhc/results from scratch.  Needs git, python3, and `pip install uproot`.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${WORK:-$(mktemp -d)}
OUT="$HERE/../results"
cd "$WORK"
[ -d ispy-webgl ] || git clone --depth 1 https://github.com/cms-outreach/ispy-webgl.git
[ -d HiggsExample20112012 ] || git clone --depth 1 https://github.com/cms-opendata-analyses/HiggsExample20112012.git
cd "$HERE"
python3 ig_inventory.py "$WORK"/ispy-webgl/data/*.ig > "$OUT/ig_inventory.txt"
python3 h4l_check.py "$WORK"/ispy-webgl/data/Hto4l_120-130GeV.ig > "$OUT/h4l_check.txt"
python3 cert_check.py "$WORK"/HiggsExample20112012/datasets/Cert_190456-208686_8TeV_22Jan2013ReReco_Collisions12_JSON.txt "$WORK"/ispy-webgl/data/*.ig > "$OUT/cert_check.txt"
python3 opendata_h4l_compare.py "$WORK"/HiggsExample20112012/rootfiles "$WORK"/ispy-webgl/data/Hto4l_120-130GeV.ig > "$OUT/opendata_h4l_compare.txt"
echo "done -> $OUT"

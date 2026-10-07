#!/usr/bin/env bash
# Fetch the CMS 2012 outreach NanoAOD files used by the two Tier-2 analyses.
#
# Source: CERN Open Data, "AOD2NanoAODOutreachTool" derived datasets
#   record 12341  Run2012BC_DoubleMuParked_Muons.root  (dimuon spectrum, ~2.1 GiB)
#   records 12360-12368  per-dataset NanoAOD for the H->4l example (data + simulation)
# Both an HTTPS path (served by opendata.cern.ch) and an XRootD path (eospublic.cern.ch)
# exist; HTTPS is used here. Hosts opendata.cern.ch and eospublic.cern.ch must be reachable.
set -euo pipefail
DEST=${1:-$HOME/cms-opendata-2012}
BASE=https://opendata.cern.ch/eos/opendata/cms/derived-data/AOD2NanoAODOutreachTool
mkdir -p "$DEST"
FILES=(
  Run2012BC_DoubleMuParked_Muons.root
  Run2012B_DoubleMuParked.root
  Run2012C_DoubleMuParked.root
  Run2012B_DoubleElectron.root
  Run2012C_DoubleElectron.root
  SMHiggsToZZTo4L.root
  ZZTo4mu.root
  ZZTo4e.root
  ZZTo2e2mu.root
)
for f in "${FILES[@]}"; do
  if [ -s "$DEST/$f" ]; then echo "have $f"; continue; fi
  echo "fetching $f"
  curl -fL --retry 4 --retry-delay 5 -C - -o "$DEST/$f.part" "$BASE/$f" && mv "$DEST/$f.part" "$DEST/$f"
done
ls -l "$DEST"

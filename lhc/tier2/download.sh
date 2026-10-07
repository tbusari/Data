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
# record 12341 (2.1 GiB) sits at the top level; records 12361-12368 (~12 GiB) under ForHiggsTo4Leptons/
FILES=(
  Run2012BC_DoubleMuParked_Muons.root
  ForHiggsTo4Leptons/SMHiggsToZZTo4L.root
  ForHiggsTo4Leptons/ZZTo4mu.root
  ForHiggsTo4Leptons/ZZTo4e.root
  ForHiggsTo4Leptons/ZZTo2e2mu.root
  ForHiggsTo4Leptons/Run2012B_DoubleMuParked.root
  ForHiggsTo4Leptons/Run2012C_DoubleMuParked.root
  ForHiggsTo4Leptons/Run2012B_DoubleElectron.root
  ForHiggsTo4Leptons/Run2012C_DoubleElectron.root
)
for f in "${FILES[@]}"; do
  b=$(basename "$f")
  if [ -s "$DEST/$b" ]; then echo "have $b"; continue; fi
  echo "fetching $f"
  curl -fL --retry 4 --retry-delay 5 -C - -o "$DEST/$b.part" "$BASE/$f" && mv "$DEST/$b.part" "$DEST/$b"
done
ls -l "$DEST"

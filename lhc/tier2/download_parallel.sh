#!/usr/bin/env bash
# Same files as download.sh, each fetched as N parallel HTTP range requests (about 3x faster
# through a rate-limited proxy). Verifies the assembled size against Content-Length.
set -euo pipefail
DEST=${1:-$HOME/cms-opendata-2012}; N=${N:-8}
BASE=https://opendata.cern.ch/eos/opendata/cms/derived-data/AOD2NanoAODOutreachTool
mkdir -p "$DEST"
FILES=(${FILES:-ForHiggsTo4Leptons/SMHiggsToZZTo4L.root ForHiggsTo4Leptons/ZZTo4mu.root ForHiggsTo4Leptons/ZZTo4e.root ForHiggsTo4Leptons/ZZTo2e2mu.root ForHiggsTo4Leptons/Run2012B_DoubleMuParked.root ForHiggsTo4Leptons/Run2012C_DoubleMuParked.root ForHiggsTo4Leptons/Run2012B_DoubleElectron.root ForHiggsTo4Leptons/Run2012C_DoubleElectron.root Run2012BC_DoubleMuParked_Muons.root})
for f in "${FILES[@]}"; do
  b=$(basename "$f"); out="$DEST/$b"
  if [ -s "$out" ]; then echo "have $b"; continue; fi
  sz=$(curl -sS --retry 5 -I "$BASE/$f" | grep -i '^content-length' | tr -dc 0-9)
  echo "$(date +%T) fetching $b ($((sz/1048576)) MiB) in $N parts"
  ch=$((sz/N+1)); pids=()
  for i in $(seq 0 $((N-1))); do
    a=$((i*ch)); e=$((a+ch-1)); if [ "$e" -ge "$sz" ]; then e=$((sz-1)); fi
    curl -sS --retry 8 --retry-delay 3 -C - -r "$a-$e" -o "$out.part$i" "$BASE/$f" & pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p"; done
  cat $(for i in $(seq 0 $((N-1))); do echo "$out.part$i"; done) > "$out.tmp"
  got=$(stat -c %s "$out.tmp")
  if [ "$got" -ne "$sz" ]; then echo "SIZE MISMATCH for $b: $got vs $sz"; exit 1; fi
  mv "$out.tmp" "$out"; rm -f "$out".part*
  echo "$(date +%T) done $b"
done
ls -l "$DEST"

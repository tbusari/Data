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
  fetch_part() {  # resume until the part has its full size; survives resets the proxy injects
    local a=$1 e=$2 part=$3 want=$(( $2 - $1 + 1 )) have=0 tries=0
    while :; do
      have=$(stat -c %s "$part" 2>/dev/null || echo 0)
      [ "$have" -ge "$want" ] && return 0
      tries=$((tries+1)); [ "$tries" -gt 40 ] && { echo "giving up on $part"; return 1; }
      curl -sS --retry 3 --retry-all-errors --retry-delay 3 -r "$((a+have))-$e" -o "$part.tmp" "$BASE/$f" \
        && cat "$part.tmp" >> "$part"; rm -f "$part.tmp"; sleep 2
    done
  }
  for i in $(seq 0 $((N-1))); do
    a=$((i*ch)); e=$((a+ch-1)); if [ "$e" -ge "$sz" ]; then e=$((sz-1)); fi
    fetch_part "$a" "$e" "$out.part$i" & pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p" || { echo "part failed for $b"; exit 1; }; done
  cat $(for i in $(seq 0 $((N-1))); do echo "$out.part$i"; done) > "$out.tmp"
  got=$(stat -c %s "$out.tmp")
  if [ "$got" -ne "$sz" ]; then echo "SIZE MISMATCH for $b: $got vs $sz"; exit 1; fi
  mv "$out.tmp" "$out"; rm -f "$out".part*
  echo "$(date +%T) done $b"
done
ls -l "$DEST"

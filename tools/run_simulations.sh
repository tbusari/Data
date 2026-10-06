#!/usr/bin/env bash
# Reproduces the simulation numbers quoted in the revised manuscript (results/*.json).
set -euo pipefail
cd "$(dirname "$0")/.."
S=10
python3 -m pcmsec.simulate --seconds $S --profile A --tag-words 4 --ber 0      --dropout-s 2.0 --out results/sim_A_tag64_clean.json   >/dev/null
python3 -m pcmsec.simulate --seconds $S --profile A --tag-words 2 --ber 0      --dropout-s 2.0 --out results/sim_A_tag32_clean.json   >/dev/null
python3 -m pcmsec.simulate --seconds $S --profile B               --ber 0      --dropout-s 2.0 --out results/sim_B_clean.json         >/dev/null
python3 -m pcmsec.simulate --seconds $S --profile A --tag-words 4 --ber 1e-6   --dropout-s 2.0 --out results/sim_A_tag64_ber1e-6.json >/dev/null
python3 -m pcmsec.simulate --seconds $S --profile A --tag-words 4 --ber 1e-5   --dropout-s 2.0 --out results/sim_A_tag64_ber1e-5.json >/dev/null
python3 -m pcmsec.simulate --seconds $S --profile B               --ber 1e-5   --dropout-s 2.0 --out results/sim_B_ber1e-5.json       >/dev/null
python3 -m pcmsec.simulate --seconds $S --profile A --tag-words 4 --ber 0      --dropout-s 2.0 --ground-skew-words 1 --skew-mode payload --out results/sim_A_skew_payload.json >/dev/null
python3 -m pcmsec.simulate --seconds $S --profile A --tag-words 4 --ber 0      --dropout-s 2.0 --ground-skew-words 1 --skew-mode layout  --out results/sim_A_skew_layout.json  >/dev/null
python3 -m pcmsec.simulate --seconds 60 --profile A --tag-words 4 --ber 0      --dropout-s 34.0 --dropout-start-frac 0.2 --out results/sim_A_dropout_across_wrap.json >/dev/null
echo done

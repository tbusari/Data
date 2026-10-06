#!/usr/bin/env python3
"""Generate paper/revised/results_table.tex from results/sim_*.json so the manuscript's
security numbers are reproducible (run tools/run_simulations.sh first)."""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")
OUT = os.path.join(ROOT, "paper", "revised", "results_table.tex")

ROWS = [
    ("sim_A_tag64_clean.json",         "A, 64-bit tag",  "0"),
    ("sim_A_tag32_clean.json",         "A, 32-bit tag",  "0"),
    ("sim_B_clean.json",               "B, deferred",    "0"),
    ("sim_A_tag64_ber1e-6.json",       "A, 64-bit tag",  "$10^{-6}$"),
    ("sim_A_tag64_ber1e-5.json",       "A, 64-bit tag",  "$10^{-5}$"),
    ("sim_B_ber1e-5.json",             "B, deferred",    "$10^{-5}$"),
    ("sim_A_dropout_across_wrap.json", "A, 64-bit tag, 34~s outage across counter wrap", "0"),
    ("sim_A_skew_payload.json",        "A, 64-bit tag, ground payload map relocated one word", "0"),
    ("sim_A_skew_layout.json",         "A, 64-bit tag, ground reads security words from wrong slot", "0"),
]

def load(name):
    with open(os.path.join(RES, name)) as fh:
        return json.load(fh)

def fmt_int(x):
    return f"{x:,}".replace(",", "{,}")

lines = []
lines.append(r"\begin{table}[htbp]")
lines.append(r"  \centering")
lines.append(r"  \caption{Security-layer simulation (\S\ref{sec:security}). Each run carries 64 injected frames (correct header, random payload) and one replayed major frame (32 frames). ``Delivered'' counts frames released to the user; ``non-genuine released'' those among them that are not bit-identical to the source (profile~B releases before authenticating and condemns 15.6~ms later). ``Lost beyond outage'' counts genuine frames after signal restoration that failed to decrypt. Transition density and longest run are for the serialized NRZ-L stream before and after the security layer.}")
lines.append(r"  \label{tab:sec}")
lines.append(r"  \scriptsize")
lines.append(r"  \begin{tabular}{@{}p{3.3cm}ccccccccc@{}}")
lines.append(r"    \toprule")
lines.append(r"    Profile & BER & Over- & Dropout & Delivered & Non-genuine & Rejected at & Lost beyond & Major frames & Cfg \\")
lines.append(r"            &     & head  & (s)     &           & released    & frame level & outage      & auth / fail / unverif. & hash \\")
lines.append(r"    \midrule")
for fn, label, ber in ROWS:
    try:
        r = load(fn)
    except FileNotFoundError:
        print(f"missing {fn}", file=sys.stderr); continue
    d = r["decryptor"]; ch = r["channel"]; ma = r["major_frame_auth"]
    nongenuine = r["delivered"] - r["payload_exact"]
    rejected = d.get("auth_fail", 0) + d.get("replay", 0)
    if r["profile"] == "A":
        rej_cell = f"{rejected} (auth {d.get('auth_fail', 0)}, replay {d.get('replay', 0)})" if r["delivered"] else "all (no session)"
        major = "--"
    else:
        rej_cell = f"{rejected} (replay {d.get('replay', 0)})"
        major = f"{ma['authenticated']} / {ma['auth_fail']} / {ma['incomplete'] + ma['unverified']}"
    lost = r["frames_lost_beyond_dropout"]
    lost_cell = "all" if lost is None else str(lost)
    cfg = {True: "match", False: "mismatch", None: "unreadable"}[r["config_hash_match"]]
    lines.append(f"    {label} & {ber} & {r['layout']['overhead_fraction']*100:.0f}\\% & {ch['dropout_seconds']:.0f} & "
                 f"{fmt_int(r['delivered'])} & {nongenuine} & {rej_cell} & {lost_cell} & {major} & {cfg} \\\\")
lines.append(r"    \bottomrule")
lines.append(r"  \end{tabular}")
# second small block: BER details and transition density
a = load("sim_A_tag64_clean.json"); b5 = load("sim_A_tag64_ber1e-5.json")
ts = a["transition_stats"]
lines.append(r"")
lines.append(r"  \vspace{4pt}")
lines.append(r"  \begin{tabular}{@{}lcc@{}}")
lines.append(r"    \toprule")
lines.append(r"     & Plaintext stream & Secured stream \\")
lines.append(r"    \midrule")
lines.append(f"    NRZ-L transition density (per bit) & {ts['plaintext']['transition_density']:.3f} & {ts['ciphertext']['transition_density']:.3f} \\\\")
lines.append(f"    Longest run without transition (bits) & {ts['plaintext']['longest_run']} & {ts['ciphertext']['longest_run']} \\\\")
lines.append(f"    Frames with a bit error at BER $10^{{-5}}$ (profile A): flipped bits / frames failing authentication & \\multicolumn{{2}}{{c}}{{{b5['channel']['flipped_bits']} / {b5['decryptor'].get('auth_fail',0) - 64}}} \\\\")
lines.append(f"    Software throughput, pure Python (ms per minor frame, encrypt / decrypt) & \\multicolumn{{2}}{{c}}{{{a['timing_ms_per_frame']['encrypt']:.2f} / {a['timing_ms_per_frame']['decrypt']:.2f}}} \\\\")
lines.append(r"    \bottomrule")
lines.append(r"  \end{tabular}")
lines.append(r"\end{table}")
with open(OUT, "w") as fh:
    fh.write("\n".join(lines) + "\n")
print(f"wrote {OUT}")

#!/usr/bin/env python3
"""Cheap structural check for a LaTeX file when no TeX distribution is available:
brace balance (ignoring escaped and commented braces), \\begin/\\end pairing,
and references to undefined labels / citations to undefined bib keys."""
import re, sys, os

path = sys.argv[1]
src = open(path, encoding="utf-8").read()

# follow \input{file} (one level) so labels defined in generated tables resolve
def _inline(m):
    name = m.group(1)
    if not name.endswith(".tex"):
        name += ".tex"
    p = os.path.join(os.path.dirname(path), name)
    return open(p, encoding="utf-8").read() if os.path.exists(p) else f"% missing input {name}"
src = re.sub(r"\\input\{([^}]*)\}", _inline, src)

# strip comments (but not \%)
lines = []
for line in src.splitlines():
    out, i = [], 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            out.append(line[i:i + 2]); i += 2; continue
        if c == "%":
            break
        out.append(c); i += 1
    lines.append("".join(out))
text = "\n".join(lines)

depth, problems = 0, []
i = 0
while i < len(text):
    c = text[i]
    if c == "\\" and i + 1 < len(text):
        i += 2; continue
    if c == "{": depth += 1
    elif c == "}":
        depth -= 1
        if depth < 0:
            problems.append(f"extra '}}' near char {i}: ...{text[max(0,i-40):i+10]!r}"); depth = 0
    i += 1
if depth: problems.append(f"unbalanced braces: depth {depth} at end")

stack = []
for m in re.finditer(r"\\(begin|end)\{([^}]*)\}", text):
    kind, env = m.group(1), m.group(2)
    if kind == "begin": stack.append((env, m.start()))
    else:
        if not stack or stack[-1][0] != env:
            problems.append(f"\\end{{{env}}} at char {m.start()} does not match {stack[-1][0] if stack else 'nothing'}")
            if stack: stack.pop()
        else: stack.pop()
for env, pos in stack: problems.append(f"\\begin{{{env}}} at char {pos} never closed")

labels = set(re.findall(r"\\label\{([^}]*)\}", text))
refs = set(re.findall(r"\\(?:ref|eqref|pageref)\{([^}]*)\}", text))
for r in sorted(refs - labels): problems.append(f"undefined label: {r}")

bib = re.search(r"\\bibliography\{([^}]*)\}", text)
if bib:
    bibpath = os.path.join(os.path.dirname(path), bib.group(1) + ".bib")
    keys = set(re.findall(r"@\w+\{([^,]*),", open(bibpath, encoding="utf-8").read()))
    cites = set()
    for m in re.finditer(r"\\cite[tp]?\*?(?:\[[^\]]*\])?\{([^}]*)\}", text):
        cites.update(k.strip() for k in m.group(1).split(","))
    for c in sorted(cites - keys): problems.append(f"undefined citation: {c}")
    for k in sorted(keys - cites): print(f"note: bib key never cited: {k}")

print("\n".join(problems) if problems else "OK: braces balanced, environments paired, labels and citations resolve")
sys.exit(1 if problems else 0)

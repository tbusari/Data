"""Minimal reader for iSpy ``.ig`` event files (zip archives of one JSON document per event).

The JSON dialect written by ispy-analyzers is loose: it uses ``(...)`` for vectors,
single quotes, and bare ``nan``/``inf`` tokens.  ispy-webgl cleans this in
``js/files-load.js`` (``ispy.cleanupData``) before ``JSON.parse``; we do the same here.
"""
import json
import math
import re
import zipfile

MZ_PDG = 91.1880      # GeV, PDG 2024
M_MU = 0.1056584      # GeV
M_E = 0.000510999     # GeV


def parse_event(text):
    text = text.replace('(', '[').replace(')', ']').replace("'", '"')
    text = re.sub(r'\bnan\b', '0', text)
    text = re.sub(r'\binf\b', '0', text)
    return json.loads(text)


def iter_events(ig_path):
    """Yield (member_name, event_dict) for every event in an .ig archive."""
    with zipfile.ZipFile(ig_path) as z:
        for name in sorted(z.namelist()):
            if 'Events/' in name and not name.endswith('/'):
                yield name, parse_event(z.read(name).decode('utf-8', 'replace'))


def collection(event, name):
    """Return a collection as a list of dicts keyed by the field names in ``Types``."""
    if name not in event['Collections']:
        return []
    keys = [k for k, _ in event['Types'][name]]
    return [dict(zip(keys, row)) for row in event['Collections'][name]]


def four_vector(pt, eta, phi, mass=0.0):
    px, py, pz = pt * math.cos(phi), pt * math.sin(phi), pt * math.sinh(eta)
    return (math.sqrt(px * px + py * py + pz * pz + mass * mass), px, py, pz)


def invariant_mass(vectors):
    e = sum(v[0] for v in vectors)
    px = sum(v[1] for v in vectors)
    py = sum(v[2] for v in vectors)
    pz = sum(v[3] for v in vectors)
    m2 = e * e - px * px - py * py - pz * pz
    return math.sqrt(m2) if m2 > 0 else 0.0


def leptons(event, min_pt=0.0):
    """Global muons and GSF electrons as (flavour, pt, eta, phi, charge, mass)."""
    out = [('mu', m['pt'], m['eta'], m['phi'], m['charge'], M_MU)
           for m in collection(event, 'GlobalMuons_V1')]
    out += [('e', e['pt'], e['eta'], e['phi'], e['charge'], M_E)
            for e in collection(event, 'GsfElectrons_V2')]
    return [l for l in out if l[1] >= min_pt]

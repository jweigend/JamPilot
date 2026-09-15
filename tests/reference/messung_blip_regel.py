"""Blip-Sperre, offline auf Meilenstein-Laeufen: <verzeichnis> <cfg[,cfg]> <T[,T]>

Spielt die Regel aus cli.EventLedger._is_blip (BLIP_BEATS) nachtraeglich
auf die committeten Events eines Laufs von messung_meilensteine.py
(r_<pipe>_<w>_<track>.pkl): Ein Event, das den Akkord von VOR dem letzten
Event zurueckbringt, kuerzer als T nach dem letzten liegt UND auf das
wieder der letzte Akkord folgt (A - D - A - D), faellt weg; die
Wiederholung (D) ist dieselbe Aussage. A - D - A - G bleibt. Je Titel
und Schwelle: Root-Accuracy des angezeigten Akkords je Hop, Timing
(median |dt| der Events zu den .lab-Wechseln, Anteil getroffener Wechsel)
und Kurz-Events < 0,6 s je Minute. Feste Schwelle statt Beat-Raster - die
Live-Sperre nimmt BLIP_BEATS * Beat-Abstand. Ergebnis 2026-09-14:
tests/reference/README.md, Abschnitt "Blip-Sperre".

Aufruf: python tests/reference/messung_blip_regel.py <dir> p2+w2,p2+w4 0.45,0.6,1.0
"""
import sys, pickle, re
from pathlib import Path
from collections import defaultdict
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import messung_meilensteine_auswertung as A
MS = Path(sys.argv[1]); CFGS = sys.argv[2].split(","); TS = [float(x) for x in sys.argv[3].split(",")]

def events(states):
    ev = {}
    for s in states:
        for e in s["committed"]: ev[e["at"]] = e["c"]
    return sorted(ev.items())

def regel(ev, T):
    out = []
    for i, (at, c) in enumerate(ev):
        naechster = ev[i + 1][1] if i + 1 < len(ev) else None
        if (len(out) >= 2 and c == out[-2][1] and c != out[-1][1]
                and at - out[-1][0] < T and naechster == out[-1][1]):
            continue                       # A - D - A - D: das A ist der Blip
        if out and c == out[-1][1]:
            continue                       # dieselbe Aussage
        out.append((at, c))
    return out

def mass(ev, rows, dauer):
    ts = np.arange(10.0, dauer, 0.25); ok = n = 0; i = 0
    ats = [a for a, _ in ev]
    for t in ts:
        g = A.gt_at(rows, t)
        if g is None: continue
        j = np.searchsorted(ats, t, side="right") - 1
        if j < 0: continue
        sn = A.split_name(ev[j][1]); n += 1; ok += int(sn is not None and sn[0] == g[0])
    changes = np.array([a for a, b, c in rows if c is not None and a > 10])
    ons = np.array([a for a, c in ev if c not in ("-", "?")]); dts = []
    for g in changes:
        k = np.argmin(np.abs(ons - g))
        if abs(ons[k] - g) <= 0.5: dts.append(ons[k] - g)
    d = np.abs(dts); kurz = sum(1 for a, b in zip(ev, ev[1:]) if a[0] >= 10 and b[0] - a[0] < 0.6)
    return ok / n, np.median(d) * 1000, len(dts) / len(changes), kurz / ((dauer - 10) / 60)

res = defaultdict(dict)
for pkl in sorted(MS.glob("r_*.pkl")):
    m = re.match(r"r_(p\d)_(w\d)_(.+)\.pkl", pkl.name); cfg = f"{m.group(1)}+{m.group(2)}"; track = m.group(3)
    if cfg not in CFGS or track == "telegraph": continue
    r = pickle.load(open(pkl, "rb")); ev = events(r["states"]); rows = A.load_gt(track)[0]
    res[(track, "ohne")][cfg] = mass(ev, rows, r["dauer"])
    for T in TS:
        res[(track, f"T={T}")][cfg] = mass(regel(ev, T), rows, r["dauer"])
print(f"{'Titel / Regel':32s}" + "".join(f"{c:>34s}" for c in CFGS))
print(f"{'':32s}" + "".join(f"{'Root  med|dt|  getroffen  kurz/min':>34s}" for c in CFGS))
for (track, k), vals in sorted(res.items()):
    print(f"{track[:16]:16s} {k:15s}" + "".join(f"{vals[c][0]*100:8.1f}%{vals[c][1]:7.0f}ms{vals[c][2]*100:8.0f}%{vals[c][3]:8.1f}  " for c in CFGS))

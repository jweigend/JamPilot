"""Meilenstein-Vergleich, Auswertung: <verzeichnis mit r_<pipe>_<w>_<track>.pkl>

Je Lauf (messung_meilensteine.py): angezeigter Akkord je Hop (letztes
committetes Event bzw. Zeitleisteneintrag <= t) gegen die .lab-Referenz
(Root/Triade/exakt, dazu "stabile Mitte" > 0,5 s von GT-Wechseln), Flackern
(angezeigte Wechsel/min, Kurzsegmente < 0,6 s, Revisionen der sichtbaren
Vorschau), Rhythmus (finale Event-Onsets gegen .lab-Wechsel, gleicher
GT-Beat; Telegraph: naechster Beat des Beat-Grids aus dem p2+w2-Lauf ist
Taktlinie oder Schlag davor) und Tonart (Anteil korrekter Hops, erste
korrekte, Anzahl Wechsel). Tabelle: docs/exploration/meilenstein-vergleich-2026-09.md."""
import sys, pickle, glob, re
from pathlib import Path
from collections import defaultdict
import numpy as np
HERE = Path(__file__).resolve().parents[2]; REF = HERE / "tests/reference"
MS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
OFF = {"let_it_be": 0.08, "eight_days_a_week": -0.15, "something": -0.06, "its_too_late": 0.05, "crazy_little_thing": -0.05}
ALIGN = {"let_it_be": (1.00135, -0.090), "eight_days_a_week": (1.00210, -0.208), "something": (1.00040, -0.100)}
KEYS = {"let_it_be": ("C major",), "eight_days_a_week": ("D major",), "something": ("C major",),
        "its_too_late": ("A minor",), "crazy_little_thing": ("D major",)}
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#", "Cb": "B", "Fb": "E"}
HARTE_Q = {"maj": "", "": "", "min": "m", "dim": "dim", "aug": "aug", "min6": "m6", "maj6": "6", "6": "6",
           "min7": "m7", "minmaj7": "mMaj7", "maj7": "maj7", "7": "7", "dim7": "dim7", "hdim7": "m7b5",
           "sus2": "sus2", "sus4": "sus4", "sus4(2)": "sus4", "sus": "sus4", "9": "7", "7sus": "sus4",
           "maj9": "maj7", "min9": "m7", "sus4(b7)": "sus4", "maj(9)": "", "min(9)": "m", "maj(4)": "", "7(#9)": "7", "maj(2)": ""}
TRIAD = {"": "maj", "6": "maj", "maj7": "maj", "7": "maj", "m": "min", "m6": "min", "m7": "min", "mMaj7": "min",
         "dim": "dim", "dim7": "dim", "m7b5": "dim", "aug": "aug", "sus2": "sus", "sus4": "sus"}

def harte(label):
    if label == "N" or label == "X": return None
    label = label.split("/")[0]
    root, _, q = label.partition(":")
    root = FLAT.get(root, root)
    q = q.split("(")[0] + ("(" + q.split("(", 1)[1] if "(" in q and q in HARTE_Q else "")
    return root, HARTE_Q.get(q, HARTE_Q.get(q.split("(")[0], ""))

def split_name(name):
    if not name or name[0] not in "ABCDEFG": return None
    root = name[:2] if len(name) > 1 and name[1] == "#" else name[:1]
    root = FLAT.get(name[:2], root) if len(name) > 1 and name[1] == "b" else root
    q = name[len(root):] if not (len(name) > 1 and name[1] == "b") else name[2:]
    return root, q

def load_gt(track):
    scale, shift = ALIGN.get(track, (1.0, OFF[track]))
    rows = []
    for l in open(REF / f"{track}.lab"):
        p = l.split()
        if len(p) < 3: continue
        rows.append((float(p[0]) * scale + shift, float(p[1]) * scale + shift, harte(p[2])))
    beats = None
    if (REF / f"{track}.beats").exists():
        b = np.loadtxt(REF / f"{track}.beats"); beats = (b[:, 0] * scale + shift, b[:, 1])
    return rows, beats

def gt_at(rows, t):
    for a, b, c in rows:
        if a <= t < b: return c
    return None

def shown(state):
    """Angezeigter Akkord an t: letztes committetes Event (publish-once) bzw. Zeitleisteneintrag <= t."""
    t = state["t"]; src = state["committed"] if state.get("committed") is not None else state["chords"]
    cand = [e for e in src if e["at"] <= t]
    return cand[-1]["c"] if cand else "-"

def final_onsets(states):
    if states[-1].get("committed") is not None:
        ev = {}
        for s in states:
            for e in s["committed"]: ev[e["at"]] = e["c"]
        return sorted(ev.items())
    ev = {}
    for s in states:
        t = s["t"]
        for e in s["chords"]:
            if t - 0.25 < e["at"] <= t: ev[round(e["at"], 3)] = e["c"]
    return sorted(ev.items())

def revisions(states, key):
    """Sichtbare Vorschau: wie oft aendert sich das Label fuer eine feste Zeit T ueber die Hops."""
    seen = {}; changes = 0
    for s in states:
        src = s.get(key)
        if src is None: continue
        t = s["t"]; hi = s.get("frontier") or (t + (s.get("lead") or 4.0))
        for T in np.arange(np.ceil(t * 4) / 4, hi, 0.25):
            cand = [e for e in src if e["at"] <= T]
            lab = cand[-1]["c"] if cand else None
            if T in seen and seen[T] != lab and lab is not None and seen[T] is not None: changes += 1
            if lab is not None: seen[T] = lab
    return changes

def analyse(pkl, tg_beats=None):
    r = pickle.load(open(pkl, "rb")); states = r["states"]; track = r["track"]; dauer = r["dauer"]
    st = [s for s in states if s["t"] >= 10.0]
    res = {}
    # Flackern
    seq = [(s["t"], shown(s)) for s in st]
    trans = sum(1 for i in range(1, len(seq)) if seq[i][1] != seq[i - 1][1])
    segs = []; start = seq[0][0]
    for i in range(1, len(seq)):
        if seq[i][1] != seq[i - 1][1]: segs.append(seq[i][0] - start); start = seq[i][0]
    minutes = (dauer - 10) / 60
    res["Wechsel/min (angezeigt)"] = trans / minutes
    res["Kurzsegmente <0,6 s /min"] = sum(1 for d in segs if d < 0.6) / minutes
    res["Revisionen Vorschau /min"] = revisions(st, "committed" if st[-1].get("committed") is not None else "chords") / minutes
    if st[-1].get("committed") is not None:
        res["Revisionen intern /min"] = revisions(st, "chords") / minutes
    onsets = final_onsets(states); ons = np.array([a for a, c in onsets if c not in ("-", "?")])
    if track == "telegraph":
        if tg_beats is not None:
            b_at, b_n = tg_beats; on = ons[ons > 20]
            nearest = [(b_n[np.argmin(np.abs(b_at - a))], abs(b_at - a).min()) for a in on]
            res["Events"] = len(on)
            res["naechster Beat ist Taktlinie"] = np.mean([n == 1 for n, d in nearest])
            res["naechster Beat ist Schlag davor"] = np.mean([n == 2 for n, d in nearest])
        return track, res
    rows, beats = load_gt(track)
    changes = np.array([a for a, b, c in rows if c is not None and a > 10])
    dts = []
    for g in changes:
        i = np.argmin(np.abs(ons - g))
        if abs(ons[i] - g) <= 0.5: dts.append(ons[i] - g)
    d = np.array(dts)
    res["Events"] = len(ons); res["GT-Wechsel/min"] = len(changes) / minutes
    res["Timing med|dt| ms"] = np.median(np.abs(d)) * 1000; res["Timing <=93 ms"] = np.mean(np.abs(d) <= 0.093)
    res["Timing med dt ms"] = np.median(d) * 1000
    if beats is not None:
        gb = beats[0]; same = tot = 0
        for g in changes:
            i = np.argmin(np.abs(ons - g))
            if abs(ons[i] - g) > 0.6: continue
            tot += 1; same += int(np.argmin(np.abs(gb - g)) == np.argmin(np.abs(gb - ons[i])))
        res["gleicher GT-Beat"] = same / tot
    # Akkordgenauigkeit je Hop
    root = triad = exact = n = 0; root_s = triad_s = exact_s = n_s = 0
    for t, name in seq:
        g = gt_at(rows, t)
        if g is None: continue
        sp = split_name(name); n += 1
        stable = np.min(np.abs(changes - t)) > 0.5
        n_s += stable
        if sp is None: continue
        rt = sp[0] == g[0]; tr = rt and TRIAD.get(sp[1], "?") == TRIAD.get(g[1], "?"); ex = rt and sp[1] == g[1]
        root += rt; triad += tr; exact += ex
        if stable: root_s += rt; triad_s += tr; exact_s += ex
    res["Root-Acc"] = root / n; res["Triad-Acc"] = triad / n; res["Exakt-Acc"] = exact / n
    res["Root-Acc stabile Mitte"] = root_s / n_s; res["Exakt-Acc stabile Mitte"] = exact_s / n_s
    # Tonart
    labels = [(s["t"], (s["key"] or {}).get("label")) for s in states]
    ok = [l in KEYS[track] for t, l in labels if t >= 10]
    res["Tonart korrekt (Anteil Hops)"] = np.mean(ok)
    first = next((t for t, l in labels if l in KEYS[track]), None)
    res["Tonart erstmals korrekt (s)"] = first if first is not None else float("nan")
    res["Tonart-Wechsel (Anzahl)"] = sum(1 for i in range(1, len(labels)) if labels[i][1] != labels[i - 1][1] and labels[i][1] is not None and labels[i-1][1] is not None)
    return track, res

if __name__ == "__main__":
    tg = pickle.load(open(MS / "r_p2_w2_telegraph.pkl", "rb"))
    beats = {}
    for s in tg["states"]:
        for b in s["beats"] or []: beats[b["at"]] = b["n"]
    b_at = np.array(sorted(beats)); b_n = np.array([beats[a] for a in b_at])
    table = defaultdict(dict)
    for pkl in sorted(MS.glob("r_*.pkl")):
        m = re.match(r"r_(p\d)_(w\d)_(.+)\.pkl", pkl.name); cfg = f"{m.group(1)}+{m.group(2)}"
        track, res = analyse(pkl, (b_at, b_n))
        for k, v in res.items(): table[(track, k)][cfg] = v
    cfgs = ["p0+w0", "p1+w0", "p1+w1", "p1+w2", "p2+w1", "p2+w2"]
    cur = None
    for (track, k), vals in sorted(table.items()):
        if track != cur:
            cur = track; print(f"\n== {track:20s} " + " ".join(f"{c:>9s}" for c in cfgs))
        print(f"{k:34s} " + " ".join((f"{vals[c]:9.2f}" if isinstance(vals.get(c), float) and abs(vals[c]) <= 1.0 and 'ms' not in k and '(s)' not in k and 'Anzahl' not in k and 'Events' not in k
                                        else f"{vals[c]:9.0f}" if c in vals else f"{'-':>9s}") for c in cfgs))
    pickle.dump(dict(table), open(MS / "tabelle.pkl", "wb"))

"""Messung: Wie dicht liegen die committeten Events - und was kostet ein
Mindestabstand an Wahrheit?

Simuliert den Live-Pfad (Modell im gleitenden 10-s-Fenster, Merge,
Grenzverfeinerung, EventLedger) ueber einen Referenztrack mit --delay 5 und
misst
  (a) die Abstaende der committeten Events (Anteil unter MIN_EVENT_GAP),
  (b) die Root-Accuracy der Event-Zeitleiste gegen die Isophonics-
      Ground-Truth (.lab), auf einem 0.1-s-Raster, GT != N.

Aufruf:  python tests/reference/messung_event_abstand.py TRACK [refine|norefine] [REPO]
         TRACK z. B. let_it_be; REPO optional (anderer Checkout zum Vergleich).
Ergebnis (2026-08-28, refine an): Events dichter als 0.25 s
  let_it_be  44 von 184 -> 0 von 165,  Root-Acc 84.2 % -> 83.4 %
  something  44 von 151 -> 0 von 139,  Root-Acc 74.8 % -> 75.0 %
Die rohen Modellsegmente unterschreiten 0.25 s nie (0 von 9086) - die Dichte
entstand erst im Live-Pfad (Refine-Floor 0.05 s, Korrektur an der
Commit-Grenze 0.02 s hinter einem eben committeten Event).
"""
import sys, json, time, re
from pathlib import Path
import numpy as np, librosa
REPO = sys.argv[3] if len(sys.argv) > 3 else str(Path(__file__).resolve().parents[2])
sys.path.insert(0, REPO)
from jampilot import cli
from jampilot.btc import (BTCModel, features_from_audio, live_segments_from_labels,
                          refine_boundary)
from jampilot.chords import SILENCE_RMS

track = sys.argv[1]
refine_on = len(sys.argv) < 3 or sys.argv[2] != "norefine"
REF = str(Path(__file__).resolve().parent)
SR = 22050
y, _ = librosa.load(f"{REF}/{track}.mp3", sr=SR, mono=True)
dur = len(y) / SR
model = BTCModel()
DELAY = 5.0
commit_ahead = cli._commit_ahead(DELAY)
hop = cli.ANALYSIS_HOP
win = cli.BTC_LIVE_WINDOW

timeline, previous, refined_bounds = [], None, []
ledger = cli.EventLedger()
seen = {}
raw_gaps = []
t0 = time.time()
for end in np.arange(2.0, dur, hop):
    start = max(0.0, end - win)
    audio = y[int(start * SR):int(end * SR)]
    feats = features_from_audio(audio, SR)
    labels = model.predict(feats)
    segs = live_segments_from_labels(labels, audio, SR, offset=start, silence_rms=SILENCE_RMS)
    for a, b in zip(segs, segs[1:]):
        raw_gaps.append(b[0] - a[0])
    audible = end - DELAY
    frontier = audible + commit_ahead
    horizon = end - cli.BTC_EDGE_GUARD
    cli._merge_model_segments(timeline, segs, audible, horizon, previous, commit_ahead=commit_ahead)
    previous = segs
    if refine_on:
        gap = getattr(cli, "MIN_EVENT_GAP", 0.05)
        for idx in range(1, len(timeline)):
            pos, name = timeline[idx]
            if pos <= frontier:
                continue
            if any(rn == name and abs(rp - pos) <= cli.ONSET_HYSTERESIS for rp, rn in refined_bounds):
                continue
            pos = start + refine_boundary(audio, SR, pos - start, timeline[idx - 1][1], name)
            pos = max(pos, timeline[idx - 1][0] + gap)
            if idx + 1 < len(timeline):
                pos = min(pos, timeline[idx + 1][0] - 0.05)
            timeline[idx] = (pos, name)
            refined_bounds.append((pos, name))
        refined_bounds[:] = [(p, n) for p, n in refined_bounds if p > audible - 2.0]
    while len(timeline) > 1 and timeline[1][0] <= audible - 2.0:
        timeline.pop(0)
    ledger.advance(timeline, [None] * len(timeline), None, frontier)
    for e in ledger.events:
        seen[e["at"]] = e["c"]
    ledger.prune(audible)

# --- Ground truth: Root-Accuracy auf 0.1-s-Raster (nur GT != N) ---
NOTE = {"C":0,"C#":1,"Db":1,"D":2,"D#":3,"Eb":3,"E":4,"F":5,"F#":6,"Gb":6,"G":7,"G#":8,"Ab":8,"A":9,"A#":10,"Bb":10,"B":11,"Cb":11,"Fb":4}
def root_of(label):
    m = re.match(r"^([A-G][#b]?)", label)
    return NOTE[m.group(1)] if m else None
gt = []
for line in open(f"{REF}/{track}.lab"):
    a, b, lab = line.split()
    gt.append((float(a), float(b), root_of(lab)))
ats = sorted(seen)
def ev_root(t):
    r = None
    for a in ats:
        if a <= t: r = root_of(seen[a])
        else: break
    return r
hits = total = 0
for a, b, groot in gt:
    if groot is None: continue
    for t in np.arange(a + 0.05, b, 0.1):
        if t < 2.0: continue
        total += 1
        hits += ev_root(t) == groot

gaps = np.diff(ats)
raw = np.array(raw_gaps)
out = {
    "track": track, "refine": refine_on, "repo": REPO, "events": len(ats),
    "gap_lt_0.25": int((gaps < 0.25).sum()), "gap_min": float(gaps.min()) if len(gaps) else None,
    "raw_model_gaps_lt_0.25": int((raw < 0.25 - 1e-6).sum()),
    "root_acc": round(100 * hits / total, 2), "gt_points": total,
    "sec": round(time.time() - t0),
}
print(json.dumps(out))

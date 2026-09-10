"""Messung: Beat-Raster gegen Isophonics-Beat-Annotationen, und was eine
Achtel-Quantisierung der Akkordgrenzen bringen wuerde.

Nur die drei Beatles-Titel tragen Beat-/Downbeat-Annotationen
(tests/reference/<track>.beats: "zeit schlagnummer", 1 = Eins).

Je Track:
  A  Tempo: Ground Truth vs. librosa (ganzer Track) - Oktavverhaeltnis
  B  Beat-F-Measure (+-70 ms) librosa vs. GT; dazu Phase (median |dt|)
  C  Eins-Abstimmung (ERKANNTE BTC-Onsets, Index mod 4 bzw. mod 8) auf dem
     librosa-Raster und auf dem GT-Raster (Oracle) -> Downbeat-F-Measure
  D  Akkordgrenzen (BTC roh / verfeinert) gegen annotierte Wechsel:
     Timing-Fehler heute, und nach dem Schnappen auf Achtel/Viertel eines
     Oracle-Rasters (GT-Beats) bzw. des librosa-Rasters
"""
import sys
from pathlib import Path
import numpy as np
import librosa

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from jampilot.btc import (BTCModel, features_from_audio, segments_from_labels,
                          refine_boundary)

REF = Path(__file__).parent
SR = 22050
OFF = {"let_it_be": 0.08, "eight_days_a_week": -0.15, "something": -0.06}
TOL = 0.07          # MIREX-Toleranz fuer Beat-/Downbeat-Treffer


def f_measure(est, ref, tol=TOL):
    if len(est) == 0 or len(ref) == 0:
        return 0.0
    ref = np.asarray(ref); est = np.asarray(est)
    used = np.zeros(len(ref), bool); hits = 0
    for e in est:
        i = np.argmin(np.abs(ref - e))
        if abs(ref[i] - e) <= tol and not used[i]:
            used[i] = True; hits += 1
    p, r = hits / len(est), hits / len(ref)
    return 0.0 if hits == 0 else 2 * p * r / (p + r)


def nearest(grid, t):
    i = np.clip(np.searchsorted(grid, t), 1, len(grid) - 1)
    return np.where(np.abs(grid[i] - t) < np.abs(grid[i - 1] - t), i, i - 1)


def subdivide(beats, n):
    """Beat-Raster in n Teile je Schlag (n=2: Achtel)."""
    out = []
    for a, b in zip(beats[:-1], beats[1:]):
        out.extend(a + (b - a) * k / n for k in range(n))
    out.append(beats[-1])
    return np.array(out)


def timing(det, gt_changes):
    """dt je annotiertem Wechsel zur naechsten erkannten Grenze (+-0.5 s)."""
    dts = []
    for g in gt_changes:
        i = np.argmin(np.abs(det - g))
        if abs(det[i] - g) <= 0.5:
            dts.append(det[i] - g)
    d = np.array(dts)
    return (f"n={len(d):3d} med|dt| {np.median(np.abs(d))*1000:4.0f} ms  "
            f"<=50 {np.mean(np.abs(d) <= .05):3.0%}  <=93 {np.mean(np.abs(d) <= .093):3.0%}  "
            f"med dt {np.median(d)*1000:+4.0f} ms")


model = BTCModel()
for track, off in OFF.items():
    y, _ = librosa.load(REF / f"{track}.mp3", sr=SR, mono=True)
    gt = np.loadtxt(REF / f"{track}.beats")
    gt_beats = gt[:, 0] + off
    gt_down = gt_beats[gt[:, 1] == 1]
    gt_changes = np.array([float(l.split()[0]) + off for l in open(REF / f"{track}.lab")
                           if l.split()[2] != "N"])
    gt_bpm = 60 / np.median(np.diff(gt_beats))

    # librosa-Raster (ganzer Track = beste Bedingungen fuer librosa)
    tempo, lb = librosa.beat.beat_track(y=y, sr=SR, hop_length=512, units="time")
    tempo = float(np.atleast_1d(tempo)[0])

    # BTC-Grenzen: roh (93-ms-Raster) und verfeinert (wie cmd_analyze)
    labels = model.predict(features_from_audio(y, SR))
    segs = segments_from_labels(labels)
    raw = np.array([p for p, n in segs[1:] if n != "N"])
    fine = []
    for i in range(1, len(segs)):
        p, n = segs[i]
        if n == "N": continue
        fine.append(refine_boundary(y, SR, p, segs[i - 1][1], n))
    fine = np.array(fine)

    print(f"\n=== {track}: GT {gt_bpm:.1f} bpm, librosa {tempo:.1f} bpm "
          f"(x{tempo / gt_bpm:.2f}); GT {len(gt_beats)} Beats, {len(gt_down)} Einsen, "
          f"{len(gt_changes)} Wechsel; BTC {len(fine)} Grenzen")
    # B: Beats
    i = nearest(gt_beats, lb); dt = lb - gt_beats[i]
    print(f"B  Beat-F {f_measure(lb, gt_beats):.2f}   Phase med|dt| {np.median(np.abs(dt))*1000:.0f} ms")
    # C: Eins aus ERKANNTEN Onsets
    for name, grid in (("librosa", lb), ("Oracle-GT", gt_beats)):
        idx = nearest(grid, fine)
        for m in (4, 8):
            votes = np.bincount(idx % m, minlength=m)
            k = int(np.argmax(votes)); down = grid[k::m]
            print(f"C  Eins auf {name:9s} mod {m}: Konz {votes.max()/votes.sum():3.0%}  "
                  f"Downbeat-F {f_measure(down, gt_down):.2f}  (Takte: {len(down)}, GT {len(gt_down)})")
    # D: Quantisierung
    print(f"D  roh                        {timing(raw, gt_changes)}")
    print(f"D  verfeinert (heute)         {timing(fine, gt_changes)}")
    for name, grid in (("Oracle", gt_beats), ("librosa", lb)):
        for sub, label in ((1, "Viertel"), (2, "Achtel "), (4, "16tel  ")):
            g = subdivide(grid, sub)
            for src, det in (("roh", raw), ("fein", fine)):
                q = g[nearest(g, det)]
                print(f"D  {src:4s} -> {label} {name:7s}    {timing(q, gt_changes)}")

"""Braucht es ein Beat-Modell? Variante ohne: Periode von librosa (oder GT als
Oracle), PHASE aus den eigenen verfeinerten Akkord-Onsets (lokaler Median
der Abweichung zum naechsten Beat, +-5 s). Dann Viertel-Snap."""
import sys
from pathlib import Path
import numpy as np, librosa
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from jampilot.btc import BTCModel, features_from_audio, segments_from_labels, refine_boundary
REF = Path(__file__).parent; SR = 22050
OFF = {"let_it_be": 0.08, "eight_days_a_week": -0.15, "something": -0.06}

def nearest(grid, t):
    i = np.clip(np.searchsorted(grid, t), 1, len(grid) - 1)
    return np.where(np.abs(grid[i] - t) < np.abs(grid[i - 1] - t), i, i - 1)

def timing(det, gt):
    d = np.array([det[np.argmin(np.abs(det - g))] - g for g in gt if np.min(np.abs(det - g)) <= 0.5])
    return f"med|dt| {np.median(np.abs(d))*1000:4.0f} ms  <=50 {np.mean(np.abs(d)<=.05):3.0%}  <=93 {np.mean(np.abs(d)<=.093):3.0%}  med dt {np.median(d)*1000:+4.0f}"

def snap_phase_from_onsets(grid, onsets, radius=5.0, bias=0.0):
    """Jeden Onset auf das Raster schnappen, nachdem das Raster lokal um den
    Median-Versatz der Nachbar-Onsets verschoben wurde."""
    out = []
    for b in onsets:
        nb = onsets[np.abs(onsets - b) <= radius]
        shift = np.median(nb - grid[nearest(grid, nb)]) - bias
        g = grid + shift
        out.append(g[nearest(g, b)][()] if False else g[nearest(g, np.array([b]))][0])
    return np.array(out)

model = BTCModel()
for track, off in OFF.items():
    y, _ = librosa.load(REF / f"{track}.mp3", sr=SR, mono=True)
    gt = np.loadtxt(REF / f"{track}.beats"); gt_beats = gt[:, 0] + off
    gt_changes = np.array([float(l.split()[0]) + off for l in open(REF / f"{track}.lab") if l.split()[2] != "N"])
    _, lb = librosa.beat.beat_track(y=y, sr=SR, hop_length=512, units="time")
    labels = model.predict(features_from_audio(y, SR)); segs = segments_from_labels(labels)
    fine = np.array([refine_boundary(y, SR, p, segs[i-1][1], n) for i, (p, n) in enumerate(segs) if i and n != "N"])
    # Oracle-Periode mit falscher Phase: GT-Beats um 150 ms verschoben
    gt_shifted = gt_beats + 0.15
    print(f"\n=== {track}")
    print(f"heute                              {timing(fine, gt_changes)}")
    print(f"Oracle-Beats, Viertel              {timing(gt_beats[nearest(gt_beats, fine)], gt_changes)}")
    print(f"Oracle +150ms verschoben, Viertel  {timing(gt_shifted[nearest(gt_shifted, fine)], gt_changes)}")
    print(f"Oracle-Periode, Phase aus Onsets   {timing(snap_phase_from_onsets(gt_shifted, fine), gt_changes)}")
    print(f"librosa-Beats, Viertel             {timing(lb[nearest(lb, fine)], gt_changes)}")
    print(f"librosa-Periode, Phase aus Onsets  {timing(snap_phase_from_onsets(lb, fine), gt_changes)}")
    print(f"  ... dito, Spaet-Bias 50 ms raus  {timing(snap_phase_from_onsets(lb, fine, bias=0.05), gt_changes)}")

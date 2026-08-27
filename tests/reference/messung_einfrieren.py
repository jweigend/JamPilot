"""Messung: Wie viel Wahrheit verlieren wir beim Einfrieren?

Simuliert das gleitende 10-s-BTC-Fenster ueber die Referenztracks
(tests/reference, Isophonics-Ground-Truth) und vergleicht fuer jeden
Zeitpunkt T:

  frozen(v) = Label fuer T aus dem Fenster mit Ende E = T + 1s (Edge-Guard) + v
              -> das Urteil im Commit-Moment bei Verstehzeit v
  final     = Label fuer T aus dem Fenster mit Ende E = T + 5s
              -> das letzte Urteil, bevor T hoerbar wird (delay 5s)
  gt        = Ground-Truth-Akkord an T (Isophonics, mit Timing-Offset)

Metriken je Verstehzeit v:
  - Revisionsrate (Label / Root): frozen != final
  - Root-Accuracy gegen GT, Delta zur final-Accuracy
  - dasselbe nur fuer "stabile Mitte" (Frames >250ms von GT-Wechseln entfernt)
"""
import json
import re
import sys
import time

from pathlib import Path

import numpy as np
import librosa

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from jampilot.btc import (BTCModel, features_from_audio, LABEL_NAMES,
                          BTC_FRAME_SECONDS)

REF = str(Path(__file__).parent)
OUT = "."   # Ergebnis-JSON landet im Arbeitsverzeichnis
SR = 22050
WIN = 10.0
HOP = 0.5              # Raster fuer Fensterenden und Messpunkte
EDGE = 1.0             # Edge-Guard
VS = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]   # Verstehzeiten
FINAL_OFF = 5.0        # Fensterende des Endurteils: T + 5s

# Chroma-Korrelations-Offsets (tests/reference/README.md): lab-Zeit + Offset = Audio-Zeit
TRACKS = {
    "let_it_be": 0.08,
    "eight_days_a_week": -0.15,
    "something": -0.06,
    "its_too_late": 0.05,
    "crazy_little_thing": -0.05,
}

NOTE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def root_pc_model(name):
    if name in ("N", "?"):
        return None
    m = re.match(r"^([A-G])(#?)", name)
    if not m:
        return None
    return (NOTE_PC[m.group(1)] + (1 if m.group(2) else 0)) % 12


def root_pc_gt(label):
    if label in ("N", "X"):
        return None
    m = re.match(r"^([A-G])([#b]*)", label)
    if not m:
        return None
    pc = NOTE_PC[m.group(1)]
    for ch in m.group(2):
        pc += 1 if ch == "#" else -1
    return pc % 12


def load_gt(path, offset):
    """[(start_audio, end_audio, root_pc)] inkl. N-Segmenten (root None)."""
    out = []
    for line in open(path):
        parts = line.split()
        if len(parts) < 3:
            continue
        out.append((float(parts[0]) + offset, float(parts[1]) + offset,
                    root_pc_gt(parts[2])))
    return out


def gt_at(gt, t):
    for s, e, pc in gt:
        if s <= t < e:
            return pc
    return None


def gt_boundary_near(gt, t, tol=0.25):
    for s, _, _ in gt:
        if abs(s - t) <= tol:
            return True
    return False


def main():
    model = BTCModel()
    per_track = {}
    agg = {v: dict(n=0, rev_label=0, rev_root=0, hit=0, hit_final=0,
                   n_mid=0, hit_mid=0, hit_final_mid=0, rev_root_mid=0)
           for v in VS}

    for track, offset in TRACKS.items():
        t0 = time.time()
        y, _ = librosa.load(f"{REF}/{track}.mp3", sr=SR, mono=True)
        dur = len(y) / SR
        gt = load_gt(f"{REF}/{track}.lab", offset)

        # Alle benoetigten Fenster einmal rechnen: Enden auf HOP-Raster.
        e_grid = np.arange(WIN + HOP, dur + 1e-6, HOP)
        labels_by_e = {}
        for e in e_grid:
            a = y[int(round((e - WIN) * SR)):int(round(e * SR))]
            labels_by_e[round(e * 2)] = model.predict(features_from_audio(a, SR))

        def label_at(e, t):
            labs = labels_by_e.get(round(e * 2))
            if labs is None:
                return None
            idx = int((t - (e - WIN)) / BTC_FRAME_SECONDS)
            if idx < 0 or idx >= len(labs):
                return None
            return LABEL_NAMES[int(labs[idx])]

        t_grid = np.arange(WIN, dur - FINAL_OFF - HOP, HOP)
        stats = {v: dict(n=0, rev_label=0, rev_root=0, hit=0, hit_final=0,
                         n_mid=0, hit_mid=0, hit_final_mid=0, rev_root_mid=0)
                 for v in VS}
        for t in t_grid:
            final = label_at(t + FINAL_OFF, t)
            g = gt_at(gt, t)
            if final is None:
                continue
            final_root = root_pc_model(final)
            mid = not gt_boundary_near(gt, t)
            for v in VS:
                frozen = label_at(t + EDGE + v, t)
                if frozen is None:
                    continue
                st = stats[v]
                fr = root_pc_model(frozen)
                st["n"] += 1
                st["rev_label"] += frozen != final
                st["rev_root"] += fr != final_root
                st["hit"] += fr == g
                st["hit_final"] += final_root == g
                if mid:
                    st["n_mid"] += 1
                    st["hit_mid"] += fr == g
                    st["hit_final_mid"] += final_root == g
                    st["rev_root_mid"] += fr != final_root
        per_track[track] = stats
        for v in VS:
            for k in agg[v]:
                agg[v][k] += stats[v][k]
        print(f"{track}: {dur:.0f}s, {len(e_grid)} Fenster, "
              f"{len(t_grid)} Messpunkte, {time.time()-t0:.0f}s", flush=True)

    def fmt(st):
        n, nm = max(st["n"], 1), max(st["n_mid"], 1)
        return dict(
            n=st["n"],
            revision_label_pct=round(100 * st["rev_label"] / n, 1),
            revision_root_pct=round(100 * st["rev_root"] / n, 1),
            acc_frozen_pct=round(100 * st["hit"] / n, 1),
            acc_final_pct=round(100 * st["hit_final"] / n, 1),
            delta_acc_pct=round(100 * (st["hit_final"] - st["hit"]) / n, 1),
            acc_frozen_mid_pct=round(100 * st["hit_mid"] / nm, 1),
            acc_final_mid_pct=round(100 * st["hit_final_mid"] / nm, 1),
            delta_acc_mid_pct=round(100 * (st["hit_final_mid"] - st["hit_mid"]) / nm, 1),
            revision_root_mid_pct=round(100 * st["rev_root_mid"] / nm, 1),
        )

    result = {
        "gesamt": {str(v): fmt(agg[v]) for v in VS},
        "tracks": {tr: {str(v): fmt(st[v]) for v in VS}
                   for tr, st in per_track.items()},
        "meta": dict(win=WIN, hop=HOP, edge=EDGE, final_off=FINAL_OFF,
                     verstehzeiten=VS,
                     hinweis="frozen: Fensterende T+1+v; final: Fensterende T+5"),
    }
    with open(f"{OUT}/messung_einfrieren.json", "w") as f:
        json.dump(result, f, indent=1)

    print("\n=== GESAMT (alle 5 Tracks) ===")
    print("v[s] | RevLabel% | RevRoot% | AccFrozen% | AccFinal% | ΔAcc | ΔAcc(Mitte)")
    for v in VS:
        r = fmt(agg[v])
        print(f"{v:4.1f} | {r['revision_label_pct']:9.1f} | {r['revision_root_pct']:8.1f} |"
              f" {r['acc_frozen_pct']:10.1f} | {r['acc_final_pct']:9.1f} |"
              f" {r['delta_acc_pct']:4.1f} | {r['delta_acc_mid_pct']:4.1f}")


if __name__ == "__main__":
    main()

"""Taktposition aus Akkordwechseln: Liegen annotierte Wechsel auf Beats, und
laesst sich die Eins per Abstimmung (Wechsel-Index mod 4) bestimmen - global
und aus 10-s-Fenstern?"""
import numpy as np, librosa
SR, HOP = 22050, 512
OFF = {"let_it_be": 0.08, "eight_days_a_week": -0.15, "something": -0.06,
       "its_too_late": 0.05, "crazy_little_thing": -0.05}
for name, off in OFF.items():
    y, _ = librosa.load(f"tests/reference/{name}.mp3", sr=SR, mono=True)
    changes = []
    for line in open(f"tests/reference/{name}.lab"):
        p = line.split()
        if len(p) >= 3 and p[2] != "N": changes.append(float(p[0]) + off)
    changes = np.array(changes)
    tempo, beats = librosa.beat.beat_track(y=y, sr=SR, hop_length=HOP, units="time")
    tempo = float(np.atleast_1d(tempo)[0])
    idx = np.searchsorted(beats, changes); idx = np.clip(idx, 1, len(beats) - 1)
    near = np.where(np.abs(beats[idx] - changes) < np.abs(beats[idx - 1] - changes), idx, idx - 1)
    dt = changes - beats[near]
    on_beat = np.mean(np.abs(dt) < 0.10)
    votes = np.bincount(near % 4, minlength=4)
    eins = int(np.argmax(votes)); konz = votes.max() / votes.sum()
    # 10-s-Fenster: stimmt die lokale Abstimmung mit der globalen ueberein?
    ok, n = 0, 0
    for s in np.arange(0, changes.max() - 10, 1.0):
        m = (changes >= s) & (changes < s + 10)
        if m.sum() < 2: continue
        v = np.bincount(near[m] % 4, minlength=4); n += 1
        ok += int(np.argmax(v) == eins and v.max() > v.sum() / 2)
    print(f"{name:20s} bpm {tempo:6.1f}  wechsel {len(changes):3d}  auf-beat(±100ms) {on_beat:4.0%}  "
          f"|dt| med {np.median(np.abs(dt))*1000:4.0f} ms  eins-votes {votes.tolist()} konz {konz:.0%}  "
          f"10s-fenster einig {ok/n:4.0%} (n={n})")

"""Machbarkeit: Tempo aus 10-s-Fenstern (wie der Live-Pfad sie sieht).

Je Datei: Onset-Huellkurve einmal fuer die ganze Datei, dann gleitende
10-s-Fenster im 1-s-Raster -> librosa.beat.beat_track (dyn. Programmierung)
und librosa.feature.tempo (Tempogramm). Gemessen: Rechenzeit je Fenster,
Streuung des Tempos, Anteil Fenster innerhalb 4 % der Median-Schaetzung,
Oktavfehler (x2 / /2).
"""
import glob, os, sys, time
import numpy as np, librosa

SR, HOP, WIN = 22050, 512, 10.0
files = sorted(glob.glob("tests/reference/*.mp3")) + ["tests/realaudio/peg.wav",
         "tests/realaudio/sting_faith.wav", "tests/realaudio/misty.wav"]
print(f"{'datei':28s} {'n':>4s} {'bt_med':>7s} {'bt_iqr':>7s} {'in4%':>5s} {'okt':>4s} "
      f"{'tg_med':>7s} {'in4%':>5s} {'ms/bt':>6s} {'ms/tg':>6s} {'ms/env':>6s} {'ms/full':>7s}")
for path in files:
    y, _ = librosa.load(path, sr=SR, mono=True, duration=150.0)
    t0 = time.perf_counter(); env_full = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    t_env_full = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter(); tempo_full, beats_full = librosa.beat.beat_track(onset_envelope=env_full, sr=SR, hop_length=HOP)
    t_full = (time.perf_counter() - t0) * 1000
    n_win = int((len(y) / SR - WIN)); bt, tg, tbt, ttg, tenv = [], [], [], [], []
    for s in range(0, n_win, 1):
        seg = y[int(s * SR):int((s + WIN) * SR)]
        t0 = time.perf_counter(); env = librosa.onset.onset_strength(y=seg, sr=SR, hop_length=HOP); tenv.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter(); tempo, beats = librosa.beat.beat_track(onset_envelope=env, sr=SR, hop_length=HOP); tbt.append((time.perf_counter() - t0) * 1000)
        bt.append(float(np.atleast_1d(tempo)[0]))
        t0 = time.perf_counter(); tt = librosa.feature.tempo(onset_envelope=env, sr=SR, hop_length=HOP); ttg.append((time.perf_counter() - t0) * 1000)
        tg.append(float(np.atleast_1d(tt)[0]))
    bt, tg = np.array(bt), np.array(tg)
    def stats(a):
        med = np.median(a); ok = np.mean(np.abs(a / med - 1) < 0.04)
        okt = np.mean((np.abs(a / med - 2) < 0.08) | (np.abs(a / med - 0.5) < 0.02))
        return med, np.subtract(*np.percentile(a, [75, 25])), ok, okt
    m1, i1, o1, k1 = stats(bt); m2, i2, o2, k2 = stats(tg)
    print(f"{os.path.basename(path)[:28]:28s} {len(bt):4d} {m1:7.1f} {i1:7.1f} {o1:5.0%} {k1:4.0%} "
          f"{m2:7.1f} {o2:5.0%} {np.median(tbt):6.1f} {np.median(ttg):6.1f} {np.median(tenv):6.1f} {t_full:7.0f}"
          f"   voll: {float(np.atleast_1d(tempo_full)[0]):.1f} bpm, env {t_env_full:.0f} ms")

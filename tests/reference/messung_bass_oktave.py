"""Bass-OKTAVE aus dem Mix gegen eine isolierte Bassspur (pYIN) messen.

Frage (docs/exploration/lagenkorrekte-bassanzeige.md): Laesst sich aus der
BTC-CQT nicht nur die Tonklasse des Basses lesen, sondern auch die Lage -
E1, E2 oder E3? Referenz ist die isolierte Bassspur einer Stem-Trennung,
auf der pYIN monophon sauber arbeitet; gemessen wird auf dem vollen Mix.

Aufrufe:
  messung_bass_oktave.py <mix.mp3> <bass-stem.mp3> [tau]
  messung_bass_oktave.py --stems <ordner-mit-stems> [tau]   (Mix = Summe aller Stems ausser metronome)

Der Stem wird per Kreuzkorrelation (Tiefpass 250 Hz) am Mix ausgerichtet.
"""
import glob, os, sys, time
import numpy as np, librosa
from scipy.signal import butter, sosfiltfilt, fftconvolve
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from jampilot.btc import (BTCModel, BTC_FRAME_SECONDS, BTC_HOP, BTC_SR, features_from_audio,
                          fold_bass_chroma, fold_bass_register, segments_from_labels)
from jampilot import bass as bassmod
from jampilot.cli import BASS_POOL_SECONDS

F = BTC_FRAME_SECONDS
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


# ---------------------------------------------------------------- Audio laden
def load_pair(mix_f, bass_f):
    mix, _ = librosa.load(mix_f, sr=BTC_SR, mono=True)
    bass, _ = librosa.load(bass_f, sr=BTC_SR, mono=True)
    sos = butter(4, 250, "low", fs=BTC_SR, output="sos")
    n = min(len(mix), len(bass), 120 * BTC_SR)
    lm, lb = sosfiltfilt(sos, mix[:n]), sosfiltfilt(sos, bass[:n])
    maxlag = 2 * BTC_SR
    xc = fftconvolve(lm, lb[::-1], mode="full")
    mid = len(lb) - 1
    lag = int(np.argmax(xc[mid - maxlag: mid + maxlag + 1])) - maxlag
    print(f"Stem-Ausrichtung: Lag {lag / BTC_SR * 1000:.1f} ms")
    bass = np.concatenate([np.zeros(lag, np.float32), bass]) if lag > 0 else bass[-lag:]
    n = min(len(mix), len(bass))
    return mix[:n], bass[:n]


def load_stems(folder):
    stems = {}
    for f in sorted(glob.glob(os.path.join(folder, "*.mp3"))):
        name = os.path.basename(f).split("(youtube)-")[1].split("-")[0]
        if name == "metronome":
            continue
        stems[name], _ = librosa.load(f, sr=BTC_SR, mono=True)
    n = min(len(v) for v in stems.values())
    return sum(v[:n] for v in stems.values()).astype(np.float32), stems["bass"][:n]


# ---------------------------------------------------------------- Referenz
def reference(bass, T):
    """MIDI je Frame aus pYIN auf der isolierten Bassspur, -1 ohne Note."""
    f0, vflag, vprob = librosa.pyin(bass, fmin=28.0, fmax=500.0, sr=BTC_SR,
                                    frame_length=4096, hop_length=BTC_HOP, center=True)
    rms = librosa.feature.rms(y=bass, frame_length=4096, hop_length=BTC_HOP, center=True)[0]
    thr = 0.05 * np.percentile(rms, 95)
    with np.errstate(all="ignore"):
        midi = 69 + 12 * np.log2(f0 / 440.0)
    gt = np.where(vflag & (vprob > 0.5) & (rms > thr) & np.isfinite(midi), np.round(midi), -1)
    gt = gt.astype(int)[:T]
    gt[(gt < 24) | (gt > 59)] = -1          # C1..B3
    return gt


def notes_of(gt, min_frames=3):
    out, t = [], 0
    while t < len(gt):
        if gt[t] < 0:
            t += 1
            continue
        u = t
        while u < len(gt) and gt[u] == gt[t]:
            u += 1
        if u - t >= min_frames:
            out.append((t, u, gt[t]))
        t = u
    return out


# ---------------------------------------------------------------- Schaetzer
def octave_lowest(m, pc, tau):
    """Tiefste Oktave (1..3), deren Notenbin >= tau * staerkster Oktavbin der Tonklasse."""
    v = np.array([m[(o - 1) * 12 + pc] for o in (1, 2, 3)])
    return int(np.where(v >= tau * v.max())[0][0]) + 1


def octave_harmonic(m, pc, nh=6, decay=0.8):
    best, arg = -1e9, None
    for o in (1, 2, 3):
        k0 = (o - 1) * 12 + pc
        s = sum(decay ** (h - 1) * np.log(m[k0 + int(round(12 * np.log2(h)))] + 1e-6)
                for h in range(1, nh + 1) if k0 + int(round(12 * np.log2(h))) < len(m))
        if s > best:
            best, arg = s, o
    return arg


# ---------------------------------------------------------------- Planer von heute (index.html)
TUN, MIDI0 = [4, 9, 2, 7], [28, 33, 38, 43]


def _plan(pcs, last):
    pos = lambda pc: [(s, (pc - TUN[s]) % 12) for s in range(4)]
    node = lambda p: 0.8 * p[0] + 0.10 * p[1] + 0.05 * (MIDI0[p[0]] + p[1] - 28) + 0.5 * max(0, p[1] - 9)
    trans = lambda a, b: 2.5 * abs(a[1] - b[1]) + 2 * abs(a[0] - b[0])
    cand = [pos(pc) for pc in pcs]
    dp = [[(trans(last, p) if last else 0) + node(p) for p in cand[0]]]
    bp = [[-1] * 4]
    for i in range(1, len(cand)):
        dp.append([]); bp.append([])
        for p in cand[i]:
            c, arg = min((dp[i - 1][k] + trans(u, p), k) for k, u in enumerate(cand[i - 1]))
            dp[i].append(c + node(p)); bp[i].append(arg)
    j = int(np.argmin(dp[-1]))
    for i in range(len(cand) - 1, 0, -1):
        j = bp[i][j]
    return cand[0][j]


def planner_octaves(seq):
    """Oktave, die der heutige Planer je Tonwechsel waehlt (Lookahead 5, publish-once)."""
    last, out = None, []
    for i in range(len(seq)):
        p = _plan(seq[i:i + 5], last)
        last = p
        out.append((MIDI0[p[0]] + p[1] - 24) // 12 + 1)
    return out


# ---------------------------------------------------------------- Messung
def main():
    args = sys.argv[1:]
    tau = 0.3
    if args and args[-1].replace(".", "").isdigit():
        tau = float(args.pop())
    t0 = time.time()
    mix, bass = load_stems(args[1]) if args[0] == "--stems" else load_pair(args[0], args[1])
    feat = features_from_audio(mix, BTC_SR)
    feat_b = features_from_audio(bass, BTC_SR)
    T = len(feat)
    gt = reference(bass, T)
    print(f"Audio {len(mix) / BTC_SR:.0f} s, Referenz-Frames mit Bassnote {np.sum(gt >= 0)} "
          f"({time.time() - t0:.0f} s)")

    mag, mag_b = np.exp(feat[:, 0::2]), np.exp(feat_b[:, 0::2])      # Notenbins C1..B6
    notes = notes_of(gt)
    print("Noten (>= 280 ms) je Oktave:",
          {o: sum(1 for *_, m in notes if (m - 24) // 12 + 1 == o) for o in (1, 2, 3)})

    ests = {f"tiefster>={t}": (lambda m, pc, t=t: octave_lowest(m, pc, t)) for t in (0.2, 0.3, 0.5)}
    ests["harmonisch"] = octave_harmonic
    for title, feats in (("isolierte Bassspur (Plausibilitaet der Referenz)", mag_b), ("Mix", mag)):
        print(f"\n== je Note, {title} ==")
        for name, fn in ests.items():
            conf = np.zeros((3, 3), int)
            for s, e, m in notes:
                conf[(m - 24) // 12, fn(feats[s:e].mean(axis=0), m % 12) - 1] += 1
            print(f"  {name:14s} {np.trace(conf) / conf.sum():5.1%}  "
                  + "  ".join(f"O{o + 1} {conf[o, o]}/{conf[o].sum()}" for o in range(3) if conf[o].sum()))

    # Segmentweise wie die Pipeline: BTC-Labels, Pooling BASS_POOL_SECONDS, slash_note
    labels = BTCModel().predict(feat)
    segs = segments_from_labels(labels)
    chroma, register = fold_bass_chroma(feat), fold_bass_register(feat)
    rows = []
    for i, (s0, name) in enumerate(segs):
        s1 = min(segs[i + 1][0] if i + 1 < len(segs) else T * F, s0 + BASS_POOL_SECONDS)
        von, bis = int(s0 / F), int(s1 / F)
        if bis - von < 2 or name == "N":
            continue
        pc = bassmod.slash_note(chroma[:, von:bis].sum(axis=1), name, register[:, von:bis].sum(axis=1))
        if pc is None:
            continue
        g = gt[von:bis]
        g = g[(g >= 0) & (g % 12 == pc)]
        ref = int(np.bincount((g - 24) // 12 + 1).argmax()) if len(g) >= 2 else None
        rows.append((s0, name, pc, octave_lowest(mag[von:bis].sum(axis=0), pc, tau), ref))
    mit = [r for r in rows if r[4] is not None]
    conf = np.zeros((3, 3), int)
    for r in mit:
        conf[r[4] - 1, r[3] - 1] += 1
    print(f"\n== segmentweise (tau {tau}): {len(segs)} Segmente, {len(rows)} mit Bassnote, "
          f"{len(mit)} mit Referenz ==")
    print(f"  Oktave richtig {np.trace(conf)}/{len(mit)} = {np.trace(conf) / max(len(mit), 1):.0%}   "
          f"Matrix Referenz x Schaetzung {conf.tolist()}")
    for r in mit:
        if r[3] != r[4]:
            print(f"    {r[0]:7.1f}s {r[1]:8s} {NAMES[r[2]]}  Schaetzung O{r[3]}  Referenz O{r[4]}")

    seq = [r for i, r in enumerate(rows) if i == 0 or rows[i - 1][2] != r[2]]
    plan = planner_octaves([r[2] for r in seq])
    paare = [(p, r[4]) for p, r in zip(plan, seq) if r[4] is not None]
    n = max(len(paare), 1)
    print(f"  Heutiger Planer auf denselben Events ({len(paare)}): gleiche Oktave "
          f"{sum(p == g for p, g in paare) / n:.0%}, zu tief {sum(p < g for p, g in paare) / n:.0%}, "
          f"zu hoch {sum(p > g for p, g in paare) / n:.0%}")


if __name__ == "__main__":
    main()

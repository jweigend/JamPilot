"""Bass-TONERKENNUNG auf dem getrennten Stem statt auf dem Mix.

Frage (nach docs/exploration/bass-stem-huellkurve.md): Der Open-Unmix-Stem
nimmt der Huellkurve die Bassdrum. Hilft derselbe Stem auch der Basston-
Messung (bass.slash_note auf dem Tiefband-Chroma der BTC-CQT) - Tonklasse
und Oktave? Gemessen wird dieselbe Kette wie in der Pipeline, einmal mit der
CQT des Mixes, einmal mit der CQT des getrennten Stems. Die Akkordlabels
kommen in beiden Faellen aus derselben Quelle (GT bzw. Mix), nur die Quelle
des Bass-Chromas wechselt.

Aufrufe:
  messung_bass_stem_tonerkennung.py gt
      Tonklasse gegen Isophonics-Slashes (5 Titel in tests/reference, wie
      messung_bass_gt.py): falsche Slashes auf Grundton-Segmenten, gefundene
      Umkehrungen, leere Urteile.
  messung_bass_stem_tonerkennung.py oktave <mix.mp3> <bass-stem.mp3>
  messung_bass_stem_tonerkennung.py oktave --stems <ordner>
      Tonklasse und Oktave je Note gegen pYIN auf der ECHTEN isolierten
      Bassspur (wie messung_bass_oktave.py), Mix gegen getrennten Stem; dazu
      segmentweise durch die Kette (BTC-Labels aus dem Mix).

Der getrennte Stem wird bei 44,1 kHz gerechnet (BassStemModel, 6-s-Bloecke
mit 1 s Rand) und fuer die CQT auf 22,05 kHz gebracht wie der Mix.
"""
import glob, os, re, sys, time
import numpy as np, librosa
from scipy.signal import butter, sosfiltfilt, fftconvolve

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from jampilot.btc import (BTCModel, BTC_FRAME_SECONDS, BTC_HOP, BTC_SR, LABEL_NAMES,
                          features_from_audio, fold_bass_chroma, fold_bass_register,
                          segments_from_labels)
from jampilot import bass as bassmod
from jampilot.stems import BassStemModel, MODEL_SR
from jampilot.cli import BASS_POOL_SECONDS

F = BTC_FRAME_SECONDS
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
REF = os.path.dirname(os.path.abspath(__file__))
TAU = 0.3                    # Oktavregel der Pipeline: tiefste Oktave >= 30 % des Maximums


# ---------------------------------------------------------------- Trennung
def separate_all(y44: np.ndarray, core=6.0, margin=1.0) -> np.ndarray:
    """Ganzer Titel (mono, 44,1 kHz) blockweise durch das Modell."""
    m = BassStemModel(threads=4)
    n = len(y44); out = np.zeros(n, np.float32); c = int(core * MODEL_SR); r = int(margin * MODEL_SR)
    t0 = time.time()
    for start in range(0, n, c):
        a, b = max(0, start - r), min(n, start + c + r)
        sep = m.separate(y44[a:b], MODEL_SR)
        out[start:min(n, start + c)] = sep[start - a: start - a + min(c, n - start)]
    print(f"  Trennung {n / MODEL_SR:.0f} s Audio in {time.time() - t0:.0f} s", flush=True)
    return out


def to_btc(y44):
    return librosa.resample(y44, orig_sr=MODEL_SR, target_sr=BTC_SR).astype(np.float32)


# ---------------------------------------------------------------- Teil 1: Isophonics
TRACKS = {"let_it_be": 0.08, "eight_days_a_week": -0.15, "something": -0.06,
          "its_too_late": 0.05, "crazy_little_thing": -0.05}
NOTE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SUFFIX = {"maj": "", "min": "m", "7": "7", "maj7": "maj7", "min7": "m7", "maj6": "6", "6": "6",
          "min6": "m6", "dim": "dim", "aug": "aug", "sus4": "sus4", "sus2": "sus2",
          "dim7": "dim7", "hdim7": "hdim7", "minmaj7": "mMaj7", "9": "7", "maj9": "maj7", "min9": "m7"}
DEG = {"1": 0, "2": 2, "3": 4, "4": 5, "5": 7, "6": 9, "7": 11, "9": 2, "11": 5, "13": 9}
suffixe = {n[1:] for n in LABEL_NAMES[:-2] if n[0] == "C" and (len(n) == 1 or n[1] != "#")}


def parse_pc(s):
    m = re.match(r"^([A-G])([#b]*)$", s)
    if not m:
        return None
    pc = NOTE_PC[m.group(1)]
    for ch in m.group(2):
        pc += 1 if ch == "#" else -1
    return pc % 12


def parse_label(lab):
    if lab in ("N", "X"):
        return None
    root, qual, bassdeg = lab, "maj", None
    if "/" in lab:
        lab, bassdeg = lab.split("/", 1)
    if ":" in lab:
        root, qual = lab.split(":", 1)
    else:
        root = lab
    qual = re.sub(r"\(.*\)", "", qual) or "maj"
    rpc = parse_pc(root)
    if rpc is None or qual not in SUFFIX or SUFFIX[qual] not in suffixe:
        return None
    bpc = rpc
    if bassdeg:
        m = re.match(r"^([b#]*)(\d+)$", bassdeg)
        if not m or m.group(2) not in DEG:
            return None
        bpc = (rpc + DEG[m.group(2)] + sum(1 if c == "#" else -1 for c in m.group(1))) % 12
    return NAMES[rpc] + SUFFIX[qual], rpc, bpc


def teil_gt(nur=None, detail=False):
    """`nur`: Liste von Titeln; `detail`: jedes Umkehrungs-Segment und jeden
    falschen Slash einzeln ausgeben (Zeit, Akkord, GT-Bass, Urteil Mix/Stem)."""
    quellen = ("Mix", "Stem")
    stats = {q: dict(root_n=0, root_falsch=0, root_leer=0, inv_n=0, inv_gefunden=0,
                     inv_falschton=0, inv_leer=0) for q in quellen}
    je_titel = []
    for track, off in TRACKS.items():
        if nur and track not in nur:
            continue
        y44, _ = librosa.load(f"{REF}/{track}.mp3", sr=MODEL_SR, mono=True)
        stem44 = separate_all(y44)
        quelle = {"Mix": to_btc(y44), "Stem": to_btc(stem44)}
        chroma, register = {}, {}
        for q, y in quelle.items():
            feat = features_from_audio(y, BTC_SR)
            chroma[q], register[q] = fold_bass_chroma(feat), fold_bass_register(feat)
        zeile = {q: dict(root_falsch=0, root_n=0, inv_gefunden=0, inv_n=0) for q in quellen}
        for line in open(f"{REF}/{track}.lab"):
            p = line.split()
            if len(p) < 3:
                continue
            s, e = float(p[0]) + off, float(p[1]) + off
            if e - s < 1.0 or s < 0:
                continue
            parsed = parse_label(p[2])
            if not parsed:
                continue
            chord, rpc, bpc = parsed
            von, bis = int(round(s / F)), int(round(min(s + BASS_POOL_SECONDS, e) / F))
            if bis - von < 2:
                continue
            urteile = {}
            for q in quellen:
                v = bassmod.slash_note(chroma[q][:, von:bis].sum(axis=1), chord,
                                       register[q][:, von:bis].sum(axis=1))
                urteile[q] = v
                st, z = stats[q], zeile[q]
                if bpc == rpc:
                    st["root_n"] += 1; z["root_n"] += 1
                    st["root_falsch"] += v is not None and v != rpc
                    z["root_falsch"] += v is not None and v != rpc
                    st["root_leer"] += v is None
                else:
                    st["inv_n"] += 1; z["inv_n"] += 1
                    st["inv_gefunden"] += v == bpc; z["inv_gefunden"] += v == bpc
                    st["inv_falschton"] += v is not None and v != bpc
                    st["inv_leer"] += v is None
            if detail and (bpc != rpc or any(v is not None and v != rpc for v in urteile.values())):
                n = lambda v: "-" if v is None else NAMES[v]
                print(f"    {s:7.2f}s {chord:7s} GT-Bass {NAMES[bpc]:2s}  Mix {n(urteile['Mix']):2s}  "
                      f"Stem {n(urteile['Stem']):2s}" + ("" if bpc != rpc else "   <- falscher Slash"))
        je_titel.append((track, zeile))
        print(f"{track}: " + "  ".join(
            f"{q}: falsche Slashes {zeile[q]['root_falsch']}/{zeile[q]['root_n']}, "
            f"Umkehrungen {zeile[q]['inv_gefunden']}/{zeile[q]['inv_n']}" for q in quellen), flush=True)

    print(f"\n== Isophonics, Pooling {BASS_POOL_SECONDS:.0f} s ab Onset, Akkord aus der Annotation ==")
    print("Quelle | falsche Slashes (Grundton-Seg.) | leer (Grundton-Seg.) | Umkehrung gefunden | falscher Ton (Umk.) | leer (Umk.)")
    for q in quellen:
        st = stats[q]
        print(f"{q:6s} | {st['root_falsch']}/{st['root_n']} = {100 * st['root_falsch'] / max(st['root_n'], 1):.1f}%"
              f" | {st['root_leer']}/{st['root_n']} = {100 * st['root_leer'] / max(st['root_n'], 1):.0f}%"
              f" | {st['inv_gefunden']}/{st['inv_n']} = {100 * st['inv_gefunden'] / max(st['inv_n'], 1):.0f}%"
              f" | {st['inv_falschton']}/{st['inv_n']} | {st['inv_leer']}/{st['inv_n']}")


# ---------------------------------------------------------------- Teil 2: Oktave gegen pYIN
def align(mix, bass, sr):
    sos = butter(4, 250, "low", fs=sr, output="sos")
    n = min(len(mix), len(bass), 120 * sr)
    lm, lb = sosfiltfilt(sos, mix[:n]), sosfiltfilt(sos, bass[:n])
    maxlag = 2 * sr
    xc = fftconvolve(lm, lb[::-1], mode="full")
    mid = len(lb) - 1
    lag = int(np.argmax(xc[mid - maxlag: mid + maxlag + 1])) - maxlag
    print(f"Stem-Ausrichtung: Lag {lag / sr * 1000:.1f} ms")
    bass = np.concatenate([np.zeros(lag, np.float32), bass]) if lag > 0 else bass[-lag:]
    n = min(len(mix), len(bass))
    return mix[:n], bass[:n]


def load_pair(mix_f, bass_f):
    mix, _ = librosa.load(mix_f, sr=MODEL_SR, mono=True)
    bass, _ = librosa.load(bass_f, sr=MODEL_SR, mono=True)
    return align(mix, bass, MODEL_SR)


def load_stems(folder):
    stems = {}
    for f in sorted(glob.glob(os.path.join(folder, "*.mp3"))):
        name = os.path.basename(f).split("(youtube)-")[1].split("-")[0]
        if name == "metronome":
            continue
        stems[name], _ = librosa.load(f, sr=MODEL_SR, mono=True)
    n = min(len(v) for v in stems.values())
    return sum(v[:n] for v in stems.values()).astype(np.float32), stems["bass"][:n]


def reference(bass22, T):
    f0, vflag, vprob = librosa.pyin(bass22, fmin=28.0, fmax=500.0, sr=BTC_SR,
                                    frame_length=4096, hop_length=BTC_HOP, center=True)
    rms = librosa.feature.rms(y=bass22, frame_length=4096, hop_length=BTC_HOP, center=True)[0]
    thr = 0.05 * np.percentile(rms, 95)
    with np.errstate(all="ignore"):
        midi = 69 + 12 * np.log2(f0 / 440.0)
    gt = np.where(vflag & (vprob > 0.5) & (rms > thr) & np.isfinite(midi), np.round(midi), -1)
    gt = gt.astype(int)[:T]
    gt[(gt < 24) | (gt > 59)] = -1
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


def octave_lowest(m, pc, tau=TAU):
    v = np.array([m[(o - 1) * 12 + pc] for o in (1, 2, 3)])
    return int(np.where(v >= tau * v.max())[0][0]) + 1


def teil_oktave(args):
    t0 = time.time()
    mix44, bass44 = load_stems(args[1]) if args[0] == "--stems" else load_pair(args[0], args[1])
    est44 = separate_all(mix44)
    mix, bass, est = to_btc(mix44), to_btc(bass44), to_btc(est44)
    feats = {"Mix": features_from_audio(mix, BTC_SR), "Stem": features_from_audio(est, BTC_SR)}
    T = min(len(f) for f in feats.values())
    gt = reference(bass, T)
    notes = notes_of(gt)
    print(f"Audio {len(mix) / BTC_SR:.0f} s, Referenznoten (>= 280 ms) {len(notes)}, "
          f"je Oktave " + str({o: sum(1 for *_, m in notes if (m - 24) // 12 + 1 == o) for o in (1, 2, 3)})
          + f" ({time.time() - t0:.0f} s)")

    print("\n== je Referenznote: Tonklasse (bass.dominant auf dem Tiefband-Chroma) und Oktave (tiefste >= 0,3) ==")
    print("Quelle | Tonklasse richtig | leer (kein klarer Gewinner) | falsch | Oktave richtig (Noten mit richtiger Tonklasse)")
    for q, feat in feats.items():
        chroma = fold_bass_chroma(feat)
        mag = np.exp(feat[:, 0::2])
        richtig = leer = falsch = okt = 0
        for s, e, m in notes:
            pc = bassmod.dominant(chroma[:, s:e])
            if pc is None:
                leer += 1
            elif pc == m % 12:
                richtig += 1
                okt += octave_lowest(mag[s:e].mean(axis=0), pc) == (m - 24) // 12 + 1
            else:
                falsch += 1
        n = len(notes)
        print(f"{q:6s} | {richtig}/{n} = {100 * richtig / n:.1f}% | {leer}/{n} = {100 * leer / n:.1f}% "
              f"| {falsch}/{n} = {100 * falsch / n:.1f}% | {okt}/{max(richtig, 1)} = {100 * okt / max(richtig, 1):.1f}%")

    # Segmentweise wie die Pipeline: BTC-Labels aus dem MIX, Pooling, slash_note je Quelle
    labels = BTCModel().predict(feats["Mix"])
    segs = segments_from_labels(labels)
    print(f"\n== segmentweise ({len(segs)} BTC-Segmente aus dem Mix, Pooling {BASS_POOL_SECONDS:.0f} s) ==")
    print("Quelle | mit Bassnote | davon mit Referenz | Tonklasse richtig | Oktave richtig")
    for q, feat in feats.items():
        chroma, register, mag = fold_bass_chroma(feat), fold_bass_register(feat), np.exp(feat[:, 0::2])
        mit = ref = pc_ok = okt_ok = 0
        for i, (s0, name) in enumerate(segs):
            s1 = min(segs[i + 1][0] if i + 1 < len(segs) else T * F, s0 + BASS_POOL_SECONDS)
            von, bis = int(s0 / F), min(int(s1 / F), T)
            if bis - von < 2 or name == "N":
                continue
            pc = bassmod.slash_note(chroma[:, von:bis].sum(axis=1), name, register[:, von:bis].sum(axis=1))
            if pc is None:
                continue
            mit += 1
            g = gt[von:bis]; g = g[g >= 0]
            if len(g) < 2:
                continue
            ref += 1
            ref_midi = int(np.bincount(g).argmax())
            if ref_midi % 12 == pc:
                pc_ok += 1
                okt_ok += octave_lowest(mag[von:bis].sum(axis=0), pc) == (ref_midi - 24) // 12 + 1
        print(f"{q:6s} | {mit} | {ref} | {pc_ok}/{ref} = {100 * pc_ok / max(ref, 1):.0f}% "
              f"| {okt_ok}/{pc_ok} = {100 * okt_ok / max(pc_ok, 1):.0f}%")


if __name__ == "__main__":
    if sys.argv[1] == "gt":
        rest = sys.argv[2:]
        detail = "--detail" in rest
        teil_gt(nur=[a for a in rest if a != "--detail"] or None, detail=detail)
    else:
        teil_oktave(sys.argv[2:])

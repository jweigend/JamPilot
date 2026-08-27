"""Bass-Erkennung gegen Isophonics-GT: Commit-Pooling vs. volles Segment."""
import re, sys
from pathlib import Path
import numpy as np, librosa
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from jampilot.btc import features_from_audio, fold_bass_chroma, BTC_FRAME_SECONDS, LABEL_NAMES
from jampilot import bass as bassmod

REF = str(Path(__file__).parent)
TRACKS = {"let_it_be": 0.08, "eight_days_a_week": -0.15, "something": -0.06,
          "its_too_late": 0.05, "crazy_little_thing": -0.05}
NOTE_PC = {"C":0,"D":2,"E":4,"F":5,"G":7,"A":9,"B":11}
NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
SUFFIX = {"maj":"","min":"m","7":"7","maj7":"maj7","min7":"m7","maj6":"6","6":"6",
          "min6":"m6","dim":"dim","aug":"aug","sus4":"sus4","sus2":"sus2",
          "dim7":"dim7","hdim7":"hdim7","minmaj7":"mMaj7","9":"7","maj9":"maj7","min9":"m7"}
DEG = {"1":0,"2":2,"3":4,"4":5,"5":7,"6":9,"7":11,"9":2,"11":5,"13":9}
suffixe = {n[1:] for n in LABEL_NAMES[:-2] if n[0] == "C" and (len(n) == 1 or n[1] != "#")}

def parse_pc(s):
    m = re.match(r"^([A-G])([#b]*)$", s)
    if not m: return None
    pc = NOTE_PC[m.group(1)]
    for ch in m.group(2): pc += 1 if ch == "#" else -1
    return pc % 12

def parse_label(lab):
    if lab in ("N","X"): return None
    root, qual, bassdeg = lab, "maj", None
    if "/" in lab: lab, bassdeg = lab.split("/", 1)
    if ":" in lab: root, qual = lab.split(":", 1)
    else: root = lab
    qual = re.sub(r"\(.*\)", "", qual) or "maj"
    rpc = parse_pc(root)
    if rpc is None or qual not in SUFFIX: return None
    if SUFFIX[qual] not in suffixe: return None
    bpc = rpc
    if bassdeg:
        m = re.match(r"^([b#]*)(\d+)$", bassdeg)
        if not m or m.group(2) not in DEG: return None
        bpc = (rpc + DEG[m.group(2)] + sum(1 if c=="#" else -1 for c in m.group(1))) % 12
    return NAMES[rpc] + SUFFIX[qual], rpc, bpc

F = BTC_FRAME_SECONDS
stats = {k: dict(root_n=0, root_falsch=0, inv_n=0, inv_gefunden=0, inv_falschton=0)
         for k in ("2s", "3s", "voll")}
kipp = 0; total = 0
for track, off in TRACKS.items():
    y, _ = librosa.load(f"{REF}/{track}.mp3", sr=22050, mono=True)
    frames = fold_bass_chroma(features_from_audio(y, 22050))
    if frames.shape[0] == 12: frames = frames.T
    def pooled(a, b):
        von, bis = int(round(a/F)), min(int(round(b/F)), len(frames))
        return frames[von:bis].sum(axis=0) if bis - von >= 2 else None
    for line in open(f"{REF}/{track}.lab"):
        p = line.split()
        if len(p) < 3: continue
        s, e = float(p[0]) + off, float(p[1]) + off
        if e - s < 1.0 or s < 0: continue
        parsed = parse_label(p[2])
        if not parsed: continue
        chord, rpc, bpc = parsed
        total += 1
        vs = {"2s": bassmod.slash_note(pooled(s, min(s+2.0, e)), chord),
              "3s": bassmod.slash_note(pooled(s, min(s+3.0, e)), chord),
              "voll": bassmod.slash_note(pooled(s, e), chord)}
        if len({vs["2s"], vs["3s"], vs["voll"]}) > 1: kipp += 1
        for k, v in vs.items():
            st = stats[k]
            if bpc == rpc:
                st["root_n"] += 1
                st["root_falsch"] += v is not None and v != rpc
            else:
                st["inv_n"] += 1
                st["inv_gefunden"] += v == bpc
                st["inv_falschton"] += v is not None and v != bpc
    print(f"{track} fertig", flush=True)

print(f"\nSegmente >=1s ausgewertet: {total}, Urteil kippt zwischen Poolingstufen: {kipp}")
print("Pooling | falsche Slashes (Grundton-Seg.) | Umkehrung gefunden | falscher Ton (Umkehrungs-Seg.)")
for k in ("2s", "3s", "voll"):
    st = stats[k]
    print(f"{k:6s} | {st['root_falsch']}/{st['root_n']} = {100*st['root_falsch']/max(st['root_n'],1):.1f}%"
          f" | {st['inv_gefunden']}/{st['inv_n']} = {100*st['inv_gefunden']/max(st['inv_n'],1):.0f}%"
          f" | {st['inv_falschton']}/{st['inv_n']}")

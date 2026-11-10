"""Bass-Stem fuer die Tonerkennung - BREIT gemessen (Isophonics, 207 Titel).

Fortsetzung von messung_bass_stem_tonerkennung.py (dort: 5 Titel). Das
Uebergabedokument docs/exploration/bass-stem-tonerkennung.md verlangt vor
einem Einbau eine breitere Messung. Referenz hier: die Isophonics-Slashes
aller 180 Beatles-Titel, 20 Queen, 7 Carole King - Zuordnung Lab -> CD-Rip
und Zeitversatz aus dem ML-Repo (chordml.isophonics.build_matching), als
isophonics_matching.csv neben diesem Skript (Audio-Pfade relativ zur
Bibliothek).

Zwei Stufen:
  1. (parallel, einmalig, Cache) je Titel: Mix laden, Open-Unmix-Stem
     (6-s-Bloecke, 1 s Rand), BTC-CQT auf Mix UND Stem, Tiefband-Chroma,
     Bassregister, Stem-/Mix-Energie je Frame -> <cache>/<lab>.npz
  2. (schnell) je Segment >= 1 s, Pooling BASS_POOL_SECONDS ab Onset,
     Akkord aus der Annotation, bass.slash_note je VARIANTE:
       Mix        - wie die Pipeline heute
       Stem       - Chroma und Register vom Stem
       Stem d1.5  - Stem mit MIN_DOMINANCE 1,5 (statt 1,25)
       Dom:Stem   - Stem entscheidet leer/nicht leer, Ton aus dem Mix
       Dom:Mix    - Mix entscheidet leer/nicht leer, Ton aus dem Stem
     Metriken wie in messung_bass_gt.py: falsche Slashes und leere Urteile
     auf Grundton-Segmenten, gefundene Umkehrungen, falscher Ton und leer
     auf Umkehrungs-Segmenten. Dazu die Teilmenge "ohne Bassgitarre"
     (Yesterday, Blackbird, ...): dort darf der Stem nichts erfinden.

Aufruf (aus dem Repo, .venv):
  python tests/reference/messung_bass_stem_isophonics.py [--workers 12]
        [--min-score 0.5] [--artist Beatles] [--detail] [--only titel ...]
"""
import argparse, csv, os, re, sys, time

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")

import numpy as np

REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, REPO)
from jampilot.btc import (BTC_FRAME_SECONDS, BTC_HOP, BTC_SR, LABEL_NAMES, features_from_audio,
                          fold_bass_chroma, fold_bass_register)
from jampilot import bass as bassmod
from jampilot.cli import BASS_POOL_SECONDS

F = BTC_FRAME_SECONDS
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
REF = os.path.dirname(os.path.abspath(__file__))
LIBRARY = "/home/johannes/mnt/archive/Musik"
ISO = os.path.join(REPO, "..", "JamPilotML", "data", "isophonics")
CACHE = os.path.join(REPO, "..", "JamPilotML", "data", "cache", "stems_iso")

# Beatles-Titel ohne Bassgitarre (Streicher/Gitarre/Indisch): der Stem darf
# hier nichts erfinden - leer ist richtig, ein Slash ist falsch.
OHNE_BASS = {"yesterday", "blackbird", "julia", "mother nature s son", "eleanor rigby",
             "her majesty", "within you without you", "good night", "love you to"}

# ---------------------------------------------------------------- Labels (wie messung_bass_stem_tonerkennung.py)
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


def lese_tabelle():
    with open(os.path.join(REF, "isophonics_matching.csv")) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["offset"] = float(r["offset"]); r["score"] = float(r["score"])
        r["am_rand"] = r["am_rand"] == "True"
    return rows


# ---------------------------------------------------------------- Stufe 1: Trennung + Merkmale (Worker)
# Trennung am Stueck (6-s-Bloecke, 1 s Rand) oder HOPWEISE wie live
# (stems.py: Kern 0,25 s, 1,0 s Kontext davor, 0,5 s dahinter) - letzteres
# beantwortet, ob die Live-Konfiguration fuer die CQT genauso taugt.
BLOCK = (6.0, 1.0, 1.0)
HOP = (0.25, 1.0, 0.5)


def cache_pfad(lab, hop=False):
    return os.path.join(CACHE + ("_hop" if hop else ""),
                        re.sub(r"[^A-Za-z0-9]+", "_", lab) + ".npz")


def berechne(row):
    """Ein Titel: Mix und Stem durch die BTC-CQT, Tiefband-Merkmale in den Cache."""
    import librosa
    from jampilot.stems import BassStemModel, MODEL_SR
    hop = row.get("hop", False)
    ziel = cache_pfad(row["lab"], hop)
    if os.path.exists(ziel):
        return row["lab"], 0.0, "cache"
    t0 = time.time()
    y44, _ = librosa.load(os.path.join(LIBRARY, row["audio"]), sr=MODEL_SR, mono=True)
    m = BassStemModel(threads=2)
    n = len(y44); stem44 = np.zeros(n, np.float32)
    core, links, rechts = HOP if hop else BLOCK
    c, l, r = int(core * MODEL_SR), int(links * MODEL_SR), int(rechts * MODEL_SR)
    for start in range(0, n, c):
        a, b = max(0, start - l), min(n, start + c + r)
        sep = m.separate(y44[a:b], MODEL_SR)
        stem44[start:min(n, start + c)] = sep[start - a: start - a + min(c, n - start)]
    out = {}
    for name, y in (("mix", y44), ("stem", stem44)):
        y22 = librosa.resample(y, orig_sr=MODEL_SR, target_sr=BTC_SR).astype(np.float32)
        feat = features_from_audio(y22, BTC_SR)
        out[name + "_chroma"] = fold_bass_chroma(feat).astype(np.float32)
        out[name + "_register"] = fold_bass_register(feat).astype(np.float32)
        out[name + "_rms"] = librosa.feature.rms(y=y22, frame_length=4096, hop_length=BTC_HOP,
                                                  center=True)[0][: feat.shape[0]].astype(np.float32)
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    np.savez_compressed(ziel, **out)
    return row["lab"], time.time() - t0, "neu"


def stufe1(rows, workers):
    import concurrent.futures as cf, multiprocessing as mp
    todo = [r for r in rows if not os.path.exists(cache_pfad(r["lab"], r.get("hop", False)))]
    print(f"Stufe 1: {len(rows)} Titel, {len(todo)} zu rechnen, {workers} Prozesse", flush=True)
    if not todo:
        return
    t0 = time.time(); fertig = 0
    with cf.ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn")) as pool:
        for lab, dauer, art in pool.map(berechne, todo):
            fertig += 1
            print(f"  [{fertig}/{len(todo)}] {dauer:5.0f} s  {lab}", flush=True)
    print(f"Stufe 1 fertig in {(time.time() - t0) / 60:.1f} min", flush=True)


# ---------------------------------------------------------------- Stufe 2: Urteile je Variante
VARIANTEN = ("Mix", "Stem", "Stem d1.5", "Dom:Stem", "Dom:Mix", "Stem r5", "Stem -5", "Stem&Mix",
             "Mix p1", "Stem p1", "Stem p.5")
INTERVALL = {0: "1", 3: "b3", 4: "3", 7: "5", 10: "b7", 11: "7"}


def urteile(d, chord, von, bis, s=None, e=None):
    """Alle Varianten fuer ein Segment -> {variante: Tonklasse | None}.
    `s`, `e` (Sekunden) fuer die Varianten mit kuerzerem Pooling (1 s, 0,5 s
    ab Onset): Der Bassist wechselt in 2 s oft Grundton und Quinte - der
    Anfang des Segments gehoert meist dem Grundton."""
    mc, mr = d["mix_chroma"][:, von:bis].sum(axis=1), d["mix_register"][:, von:bis].sum(axis=1)
    sc, sr = d["stem_chroma"][:, von:bis].sum(axis=1), d["stem_register"][:, von:bis].sum(axis=1)
    mix = bassmod.slash_note(mc, chord, mr)
    stem = bassmod.slash_note(sc, chord, sr)
    alt = bassmod.MIN_DOMINANCE
    bassmod.MIN_DOMINANCE = 1.5
    try:
        stem15 = bassmod.slash_note(sc, chord, sr)
    finally:
        bassmod.MIN_DOMINANCE = alt
    alt = bassmod.SLASH_ROOT_RATIO
    bassmod.SLASH_ROOT_RATIO = 5.0
    try:
        stem_r5 = bassmod.slash_note(sc, chord, sr)
    finally:
        bassmod.SLASH_ROOT_RATIO = alt
    dom_stem = bassmod.dominant(sc) is not None
    dom_mix = bassmod.dominant(mc) is not None
    root = bassmod.chord_root(chord)
    # Quinte nie als Slash (der Bassist spielt sie, die Harmonie meint den Grundton)
    stem_ohne5 = root if (stem is not None and root is not None and (stem - root) % 12 == 7) else stem
    # Stem nur, wenn der Mix nicht widerspricht (leer oder gleich)
    stem_und_mix = stem if (mix is None or mix == stem) else None
    out = {"Mix": mix, "Stem": stem, "Stem d1.5": stem15,
           "Dom:Stem": mix if dom_stem else None,
           "Dom:Mix": stem if dom_mix else None,
           "Stem r5": stem_r5, "Stem -5": stem_ohne5, "Stem&Mix": stem_und_mix}
    T = d["mix_chroma"].shape[1]
    for name, quelle, pool in (("Mix p1", "mix", 1.0), ("Stem p1", "stem", 1.0), ("Stem p.5", "stem", 0.5)):
        b2 = min(int(round(min(s + pool, e) / F)), T) if s is not None else bis
        b2 = max(b2, von + 2)
        out[name] = bassmod.slash_note(d[quelle + "_chroma"][:, von:b2].sum(axis=1), chord,
                                       d[quelle + "_register"][:, von:b2].sum(axis=1))
    return out


def leer_stat():
    return dict(root_n=0, root_falsch=0, root_leer=0, inv_n=0, inv_gefunden=0,
                inv_falschton=0, inv_leer=0)


def addiere(st, v, rpc, bpc):
    if bpc == rpc:
        st["root_n"] += 1
        st["root_falsch"] += v is not None and v != rpc
        st["root_leer"] += v is None
    else:
        st["inv_n"] += 1
        st["inv_gefunden"] += v == bpc
        st["inv_falschton"] += v is not None and v != bpc
        st["inv_leer"] += v is None


def zeile(st):
    rn, inn = max(st["root_n"], 1), max(st["inv_n"], 1)
    return (f"{st['root_falsch']:3d}/{st['root_n']} = {100 * st['root_falsch'] / rn:4.1f} % | "
            f"{st['root_leer']:4d}/{st['root_n']} = {100 * st['root_leer'] / rn:3.0f} % | "
            f"{st['inv_gefunden']:3d}/{st['inv_n']} = {100 * st['inv_gefunden'] / inn:3.0f} % | "
            f"{st['inv_falschton']:3d}/{st['inv_n']} | {st['inv_leer']:3d}/{st['inv_n']}")


def drucke_tabelle(titel, stats):
    print(f"\n== {titel} ==")
    print(f"{'Variante':10s} | falsche Slashes (Grundton-Seg.) | leer (Grundton-Seg.) | "
          f"Umkehrung gefunden | falscher Ton (Umk.) | leer (Umk.)")
    for v in VARIANTEN:
        print(f"{v:10s} | {zeile(stats[v])}")


def stufe2(rows, detail=False):
    gesamt = {v: leer_stat() for v in VARIANTEN}
    je_artist = {}
    ohne_bass = {v: leer_stat() for v in VARIANTEN}
    je_titel = []
    falsche = {v: [] for v in VARIANTEN}
    stem_anteil_ohne_bass, stem_anteil_mit_bass = [], []
    for row in rows:
        pfad = cache_pfad(row["lab"], row.get("hop", False))
        if not os.path.exists(pfad):
            continue
        d = dict(np.load(pfad))
        T = d["mix_chroma"].shape[1]
        # Stem-Energie relativ zum Mix (RMS-Median) - "erfindet der Stem Bass?"
        anteil = float(np.median(d["stem_rms"]) / max(np.median(d["mix_rms"]), 1e-9))
        (stem_anteil_ohne_bass if row["title"] in OHNE_BASS else stem_anteil_mit_bass).append(
            (anteil, row["title"]))
        st_titel = {v: leer_stat() for v in VARIANTEN}
        for line in open(os.path.join(ISO, row["lab"])):
            p = line.split()
            if len(p) < 3:
                continue
            s, e = float(p[0]) + row["offset"], float(p[1]) + row["offset"]
            if e - s < 1.0 or s < 0:
                continue
            parsed = parse_label(p[2])
            if not parsed:
                continue
            chord, rpc, bpc = parsed
            von, bis = int(round(s / F)), min(int(round(min(s + BASS_POOL_SECONDS, e) / F)), T)
            if bis - von < 2:
                continue
            u = urteile(d, chord, von, bis, s, e)
            for v, pc in u.items():
                addiere(gesamt[v], pc, rpc, bpc)
                addiere(st_titel[v], pc, rpc, bpc)
                addiere(je_artist.setdefault(row["artist"], {w: leer_stat() for w in VARIANTEN})[v],
                        pc, rpc, bpc)
                if row["title"] in OHNE_BASS:
                    addiere(ohne_bass[v], pc, rpc, bpc)
                if bpc == rpc and pc is not None and pc != rpc:
                    falsche[v].append((row["title"], s, chord, NAMES[pc],
                                       INTERVALL.get((pc - rpc) % 12, "andere")))
            if detail and bpc != rpc:
                n = lambda x: "-" if x is None else NAMES[x]
                print(f"    {row['title'][:28]:28s} {s:7.2f}s {chord:7s} GT {NAMES[bpc]:2s}  "
                      + "  ".join(f"{v} {n(u[v]):2s}" for v in ("Mix", "Stem")))
        je_titel.append((row, st_titel))

    print(f"\nTitel ausgewertet: {len(je_titel)}  (Segmente Grundton {gesamt['Mix']['root_n']}, "
          f"Umkehrung {gesamt['Mix']['inv_n']}; Pooling {BASS_POOL_SECONDS:.0f} s ab Onset)")
    drucke_tabelle("Alle Titel", gesamt)
    for artist, st in sorted(je_artist.items()):
        drucke_tabelle(artist, st)
    if ohne_bass["Mix"]["root_n"]:
        drucke_tabelle("Beatles ohne Bassgitarre (" + ", ".join(sorted(OHNE_BASS)) + ")", ohne_bass)

    print("\n== Stem-Energie / Mix-Energie (Median je Titel) ==")
    if stem_anteil_mit_bass:
        a = np.array([x for x, _ in stem_anteil_mit_bass])
        print(f"mit Bass   (n={len(a)}): Median {np.median(a):.3f}, 10 %-Quantil {np.quantile(a, .1):.3f}")
    for anteil, titel in sorted(stem_anteil_ohne_bass):
        print(f"ohne Bass  {anteil:.3f}  {titel}")

    print("\n== Falsche Slashes nach Intervall zum Grundton ==")
    print(f"{'Variante':10s} | " + " | ".join(f"{k:>4s}" for k in ("3", "b3", "5", "b7", "7", "andere")) + " | Titel betroffen")
    for v in VARIANTEN:
        from collections import Counter
        c = Counter(iv for *_, iv in falsche[v])
        titel = len({t for t, *_ in falsche[v]})
        print(f"{v:10s} | " + " | ".join(f"{c.get(k, 0):4d}" for k in ("3", "b3", "5", "b7", "7", "andere")) + f" | {titel}")
    print("\n== Falsche Slashes je Variante (Titel, Zeit, Akkord -> Urteil), Auszug ==")
    for v in ("Mix", "Stem", "Stem -5", "Stem&Mix"):
        print(f"{v} ({len(falsche[v])}):")
        for titel, s, chord, note, iv in falsche[v][:15]:
            print(f"    {titel[:30]:30s} {s:7.2f}s {chord:7s} -> {note} ({iv})")
        if len(falsche[v]) > 15:
            print(f"    ... {len(falsche[v]) - 15} weitere")

    # Titel, bei denen Stem und Mix am weitesten auseinanderliegen (leer auf Grundton)
    print("\n== Titel mit groesstem Unterschied leer(Mix) - leer(Stem) auf Grundton-Segmenten ==")
    diff = []
    for row, st in je_titel:
        n = st["Mix"]["root_n"]
        if n >= 10:
            diff.append((st["Mix"]["root_leer"] - st["Stem"]["root_leer"], n, row["title"],
                         st["Mix"]["root_leer"], st["Stem"]["root_leer"],
                         st["Mix"]["root_falsch"], st["Stem"]["root_falsch"]))
    diff.sort()
    for eintrag in diff[:8]:
        d_, n, t, lm, ls, fm, fs = eintrag
        print(f"  {d_:+4d}  n={n:3d}  leer Mix {lm:3d} Stem {ls:3d}  falsch Mix {fm} Stem {fs}  {t}")
    print("  ...")
    for eintrag in diff[-8:]:
        d_, n, t, lm, ls, fm, fs = eintrag
        print(f"  {d_:+4d}  n={n:3d}  leer Mix {lm:3d} Stem {ls:3d}  falsch Mix {fm} Stem {fs}  {t}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--min-score", type=float, default=0.5)
    ap.add_argument("--artist", default=None)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--nur-auswerten", action="store_true")
    ap.add_argument("--hopweise", action="store_true",
                    help="Trennung hopweise wie live (Kern 0,25 s, Kontext 1,0/0,5 s)")
    args = ap.parse_args()
    rows = [r for r in lese_tabelle()
            if r["score"] >= args.min_score and not r["am_rand"]
            and (args.artist is None or args.artist.lower() in r["artist"].lower())
            and (args.only is None or any(o.lower() in r["title"] for o in args.only))]
    for r in rows:
        r["hop"] = args.hopweise
    print(f"{len(rows)} Titel mit Score >= {args.min_score} und Versatz im Sweep"
          + (" - Trennung HOPWEISE (0,25 s / 1,0 s / 0,5 s)" if args.hopweise else ""))
    if not args.nur_auswerten:
        stufe1(rows, args.workers)
    stufe2(rows, detail=args.detail)


if __name__ == "__main__":
    main()

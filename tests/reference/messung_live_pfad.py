"""Messung: der LIVE-Pfad (_display_loop, hop fuer hop) mit Realaudio gegen
die Isophonics-Referenz - einmal ohne Beat-Tracker (Verfeinerung wie 1.3.1),
einmal mit (Viertel-Snap beim Commit). Gemessen werden die COMMITTETEN
Events, also das, was die Anzeige zeigt: Event-Onsets gegen die annotierten
Wechsel (.lab), committete Beats gegen die .beats (F +-70 ms, Downbeat-F
ueber n == 1). Ergebnisse und Lesart: docs/exploration/beat-tracking-
ergebnisse.md §8.3, Tabelle in README.md hier.

Die Soundkarte ersetzt ein Fake-Loop, der die Datei hopweise durchreicht;
der Beat-Tracker laeuft SYNCHRON im Analyse-Thread - die Simulation ist
schneller als Echtzeit, ein echter Worker-Thread saehe seine Fenster zu
spaet (das ist ein Artefakt der Zeitraffung, nicht des Programms).

Referenzkorrektur: Die Isophonics-Beats DRIFTEN gegen unsere Rips (bis
~0,3 s ueber den Titel). ALIGNMENT unten ist ein linearer Fit je Titel
(Skalierung + Versatz) aus den Modell-Beats, Familie (Versatz modulo
Viertel) am Chroma-Offset der Akkorde verankert (Titelmitte +-0,2 s);
`--fit` rechnet ihn neu. Die Chroma-Offsets (README) werden zum Vergleich
weiter mitgemessen.

Messregeln (seit 2026-09-12, s. README "Was 'kein Event' wirklich war"):
- Ein annotierter WECHSEL ist eine .lab-Zeile, deren Akkord (ohne Basston)
  sich von der Zeile davor unterscheidet. Isophonics splittet Segmente an
  Phrasengrenzen (C nach C) - das sind keine Wechsel. Zeilen, die nur den
  Basston aendern (C nach C/7), werden getrennt gegen das Bass-Feld der
  Events gemessen (`lab_changes`, `bass_treffer`).
- Die Zuordnung Event <-> Wechsel gilt bis zu einem HALBEN SCHLAG (aus den
  GT-Beats, sonst aus den Modell-Beats). Dahinter bis anderthalb Schlaege
  ist das Event auf dem Nachbarschlag, dahinter fehlt es (`timing_stats`).
- Die Simulation laeuft am Dateiende um die Verzoegerung mit Stille nach
  (`lauf(drain=True)`), sonst fehlen die letzten `delay` Sekunden Anzeige.

Aufruf: python tests/reference/messung_live_pfad.py [track ...] [--fit]
"""
import argparse
import sys
import threading
import time
from pathlib import Path

import numpy as np
import librosa

PROJEKT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJEKT))
from jampilot import cli, beats  # noqa: E402

REF = PROJEKT / "tests" / "reference"
OFF = {"let_it_be": 0.08, "eight_days_a_week": -0.15, "something": -0.06}
# GT-Zeit * scale + shift = Audio-Zeit (Fit vom 2026-09-10, Beat-F danach
# 0,96 / 0,98 / 0,86; Something zaehlt das Modell im unannotierten Intro/Outro)
ALIGNMENT = {"let_it_be": (1.00135, -0.090),
             "eight_days_a_week": (1.00210, -0.208),
             "something": (1.00040, -0.100)}
SR = 22050


class FakeLoop:
    xruns, last_status, capture_dropouts = 0, None, None
    recording = record_paused = muted = control_guitar = False
    record_epoch, record_offset_seconds, record_capacity_seconds = 0, 0.0, 0.0

    def __init__(self, y, delay, stop):
        self.y, self.delay_seconds, self._stop = y, delay, stop
        self._pos, self.hop = 0, int(0.25 * SR)
        self.control = []

    @property
    def captured_frames(self):
        self._pos = min(self._pos + self.hop, len(self.y))
        if self._pos >= len(self.y):
            self._stop.set()
        return self._pos

    def audio_ending_at(self, end, length):
        if end - length < 0 or end > len(self.y):
            return None
        return self.y[end - length:end].copy()

    def audible_position(self):
        return self._pos / SR - self.delay_seconds

    heard_position = audible_position

    def set_control_timeline(self, tl):
        self.control = list(tl)


class Sammler:
    def __init__(self):
        self.events, self.beats, self.n = {}, {}, 0

    def publish(self, s):
        self.n += 1
        for e in s["committed"]:
            self.events[e["at"]] = e
        for b in s.get("beats", []):
            self.beats[b["at"]] = b


def f_measure(est, ref, tol=0.07):
    if len(est) == 0 or len(ref) == 0:
        return 0.0
    ref, est = np.asarray(ref), np.asarray(est)
    used, hits = np.zeros(len(ref), bool), 0
    for e in est:
        i = np.argmin(np.abs(ref - e))
        if abs(ref[i] - e) <= tol and not used[i]:
            used[i] = True
            hits += 1
    p, r = hits / len(est), hits / len(ref)
    return 0.0 if hits == 0 else 2 * p * r / (p + r)


# Harte-Intervall -> Halbtoene (fuer den Basston einer /-Angabe)
_INTERVALL = {"1": 0, "2": 2, "b3": 3, "3": 4, "4": 5, "b5": 6, "5": 7,
              "b6": 8, "6": 9, "b7": 10, "7": 11, "b2": 1, "#4": 6, "#5": 8}
_NOTEN = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_ROOT = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _note_index(name):
    i = _ROOT[name[0]]
    for c in name[1:]:
        i += {"#": 1, "b": -1}[c]
    return i % 12


def bass_note(label):
    """'C/3' -> 'E', 'A:min/b7' -> 'G', 'C' -> None (Grundton = kein Slash)."""
    if "/" not in label:
        return None
    root, iv = label.split("/")
    root = root.split(":")[0]
    return _NOTEN[(_note_index(root) + _INTERVALL[iv]) % 12]


def lab_changes(track, korr):
    """Annotierte Wechsel aus <track>.lab, driftkorrigiert.

    chords:    Zeiten, an denen der Akkord (ohne Basston) wechselt
    bass_only: [(Zeit, erwarteter Basston)] - nur der Basston wechselt
    gleich:    Anzahl Zeilen mit demselben Akkord wie davor (Phrasensplit)
    """
    zeilen = [l.split() for l in open(REF / f"{track}.lab") if l.strip()]
    chords, bass_only, gleich, prev = [], [], 0, "N"
    for a, _, c in zeilen:
        if c == "N":
            prev = c
            continue
        akkord = c.split("/")[0].removesuffix(":maj")
        if akkord != prev.split("/")[0].removesuffix(":maj"):
            chords.append(korr(float(a)))
        elif bass_note(c) != bass_note(prev):
            bass_only.append((korr(float(a)), bass_note(c)))
        else:
            gleich += 1
        prev = c
    return {"chords": np.array(chords), "bass_only": bass_only, "gleich": gleich,
            "zeilen": sum(1 for z in zeilen if z[2] != "N")}


def beat_intervall(gt_beats=None, model_beats=None):
    """Median-Schlagabstand in Sekunden: GT-Beats, sonst Modell-Beats, sonst 0,5 s."""
    for b in (gt_beats, model_beats):
        if b is not None and len(b) > 3:
            return float(np.median(np.diff(np.sort(np.asarray(b)))))
    return 0.5


def timing_stats(det, gt_changes, beat=0.5):
    """Event je Wechsel: innerhalb eines halben Schlags -> dt; bis anderthalb
    Schlaege -> Nachbarschlag; sonst fehlt."""
    det = np.asarray(det)
    dts, nachbar, fehlt = [], 0, 0
    for g in gt_changes:
        if len(det) == 0:
            fehlt += 1
            continue
        i = np.argmin(np.abs(det - g))
        d = det[i] - g
        if abs(d) <= 0.5 * beat:
            dts.append(d)
        elif abs(d) <= 1.5 * beat:
            nachbar += 1
        else:
            fehlt += 1
    d = np.array(dts) if dts else np.zeros(0)
    return {"dt": d, "n": len(gt_changes), "nachbar": nachbar, "fehlt": fehlt, "beat": beat}


def timing(det, gt_changes, beat=0.5):
    st = timing_stats(det, gt_changes, beat)
    d = st["dt"]
    if len(d) == 0:
        return f"n={st['n']:3d} kein Event innerhalb eines halben Schlags"
    n = st["n"]
    return (f"n={n:3d} med|dt| {np.median(np.abs(d))*1000:4.0f} ms  "
            f"<=50 {np.mean(np.abs(d) <= .05):3.0%}  <=93 {np.mean(np.abs(d) <= .093):3.0%}  "
            f"med dt {np.median(d)*1000:+4.0f} ms  "
            f"| auf dem Schlag {len(d)/n:3.0%}, Nachbarschlag {st['nachbar']/n:3.0%}, "
            f"fehlt {st['fehlt']/n:3.0%} (Schlag {st['beat']*1000:.0f} ms)")


def bass_treffer(events, bass_only, beat=0.5):
    """Anteil der Nur-Bass-Wechsel, bei denen das Event, das die Stelle
    (bis einen halben Schlag spaeter) abdeckt, den erwarteten Basston traegt."""
    if not bass_only:
        return None
    ev = sorted((e["at"], e.get("b")) for e in events if e["c"] != "-")
    at = np.array([a for a, _ in ev])
    hits = 0
    for g, note in bass_only:
        j = np.searchsorted(at, g + 0.5 * beat, side="right") - 1
        if j >= 0 and ev[j][1] == note:
            hits += 1
    return hits / len(bass_only)


class SyncTracker:
    """Wie BeatTracker, aber das Modell laeuft synchron im Analyse-Thread:
    kein Latenz-Artefakt der Zeitraffung, die Messung gilt dem Algorithmus."""
    ready, error = True, None

    def __init__(self):
        self.grid = beats.BeatGrid()
        self.model = beats.BeatModel()
        self.provider = self.model.provider
        self.runs = 0

    def submit(self, audio, sr, start, end):
        b, d = self.model.run(beats._to_model_rate(audio, sr))
        self.grid.absorb(b, d, start, end)
        self.runs += 1
        return True

    def poll(self):
        return 0

    def stop(self):
        pass


def lauf(y, mit_tracker, delay=5.0, drain=True):
    if drain:
        # Die Anzeige laeuft `delay` s hinter dem Puffer; ohne Nachlauf mit
        # Stille wuerden die letzten `delay` Sekunden des Titels nie gezeigt.
        y = np.concatenate([y, np.zeros(int(delay * SR), dtype=np.float32)])
    stop = threading.Event()
    loop = FakeLoop(y, delay, stop)
    bc = Sammler()
    args = argparse.Namespace(samplerate=SR, delay=delay, record_buffer=0)
    orig = beats.BeatTracker.create
    beats.BeatTracker.create = classmethod(
        (lambda cls: SyncTracker()) if mit_tracker else (lambda cls: None))
    t0 = time.perf_counter()
    try:
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            cli._display_loop(loop, args, bc, stop=stop)
    finally:
        beats.BeatTracker.create = orig
    return bc, time.perf_counter() - t0


def fit_alignment(y, track):
    """Linearer Fit (scale, shift) aus den Modell-Beats der Offline-
    Fensterpipeline; Familie am Chroma-Offset verankert."""
    m = beats.BeatModel()
    gt = np.loadtxt(REF / f"{track}.beats")[:, 0]
    mid = len(y) / SR / 2
    grid = beats.BeatGrid()
    for end in np.arange(10.0, len(y) / SR, 1.0):
        b, d = m.run(y[int((end - 10) * SR):int(end * SR)])
        grid.absorb(b, d, end - 10, end)
        grid.commit(end - 3)
    est = np.array([e["at"] for e in grid.events])
    best = (0.0, 1.0, 0.0)
    for scale in np.arange(0.996, 1.0041, 0.0001):
        for rest in np.arange(-0.2, 0.201, 0.005):
            shift = OFF[track] + rest - (scale - 1) * mid
            f = f_measure(est, gt * scale + shift)
            if f > best[0]:
                best = (f, scale, shift)
    print(f"   Fit: scale {best[1]:.5f} shift {best[2]:+.3f} s (Beat-F {best[0]:.3f})",
          flush=True)
    return best[1], best[2]


def main():
    fit = "--fit" in sys.argv
    tracks = [a for a in sys.argv[1:] if not a.startswith("--")] or list(OFF)
    for track in tracks:
        off = OFF[track]
        y, _ = librosa.load(REF / f"{track}.mp3", sr=SR, mono=True)
        y = y.astype(np.float32)
        gt = np.loadtxt(REF / f"{track}.beats")
        scale, shift = fit_alignment(y, track) if fit else ALIGNMENT[track]
        korr = lambda t: t * scale + shift                   # driftkorrigiert
        gt_beats = korr(gt[:, 0])
        gt_down = gt_beats[gt[:, 1] == 1]
        lab = lab_changes(track, korr)
        gt_changes = lab["chords"]
        gt_changes_alt = lab_changes(track, lambda t: t + off)["chords"]  # Chroma-Offset wie bisher
        beat = beat_intervall(gt_beats)
        print(f"   Korrektur: scale {scale:.5f} shift {shift:+.3f} s "
              f"(Chroma-Offset {off:+.2f})", flush=True)
        print(f"\n== {track}  ({len(y)/SR:.0f} s, {lab['zeilen']} .lab-Zeilen: "
              f"{len(gt_changes)} Akkordwechsel, {len(lab['bass_only'])} nur Bass, "
              f"{lab['gleich']} Phrasensplits; {len(gt_beats)} Beats, Schlag {beat*1000:.0f} ms)",
              flush=True)
        for mit in (False, True):
            bc, dauer = lauf(y, mit)
            ev = np.array(sorted(at for at, e in bc.events.items() if e["c"] != "-"))
            name = "MIT  Tracker" if mit else "OHNE Tracker"
            print(f"  {name}: {len(ev)} Events, {dauer:.0f} s Rechenzeit", flush=True)
            print(f"     vs .lab driftkorrigiert: {timing(ev, gt_changes, beat)}", flush=True)
            print(f"     vs .lab Chroma-Offset:   {timing(ev, gt_changes_alt, beat)}", flush=True)
            bt = bass_treffer(bc.events.values(), lab["bass_only"], beat)
            if bt is not None:
                print(f"     Nur-Bass-Wechsel: Basston getroffen {bt:3.0%} "
                      f"(n={len(lab['bass_only'])})", flush=True)
            if mit:
                b = np.array(sorted(bc.beats))
                d = np.array(sorted(at for at, x in bc.beats.items() if x["n"] == 1))
                unbek = sum(1 for x in bc.beats.values() if x["n"] == 0)
                print(f"    Beats: {len(b)} (GT {len(gt_beats)}), F {f_measure(b, gt_beats):.3f}; "
                      f"Einsen: {len(d)} (GT {len(gt_down)}), Downbeat-F {f_measure(d, gt_down):.3f}; "
                      f"n=0 (Takt unbekannt): {unbek}", flush=True)
                if len(b) > 1:
                    print(f"    Tempo median {60/np.median(np.diff(b)):.1f} bpm "
                          f"(GT {60/np.median(np.diff(gt_beats)):.1f})", flush=True)


if __name__ == "__main__":
    main()

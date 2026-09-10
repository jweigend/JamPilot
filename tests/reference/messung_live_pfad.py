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


def timing(det, gt_changes):
    dts = []
    for g in gt_changes:
        i = np.argmin(np.abs(det - g))
        if abs(det[i] - g) <= 0.5:
            dts.append(det[i] - g)
    d = np.array(dts)
    return (f"n={len(d):3d} med|dt| {np.median(np.abs(d))*1000:4.0f} ms  "
            f"<=50 {np.mean(np.abs(d) <= .05):3.0%}  <=93 {np.mean(np.abs(d) <= .093):3.0%}  "
            f"med dt {np.median(d)*1000:+4.0f} ms")


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


def lauf(y, mit_tracker, delay=5.0):
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
        roh = np.array([float(l.split()[0]) for l in open(REF / f"{track}.lab")
                        if l.split()[2] != "N"])
        gt_changes_alt = roh + off                          # Chroma-Offset wie bisher
        gt_changes = korr(roh)
        print(f"   Korrektur: scale {scale:.5f} shift {shift:+.3f} s "
              f"(Chroma-Offset {off:+.2f})", flush=True)
        print(f"\n== {track}  ({len(y)/SR:.0f} s, {len(gt_changes)} annotierte Wechsel, "
              f"{len(gt_beats)} Beats)", flush=True)
        for mit in (False, True):
            bc, dauer = lauf(y, mit)
            ev = np.array(sorted(at for at, e in bc.events.items() if e["c"] != "-"))
            name = "MIT  Tracker" if mit else "OHNE Tracker"
            print(f"  {name}: {len(ev)} Events, {dauer:.0f} s Rechenzeit", flush=True)
            print(f"     vs .lab driftkorrigiert: {timing(ev, gt_changes)}", flush=True)
            print(f"     vs .lab Chroma-Offset:   {timing(ev, gt_changes_alt)}", flush=True)
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

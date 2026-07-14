"""Selbsttest ohne Audiohardware: synthetische Akkorde -> Erkennung pruefen.

Zwei Stufen:
1. "sauber":      nur der Akkord (Grundton + Obertoene)
2. "realistisch": Akkord + Schlagzeug (Rauschimpulse) + Melodiestimme

Vergleicht den FFT-Fallback (V1) mit der librosa-Pipeline (HPSS + CQT +
Bass-Chroma), um Verbesserungen der Erkennung messbar zu machen.

Zwei Gruppen von Faellen, und die zweite gab es lange nicht:

  GRUNDSTELLUNGEN   Der Bass spielt den Grundton. Das ist der bequeme Fall.
  UMKEHRUNGEN       Der Bass spielt einen anderen Akkordton (C/E, F/A, Bm/D).

Solange nur Grundstellungen geprueft wurden, war der Selbsttest blind fuer den
teuersten Fehler der Akkorderkennung: den Grundton auf die Bassnote zu ziehen.
Ein BASS_BONUS tat genau das und machte aus C/E ein Em - der Test sah 8/8, weil
er den Fall nie stellte. Ein Massstab, der die unangenehme Frage nicht stellt,
misst nichts. Die Umkehrungen stellen sie.
"""

import os

import numpy as np

from . import bass as bassmodul
from .chroma import HAVE_LIBROSA, analyze_window, chroma_from_audio
from .chords import match_chord

SAMPLERATE = 48000
CHORD_SECONDS = 2.0


def _tone(freq: float, seconds: float, harmonics: int = 5) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLERATE)) / SAMPLERATE
    signal = np.zeros_like(t)
    for h in range(1, harmonics + 1):
        signal += (1.0 / h) * np.sin(2 * np.pi * freq * h * t)
    return signal


def _midi_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12.0)


def _chord(midi_notes, seconds: float = CHORD_SECONDS) -> np.ndarray:
    signal = sum(_tone(_midi_hz(m), seconds) for m in midi_notes)
    return (signal / len(midi_notes)).astype(np.float32)


def _drums(seconds: float, rng) -> np.ndarray:
    """Rauschimpulse alle 250 ms - grob wie HiHat/Snare."""
    n = int(seconds * SAMPLERATE)
    out = np.zeros(n, dtype=np.float32)
    hit = int(0.25 * SAMPLERATE)
    length = int(0.06 * SAMPLERATE)
    for start in range(0, n - length, hit):
        burst = rng.standard_normal(length) * np.exp(-np.linspace(0.0, 8.0, length))
        out[start : start + length] += burst.astype(np.float32)
    return out


def _melody(root_midi: int, seconds: float) -> np.ndarray:
    """Achtel-Lauf ueber der Dur-Pentatonik - enthaelt akkordfremde Toene."""
    steps = [0, 2, 4, 7, 9, 7, 4, 2]
    note_len = seconds / len(steps)
    parts = [_tone(_midi_hz(root_midi + 24 + s), note_len, harmonics=3) for s in steps]
    return np.concatenate(parts).astype(np.float32)


TEST_CASES = [
    ("C", [36, 48, 52, 55, 60]),    # Bass C2 + C3 E3 G3 C4
    ("G", [31, 43, 47, 50, 55]),
    ("Am", [33, 45, 48, 52, 57]),
    ("F", [29, 41, 45, 48, 53]),
    ("Dm", [38, 50, 53, 57, 62]),
    ("E", [28, 40, 44, 47, 52]),
    ("C7", [36, 48, 52, 55, 58]),
    ("Bm", [35, 47, 50, 54, 59]),
]

# Umkehrungen: unten ein Akkordton, der NICHT der Grundton ist. Gesetzt wie eine
# Band es spielt - der Bass nimmt die Umkehrungsnote einmal, tief; die Gitarre
# greift den Akkord in Grundstellung darueber. (Die Bassnote oben nochmal zu
# verdoppeln waere ein anderer Test: dann zieht die Tonklasse das Chroma so weit
# zu sich, dass schon die Tonklassen-MENGE mehrdeutig wird. So spielt das aber
# niemand.)
#
# Erwartet wird der volle Slash-Name: Akkord aus dem Chroma, Bassnote gemessen.
INVERSIONS = [
    ("C/E",  [28, 48, 52, 55]),     # E1 | C3 E3 G3
    ("C/G",  [31, 48, 52, 55]),
    ("F/A",  [33, 53, 57, 60]),     # A1 | F3 A3 C4
    ("F/C",  [36, 53, 57, 60]),
    ("G/B",  [35, 55, 59, 62]),
    ("G/D",  [38, 55, 59, 62]),
    ("Dm/F", [29, 50, 53, 57]),
    ("Am/E", [28, 45, 48, 52]),
    ("Em/G", [31, 52, 55, 59]),     # teilt G und B mit G-Dur
    ("Bm/D", [38, 47, 50, 54]),
]


def _realistic(notes, rng, root_pc: int | None = None) -> np.ndarray:
    # Die Melodie laeuft ueber dem AKKORD-Grundton. Bei Umkehrungen ist der
    # nicht notes[0]: unten liegt dann ein anderer Akkordton.
    if root_pc is None:
        root_pc = notes[0] % 12
    mix = (
        1.0 * _chord(notes)
        + 0.8 * _drums(CHORD_SECONDS, rng)
        + 0.5 * _melody(root_pc + 48, CHORD_SECONDS)
    )
    return (mix / np.abs(mix).max() * 0.8).astype(np.float32)


def _detect_fft(audio: np.ndarray) -> str:
    return match_chord(chroma_from_audio(audio, SAMPLERATE)).name


def _detect_full(audio: np.ndarray) -> str:
    analysis = analyze_window(audio, SAMPLERATE)
    return match_chord(analysis.chroma, cqt=analysis.cqt).name


def _detect_slash(audio: np.ndarray) -> str:
    """Akkord + gemessene Bassnote - was die Anzeige tatsaechlich zeigt.

    Beide muessen ueber denselben Zeitraum reden: das Chroma wird nur aus der
    juengeren Fensterhaelfte gepoolt, also darf auch der Bass nur von dort
    kommen (genau wie in cli.py).
    """
    analysis = analyze_window(audio, SAMPLERATE)
    chord = match_chord(analysis.chroma, cqt=analysis.cqt).name
    frames = analysis.bass_frames
    juengere = frames[:, frames.shape[1] // 2:] if frames is not None else None
    return bassmodul.slash(chord, bassmodul.name(bassmodul.dominant(juengere)))


def _fenster_pruefen() -> bool | None:
    """Laesst sich das Kontrollfenster bauen? True/False - oder None (kein Qt).

    Das ist die einzige Aussage ueber die Oberflaeche, die eine Maschine OHNE
    Bildschirm treffen kann - und ausgerechnet sie deckt den Fehler ab, der beim
    Buendeln wirklich passiert: Qt findet sein Plattform-Plugin nicht (unter
    macOS "cocoa", unter Linux "xcb") und der Prozess stirbt beim ersten Fenster.
    Ein Bundle, das startet, aber kein Fenster oeffnen KANN, ist genau die Sorte
    Fehler, die man sonst erst auf dem Rechner des Nutzers findet.

    Gebaut wird gegen die Offscreen-Plattform: Sie braucht keinen Desktop und
    keine angemeldete Sitzung - beides hat ein CI-Runner nicht. Damit ist
    bewiesen, dass Qt geladen und das Fenster konstruiert werden kann. NICHT
    bewiesen ist, dass es auf einem echten Desktop erscheint; das kann nur ein
    echter Start zeigen.
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        return None                     # ohne Qt laeuft JamPilot rein im Terminal

    from types import SimpleNamespace

    from . import gui

    app = QApplication.instance() or QApplication([])
    leer = SimpleNamespace(running=False, muted=False, delay_seconds=4.0,
                           lead=0.0, status="stopped", fehler=None,
                           start=lambda: None, stop=lambda: None,
                           toggle_mute=lambda: False)
    fenster = gui.Fenster(leer, "http://127.0.0.1:8765/")
    fenster.nachziehen()
    ok = fenster.zustand.text() == "Stopped"
    fenster.close()
    app.processEvents()
    return ok


def run() -> bool:
    rng = np.random.default_rng(42)
    print(f"Selftest: {len(TEST_CASES)} root-position chords, "
          f"{len(INVERSIONS)} inversions @ {SAMPLERATE} Hz, "
          f"librosa: {'yes' if HAVE_LIBROSA else 'NO (FFT fallback only)'}\n")

    print("  Root position - the bass plays the root")
    header = f"  {'':6s} {'FFT clean':>12s} {'FFT noisy':>12s}"
    if HAVE_LIBROSA:
        header += f" {'CQT clean':>12s} {'CQT noisy':>12s}"
    print(header)

    scores = {"fft_clean": 0, "fft_real": 0, "cqt_clean": 0, "cqt_real": 0}
    for expected, notes in TEST_CASES:
        clean = _chord(notes)
        real = _realistic(notes, rng)

        row = {"fft_clean": _detect_fft(clean), "fft_real": _detect_fft(real)}
        if HAVE_LIBROSA:
            row["cqt_clean"] = _detect_full(clean)
            row["cqt_real"] = _detect_full(real)

        line = f"  {expected:6s}"
        for key in ("fft_clean", "fft_real", "cqt_clean", "cqt_real"):
            if key not in row:
                continue
            hit = row[key] == expected
            scores[key] += hit
            line += f" {row[key] + (' +' if hit else ' -'):>12s}"
        print(line)

    total = len(TEST_CASES)
    print(f"\n  FFT: clean {scores['fft_clean']}/{total}, "
          f"noisy {scores['fft_real']}/{total}")
    if HAVE_LIBROSA:
        print(f"  CQT: clean {scores['cqt_clean']}/{total}, "
              f"noisy {scores['cqt_real']}/{total}")

    if not HAVE_LIBROSA:
        # Ohne librosa gibt es kein Tiefband-Chroma und damit keine Bassnote -
        # Umkehrungen sind nicht messbar. Der FFT-Fallback kann C/E nicht von C
        # unterscheiden, und das ist ehrlicher, als es zu behaupten.
        print("\n  Inversions: skipped (no librosa, no bass measurement)")
        return scores["fft_clean"] == total

    # Umkehrungen. Der Akkord kommt aus dem Chroma, die Bassnote aus dem
    # Tiefband - erst zusammen ergeben sie C/E statt C oder (frueher) Em.
    print("\n  Inversions - the bass plays a chord tone that is NOT the root")
    print(f"  {'':6s} {'CQT clean':>12s} {'CQT noisy':>12s}")

    inv = {"clean": 0, "noisy": 0}
    for expected, notes in INVERSIONS:
        root_pc = bassmodul.chord_root(expected.split("/")[0])
        got = {
            "clean": _detect_slash(_chord(notes)),
            "noisy": _detect_slash(_realistic(notes, rng, root_pc)),
        }
        line = f"  {expected:6s}"
        for key in ("clean", "noisy"):
            hit = got[key] == expected
            inv[key] += hit
            line += f" {got[key] + (' +' if hit else ' -'):>12s}"
        print(line)

    inv_total = len(INVERSIONS)
    print(f"\n  Inversions: clean {inv['clean']}/{inv_total}, "
          f"noisy {inv['noisy']}/{inv_total}")

    # Die Oberflaeche - so weit es ohne Bildschirm geht. Fehlt Qt, laeuft
    # JamPilot im Terminal; das ist kein Fehler. Ist Qt DA, muss das Fenster sich
    # aber bauen lassen: Genau daran scheitert ein Bundle, dem das
    # Plattform-Plugin fehlt.
    fenster = _fenster_pruefen()
    if fenster is None:
        print("\n  Control window: skipped (no Qt - terminal only)")
    elif fenster:
        print("\n  Control window: builds (Qt loads, offscreen)")
    else:
        print("\n  Control window: FAILED to build")

    return (scores["cqt_clean"] == total and scores["cqt_real"] >= total - 1
            and inv["clean"] == inv_total and inv["noisy"] >= inv_total - 1
            and fenster is not False)

"""Selbsttest ohne Audiohardware: synthetische Akkorde -> Erkennung pruefen.

Zwei Stufen:
1. "sauber":      nur der Akkord (Grundton + Obertoene)
2. "realistisch": Akkord + Schlagzeug (Rauschimpulse) + Melodiestimme

Vergleicht den FFT-Fallback (V1) mit der librosa-Pipeline (HPSS + CQT +
Bass-Chroma), um Verbesserungen der Erkennung messbar zu machen.
"""

import numpy as np

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


def _realistic(notes, rng) -> np.ndarray:
    root = notes[0]
    mix = (
        1.0 * _chord(notes)
        + 0.8 * _drums(CHORD_SECONDS, rng)
        + 0.5 * _melody(root % 12 + 48, CHORD_SECONDS)
    )
    return (mix / np.abs(mix).max() * 0.8).astype(np.float32)


def _detect_fft(audio: np.ndarray) -> str:
    return match_chord(chroma_from_audio(audio, SAMPLERATE)).name


def _detect_full(audio: np.ndarray) -> str:
    analysis = analyze_window(audio, SAMPLERATE)
    return match_chord(analysis.chroma, analysis.bass).name


def run() -> bool:
    rng = np.random.default_rng(42)
    print(f"Selbsttest: {len(TEST_CASES)} Akkorde @ {SAMPLERATE} Hz, "
          f"librosa: {'ja' if HAVE_LIBROSA else 'NEIN (nur FFT-Fallback)'}\n")

    header = f"  {'':6s} {'FFT sauber':>12s} {'FFT real.':>12s}"
    if HAVE_LIBROSA:
        header += f" {'CQT sauber':>12s} {'CQT real.':>12s}"
    print(header)

    scores = {"fft_clean": 0, "fft_real": 0, "cqt_clean": 0, "cqt_real": 0}
    for expected, notes in TEST_CASES:
        clean = _chord(notes)
        real = _realistic(notes, rng)

        row = {}
        row["fft_clean"] = _detect_fft(clean)
        row["fft_real"] = _detect_fft(real)
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
    print(f"\n  FFT: sauber {scores['fft_clean']}/{total}, "
          f"realistisch {scores['fft_real']}/{total}")
    if HAVE_LIBROSA:
        print(f"  CQT: sauber {scores['cqt_clean']}/{total}, "
              f"realistisch {scores['cqt_real']}/{total}")
        return scores["cqt_clean"] == total and scores["cqt_real"] >= total - 1
    return scores["fft_clean"] == total

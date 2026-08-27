"""Chroma-Extraktion: Audiofenster -> 12-dimensionaler Tonklassen-Vektor.

Zwei Verfahren (siehe docs/exploration/first-draft.md, "Audioverarbeitung"):

1. `analyze_window` (Standard): librosa-Pipeline mit harmonischer Trennung
   (HPSS, entfernt Drums/Percussion) und Constant-Q-Chroma (logarithmische
   Frequenzaufloesung, trifft auch tiefe Grundtoene). Liefert zusaetzlich ein
   Bass-Chroma zur Grundton-Gewichtung.
2. `chroma_from_audio`: leichtgewichtiger FFT-Fallback ohne librosa.
"""

from typing import NamedTuple

import numpy as np

try:
    import librosa

    HAVE_LIBROSA = True
except ImportError:  # Fallback: reine FFT-Pipeline
    HAVE_LIBROSA = False

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Analyse laeuft intern auf reduzierter Rate - reicht bis weit ueber die
# hoechsten relevanten Teiltoene und spart CQT-Rechenzeit.
ANALYSIS_SR = 22050

# Zeitraster der CQT-Frames. Die Frames fallen ohnehin an; sie festzuhalten
# statt sie nur wegzumitteln ist die Grundlage der Onset-Bestimmung: der
# Akkordwechsel wird darin auf ~23 ms genau lokalisiert, statt aus dem
# Analysetakt (~0.5 s) geschaetzt zu werden.
FRAME_HOP = 512
FRAME_SECONDS = FRAME_HOP / ANALYSIS_SR

# Frequenzbereich fuer die Analyse: unterhalb ~55 Hz dominiert Rumpeln,
# oberhalb ~2 kHz dominieren Obertoene, die das Chroma verschmieren.
FMIN = 55.0
FMAX = 2000.0


class WindowAnalysis(NamedTuple):
    chroma: np.ndarray               # gepoolt: entscheidet, WELCHER Akkord klingt
    bass: np.ndarray | None          # gepoolt (nur noch fuer die Tonart-Statistik)
    frames: np.ndarray | None        # 12 x F Frame-Chroma: WANN der Akkord einsetzt
    # 12 x F im Tiefband. Wurde frueher berechnet und weggeworfen - dabei steht
    # genau hier, WELCHE NOTE unten liegt (bass.py). Das ist die Information,
    # die der Akkordname nicht enthaelt: bei C/E steht im Akkord ein C.
    bass_frames: np.ndarray | None

    @property
    def cqt(self) -> bool:
        """Lief die librosa-Pipeline? Ihr Chroma ist sauberer als das rohe FFT -
        die Akkordwahl kommt damit mit einer kleineren Komplexitaetsmarge aus."""
        return self.frames is not None


def chroma_from_audio(samples: np.ndarray, samplerate: int) -> np.ndarray:
    """Berechnet einen normalisierten Chroma-Vektor aus einem Mono-Fenster.

    Rueckgabe: np.ndarray shape (12,), Summe 1.0 - oder Nullvektor bei Stille.
    """
    n = len(samples)
    if n < 256:
        return np.zeros(12)

    windowed = samples * np.hanning(n)
    spectrum = np.abs(np.fft.rfft(windowed))
    freqs = np.fft.rfftfreq(n, 1.0 / samplerate)

    mask = (freqs >= FMIN) & (freqs <= FMAX)
    spectrum = spectrum[mask]
    freqs = freqs[mask]

    # Log-Kompression daempft dominante Grundtoene gegenueber Obertoenen.
    spectrum = np.log1p(spectrum)

    midi = 69.0 + 12.0 * np.log2(freqs / 440.0)
    pitch_class = np.round(midi).astype(int) % 12

    # Bins nahe der Halbtonmitte zaehlen voll, Bins dazwischen kaum.
    center_distance = midi - np.round(midi)
    weight = np.cos(np.pi * center_distance) ** 2

    chroma = np.zeros(12)
    np.add.at(chroma, pitch_class, spectrum * weight)

    total = chroma.sum()
    if total < 1e-9:
        return np.zeros(12)
    return chroma / total


def _cqt_frames(y: np.ndarray, fmin_note: str, n_octaves: int) -> np.ndarray:
    # librosa warnt bei kurzen Fenstern ueber intern verkuerzte FFTs in den
    # tiefen Oktaven - fuer Chroma-Zwecke unkritisch.
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="n_fft=.*too large")
        return librosa.feature.chroma_cqt(
            y=y,
            sr=ANALYSIS_SR,
            fmin=librosa.note_to_hz(fmin_note),
            n_octaves=n_octaves,
            bins_per_octave=36,
            hop_length=FRAME_HOP,
        )


def _pool(frames: np.ndarray) -> np.ndarray:
    # Median ueber die juengere Haelfte der Frames: robust gegen Ausreisser,
    # reagiert trotzdem auf Akkordwechsel im Fenster.
    recent = frames[:, frames.shape[1] // 2 :]
    pooled = np.median(recent, axis=1)
    total = pooled.sum()
    return pooled / total if total > 1e-9 else np.zeros(12)


def analyze_window(samples: np.ndarray, samplerate: int) -> WindowAnalysis:
    """Chroma, Bass-Chroma und beide Frame-Chromas eines Fensters (>= ~1.5s).

    Alle Felder ausser `chroma` sind None im FFT-Fallback; ohne
    `bass_frames` gibt es keine Bassnote.
    """
    if not HAVE_LIBROSA:
        return WindowAnalysis(chroma_from_audio(samples, samplerate),
                              None, None, None)

    y = np.ascontiguousarray(samples, dtype=np.float32)
    if samplerate != ANALYSIS_SR:
        y = librosa.resample(y, orig_sr=samplerate, target_sr=ANALYSIS_SR)

    # Harmonische Trennung: Percussion (breitbandig, kurz) wird entfernt,
    # nur der tonale Anteil geht in die Akkordanalyse.
    y = librosa.effects.harmonic(y, margin=4.0)

    frames = _cqt_frames(y, "C2", 6)       # 65 Hz .. ~4.2 kHz: Akkordklang
    bass_frames = _cqt_frames(y, "C1", 3)  # 32 .. ~260 Hz: wo der Grundton liegt
    # Beide Frame-Chromas gehen raus: das obere sagt, WANN der Akkord wechselt,
    # das untere, WELCHE Note dabei unten liegt. Das Bass-Chroma wurde bisher
    # gepoolt und weggeworfen - dabei kostet es nichts, es aufzuheben.
    return WindowAnalysis(_pool(frames), _pool(bass_frames), frames, bass_frames)


def rms(samples: np.ndarray) -> float:
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples**2)))

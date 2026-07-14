"""Chroma-Extraktion: Audiofenster -> 12-dimensionaler Tonklassen-Vektor.

Zwei Verfahren (siehe docs/exploration/first-draft.md, "Audioverarbeitung"):

1. `analyze_window` (Standard): librosa-Pipeline mit harmonischer Trennung
   (HPSS, entfernt Drums/Percussion) und Constant-Q-Chroma (logarithmische
   Frequenzaufloesung, trifft auch tiefe Grundtoene). Liefert zusaetzlich ein
   Bass-Chroma zur Grundton-Gewichtung.
2. `chroma_from_audio`: leichtgewichtiger FFT-Fallback ohne librosa.
"""

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

# Frequenzbereich fuer die Analyse: unterhalb ~55 Hz dominiert Rumpeln,
# oberhalb ~2 kHz dominieren Obertoene, die das Chroma verschmieren.
FMIN = 55.0
FMAX = 2000.0


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


def analyze_window(samples: np.ndarray, samplerate: int):
    """Chroma + Bass-Chroma eines Analysefensters (>= ~1.5s empfohlen).

    Rueckgabe: (chroma, bass_chroma) - bass_chroma ist None im FFT-Fallback.
    Beide Vektoren sind auf Summe 1 normalisiert (bzw. Nullvektor bei Stille).
    """
    if not HAVE_LIBROSA:
        return chroma_from_audio(samples, samplerate), None

    y = np.ascontiguousarray(samples, dtype=np.float32)
    if samplerate != ANALYSIS_SR:
        y = librosa.resample(y, orig_sr=samplerate, target_sr=ANALYSIS_SR)

    # Harmonische Trennung: Percussion (breitbandig, kurz) wird entfernt,
    # nur der tonale Anteil geht in die Akkordanalyse.
    y = librosa.effects.harmonic(y, margin=4.0)

    def _pooled(fmin_note: str, n_octaves: int) -> np.ndarray:
        # librosa warnt bei kurzen Fenstern ueber intern verkuerzte FFTs
        # in den tiefen Oktaven - fuer Chroma-Zwecke unkritisch.
        import warnings

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="n_fft=.*too large")
            return _pooled_inner(fmin_note, n_octaves)

    def _pooled_inner(fmin_note: str, n_octaves: int) -> np.ndarray:
        frames = librosa.feature.chroma_cqt(
            y=y,
            sr=ANALYSIS_SR,
            fmin=librosa.note_to_hz(fmin_note),
            n_octaves=n_octaves,
            bins_per_octave=36,
        )
        # Median ueber die juengere Haelfte der Frames: robust gegen
        # Ausreisser, reagiert trotzdem auf Akkordwechsel im Fenster.
        recent = frames[:, frames.shape[1] // 2 :]
        pooled = np.median(recent, axis=1)
        total = pooled.sum()
        return pooled / total if total > 1e-9 else np.zeros(12)

    chroma = _pooled("C2", 6)      # 65 Hz .. ~4.2 kHz: Akkordklang
    bass = _pooled("C1", 3)        # 32 .. ~260 Hz: wo der Grundton liegt
    return chroma, bass


def warmup(samplerate: int = 48000, window_seconds: float = 1.5):
    """Einmalige librosa/numba-Initialisierung (~2-3s) vorziehen.

    Muss VOR dem Start des Audio-Streams laufen, sonst blockiert der erste
    Analyse-Aufruf den Audio-Callback und verursacht einen Dropout.
    """
    if HAVE_LIBROSA:
        rng = np.random.default_rng(0)
        dummy = (rng.standard_normal(int(window_seconds * samplerate)) * 0.01)
        analyze_window(dummy.astype(np.float32), samplerate)


def rms(samples: np.ndarray) -> float:
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples**2)))

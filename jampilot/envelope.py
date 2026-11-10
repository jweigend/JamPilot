"""Huellkurve der Musik unter dem Laufband - WANN wird angeschlagen.

Der Chip sagt, WAS erklingt; wann genau ein Akkord anzuzeigen ist, entscheidet
die Pipeline, und jede Entscheidung dort ist ein Trade-off zwischen zu viel
(jeder Bassanschlag) und zu wenig (ein Wechsel geht unter). Die Huellkurve
entscheidet nichts: Sie zeigt die Anschlaege, wie sie im Audio liegen, und der
Spieler nimmt mit, was er braucht - oder ignoriert sie.

Der Witz ist der Delay: Das Audio der naechsten Sekunden liegt schon im
Puffer, bevor es hoerbar wird. Die Kurve zeigt also die KOMMENDEN Anschlaege,
die auf die JETZT-Linie zulaufen wie die Chips.

Zwei Kurven je Block (12,5 ms):
  full - RMS des ganzen Mixes (gemastert meist ein Ziegel, Snare und Kick)
  bass - RMS des Tiefbands 30..250 Hz, wo Bass und Akkordgrund anschlagen

Zeitachse sind Stream-Frames wie ueberall; die Bloecke beginnen bei einem
Vielfachen der Blocklaenge, damit jeder Hop nahtlos an den vorigen anschliesst,
auch wenn die Analyse mal einen Hop ueberspringt. Fehlt Audio (Puffer
ueberholt), wird mit Nullen aufgefuellt statt die Achse zu verschieben.
"""

from __future__ import annotations

import math

import numpy as np

# Bloecke je Analyse-Hop (0,25 s): 20 -> 12,5 ms. Fein genug, dass ein
# Anschlag als Kante erscheint; grob genug, dass ein Snapshot (rund 6 s
# Fenster) unter 10 kB bleibt.
BLOCKS_PER_HOP = 20

# Tiefband wie das Bass-Chroma (chroma.analyze_window: 32..260 Hz).
BASS_LOW_HZ = 30.0
BASS_HIGH_HZ = 250.0


def bandpass_filter(samplerate: int, low_hz: float = BASS_LOW_HZ,
                    high_hz: float = BASS_HIGH_HZ):
    """Butterworth 2. Ordnung als SOS - ein IIR mit Zustand, damit die
    Bloecke zweier Hops nahtlos aneinanderpassen. (Eine FFT-Maske klingelte
    an jeder Fensterkante, hopweise anders als am Stueck.) scipy kommt mit
    librosa ohnehin mit."""
    from scipy.signal import butter
    return butter(2, [low_hz, high_hz], btype="bandpass", fs=samplerate, output="sos")


def lowpass(signal: np.ndarray, samplerate: int) -> np.ndarray:
    """Tiefband eines Signals am Stueck (Tests, Offline)."""
    from scipy.signal import sosfilt
    return sosfilt(bandpass_filter(samplerate), np.asarray(signal, dtype=np.float64))


def block_rms(signal: np.ndarray, block_frames: int) -> np.ndarray:
    n = len(signal) // block_frames
    if n == 0:
        return np.zeros(0)
    blocks = signal[: n * block_frames].reshape(n, block_frames)
    return np.sqrt(np.mean(blocks.astype(np.float64) ** 2, axis=1))


class Envelope:
    def __init__(self, samplerate: int, hop_frames: int,
                 blocks_per_hop: int = BLOCKS_PER_HOP):
        self.samplerate = int(samplerate)
        self.block_frames = max(1, int(hop_frames) // blocks_per_hop)
        self.block_seconds = self.block_frames / self.samplerate
        self._sos = bandpass_filter(self.samplerate)
        self._zi = None                  # Filterzustand ueber Hops hinweg
        self._start: int | None = None   # Stream-Frame des ersten gehaltenen Blocks
        self._done: int | None = None    # Stream-Frame, bis zu dem die Kurve reicht
        self.full: list[float] = []
        self.bass: list[float] = []

    # -- Aufbau -------------------------------------------------------------

    def add(self, audio: np.ndarray, end_frame: int) -> None:
        """`audio` (mono) endet exakt bei Stream-Frame `end_frame`."""
        bf = self.block_frames
        audio_start = end_frame - len(audio)
        if self._done is None:
            # Erster Block auf die Blockraster-Linie legen.
            first = -(-max(audio_start, 0) // bf) * bf
            self._start = self._done = first
        if end_frame - self._done < bf:
            return
        new_start = self._done
        if new_start < audio_start:
            # Luecke: Audio schon aus dem Puffer - Nullen, Achse bleibt.
            luecke = -(-(audio_start - new_start) // bf)
            self.full.extend([0.0] * luecke)
            self.bass.extend([0.0] * luecke)
            new_start += luecke * bf
            self._zi = None              # Filter nach der Luecke frisch
            self._done = new_start
            if end_frame - new_start < bf:
                return
        n_blocks = (end_frame - new_start) // bf
        lo = new_start - audio_start
        chunk = np.asarray(audio[lo: lo + n_blocks * bf], dtype=np.float64)
        if chunk.ndim > 1:
            chunk = chunk.mean(axis=1)
        from scipy.signal import sosfilt, sosfilt_zi
        if self._zi is None:
            self._zi = sosfilt_zi(self._sos) * 0.0
        tief, self._zi = sosfilt(self._sos, chunk, zi=self._zi)
        self.full.extend(float(v) for v in block_rms(chunk, bf))
        self.bass.extend(float(v) for v in block_rms(tief, bf))
        self._done = new_start + n_blocks * bf

    # -- Lesen --------------------------------------------------------------

    @property
    def start_seconds(self) -> float | None:
        return None if self._start is None else self._start / self.samplerate

    @property
    def end_seconds(self) -> float | None:
        return None if self._done is None else self._done / self.samplerate

    def window(self, lo: float, hi: float) -> dict | None:
        """Bloecke, die [lo, hi] Sekunden beruehren, als kompakter Snapshot
        {t0, dt, full, bass} - None, wenn nichts davon vorliegt."""
        if self._start is None or not self.full:
            return None
        dt = self.block_seconds
        t0 = self._start / self.samplerate
        i0 = max(0, math.floor((lo - t0) / dt))
        i1 = min(len(self.full), math.ceil((hi - t0) / dt) + 1)
        if i1 <= i0:
            return None
        return {
            "t0": round(t0 + i0 * dt, 4),
            "dt": round(dt, 6),
            "full": [round(v, 5) for v in self.full[i0:i1]],
            "bass": [round(v, 5) for v in self.bass[i0:i1]],
        }

    def prune(self, heard_pos: float, rueckhalt: float = 2.0) -> None:
        """Vergangenes vergessen - gemessen an der HOERBAREN Position, nicht
        weiter zurueck als der Mitschnitt reicht (wie EventLedger.prune)."""
        if self._start is None:
            return
        grenze = heard_pos - max(rueckhalt, 2.0)
        drop = int((grenze - self._start / self.samplerate) / self.block_seconds)
        drop = max(0, min(drop, len(self.full)))
        if drop:
            del self.full[:drop]
            del self.bass[:drop]
            self._start += drop * self.block_frames

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
    """Zwei Kurven auf EINEM Blockraster ab `_start`: `full` (Mix) und `bass`.
    Jede Kurve reicht so weit, wie sie Werte hat - Block i liegt bei
    `_start + i * block_frames`, fuer beide. Die Bass-Kurve kommt entweder aus
    dem Bandpass (in `add`, wie der Mix) oder, mit `separated=True`, aus
    `add_bass()` mit dem getrennten Stem (stems.py) - der laeuft asynchron und
    darf hinter dem Mix zurueckliegen, die Kurve ist dann einfach kuerzer.
    Luecken (Audio schon aus dem Puffer, Hop ausgelassen) werden mit Nullen
    gefuellt, nie durch Verschieben der Achse."""

    def __init__(self, samplerate: int, hop_frames: int,
                 blocks_per_hop: int = BLOCKS_PER_HOP, separated: bool = False):
        self.samplerate = int(samplerate)
        self.block_frames = max(1, int(hop_frames) // blocks_per_hop)
        self.block_seconds = self.block_frames / self.samplerate
        self.separated = separated
        self._sos = bandpass_filter(self.samplerate)
        self._zi = None                  # Filterzustand ueber Hops hinweg
        self._start: int | None = None   # Stream-Frame von Block 0 (beide Kurven)
        self.full: list[float] = []
        self.bass: list[float] = []

    # -- Aufbau -------------------------------------------------------------

    def _done(self, curve: list[float]) -> int:
        return self._start + len(curve) * self.block_frames

    def _place(self, curve: list[float], audio_len: int, end_frame: int):
        """Neue Bloecke fuer `curve` aus Audio, das bei `end_frame` endet:
        Luecke vor dem Audio mit Nullen fuellen; liefert (Offset im Audio,
        Anzahl neuer Bloecke, Luecke gefuellt?) oder None, wenn nichts Neues
        dazukommt."""
        bf = self.block_frames
        audio_start = end_frame - audio_len
        if self._start is None:
            # Block 0 auf die Blockraster-Linie legen.
            self._start = -(-max(audio_start, 0) // bf) * bf
        done = self._done(curve)
        if end_frame - done < bf:
            return None
        luecke = False
        if done < audio_start:
            n = -(-(audio_start - done) // bf)
            curve.extend([0.0] * n)
            done += n * bf
            luecke = True
            if end_frame - done < bf:
                return None
        return done - audio_start, (end_frame - done) // bf, luecke

    def add(self, audio: np.ndarray, end_frame: int) -> None:
        """`audio` (mono) endet exakt bei Stream-Frame `end_frame`: Mix-Kurve,
        und ohne Stem-Trennung auch die Bass-Kurve aus dem Bandpass."""
        bf = self.block_frames
        audio = np.asarray(audio, dtype=np.float64)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        placed = self._place(self.full, len(audio), end_frame)
        if placed is not None:
            lo, n_blocks, _ = placed
            self.full.extend(float(v) for v in block_rms(audio[lo: lo + n_blocks * bf], bf))
        if self.separated:
            return
        placed = self._place(self.bass, len(audio), end_frame)
        if placed is None:
            return
        lo, n_blocks, luecke = placed
        from scipy.signal import sosfilt, sosfilt_zi
        if luecke or self._zi is None:
            self._zi = sosfilt_zi(self._sos) * 0.0      # nach der Luecke frisch
        tief, self._zi = sosfilt(self._sos, audio[lo: lo + n_blocks * bf], zi=self._zi)
        self.bass.extend(float(v) for v in block_rms(tief, bf))

    def add_bass(self, stem: np.ndarray, end_frame: int) -> None:
        """Getrennter Bass-Stem (mono), endet bei Stream-Frame `end_frame`."""
        bf = self.block_frames
        stem = np.asarray(stem, dtype=np.float64)
        placed = self._place(self.bass, len(stem), end_frame)
        if placed is None:
            return
        lo, n_blocks, _ = placed
        self.bass.extend(float(v) for v in block_rms(stem[lo: lo + n_blocks * bf], bf))

    # -- Lesen --------------------------------------------------------------

    @property
    def start_seconds(self) -> float | None:
        return None if self._start is None else self._start / self.samplerate

    @property
    def end_seconds(self) -> float | None:
        """Ende der Mix-Kurve (die Bass-Kurve kann dahinter zurueckliegen)."""
        return None if self._start is None else self._done(self.full) / self.samplerate

    @property
    def bass_end_seconds(self) -> float | None:
        return None if self._start is None else self._done(self.bass) / self.samplerate

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
            # Beide Kurven um dieselben Bloecke: ist die Bass-Kurve kuerzer,
            # wird sie leer und setzt beim naechsten add_bass mit Nullen ab
            # dem neuen Block 0 wieder auf - die Achse bleibt gemeinsam.
            del self.full[:drop]
            del self.bass[:drop]
            self._start += drop * self.block_frames

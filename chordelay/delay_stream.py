"""Verzoegertes Audio-Loopback: Eingang -> Ringpuffer -> Ausgang.

Der Eingang (Systemaudio-Monitor bzw. Loopback-Device) wird unveraendert um
eine feste Zeit verzoegert ausgegeben. Parallel wird das frische (noch nicht
hoerbare) Signal fuer die Akkordanalyse bereitgestellt - daraus entsteht der
Vorlauf der Anzeige.
"""

import threading

import numpy as np
import sounddevice as sd


class DelayedLoopback:
    def __init__(
        self,
        input_device,
        output_device,
        delay_seconds: float,
        samplerate: int = 48000,
        blocksize: int = 2048,
        channels: int = 2,
        analysis_seconds: float = 2.0,
    ):
        self.samplerate = samplerate
        self.channels = channels
        self.delay_seconds = delay_seconds

        delay_frames = max(blocksize, int(round(delay_seconds * samplerate)))
        # Ringpuffer exakt in Delay-Laenge: an der Schreibposition wird erst
        # der alte Wert ausgegeben, dann der neue geschrieben.
        self._ring = np.zeros((delay_frames, channels), dtype=np.float32)
        self._pos = 0

        # Separater Puffer mit dem juengsten Mono-Signal fuer die Analyse.
        analysis_frames = int(analysis_seconds * samplerate)
        self._analysis = np.zeros(analysis_frames, dtype=np.float32)
        self._analysis_lock = threading.Lock()
        self._frames_seen = 0

        # latency="high": die Akkordanalyse (~230ms CPU) haelt den GIL
        # zeitweise - grosszuegige Puffer verhindern Audio-Dropouts.
        self._stream = sd.Stream(
            device=(input_device, output_device),
            samplerate=samplerate,
            blocksize=blocksize,
            channels=channels,
            dtype="float32",
            latency="high",
            callback=self._callback,
        )
        self.status_messages: list[str] = []

    def _callback(self, indata, outdata, frames, time_info, status):
        if status:
            self.status_messages.append(str(status))

        ring = self._ring
        n = len(ring)
        pos = self._pos
        end = pos + frames

        if end <= n:
            outdata[:] = ring[pos:end]
            ring[pos:end] = indata
        else:
            first = n - pos
            outdata[:first] = ring[pos:]
            outdata[first:] = ring[: end - n]
            ring[pos:] = indata[:first]
            ring[: end - n] = indata[first:]
        self._pos = end % n

        mono = indata.mean(axis=1)
        with self._analysis_lock:
            self._analysis = np.roll(self._analysis, -frames)
            self._analysis[-frames:] = mono
            self._frames_seen += frames

    @property
    def output_latency(self) -> float:
        """Zusaetzliche Pufferzeit der Soundkarte hinter dem Ringpuffer."""
        return float(self._stream.latency[1])

    @property
    def captured_seconds(self) -> float:
        """Wie viel Audio seit dem Start eingegangen ist."""
        return self._frames_seen / self.samplerate

    def latest_audio(self, seconds: float) -> np.ndarray:
        """Die juengsten `seconds` Mono-Samples (frisch, noch nicht hoerbar)."""
        frames = int(seconds * self.samplerate)
        with self._analysis_lock:
            return self._analysis[-frames:].copy()

    def start(self):
        self._stream.start()

    def stop(self):
        self._stream.stop()
        self._stream.close()

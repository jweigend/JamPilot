"""Verzoegertes Audio-Loopback: Eingang -> Ringpuffer -> Ausgang.

Der Eingang (Systemaudio-Monitor bzw. Loopback-Device) wird unveraendert um
eine feste Zeit verzoegert ausgegeben. Parallel wird das frische (noch nicht
hoerbare) Signal fuer die Akkordanalyse bereitgestellt - daraus entsteht der
Vorlauf der Anzeige.

Zeitbasis ist durchgehend die Stream-Position in Frames (nicht die Wanduhr):
`audio_ending_at` liefert ein Fenster, das exakt an einer angeforderten
Position endet, und `audible_position` sagt, welche Position gerade aus dem
Lautsprecher kommt. Beides zusammen macht die Anzeige unabhaengig davon, wie
lange eine Analyse dauert oder wann der Analysethread drankommt.
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
        analysis_seconds: float = 3.0,
    ):
        self.samplerate = samplerate
        self.channels = channels

        self.delay_frames = max(blocksize, int(round(delay_seconds * samplerate)))
        self.delay_seconds = self.delay_frames / samplerate
        # Ringpuffer exakt in Delay-Laenge: an der Schreibposition wird erst
        # der alte Wert ausgegeben, dann der neue geschrieben.
        self._ring = np.zeros((self.delay_frames, channels), dtype=np.float32)
        self._pos = 0

        # Zirkularer Mono-Puffer mit dem juengsten Signal fuer die Analyse.
        # Zirkular (nicht np.roll) - roll allokiert bei jedem Callback ein
        # neues Array, das gehoert nicht in einen Audio-Callback.
        self._analysis = np.zeros(int(analysis_seconds * samplerate), dtype=np.float32)
        self._write = 0
        self._lock = threading.Lock()
        self._frames_seen = 0

        # Anker fuer die Ausgabeuhr: (Stream-Position, PortAudio-DAC-Zeit).
        self._dac_anchor: tuple[int, float] | None = None

        # latency="high": die Akkordanalyse (~280ms CPU) haelt den GIL
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
        # Zaehler statt Liste: eine wachsende Liste im Audio-Callback wuerde
        # ausgerechnet dann Speicher belegen und allokieren, wenn der Stream
        # ohnehin schon klemmt. `status` baut sounddevice pro Callback neu -
        # die Referenz zu halten kostet nichts, str() passiert beim Ausgeben.
        self.xruns = 0
        self.last_status = None

    def _callback(self, indata, outdata, frames, time_info, status):
        if status:
            self.xruns += 1
            self.last_status = status

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

        # Was gerade in outdata geschrieben wurde, ist genau das Material, das
        # n Frames vor diesem Block eingelesen wurde - und es erklingt zur
        # gemessenen DAC-Zeit. Das ist die einzige Stelle, an der Eingang und
        # Lautsprecher hart verkoppelt sind: exakter als jede Latenzschaetzung.
        self._dac_anchor = (self._frames_seen - n, float(time_info.outputBufferDacTime))

        mono = indata.mean(axis=1)
        buf = self._analysis
        size = len(buf)
        with self._lock:
            write = self._write
            stop = write + frames
            if stop <= size:
                buf[write:stop] = mono
            else:
                head = size - write
                buf[write:] = mono[:head]
                buf[: stop - size] = mono[head:]
            self._write = stop % size
            self._frames_seen += frames

    @property
    def captured_frames(self) -> int:
        """Wie viele Frames seit dem Start eingegangen sind."""
        return self._frames_seen

    @property
    def captured_seconds(self) -> float:
        return self._frames_seen / self.samplerate

    @property
    def output_latency(self) -> float:
        """Geschaetzte Pufferzeit der Soundkarte hinter dem Ringpuffer."""
        return float(self._stream.latency[1])

    def audible_position(self) -> float:
        """Stream-Position (Sekunden), die JETZT aus dem Lautsprecher kommt.

        Nutzt PortAudios DAC-Zeitstempel. Meldet die Hardware unbrauchbare
        Zeiten (manche Host-APIs tun das), faellt die Rechnung auf die
        geschaetzte Ausgabelatenz zurueck.
        """
        fallback = self.captured_seconds - self.delay_seconds - self.output_latency

        anchor = self._dac_anchor
        if anchor is None:
            return fallback
        anchor_frames, anchor_dac = anchor
        try:
            now = float(self._stream.time)
        except Exception:
            return fallback

        position = anchor_frames / self.samplerate + (now - anchor_dac)
        # Plausibilitaet: die hoerbare Position muss hinter dem Eingang liegen,
        # mindestens um die Ringpufferlaenge und hoechstens um 2s mehr.
        behind = self.captured_seconds - position
        if not (self.delay_seconds - 0.05 <= behind <= self.delay_seconds + 2.0):
            return fallback
        return position

    def audio_ending_at(self, end_frame: int, length_frames: int) -> np.ndarray | None:
        """Mono-Fenster, das exakt bei Stream-Position `end_frame` endet.

        None, wenn das Fenster nicht (mehr) vollstaendig im Puffer liegt.
        """
        buf = self._analysis
        size = len(buf)
        with self._lock:
            lag = self._frames_seen - end_frame  # schon eingelesen nach Fensterende
            if lag < 0 or lag + length_frames > size:
                return None
            stop = (self._write - lag) % size
            start = (stop - length_frames) % size
            if start < stop:
                return buf[start:stop].copy()
            return np.concatenate((buf[start:], buf[:stop]))

    def start(self):
        self._stream.start()

    def stop(self):
        self._stream.stop()
        self._stream.close()

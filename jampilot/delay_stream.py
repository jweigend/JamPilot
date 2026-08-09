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

from .control_guitar import PLAYBACK_GAIN

# Unter dieser Block-RMS gilt der Eingang als still (dieselbe Schwelle, ab der
# auch die Erkennung "kein Akkord" sagt - chords.SILENCE_RMS; hier als eigene
# Konstante, damit der Audio-Callback keine Analyse-Module importiert).
COUNTIN_SILENCE_RMS = 1e-4


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
        capture=None,
    ):
        self.samplerate = samplerate
        self.channels = channels
        # Woher der Eingang kommt: normalerweise aus demselben Vollduplex-Stream,
        # der auch ausgibt. `capture` setzt an dessen Stelle eine fremde Quelle
        # (unter Windows der WASAPI-Loopback eines stummgeschalteten Ausgangs) -
        # dann laeuft nur noch die AUSGABE ueber PortAudio, und der Callback
        # holt sich seinen Block vorher ab. Alles danach ist Zeile fuer Zeile
        # dasselbe: Ringpuffer, Einzaehler, Analyse, Stummschaltung.
        self._capture = capture

        self.delay_frames = max(blocksize, int(round(delay_seconds * samplerate)))
        self.delay_seconds = self.delay_frames / samplerate
        # Ringpuffer exakt in Delay-Laenge: an der Schreibposition wird erst
        # der alte Wert ausgegeben, dann der neue geschrieben.
        self._ring = np.zeros((self.delay_frames, channels), dtype=np.float32)
        self._pos = 0

        # Der Einzaehler. Startet die Quelle nach laengerer Stille (Programm-
        # start ist der Spezialfall davon), liegen zwischen Lautsprecher und
        # neuem Material genau delay Sekunden Stille - und die sehen aus wie
        # ein Programm, das nicht funktioniert. In diese Luecke legt der
        # Callback drei Toene: einer pro Restsekunde (3 - 2 - 1, der letzte
        # betont), dann kommt die Musik. Die Klaenge sind vorberechnet
        # (Abstand vor der Musik in Frames, Mono-Welle); gemischt wird im
        # Callback nur.
        self._count_beeps = tuple(
            (k * samplerate,
             self._render_beep(*((0.14, 0.32) if k == 1 else (0.09, 0.22))))
            for k in (3, 2, 1))
        self._count_events: tuple[tuple[int, np.ndarray], ...] = ()
        # Der Stream beginnt "nach langer Stille": Musik, die schon beim Start
        # laeuft oder kurz danach beginnt, wird genauso eingezaehlt.
        self._silent_frames = self.delay_frames

        # Zirkularer Mono-Puffer mit dem juengsten Signal fuer die Analyse.
        # Zirkular (nicht np.roll) - roll allokiert bei jedem Callback ein
        # neues Array, das gehoert nicht in einen Audio-Callback.
        self._analysis = np.zeros(int(analysis_seconds * samplerate), dtype=np.float32)
        self._write = 0
        self._lock = threading.Lock()
        self._frames_seen = 0

        # Anker fuer die Ausgabeuhr: (Stream-Position, PortAudio-DAC-Zeit).
        self._dac_anchor: tuple[int, float] | None = None

        # STUMM, nicht pausiert - und das ist keine Wortklauberei, sondern der
        # Entwurf. Der Ringpuffer laeuft weiter, die Analyse laeuft weiter, die
        # Quelle laeuft weiter; nur der Lautsprecher schweigt. Beim Aufheben ist
        # man deshalb sofort wieder synchron zur Quelle. Wuerde man stattdessen
        # den Puffer anhalten - also wirklich PAUSIEREN -, waere das in Wahrheit
        # "Verzoegerung vergroessern": Man kaeme mit jeder Sekunde eine Sekunde
        # weiter hinter die Quelle, und der Vorlauf, der ganze Sinn des
        # Programms, waere hinueber.
        self._muted = False
        self._control_guitar = False
        self._control_timeline = ()
        # Immutable Snapshot: Der Analyse-Thread ersetzt das Tupel atomar, der
        # Audio-Callback liest es ohne Lock. Ein Event ist (Onset-Frame, Stereo).
        self._control_events: tuple[tuple[int, np.ndarray], ...] = ()

        # Hart auf Null zu schalten ist ein Sprung im Signal, und den hoert man
        # als Knacken. Also in ~15 ms aus- und wieder einblenden. Die Rampe wird
        # hier einmal vorberechnet: im Audio-Callback wird nicht allokiert.
        self._fade_frames = max(int(0.015 * samplerate), 1)
        self._gain = 1.0
        self._ramp = np.arange(blocksize, dtype=np.float32)
        self._scratch = np.empty(blocksize, dtype=np.float32)

        # latency="high": die Akkordanalyse (~280ms CPU) haelt den GIL
        # zeitweise - grosszuegige Puffer verhindern Audio-Dropouts.
        if capture is None:
            self._stream = sd.Stream(
                device=(input_device, output_device),
                samplerate=samplerate,
                blocksize=blocksize,
                channels=channels,
                dtype="float32",
                latency="high",
                callback=self._callback,
            )
        else:
            # Einmal vorbereitet, im Callback nur noch gefuellt: In einem
            # Audio-Callback wird nicht allokiert.
            self._indata = np.zeros((blocksize, channels), dtype=np.float32)
            self._stream = sd.OutputStream(
                device=output_device,
                samplerate=samplerate,
                blocksize=blocksize,
                channels=channels,
                dtype="float32",
                latency="high",
                callback=self._callback_ziehend,
            )
        # Zaehler statt Liste: eine wachsende Liste im Audio-Callback wuerde
        # ausgerechnet dann Speicher belegen und allokieren, wenn der Stream
        # ohnehin schon klemmt. `status` baut sounddevice pro Callback neu -
        # die Referenz zu halten kostet nichts, str() passiert beim Ausgeben.
        self.xruns = 0
        self.last_status = None

    def _render_beep(self, dauer: float, amp: float) -> np.ndarray:
        """Ein Ton des Einzaehlers (Mono). Sinus statt Sprache: braucht keine
        Stimmdaten im Bundle und ist neutral zu jeder Tonart, die folgt."""
        t = np.arange(int(dauer * self.samplerate)) / self.samplerate
        beep = (amp * np.sin(2 * np.pi * 880.0 * t)).astype(np.float32)
        # An- und Abstiegsrampe gegen Knacken an den Tonraendern.
        fade = max(min(int(0.005 * self.samplerate), len(beep) // 2), 1)
        beep[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        beep[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
        return beep

    def _callback_ziehend(self, outdata, frames, time_info, status):
        """Nur-Ausgabe-Fassung: den Eingangsblock erst holen, dann wie immer.

        Die fremde Quelle liefert IMMER `frames` Frames - fehlendes Material
        ergaenzt sie mit Stille, statt zu warten. Ein Audio-Callback, der auf
        einen anderen Thread wartet, reisst den ganzen Ausgabestream mit.
        """
        block = self._indata[:frames]
        if frames > len(self._indata):        # sollte nie passieren
            block = np.zeros((frames, self.channels), dtype=np.float32)
        self._capture.read_into(block)
        self._callback(block, outdata, frames, time_info, status)

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

        mono = indata.mean(axis=1)

        # Einzaehler ausloesen: Beginnt nach Stille wieder Signal, wird auf
        # dessen Ankunft hin eingezaehlt - die Toene liegen k Sekunden VOR der
        # Startposition auf der Stream-Zeitachse und fallen damit genau in die
        # Verzoegerungsluecke. Die Stille muss mindestens pufferlang gewesen
        # sein: Nur dann ist der Lautsprecher bis zur Ankunft wirklich stumm.
        # Ein Break im Song oder die Luecke zwischen zwei Titeln zaehlen NICHT
        # ein - dort spielt der Ausgang noch altes Material.
        if float(np.sqrt(np.mean(mono * mono))) < COUNTIN_SILENCE_RMS:
            self._silent_frames += frames
        else:
            if self._silent_frames >= n:
                start = self._frames_seen
                self._count_events = tuple(
                    (start - abstand, klang)
                    for abstand, klang in self._count_beeps)
            self._silent_frames = 0

        # Faellige Toene mischen - dieselbe Ueberlappungslogik wie bei den
        # Kontrollanschlaegen unten. Zu frueh geplante Toene (Delay kuerzer
        # als der Abstand) liegen vor der Ausgabeposition und entfallen von
        # selbst. Nach dem letzten Ton kostet der Zweig nur den Leertest.
        if self._count_events:
            played_start = self._frames_seen - n
            played_end = played_start + frames
            for onset, klang in self._count_events:
                overlap_start = max(played_start, onset)
                overlap_end = min(played_end, onset + len(klang))
                if overlap_start < overlap_end:
                    dst = overlap_start - played_start
                    src = overlap_start - onset
                    count = overlap_end - overlap_start
                    outdata[dst : dst + count] += klang[src : src + count, None]
            letzter_onset, letzter_klang = self._count_events[-1]
            if played_start >= letzter_onset + len(letzter_klang):
                self._count_events = ()

        # Kontrollanschlaege liegen auf derselben Stream-Zeitachse wie das
        # Original. `frames_seen - delay_frames` ist genau der erste Frame, der
        # in diesem Callback hoerbar wird. Nur wenige Timeline-Events werden
        # geschnitten; Synthese/Allokation passiert vorher im Analyse-Thread.
        if self._control_guitar:
            # Platz fuer die Kontrollgitarre schaffen: Nur in diesem bewusst
            # aktivierten Diagnosemodus wird das Original abgesenkt. Ohne
            # Kontrollgitarre bleibt die Wiedergabe bit-identisch wie vorher.
            outdata *= PLAYBACK_GAIN
            output_start = self._frames_seen - n
            output_end = output_start + frames
            for onset, sound in self._control_events:
                overlap_start = max(output_start, onset)
                overlap_end = min(output_end, onset + len(sound))
                if overlap_start < overlap_end:
                    dst = overlap_start - output_start
                    src = overlap_start - onset
                    count = overlap_end - overlap_start
                    outdata[dst:dst + count] += sound[src:src + count]
            np.clip(outdata, -1.0, 1.0, out=outdata)

        # Stummschalten NACH dem Ringpuffer: Der Puffer wird weiter befuellt und
        # weiter ausgelesen, nur was rausgeht, wird leise. Damit bleibt die
        # Zeitrechnung unangetastet - `audible_position` gilt stumm genauso, und
        # der Vorlauf stimmt sofort wieder, sobald der Ton zurueckkommt.
        ziel = 0.0 if self._muted else 1.0
        if self._gain != ziel:
            schritt = frames / self._fade_frames
            neu = (min(self._gain + schritt, ziel) if ziel > self._gain
                   else max(self._gain - schritt, ziel))
            # rampe = gain + (neu - gain) * i/frames, in-place: kein malloc hier.
            rampe = self._scratch[:frames]
            np.multiply(self._ramp[:frames], (neu - self._gain) / frames, out=rampe)
            rampe += self._gain
            outdata *= rampe[:, None]
            self._gain = neu
        elif ziel == 0.0:
            outdata[:] = 0.0

        # Was gerade in outdata geschrieben wurde, ist genau das Material, das
        # n Frames vor diesem Block eingelesen wurde - und es erklingt zur
        # gemessenen DAC-Zeit. Das ist die einzige Stelle, an der Eingang und
        # Lautsprecher hart verkoppelt sind: exakter als jede Latenzschaetzung.
        self._dac_anchor = (self._frames_seen - n, float(time_info.outputBufferDacTime))

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
    def muted(self) -> bool:
        return self._muted

    def toggle_mute(self) -> bool:
        """Stumm an/aus. Gibt den neuen Zustand zurueck.

        Ein einzelnes bool, vom Audio-Callback nur gelesen - dafuer braucht es
        kein Lock: In CPython ist die Zuweisung atomar, und ein Callback, der den
        Wechsel eine Blockgrenze spaeter sieht, blendet eben 40 ms spaeter aus.
        Ein Lock im Audio-Callback waere der teurere Fehler.
        """
        self._muted = not self._muted
        return self._muted

    @property
    def control_guitar(self) -> bool:
        return self._control_guitar

    def toggle_control_guitar(self) -> bool:
        self._control_guitar = not self._control_guitar
        if self._control_guitar:
            self._render_control_timeline()
        else:
            self._control_events = ()
        return self._control_guitar

    def set_control_timeline(self, timeline):
        """Timeline-Snapshot in fertig gerenderte Kontrollanschlaege wandeln."""
        self._control_timeline = tuple(timeline)
        if self._control_guitar:
            self._render_control_timeline()

    def _render_control_timeline(self):
        from .control_guitar import render

        events = []
        for item in self._control_timeline:
            onset, chord = item[:2]
            safe = tuple(item[2]) if len(item) > 2 and item[2] is not None else None
            sound = render(chord, self.samplerate, safe)
            if sound is not None:
                events.append((int(round(onset * self.samplerate)), sound))
        self._control_events = tuple(events)

    @property
    def capture_dropouts(self) -> tuple[int, int] | None:
        """(Unterlaeufe, Ueberlaeufe) der fremden Quelle - None, wenn keine.

        Zwei unabhaengige Uhren (Mitschnitt und Ausgabe) laufen langsam
        auseinander; wer spaeter einem Knacken nachgeht, soll nicht raten
        muessen, ob es von hier kam.
        """
        if self._capture is None:
            return None
        return (self._capture.unterlaeufe, self._capture.ueberlaeufe)

    @property
    def captured_frames(self) -> int:
        """Wie viele Frames seit dem Start eingegangen sind."""
        return self._frames_seen

    @property
    def captured_seconds(self) -> float:
        return self._frames_seen / self.samplerate

    @property
    def output_latency(self) -> float:
        """Geschaetzte Pufferzeit der Soundkarte hinter dem Ringpuffer.

        `latency` ist beim Vollduplex-Stream ein Paar (rein, raus), beim reinen
        Ausgabestream ein einzelner Wert - gemeint ist beide Male derselbe.
        """
        latenz = self._stream.latency
        return float(latenz[1] if isinstance(latenz, (tuple, list)) else latenz)

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

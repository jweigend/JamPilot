"""Mitschnitt hinter dem fertigen Mix: aufnehmen, anhalten, zurueck, wieder vor.

WOFUER: Wer einen Akkordwechsel nicht mitbekommen hat, will ihn noch einmal
hoeren - ohne die Quelle anzufassen. Die Taste R schaltet den Mitschnitt ein,
danach springen die Pfeiltasten von Akkord zu Akkord, P haelt an, R schaltet
wieder aus und stellt alles zurueck.

WO: Diese Stufe sitzt GANZ HINTEN, hinter der Verzoegerungsstufe und hinter
allem, was ihr Callback dem Signal noch beimischt (Einzaehler,
Kontrollgitarre) - und vor der Stummschaltung. Aufgezeichnet wird also genau
das Signal, das der Lautsprecher bekommen haette; beim Zurueckgehen hoert man
es Ton fuer Ton wieder, Einzaehler und Kontrollgitarre inklusive. Stummes
bleibt draussen: Wer stumm schaltet und spaeter zurueckspult, will nicht
Stille wiederfinden.

WARUM EIN MODUS: Solange nicht aufgezeichnet wird, tut diese Stufe NICHTS -
`process()` kehrt um, bevor es ein Byte anfasst. Die Ausgabe ist dann bitgleich
zu einem Lauf ohne Mitschnitt, und die Anzeige rechnet auf derselben Uhr wie
vorher. Das ist die Zusage, die den Modus tragbar macht: Wer R nie drueckt,
bekommt das Programm von vorher, nicht ein Programm mit einem schlafenden
zweiten Zeitstrahl.

WARUM GETRENNT: Die Verzoegerungsstufe (delay_stream) bleibt davon voellig
unberuehrt - ihr Ringpuffer ist weiter exakt `delay` lang, ihre Zeitrechnung
weiter konstant, und die ganze Analyse samt Commit-Grenze rechnet unveraendert
auf dieser konstanten Basis weiter. Waere stattdessen die Verzoegerung selbst
gewachsen, muesste die Zeitleiste bis zu 30 Minuten Zukunft offenhalten - und
der Merge, der sie jeden Hop neu aufbaut, arbeitet quadratisch in ihrer
Laenge. Ein zweiter Puffer kostet Speicher; eine variable Verzoegerung haette
die Analyse gekostet.

ZEITBASIS: Der Mitschnitt fuehrt keine eigene Uhr. `process()` bekommt bei
jedem Block die Stream-Position der Verzoegerungsstufe mit und schreibt sie als
`_written` fort - beide Zaehler sind damit per Konstruktion dieselbe Zahl, und
`play_position_frames` liegt exakt auf der Zeitachse, auf der auch die
Akkorde liegen. Ein eigener Zaehler, den man beim Einschalten "angleicht",
waere um genau den Block danebengelegen, der zwischen Angleichen und erstem
Callback vergeht.
"""

import ctypes
import sys
import threading

import numpy as np

# Voreinstellung: 30 Minuten. Das ist eine LP-Seite - ein komplettes
# traditionelles Album am Stueck, ohne dass der Mitschnitt reisst.
DEFAULT_MINUTES = 30.0

# Darunter lohnt der Puffer nicht mehr: Wer eine Strophe zurueck will, braucht
# mehr als ein paar Sekunden. Reicht der Speicher nicht einmal dafuer, laeuft
# JamPilot lieber ganz ohne Mitschnitt weiter (siehe `plan`).
MIN_MINUTES = 1.0

# Soviel freien Arbeitsspeicher lassen wir dem System stehen. Der Mitschnitt
# ist Komfort; ihn auf Kosten des restlichen Rechners zu reservieren, waere der
# falsche Handel - erst recht, weil daneben ein Browser die Anzeige zeigt.
HEADROOM_BYTES = 768 * 1024 * 1024

# Ueberblendung an jeder Sprungstelle (Pause, Fortsetzen, Sprung). Ein harter
# Schnitt im Signal ist ein Knacken - dieselbe Begruendung wie beim Fade der
# Stummschaltung in delay_stream.
FADE_SECONDS = 0.015


def verfuegbarer_speicher() -> int | None:
    """Frei verfuegbarer Arbeitsspeicher in Bytes - None, wenn unbekannt.

    Kein psutil: Das waere eine weitere Abhaengigkeit im Bundle fuer eine
    einzige Zahl. Gefragt ist ausdruecklich der VERFUEGBARE Speicher, nicht der
    freie - unter Linux ist der Unterschied der Seitencache, und der gibt bei
    Bedarf nach. Wo wir es nicht sicher wissen (BSD, exotische Systeme), geben
    wir None zurueck: Dann wird nicht geraten, sondern nur der Versuch gewagt
    und ein MemoryError sauber behandelt.
    """
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/meminfo") as f:
                for zeile in f:
                    if zeile.startswith("MemAvailable:"):
                        return int(zeile.split()[1]) * 1024
        except OSError:
            return None
        return None

    if sys.platform == "win32":
        class _Status(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        try:
            status = _Status()
            status.dwLength = ctypes.sizeof(_Status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys)
        except Exception:
            return None
        return None

    if sys.platform == "darwin":
        # vm_stat statt sysctl: hw.memsize ist der VERBAUTE Speicher und sagt
        # nichts darueber, wieviel davon noch zu haben ist. Frei ist, was weder
        # belegt noch komprimiert ist - "inactive" zaehlt mit, das gibt macOS
        # unter Druck her.
        import re
        import subprocess
        try:
            aus = subprocess.run(["vm_stat"], capture_output=True, text=True,
                                 timeout=2.0)
        except (OSError, subprocess.SubprocessError):
            return None
        if aus.returncode != 0:
            return None
        seite = 4096
        kopf = re.search(r"page size of (\d+) bytes", aus.stdout)
        if kopf:
            seite = int(kopf.group(1))
        summe = 0
        for name in ("Pages free", "Pages inactive", "Pages speculative"):
            treffer = re.search(rf"{name}:\s+(\d+)", aus.stdout)
            if treffer:
                summe += int(treffer.group(1))
        return summe * seite if summe else None

    return None


def bytes_pro_sekunde(samplerate: int, channels: int) -> int:
    return samplerate * channels * 4        # float32


def plan(minutes: float, samplerate: int, channels: int,
         verfuegbar: int | None = None) -> tuple[float, str | None]:
    """Wieviele Minuten Mitschnitt sind vertretbar? (minuten, hinweis)

    Gibt (0.0, grund) zurueck, wenn nicht einmal MIN_MINUTES hineinpassen -
    dann laeuft JamPilot ohne Mitschnitt weiter. Das ist Absicht: Der
    Mitschnitt ist ein Zusatz, kein Betriebsmittel. Lieber ohne R-Taste
    spielen als gar nicht starten.
    """
    if minutes <= 0:
        return 0.0, None
    if verfuegbar is None:
        verfuegbar = verfuegbarer_speicher()
    if verfuegbar is None:
        return minutes, None                # unbekannt: Versuch wagen

    proSekunde = bytes_pro_sekunde(samplerate, channels)
    budget = verfuegbar - HEADROOM_BYTES
    if budget < MIN_MINUTES * 60 * proSekunde:
        return 0.0, (
            f"not enough free memory for the record buffer "
            f"({verfuegbar / 2**20:.0f} MB available) - "
            f"record mode (R) is off, everything else works")
    passen = budget / (60 * proSekunde)
    if passen >= minutes:
        return minutes, None
    gekuerzt = max(MIN_MINUTES, float(int(passen)))
    return gekuerzt, (
        f"record buffer shortened to {gekuerzt:.0f} min "
        f"({minutes:.0f} min would need "
        f"{minutes * 60 * proSekunde / 2**20:.0f} MB, "
        f"{verfuegbar / 2**20:.0f} MB free)")


class RecordBuffer:
    """Ringpuffer mit eigener Leseposition hinter dem fertigen Mix.

    Zwei Zeiger, nicht einer - das ist der ganze Unterschied zur
    Verzoegerungsstufe: Dort liegt der Abstand zwischen Schreiben und Lesen
    fest (er IST die Verzoegerung), hier ist er beweglich und heisst `offset`.

    Der Speicher wird im Konstruktor angefasst, nicht nur angefordert. `np.zeros`
    gibt unter Linux eine Zusage, keine Seiten; die Seiten kaemen erst beim
    ersten Schreiben - also mitten im Audio-Callback, und ein Seitenfehler ueber
    600 MB waere dort ein Aussetzer. Angelegt wird darum abseits des Callbacks
    (die Engine tut es in einem Hintergrundthread beim ersten R), und erst der
    fertige Puffer wird eingehaengt.
    """

    def __init__(self, samplerate: int, channels: int, minutes: float,
                 blocksize: int = 2048):
        self.samplerate = samplerate
        self.channels = channels
        frames = int(round(minutes * 60 * samplerate))
        self._ring = np.zeros((frames, channels), dtype=np.float32)
        # Seiten wirklich holen (s. Docstring). In Stuecken, damit kein
        # zweites Array in dieser Groesse entsteht.
        schritt = max(samplerate, 1) * 60
        for start in range(0, frames, schritt):
            self._ring[start:start + schritt] = 0.0

        self.capacity_frames = frames
        self.capacity_seconds = frames / samplerate
        # ZWEI Zeiger, beide absolut in Stream-Frames der Verzoegerungsstufe -
        # und der Versatz ist ihre DIFFERENZ, kein eigener Zustand. Das ist der
        # Grund fuer diese Form: Waere `offset` ein eigenes Feld, muesste der
        # Audio-Callback es bei jeder Pause fortschreiben - und zwar genau dann,
        # wenn der Nutzer am ehesten springt (anhalten, dann mit den Pfeilen die
        # Stelle suchen). Zwei Threads, die dasselbe Feld lesen und
        # zurueckschreiben, verlieren gelegentlich einen Tastendruck. So
        # schreibt der Callback waehrend der Pause GAR NICHTS, und der Versatz
        # waechst trotzdem - weil die Schreibkante davonlaeuft und die
        # Leseposition steht.
        self._written = 0            # bis hierhin ist aufgezeichnet
        self._play_end = 0           # hier endet der naechste auszugebende Block
        self._record_start = None    # erster Frame DIESER Aufnahme (None: noch keiner)
        self._recording = False
        self._paused = False
        self._lock = threading.Lock()

        # Sprungstellen werden ueberblendet, nicht geschnitten. Die Rampe ist
        # vorberechnet: im Audio-Callback wird nicht allokiert.
        self._fade_frames = min(max(int(FADE_SECONDS * samplerate), 1), blocksize)
        self._ramp = np.linspace(0.0, 1.0, self._fade_frames,
                                 dtype=np.float32)[:, None]
        self._scratch = np.empty((blocksize, channels), dtype=np.float32)
        # Von welcher Leseposition ueberblendet wird. -1 = keine Sprungstelle.
        self._blend_from = -1
        # Zaehlt jede Unstetigkeit der hoerbaren Zeit (Pause, Sprung, Modus
        # an/aus). Die Anzeige stellt daran ihre Uhr NEU, statt sie sanft
        # nachzuziehen - sanftes Nachziehen ist fuer Drift gebaut, nicht fuer
        # Spruenge.
        self.epoch = 0

    # --- Zustand ------------------------------------------------------------
    @property
    def recording(self) -> bool:
        return self._recording

    @property
    def paused(self) -> bool:
        return self._paused

    def _stand(self) -> tuple[int, int]:
        """(Schreibkante, Versatz) aus EINEM Blick auf den Zaehler.

        Beides aus demselben `written` zu rechnen ist kein Geiz, sondern
        Notwendigkeit: Der Audio-Callback erhoeht den Zaehler nebenher. Wer
        Schreibkante und Versatz einzeln abfragt, kann einen Callback dazwischen
        erwischen - und haelt dann zwei Werte in der Hand, die um einen Block
        nicht zusammenpassen.

        Drei Grenzen fuer den Versatz: die Pufferlaenge, die Schreibkante
        (davor gibt es nichts) und der Anfang DIESER Aufnahme - was vor dem
        letzten R im Ring liegt, ist Material von frueher und gilt als
        verworfen.
        """
        written = self._written
        if not self._recording or self._record_start is None:
            return written, 0
        block = self._scratch.shape[0]
        max_off = max(0, min(self.capacity_frames - block,
                             written - block,
                             written - self._record_start))
        return written, max(0, min(written - self._play_end, max_off))

    @property
    def _offset(self) -> int:
        """Frames zwischen Live-Kante und Leseposition - abgeleitet, nie gesetzt."""
        return self._stand()[1]

    @property
    def offset_seconds(self) -> float:
        """Wie weit hinter der Live-Kante gerade gehoert wird."""
        return self._offset / self.samplerate

    @property
    def live(self) -> bool:
        return self._offset == 0 and not self._paused

    @property
    def behind_limit(self) -> bool:
        """Steht der Mitschnitt am Anschlag? (Puffer voll oder Aufnahmeanfang)"""
        return self._recording and self._offset >= self._max_offset() > 0

    @property
    def play_position_frames(self) -> int:
        """Absolute Stream-Position, an der die Wiedergabe steht.

        Waehrend der Pause ist das eine KONSTANTE - und genau darum gibt es
        diese Eigenschaft. `Schreibkante minus Versatz` aus zwei getrennten
        Abfragen ist es naemlich nicht: Beide Zaehler wachsen zwar im
        Gleichschritt, aber zwischen den beiden Abfragen kann ein Callback
        liegen.
        """
        written, versatz = self._stand()
        return written - versatz

    def _max_offset(self) -> int:
        written = self._written
        if self._record_start is None:
            return 0
        block = self._scratch.shape[0]
        return max(0, min(self.capacity_frames - block,
                          written - block,
                          written - self._record_start))

    # --- Modus --------------------------------------------------------------
    def start_record(self) -> None:
        """Aufnahme an. Der Anfang wird vom naechsten Callback gesetzt."""
        with self._lock:
            if self._recording:
                return
            self._record_start = None        # der erste Block legt ihn fest
            self._recording = True
            self._paused = False
            self._blend_from = -1
            self.epoch += 1

    def stop_record(self) -> None:
        """Aufnahme aus: zurueck an die Live-Kante, Inhalt gilt als verworfen.

        Der Speicher bleibt - ein zweites R muss sofort greifen. Verworfen ist
        der Inhalt dadurch, dass `_record_start` faellt: Ohne Anfang laesst
        `_stand` keinen Versatz zu, und der Ring wird beim naechsten R von der
        neuen Kante an frisch beschrieben.
        """
        with self._lock:
            if not self._recording:
                return
            # Ueberblenden, falls gerade zurueckgesprungen oder angehalten war:
            # Der naechste Block ist wieder der Live-Block.
            self._blend_from = self._offset
            self._recording = False
            self._paused = False
            self._record_start = None
            self.epoch += 1

    # --- Transport ----------------------------------------------------------
    def _stellen(self, play_end: int) -> None:
        """Leseposition setzen - der einzige Weg dorthin von aussen.

        Immer unter dem Lock und immer geklemmt: nie vor die Live-Kante (weiter
        als JETZT gibt es nichts) und nie hinter den Anfang der Aufnahme.
        """
        ziel = max(self._written - self._max_offset(),
                   min(play_end, self._written))
        if ziel != self._play_end:
            self._blend_from = self._offset
            self._play_end = ziel
            self.epoch += 1

    def toggle_pause(self) -> bool:
        """Anhalten/weiterlaufen. Gibt den neuen Zustand zurueck.

        Ausserhalb der Aufnahme gibt es nichts anzuhalten: dann bleibt es bei
        False, ohne Fehler - die Oberflaeche darf die Taste immer anbieten.
        """
        with self._lock:
            if not self._recording:
                return False
            self._paused = not self._paused
            # Ueberblenden, ohne die Position zu aendern: Beim Anhalten wird
            # ausgeblendet, beim Fortsetzen wieder ein.
            self._blend_from = self._offset
            self.epoch += 1
            return self._paused

    def seek(self, seconds: float) -> float:
        """Zurueck (negativ) oder vor (positiv). Gibt den neuen Versatz zurueck.

        Vorwaerts ist an der Live-Kante zu Ende - weiter als JETZT geht nicht.
        Rueckwaerts endet der Weg am Anfang der Aufnahme.
        """
        with self._lock:
            if not self._recording:
                return 0.0
            self._stellen(self._play_end + int(round(seconds * self.samplerate)))
            return self._offset / self.samplerate

    def to_now(self) -> None:
        """Zurueck an die Live-Kante und weiterlaufen lassen."""
        with self._lock:
            if not self._recording:
                return
            if self._paused:
                self._paused = False
                self._blend_from = self._offset
                self.epoch += 1
            self._stellen(self._written)

    def to_start(self) -> None:
        """An den Anfang der Aufnahme (oder so weit zurueck, wie der Puffer reicht)."""
        with self._lock:
            if not self._recording or self._record_start is None:
                return
            self._stellen(self._record_start)

    # --- Audio --------------------------------------------------------------
    def process(self, block: np.ndarray, stream_frames: int) -> None:
        """Block mitschreiben und durch das ersetzen, was gehoert werden soll.

        Wird IM Audio-Callback gerufen und aendert `block` an Ort und Stelle.
        `stream_frames` ist die Stream-Position der Verzoegerungsstufe VOR
        diesem Block - der Mitschnitt uebernimmt sie als seine eigene Uhr.

        Kein Lock - ein Lock im Audio-Callback waere der teurere Fehler
        (dieselbe Abwaegung wie bei toggle_mute in delay_stream). Dafuer ist die
        Zustaendigkeit aufgeteilt: `_written` schreibt nur dieser Callback,
        `_play_end` nur er ODER die Bedienung, und waehrend der Pause - wenn am
        ehesten gesprungen wird - ruehrt er `_play_end` gar nicht an. Bleibt
        `_blend_from`: Setzt die Bedienung es genau zwischen Lesen und
        Zuruecksetzen hier, entfaellt eine Ueberblendung und man hoert an dieser
        einen Stelle ein Knacken. Kein Zustand geht dabei verloren.
        """
        if not self._recording:
            return                           # Modus aus: kein Byte angefasst
        frames = len(block)
        ring = self._ring
        n = self.capacity_frames
        if n < frames:                       # Puffer kleiner als ein Block
            return

        if self._record_start is None:
            # Erster Block dieser Aufnahme: Hier beginnt sie, und hier steht
            # die Leseposition - an der Live-Kante.
            self._record_start = stream_frames
            self._play_end = stream_frames

        # 1. Mitschreiben - IMMER, auch waehrend der Pause. Das ist der Sinn
        #    der Sache: Die Quelle laeuft weiter, und was sie liefert, soll
        #    beim Fortsetzen da sein.
        schreib = stream_frames % n
        if schreib + frames <= n:
            ring[schreib:schreib + frames] = block
        else:
            erst = n - schreib
            ring[schreib:] = block[:erst]
            ring[:frames - erst] = block[erst:]
        self._written = stream_frames + frames

        paused = self._paused
        blend_from = self._blend_from
        self._blend_from = -1

        # 2. Waehrend der Pause bleibt `_play_end` unberuehrt - die Leseposition
        #    steht absolut still, waehrend die Schreibkante davonlaeuft. Genau
        #    so waechst der Versatz um die Dauer der Pause, OHNE dass dieser
        #    Callback etwas schreiben muesste, das die Bedienung auch schreibt.
        if paused:
            if blend_from < 0:
                block[:] = 0.0               # laengst still
            else:
                fade = min(self._fade_frames, frames)
                # Der erste Block der Pause: Ausgegeben wird der Block, der
                # jetzt an der Reihe GEWESEN waere - ausgeblendet statt
                # abgeschnitten, sonst knackt es. `_play_end` rueckt dafuer
                # NICHT vor: Damit gilt dieser Block als ungehoert und wird
                # beim Fortsetzen wiederholt, statt verschluckt zu werden.
                self._lies(block, self._offset - frames, frames)
                block[:fade] *= self._ramp[:fade][::-1]
                block[fade:] = 0.0
            return

        # 3. Laufender Betrieb: Die Leseposition rueckt mit der Schreibkante
        #    mit. Steht sie an der Kante (Versatz 0), ist der zu hoerende Block
        #    genau der eben geschriebene - `block` bleibt dann unangetastet und
        #    damit bitgleich zu einem Lauf ganz ohne Mitschnitt.
        #    Zwei Grenzen in einem Ausdruck: nie ueber die Schreibkante hinaus
        #    (weiter als JETZT gibt es nichts) und nie weiter zurueck, als der
        #    Puffer reicht - Letzteres holt eine ueberlange Pause wieder ein.
        self._play_end = max(min(self._play_end + frames, self._written),
                             self._written - self._max_offset())
        offset = self._offset
        if offset > 0:
            self._lies(block, offset, frames)

        # 4. Sprungstelle ueberblenden: Das Alte geht, das Neue kommt, beides
        #    im selben Block. Ohne das knackt jeder Tastendruck.
        #
        #    "Das Alte" ist der Block, der OHNE den Sprung an der Reihe gewesen
        #    waere - also derselbe Ausschnitt am alten Versatz, nicht dessen
        #    Ende. Faellt der Sprung auf denselben Versatz - Fortsetzen nach
        #    einer Pause -, sind alt und neu identisch und die Ueberblendung ist
        #    rechnerisch die Identitaet: kein Pegelloch.
        if blend_from >= 0 and frames <= len(self._scratch):
            fade = min(self._fade_frames, frames)
            alt = self._scratch[:frames]
            self._lies(alt, blend_from, frames)
            block[:fade] *= self._ramp[:fade]
            block[:fade] += alt[:fade] * self._ramp[:fade][::-1]

    def _lies(self, ziel: np.ndarray, offset: int, frames: int) -> None:
        """`frames` Frames, die `offset` Frames hinter der Schreibkante enden."""
        ring = self._ring
        n = self.capacity_frames
        start = (self._written - offset - frames) % n
        if start + frames <= n:
            ziel[:frames] = ring[start:start + frames]
        else:
            erst = n - start
            ziel[:erst] = ring[start:]
            ziel[erst:frames] = ring[:frames - erst]

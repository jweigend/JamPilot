"""WASAPI-Loopback: den Ton eines Wiedergabe-Endpunkts mitschneiden.

WOFUER: Unter Linux legt JamPilot einen Null-Sink an - einen Ausgang, aus dem
nichts herauskommt und den man abhoeren kann. Unter Windows gibt es so etwas
nicht zu erzeugen; bisher uebernahm das virtuelle Kabel VB-CABLE die Rolle,
und das musste der Nutzer installieren.

Er muss nicht. Windows kann jeden Wiedergabe-Endpunkt mitschneiden (Loopback,
seit Vista, ohne Fremdtreiber), und die Stummschaltung eines Endpunkts sitzt
HINTER diesem Abgriff. Zusammen ergibt das den Null-Sink aus Bordmitteln:

    Endpunkt stummschalten      der Nutzer hoert das Original nicht mehr
    Loopback mitschneiden       wir bekommen es trotzdem vollstaendig
    verzoegert auf Endpunkt B   dorthin, wo wirklich jemand zuhoert

Nachgemessen auf vier Treiberfamilien (Realtek HD Audio, NVIDIA HDMI, VB-Audio,
Oculus): Peak am Abgriff exakt gleich der gesendeten Amplitude, stumm wie nicht
stumm. Verlassen wird sich darauf trotzdem nicht - `pruefen()` misst es beim
Start auf DIESEM Rechner nach, und faellt die Pruefung durch, bleibt der
Kabelweg (siehe routing.py).

WARUM KEIN PORTAUDIO: Das mitgelieferte PortAudio (19.7.0-devel im
sounddevice-Rad) kennt Loopback nicht - der Code ist nicht enthalten, nicht
bloss abgeschaltet. Eine eigene DLL zu bauen hiesse, einen C-Build in die
Auslieferung zu holen; ctypes kostet nichts davon und ist dieselbe Technik, mit
der winaudio.py schon Core Audio bedient.

WARUM ALLES IM EIGENEN THREAD ENTSTEHT: IAudioClient wird dort erzeugt, wo er
auch benutzt wird. COM-Objekte ueber Threadgrenzen zu reichen, ohne sie zu
marshallen, ist die Art Fehler, die monatelang gutgeht und dann auf einem
fremden Rechner zuschlaegt.
"""

import ctypes
import threading
import time
from ctypes import POINTER, byref, c_longlong, c_uint32, c_ulonglong, c_void_p
from ctypes.wintypes import DWORD

import numpy as np

# Die COM-Grundlagen stehen in winaudio - dasselbe Subsystem, dieselben
# vtables. Sie hier ein zweites Mal zu bauen waere die schlechtere Wahl.
from .winaudio import (
    CoreAudioError, _GUID, _aufrufen, _com_bereit, _freigeben, aktivieren,
    geraet, _ole32,
)

_IID_IAudioClient = "{1CB9AD4C-DBFA-4C32-B178-C2F568A703B2}"
_IID_IAudioCaptureClient = "{C8ADBD64-E71E-48A0-A4DE-185C395CD317}"
_IID_IAudioRenderClient = "{F294ACFC-3146-4483-A7BF-ADDCA7C260E2}"

# vtable-Plaetze. Die ersten drei gehoeren immer IUnknown.
_INITIALIZE = 3                 # IAudioClient
_GET_BUFFER_SIZE = 4
_GET_CURRENT_PADDING = 6
_GET_MIX_FORMAT = 8
_START = 10
_STOP = 11
_GET_SERVICE = 14
_CC_GET_BUFFER = 3              # IAudioCaptureClient
_CC_RELEASE_BUFFER = 4
_CC_NEXT_PACKET = 5
_RC_GET_BUFFER = 3              # IAudioRenderClient
_RC_RELEASE_BUFFER = 4

AUDCLNT_SHAREMODE_SHARED = 0
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2
WAVE_FORMAT_EXTENSIBLE = 0xFFFE
_SUBTYPE_IEEE_FLOAT = 3         # erstes Feld der SubFormat-GUID

# Wie lange der Mitschnitt vorlaufen darf, bevor der Ausgabestream ihn abholt.
# Grosszuegig: Der Analysethread haelt den GIL zeitweise (~280 ms), und ein
# Ueberlauf kostet Ton. Zwei Sekunden sind ein halbes Megabyte.
RING_SEKUNDEN = 2.0

# Wieviel im Ring liegen muss, bevor der Ausgabe-Callback zu lesen anfaengt.
# Deckt die Blockgroesse der Ausgabe (43 ms bei 2048/48k) mit Reserve ab; es
# ist reine Puffertiefe im Mitschnitt und geht NICHT von der Verzoegerung ab.
VORLAUF_SEKUNDEN = 0.15

# Abtastintervall des Mitschnitt-Threads. WASAPI liefert in Paketen von rund
# 10 ms; haeufiger zu fragen kostet nur Kontextwechsel.
_POLL = 0.005


class WinCaptureError(RuntimeError):
    """Der Loopback-Mitschnitt kam nicht zustande."""


class _WAVEFORMATEX(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("wFormatTag", ctypes.c_ushort),
                ("nChannels", ctypes.c_ushort),
                ("nSamplesPerSec", ctypes.c_uint32),
                ("nAvgBytesPerSec", ctypes.c_uint32),
                ("nBlockAlign", ctypes.c_ushort),
                ("wBitsPerSample", ctypes.c_ushort),
                ("cbSize", ctypes.c_ushort)]


class _WAVEFORMATEXTENSIBLE(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("Format", _WAVEFORMATEX),
                ("wValidBitsPerSample", ctypes.c_ushort),
                ("dwChannelMask", ctypes.c_uint32),
                ("SubFormat", _GUID)]


def _mixformat(client) -> tuple[c_void_p, dict]:
    """Das Format, in dem die Audio-Engine auf diesem Endpunkt mischt.

    Es wird uebernommen, nicht ausgehandelt: Im Shared Mode ist das Mixformat
    das einzige, das WASAPI ohne Umwege annimmt. Was daraus fuer Abtastrate und
    Kanalzahl folgt, reicht der Aufrufer nach oben durch.
    """
    roh = c_void_p()
    _aufrufen(client, _GET_MIX_FORMAT, (POINTER(c_void_p),), byref(roh))
    kopf = ctypes.cast(roh, POINTER(_WAVEFORMATEX)).contents
    if kopf.wFormatTag == WAVE_FORMAT_EXTENSIBLE:
        ext = ctypes.cast(roh, POINTER(_WAVEFORMATEXTENSIBLE)).contents
        subtyp = ext.SubFormat.Data1
    else:
        subtyp = kopf.wFormatTag
    return roh, {
        "kanaele": kopf.nChannels,
        "rate": kopf.nSamplesPerSec,
        "bits": kopf.wBitsPerSample,
        "blockalign": kopf.nBlockAlign,
        "float": subtyp == _SUBTYPE_IEEE_FLOAT,
    }


def _client(kennung: str, flags: int, puffer_ms: int = 200):
    """Ein initialisierter IAudioClient auf diesem Endpunkt (samt Format)."""
    ptr = geraet(kennung)
    try:
        client = aktivieren(ptr, _IID_IAudioClient)
    finally:
        _freigeben(ptr)
    try:
        format_ptr, info = _mixformat(client)
    except CoreAudioError:
        _freigeben(client)
        raise
    try:
        if not (info["float"] and info["bits"] == 32):
            # Im Shared Mode mischt Windows praktisch immer in float32. Faenden
            # wir etwas anderes vor, waere jede Umrechnung hier geraten - und
            # geraten wird an einer Stelle, an der der Ton entsteht, nicht.
            raise WinCaptureError(
                f"Unerwartetes Mixformat ({info['bits']} bit, "
                f"float={info['float']}) - Loopback nicht nutzbar.")
        _aufrufen(client, _INITIALIZE,
                  (DWORD, DWORD, c_longlong, c_longlong, c_void_p, c_void_p),
                  AUDCLNT_SHAREMODE_SHARED, flags, puffer_ms * 10000, 0,
                  format_ptr, None)
    except BaseException:
        _ole32.CoTaskMemFree(format_ptr)
        _freigeben(client)
        raise
    _ole32.CoTaskMemFree(format_ptr)
    return client, info


class Loopback:
    """Der Mitschnitt eines Endpunkts, als Quelle fuer den Audio-Callback.

    ZIEHEN, NICHT DRUECKEN: Ein eigener Thread holt die WASAPI-Pakete ab und
    legt sie in einen Ringpuffer; der Audio-Callback der AUSGABE holt sich
    daraus, was er braucht (`read_into`). Damit gibt die Ausgabeuhr den Takt an,
    nicht der Mitschnitt - und das ist genau richtig, denn Loopback liefert
    NICHTS, solange niemand auf dem Endpunkt spielt (gemessen: null Frames).
    Die Luecke wird mit Stille gefuellt, und Stille ist die ehrliche Antwort:
    Es hat ja auch nichts geklungen.

    Der Preis sind zwei unabhaengige Uhren. Ihre Drift (wenige ppm) laeuft
    langsam in den Ringpuffer hinein; laeuft er ueber, faellt das aelteste
    Paket weg. Bei mehreren Sekunden Verzoegerung ist das folgenlos - gezaehlt
    wird es trotzdem (`ueberlaeufe`, `unterlaeufe`), sonst sucht spaeter jemand
    ein Knacken, das hier ordentlich verbucht ist.
    """

    def __init__(self, kennung: str, name: str = ""):
        self.kennung = kennung
        self.name = name
        self.samplerate = 0
        self.ueberlaeufe = 0
        self.unterlaeufe = 0

        self._ring = None
        self._schreib = 0
        self._gefuellt = 0
        self._vorlauf = 0
        self._angelaufen = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._bereit = threading.Event()
        self._fehler: BaseException | None = None

        self._thread = threading.Thread(target=self._laufen, name="jampilot-loopback",
                                        daemon=True)
        self._thread.start()
        # Der Aufbau ist COM plus Geraetestart; fuenf Sekunden sind reichlich.
        # Ohne Frist haenge das ganze Programm an einem Treiber, der nicht
        # antwortet, und niemand saehe warum.
        if not self._bereit.wait(timeout=5.0):
            self._stop.set()
            raise WinCaptureError(f"Loopback auf {name or kennung!r} "
                                  f"antwortet nicht.")
        if self._fehler is not None:
            raise self._fehler

    # --- Der Mitschnitt-Thread ---------------------------------------------
    def _laufen(self):
        client = capture = None
        try:
            _com_bereit()
            client, info = _client(self.kennung, AUDCLNT_STREAMFLAGS_LOOPBACK)
            capture = c_void_p()
            _aufrufen(client, _GET_SERVICE, (POINTER(_GUID), POINTER(c_void_p)),
                      byref(_GUID(_IID_IAudioCaptureClient)), byref(capture))

            self.samplerate = info["rate"]
            self._quellkanaele = info["kanaele"]
            self._blockalign = info["blockalign"]
            self._ring = np.zeros((int(RING_SEKUNDEN * info["rate"]), 2),
                                  dtype=np.float32)
            self._vorlauf = int(VORLAUF_SEKUNDEN * info["rate"])
            _aufrufen(client, _START, ())
        except BaseException as exc:
            self._fehler = exc
            self._bereit.set()
            if capture:
                _freigeben(capture)
            if client:
                _freigeben(client)
            return

        self._bereit.set()
        try:
            while not self._stop.is_set():
                if not self._abholen(capture):
                    time.sleep(_POLL)
        except BaseException as exc:      # Treiber weg, Geraet abgezogen
            self._fehler = exc
        finally:
            try:
                _aufrufen(client, _STOP, ())
            except Exception:
                pass
            _freigeben(capture)
            _freigeben(client)

    def _abholen(self, capture) -> bool:
        """Ein Paket abholen. False, wenn gerade keines da ist."""
        naechste = c_uint32()
        _aufrufen(capture, _CC_NEXT_PACKET, (POINTER(c_uint32),), byref(naechste))
        if naechste.value == 0:
            return False

        daten = POINTER(ctypes.c_byte)()
        anzahl = c_uint32()
        flags = DWORD()
        _aufrufen(capture, _CC_GET_BUFFER,
                  (POINTER(POINTER(ctypes.c_byte)), POINTER(c_uint32),
                   POINTER(DWORD), POINTER(c_ulonglong), POINTER(c_ulonglong)),
                  byref(daten), byref(anzahl), byref(flags), None, None)
        n = anzahl.value
        try:
            if n:
                if flags.value & AUDCLNT_BUFFERFLAGS_SILENT:
                    # WASAPI sagt "hier waere Stille" und schreibt den Puffer
                    # nicht - ihn zu lesen waere ein Griff in alten Inhalt.
                    self._schreiben(None, n)
                else:
                    roh = ctypes.string_at(daten, n * self._blockalign)
                    block = np.frombuffer(roh, dtype=np.float32)
                    block = block.reshape(n, self._quellkanaele)
                    self._schreiben(block, n)
        finally:
            _aufrufen(capture, _CC_RELEASE_BUFFER, (c_uint32,), n)
        return True

    def _schreiben(self, block, n: int):
        """n Frames in den Ring legen (block=None heisst Stille)."""
        if block is None:
            stereo = None
        elif self._quellkanaele >= 2:
            stereo = block[:, :2]
        else:
            stereo = np.repeat(block, 2, axis=1)

        ring = self._ring
        groesse = len(ring)
        with self._lock:
            if n >= groesse:
                # Ein einzelnes Paket groesser als der ganze Ring - kann nur
                # nach einem sehr langen Aussetzer passieren. Dann zaehlt nur
                # das Juengste.
                self.ueberlaeufe += 1
                if stereo is None:
                    ring[:] = 0.0
                else:
                    ring[:] = stereo[-groesse:]
                self._schreib = 0
                self._gefuellt = groesse
                return

            pos = self._schreib
            ende = pos + n
            if ende <= groesse:
                ring[pos:ende] = 0.0 if stereo is None else stereo
            else:
                erste = groesse - pos
                if stereo is None:
                    ring[pos:] = 0.0
                    ring[:ende - groesse] = 0.0
                else:
                    ring[pos:] = stereo[:erste]
                    ring[:ende - groesse] = stereo[erste:]
            self._schreib = ende % groesse
            self._gefuellt += n
            if self._gefuellt > groesse:
                self.ueberlaeufe += 1
                self._gefuellt = groesse

    # --- Die Seite des Audio-Callbacks -------------------------------------
    def read_into(self, ziel: np.ndarray):
        """`len(ziel)` Frames in ein VORHANDENES Array schreiben.

        Kein Rueckgabearray, weil der Aufrufer der Audio-Callback ist: Dort
        wird nicht allokiert. Fehlt Material, bleibt der Rest Stille - der
        Ausgabestream darf niemals blockieren, lieber ein stiller Block als ein
        Aussetzer im ganzen Geraet.

        VORLAUF: Gelesen wird erst, wenn ein Polster im Ring liegt. Ohne das
        raeumte der Callback den Ring bei jedem Durchgang restlos leer und
        stolperte ueber jede Schwankung des Mitschnitt-Threads - zwei
        unabhaengige Uhren treffen sich nun einmal nicht auf den Frame genau.
        Solange gar nichts spielt, liefert WASAPI ueberhaupt nichts; dann bleibt
        es bei Stille, und das ist die richtige Antwort.
        """
        n = len(ziel)
        ring = self._ring
        if ring is None:
            ziel[:] = 0.0
            return
        groesse = len(ring)
        with self._lock:
            if not self._angelaufen:
                if self._gefuellt < self._vorlauf:
                    ziel[:] = 0.0
                    return
                self._angelaufen = True
            habe = min(self._gefuellt, n)
            if habe < n:
                # Der Vorlauf ist aufgezehrt - danach wird er neu aufgebaut,
                # statt von jetzt an bei jedem Block ein Stueck Stille
                # einzustreuen.
                self.unterlaeufe += 1
                self._angelaufen = False
                ziel[habe:] = 0.0
            if habe:
                start = (self._schreib - self._gefuellt) % groesse
                ende = start + habe
                if ende <= groesse:
                    ziel[:habe] = ring[start:ende]
                else:
                    erste = groesse - start
                    ziel[:erste] = ring[start:]
                    ziel[erste:habe] = ring[:ende - groesse]
                self._gefuellt -= habe

    def close(self):
        self._stop.set()
        self._thread.join(timeout=2.0)


# --- Die Startpruefung ------------------------------------------------------

_PROBE_HZ = 1000.0
_PROBE_AMPLITUDE = 0.25
_PROBE_SEKUNDEN = 0.35
# Ab diesem Peak gilt der Probeton als angekommen. Weit unter der Amplitude,
# weit ueber allem, was Rauschen erzeugt - dazwischen gibt es nichts, was eine
# feinere Schwelle entscheiden koennte.
_PROBE_SCHWELLE = 0.05


class _Probeton:
    """Ein Sinus, direkt auf einen Endpunkt gerendert - nur fuer die Pruefung.

    Ueber Core Audio und nicht ueber PortAudio, weil der Ton GARANTIERT auf dem
    geprueften Endpunkt landen muss. Die Zuordnung Core-Audio-Name ->
    PortAudio-Index ist genau die Stelle, an der das schiefgehen kann, und eine
    Pruefung, die am falschen Geraet misst, ist schlimmer als keine.
    """

    def __init__(self, kennung: str):
        self.client, self.info = _client(kennung, 0)
        self.render = c_void_p()
        try:
            _aufrufen(self.client, _GET_SERVICE,
                      (POINTER(_GUID), POINTER(c_void_p)),
                      byref(_GUID(_IID_IAudioRenderClient)), byref(self.render))
            self.frames = c_uint32()
            _aufrufen(self.client, _GET_BUFFER_SIZE, (POINTER(c_uint32),),
                      byref(self.frames))
        except BaseException:
            self.close()
            raise
        self._phase = 0

    def schreiben(self):
        belegt = c_uint32()
        _aufrufen(self.client, _GET_CURRENT_PADDING, (POINTER(c_uint32),),
                  byref(belegt))
        frei = self.frames.value - belegt.value
        if not frei:
            return
        ziel = POINTER(ctypes.c_byte)()
        _aufrufen(self.render, _RC_GET_BUFFER,
                  (c_uint32, POINTER(POINTER(ctypes.c_byte))), frei, byref(ziel))
        t = (np.arange(frei) + self._phase) / self.info["rate"]
        self._phase += frei
        welle = (_PROBE_AMPLITUDE * np.sin(2 * np.pi * _PROBE_HZ * t)).astype(np.float32)
        roh = np.repeat(welle, self.info["kanaele"]).tobytes()
        ctypes.memmove(ziel, roh, len(roh))
        _aufrufen(self.render, _RC_RELEASE_BUFFER, (c_uint32, DWORD), frei, 0)

    def start(self):
        self.schreiben()            # vorfuellen, sonst startet er leer
        _aufrufen(self.client, _START, ())

    def close(self):
        try:
            _aufrufen(self.client, _STOP, ())
        except Exception:
            pass
        _freigeben(self.render)
        _freigeben(self.client)


def pruefen(kennung: str) -> bool:
    """Ueberlebt der Mitschnitt die Stummschaltung DIESES Endpunkts?

    Schaltet stumm, schickt einen Probeton hinein, misst am Loopback-Abgriff
    nach, stellt den Mute-Zustand wieder her. Rund 350 ms, unhoerbar (der
    Endpunkt ist waehrenddessen ja stumm).

    Das ist die eine Messung, an der der ganze Weg haengt. Sitzt der Mute im
    Treiber VOR dem Abgriff, kommt hier nichts an - dann sagt die Funktion
    Nein, und routing.py nimmt den Kabelweg. Geraten wird nichts.

    Der Mute-Zustand wird IMMER wiederhergestellt, auch wenn dazwischen etwas
    fliegt. Ein Programm, das den Rechner stumm zuruecklaesst, weil seine
    Selbstpruefung gestolpert ist, waere schlimmer als eines, das nie geprueft
    haette.
    """
    from . import winaudio

    vorher = None
    lb = ton = None
    try:
        _com_bereit()
        vorher = winaudio.stumm(kennung)
        winaudio.setze_stumm(kennung, True)

        lb = Loopback(kennung)
        ton = _Probeton(kennung)
        ton.start()

        block = np.empty((1024, 2), dtype=np.float32)
        peak = 0.0
        ende = time.monotonic() + _PROBE_SEKUNDEN
        while time.monotonic() < ende and peak < _PROBE_SCHWELLE:
            ton.schreiben()
            lb.read_into(block)
            peak = max(peak, float(np.abs(block).max()))
            time.sleep(0.01)
        return peak >= _PROBE_SCHWELLE
    except (CoreAudioError, WinCaptureError, OSError):
        return False
    finally:
        if ton is not None:
            ton.close()
        if lb is not None:
            lb.close()
        if vorher is not None:
            try:
                winaudio.setze_stumm(kennung, vorher)
            except Exception:
                pass

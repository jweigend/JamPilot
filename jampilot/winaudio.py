"""Windows Core Audio, so weit JamPilot es braucht: Endpunkte auflisten und
das Standard-Wiedergabegeraet lesen und setzen.

WARUM ES DIESES MODUL GIBT: Unter Linux legt JamPilot einen Null-Sink an und
macht ihn per `pactl set-default-sink` zum Standard-Ausgang - alles spielt
unhoerbar dorthin, wir hoeren es ab und geben es verzoegert auf die echte
Hardware. Unter Windows uebernimmt VB-CABLE die Rolle des Null-Sinks, aber es
fehlte das Gegenstueck zu `set-default-sink`: der Nutzer musste den Ton von
Hand in das Kabel umstellen. Das ist genau der Schritt, der hier wegfaellt.

WARUM ctypes UND NICHT comtypes/pycaw: Es geht um vier COM-Aufrufe. Dafuer eine
Abhaengigkeit in eine Sperrdatei aufzunehmen, die auf drei Plattformen gilt,
waere ein schlechter Tausch - zumal comtypes selbst nichts anderes tut, als
diese vtables zu bauen.

WARUM IPolicyConfig: Microsoft hat nie eine dokumentierte Schnittstelle
veroeffentlicht, um das Standardgeraet zu setzen - der offizielle Weg ist die
Systemsteuerung. IPolicyConfig ist die undokumentierte Schnittstelle, die
dahintersteckt; sie ist seit Vista unveraendert und ist das, was nircmd,
SoundVolumeView und AudioDeviceCmdlets benutzen. Sie braucht KEINE
Administratorrechte. Undokumentiert heisst aber auch: Sie kann in einer
kuenftigen Windows-Version verschwinden. Deshalb faengt der Aufrufer einen
Fehlschlag ab und faellt auf den Handbetrieb zurueck, statt zu sterben.
"""

import ctypes
from ctypes import POINTER, byref, c_uint32, c_ulong, c_void_p, c_wchar_p
from ctypes.wintypes import DWORD, LPCWSTR

# --- Flow und Rolle (die Begriffe von Core Audio) ---------------------------

RENDER = 0          # Wiedergabe (Lautsprecher, Kopfhoerer, CABLE Input)
CAPTURE = 1         # Aufnahme (Mikrofon, CABLE Output)

CONSOLE = 0         # "normale" Wiedergabe: Musik, Videos, Spiele
MULTIMEDIA = 1      # in der Praxis identisch belegt
COMMUNICATIONS = 2  # Telefonie - Teams, Discord, Zoom

# Nur diese beiden werden umgestellt. COMMUNICATIONS bleibt, wo es ist, und das
# ist Absicht: Ein Videogespraech durch einen Vier-Sekunden-Puffer zu schicken
# macht es unbenutzbar, und niemand sucht die Ursache dafuer bei einem
# Akkordanzeiger. Unter Linux gibt es diese Unterscheidung nicht - dort trifft
# der Null-Sink zwangslaeufig alles. Hier kann man es besser machen, also wird
# es besser gemacht.
UMZUSTELLENDE_ROLLEN = (CONSOLE, MULTIMEDIA)


class CoreAudioError(RuntimeError):
    """Ein Core-Audio-Aufruf ist fehlgeschlagen."""


# --- Das Noetigste an COM ---------------------------------------------------

_ole32 = ctypes.windll.ole32

_S_FALSE = 1
_RPC_E_CHANGED_MODE = -2147417850        # 0x80010106
_COINIT_APARTMENTTHREADED = 0x2
_CLSCTX_ALL = 23


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]

    def __init__(self, text):
        super().__init__()
        if _ole32.CLSIDFromString(text, byref(self)) < 0:
            raise CoreAudioError(f"kein GUID: {text}")


class _PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", _GUID), ("pid", DWORD)]


class _PROPVARIANT(ctypes.Structure):
    # Nur so weit ausmodelliert, wie wir sie lesen: Der Anzeigename ist ein
    # VT_LPWSTR, und dessen Zeiger liegt am Anfang der Union.
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort),
                ("r2", ctypes.c_ushort), ("r3", ctypes.c_ushort),
                ("data", c_void_p), ("_pad", c_void_p)]


_CLSID_MMDeviceEnumerator = "{BCDE0395-E52F-467C-8E3D-C4579291692E}"
_IID_IMMDeviceEnumerator = "{A95664D2-9614-4F35-A746-DE8DB63617E6}"
_CLSID_PolicyConfigClient = "{870AF99C-171D-4F9E-AF0D-E63DF40C2BC9}"
_IID_IPolicyConfig = "{F8679F50-850A-41CF-9C72-430F290290C8}"
_IID_IAudioEndpointVolume = "{5CDF2C82-841E-4546-9722-0CF74078229A}"
_FMTID_Device = "{A45C254E-DF1C-4EFD-8020-67D146A850E0}"
_PID_FriendlyName = 14
_FMTID_AudioEndpoint = "{1DA5D803-D492-4EDD-8C23-E0C0FFEE7F0E}"
_PID_FormFactor = 0

# EndpointFormFactor - wie der Endpunkt physisch angebunden ist. Wir brauchen
# nur die Unterscheidung "da hoert jemand" gegen "da haengt hoechstens ein
# Bildschirm dran", und die kann man dem NAMEN nicht ansehen: Der HDMI-Ausgang
# einer NVIDIA-Karte heisst "LEN LT2452pwC (NVIDIA High Definition Audio)" -
# kein "HDMI" weit und breit. Windows weiss es trotzdem.
FF_UNBEKANNT = 10
FF_LAUTSPRECHER = 1
FF_KOPFHOERER = 3
FF_HEADSET = 5
FF_DIGITAL_DURCHREICHUNG = 7
FF_SPDIF = 8
FF_HDMI = 9                             # DigitalAudioDisplayDevice

_DEVICE_STATE_ACTIVE = 0x1

# Positionen in den vtables. Die ersten drei Plaetze gehoeren immer IUnknown
# (QueryInterface, AddRef, Release), danach zaehlen die Methoden der
# Schnittstelle in Deklarationsreihenfolge weiter.
_RELEASE = 2
_ENUM_AUDIO_ENDPOINTS = 3               # IMMDeviceEnumerator
_GET_DEFAULT_AUDIO_ENDPOINT = 4
_GET_DEVICE = 5
_GET_COUNT = 3                          # IMMDeviceCollection
_ITEM = 4
_ACTIVATE = 3                           # IMMDevice
_OPEN_PROPERTY_STORE = 4
_GET_ID = 5
_GET_VALUE = 5                          # IPropertyStore
_SET_MUTE = 14                          # IAudioEndpointVolume
_GET_MUTE = 15
# IPolicyConfig: GetMixFormat, GetDeviceFormat, ResetDeviceFormat,
# SetDeviceFormat, GetProcessingPeriod, SetProcessingPeriod, GetShareMode,
# SetShareMode, GetPropertyValue, SetPropertyValue, SetDefaultEndpoint.
_SET_DEFAULT_ENDPOINT = 13


def _com_bereit():
    """COM auf DIESEM Thread hochfahren.

    Jeder Thread braucht das einzeln, und JamPilot ruft hier aus mehreren
    heraus: der Aufbau laeuft im Qt-Thread, der Abbau bei Strg+C im
    Signalhandler. Zwei Rueckgaben sind kein Fehler - S_FALSE heisst "war
    schon", RPC_E_CHANGED_MODE heisst "war schon, in einem anderen Modell"
    (genau das liefert Qt, das den Hauptthread als STA anmeldet). In beiden
    Faellen ist COM benutzbar; nur ein echter Fehlercode zaehlt.

    CoUninitialize gibt es hier bewusst NICHT: Der Thread gehoert uns nicht
    allein, und wer COM unter Qt wegraeumt, nimmt es Qt mit weg.
    """
    hr = _ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
    if hr < 0 and hr != _RPC_E_CHANGED_MODE:
        raise CoreAudioError(f"CoInitializeEx: 0x{hr & 0xFFFFFFFF:08x}")


def _aufrufen(ptr, index, argtypes, *args):
    """Die Methode an Position `index` der vtable von `ptr` aufrufen."""
    vtbl = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
    proto = ctypes.WINFUNCTYPE(ctypes.c_long, c_void_p, *argtypes)
    hr = proto(vtbl[index])(ptr, *args)
    if hr < 0:
        raise CoreAudioError(f"COM-Aufruf {index} fehlgeschlagen: "
                             f"0x{hr & 0xFFFFFFFF:08x}")
    return hr


def _freigeben(ptr):
    if ptr:
        vtbl = ctypes.cast(ptr, POINTER(POINTER(c_void_p))).contents
        ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtbl[_RELEASE])(ptr)


def _erzeugen(clsid: str, iid: str) -> c_void_p:
    _com_bereit()
    ptr = c_void_p()
    hr = _ole32.CoCreateInstance(byref(_GUID(clsid)), None, _CLSCTX_ALL,
                                 byref(_GUID(iid)), byref(ptr))
    if hr < 0:
        raise CoreAudioError(f"CoCreateInstance {clsid}: "
                             f"0x{hr & 0xFFFFFFFF:08x}")
    return ptr


# --- Endpunkte --------------------------------------------------------------

class Endpunkt:
    """Ein Audiogeraet, wie Windows es sieht.

    `kennung` ist die stabile Endpunkt-ID ("{0.0.0.00000000}.{guid}") - damit
    wird gesetzt. `name` ist der Anzeigename ("Lautsprecher (Realtek High
    Definition Audio)") - unter genau diesem Namen fuehrt PortAudio das Geraet
    ueber WASAPI ebenfalls, und darueber finden die beiden zusammen.
    `formfaktor` sagt, was fuer ein Anschluss es ist (FF_*) - die einzige
    verlaessliche Auskunft darueber, ob dort jemand zuhoert.
    """

    __slots__ = ("kennung", "name", "formfaktor")

    def __init__(self, kennung: str, name: str, formfaktor: int = FF_UNBEKANNT):
        self.kennung = kennung
        self.name = name
        self.formfaktor = formfaktor

    def __repr__(self):
        return f"Endpunkt({self.name!r})"

    def __eq__(self, other):
        return isinstance(other, Endpunkt) and self.kennung == other.kennung

    def __hash__(self):
        return hash(self.kennung)


def _kennung(geraet) -> str:
    text = c_wchar_p()
    _aufrufen(geraet, _GET_ID, (POINTER(c_wchar_p),), byref(text))
    try:
        return text.value
    finally:
        _ole32.CoTaskMemFree(text)


def _eigenschaft(geraet, fmtid: str, pid: int, lesen):
    """Eine Eigenschaft aus dem Property Store des Endpunkts holen.

    `lesen` bekommt die PROPVARIANT und macht daraus, was drinsteht - der Typ
    haengt an der Eigenschaft, nicht am Abrufweg.
    """
    schluessel = _PROPERTYKEY()
    schluessel.fmtid = _GUID(fmtid)
    schluessel.pid = pid

    speicher = c_void_p()
    _aufrufen(geraet, _OPEN_PROPERTY_STORE, (DWORD, POINTER(c_void_p)),
              0, byref(speicher))                    # 0 = STGM_READ
    try:
        wert = _PROPVARIANT()
        _aufrufen(speicher, _GET_VALUE,
                  (POINTER(_PROPERTYKEY), POINTER(_PROPVARIANT)),
                  byref(schluessel), byref(wert))
        try:
            return lesen(wert)
        finally:
            _ole32.PropVariantClear(byref(wert))
    finally:
        _freigeben(speicher)


def _name(geraet) -> str:
    return _eigenschaft(geraet, _FMTID_Device, _PID_FriendlyName,
                        lambda wert: ctypes.cast(wert.data, c_wchar_p).value or "")


def _formfaktor(geraet) -> int:
    """Der Anschlusstyp - VT_UI4, also die ersten vier Bytes der Union.

    NICHT ueber `wert.data` gelesen: Das ist ein c_void_p und holte auf 64 Bit
    acht Bytes, von denen die oberen vier hier nicht gesetzt sind.
    """
    def lesen(wert):
        roh = ctypes.cast(ctypes.byref(wert, _PROPVARIANT.data.offset),
                          POINTER(ctypes.c_uint32))
        return int(roh.contents.value)

    try:
        return _eigenschaft(geraet, _FMTID_AudioEndpoint, _PID_FormFactor, lesen)
    except CoreAudioError:
        # Nicht jeder Treiber setzt die Eigenschaft. Unbekannt ist eine
        # brauchbare Antwort - sie fuehrt nur dazu, dass der Endpunkt beim
        # Sortieren nicht bevorzugt wird.
        return FF_UNBEKANNT


def endpunkte(flow: int = RENDER) -> list[Endpunkt]:
    """Alle AKTIVEN Endpunkte einer Richtung.

    Aktiv heisst: eingesteckt und eingeschaltet. Deaktivierte und nicht
    verbundene Geraete stehen zwar in der Registry, sind als Ziel aber
    wertlos - wer darauf umstellt, hat einen stummen Rechner.
    """
    aufzaehler = _erzeugen(_CLSID_MMDeviceEnumerator, _IID_IMMDeviceEnumerator)
    try:
        sammlung = c_void_p()
        _aufrufen(aufzaehler, _ENUM_AUDIO_ENDPOINTS,
                  (DWORD, DWORD, POINTER(c_void_p)),
                  flow, _DEVICE_STATE_ACTIVE, byref(sammlung))
        try:
            anzahl = c_uint32()
            _aufrufen(sammlung, _GET_COUNT, (POINTER(c_uint32),), byref(anzahl))
            gefunden = []
            for i in range(anzahl.value):
                geraet = c_void_p()
                _aufrufen(sammlung, _ITEM, (c_uint32, POINTER(c_void_p)),
                          i, byref(geraet))
                try:
                    gefunden.append(Endpunkt(_kennung(geraet), _name(geraet),
                                             _formfaktor(geraet)))
                finally:
                    _freigeben(geraet)
            return gefunden
        finally:
            _freigeben(sammlung)
    finally:
        _freigeben(aufzaehler)


def standard(flow: int = RENDER, rolle: int = CONSOLE) -> Endpunkt | None:
    """Das aktuelle Standardgeraet - oder None, wenn es gar keines gibt."""
    aufzaehler = _erzeugen(_CLSID_MMDeviceEnumerator, _IID_IMMDeviceEnumerator)
    try:
        geraet = c_void_p()
        try:
            _aufrufen(aufzaehler, _GET_DEFAULT_AUDIO_ENDPOINT,
                      (DWORD, DWORD, POINTER(c_void_p)),
                      flow, rolle, byref(geraet))
        except CoreAudioError:
            return None          # E_NOTFOUND: kein Geraet dieser Richtung
        try:
            return Endpunkt(_kennung(geraet), _name(geraet), _formfaktor(geraet))
        finally:
            _freigeben(geraet)
    finally:
        _freigeben(aufzaehler)


def setze_standard(kennung: str, rollen=UMZUSTELLENDE_ROLLEN):
    """Das Standardgeraet umstellen - das Gegenstueck zu `set-default-sink`."""
    politik = _erzeugen(_CLSID_PolicyConfigClient, _IID_IPolicyConfig)
    try:
        for rolle in rollen:
            _aufrufen(politik, _SET_DEFAULT_ENDPOINT, (LPCWSTR, DWORD),
                      kennung, rolle)
    finally:
        _freigeben(politik)


# --- Ein einzelner Endpunkt -------------------------------------------------

def geraet(kennung: str) -> c_void_p:
    """Der IMMDevice-Zeiger zu einer Endpunkt-ID. DER AUFRUFER GIBT IHN FREI.

    Alles darueber (endpunkte, standard) liefert Namen und Kennungen und raeumt
    hinter sich auf. Wer den Endpunkt selbst braucht - um eine Schnittstelle
    darauf zu aktivieren -, bekommt ihn hier, und dann gilt die COM-Regel: wer
    ihn holt, gibt ihn frei.
    """
    aufzaehler = _erzeugen(_CLSID_MMDeviceEnumerator, _IID_IMMDeviceEnumerator)
    try:
        ptr = c_void_p()
        _aufrufen(aufzaehler, _GET_DEVICE, (c_wchar_p, POINTER(c_void_p)),
                  kennung, byref(ptr))
        return ptr
    finally:
        _freigeben(aufzaehler)


def aktivieren(geraet_ptr: c_void_p, iid: str) -> c_void_p:
    """IMMDevice::Activate - eine Schnittstelle AUF diesem Endpunkt erzeugen.

    Das ist der Einstieg in alles, was mit dem Endpunkt selbst zu tun hat:
    IAudioEndpointVolume hier, IAudioClient in wincapture. Auch hier gibt der
    Aufrufer frei.
    """
    ptr = c_void_p()
    _aufrufen(geraet_ptr, _ACTIVATE,
              (POINTER(_GUID), DWORD, c_void_p, POINTER(c_void_p)),
              byref(_GUID(iid)), _CLSCTX_ALL, None, byref(ptr))
    return ptr


# --- Stummschaltung ---------------------------------------------------------
#
# WOFUER: Der Mute eines Endpunkts sitzt HINTER dem Loopback-Abgriff - der
# Lautsprecher schweigt, der Mitschnitt bleibt vollstaendig. Damit taugt jeder
# gewoehnliche Ausgang als stummer Umweg, und das virtuelle Kabel ist nur noch
# eine Moeglichkeit von mehreren (siehe wincapture, routing.WINMUTE).
#
# Die App-Lautstaerke im Lautstaerkemixer taugt dafuer ausdruecklich NICHT: Die
# wirkt VOR dem Abgriff, man schnitte Stille mit. Nachgemessen; wer es erneut
# probieren will, spart sich die Stunde.
#
# IAudioEndpointVolume ist im Gegensatz zu IPolicyConfig dokumentiert - dieser
# Teil kann uns also nicht unter der Hand weggenommen werden.

def _lautstaerke(kennung: str) -> c_void_p:
    ptr = geraet(kennung)
    try:
        return aktivieren(ptr, _IID_IAudioEndpointVolume)
    finally:
        _freigeben(ptr)


def stumm(kennung: str) -> bool:
    """Ist dieser Endpunkt stummgeschaltet?"""
    volume = _lautstaerke(kennung)
    try:
        zustand = ctypes.c_int()
        _aufrufen(volume, _GET_MUTE, (POINTER(ctypes.c_int),), byref(zustand))
        return bool(zustand.value)
    finally:
        _freigeben(volume)


def setze_stumm(kennung: str, an: bool):
    """Endpunkt stummschalten oder wieder freigeben."""
    volume = _lautstaerke(kennung)
    try:
        _aufrufen(volume, _SET_MUTE, (ctypes.c_int, c_void_p),
                  1 if an else 0, None)
    finally:
        _freigeben(volume)

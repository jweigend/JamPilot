"""Automatisches Audio-Routing - unter Linux und unter Windows.

Problem: Greift man den Monitor des Standard-Ausgangs ab und gibt verzoegert
auf denselben Ausgang aus, hoert man Original + Verzoegerung + Echo-Kaskade.

Loesung: Ein stummer Umweg wird temporaer zum Standard-Ausgang. Player
(YouTube, Spotify, ...) spielen unhoerbar dorthin; wir hoeren den Umweg ab und
geben nur das verzoegerte Signal auf die echte Hardware aus. Beim Beenden wird
alles zurueckgedreht.

DIESELBE IDEE, ZWEI SYSTEME:

    Linux    PulseAudio/PipeWire, `LinuxRouting`. Der Umweg ist ein Null-Sink,
             den wir selbst anlegen und per `pactl` zum Standard machen.

    Windows  Core Audio, zwei Wege - und der bessere braucht keine Installation.

             `WindowsMuteRouting` (WINMUTE, der Normalfall): Der Endpunkt, auf
             dem die Player ohnehin spielen, wird STUMMGESCHALTET und per
             WASAPI-Loopback mitgeschnitten. Der Mute sitzt hinter dem Abgriff -
             der Nutzer hoert das Original nicht mehr, wir bekommen es
             vollstaendig. Der Standard-Ausgang bleibt, wo er ist; die
             verzoegerte Ausgabe geht auf ein zweites Geraet (Kopfhoerer,
             Interface). Ob der Treiber das mitmacht, wird beim Start GEMESSEN,
             nicht geglaubt (wincapture.pruefen).

             `WindowsRouting` (WINCABLE, der Rueckfallweg): Wo kein zweites
             Ausgabegeraet da ist oder der Mute vor dem Abgriff sitzt, uebernimmt
             das virtuelle Kabel VB-CABLE die Rolle des Null-Sinks, und der
             Standard-Ausgang wird ueber winaudio.setze_standard darauf
             umgebogen (das Gegenstueck zu `set-default-sink`).

    macOS    noch nicht. Dort uebernimmt BlackHole die Rolle des Kabels, aber
             die Umstellung des Standardgeraets ist eine andere Baustelle
             (AudioObjectSetPropertyData) - bis dahin gilt dort der Handbetrieb
             mit `--input`, siehe README.

Der Unterschied nach aussen ist KEINER: In beiden Faellen genuegt `jampilot`
ohne Argumente. Und in beiden Faellen ist der Rueckbau die eigentliche Arbeit -
wer den Systemton umbiegt und ihn nicht zurueckgibt, hinterlaesst einen
Rechner, der stumm ist, ohne dass jemand den Grund sieht.
"""

import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SINK_NAME = "jampilot"
APP_NAME = "jampilot"

# Welches Verfahren auf diesem Rechner traegt.
PULSE = "pulse"          # Linux, Null-Sink ueber pactl
WINMUTE = "winmute"      # Windows, stummer Endpunkt + WASAPI-Loopback
WINCABLE = "wincable"    # Windows, VB-CABLE ueber Core Audio

# Welcher Windows-Weg gewuenscht ist: "auto", "mute" oder "cable". Modulweit,
# weil backend() von einem Dutzend Stellen ohne Argumente gefragt wird und die
# Antwort ueberall dieselbe sein MUSS - eine Stelle, die anders entscheidet als
# der Aufbau, prueft das falsche Geraet. cmd_run setzt es einmal, bevor
# irgendetwas fragt.
_wunsch = "auto"


def _nutzerkennung() -> str:
    """Wer wir sind - fuer den Namen der Sperrdatei.

    `os.getuid` gibt es unter Windows NICHT, und das ist kein Laufzeitproblem,
    sondern ein AttributeError beim IMPORT dieses Moduls. engine.start()
    importiert routing bei jedem Start, auch wenn es hinterher gar nichts
    umleitet - JamPilot stuerbe also, bevor es irgendetwas tut. Der Name muss
    nur pro Nutzer eindeutig sein; dafuer taugt der Anmeldename genauso.
    """
    try:
        return str(os.getuid())
    except AttributeError:
        return getpass.getuser()


# Merkt sich, WER die Umleitung haelt. Ohne diesen Besitzvermerk kann eine
# zweite Instanz den Zustand einer noch laufenden ersten nicht von der Waise
# eines abgestuerzten Laufs unterscheiden.
LOCK_FILE = Path(tempfile.gettempdir()) / f"jampilot-{_nutzerkennung()}.pid"

# NUR WINDOWS: was vor der Umstellung Standard-Ausgang war.
#
# Unter Linux braucht es das nicht - dort verschwindet der Null-Sink mit dem
# Prozess, und was danach Standard ist, findet PulseAudio selbst wieder. Unter
# Windows ueberlebt die Umstellung den Prozess: Nach einem Absturz bliebe das
# Kabel Standard-Ausgang und der Rechner waere stumm, ueber den naechsten
# Neustart hinaus. Das Ziel steht deshalb auf der Platte, bevor umgestellt
# wird, und der naechste Start (oder `jampilot cleanup`) holt es zurueck.
STATE_FILE = Path(tempfile.gettempdir()) / f"jampilot-{_nutzerkennung()}.json"

_UNSET = object()


class InstanceRunning(RuntimeError):
    """Eine andere JamPilot-Instanz haelt das Audio-Routing."""

    def __init__(self, pid: int):
        super().__init__(
            f"Another JamPilot instance is already running (PID {pid}). "
            f"Stop it first - two instances would tear each other's audio "
            f"routing apart."
        )
        self.pid = pid


def bevorzugen(wahl: str | None):
    """Den Windows-Weg festlegen ("auto", "mute", "cable"). Einmal, ganz frueh."""
    global _wunsch, _stummweg_cache
    neu = wahl or "auto"
    if neu != _wunsch:
        _stummweg_cache = _UNSET       # die alte Antwort galt fuer eine andere Frage
    _wunsch = neu


def backend() -> str | None:
    """Welches Umleitungsverfahren dieser Rechner hergibt - oder keines.

    EINE Stelle, an der die Plattformfrage beantwortet wird. Alles andere fragt
    hier nach, statt selbst `sys.platform` zu lesen - sonst steht die Antwort
    fuenfmal im Programm und viermal davon leicht anders.

    Unter Windows gilt: Das Kabel zuerst, WENN es installiert ist. Es ist der
    erprobte Weg, es braucht keinen zweiten Endpunkt, und wer es installiert
    hat, hat sich dafuer entschieden - dem faehrt man nicht ueber Nacht in die
    Konfiguration. Erst wenn keines da ist, kommt der Mute-Weg, und der ist
    dafuer gebaut: fuer den ersten Start auf einem Rechner, auf dem nichts
    vorbereitet ist. Ob er traegt, wird GEMESSEN (siehe _stummweg) - und die
    Messung laeuft nur, wenn sie gebraucht wird.
    """
    if shutil.which("pactl"):
        return PULSE
    if sys.platform == "win32":
        if _wunsch != "mute" and _kabel_vorhanden():
            return WINCABLE
        if _wunsch != "cable" and _stummweg() is not None:
            return WINMUTE
    return None


def available() -> bool:
    return backend() is not None


def uses_routing(args) -> bool:
    """Ob dieser Lauf ueber den stummen Umweg laeuft.

    Eine EINZIGE Stelle, weil `--output` je nach Antwort etwas anderes ist: ein
    Sink-Name hier, ein PortAudio-Geraet dort. Rechnete die Geraetepruefung
    anders als der Aufbau, pruefte sie das Falsche - und wies genau die
    Sink-Namen ab, die die eigene Hilfe nennt.
    """
    return available() and not args.no_route and args.input is None


def create(args):
    """Die Umleitung dieses Rechners - als Kontextmanager."""
    gewaehlt = backend()
    if gewaehlt == WINMUTE:
        return WindowsMuteRouting(args)
    if gewaehlt == WINCABLE:
        return WindowsRouting(args)
    return LinuxRouting(args)


def current_output() -> str:
    """Wie der Standard-Ausgang gerade heisst - fuer `jampilot cleanup`."""
    if backend() in (WINMUTE, WINCABLE):
        from . import winaudio

        ziel = winaudio.standard(winaudio.RENDER)
        return ziel.name if ziel else "(none)"
    return _pactl("get-default-sink")


def _pactl(*args: str) -> str:
    # pactl uebersetzt seine Ausgabe: aus "Sink Input #7" wird in einer
    # portugiesischen Sitzung "Entrada do destino #7". Wir LESEN diese Ausgabe
    # (siehe _find_own_stream), also muss sie englisch bleiben. Sonst laeuft
    # JamPilot aus einem englischen Terminal - und stirbt per Doppelklick, weil
    # es dann das Locale der Sitzung erbt.
    result = subprocess.run(
        ["pactl", *args], capture_output=True, text=True, timeout=5,
        env={**os.environ, "LC_ALL": "C", "LANGUAGE": "C"},
    )
    if result.returncode != 0:
        raise RuntimeError(f"pactl {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def _alive_windows(pid: int) -> bool:
    """Laeuft dieser Prozess noch? - die Windows-Antwort.

    os.kill(pid, 0) waere hier KEINE Frage, sondern ein Todesurteil: Unter
    Windows ruft os.kill fuer alles ausser CTRL_C_EVENT/CTRL_BREAK_EVENT in
    Wahrheit TerminateProcess auf. Die Lebendpruefung braechte ihr Opfer um.

    Statt dessen OpenProcess mit dem kleinstmoeglichen Recht. Scheitert es mit
    ERROR_INVALID_PARAMETER, gibt es die PID nicht mehr; scheitert es mit
    ERROR_ACCESS_DENIED, gibt es sie sehr wohl (sie gehoert nur jemand
    anderem). Und ein offener Handle allein heisst noch nicht "lebt": Ein
    beendeter Prozess bleibt als Leiche offenbar, solange irgendwer einen
    Handle haelt. Deshalb zusaetzlich der Exitcode - STILL_ACTIVE (259) ist die
    einzige Antwort, die wirklich "laeuft" bedeutet.
    """
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    ERROR_INVALID_PARAMETER = 87
    STILL_ACTIVE = 259

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return kernel32.GetLastError() != ERROR_INVALID_PARAMETER
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True          # nicht zu ermitteln - lieber "lebt"
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _alive(pid: int) -> bool:
    if os.name != "posix":
        return _alive_windows(pid)
    try:
        os.kill(pid, 0)          # Signal 0 stellt nur zu, es passiert nichts
    except ProcessLookupError:
        return False
    except PermissionError:
        return True              # fremder Nutzer - lebt, gehoert uns aber nicht
    return True


def owner_pid() -> int | None:
    """PID der Instanz, der der laufende Null-Sink gehoert - oder None."""
    try:
        pid = int(LOCK_FILE.read_text().strip())
    except (OSError, ValueError):
        return None
    return pid if _alive(pid) else None


def sink_modules() -> list[str]:
    ids = []
    for line in _pactl("list", "short", "modules").splitlines():
        if "module-null-sink" in line and f"sink_name={SINK_NAME}" in line:
            ids.append(line.split("\t")[0])
    return ids


def hardware_sinks() -> list[tuple[str, str]]:
    """(Index, Name) aller Ausgaenge ausser unserem eigenen Null-Sink.

    Der Null-Sink ist als Ziel naemlich kein Ausgang, sondern das Gegenteil:
    Wer dorthin ausgibt, gibt in genau den Eimer aus, den wir abhoeren.
    """
    sinks = []
    for line in _pactl("list", "short", "sinks").splitlines():
        felder = line.split("\t")
        if len(felder) >= 2 and felder[1] != SINK_NAME:
            sinks.append((felder[0], felder[1]))
    return sinks


def _first_hardware_sink() -> str | None:
    sinks = hardware_sinks()
    return sinks[0][1] if sinks else None


# --- Windows: das virtuelle Kabel -------------------------------------------

# VB-CABLE meldet sich mit festen Namen an: "CABLE Input (VB-Audio Virtual
# Cable)" ist die Wiedergabeseite (dorthin spielt alles), "CABLE Output
# (VB-Audio Virtual Cable)" die Aufnahmeseite desselben Rohrs (von dort lesen
# wir). Die Zusatzpakete bringen "CABLE-A", "CABLE-B" und "CABLE In 16ch" mit;
# gemeint ist immer das schlichte Paar, deshalb wird auf "Input"/"Output"
# geprueft und nicht bloss auf "CABLE".
_KABEL_EIN = re.compile(r"^CABLE(-[A-Z])? Input\b")
_KABEL_AUS = re.compile(r"^CABLE(-[A-Z])? Output\b")

_kabel_cache = _UNSET


def _kabel(neu_pruefen: bool = False):
    """Das Kabelpaar (Wiedergabeseite, Aufnahmeseite) - oder None.

    Das Ergebnis wird gemerkt. Nicht aus Geschwindigkeit, sondern weil
    uses_routing() mehrfach pro Start gefragt wird und jede Antwort sonst eine
    COM-Aufzaehlung waere - und weil sich waehrend eines Laufs ohnehin nichts
    daran aendert, welche Treiber installiert sind.
    """
    global _kabel_cache
    if _kabel_cache is not _UNSET and not neu_pruefen:
        return _kabel_cache

    paar = None
    try:
        from . import winaudio

        ein = next((e for e in winaudio.endpunkte(winaudio.RENDER)
                    if _KABEL_EIN.match(e.name)), None)
        aus = next((e for e in winaudio.endpunkte(winaudio.CAPTURE)
                    if _KABEL_AUS.match(e.name)), None)
        if ein and aus:
            paar = (ein, aus)
    except Exception:
        # Kein Grund zu sterben: Ohne Kabel laeuft JamPilot im Direktmodus
        # weiter und sagt dem Nutzer, was ihm fehlt. Ein Traceback aus einer
        # COM-vtable saehe dagegen nach einem kaputten Programm aus.
        paar = None

    _kabel_cache = paar
    return paar


def _kabel_vorhanden() -> bool:
    return _kabel() is not None


def _portaudio_index(name: str, kind: str) -> int | None:
    """Den Core-Audio-Endpunkt `name` als PortAudio-Geraet wiederfinden.

    Zwei Namensraeume, ein Geraet. Ueber WASAPI fuehrt PortAudio jeden Endpunkt
    unter GENAU dem Anzeigenamen, den auch Core Audio nennt - darum wird exakt
    verglichen und nicht per Teilstring.

    Die Reihenfolge der Host-APIs ist dabei keine Geschmacksfrage:

    * WASAPI ist der Weg, den Windows selbst geht, und der einzige, der die
      Kanalzahl ehrlich meldet. Das Kabel steht dort mit 2 Kanaelen.
    * MME und DirectSound sind Emulationen darueber. MME kuerzt Namen auf 31
      Zeichen ("CABLE Output (VB-Audio Virtual "), scheidet beim exakten
      Vergleich also von selbst aus - was gut ist, denn MME meldet fuer
      dasselbe Kabel 16 Kanaele und legt damit einen Stream an, den niemand
      hoeren will.

    Ohne diese Aufloesung muesste der Nutzer `--input 23` tippen, und ein
    Teilstring wie "CABLE Output" waere mehrdeutig: sounddevice findet ihn in
    vier Host-APIs und lehnt mit "Multiple input devices found" ab.
    """
    import sounddevice as sd

    apis = sd.query_hostapis()
    bevorzugt = ["Windows WASAPI", "Windows DirectSound", "MME"]
    reihenfolge = sorted(
        range(len(apis)),
        key=lambda i: bevorzugt.index(apis[i]["name"])
        if apis[i]["name"] in bevorzugt else len(bevorzugt),
    )

    geraete = sd.query_devices()
    spalte = f"max_{kind}_channels"
    for api in reihenfolge:
        for index, geraet in enumerate(geraete):
            if (geraet["hostapi"] == api and geraet["name"] == name
                    and geraet[spalte] >= 2):
                return index
    return None


def _echte_wiedergabe():
    """Ein Ausgang, der KEIN Kabel ist - Notnagel fuer zwei Faelle.

    Erstens: Wer JamPilot bisher von Hand benutzt hat, hat seinen Systemton
    selbst auf CABLE Input gestellt. Dann ist der "vorherige" Ausgang das
    Kabel, und darauf auszugeben hiesse, in genau das Rohr zu spielen, das wir
    abhoeren - eine Rueckkopplung, die man als Stille erlebt.

    Zweitens: dasselbe nach einem Absturz, bei dem die Umstellung stehenblieb.
    """
    from . import winaudio

    for endpunkt in winaudio.endpunkte(winaudio.RENDER):
        if not _KABEL_EIN.match(endpunkt.name) and "VB-Audio" not in endpunkt.name:
            return endpunkt
    return None


def windows_playback_target():
    """Wohin die verzoegerte Ausgabe geht: der Ausgang, der VOR uns Standard war.

    Dieselbe Wahl wie LinuxRouting mit `previous_sink` - der Nutzer hoert
    weiter da, wo er vorher gehoert hat. Nur wenn dort schon das Kabel steht,
    muss ein anderer Ausgang her.

    Eine Funktion, weil zwei Stellen sie brauchen: der Aufbau, der das Geraet
    oeffnet, und `jampilot devices`, das ANKUENDIGT, welches geoeffnet wuerde.
    Zwei Antworten auf dieselbe Frage waeren zwei Antworten zu viel.
    """
    from . import winaudio

    ziel = winaudio.standard(winaudio.RENDER, winaudio.CONSOLE)
    if ziel is None or _KABEL_EIN.match(ziel.name):
        ziel = _echte_wiedergabe()
    return ziel


# --- Windows: ein stummgeschalteter Endpunkt als Umweg (ohne Kabel) ---------
#
# DIE ROLLEN, weil man sie genau einmal verwechseln muss, um alles kaputt zu
# machen (und das ist passiert):
#
#     Umweg    das Geraet, in das die Player unhoerbar spielen. Beim Kabelweg
#              ist das CABLE Input. Hier ist es ein ECHTER zweiter Endpunkt,
#              den wir stummschalten - der Mute ersetzt den Treiber, nicht das
#              Umschalten des Standardgeraets.
#     Ausgabe  das Geraet, auf dem der Nutzer HOERT - also das, was vor dem
#              Start Standard war. Dorthin geht das verzoegerte Signal, und
#              genau dieses Geraet darf niemals stumm werden.
#
# Was der Weg spart, ist damit genau eine Sache: die Installation. Umgebogen
# und zurueckgebogen wird wie beim Kabel.

_stummweg_cache = _UNSET

def _umwegkandidaten(ausgabe):
    """Endpunkte, die als stummer Umweg taugen - beste zuerst.

    Ausgeschlossen sind zwei, und beide aus demselben Grund: Dort hoert jemand
    zu. Das ist der Standard-Ausgang selbst (dorthin geben WIR aus) und das
    Telefoniegeraet (dort laeuft Teams; ein stummes Headset mitten im Gespraech
    waere ein Fehler, den niemand bei einem Akkordanzeiger suchte).

    Sortiert wird nach dem FORMFAKTOR und nicht nach dem Namen. Der Mute macht
    zwar jeden Endpunkt still, aber einen Kopfhoerer zum Umweg zu machen hiesse,
    dass jemand, der ihn waehrend des Laufs aufsetzt, Stille hoert - ein
    Bildschirmausgang stoert dagegen niemanden. Am Namen ist das nicht
    abzulesen: Der HDMI-Ausgang heisst hier "LEN LT2452pwC (NVIDIA High
    Definition Audio)", und ein virtuelles Kabel heisst, wie sein Hersteller
    will. Windows fuehrt die Antwort als Eigenschaft, also wird sie gefragt.
    """
    from . import winaudio

    # Je kleiner, desto lieber. Virtuelle Kabel zuerst: Aus denen kommt per
    # Bauart nichts heraus, da braucht es nicht einmal den Mute.
    rang = {winaudio.FF_SPDIF: 1, winaudio.FF_HDMI: 1,
            winaudio.FF_DIGITAL_DURCHREICHUNG: 1}

    def gewicht(endpunkt):
        if _KABEL_EIN.match(endpunkt.name) or "VB-Audio" in endpunkt.name:
            return 0
        return rang.get(endpunkt.formfaktor, 2)

    telefonie = winaudio.standard(winaudio.RENDER, winaudio.COMMUNICATIONS)
    frei = [e for e in winaudio.endpunkte(winaudio.RENDER)
            if e != ausgabe and e != telefonie]
    return sorted(frei, key=gewicht)


def _stummweg(neu_pruefen: bool = False):
    """(Umweg-Endpunkt, Ausgabe-Endpunkt) - oder None.

    None heisst: Dieser Rechner kann den Weg nicht. Es gibt keinen
    Standard-Ausgang, es gibt keinen zweiten Endpunkt fuer den Umweg, oder auf
    keinem davon ueberlebt der Mitschnitt die Stummschaltung. Der letzte Punkt
    ist der einzige, den man nicht nachschlagen kann: Ob der Mute vor oder
    hinter dem Loopback-Abgriff sitzt, entscheidet der Treiber - deshalb wird
    jeder Kandidat gemessen, bis einer traegt.

    Das Ergebnis wird gemerkt. Nicht aus Geschwindigkeit: Jede Messung schaltet
    kurz stumm, und uses_routing() wird mehrfach pro Start gefragt.
    """
    global _stummweg_cache
    if _stummweg_cache is not _UNSET and not neu_pruefen:
        return _stummweg_cache

    weg = None
    try:
        from . import winaudio, wincapture

        ausgabe = winaudio.standard(winaudio.RENDER, winaudio.CONSOLE)
        if ausgabe is not None:
            for kandidat in _umwegkandidaten(ausgabe):
                if wincapture.pruefen(kandidat.kennung):
                    weg = (kandidat, ausgabe)
                    break
    except Exception:
        # Kein Grund zu sterben: Ohne diesen Weg bleibt der Kabelweg, und ohne
        # den bleibt der Direktmodus. Ein Traceback aus einer COM-vtable saehe
        # dagegen nach einem kaputten Programm aus.
        weg = None

    _stummweg_cache = weg
    return weg


class WindowsMuteRouting:
    """Kontextmanager: zweiten Endpunkt stumm schalten und zum Umweg machen.

    Schritt fuer Schritt dasselbe Stueck wie WindowsRouting - nur dass der
    Umweg kein installierter Treiber ist, sondern ein Geraet, das ohnehin da
    ist und dem wir den Ton abdrehen:

        Kabelweg                        Mute-Weg
        (VB-CABLE ist schon stumm)      setze_stumm(Umweg, True)
        setze_standard(CABLE Input)     setze_standard(Umweg)
        Capture liest CABLE Output      wincapture.Loopback auf dem Umweg
        Ausgabe -> vorheriger Standard  Ausgabe -> vorheriger Standard

    Die letzte Zeile ist die wichtigste: Der Nutzer hoert weiter da, wo er
    vorher gehoert hat. Der stumme Endpunkt ist der UMWEG, nicht das
    Hoergeraet - wer das vertauscht, dreht dem Nutzer den Ton ab und spielt
    die Musik auf ein Geraet, an dem niemand sitzt.

    WAS DER MUTE BRINGT: Ohne ihn taugte als Umweg nur ein Endpunkt, aus dem
    ohnehin nichts herauskommt (HDMI ohne Lautsprecher, ungenutztes S/PDIF).
    Mit ihm taugt jeder zweite Endpunkt, auch einer, an dem ein Fernseher
    haengt. Das ist der ganze Unterschied zum Treiber - und der Grund, warum
    hier nichts zu installieren ist.

    ALLES WIRD AUFGELOEST, BEVOR ETWAS UMGESTELLT WIRD. Ein fehlendes Geraet
    soll an einem Rechner scheitern, der noch Ton hat.
    """

    capture_device = None       # der Mitschnitt kommt nicht von PortAudio

    def __init__(self, args=None):
        self.args = args
        self.umweg = None            # Endpunkt, der stumm und Standard wird
        self.ausgabe = None          # wo gehoert wird - der vorherige Standard
        self.capture_source = None   # wincapture.Loopback auf dem Umweg
        self.playback_device = None  # PortAudio-Index der Ausgabe
        self.samplerate = None       # das Mixformat des Umwegs gibt sie vor
        self._war_stumm = False
        self._undo = []

    def __enter__(self):
        from . import winaudio, wincapture

        try:
            # Waisen zuerst - sonst merkt sich `ausgabe` womoeglich den Umweg
            # eines abgestuerzten Laufs, und wir gaeben die Musik auf ein
            # stummgeschaltetes Geraet aus.
            cleanup()

            weg = _stummweg(neu_pruefen=True)
            if weg is None:
                raise RuntimeError(
                    "No endpoint can serve as the silent detour (needs a "
                    "second playback device whose capture survives muting).")
            self.umweg, self.ausgabe = weg

            gewuenscht = getattr(self.args, "output", None)
            if gewuenscht is not None:
                self.playback_device = gewuenscht
            else:
                self.playback_device = _portaudio_index(self.ausgabe.name, "output")
                if self.playback_device is None:
                    raise RuntimeError(
                        f"{self.ausgabe.name!r} is a Windows playback device "
                        f"but PortAudio does not offer it in stereo. Pass "
                        f"--output to pick another one; 'jampilot devices' "
                        f"lists them.")

            self._war_stumm = winaudio.stumm(self.umweg.kennung)

            # ERST merken, DANN umstellen. Andersherum gaebe es ein Fenster, in
            # dem der Umweg Standard und stumm ist und niemand mehr weiss, was
            # vorher galt - ein Absturz genau dort liesse einen stummen Rechner
            # zurueck, den auch der naechste Start nicht mehr reparieren
            # koennte.
            STATE_FILE.write_text(json.dumps({
                "previous": self.ausgabe.kennung,
                "previous_name": self.ausgabe.name,
                "umweg": self.umweg.kennung,
                "muted": self.umweg.kennung,
                "muted_name": self.umweg.name,
                "war_stumm": self._war_stumm,
            }))
            LOCK_FILE.write_text(str(os.getpid()))
            self._undo.append(self._vermerke_loeschen)

            # Stumm VOR dem Umschalten: Andersherum liefe der Systemton fuer
            # einen Wimpernschlag hoerbar auf den Umweg - bei einem Fernseher
            # am HDMI-Ausgang ein Schreck, kein Schoenheitsfehler.
            winaudio.setze_stumm(self.umweg.kennung, True)
            self._undo.append(self._stumm_zurueck)

            winaudio.setze_standard(self.umweg.kennung)
            self._undo.append(self._standard_zurueck)

            self.capture_source = wincapture.Loopback(self.umweg.kennung,
                                                      self.umweg.name)
            self._undo.append(self.capture_source.close)
            self.samplerate = self.capture_source.samplerate
        except BaseException:
            self._rollback()
            raise
        return self

    def after_start(self):
        """Nichts zu tun - die Ausgabe haengt schon am richtigen Geraet."""

    def _vermerke_loeschen(self):
        from . import winaudio

        LOCK_FILE.unlink(missing_ok=True)
        # Der Vermerk bleibt liegen, WENN etwas nicht zurueckgenommen werden
        # konnte: Dann ist er das Einzige, woraus `jampilot cleanup` noch
        # erfahren kann, was zu tun ist.
        try:
            jetzt = winaudio.standard(winaudio.RENDER, winaudio.CONSOLE)
            offen = ((jetzt is not None and jetzt.kennung == self.umweg.kennung)
                     or (not self._war_stumm
                         and winaudio.stumm(self.umweg.kennung)))
        except Exception:
            offen = False
        if not offen:
            STATE_FILE.unlink(missing_ok=True)

    def _standard_zurueck(self):
        from . import winaudio

        # Nur zurueckstellen, wenn WIR noch stehen. Hat der Nutzer waehrend des
        # Laufs selbst umgestellt, ist seine Wahl die juengere.
        jetzt = winaudio.standard(winaudio.RENDER, winaudio.CONSOLE)
        if jetzt is not None and jetzt.kennung != self.umweg.kennung:
            return
        winaudio.setze_standard(self.ausgabe.kennung)

    def _stumm_zurueck(self):
        from . import winaudio

        if self._war_stumm:
            return          # der Nutzer hatte selbst stummgeschaltet
        winaudio.setze_stumm(self.umweg.kennung, False)

    def _rollback(self):
        # Rueckwaerts: Mitschnitt zu, Standard zurueck, entstummen, Vermerke
        # weg. Ein scheiternder Schritt darf die uebrigen nicht verhindern -
        # sonst bleibt ausgerechnet der Standard auf einem stummen Geraet.
        while self._undo:
            step = self._undo.pop()
            try:
                step()
            except Exception as exc:
                print(f"Warning: cleanup incomplete ({exc}). "
                      f"'jampilot cleanup' resets the rest.",
                      file=sys.stderr)

    def __exit__(self, *exc):
        self._rollback()
        return False


def _cleanup_windows() -> int:
    """Zuruecknehmen, was ein abgestuerzter Lauf hinterlassen hat - beide Wege.

    WELCHER Weg lief, sagt der Vermerk und nicht das heutige backend(): Zwischen
    dem Absturz und dem Aufraeumen kann sich der Rechner geaendert haben (der
    Kopfhoerer ist ab, das Kabel deinstalliert), und eine Fallunterscheidung
    nach backend() raeumte dann ausgerechnet das Falsche weg - oder gar nichts.
    """
    try:
        gemerkt = json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        gemerkt = {}
    STATE_FILE.unlink(missing_ok=True)
    LOCK_FILE.unlink(missing_ok=True)

    if gemerkt.get("muted"):
        return _stummschaltung_zurueck(gemerkt)
    return _kabel_zurueck(gemerkt)


def _stummschaltung_zurueck(gemerkt: dict) -> int:
    """Den Mute-Umweg zuruecknehmen, den ein abgestuerzter Lauf stehen liess.

    ZWEI Dinge, und sie sind unabhaengig voneinander: Der Standard-Ausgang
    haengt womoeglich noch auf dem Umweg (dann hoert der Nutzer gar nichts),
    und der Umweg ist womoeglich noch stumm (dann hoert er auch nichts, wenn er
    von Hand zurueckstellt). Beides wird einzeln geprueft, denn ein abgebrochener
    Rueckbau kann genau eines von beiden hinterlassen haben.

    Zwei Faelle bleiben ausdruecklich liegen: Der Nutzer hatte den Umweg schon
    vorher selbst stumm (`war_stumm`), oder er hat laengst selbst
    zurueckgestellt. Fremde Entscheidungen ueberschreibt man nicht, auch nicht
    mit guten Absichten.
    """
    from . import winaudio

    umweg = gemerkt.get("umweg") or gemerkt.get("muted")
    getan = 0

    try:
        jetzt = winaudio.standard(winaudio.RENDER, winaudio.CONSOLE)
        if jetzt is not None and jetzt.kennung == umweg:
            aktive = {e.kennung: e for e in winaudio.endpunkte(winaudio.RENDER)}
            ziel = gemerkt.get("previous")
            if ziel not in aktive:
                # Das gemerkte Hoergeraet ist weg (Kopfhoerer abgezogen).
                # Irgendein Ausgang, der nicht der stumme Umweg ist, ist immer
                # noch besser als gar keiner.
                ersatz = next((k for k in aktive if k != umweg), None)
                ziel = ersatz
            if ziel:
                winaudio.setze_standard(ziel)
                getan = 1
    except Exception:
        pass            # Core Audio streikt - der Mute-Teil unten zaehlt trotzdem

    if umweg and not gemerkt.get("war_stumm"):
        try:
            if winaudio.stumm(umweg):
                winaudio.setze_stumm(umweg, False)
                getan = 1
        except Exception:
            pass        # Geraet abgezogen - dann ist auch nichts stumm
    return getan


def _kabel_zurueck(gemerkt: dict) -> int:
    """Den Standard-Ausgang zurueckholen, wenn er noch am Kabel haengt.

    Die Bedingung ist wichtiger als das Zurueckstellen: Steht der Standard
    NICHT auf dem Kabel, hat entweder nie eine Umleitung gestanden oder der
    Nutzer hat sie laengst selbst korrigiert. In beiden Faellen waere es
    uebergriffig, ihm jetzt ein Geraet von vorgestern unterzuschieben.
    """
    from . import winaudio

    jetzt = winaudio.standard(winaudio.RENDER)
    if jetzt is None or not _KABEL_EIN.match(jetzt.name):
        return 0

    aktive = {e.kennung: e for e in winaudio.endpunkte(winaudio.RENDER)}
    ziel = aktive.get(gemerkt.get("previous"))
    if ziel is None:
        # Der gemerkte Ausgang ist weg (Kopfhoerer abgezogen, anderer Rechner
        # nach einem Profilwechsel) oder es gab nie einen Vermerk. Irgendein
        # echter Ausgang ist immer noch besser als ein stummer.
        ziel = _echte_wiedergabe()
    if ziel is None:
        return 0
    winaudio.setze_standard(ziel.kennung)
    return 1


def cleanup(force: bool = False) -> int:
    """Raeumt weg, was ein abgestuerzter Lauf hinterlassen hat.

    Verwaist heisst: der Prozess, der die Umleitung aufgebaut hat, lebt nicht
    mehr. Ohne diese Pruefung wuerde eine zweite Instanz der laufenden ersten
    den Boden wegziehen - und beide riefen sich gegenseitig das Routing kaputt.
    `force=True` raeumt auch dann, wenn kein Besitzer eingetragen ist (etwa
    nach einem Lauf aus einer aelteren Version).

    Rueckgabe: wie viel zurueckgenommen wurde (0 = es war nichts zu tun).
    """
    pid = owner_pid()
    if pid is not None and pid != os.getpid() and not force:
        raise InstanceRunning(pid)
    # Der Pulse-Weg braucht pactl, also entscheidet ihn backend(). Alles andere
    # unter Windows raeumt _cleanup_windows - und zwar auch dann, wenn backend()
    # gerade None sagt: Der Weg, der den Rest hinterlassen hat, muss heute nicht
    # mehr zur Verfuegung stehen (Kopfhoerer ab, Kabel deinstalliert).
    if backend() == PULSE:
        return _cleanup_pulse()
    return _cleanup_windows() if sys.platform == "win32" else 0


def _cleanup_pulse() -> int:
    ids = sink_modules()
    for module_id in ids:
        _pactl("unload-module", module_id)
    LOCK_FILE.unlink(missing_ok=True)

    # Der Standard-Sink zeigt nach einem Absturz womoeglich noch auf den
    # (jetzt entladenen) Null-Sink - dann waehlt nicht jede Implementierung
    # von selbst einen brauchbaren Ersatz.
    if _pactl("get-default-sink") == SINK_NAME:
        fallback = _first_hardware_sink()
        if fallback:
            _pactl("set-default-sink", fallback)
    return len(ids)


class LinuxRouting:
    """Kontextmanager: Null-Sink einrichten und beim Verlassen zuruecksetzen.

    Jeder Schritt wird registriert, bevor der naechste laeuft. Scheitert einer,
    wird alles Vorherige rueckwaerts zurueckgenommen - sonst bliebe der stumme
    Null-Sink als Standard-Ausgang stehen und der Rechner haette keinen Ton
    mehr. `with` ruft `__exit__` naemlich nicht auf, wenn `__enter__` fliegt.

    Was der Stream danach oeffnen soll, sagt die Umleitung selbst
    (`capture_device`/`playback_device`) - hier beides "default", weil das
    Umbiegen ueber die Standardgeraete laeuft und nicht ueber die Geraetewahl.
    Unter Windows ist es andersherum, siehe WindowsRouting.
    """

    capture_device = "default"
    playback_device = "default"

    def __init__(self, args=None):
        self.args = args
        self.previous_sink = None
        self.previous_source = None
        self.module_id = None
        self._undo = []

    def __enter__(self):
        try:
            # Waisen zuerst - sonst merkt sich `previous_sink` womoeglich den
            # Null-Sink eines abgestuerzten Laufs und wir "stellen" beim Beenden
            # genau die Stummschaltung wieder her, die wir beheben wollten.
            # Laeuft dagegen eine echte zweite Instanz, bricht cleanup() hier
            # mit InstanceRunning ab, statt ihr den Sink wegzuziehen.
            cleanup()

            self.previous_sink = _pactl("get-default-sink")
            self.previous_source = _pactl("get-default-source")

            self.module_id = _pactl(
                "load-module", "module-null-sink",
                f"sink_name={SINK_NAME}",
                "sink_properties=device.description=JamPilot-Systemaudio",
            )
            self._undo.append(lambda: _pactl("unload-module", self.module_id))

            # Besitz anmelden, sobald der Sink existiert: ab jetzt weiss eine
            # zweite Instanz, dass er nicht verwaist ist.
            LOCK_FILE.write_text(str(os.getpid()))
            self._undo.append(lambda: LOCK_FILE.unlink(missing_ok=True))

            # Player spielen ab jetzt unhoerbar in den Null-Sink; unser
            # Capture-Stream ("default"-Quelle) liest dessen Monitor.
            _pactl("set-default-sink", SINK_NAME)
            self._undo.append(lambda: _pactl("set-default-sink", self.previous_sink))

            _pactl("set-default-source", f"{SINK_NAME}.monitor")
            self._undo.append(
                lambda: _pactl("set-default-source", self.previous_source)
            )

            # PipeWire-ALSA setzt keine PID-Property; ueber den Namen finden
            # wir unseren Wiedergabe-Stream fuer move_own_playback_to wieder.
            previous_props = os.environ.get("PIPEWIRE_PROPS", _UNSET)
            os.environ["PIPEWIRE_PROPS"] = f'{{ application.name = "{APP_NAME}" }}'
            self._undo.append(lambda: _restore_env("PIPEWIRE_PROPS", previous_props))
        except Exception:
            self._rollback()
            raise
        return self

    def after_start(self):
        """Nach dem Start des Streams: die eigene Ausgabe auf die Hardware."""
        self.move_own_playback_to(getattr(self.args, "output", None))

    def move_own_playback_to(self, sink: str | None = None):
        """Verschiebt den Wiedergabe-Stream dieses Prozesses auf die echte
        Hardware (sonst landet die verzoegerte Ausgabe im Null-Sink)."""
        target = sink or self.previous_sink
        deadline = time.monotonic() + 3.0
        while True:
            stream_id = self._find_own_stream()
            if stream_id is not None:
                break
            if time.monotonic() > deadline:
                raise RuntimeError("Could not find our own playback stream.")
            time.sleep(0.2)
        _pactl("move-sink-input", stream_id, target)

    @staticmethod
    def _find_own_stream() -> str | None:
        output = _pactl("list", "sink-inputs")
        current = None
        for line in output.splitlines():
            header = re.match(r"Sink Input #(\d+)", line.strip())
            if header:
                current = header.group(1)
            elif f'application.name = "{APP_NAME}"' in line:
                return current
        return None

    def _rollback(self):
        # Rueckwaerts: erst den Standard-Ausgang zurueckholen, dann den Null-Sink
        # entladen. Ein scheiternder Schritt darf die uebrigen nicht verhindern -
        # sonst bleibt beim Aufraeumen ausgerechnet das Modul haengen.
        while self._undo:
            step = self._undo.pop()
            try:
                step()
            except Exception as exc:
                print(f"Warning: cleanup incomplete ({exc}). "
                      f"'jampilot cleanup' resets the rest.",
                      file=sys.stderr)

    def __exit__(self, *exc):
        self._rollback()
        return False


def _restore_env(name: str, previous):
    if previous is _UNSET:
        os.environ.pop(name, None)
    else:
        os.environ[name] = previous


class WindowsRouting:
    """Kontextmanager: VB-CABLE zum Standard-Ausgang machen und zuruecknehmen.

    Das Gegenstueck zu LinuxRouting, Schritt fuer Schritt dasselbe Stueck:

        Linux                           Windows
        module-null-sink laden          entfaellt - das Kabel ist schon da
        set-default-sink jampilot       setze_standard(CABLE Input)
        Capture liest den Monitor       Capture liest CABLE Output
        move_own_playback_to(hardware)  Ausgabe direkt auf die Hardware

    Der letzte Punkt ist der einzige echte Unterschied, und er macht die Sache
    EINFACHER: PortAudio bindet den Ausgabestream an ein festes Geraet, nicht
    an "was gerade Standard ist". Unser eigener Ton laeuft also von vornherein
    an der Umleitung vorbei - unter Linux muss er ihr nachtraeglich entrissen
    werden.

    WELCHE GERAETE (und warum in dieser Reihenfolge entschieden wird):

        Ausgabe   `--output`, sonst der Ausgang, der VOR uns Standard war -
                  genau wie LinuxRouting mit `previous_sink`. Ist das schon das
                  Kabel (der Nutzer hatte von Hand umgestellt), waere das eine
                  Rueckkopplung; dann greift _echte_wiedergabe().
        Eingang   die Aufnahmeseite des Kabels. Nicht verhandelbar - das ist
                  die ganze Idee.

    ALLES WIRD AUFGELOEST, BEVOR ETWAS UMGESTELLT WIRD. Ein fehlendes Geraet
    soll an einem Rechner scheitern, der noch Ton hat.
    """

    def __init__(self, args=None):
        self.args = args
        self.previous = None          # winaudio.Endpunkt vor der Umstellung
        self.capture_device = None    # PortAudio-Index
        self.playback_device = None
        self._undo = []

    def __enter__(self):
        from . import winaudio

        try:
            # Waisen zuerst - sonst merkt sich `previous` womoeglich das Kabel
            # aus einem abgestuerzten Lauf, und beim Beenden "stellen" wir
            # genau die Stummschaltung wieder her, die wir beheben wollten.
            cleanup()

            paar = _kabel(neu_pruefen=True)
            if paar is None:
                # Zwischen der Wahl des Verfahrens und hier ist der Treiber
                # verschwunden. Kaum je, aber das Auspacken von None waere ein
                # TypeError statt einer Auskunft.
                raise RuntimeError(
                    "VB-CABLE is gone (uninstalled or disabled while running)."
                )
            kabel_ein, kabel_aus = paar
            self.previous = winaudio.standard(winaudio.RENDER, winaudio.CONSOLE)

            gewuenscht = getattr(self.args, "output", None)
            if gewuenscht is not None:
                # Wer `--output` angibt, braucht keinen brauchbaren
                # Standard-Ausgang - danach wird also gar nicht erst gesucht.
                self.playback_device = gewuenscht
            else:
                ziel = windows_playback_target()
                if ziel is None:
                    raise RuntimeError(
                        "No real playback device found - only the VB-CABLE "
                        "endpoints are active. Plug in speakers or headphones."
                    )
                self.playback_device = _portaudio_index(ziel.name, "output")
                if self.playback_device is None:
                    raise RuntimeError(
                        f"{ziel.name!r} is a Windows playback device but "
                        f"PortAudio does not offer it in stereo. Pass --output "
                        f"to pick another one; 'jampilot devices' lists them."
                    )

            self.capture_device = _portaudio_index(kabel_aus.name, "input")
            if self.capture_device is None:
                raise RuntimeError(
                    f"{kabel_aus.name!r} exists but PortAudio does not offer "
                    f"it. Reinstall VB-CABLE and reboot."
                )

            # ERST merken, DANN umstellen. Andersherum gaebe es ein Fenster, in
            # dem das Kabel Standard ist und niemand mehr weiss, was vorher galt
            # - ein Absturz genau dort liesse einen stummen Rechner zurueck, den
            # auch der naechste Start nicht mehr reparieren koennte.
            STATE_FILE.write_text(json.dumps({
                "previous": self.previous.kennung if self.previous else None,
                "previous_name": self.previous.name if self.previous else None,
            }))
            LOCK_FILE.write_text(str(os.getpid()))
            # EIN Ruecknahmeschritt fuer beide Vermerke, und er wird erst
            # angemeldet, wenn sie geschrieben sind. Wuerde stattdessen
            # bedingungslos aufgeraeumt, riebe ein Abbruch in cleanup() - dort
            # faellt InstanceRunning - die Sperrdatei einer LAUFENDEN zweiten
            # Instanz weg, und die beiden zerlegten sich gegenseitig.
            self._undo.append(self._vermerke_loeschen)

            winaudio.setze_standard(kabel_ein.kennung)
            self._undo.append(self._standard_zurueck)
        except BaseException:
            self._rollback()
            raise
        return self

    def after_start(self):
        """Nichts zu tun - die Ausgabe haengt schon am richtigen Geraet."""

    def _vermerke_loeschen(self):
        from . import winaudio

        LOCK_FILE.unlink(missing_ok=True)     # wir halten die Umleitung nicht mehr
        # Das Ziel dagegen bleibt liegen, WENN das Zurueckstellen nicht
        # geklappt hat: Dann haengt der Rechner noch am Kabel, und der Vermerk
        # ist das Einzige, woraus `jampilot cleanup` noch erfahren kann, wohin
        # der Ton eigentlich gehoert.
        jetzt = winaudio.standard(winaudio.RENDER, winaudio.CONSOLE)
        if jetzt is None or not _KABEL_EIN.match(jetzt.name):
            STATE_FILE.unlink(missing_ok=True)

    def _standard_zurueck(self):
        from . import winaudio

        if self.previous is None:
            return
        # Nur zurueckstellen, wenn WIR noch stehen. Hat der Nutzer waehrend des
        # Laufs selbst umgestellt (Kopfhoerer eingesteckt, Windows schaltet um),
        # ist seine Wahl die juengere - die ueberschreibt man nicht.
        jetzt = winaudio.standard(winaudio.RENDER, winaudio.CONSOLE)
        if jetzt is not None and not _KABEL_EIN.match(jetzt.name):
            return
        winaudio.setze_standard(self.previous.kennung)

    def _rollback(self):
        # Rueckwaerts: erst den Standard-Ausgang zurueckholen, dann die
        # Vermerke. Ein scheiternder Schritt darf die uebrigen nicht verhindern.
        while self._undo:
            step = self._undo.pop()
            try:
                step()
            except Exception as exc:
                print(f"Warning: cleanup incomplete ({exc}). "
                      f"'jampilot cleanup' resets the rest.",
                      file=sys.stderr)

    def __exit__(self, *exc):
        self._rollback()
        return False

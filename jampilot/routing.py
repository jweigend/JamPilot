"""Automatisches Audio-Routing unter Linux (PulseAudio/PipeWire).

Problem: Greift man den Monitor des Standard-Ausgangs ab und gibt verzoegert
auf denselben Ausgang aus, hoert man Original + Verzoegerung + Echo-Kaskade.

Loesung: Ein Null-Sink wird temporaer zum Standard-Ausgang. Player (YouTube,
Spotify, ...) spielen unhoerbar dorthin; wir capturen den Monitor des
Null-Sinks und geben nur das verzoegerte Signal auf die echte Hardware aus.

Unter macOS uebernimmt ein Loopback-Treiber (z.B. BlackHole) die Rolle des
Null-Sinks - dort ist kein automatisches Routing noetig, siehe README.
"""

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

# Merkt sich, WER den Null-Sink angelegt hat. Ohne diesen Besitzvermerk kann
# eine zweite Instanz den Sink einer noch laufenden ersten nicht von der Waise
# eines abgestuerzten Laufs unterscheiden.
LOCK_FILE = Path(tempfile.gettempdir()) / f"jampilot-{os.getuid()}.pid"

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


def available() -> bool:
    return shutil.which("pactl") is not None


def _pactl(*args: str) -> str:
    result = subprocess.run(
        ["pactl", *args], capture_output=True, text=True, timeout=5
    )
    if result.returncode != 0:
        raise RuntimeError(f"pactl {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def _alive(pid: int) -> bool:
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


def _first_hardware_sink() -> str | None:
    for line in _pactl("list", "short", "sinks").splitlines():
        name = line.split("\t")[1]
        if name != SINK_NAME:
            return name
    return None


def cleanup(force: bool = False) -> int:
    """Entfernt VERWAISTE Null-Sinks und holt den Standard-Ausgang zurueck.

    Verwaist heisst: der Prozess, der den Sink angelegt hat, lebt nicht mehr.
    Ohne diese Pruefung wuerde eine zweite Instanz den Sink einer laufenden
    ersten entladen - und beide riefen sich gegenseitig das Routing kaputt.
    `force=True` raeumt auch dann, wenn kein Besitzer eingetragen ist (etwa
    nach einem Sink aus einer aelteren Version).
    """
    pid = owner_pid()
    if pid is not None and pid != os.getpid() and not force:
        raise InstanceRunning(pid)

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
    """

    def __init__(self):
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

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
import time

SINK_NAME = "chordelay"
APP_NAME = "chordelay"


def available() -> bool:
    return shutil.which("pactl") is not None


def _pactl(*args: str) -> str:
    result = subprocess.run(
        ["pactl", *args], capture_output=True, text=True, timeout=5
    )
    if result.returncode != 0:
        raise RuntimeError(f"pactl {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


class LinuxRouting:
    """Kontextmanager: Null-Sink einrichten und beim Verlassen zuruecksetzen."""

    def __init__(self):
        self.previous_sink = None
        self.previous_source = None
        self.module_id = None

    def __enter__(self):
        self.previous_sink = _pactl("get-default-sink")
        self.previous_source = _pactl("get-default-source")
        self.module_id = _pactl(
            "load-module", "module-null-sink",
            f"sink_name={SINK_NAME}",
            "sink_properties=device.description=chordelay-Systemaudio",
        )
        # Player spielen ab jetzt unhoerbar in den Null-Sink; unser
        # Capture-Stream ("default"-Quelle) liest dessen Monitor.
        _pactl("set-default-sink", SINK_NAME)
        _pactl("set-default-source", f"{SINK_NAME}.monitor")
        # PipeWire-ALSA setzt keine PID-Property; ueber den Namen finden
        # wir unseren Wiedergabe-Stream fuer move_own_playback_to wieder.
        os.environ["PIPEWIRE_PROPS"] = f'{{ application.name = "{APP_NAME}" }}'
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
                raise RuntimeError("Eigener Wiedergabe-Stream nicht gefunden.")
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

    def __exit__(self, *exc):
        os.environ.pop("PIPEWIRE_PROPS", None)
        try:
            if self.previous_sink:
                _pactl("set-default-sink", self.previous_sink)
            if self.previous_source:
                _pactl("set-default-source", self.previous_source)
        finally:
            if self.module_id:
                _pactl("unload-module", self.module_id)
        return False

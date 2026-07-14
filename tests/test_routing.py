"""Routing: ein Fehler darf den Rechner nicht stumm zuruecklassen."""

import os
import subprocess

import pytest

from jampilot import routing


class FakeAudioSystem:
    """pactl inklusive Systemzustand - so laesst sich pruefen, was ein
    abgebrochener Lauf tatsaechlich hinterlaesst."""

    def __init__(self, fail_on=None):
        self.default_sink = "alsa_output.hardware"
        self.default_source = "alsa_input.mic"
        self.modules = {}
        self._next_id = 100
        self.fail_on = fail_on

    def __call__(self, *args):
        if self.fail_on and args[:2] == self.fail_on:
            raise RuntimeError(f"pactl {' '.join(args[:2])}: simulierter Fehler")
        cmd = args[0]
        if cmd == "get-default-sink":
            return self.default_sink
        if cmd == "get-default-source":
            return self.default_source
        if cmd == "set-default-sink":
            self.default_sink = args[1]
            return ""
        if cmd == "set-default-source":
            self.default_source = args[1]
            return ""
        if cmd == "load-module":
            module_id = str(self._next_id)
            self._next_id += 1
            self.modules[module_id] = args
            return module_id
        if cmd == "unload-module":
            self.modules.pop(args[1], None)
            return ""
        if args[:3] == ("list", "short", "modules"):
            return "\n".join(
                f"{k}\tmodule-null-sink\tsink_name={routing.SINK_NAME}"
                for k in self.modules)
        if args[:3] == ("list", "short", "sinks"):
            return f"0\talsa_output.hardware\n1\t{routing.SINK_NAME}"
        return ""

    @property
    def sauber(self):
        return (self.default_sink == "alsa_output.hardware"
                and self.default_source == "alsa_input.mic"
                and not self.modules)


@pytest.fixture
def audio(monkeypatch, tmp_path):
    system = FakeAudioSystem()
    monkeypatch.setattr(routing, "_pactl", system)
    monkeypatch.setattr(routing, "LOCK_FILE", tmp_path / "jampilot.pid")
    monkeypatch.delenv("PIPEWIRE_PROPS", raising=False)
    return system


class TestRollback:
    def test_normaler_durchlauf_hinterlaesst_nichts(self, audio):
        with routing.LinuxRouting():
            assert audio.default_sink == routing.SINK_NAME   # waehrenddessen stumm
        assert audio.sauber

    @pytest.mark.parametrize("fail_on", [
        ("load-module", "module-null-sink"),
        ("set-default-sink", routing.SINK_NAME),
        ("set-default-source", f"{routing.SINK_NAME}.monitor"),
    ])
    def test_fehler_in_jedem_schritt_raeumt_vollstaendig_auf(self, audio, monkeypatch,
                                                             tmp_path, fail_on):
        # `with` ruft __exit__ NICHT auf, wenn __enter__ fliegt - ohne eigene
        # Ruecknahme bliebe der stumme Null-Sink der Standard-Ausgang.
        audio.fail_on = fail_on
        with pytest.raises(RuntimeError):
            with routing.LinuxRouting():
                pytest.fail("darf nicht erreicht werden")
        assert audio.sauber, f"Leck nach Fehler in {fail_on[0]}"

    def test_pipewire_props_wird_wiederhergestellt(self, audio, monkeypatch):
        monkeypatch.setenv("PIPEWIRE_PROPS", "vorher")
        with routing.LinuxRouting():
            assert os.environ["PIPEWIRE_PROPS"] != "vorher"
        assert os.environ["PIPEWIRE_PROPS"] == "vorher"


class TestWaisen:
    def test_abgestuerzter_lauf_wird_beim_start_aufgeraeumt(self, audio):
        audio.modules["99"] = ("load-module", "module-null-sink",
                               f"sink_name={routing.SINK_NAME}")
        audio.default_sink = routing.SINK_NAME          # Rechner ist stumm
        # Kein Besitzer eingetragen -> die Waise darf weg.
        with routing.LinuxRouting() as route:
            # Entscheidend: NICHT den Null-Sink als "vorherigen" Zustand merken,
            # sonst stellen wir beim Beenden die Stummschaltung wieder her.
            assert route.previous_sink == "alsa_output.hardware"
        assert audio.sauber

    def test_cleanup_holt_den_standard_ausgang_zurueck(self, audio):
        audio.modules["99"] = ("load-module", "module-null-sink",
                               f"sink_name={routing.SINK_NAME}")
        audio.default_sink = routing.SINK_NAME
        assert routing.cleanup() == 1
        assert audio.default_sink == "alsa_output.hardware"

    def test_cleanup_ohne_waisen(self, audio):
        assert routing.cleanup() == 0


class TestZweiteInstanz:
    def test_laufende_instanz_wird_nicht_abgeraeumt(self, audio, monkeypatch):
        # Erste Instanz laeuft und haelt den Sink.
        routing.LOCK_FILE.write_text("4242")
        monkeypatch.setattr(routing, "_alive", lambda pid: True)
        audio.modules["99"] = ("load-module", "module-null-sink",
                               f"sink_name={routing.SINK_NAME}")

        # Zweite Instanz startet: sie darf der ersten den Sink NICHT wegziehen.
        with pytest.raises(routing.InstanceRunning) as fehler:
            with routing.LinuxRouting():
                pytest.fail("zweite Instanz darf nicht starten")
        assert fehler.value.pid == 4242
        assert audio.modules, "Sink der laufenden Instanz darf nicht entladen werden"
        assert audio.default_sink == "alsa_output.hardware"

    def test_tote_pid_gilt_als_waise(self, audio, monkeypatch):
        routing.LOCK_FILE.write_text("999999")          # existiert sicher nicht
        monkeypatch.setattr(routing, "_alive", lambda pid: False)
        audio.modules["99"] = ("load-module", "module-null-sink",
                               f"sink_name={routing.SINK_NAME}")
        assert routing.owner_pid() is None
        assert routing.cleanup() == 1

    def test_force_raeumt_trotz_lebendem_besitzer(self, audio, monkeypatch):
        routing.LOCK_FILE.write_text("4242")
        monkeypatch.setattr(routing, "_alive", lambda pid: True)
        audio.modules["99"] = ("load-module", "module-null-sink",
                               f"sink_name={routing.SINK_NAME}")
        assert routing.cleanup(force=True) == 1

    def test_kaputte_lock_datei_blockiert_nicht(self, audio):
        routing.LOCK_FILE.write_text("kein-integer")
        assert routing.owner_pid() is None


class TestSprache:
    """pactl uebersetzt seine Ausgabe - wir lesen sie und muessen sie festnageln.

    Aus einem englischen Terminal gestartet fiel das nie auf. Per Doppelklick
    erbt JamPilot das Locale der Sitzung: in einer portugiesischen heisst der
    Kopf einer Stream-Liste "Entrada do destino #7" statt "Sink Input #7", das
    Muster greift nicht, und der eigene Stream bleibt unauffindbar.
    """

    def test_pactl_laeuft_immer_auf_englisch(self, monkeypatch):
        gesehen = {}

        def fake_run(cmd, **kwargs):
            gesehen.update(kwargs.get("env") or {})
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setenv("LC_ALL", "pt_BR.UTF-8")
        monkeypatch.setenv("LANGUAGE", "pt_BR:pt:en")
        monkeypatch.setattr(routing.subprocess, "run", fake_run)

        routing._pactl("list", "sink-inputs")

        assert gesehen["LC_ALL"] == "C"
        assert gesehen["LANGUAGE"] == "C"

    def test_eigener_stream_wird_auch_in_fremder_sitzung_gefunden(self, monkeypatch):
        # Die Ausgabe, die pactl unter LC_ALL=C liefert - also die, auf die wir
        # uns mit dem Locale-Riegel wieder verlassen koennen.
        monkeypatch.setattr(routing, "_pactl", lambda *a: (
            'Sink Input #12\n'
            '\tapplication.name = "spotify"\n'
            'Sink Input #13\n'
            f'\tapplication.name = "{routing.APP_NAME}"\n'
        ))
        assert routing.LinuxRouting._find_own_stream() == "13"

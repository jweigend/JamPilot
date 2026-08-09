"""CLI: Randfaelle der Dateianalyse und Argumentpruefung."""

import argparse
import struct
import threading
import wave
import sys

import numpy as np
import pytest

from jampilot import cli
from jampilot.selftest import SAMPLERATE, _chord


@pytest.fixture
def wav(tmp_path):
    def schreibe(sekunden: float, name="test.wav"):
        pfad = tmp_path / name
        samples = _chord([36, 48, 52, 55, 60], sekunden)
        with wave.open(str(pfad), "wb") as datei:
            datei.setnchannels(1)
            datei.setsampwidth(2)
            datei.setframerate(SAMPLERATE)
            datei.writeframes(b"".join(
                struct.pack("<h", int(np.clip(s, -1, 1) * 32000)) for s in samples))
        return pfad
    return schreibe


class TestAnalyze:
    def test_datei_von_genau_einer_fensterlaenge_wird_analysiert(self, wav, capsys):
        # range(0, len - window) ist bei len == window leer - die Datei wurde
        # frueher stillschweigend uebersprungen.
        cli.cmd_analyze(argparse.Namespace(file=str(wav(cli.ANALYSIS_WINDOW))))
        ausgabe = capsys.readouterr().out
        assert "C" in ausgabe, "Akkord der 1.5s-Datei fehlt"

    def test_letztes_vollstaendiges_fenster_faellt_nicht_raus(self, wav, capsys):
        # 2.5s = Fenster (1.5s) + genau zwei Hops (2x0.5s): das Fenster bei
        # 1.0s muss noch analysiert werden.
        cli.cmd_analyze(argparse.Namespace(file=str(wav(2.5))))
        zeilen = [z for z in capsys.readouterr().out.splitlines() if z.startswith("  ")]
        assert zeilen, "keine Analyse ausgegeben"

    def test_zu_kurze_datei_meldet_das_verstaendlich(self, wav, capsys):
        cli.cmd_analyze(argparse.Namespace(file=str(wav(0.5))))
        assert "shorter than the analysis window" in capsys.readouterr().out

    def test_zu_wenig_musik_raet_die_tonart_nicht(self, wav, capsys):
        # Ein einzelner Akkord ueber 2.5s legt keine Tonart fest. Statt eine zu
        # raten (und die Akkorde womoeglich falsch zu schreiben), sagt die
        # Ausgabe, dass sie unbestimmt ist - und bleibt beim Kreuz.
        cli.cmd_analyze(argparse.Namespace(file=str(wav(2.5))))
        ausgabe = capsys.readouterr().out
        assert "Key: undetermined" in ausgabe


class TestArgumentGrenzen:
    @pytest.mark.parametrize("wert", ["-5", "0.1", "999"])
    def test_unsinniger_delay_wird_abgelehnt(self, wert):
        pruefer = cli._bounded(float, 0.5, 30.0, "s")
        with pytest.raises(argparse.ArgumentTypeError):
            pruefer(wert)

    @pytest.mark.parametrize("wert", ["0.5", "4", "30"])
    def test_gueltiger_delay_geht_durch(self, wert):
        pruefer = cli._bounded(float, 0.5, 30.0, "s")
        assert pruefer(wert) == float(wert)

    @pytest.mark.parametrize("wert", ["80", "0", "70000"])
    def test_unsinniger_port_wird_abgelehnt(self, wert):
        pruefer = cli._bounded(int, 1024, 65535)
        with pytest.raises(argparse.ArgumentTypeError):
            pruefer(wert)

    def test_keine_zahl_wird_verstaendlich_gemeldet(self):
        pruefer = cli._bounded(float, 0.5, 30.0, "s")
        with pytest.raises(argparse.ArgumentTypeError, match="is not a number"):
            pruefer("viel")

    @pytest.mark.parametrize("wert", ["7999", "200000"])
    def test_unsinnige_samplerate_wird_abgelehnt(self, wert):
        pruefer = cli._bounded(int, 8000, 192000, " Hz")
        with pytest.raises(argparse.ArgumentTypeError):
            pruefer(wert)


def _args(**felder):
    return argparse.Namespace(**{"input": None, "output": None, "no_route": False,
                                 **felder})


# Was query_devices ueber ein Geraet liefert - die Pruefung liest davon nur die
# Kanalzahl und (fuer die Meldung) den Namen.
_stereo = {"name": "Kabel", "max_input_channels": 2, "max_output_channels": 2}


class TestGeraetepruefung:
    @pytest.fixture(autouse=True)
    def keine_umleitung(self, monkeypatch):
        """Standardfall: kein Routing - `--output` ist dann ein PortAudio-Geraet."""
        from jampilot import routing
        monkeypatch.setattr(routing, "backend", lambda: None)

    def test_unbekanntes_geraet_bricht_sofort_ab(self, monkeypatch):
        import sounddevice as sd

        def explodiere(device, kind):
            raise ValueError(f"kein Geraet {device!r}")
        monkeypatch.setattr(sd, "query_devices", explodiere)

        # Muss VOR dem teuren Warmup zuschlagen und verstaendlich sein.
        with pytest.raises(SystemExit, match="not usable"):
            cli._check_devices(_args(input="gibtsnicht"))

    def test_kein_geraet_angegeben_ist_in_ordnung(self, monkeypatch):
        import sounddevice as sd

        monkeypatch.setattr(sd, "query_devices",
                            lambda device=None, kind=None: _stereo)
        cli._check_devices(_args())      # darf nicht werfen

    def test_unter_linux_bleibt_das_standardgeraet_ungeprueft(self, monkeypatch):
        """Dort gibt engine.py die ALSA-Quelle "default" an, nicht PortAudios
        Standardgeraet. Es zu pruefen hiesse, etwas anderes zu pruefen als das,
        was gleich geoeffnet wird - und waere eine Verhaltensaenderung auf der
        Referenzplattform."""
        import sounddevice as sd

        def explodiere(device=None, kind=None):
            raise AssertionError("unter Linux darf hier nichts gefragt werden")

        monkeypatch.setattr(sys, "platform", "linux")
        monkeypatch.setattr(sd, "query_devices", explodiere)
        cli._check_devices(_args())      # darf nicht werfen

    def test_stereo_geraet_geht_durch(self, monkeypatch):
        import sounddevice as sd

        monkeypatch.setattr(sd, "query_devices",
                            lambda device=None, kind=None: _stereo)
        cli._check_devices(_args(input=1, output=2))     # darf nicht werfen

    def test_mono_eingang_wird_abgewiesen(self, monkeypatch):
        """Der haeufigste Fehlgriff unter Windows und macOS: ein Mikrofon.

        Der Stream ist stereo. Ohne diese Pruefung stirbt er in PortAudio mit
        "Invalid number of channels [PaErrorCode -9998]" - eine Meldung, die
        weder sagt, WELCHES der beiden Geraete gemeint ist, noch was statt
        dessen zu nehmen waere.
        """
        import sounddevice as sd

        monkeypatch.setattr(sd, "query_devices", lambda device=None, kind=None:
                            {"name": "Mikro", "max_input_channels": 1,
                             "max_output_channels": 0})
        with pytest.raises(SystemExit, match="needs 2"):
            cli._check_devices(_args(input="Mikrofon"))

    def test_auch_das_STANDARDGERAET_wird_geprueft(self, monkeypatch):
        """Ohne --input nimmt PortAudio sein Standardgeraet - unter Windows das
        Mikrofon. Wer hier nichts prueft, prueft genau den Fall nicht, der beim
        ersten Start eintritt."""
        import sounddevice as sd

        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(sd, "query_devices", lambda device=None, kind=None:
                            {"name": "Headset Microphone",
                             "max_input_channels": 1, "max_output_channels": 2})
        with pytest.raises(SystemExit, match="default input device"):
            cli._check_devices(_args())

    def test_fehlendes_standardgeraet_bricht_hier_nicht_ab(self, monkeypatch):
        """Kein Standardgeraet ist kein Grund, hier zu sterben - das faellt beim
        Aufbau auf, mit der Meldung von PortAudio selbst."""
        import sounddevice as sd

        def explodiere(device=None, kind=None):
            raise sd.PortAudioError("no default device")

        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(sd, "query_devices", explodiere)
        cli._check_devices(_args())      # darf nicht werfen


class TestGeraetepruefungMitRouting:
    """Im Routing-Modus ist `--output` ein Sink-Name, kein PortAudio-Geraet.

    Beides gegen PortAudio zu pruefen wies genau die Namen ab, die
    `jampilot devices` fuer den Routing-Modus auflistet.
    """

    @pytest.fixture(autouse=True)
    def mit_pactl(self, monkeypatch):
        from jampilot import routing
        monkeypatch.setattr(routing, "backend", lambda: routing.PULSE)
        monkeypatch.setattr(routing, "hardware_sinks",
                            lambda: [("0", "alsa_output.usb-Mackie_ProFX16v3-00")])

    def test_sink_name_geht_durch_ohne_portaudio_zu_fragen(self, monkeypatch):
        import sounddevice as sd

        def explodiere(device, kind):
            raise AssertionError("Sink-Name darf nicht als Geraet geprueft werden")
        monkeypatch.setattr(sd, "query_devices", explodiere)

        cli._check_devices(_args(output="alsa_output.usb-Mackie_ProFX16v3-00"))

    def test_sink_index_geht_ebenfalls(self):
        cli._check_devices(_args(output=0))

    def test_unbekannter_sink_bricht_ab(self):
        with pytest.raises(SystemExit, match="unknown"):
            cli._check_devices(_args(output="gibtsnicht"))

    def test_mit_eigenem_eingang_gilt_wieder_die_geraetepruefung(self, monkeypatch):
        # --input schaltet in den Direktmodus; dann IST --output ein Geraet.
        import sounddevice as sd

        gefragt = []

        def fragen(device, kind):
            gefragt.append((device, kind))
            return _stereo

        monkeypatch.setattr(sd, "query_devices", fragen)
        cli._check_devices(_args(input=1, output=2))
        assert gefragt == [(1, "input"), (2, "output")]


class TestWachhund:
    """Ein Geraet, das verschwindet, meldet sich nicht ab.

    PortAudio ruft den Callback dann einfach nicht mehr - ohne Fehler, ohne Ende
    des Streams. Von aussen sieht das aus wie "laeuft": Schalter an, Umleitung
    steht, Anzeige eingefroren. Erkannt wird es nur am Ringpuffer, der still
    steht.
    """

    @pytest.fixture
    def args(self):
        return argparse.Namespace(samplerate=48000, delay=4.0)

    def test_stehender_ringpuffer_wird_gemeldet(self, args, monkeypatch, capsys):
        monkeypatch.setattr(cli, "STREAM_STALL_TIMEOUT", 0.05)

        class ToterStream:
            delay_seconds, captured_frames, xruns, last_status = 4.0, 0, 0, None

        with pytest.raises(cli.StreamStalled, match="No audio"):
            cli._display_loop(ToterStream(), args)

    def test_laufender_stream_schlaegt_nicht_an(self, args, monkeypatch, capsys):
        # Ein Fehlalarm waere schlimmer als das Problem: Er braeche einen
        # laufenden Betrieb ab. Also muss ein Puffer, der sich bewegt, den
        # Wachhund auch bei knappem Zeitlimit ruhig halten.
        monkeypatch.setattr(cli, "STREAM_STALL_TIMEOUT", 0.05)
        halt = threading.Event()

        class LaufenderStream:
            delay_seconds, xruns, last_status = 4.0, 0, None

            def __init__(self):
                self._runden = 0

            @property
            def captured_frames(self):
                self._runden += 1
                if self._runden > 200:
                    halt.set()
                return self._runden * 100_000

            def audio_ending_at(self, ende, laenge):
                return None      # nichts zu analysieren - die Schleife dreht nur

        cli._display_loop(LaufenderStream(), args, stop=halt)   # darf nicht werfen


class TestOhneArgument:
    """Kein Befehl = `run`.

    Eine ausgelieferte Binary wird DOPPELGEKLICKT, und ein Doppelklick uebergibt
    kein Argument. Bestand argparse darauf, brach das Programm mit "the following
    arguments are required: command" ab - und das Fenster, das dem Nutzer alles
    erklaert haette, ging nie auf. Fuer eine App ist "kein Argument" der
    Normalfall, nicht ein Fehler.
    """

    def test_ohne_argument_laeuft_run(self, monkeypatch):
        from unittest.mock import patch

        from jampilot import cli

        monkeypatch.setattr(sys, "argv", ["jampilot"])
        with patch("jampilot.cli.cmd_run") as run:
            cli.main()
        assert run.called
        args = run.call_args[0][0]
        assert args.delay == 4.0 and args.port == 8765      # die Standardwerte

    def test_hilfe_geht_weiterhin(self, monkeypatch, capsys):
        from jampilot import cli

        monkeypatch.setattr(sys, "argv", ["jampilot", "--help"])
        with pytest.raises(SystemExit) as exit:
            cli.main()
        assert exit.value.code == 0
        assert "run" in capsys.readouterr().out

    def test_die_anderen_befehle_gehen_weiterhin(self, monkeypatch):
        from unittest.mock import patch

        from jampilot import cli

        monkeypatch.setattr(sys, "argv", ["jampilot", "selftest"])
        with patch("jampilot.cli.cmd_selftest") as st:
            cli.main()
        assert st.called

    def test_optionen_ohne_befehl_gehen_an_run(self, monkeypatch):
        # `jampilot --delay 6` ist der Aufruf, den jeder tippt. Vorher scheiterte
        # er an "invalid choice: '6'" - einer Meldung, die den Grund nicht nennt.
        from unittest.mock import patch

        from jampilot import cli

        monkeypatch.setattr(sys, "argv", ["jampilot", "--delay", "6", "--no-web"])
        with patch("jampilot.cli.cmd_run") as run:
            cli.main()
        args = run.call_args[0][0]
        assert args.delay == 6.0 and args.no_web

    def test_ein_echter_befehl_wird_nicht_zu_run_umgebogen(self, monkeypatch):
        from unittest.mock import patch

        from jampilot import cli

        monkeypatch.setattr(sys, "argv", ["jampilot", "analyze", "song.wav"])
        with patch("jampilot.cli.cmd_analyze") as an:
            cli.main()
        assert an.called and an.call_args[0][0].file == "song.wav"

"""CLI: Randfaelle der Dateianalyse und Argumentpruefung."""

import argparse
import struct
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


class TestGeraetepruefung:
    def test_unbekanntes_geraet_bricht_sofort_ab(self, monkeypatch):
        import sounddevice as sd

        def explodiere(device, kind):
            raise ValueError(f"kein Geraet {device!r}")
        monkeypatch.setattr(sd, "query_devices", explodiere)

        # Muss VOR dem teuren Warmup zuschlagen und verstaendlich sein.
        with pytest.raises(SystemExit, match="not usable"):
            cli._check_devices("gibtsnicht", None)

    def test_kein_geraet_angegeben_ist_in_ordnung(self):
        cli._check_devices(None, None)   # darf nicht werfen


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

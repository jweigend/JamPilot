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
            capture_dropouts = None          # kein fremder Mitschnitt
            recording, record_paused, record_epoch = False, False, 0
            record_offset_seconds, record_capacity_seconds = 0.0, 0.0
            def heard_position(self):
                return self.captured_frames / 48000 - self.delay_seconds

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
            capture_dropouts = None          # kein fremder Mitschnitt
            recording, record_paused, record_epoch = False, False, 0
            record_offset_seconds, record_capacity_seconds = 0.0, 0.0
            def heard_position(self):
                return self.captured_frames / 48000 - self.delay_seconds

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
        assert args.delay == 5.0 and args.port == 8765      # die Standardwerte

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


class TestRefineFreshBounds:
    """Verfeinerung frischer Grenzen - und ihre Leitplanke an der Commit-Grenze."""

    def test_verfeinerung_zieht_die_grenze_aufs_ereignis(self):
        timeline = [(0.0, "A"), (11.6, "D")]
        cli._refine_fresh_bounds(timeline, [], frontier=10.5,
                                 refine=lambda pos, prev, name: pos - 0.35)
        assert timeline == [(0.0, "A"), (11.25, "D")]

    def test_verfeinerte_grenze_faellt_nicht_hinter_die_wasserlinie(self):
        # Befund 2026-08-30 (verschluckter Akkordanfang): Eine spaet erkannte
        # Grenze taucht knapp UEBER der Commit-Grenze auf (10.55 > 10.5), die
        # Verfeinerung zieht sie 0.35 s zurueck - hinter die Wasserlinie des
        # vorigen Hops (10.25). Ohne Klemmung committet der Ledger sie nie:
        # Die Anzeige zeigte den vorigen Akkord, bis das Stueck real wechselt.
        led = cli.EventLedger()
        timeline = [(0.0, "A")]
        led.advance(timeline, [None], None, frontier=10.25)   # voriger Hop
        timeline.append((10.55, "D"))                         # Merge, neuer Hop
        cli._refine_fresh_bounds(timeline, [], frontier=10.5,
                                 refine=lambda pos, prev, name: pos - 0.35)
        led.advance(timeline, [None, None], None, frontier=10.5)
        assert [(e["at"], e["c"]) for e in led.events] == [(0.0, "A"), (10.5, "D")]

    def test_committetes_wird_nicht_angefasst(self):
        timeline = [(0.0, "A"), (9.0, "D")]
        cli._refine_fresh_bounds(timeline, [], frontier=10.5,
                                 refine=lambda pos, prev, name: pos - 0.35)
        assert timeline == [(0.0, "A"), (9.0, "D")]


class TestEventLedger:
    """[Redesign 6.1] Publish-once-Kanal: committete Events sind unantastbar."""

    def test_eintrag_wird_genau_einmal_committet(self):
        led = cli.EventLedger()
        zeitleiste = [(1.0, "C"), (3.0, "G")]
        baesse = [None, None]
        led.advance(zeitleiste, baesse, None, frontier=2.0)
        assert [e["c"] for e in led.events] == ["C"]
        led.advance(zeitleiste, baesse, None, frontier=3.5)
        led.advance(zeitleiste, baesse, None, frontier=3.5)
        assert [(e["at"], e["c"]) for e in led.events] == [(1.0, "C"), (3.0, "G")]

    def test_revision_unter_der_grenze_wird_nicht_mehr_committet(self):
        led = cli.EventLedger()
        led.advance([(1.0, "C")], [None], None, frontier=2.0)
        # Merge schiebt nachtraeglich einen Wechsel bei 1.8 ein - zu spaet:
        # die Grenze ist schon vorbei, das Event darf nicht mehr entstehen.
        led.advance([(1.0, "C"), (1.8, "Am")], [None, None], None, frontier=2.0)
        assert [e["c"] for e in led.events] == ["C"]

    def test_attribute_bleiben_eingefroren(self):
        led = cli.EventLedger()
        for _ in range(cli.BASS_COMMIT_HOPS):
            led.advance([(1.0, "C")], ["E"], {"tonic": "C"}, frontier=0.5)
        led.advance([(1.0, "C")], ["E"], {"tonic": "C"}, frontier=2.0)
        # Zeitleiste, Bass und Tonart aendern sich danach - das Event nicht.
        led.advance([(1.0, "Cmaj7")], ["G"], {"tonic": "G"}, frontier=2.5)
        assert led.events == [{"at": 1.0, "c": "C", "b": "E", "key": {"tonic": "C"}}]

    def test_prune_behaelt_das_letzte_event_vor_jetzt(self):
        led = cli.EventLedger()
        led.advance([(1.0, "C"), (2.0, "G"), (6.0, "F")], [None] * 3, None,
                    frontier=7.0)
        led.prune(heard_pos=5.0)
        assert [e["at"] for e in led.events] == [2.0, 6.0]


class TestEventAbstand:
    """Events liegen nie dichter als MIN_EVENT_GAP und wiederholen sich nicht."""

    def test_im_selben_hop_gewinnt_der_spaetere(self):
        led = cli.EventLedger()
        # F 6.98 und die Korrektur G 7.0 passieren die Grenze im selben Hop:
        # das F war ein Flackern, das G ist das juengere Urteil.
        led.advance([(1.0, "C"), (6.98, "F"), (7.0, "G")], [None] * 3, None,
                    frontier=7.0)
        assert [(e["at"], e["c"]) for e in led.events] == [(1.0, "C"), (7.0, "G")]

    def test_gegen_veroeffentlichtes_rueckt_das_neue_nach(self):
        led = cli.EventLedger()
        led.advance([(1.0, "C"), (6.98, "F")], [None] * 2, None, frontier=6.98)
        # F ist draussen - unantastbar. Das G kommt trotzdem an, nur auf
        # Mindestabstand nachgerueckt statt 0.02 s hinter dem F.
        led.advance([(1.0, "C"), (6.98, "F"), (7.0, "G")], [None] * 3, None,
                    frontier=7.25)
        assert [(e["at"], e["c"]) for e in led.events] == [
            (1.0, "C"), (6.98, "F"), (round(6.98 + cli.MIN_EVENT_GAP, 3), "G")]

    def test_kaskade_laesst_nur_das_letzte_des_buendels(self):
        led = cli.EventLedger()
        led.advance([(1.0, "C"), (6.9, "C7"), (7.0, "F"), (7.1, "Fmaj7")],
                    [None] * 4, None, frontier=7.25)
        assert [(e["at"], e["c"]) for e in led.events] == [(1.0, "C"), (7.1, "Fmaj7")]

    def test_gleiche_aussage_wird_kein_zweites_event(self):
        led = cli.EventLedger()
        led.advance([(1.0, "C"), (2.0, "C"), (3.0, "G")], [None] * 3, None,
                    frontier=4.0)
        assert [(e["at"], e["c"]) for e in led.events] == [(1.0, "C"), (3.0, "G")]

    def test_gleicher_akkord_mit_anderem_bass_bleibt_ein_event(self):
        led = cli.EventLedger()
        zeitleiste = [(1.0, "C"), (2.0, "C")]
        for _ in range(cli.BASS_COMMIT_HOPS):
            led.advance(zeitleiste, [None, "E"], None, frontier=0.5)
        led.advance(zeitleiste, [None, "E"], None, frontier=3.0)
        assert [(e["at"], e["c"], e["b"]) for e in led.events] == [
            (1.0, "C", None), (2.0, "C", "E")]

    def test_nachgerueckter_bass_findet_seine_messung(self):
        led = cli.EventLedger()
        led.advance([(1.0, "C"), (6.98, "F")], [None] * 2, None, frontier=6.98)
        zeitleiste = [(1.0, "C"), (6.98, "F"), (7.0, "G")]
        led.advance(zeitleiste, [None, None, None], None, frontier=7.25)
        for _ in range(cli.BASS_COMMIT_HOPS):
            led.advance(zeitleiste, [None, None, "B"], None, frontier=7.25)
        g = led.events[-1]
        assert g["c"] == "G" and g["b"] == "B" and g["b_up"] is True


class TestBassRegel:
    """Monotone Bass-Regel: Persistenz vor Commit, einmal nachruecken, nie zurueck."""

    def test_fluechtiger_bass_wird_nicht_committet(self):
        led = cli.EventLedger()
        zeitleiste = [(1.0, "C")]
        # Nur 2 Hops mit derselben Note gemessen - unter BASS_COMMIT_HOPS.
        led.advance(zeitleiste, ["E"], None, frontier=0.5)
        led.advance(zeitleiste, ["E"], None, frontier=2.0)
        assert led.events[0]["b"] is None

    def test_persistenter_bass_wird_committet(self):
        led = cli.EventLedger()
        zeitleiste = [(1.0, "C")]
        for _ in range(cli.BASS_COMMIT_HOPS):
            led.advance(zeitleiste, ["E"], None, frontier=0.5)
        led.advance(zeitleiste, ["E"], None, frontier=2.0)
        assert led.events[0]["b"] == "E"
        assert "b_up" not in led.events[0]

    def test_flatternder_bass_setzt_die_persistenz_zurueck(self):
        led = cli.EventLedger()
        zeitleiste = [(1.0, "C")]
        for note in ["E", "E", "E", None, "E"]:
            led.advance(zeitleiste, [note], None, frontier=0.5)
        led.advance(zeitleiste, ["E"], None, frontier=2.0)   # erst 3 Hops "E"
        assert led.events[0]["b"] is None

    def test_bass_darf_genau_einmal_nachruecken(self):
        led = cli.EventLedger()
        zeitleiste = [(1.0, "C")]
        led.advance(zeitleiste, [None], None, frontier=2.0)  # leer committet
        for _ in range(cli.BASS_COMMIT_HOPS):
            led.advance(zeitleiste, ["E"], None, frontier=2.0)
        assert led.events[0]["b"] == "E" and led.events[0]["b_up"] is True
        # Danach ist der Bass unantastbar - auch wenn die Messung kippt.
        for note in [None, "G", "G", "G", "G", "G"]:
            led.advance(zeitleiste, [note], None, frontier=2.0)
        assert led.events[0]["b"] == "E"

    def test_gesetzter_bass_faellt_nie_zurueck(self):
        led = cli.EventLedger()
        zeitleiste = [(1.0, "C")]
        for _ in range(cli.BASS_COMMIT_HOPS):
            led.advance(zeitleiste, ["E"], None, frontier=0.5)
        led.advance(zeitleiste, ["E"], None, frontier=2.0)
        for _ in range(6):
            led.advance(zeitleiste, [None], None, frontier=2.0)
        assert led.events[0]["b"] == "E"


class TestBassFenster:
    """Bass wird ueber ein festes Fenster ab dem Onset gepoolt."""

    def test_pooling_endet_nach_bass_pool_seconds(self):
        class Aufzeichnung:
            def __init__(self):
                self.intervalle = []
            def pooled_between(self, a, b):
                self.intervalle.append((a, b))
                return None
        track = Aufzeichnung()
        cli._bass_per_segment([(1.0, "C"), (8.0, "G")], track, front=20.0)
        assert track.intervalle == [(1.0, 1.0 + cli.BASS_POOL_SECONDS),
                                    (8.0, 8.0 + cli.BASS_POOL_SECONDS)]

    def test_kurzes_segment_bleibt_am_naechsten_onset_gekappt(self):
        class Aufzeichnung:
            def __init__(self):
                self.intervalle = []
            def pooled_between(self, a, b):
                self.intervalle.append((a, b))
                return None
        track = Aufzeichnung()
        cli._bass_per_segment([(1.0, "C"), (2.2, "G")], track, front=2.8)
        assert track.intervalle == [(1.0, 2.2), (2.2, 2.8)]


class TestCommitAhead:
    """--delay teilt sich haelftig in Vorlauf und Verstehzeit."""

    @pytest.mark.parametrize("delay,vorlauf", [
        (5.0, 2.0),    # Default: der gemessene Arbeitspunkt
        (6.0, 2.5),
        (3.0, 1.0),
        (8.0, 3.5),
    ])
    def test_haelftige_teilung_nach_edge_guard(self, delay, vorlauf):
        assert cli._commit_ahead(delay) == pytest.approx(vorlauf)

    def test_winziger_puffer_wird_geklemmt(self):
        # Unter der Klemme gaebe es gar keine Commit-Grenze mehr vor NOW.
        assert cli._commit_ahead(1.5) == pytest.approx(0.5)


class TestLiveZeile:
    """Die eine Zeile fuers Kontrollfenster - ein Satz, mit dem naechsten Wechsel
    als Countdown (nicht dem konstanten Analysevorsprung), und er sagt, wenn
    kein Ton ankommt."""

    def test_akkord_naechster_und_tonart(self):
        assert cli._live_zeile("C/E", "G", 1.34, "C major") == \
            "Now playing C/E \u00b7 next G in 1.3 s \u00b7 Key C major"

    def test_ohne_bekannten_wechsel_nur_akkord_und_tonart(self):
        assert cli._live_zeile("C", None, 0.0, "C major") == \
            "Now playing C \u00b7 Key C major"

    def test_stille_wird_benannt(self):
        assert cli._live_zeile("-", "-", 3.0, None) == \
            "Now playing \u2013 \u00b7 no sound arriving? \u00b7 Key \u2026"

    def test_kommende_stille_heisst_strich(self):
        assert "next \u2013 in 2.0 s" in cli._live_zeile("C", "-", 2.0, "C major")

    def test_der_countdown_kommt_aus_der_zeitleiste(self):
        """Der Analysethread nimmt den ersten Eintrag hinter der hoerbaren
        Position - so, wie _display_loop ihn sucht."""
        timeline = [(10.0, "C"), (12.5, "G"), (14.0, "Am")]
        audible_pos = 11.2
        naechster, in_s = None, 0.0
        for pos, name in timeline:
            if pos > audible_pos:
                naechster, in_s = name, pos - audible_pos
                break
        assert (naechster, round(in_s, 1)) == ("G", 1.3)


class TestRecordImAnzeigepfad:
    """Die Trennung von Analysezeit und Hoerzeit - im Anzeigepfad."""

    def test_events_reichen_so_weit_zurueck_wie_der_mitschnitt(self):
        led = cli.EventLedger()
        led.advance([(10.0, "C"), (200.0, "G"), (900.0, "F")], [None] * 3, None,
                    frontier=1000.0)
        led.prune(heard_pos=950.0, rueckhalt=1800.0)
        assert [e["at"] for e in led.events] == [10.0, 200.0, 900.0]

    def test_ohne_mitschnitt_bleibt_es_bei_zwei_sekunden(self):
        led = cli.EventLedger()
        led.advance([(1.0, "C"), (2.0, "G"), (6.0, "F")], [None] * 3, None,
                    frontier=7.0)
        led.prune(heard_pos=5.0, rueckhalt=0.0)
        assert [e["at"] for e in led.events] == [2.0, 6.0]

    def test_ohne_mitschnitt_ist_das_fenster_die_identitaet(self):
        # Die Zusage "R nie gedrueckt = Code von vorher" fuer den Anzeigepfad:
        # Alles, was der Ledger nach zwei Sekunden Rueckhalt noch hat, liegt im
        # Fenster - der Schnitt aendert nichts.
        led = cli.EventLedger()
        led.advance([(1.0, "C"), (4.5, "G"), (6.0, "F")], [None] * 3, None,
                    frontier=7.0)
        led.prune(heard_pos=5.0, rueckhalt=0.0)
        assert cli._im_fenster(led.events, 5.0, 7.0) == led.events

    def test_ein_lang_gehaltener_akkord_faellt_nicht_aus_dem_fenster(self):
        events = [{"at": 100.0, "c": "C", "b": None},
                  {"at": 118.0, "c": "G", "b": None}]
        for gehoert in (102.0, 109.0, 115.0, 117.9):
            klingt = cli._event_bei(cli._im_fenster(events, gehoert, gehoert + 2.0),
                                    gehoert)
            assert klingt is not None and klingt["c"] == "C", gehoert

    def test_das_fenster_bleibt_kurz(self):
        events = [{"at": float(t), "c": "C"} for t in range(0, 100)]
        assert len(cli._im_fenster(events, 90.0, 92.0)) <= 16

    def test_gehoerter_akkord_und_countdown_kommen_aus_dem_kanal(self):
        events = [{"at": 1.0, "c": "C", "b": None}, {"at": 5.0, "c": "G", "b": "B"}]
        assert cli._event_bei(events, 6.0)["c"] == "G"
        assert cli._event_bei(events, 0.5) is None
        assert cli._naechstes_event(events, 3.0)["at"] == 5.0
        assert cli._naechstes_event(events, 7.0) is None


class TestRecordBefehl:
    class Attrappe:
        def __init__(self):
            self.recording, self.record_pending = True, False
            self.record_paused, self.record_epoch = False, 3
            self.record_hinweis = None
            self.gerufen = []
        def toggle_record(self): self.gerufen.append("toggle")
        def toggle_record_pause(self): self.gerufen.append("pause")
        def seek_chord(self, r): self.gerufen.append(("chord", r))
        def record_to_start(self): self.gerufen.append("start")
        def record_to_now(self): self.gerufen.append("end")

    def test_alle_sechs_befehle_landen_richtig(self):
        e = self.Attrappe()
        b = cli._record_befehl(e)
        for name in ("toggle", "pause", "prev", "next", "start", "end"):
            b(name)
        assert e.gerufen == ["toggle", "pause", ("chord", -1), ("chord", 1),
                             "start", "end"]

    def test_die_antwort_traegt_immer_den_ganzen_zustand(self):
        zustand = cli._record_befehl(self.Attrappe())("end")
        assert set(zustand) == {"recording", "record_pending", "paused",
                                "epoch", "hint"}


class TestLiveZeileRecord:
    def test_ohne_aufnahme_bleibt_die_zeile_wie_vorher(self):
        assert cli._live_zeile("C", "G", 1.5, "C major") == \
            "Now playing C · next G in 1.5 s · Key C major"
        assert cli._aufnahme_text(False, 0.0, False) == ""

    def test_aufnahme_steht_in_der_zeile_und_im_terminal(self):
        zeile = cli._live_zeile("C", "G", 1.5, "C major", aufnahme=True, zurueck=8.0)
        assert "REC 8 s behind live" in zeile and "next G in 1.5 s" in zeile
        assert cli._aufnahme_text(True, 8.0, False).strip() == "| REC 8s back"
        assert cli._aufnahme_text(True, 0.0, False).strip() == "| REC"

    def test_pausiert_steht_nicht_now_playing_da(self):
        zeile = cli._live_zeile("C", "G", 1.5, "C major", aufnahme=True,
                                zurueck=12.0, pausiert=True)
        assert zeile.startswith("Paused at C") and "next G" not in zeile
        assert cli._aufnahme_text(True, 12.0, True).strip() == "| REC paused 12s back"


class TestViertelSnap:
    """Viertel-Snap: der Event-Onset liegt auf dem naechsten Beat (beats.py),
    die Zeitleiste behaelt die rohe Modellgrenze."""

    def test_event_liegt_auf_dem_beat(self):
        led = cli.EventLedger()
        zeitleiste = [(1.0, "C"), (6.13, "G")]
        led.advance(zeitleiste, [None, None], None, frontier=7.0,
                    snap=lambda pos: 6.0 if abs(pos - 6.0) < 0.3 else None)
        assert [(e["at"], e["c"]) for e in led.events] == [(1.0, "C"), (6.0, "G")]
        assert zeitleiste == [(1.0, "C"), (6.13, "G")]   # Hypothese bleibt roh

    def test_ohne_beat_in_reichweite_bleibt_der_gemessene_onset(self):
        led = cli.EventLedger()
        led.advance([(1.0, "C"), (6.13, "G")], [None, None], None, frontier=7.0,
                    snap=lambda pos: None)
        assert [e["at"] for e in led.events] == [1.0, 6.13]

    def test_snap_vor_die_wasserlinie_verschluckt_kein_event(self):
        # Der Beat liegt VOR der Wasserlinie des vorigen Hops - anders als
        # bei der Verfeinerung (1.3.1) ist das unschaedlich: Der Ledger merkt
        # sich den Zeitleisten-Onset, nicht den Event-Onset.
        led = cli.EventLedger()
        zeitleiste = [(0.0, "A")]
        led.advance(zeitleiste, [None], None, frontier=10.25)
        zeitleiste.append((10.4, "D"))
        led.advance(zeitleiste, [None, None], None, frontier=10.5,
                    snap=lambda pos: 10.1)
        assert [(e["at"], e["c"]) for e in led.events] == [(0.0, "A"), (10.1, "D")]
        led.advance(zeitleiste, [None, None], None, frontier=10.75,
                    snap=lambda pos: 10.1)
        assert len(led.events) == 2                       # und nur einmal

    def test_zwei_grenzen_auf_demselben_beat_der_spaetere_gewinnt(self):
        led = cli.EventLedger()
        zeitleiste = [(1.0, "C"), (5.9, "F"), (6.1, "G")]
        led.advance(zeitleiste, [None] * 3, None, frontier=7.0,
                    snap=lambda pos: 6.0 if abs(pos - 6.0) < 0.3 else None)
        assert [(e["at"], e["c"]) for e in led.events] == [(1.0, "C"), (6.0, "G")]

    def test_der_bass_findet_seine_messung_unter_dem_rohen_onset(self):
        led = cli.EventLedger()
        zeitleiste = [(1.0, "C"), (6.13, "G")]
        for _ in range(cli.BASS_COMMIT_HOPS):
            led.advance(zeitleiste, [None, "B"], None, frontier=7.0,
                        snap=lambda pos: 6.0 if abs(pos - 6.0) < 0.3 else None)
        assert led.events[-1]["at"] == 6.0 and led.events[-1]["b"] == "B"

    def test_kontrollgitarre_spielt_auf_dem_event_onset(self):
        led = cli.EventLedger()
        zeitleiste = [(1.0, "C"), (6.13, "G"), (9.07, "A")]
        snap = lambda pos: round(pos * 2) / 2 if abs(pos - round(pos * 2) / 2) < 0.3 else None
        led.advance(zeitleiste, [None] * 3, None, frontier=7.0, snap=snap)
        assert led.published_at(6.13) == 6.0
        assert led.published_at(1.0) == 1.0          # unveraendert committet
        assert led.published_at(9.07) == 9.07        # noch kein Event
        led.advance(zeitleiste, [None] * 3, None, frontier=10.0, snap=snap)
        assert led.published_at(9.07) == 9.0
        led.prune(heard_pos=100.0)                   # laesst nur das letzte Event
        assert led.published_at(6.13) == 6.13        # vergessen mit dem Event
        assert led.published_at(9.07) == 9.0


class TestBeatsImAnzeigepfad:
    """_display_loop mit Attrappen fuer Akkordmodell und Beat-Tracker: Beats
    kommen als zweiter Kanal an, die Grenze liegt auf dem Beat, die
    Kontrollgitarre spielt dort - und die Verfeinerung laeuft weiter."""

    SR = 22050
    # Wo die Grenzen in der Zeitleiste landen sollen. Die Modell-Attrappe
    # liefert sie um BTC_ONSET_SHIFT FRUEHER - wie das echte Modell, dessen
    # Bias die Korrektur im Anzeigepfad gerade ausgleicht.
    WECHSEL = [(0.0, "C"), (6.13, "G"), (12.1, "C")]

    class Loop:
        xruns, last_status, capture_dropouts = 0, None, None
        recording = record_paused = muted = control_guitar = False
        record_epoch, record_offset_seconds, record_capacity_seconds = 0, 0.0, 0.0

        def __init__(self, sr, sekunden, stop):
            self.sr, self.delay_seconds, self._stop = sr, 5.0, stop
            self.hop, self.ende, self._pos = int(0.25 * sr), int(sekunden * sr), 0
            self.control = []

        @property
        def captured_frames(self):
            self._pos = min(self._pos + self.hop, self.ende)
            if self._pos >= self.ende:
                self._stop.set()
            return self._pos

        def audio_ending_at(self, end, length):
            return np.zeros(length, dtype=np.float32) if end - length >= 0 else None

        def audible_position(self):
            return self._pos / self.sr - self.delay_seconds

        heard_position = audible_position

        def set_control_timeline(self, tl):
            self.control = list(tl)

    class Tracker:
        """Beats alle 0,5 s, die Eins alle 2 s - synchron, ohne Thread."""
        ready, error, provider = True, None, "fake"

        def __init__(self):
            from jampilot.beats import BeatGrid
            self.grid = BeatGrid()

        def submit(self, audio, sr, start, end):
            alle = np.arange(np.ceil(start * 2) / 2, end, 0.5)
            self.grid.absorb(alle - start, alle[alle % 2 == 0] - start, start, end)
            return True

        def poll(self):
            return 0

        def stop(self):
            pass

    def _lauf(self, monkeypatch, tracker):
        from jampilot import beats, btc
        wechsel = self.WECHSEL
        verfeinert = []

        class Modell:
            def predict(self, features):
                return np.zeros(len(features), dtype=int)

        def segmente(labels, audio, sr, offset=0.0, **kw):
            ende = offset + len(audio) / sr
            out = [(round(pos - cli.BTC_ONSET_SHIFT, 6), name)
                   for pos, name in wechsel if offset <= pos < ende]
            if not out or out[0][0] > offset:
                davor = [n for p, n in wechsel if p <= offset]
                out.insert(0, (offset, davor[-1] if davor else wechsel[0][1]))
            return out

        monkeypatch.setattr(btc, "BTCModel", Modell)
        monkeypatch.setattr(btc, "features_from_audio",
                            lambda audio, sr: np.zeros((108, 144), dtype=np.float32))
        monkeypatch.setattr(btc, "live_segments_from_labels", segmente)
        monkeypatch.setattr(btc, "refine_boundary",
                            lambda *a: verfeinert.append(a[2]) or a[2])
        monkeypatch.setattr(beats.BeatTracker, "create", classmethod(lambda cls: tracker))
        stop = threading.Event()
        loop = self.Loop(self.SR, 22.0, stop)
        zustaende = []

        class Broadcaster:
            def publish(self, s):
                zustaende.append(s)

        args = argparse.Namespace(samplerate=self.SR, delay=5.0, record_buffer=0)
        cli._display_loop(loop, args, Broadcaster(), stop=stop)
        return zustaende, loop, verfeinert

    def test_grenze_liegt_auf_dem_beat_und_beats_kommen_mit(self, monkeypatch):
        zustaende, loop, verfeinert = self._lauf(monkeypatch, self.Tracker())
        events = {}
        beats = {}
        for s in zustaende:
            for e in s["committed"]:
                events[e["at"]] = e["c"]
            for b in s["beats"]:
                beats[b["at"]] = b["n"]
        assert events[6.0] == "G" and events[12.0] == "C"
        assert 6.13 not in events and 12.1 not in events
        assert len(verfeinert) == 2                    # verfeinert wird weiterhin
        assert beats[6.0] == 1 and beats[6.5] == 2 and beats[7.5] == 4
        assert all(round(at * 2) == at * 2 for at in beats)
        # Die Kontrollgitarre spielt auf dem Event-Onset, nicht der rohen Grenze
        # (am Ende des Laufs steht nur noch der letzte Wechsel in der Zeitleiste).
        assert loop.control == [(12.0, "C", None)]

    def test_ohne_tracker_wie_zuvor(self, monkeypatch):
        zustaende, loop, verfeinert = self._lauf(monkeypatch, None)
        events = {}
        for s in zustaende:
            for e in s["committed"]:
                events[e["at"]] = e["c"]
        assert events[6.13] == "G" and all(s["beats"] == [] for s in zustaende)
        assert len(verfeinert) == 2                    # Verfeinerung wie in 1.3.1

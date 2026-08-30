"""Der Betrieb als schaltbares Ding: an, aus, stumm - und sauber zurueckgebaut.

Ohne echtes Audio: `DelayedLoopback` und die Umleitung sind Attrappen. Geprueft
wird die Verdrahtung, nicht PortAudio - und vor allem die REIHENFOLGE beim
Abbauen, denn die ist der gefaehrliche Teil.
"""

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from jampilot.engine import Engine


def _warte_bis(bedingung, timeout=3.0):
    """Warten auf einen Hintergrundthread - ohne feste Schlafzeit im Test."""
    ende = time.monotonic() + timeout
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture
def args():
    return SimpleNamespace(delay=4.0, samplerate=48000, input=None, output=None,
                           no_route=True, no_web=True, port=8765)


@pytest.fixture
def engine(args):
    """Engine mit Attrappen-Stream; die Analyse laeuft ins Leere."""
    with patch("jampilot.delay_stream.DelayedLoopback") as Loop, \
         patch("jampilot.cli._display_loop"):
        loop = Loop.return_value
        loop.muted = False
        loop.delay_seconds = 4.0
        loop.toggle_mute.side_effect = lambda: setattr(
            loop, "muted", not loop.muted) or loop.muted
        e = Engine(args)
        e._Loop = Loop
        yield e
        e.stop()


class TestAnUndAus:
    def test_startet_und_stoppt(self, engine):
        assert not engine.running
        engine.start()
        assert engine.running and engine.status == "running"
        engine.stop()
        assert not engine.running and engine.status == "stopped"

    def test_zweimal_starten_startet_nur_einmal(self, engine):
        engine.start()
        engine.start()                    # Doppelklick auf den Schieber
        assert engine._Loop.call_count == 1

    def test_stoppen_ohne_start_tut_nichts(self, engine):
        engine.stop()                     # darf nicht fliegen
        assert not engine.running

    def test_wieder_einschalten_baut_neu_auf(self, engine):
        engine.start()
        engine.stop()
        engine.start()
        assert engine.running
        assert engine._Loop.call_count == 2


class TestAbbauReihenfolge:
    """Der Stream MUSS vor der Umleitung sterben.

    Andersherum liegt zwischen "Umleitung weg" und "Stream weg" ein Fenster, in
    dem der Stream die zurueckgesetzte Standardquelle liest - typischerweise das
    MIKROFON. Das dann verzoegert auf die Lautsprecher zu geben, ist die
    klassische Rueckkopplung. Deshalb steht diese Reihenfolge in einem Test und
    nicht nur in einem Kommentar.
    """

    def test_stream_zuerst_dann_die_umleitung(self, args):
        args.no_route = False
        reihenfolge = []

        with patch("jampilot.routing.available", return_value=True), \
             patch("jampilot.routing.create") as Routing, \
             patch("jampilot.delay_stream.DelayedLoopback") as Loop, \
             patch("jampilot.cli._display_loop"):
            Loop.return_value.stop.side_effect = lambda: reihenfolge.append("stream")
            Routing.return_value.__exit__.side_effect = \
                lambda *a: reihenfolge.append("routing")

            e = Engine(args)
            e.start()
            e.stop()

        assert reihenfolge == ["stream", "routing"]

    def test_fehler_beim_start_raeumt_alles_weg(self, args):
        # Halb aufgebaut ist schlimmer als gar nicht: bliebe der Null-Sink als
        # Standardausgang stehen, waere der Rechner stumm - und der Nutzer haette
        # keine Ahnung, warum.
        args.no_route = False
        with patch("jampilot.routing.available", return_value=True), \
             patch("jampilot.routing.create") as Routing, \
             patch("jampilot.delay_stream.DelayedLoopback",
                   side_effect=RuntimeError("keine Soundkarte")):
            e = Engine(args)
            with pytest.raises(RuntimeError):
                e.start()

        assert not e.running
        assert e.status == "error"
        assert "keine Soundkarte" in e.fehler
        Routing.return_value.__exit__.assert_called_once()

    def test_strg_c_mitten_im_aufbau_raeumt_auch_weg(self, args):
        """Der Abbruch ist keine Exception - und traf trotzdem genau hier.

        Der Aufbau dauert Sekunden (PortAudio oeffnen, Geraet einschwingen), und
        genau dann drueckt der ungeduldige Nutzer Strg+C. KeyboardInterrupt ist
        aber eine BaseException: Ein `except Exception` sieht sie nicht. Vorher
        rutschte der Abbruch durch, der Null-Sink blieb als Standardausgang
        stehen - und der Rechner war stumm, ohne dass irgendetwas das erklaerte.
        (Nachgemessen mit einem SIGHUP mitten im DelayedLoopback.__init__.)
        """
        args.no_route = False
        with patch("jampilot.routing.available", return_value=True), \
             patch("jampilot.routing.create") as Routing, \
             patch("jampilot.delay_stream.DelayedLoopback",
                   side_effect=KeyboardInterrupt):
            e = Engine(args)
            with pytest.raises(KeyboardInterrupt):
                e.start()

        assert not e.running
        assert e.status == "stopped"          # ein Abbruch ist kein Fehler
        Routing.return_value.__exit__.assert_called_once()

    def test_stop_baut_auch_eine_halbe_umleitung_ab(self, args):
        """Nur die Umleitung steht, der Stream noch nicht - abbauen muss trotzdem.

        Genau diesen Zustand laesst ein Abbruch mitten im Aufbau zurueck. Ein
        `stop()`, das auf den Stream prueft und sonst sofort zurueckkehrt, geht
        darueber hinweg und laesst den Null-Sink stehen.
        """
        args.no_route = False
        with patch("jampilot.routing.available", return_value=True), \
             patch("jampilot.routing.create") as Routing:
            e = Engine(args)
            e._route = Routing.return_value      # halb aufgebaut, wie nach Strg+C
            e.stop()

        Routing.return_value.__exit__.assert_called_once()
        assert e._route is None


class TestSterbenderStream:
    """Stirbt die Analyse, MUSS die Umleitung fallen.

    Wenn das Audiogeraet verschwindet - USB-Kabel raus, Mischpult aus -, bleibt
    sonst der schlimmste Zustand zurueck: Der Systemton laeuft weiter in den
    Null-Sink, zu hoeren ist nichts, und die Anzeige, die das erklaeren koennte,
    steht still. Der Rechner sieht kaputt aus.
    """

    def test_baut_ab_und_behaelt_den_grund(self, args):
        from jampilot.cli import StreamStalled

        args.no_route = False
        with patch("jampilot.routing.available", return_value=True), \
             patch("jampilot.routing.create") as Routing, \
             patch("jampilot.delay_stream.DelayedLoopback") as Loop, \
             patch("jampilot.cli._display_loop",
                   side_effect=StreamStalled("kein Ton mehr")):
            e = Engine(args)
            e.start()
            assert _warte_bis(lambda: e._route is None and e._loop is None), \
                "Umleitung blieb nach dem Tod des Streams stehen"

        assert not e.running
        # "stopped" waere hier eine Luege: Es hat nicht jemand ausgeschaltet.
        assert e.status == "error"
        assert "kein Ton mehr" in e.fehler
        Loop.return_value.stop.assert_called_once()
        Routing.return_value.__exit__.assert_called_once()


class TestStumm:
    def test_umschalten_geht_nur_im_betrieb(self, engine):
        assert engine.toggle_mute() is False      # steht ja nicht
        engine.start()
        assert engine.toggle_mute() is True
        assert engine.muted

    def test_der_browser_erfaehrt_es_sofort(self, args):
        broadcaster = MagicMock()
        with patch("jampilot.delay_stream.DelayedLoopback") as Loop, \
             patch("jampilot.cli._display_loop"):
            Loop.return_value.muted = False
            Loop.return_value.toggle_mute.return_value = True
            e = Engine(args, broadcaster=broadcaster)
            e.start()
            e.toggle_mute()
            e.stop()

        broadcaster.republish.assert_any_call(muted=True)

    def test_stoppen_hebt_die_stummschaltung_auf(self, engine):
        engine.start()
        engine.toggle_mute()
        engine.stop()
        # Sonst startet der naechste Lauf stumm, und niemand weiss warum.
        assert not engine.muted


class TestStartprotokoll:
    """Die Etappen des Starts: lesbar, mit Dauer, aus jedem Thread.

    Der Grund fuer das Protokoll steht in engine.py - ein erster Start, der bis
    zu einer Minute lang "Starting" sagt, sieht aus wie ein Absturz.
    """

    def test_etappe_bekommt_ihre_dauer(self):
        from jampilot.engine import Startprotokoll

        p = Startprotokoll()
        with p.etappe("Compiling"):
            assert p.zeilen()[-1].endswith("Compiling ...")   # laeuft noch
            time.sleep(0.06)
        zeile = p.zeilen()[-1]
        assert "Compiling (" in zeile and zeile.endswith(" s)")
        assert "..." not in zeile

    def test_meldung_ohne_dauer_und_reihenfolge(self):
        from jampilot.engine import Startprotokoll

        p = Startprotokoll()
        p.melden("Window open")
        with p.etappe("Loading"):
            pass
        p.melden("Live")
        texte = [z.split(" s  ", 1)[1] for z in p.zeilen()]
        assert texte == ["Window open", "Loading", "Live"]

    def test_fehler_bleibt_in_der_zeile_stehen(self):
        from jampilot.engine import Startprotokoll

        p = Startprotokoll()
        with pytest.raises(RuntimeError):
            with p.etappe("Opening the audio devices"):
                raise RuntimeError("keine Soundkarte")
        assert p.zeilen()[-1].endswith("failed: keine Soundkarte")

    def test_aktuell_ist_die_juengste_zeile_ohne_zeit(self):
        from jampilot.engine import Startprotokoll

        p = Startprotokoll()
        assert p.aktuell() == ""
        p.melden("Window open")
        with p.etappe("Compiling"):
            assert p.aktuell() == "Compiling ..."
        assert p.aktuell().startswith("Compiling")
        assert " s  " not in p.aktuell()

    def test_stand_zaehlt_jede_aenderung(self):
        from jampilot.engine import Startprotokoll

        p = Startprotokoll()
        s0 = p.stand()
        with p.etappe("x"):
            s1 = p.stand()
        assert s0 < s1 < p.stand()

    def test_ausgabe_bekommt_fertige_zeilen(self):
        from jampilot.engine import Startprotokoll

        zeilen = []
        p = Startprotokoll(ausgabe=zeilen.append)
        p.melden("Window open")
        with p.etappe("Loading"):
            assert len(zeilen) == 1            # erst die fertige Zeile
        assert len(zeilen) == 2 and "Loading" in zeilen[1]

    def test_engine_schreibt_ihre_etappen_hinein(self, engine):
        engine.start()
        texte = "\n".join(engine.protokoll.zeilen())
        assert "Opening the audio devices" in texte
        assert "..." not in texte              # abgeschlossen

    def test_umleitung_ist_eine_eigene_etappe(self, args):
        args.no_route = False
        with patch("jampilot.routing.available", return_value=True), \
             patch("jampilot.routing.create"), \
             patch("jampilot.delay_stream.DelayedLoopback"), \
             patch("jampilot.cli._display_loop"):
            e = Engine(args)
            e.start()
            e.stop()
        texte = [z.split(" s  ", 1)[1] for z in e.protokoll.zeilen()]
        assert texte[0].startswith("Routing the system audio")
        assert texte[1].startswith("Opening the audio devices")

    def test_fehler_beim_oeffnen_steht_im_protokoll(self, args):
        with patch("jampilot.delay_stream.DelayedLoopback",
                   side_effect=RuntimeError("keine Soundkarte")):
            e = Engine(args)
            with pytest.raises(RuntimeError):
                e.start()
        assert e.protokoll.zeilen()[-1].endswith("failed: keine Soundkarte")


class TestLiveZeile:
    def test_stop_leert_die_live_zeile(self, engine):
        engine.start()
        engine.jetzt = "Now playing C"
        engine.stop()
        assert engine.jetzt == ""


def _warten_bis_reserviert(e, timeout=5.0):
    """Der Speicher kommt im Hintergrundthread - der Test wartet darauf."""
    t = e._record_lade
    if t is not None:
        t.join(timeout=timeout)
    assert e._record_lade is None, "Reservierung haengt"


class TestRecordModus:
    """Die Engine-Seite des Record-Modus.

    Wichtigste Zusage: Ohne Mitschnitt darf NICHTS abstuerzen. Die Oberflaechen
    bieten die Tasten immer an - sie koennen nicht wissen, ob der Speicher
    gereicht hat -, und dann muessen sie eben folgenlos bleiben.
    """

    @pytest.fixture
    def laufend(self, args):
        args.record_buffer = 0.02            # 1,2 s - klein, aber echt
        with patch("jampilot.delay_stream.DelayedLoopback") as Loop, \
             patch("jampilot.cli._display_loop"):
            loop = Loop.return_value
            loop.muted = False
            loop.samplerate, loop.channels = 8000, 2
            # Die Attrappe reicht die Mitschnitt-Eigenschaften an einen echten
            # Puffer durch, sobald einer eingehaengt ist.
            loop.attach_record.side_effect = lambda p: setattr(loop, "_rec", p)
            loop._rec = None
            type(loop).recording = property(lambda l: l._rec is not None and l._rec.recording)
            type(loop).record_paused = property(lambda l: l._rec is not None and l._rec.paused)
            type(loop).record_offset_seconds = property(
                lambda l: l._rec.offset_seconds if l._rec else 0.0)
            type(loop).record_epoch = property(lambda l: l._rec.epoch if l._rec else 0)
            loop.heard_position.return_value = 10.0
            e = Engine(args)
            e.start()
            try:
                yield e, loop
            finally:
                e.stop()

    def test_im_stopp_zustand_folgenlos(self, engine):
        assert engine.toggle_record() is False
        assert engine.recording is False
        engine.seek_chord(-1); engine.record_to_now()      # darf nicht werfen

    def test_r_reserviert_im_hintergrund_und_nimmt_dann_auf(self, laufend):
        e, loop = laufend
        assert e.toggle_record() is True
        assert e.record_pending                            # laedt gerade
        _warten_bis_reserviert(e)
        loop.attach_record.assert_called_once()
        assert e.recording and not e.record_pending

    def test_die_seite_sieht_das_reservieren_sofort(self, args):
        # Der hohle Punkt: R hat gegriffen, der Speicher kommt. Ohne die
        # Sofortmeldung erschiene er erst, wenn die Reservierung fertig ist -
        # also nie, denn dann ist er schon gefuellt.
        args.record_buffer = 0.02
        broadcaster = MagicMock()
        with patch("jampilot.delay_stream.DelayedLoopback") as Loop, \
             patch("jampilot.cli._display_loop"):
            loop = Loop.return_value
            loop.muted = False
            loop.samplerate, loop.channels = 8000, 2
            loop.recording, loop.record_paused = False, False
            e = Engine(args, broadcaster=broadcaster)
            e.start()
            try:
                e.toggle_record()
                erste = broadcaster.republish.call_args_list[0].kwargs
                assert erste["record_pending"] is True
                _warten_bis_reserviert(e)
            finally:
                e.stop()

    def test_scheitert_die_reservierung_erfaehrt_es_die_seite_einmal(self, args):
        args.record_buffer = 30.0
        broadcaster = MagicMock()
        with patch("jampilot.delay_stream.DelayedLoopback") as Loop, \
             patch("jampilot.cli._display_loop"), \
             patch("jampilot.record_buffer.verfuegbarer_speicher",
                   return_value=2 ** 20):
            loop = Loop.return_value
            loop.muted = False
            loop.samplerate, loop.channels = 48000, 2
            loop.recording, loop.record_paused = False, False
            e = Engine(args, broadcaster=broadcaster)
            e.start()
            try:
                e.toggle_record(); _warten_bis_reserviert(e)
                hinweise = [c.kwargs.get("record_hint")
                            for c in broadcaster.republish.call_args_list]
                assert any(h and "not enough free memory" in h for h in hinweise)
                assert e.record_hinweis is None              # abgeraeumt
                # ... und R darf es wieder versuchen.
                assert e.toggle_record() is True
                _warten_bis_reserviert(e)
            finally:
                e.stop()

    def test_zweites_r_schaltet_aus_und_ein_drittes_greift_sofort(self, laufend):
        e, _ = laufend
        e.toggle_record(); _warten_bis_reserviert(e)
        assert e.toggle_record() is False and not e.recording
        assert e._record is not None                        # Speicher bleibt
        assert e.toggle_record() is True and e.recording   # ohne Laden
        assert not e.record_pending

    def test_stoppen_gibt_den_speicher_wieder_her(self, laufend):
        e, _ = laufend
        e.toggle_record(); _warten_bis_reserviert(e)
        e.stop()
        assert e._record is None and not e.recording

    def test_zu_wenig_speicher_ist_kein_fehler(self, args):
        args.record_buffer = 30.0
        with patch("jampilot.delay_stream.DelayedLoopback") as Loop, \
             patch("jampilot.cli._display_loop"), \
             patch("jampilot.record_buffer.verfuegbarer_speicher",
                   return_value=2 ** 20):
            Loop.return_value.muted = False
            Loop.return_value.samplerate, Loop.return_value.channels = 48000, 2
            Loop.return_value.recording = False
            e = Engine(args)
            e.start()
            try:
                e.toggle_record(); _warten_bis_reserviert(e)
                assert e.status == "running"
                assert e._record is None
                # Der Hinweis wird einmal gemeldet und dann abgeraeumt (damit
                # R es wieder versuchen darf) - dauerhaft steht er im
                # Startprotokoll.
                assert "not enough free memory" in " ".join(e.protokoll.zeilen())
                Loop.return_value.attach_record.assert_not_called()
            finally:
                e.stop()

    def test_der_browser_erfaehrt_jeden_wechsel_sofort(self, args):
        args.record_buffer = 0.02
        broadcaster = MagicMock()
        with patch("jampilot.delay_stream.DelayedLoopback") as Loop, \
             patch("jampilot.cli._display_loop"):
            loop = Loop.return_value
            loop.muted = False
            loop.samplerate, loop.channels = 8000, 2
            loop.recording, loop.record_paused, loop.record_epoch = True, False, 7
            e = Engine(args, broadcaster=broadcaster)
            e.start()
            try:
                e._record = MagicMock()
                e.toggle_record_pause()
                broadcaster.republish.assert_called_with(
                    recording=True, record_pending=False, paused=False,
                    record_hint=None)
            finally:
                e.stop()

    def test_der_epoch_reist_nie_ohne_frisches_t(self, args):
        """Der Fehler, der das Laufband nach jedem Sprung stehen liess.

        `republish` traegt das ALTE `t`. Ein Epoch darin liesse die Seite ihre
        Uhr auf die alte Position neu stellen - und der richtige Wert eine
        Viertelsekunde spaeter bekaeme nur noch die Drift-Glaettung: bis zu zehn
        Sekunden falsche Anzeige nach einem Sprung zurueck.
        """
        args.record_buffer = 0.02
        broadcaster = MagicMock()
        with patch("jampilot.delay_stream.DelayedLoopback") as Loop, \
             patch("jampilot.cli._display_loop"):
            loop = Loop.return_value
            loop.muted = False
            loop.samplerate, loop.channels = 8000, 2
            loop.recording, loop.record_paused, loop.record_epoch = True, False, 7
            loop.heard_position.return_value = 30.0
            e = Engine(args, broadcaster=broadcaster)
            e.start()
            try:
                e._record = MagicMock()
                e.onsets = (10.0, 20.0, 40.0)
                e.seek_chord(-1)
                e.seek_chord(+1)
                e.record_to_now()
                for aufruf in broadcaster.republish.call_args_list:
                    assert "epoch" not in aufruf.kwargs, aufruf
                    assert "t" not in aufruf.kwargs, aufruf
            finally:
                e.stop()


class TestAkkordspruenge:
    """Die Pfeiltasten springen auf Akkordgrenzen, nicht auf Sekunden."""

    def _engine(self, jetzt, onsets):
        from jampilot.engine import Engine as E
        e = E.__new__(E)
        e._loop = MagicMock()
        e._loop.recording = True
        e._loop.heard_position.return_value = jetzt
        e._record = MagicMock()
        e.onsets = tuple(onsets)
        e.broadcaster = None
        e._on_change = lambda: None
        return e

    def test_zurueck_geht_an_den_anfang_des_laufenden_akkords(self):
        from jampilot.engine import LANDUNG
        e = self._engine(jetzt=14.0, onsets=(10.0, 20.0))     # 4 s im Akkord
        e.seek_chord(-1)
        e._record.seek.assert_called_once_with(pytest.approx(10.0 + LANDUNG - 14.0))

    def test_am_anfang_geht_zurueck_eine_grenze_weiter(self):
        # CD-Player: Wer schon am Anfang steht, will den davor.
        from jampilot.engine import LANDUNG
        e = self._engine(jetzt=10.5, onsets=(4.0, 10.0, 20.0))
        e.seek_chord(-1)
        e._record.seek.assert_called_once_with(pytest.approx(4.0 + LANDUNG - 10.5))

    def test_am_anfang_des_ersten_akkords_geht_es_an_den_anfang(self):
        e = self._engine(jetzt=10.2, onsets=(10.0, 20.0))
        e.seek_chord(-1)
        e._record.to_start.assert_called_once()

    def test_vor_landet_auf_dem_naechsten_nicht_davor(self):
        """Der Zielakkord muss in der Anzeige der KLINGENDE sein.

        Der erste Entwurf landete 0,7 s vor dem Onset ("den Anlauf hoeren") und
        ist im Proberaum gescheitert: Der Zielakkord sass sichtbar rechts von
        NOW, gross stand noch der davor. Jetzt: ein Wimpernschlag NACH dem
        Onset - nie davor.
        """
        from jampilot.engine import LANDUNG
        assert LANDUNG > 0
        e = self._engine(jetzt=12.0, onsets=(10.0, 20.0, 30.0))
        e.seek_chord(+1)
        e._record.seek.assert_called_once_with(pytest.approx(20.0 + LANDUNG - 12.0))

    def test_vor_zaehlt_den_akkord_nicht_auf_dem_man_gerade_gelandet_ist(self):
        # Nach einem Sprung auf 20.0 steht man bei 20.0 + LANDUNG. "Vor" muss
        # dann 30.0 meinen - sonst spraenge es um LANDUNG zurueck.
        from jampilot.engine import LANDUNG
        e = self._engine(jetzt=20.0 + LANDUNG, onsets=(10.0, 20.0, 30.0))
        e.seek_chord(+1)
        e._record.seek.assert_called_once_with(pytest.approx(30.0 + LANDUNG - (20.0 + LANDUNG)))

    def test_ohne_naechsten_geht_es_an_die_live_kante(self):
        e = self._engine(jetzt=25.0, onsets=(10.0, 20.0))
        e.seek_chord(+1)
        e._record.to_now.assert_called_once()
        e._record.seek.assert_not_called()

    def test_ohne_vorigen_geht_es_an_den_anfang(self):
        e = self._engine(jetzt=5.0, onsets=(10.0, 20.0))
        e.seek_chord(-1)
        e._record.to_start.assert_called_once()

    def test_ohne_aufnahme_passiert_nichts(self):
        e = self._engine(jetzt=14.0, onsets=(10.0,))
        e._loop.recording = False
        e.seek_chord(-1)
        e._record.seek.assert_not_called()

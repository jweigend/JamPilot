"""Das Kontrollfenster: zeigt es den Zustand, und raeumt es beim Schliessen auf?

Ohne Anzeige laeuft Qt hier im Offscreen-Modus. Geprueft wird die Verdrahtung
zur Engine - nicht, wie es aussieht.
"""

import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from jampilot import gui  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class FakeEngine:
    def __init__(self):
        self._running = False
        self._muted = False
        self.status = "stopped"
        self.fehler = None
        self.lead = 0.0
        self.starts = 0
        self.stops = 0

    running = property(lambda self: self._running)
    muted = property(lambda self: self._muted)
    delay_seconds = 4.0

    def start(self):
        self._running, self.status, self.starts = True, "running", self.starts + 1

    def stop(self):
        self._running, self._muted = False, False
        self.status, self.stops = "stopped", self.stops + 1

    def toggle_mute(self):
        self._muted = not self._muted
        return self._muted


@pytest.fixture
def fenster(app):
    e = FakeEngine()
    return gui.Fenster(e, "http://192.168.1.42:8765/"), e


class TestSymbol:
    def test_das_fenster_traegt_das_programmsymbol(self, fenster):
        # Ein leeres QIcon ist kein Fehler fuer Qt - nur ein Fenster ohne Symbol
        # in der Leiste. Also pruefen, dass die Datei gefunden und geladen wurde.
        f, _ = fenster
        assert not f.windowIcon().isNull()
        assert f.windowIcon().availableSizes()


class TestZustandAnzeigen:
    def test_zeigt_gestoppt(self, fenster):
        f, _ = fenster
        assert f.zustand.text() == "Stopped"
        assert not f.routing.schieber.isChecked()

    def test_zeigt_laufend(self, fenster):
        f, e = fenster
        e.start()
        f.nachziehen()
        assert f.zustand.text() == "Running"
        assert f.routing.schieber.isChecked()
        assert f.stumm.schieber.isChecked()      # Schieber heisst SOUND: an = hoerbar

    def test_zeigt_stumm(self, fenster):
        f, e = fenster
        e.start()
        e.toggle_mute()
        f.nachziehen()
        assert f.zustand.text() == "Muted"
        assert f.routing.schieber.isChecked()    # umgeleitet bleibt es!
        assert not f.stumm.schieber.isChecked()

    def test_der_schieber_steht_sofort_richtig(self, fenster):
        # Beim Oeffnen laeuft der Betrieb laengst. Wuerde der Schieber von "aus"
        # losanimieren, zeigte das Fenster im ersten Moment genau die Luege,
        # gegen die es gebaut wurde.
        f, e = fenster
        e.start()
        f.nachziehen()
        assert f.routing.schieber.schieberPos == 1.0

    def test_stummschalter_ist_ohne_betrieb_gesperrt(self, fenster):
        f, _ = fenster
        assert not f.stumm.schieber.isEnabled()


class TestBedienung:
    def test_hauptschalter_startet_und_stoppt(self, fenster):
        f, e = fenster
        f.routing.schieber.click()
        assert e.starts == 1 and e.running
        f.routing.schieber.click()
        assert e.stops >= 1 and not e.running

    def test_nachziehen_loest_keinen_schaltvorgang_aus(self, fenster):
        # Sonst wuerde das Fenster sich selbst im Kreis schalten: nachziehen()
        # setzt den Schieber, der Schieber ruft den Handler, der schaltet die
        # Engine... Diesen Kreis bricht `_eigene_aenderung`.
        f, e = fenster
        e.start()
        for _ in range(5):
            f.nachziehen()
        assert e.starts == 1 and e.stops == 0

    def test_stummschalter_schaltet_stumm(self, fenster):
        f, e = fenster
        e.start()
        f.nachziehen()
        f.stumm.schieber.click()        # von "Sound an" auf "Sound aus"
        assert e.muted


class TestAufraeumen:
    def test_schliessen_baut_die_umleitung_zurueck(self, fenster):
        # Das ist der Punkt der ganzen Uebung: Wer das Fenster zumacht, darf
        # keinen umgeleiteten Systemton zuruecklassen.
        f, e = fenster
        e.start()
        f.close()
        assert e.stops >= 1
        assert not e.running


class TestSignale:
    """`kill` und Strg+C muessen die Qt-Schleife verlassen.

    Sonst ueberlebt JamPilot ein SIGTERM: Der Prozess laeuft weiter, der
    Null-Sink bleibt Standardausgang - und der Rechner bleibt stumm. Genau der
    Zustand, gegen den es das Fenster gibt. (So war es: Der Handler der
    Kommandozeile wirft KeyboardInterrupt, PySide6 faengt das in seinen
    Verbindungen ab, druckt einen Traceback und macht weiter. Zu beenden war der
    Prozess nur noch mit kill -9.)
    """

    def test_sigterm_und_sigint_verlassen_die_schleife(self, app):
        import signal

        gerufen = []
        app.quit = lambda: gerufen.append(True)

        wecker = gui.beenden_bei_signal(app)
        try:
            for zeichen in (signal.SIGTERM, signal.SIGINT):
                handler = signal.getsignal(zeichen)
                assert callable(handler)
                handler(zeichen, None)          # so kaeme das Signal an
            assert len(gerufen) == 2            # ... und beide Male wird beendet
        finally:
            wecker.stop()
            signal.signal(signal.SIGINT, signal.default_int_handler)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)

    def test_ein_zeitgeber_haelt_den_interpreter_wach(self, app):
        """Ohne ihn kommt der Signalhandler nie dran.

        Python fuehrt Handler nur zwischen Bytecodes aus - waehrend app.exec()
        laeuft, steckt der Interpreter in C++. Ein Zeitgeber, der nichts tut,
        gibt ihm regelmaessig die Gelegenheit dazu.
        """
        import signal

        wecker = gui.beenden_bei_signal(app)
        try:
            assert wecker.isActive()
        finally:
            wecker.stop()
            signal.signal(signal.SIGINT, signal.default_int_handler)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)


class TestLink:
    def test_die_adresse_der_webanzeige_steht_da_und_ist_klickbar(self, fenster):
        f, _ = fenster
        assert "http://192.168.1.42:8765/" in f.link.text()
        assert "<a href=" in f.link.text()
        assert f.link.openExternalLinks()

    def test_ohne_webanzeige_wird_das_gesagt(self, app):
        f = gui.Fenster(FakeEngine(), None)
        assert "--no-web" in f.link.text()
        assert not f.anzeige_knopf.isEnabled()


class TestStartprotokoll:
    """Das Fenster zeigt die laufende Etappe - eine Zeile, die wechselt."""

    def test_ohne_protokoll_bleibt_die_zeile_leer(self, fenster):
        f, _ = fenster                       # FakeEngine hat kein Protokoll
        f.nachziehen()
        assert f.etappe.text() == ""

    def test_das_fenster_oeffnet_sich_gross_genug_fuer_den_start(self, app):
        """Die Karten wurden beim Start zusammengedrueckt: Das Fenster ging mit
        dem Stopped-Inhalt auf, dann kamen Starthinweis und Etappenzeile dazu,
        und ein geoeffnetes Fenster waechst nicht nach. Der Inhalt darf nach
        dem show() also nicht mehr Platz brauchen, als das Fenster hat."""
        from jampilot.engine import Startprotokoll

        e = FakeEngine()
        e.protokoll = Startprotokoll()
        f = gui.Fenster(e, "http://192.168.1.42:8765/")
        f.startet = True                     # wie run(): Starting VOR dem show()
        f.nachziehen()
        f.show()
        app.processEvents()
        hoehe_beim_oeffnen = f.height()

        e.protokoll.melden("Window open")
        with e.protokoll.etappe("Compiling the analysis (first start: up to "
                                "a minute)"):
            f.nachziehen()
            app.processEvents()
            assert f.sizeHint().height() <= hoehe_beim_oeffnen
            assert f.height() == hoehe_beim_oeffnen
        f.close()

    def test_zeigt_nur_die_juengste_etappe(self, app):
        from jampilot.engine import Startprotokoll

        e = FakeEngine()
        e.protokoll = Startprotokoll()
        f = gui.Fenster(e, "http://192.168.1.42:8765/")
        e.protokoll.melden("Window open")
        with e.protokoll.etappe("Compiling the analysis"):
            f.nachziehen()
            assert f.etappe.text() == "Compiling the analysis ..."
        with e.protokoll.etappe("Routing the system audio"):
            f.nachziehen()
            assert f.etappe.text() == "Routing the system audio ..."
            assert "Compiling" not in f.etappe.text()   # kein Log

    def test_der_starthinweis_nennt_die_erste_minute(self, fenster):
        f, _ = fenster
        f.startet = True
        f.nachziehen()
        assert "up to a minute" in f.hinweis.text()


class TestLiveZeile:
    """Laeuft die Analyse, wird die Etappenzeile zur Live-Zeile."""

    def test_zeigt_now_playing_sobald_es_laeuft(self, fenster):
        f, e = fenster
        e.start()
        e.jetzt = "Now playing C \u00b7 next G in 1.3 s \u00b7 Key C major"
        f.nachziehen()
        assert f.etappe.text() == e.jetzt

    def test_nach_dem_stopp_wieder_die_etappe(self, app):
        from jampilot.engine import Startprotokoll

        e = FakeEngine()
        e.protokoll = Startprotokoll()
        e.protokoll.melden("First window analysed - chords are live")
        f = gui.Fenster(e, "http://192.168.1.42:8765/")
        e.start()
        e.jetzt = "Now playing C \u00b7 next G in 1.3 s \u00b7 Key C major"
        f.nachziehen()
        e.stop()
        e.jetzt = ""
        f.nachziehen()
        assert f.etappe.text() == "First window analysed - chords are live"

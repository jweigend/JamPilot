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

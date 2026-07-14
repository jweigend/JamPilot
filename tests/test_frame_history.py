"""Die Onset-Suche darf nicht an der Fensterlaenge scheitern.

Wie lange die Erkennung braucht, haengt vom Material ab: bei mehrdeutigen
Wechseln (C/Am, G/Em) dauert es laenger, bis die gepoolte Mehrheit kippt. Wird
der Onset nur im aktuellen Analysefenster gesucht, liegt der Einsatz dann VOR
dem Fensteranfang - und die Suche klemmt darauf. Dieser Fehler ist einseitig:
die Anzeige wird zu spaet, nie zu frueh, und die Verspaetung ist unbegrenzt.
Gemessen: bei 2s Erkennungslatenz meldete die alte Fensterlogik den Wechsel um
bis zu 600 ms zu spaet.
"""

import numpy as np
import pytest

from jampilot.chords import find_onset_frame
from jampilot.chroma import FRAME_SECONDS, FrameHistory
from jampilot.cli import MAX_ONSET_SEARCH, _locate_onset

TAKT = 0.28          # so schnell folgen die Analysen aufeinander
FENSTER = 1.5


def _fenster_frames(akkord_bei, window_start, window_laenge=FENSTER):
    """Frame-Chroma eines Fensters: vor `akkord_bei` klingt C, danach G."""
    from jampilot.chroma import NOTE_NAMES

    def chroma(*noten):
        vec = np.zeros(12)
        for n in noten:
            vec[NOTE_NAMES.index(n)] = 1.0
        return vec / vec.sum()

    anzahl = int(window_laenge / FRAME_SECONDS) + 1
    spalten = []
    for i in range(anzahl):
        zeit = window_start + i * FRAME_SECONDS
        spalten.append(chroma("G", "B", "D") if zeit >= akkord_bei
                       else chroma("C", "E", "G"))
    return np.array(spalten).T


class TestFrameHistory:
    def test_gibt_frames_in_stream_koordinaten_zurueck(self):
        history = FrameHistory(seconds=8.0)
        history.add(_fenster_frames(akkord_bei=99, window_start=2.0), window_start=2.0)

        frames, start = history.since(2.5)
        assert start == pytest.approx(2.5, abs=FRAME_SECONDS)
        assert frames.shape[0] == 12
        assert frames.shape[1] > 10

    def test_zu_wenig_material_liefert_none(self):
        history = FrameHistory(seconds=8.0)
        assert history.since(0.0) is None

    def test_ueberlebt_den_wraparound(self):
        history = FrameHistory(seconds=2.0)          # absichtlich kurz
        for i in range(20):                          # weit mehr als der Puffer fasst
            start = i * TAKT
            history.add(_fenster_frames(akkord_bei=99, window_start=start), start)

        juengste = history.since(history.end * FRAME_SECONDS - 1.0)
        assert juengste is not None
        frames, _ = juengste
        assert np.all(np.isfinite(frames))


class TestOnsetSucheReichtZurueck:
    @staticmethod
    def _historie_bis(window_end, onset=2.0):
        """Frame-Historie, wie sie nach mehreren Analysetakten aussieht -
        der Akkord wechselt bei `onset` von C auf G."""
        history = FrameHistory(MAX_ONSET_SEARCH + FENSTER + 1.0)
        start = 0.0
        while start + FENSTER <= window_end + 1e-9:
            history.add(_fenster_frames(onset, start), start)
            start += TAKT
        return history

    @pytest.mark.parametrize("erkennungslatenz", [0.8, 1.2, 1.6, 2.0, 2.8])
    def test_onset_bleibt_genau_egal_wie_spaet_erkannt_wird(self, erkennungslatenz):
        # Der Wechsel liegt bei 2.0s; erkannt wird er erst `erkennungslatenz`
        # spaeter. Frueher reichte die Suche nur 1.5s zurueck - alles darueber
        # wurde auf den Fensteranfang geklemmt und damit zu spaet gemeldet.
        onset_echt = 2.0
        window_end = onset_echt + erkennungslatenz
        history = self._historie_bis(window_end, onset_echt)

        gemessen = _locate_onset("G", "C", history, window_end, last_onset=0.0)
        fehler = gemessen - onset_echt
        assert abs(fehler) < 0.100, (
            f"bei {erkennungslatenz}s Erkennungslatenz um {fehler * 1000:+.0f} ms daneben")

    def test_fehler_ist_nicht_einseitig_verspaetet(self):
        """Der Kern der Beschwerde: es hinkt nur NACH hinten. Ein Verfahren, das
        klemmt, kann gar nicht zu frueh liegen - genau daran erkennt man es."""
        fehler = []
        for latenz in [0.8, 1.2, 1.6, 2.0, 2.4, 2.8]:
            history = self._historie_bis(2.0 + latenz, onset=2.0)
            fehler.append(_locate_onset("G", "C", history, 2.0 + latenz, 0.0) - 2.0)

        assert max(fehler) < 0.100, "kein Wechsel darf spuerbar zu spaet kommen"
        # Und die Verspaetung darf nicht mit der Erkennungslatenz wachsen.
        assert abs(fehler[-1] - fehler[0]) < 0.060, (
            "Fehler waechst mit der Erkennungslatenz - die Suche klemmt wieder")

    def test_sucht_nicht_hinter_den_letzten_wechsel_zurueck(self):
        # Vor `last_onset` stand ein anderer Akkord; dessen Frames wuerden die
        # Suche nur verwaessern.
        history = self._historie_bis(4.0, onset=2.0)
        gemessen = _locate_onset("G", "C", history, 4.0, last_onset=1.8)
        assert gemessen >= 1.8

    def test_stille_braucht_keine_historie(self):
        history = FrameHistory(4.0)
        gemessen = _locate_onset("-", "C", history, 10.0, last_onset=5.0)
        assert 9.0 < gemessen <= 10.0

"""Zeitleiste: `_commit` nimmt zu kurze Segmente zurueck, statt sie anzuzeigen."""

import pytest

from chordelay.cli import MIN_CHORD_SECONDS, _commit

NICHT_HOERBAR = -99.0   # alles liegt noch im Vorlauf und ist ruecknehmbar


def _dauern(timeline):
    return [round(timeline[i + 1][0] - timeline[i][0], 3)
            for i in range(len(timeline) - 1)]


def _spiele(events, audible=NICHT_HOERBAR):
    timeline = []
    for onset, chord in events:
        _commit(timeline, onset, chord, audible)
    return timeline


class TestCommit:
    def test_normale_wechsel_bleiben_erhalten(self):
        timeline = _spiele([(0.0, "C"), (2.0, "G"), (4.0, "Am")])
        assert timeline == [(0.0, "C"), (2.0, "G"), (4.0, "Am")]

    def test_schnelle_echte_wechsel_ueberleben(self):
        # Halbe Sekunde pro Akkord ist Musik, kein Artefakt.
        timeline = _spiele([(4.0, "Am"), (4.5, "F"), (5.0, "C"), (5.5, "G")])
        assert [c for _, c in timeline] == ["Am", "F", "C", "G"]
        assert _dauern(timeline) == [0.5, 0.5, 0.5]

    def test_fehlgriff_zwischen_gleichen_akkorden_verschwindet(self):
        # C - (Blip Em) - C  =>  C lief einfach durch.
        timeline = _spiele([(2.0, "C"), (6.0, "Em"), (6.05, "C")])
        assert timeline == [(2.0, "C")]

    def test_fehlgriff_nach_echtem_wechsel_wird_zurueckgenommen(self):
        # Der korrekte Wechsel auf G bleibt erhalten, der Blip Em fliegt raus.
        timeline = _spiele([(2.0, "C"), (6.0, "G"), (6.1, "Em"), (6.05, "G")])
        assert timeline == [(2.0, "C"), (6.0, "G")]

    def test_onset_vor_dem_vorigen_erzeugt_kein_kurzsegment(self):
        # Faellt die Changepoint-Suche VOR den letzten Onset, entstand frueher
        # ein 23-ms-Segment (Monotonie-Clamp). Jetzt loest sich das auf.
        timeline = _spiele([(2.0, "C"), (6.0, "G"), (5.98, "Am")])
        assert _dauern(timeline) == [3.98]
        assert [c for _, c in timeline] == ["C", "Am"]

    def test_kette_von_fehlgriffen_konvergiert(self):
        # Vier Fehldetektionen in 80 ms -> ein einziger Wechsel, Zeitpunkt bleibt.
        timeline = _spiele([(2.0, "C"), (6.0, "Em"), (6.05, "Dm"),
                            (6.02, "F"), (6.08, "G")])
        assert timeline == [(2.0, "C"), (6.0, "G")]

    def test_grenzfall_genau_min_chord_ist_gueltig(self):
        timeline = _spiele([(2.0, "C"), (2.0 + MIN_CHORD_SECONDS, "G")])
        assert len(timeline) == 2

    def test_bereits_hoerbares_segment_wird_nicht_umgeschrieben(self):
        # Was der Nutzer schon gehoert hat, laesst sich nicht zuruecknehmen -
        # der Wechsel wird stattdessen nach hinten geschoben, damit die Anzeige
        # trotzdem nicht fuer 50 ms aufblitzt.
        timeline = _spiele([(2.0, "C"), (2.05, "G")], audible=3.0)
        assert timeline[0] == (2.0, "C")
        assert timeline[1][1] == "G"
        assert timeline[1][0] - timeline[0][0] >= MIN_CHORD_SECONDS

    @pytest.mark.parametrize("events", [
        [(2.0, "C"), (6.0, "Em"), (6.05, "C")],
        [(2.0, "C"), (6.0, "G"), (6.1, "Em"), (6.05, "G")],
        [(2.0, "C"), (6.0, "Em"), (6.05, "Dm"), (6.02, "F"), (6.08, "G")],
        [(4.0, "Am"), (4.5, "F"), (5.0, "C"), (5.5, "G")],
    ])
    def test_niemals_ein_segment_unter_min_chord(self, events):
        timeline = _spiele(events)
        assert all(d >= MIN_CHORD_SECONDS for d in _dauern(timeline))

    def test_rueckgabe_ist_der_wirksame_onset(self):
        timeline = []
        assert _commit(timeline, 2.0, "C", NICHT_HOERBAR) == 2.0
        # Blip: neues Segment, aber es erbt spaeter den frueheren Onset.
        assert _commit(timeline, 6.0, "Em", NICHT_HOERBAR) == 6.0
        # Rueckkehr zu C -> kein neues Segment, also None.
        assert _commit(timeline, 6.05, "C", NICHT_HOERBAR) is None
        assert timeline == [(2.0, "C")]

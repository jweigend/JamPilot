"""Akkordwahl, Glaetter und Onset-Suche."""

import numpy as np
import pytest

from jampilot.bass import slash
from jampilot.chords import (
    ChordResult,
    ChordSmoother,
    find_onset_frame,
    match_chord,
)
from jampilot.chroma import NOTE_NAMES


def _chroma(*notes: str) -> np.ndarray:
    vec = np.zeros(12)
    for note in notes:
        vec[NOTE_NAMES.index(note)] = 1.0
    return vec / vec.sum()


class TestMatchChord:
    def test_erkennt_dur_und_moll(self):
        assert match_chord(_chroma("C", "E", "G")).name == "C"
        assert match_chord(_chroma("A", "C", "E")).name == "Am"

    def test_stille_ist_kein_akkord(self):
        assert match_chord(np.zeros(12)).name == "N"
        assert not match_chord(np.zeros(12)).is_chord

    def test_umkehrung_verbiegt_den_akkord_nicht(self):
        # F-A-C bleibt F, auch wenn unten das A liegt. Ein BASS_BONUS zog hier
        # frueher den Grundton auf die Bassnote und machte ein Am daraus - und
        # Am verspricht ein E, das im Stueck gar nicht klingt. Der Akkord
        # entscheidet sich an der Tonklassen-MENGE, sonst an nichts.
        assert match_chord(_chroma("F", "A", "C"), cqt=True).name == "F"
        assert match_chord(_chroma("C", "E", "G"), cqt=True).name == "C"

    def test_der_bass_redet_bei_der_akkordwahl_nicht_mit(self):
        # C-E-G-A ist als C6 dieselbe Tonklassenmenge wie als Am7. Welche davon
        # unten liegt, kann und soll das Chroma nicht entscheiden - die Bassnote
        # wird gemessen (bass.py) und erst im Slash-Namen sichtbar. Genau diese
        # Trennung macht Umkehrungen ueberhaupt erst erkennbar.
        akkord = match_chord(_chroma("C", "E", "G", "A"), cqt=True).name
        assert slash(akkord, "C") != slash(akkord, "A")
        # Beide Lesarten sind musikalisch dieselbe Menge - egal, welche das
        # Matching waehlt: mit dem gemessenen Bass steht die Umkehrung da.
        assert akkord in ("C", "Am7")


class TestChordSmoother:
    def test_liefert_fragezeichen_bis_fenster_voll(self):
        smoother = ChordSmoother(window=3)
        assert smoother.update(ChordResult("C", 0.9)) == "?"
        assert smoother.update(ChordResult("C", 0.9)) == "?"
        assert smoother.update(ChordResult("C", 0.9)) == "C"

    @pytest.mark.parametrize("folge,erwartet", [
        (["C", "C", "G"], "C"),
        (["C", "G", "G"], "G"),
        (["G", "G", "G"], "G"),
    ])
    def test_mehrheit_setzt_sich_durch(self, folge, erwartet):
        smoother = ChordSmoother(window=3)
        for name in folge:
            ergebnis = smoother.update(ChordResult(name, 0.9))
        assert ergebnis == erwartet

    def test_gleichstand_raet_nicht(self):
        # Drei verschiedene Akkorde = keine Mehrheit. Frueher entschied hier die
        # Set-Iterationsreihenfolge, also der PYTHONHASHSEED - das Ergebnis war
        # zwischen Laeufen verschieden und erzeugte Phantomwechsel.
        smoother = ChordSmoother(window=3)
        for name in ["C", "G", "Am"]:
            ergebnis = smoother.update(ChordResult(name, 0.9))
        assert ergebnis == "?"

    def test_gleichstand_ist_deterministisch(self):
        # Reihenfolge darf das Ergebnis nicht aendern.
        ergebnisse = set()
        for folge in [["C", "G", "Am"], ["Am", "C", "G"], ["G", "Am", "C"]]:
            smoother = ChordSmoother(window=3)
            for name in folge:
                ergebnis = smoother.update(ChordResult(name, 0.9))
            ergebnisse.add(ergebnis)
        assert ergebnisse == {"?"}

    def test_reset_leert_die_historie(self):
        smoother = ChordSmoother(window=3)
        for _ in range(3):
            smoother.update(ChordResult("C", 0.9))
        smoother.reset()
        assert smoother.update(ChordResult("G", 0.9)) == "?"


class TestFindOnsetFrame:
    @staticmethod
    def _frames(erster: str, zweiter: str, wechsel_bei: int, gesamt: int = 60):
        """Frame-Chroma, das bei `wechsel_bei` hart von einem Akkord zum
        anderen springt."""
        spalten = []
        for i in range(gesamt):
            akkord = erster if i < wechsel_bei else zweiter
            noten = {"C": ("C", "E", "G"), "G": ("G", "B", "D"),
                     "Am": ("A", "C", "E"), "F": ("F", "A", "C")}[akkord]
            spalten.append(_chroma(*noten))
        return np.array(spalten).T

    def test_findet_den_wechsel(self):
        frames = self._frames("C", "G", wechsel_bei=25)
        assert find_onset_frame(frames, "C", "G") == 25

    def test_findet_wechsel_am_fensteranfang(self):
        frames = self._frames("C", "G", wechsel_bei=3)
        assert find_onset_frame(frames, "C", "G") == 3

    def test_ohne_vorgaenger_und_ganzes_fenster_neu(self):
        # Traegt der Akkord das ganze Fenster, liegt sein Einsatz DAVOR - die
        # ehrliche Antwort ist Frame 0, nicht ein erfundener Wechsel in der Mitte.
        frames = self._frames("G", "G", wechsel_bei=0)
        assert find_onset_frame(frames, None, "G") == 0

    def test_unbekannter_akkord_liefert_none(self):
        frames = self._frames("C", "G", wechsel_bei=25)
        assert find_onset_frame(frames, "C", "Hx7") is None

    def test_ohne_frames_liefert_none(self):
        assert find_onset_frame(None, "C", "G") is None

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
from jampilot.harmony import interpret_chord, safe_pitch_classes
from jampilot.chroma import NOTE_NAMES
from jampilot.tonality import Key


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


class TestHarmonicInterpreter:
    @staticmethod
    def _result(*candidates):
        from jampilot.chords import ChordCandidate
        hypotheses = tuple(ChordCandidate(*candidate) for candidate in candidates)
        first = hypotheses[0]
        return ChordResult(first.name, first.score, first.root, first.quality,
                           hypotheses)

    def test_korrigiert_knappes_dur_in_moll(self):
        # A-Dur gewinnt akustisch hauchduenn, bringt in a-Moll aber ein C# mit.
        raw = self._result(("A", .80, 9, ""), ("Am", .78, 9, "m"))
        key = Key(tonic=9, minor=True, confidence=.9)
        assert interpret_chord(raw, key).name == "Am"

    def test_korrigiert_echte_matcher_kandidaten(self):
        # Gemeinsame Toene A/E, beide Terzen im Spektrum; C# ist nur etwas
        # staerker und laesst den Signal-Matcher knapp A-Dur waehlen.
        chroma = np.zeros(12)
        chroma[[NOTE_NAMES.index(note) for note in ("A", "E")]] = (1.0, .8)
        chroma[NOTE_NAMES.index("C#")] = .55
        chroma[NOTE_NAMES.index("C")] = .45
        raw = match_chord(chroma, cqt=True)
        assert raw.name == "A"
        key = Key(tonic=9, minor=True, confidence=.9)
        assert interpret_chord(raw, key).name == "Am"

    def test_klare_audioevidenz_bleibt_unangetastet(self):
        raw = self._result(("A", .90, 9, ""), ("Am", .76, 9, "m"))
        key = Key(tonic=9, minor=True, confidence=.95)
        assert interpret_chord(raw, key).name == "A"

    def test_tonart_erfindet_keinen_anderen_grundton(self):
        raw = self._result(("A", .80, 9, ""), ("Dm", .79, 2, "m"))
        key = Key(tonic=9, minor=True, confidence=.95)
        assert interpret_chord(raw, key).name == "A"

    @pytest.mark.parametrize("name,quality", [("E", ""), ("E7", "7")])
    def test_dur_dominante_in_moll_bleibt_erlaubt(self, name, quality):
        raw = self._result((name, .80, 4, quality), ("Em", .79, 4, "m"))
        key = Key(tonic=9, minor=True, confidence=.95)
        assert interpret_chord(raw, key).name == name

    def test_ohne_tonart_bleibt_roher_gewinner(self):
        raw = self._result(("A", .80, 9, ""), ("Am", .79, 9, "m"))
        assert interpret_chord(raw, None).name == "A"

    def test_unsichere_terz_wird_nicht_zum_mitspielen_freigegeben(self):
        raw = self._result(("A", .80, 9, ""), ("Am", .78, 9, "m"))
        assert safe_pitch_classes(raw) == (9, 4)       # A + E, weder C# noch C

    def test_unsichere_septime_faellt_auf_dreiklang_zurueck(self):
        raw = self._result(("A7", .80, 9, "7"), ("A", .77, 9, ""))
        assert safe_pitch_classes(raw) == (9, 1, 4)    # A C# E, ohne G

    def test_eindeutiger_akkord_bleibt_vollstaendig(self):
        raw = self._result(("Am7", .90, 9, "m7"), ("Am", .82, 9, "m"))
        assert safe_pitch_classes(raw) == (9, 0, 4, 7)


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

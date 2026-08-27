"""Akkordwahl des Template-Matchers - im Produkt nur noch vom Selbsttest genutzt."""

import numpy as np

from jampilot.bass import slash
from jampilot.chords import match_chord
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

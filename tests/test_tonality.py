"""Tonart-Erkennung und die daraus folgende Schreibweise (# oder b)."""

import numpy as np
import pytest

from jampilot.chroma import NOTE_NAMES
from jampilot.tonality import (
    FLAT,
    MIN_KEY_SECONDS,
    SHARP,
    Key,
    KeyEstimator,
    accidental_for_key,
    estimate_key,
    spell,
)


def _chroma(*notes: str) -> np.ndarray:
    vec = np.zeros(12)
    for note in notes:
        vec[NOTE_NAMES.index(note)] = 1.0
    return vec / vec.sum()


# Typische Kadenzen. Die Tonart steckt nicht im einzelnen Akkord, sondern in
# dem, was ueber mehrere Akkorde hinweg klingt - genau das wird hier gefuettert.
KADENZEN = {
    # C-Dur: C  F  G  Am
    "C major": [("C", "E", "G"), ("F", "A", "C"), ("G", "B", "D"), ("A", "C", "E")],
    # F-Dur: F  Bb  C  Dm   (Bb = die Tonklasse, die als A# falsch geschrieben waere)
    "F major": [("F", "A", "C"), ("A#", "D", "F"), ("C", "E", "G"), ("D", "F", "A")],
    # D-Dur: D  G  A  Bm    (mit F# und C#)
    "D major": [("D", "F#", "A"), ("G", "B", "D"), ("A", "C#", "E"), ("B", "D", "F#")],
    # a-Moll: Am  Dm  E  Am
    "A minor": [("A", "C", "E"), ("D", "F", "A"), ("E", "G#", "B"), ("A", "C", "E")],
    # d-Moll: Dm  Gm  A  Dm
    "D minor": [("D", "F", "A"), ("G", "A#", "D"), ("A", "C#", "E"), ("D", "F", "A")],
}


def _hoere(kadenz, sekunden: float = 40.0, hop: float = 0.25) -> KeyEstimator:
    """Die Kadenz so lange in einen Estimator spielen, wie angegeben."""
    estimator = KeyEstimator(hop)
    schritte = int(sekunden / hop)
    for i in range(schritte):
        estimator.add(_chroma(*kadenz[i // 8 % len(kadenz)]))
    return estimator


class TestAccidentalForKey:
    @pytest.mark.parametrize("tonart,tonika,moll,erwartet", [
        ("C major", 0, False, SHARP),     # keine Vorzeichen -> Kreuze als Vorgabe
        ("G major", 7, False, SHARP),
        ("D major", 2, False, SHARP),
        ("F major", 5, False, FLAT),
        ("Bb major", 10, False, FLAT),
        ("Eb major", 3, False, FLAT),
        ("A minor", 9, True, SHARP),     # Paralleltonart C-Dur
        ("E minor", 4, True, SHARP),     # Paralleltonart G-Dur
        ("D minor", 2, True, FLAT),      # Paralleltonart F-Dur
        ("G minor", 7, True, FLAT),      # Paralleltonart Bb-Dur
        ("C minor", 0, True, FLAT),      # Paralleltonart Eb-Dur
    ])
    def test_vorzeichen_der_tonart(self, tonart, tonika, moll, erwartet):
        assert accidental_for_key(tonika, moll) == erwartet, tonart

    def test_moll_erbt_von_der_paralleltonart(self):
        # Jede Molltonart schreibt sich wie ihre Durparallele (kleine Terz hoeher).
        for tonika in range(12):
            assert (accidental_for_key(tonika, minor=True)
                    == accidental_for_key((tonika + 3) % 12, minor=False))


class TestSpell:
    def test_kreuz_laesst_die_kanonische_form_stehen(self):
        assert spell("A#m7", SHARP) == "A#m7"
        assert spell("F#", SHARP) == "F#"

    @pytest.mark.parametrize("kanonisch,erwartet", [
        ("A#", "Bb"), ("A#m7", "Bbm7"), ("C#", "Db"), ("D#maj7", "Ebmaj7"),
        ("F#m", "Gbm"), ("G#7", "Ab7"),
    ])
    def test_b_schreibweise(self, kanonisch, erwartet):
        assert spell(kanonisch, FLAT) == erwartet

    def test_akkorde_ohne_vorzeichen_bleiben(self):
        for name in ("C", "Am", "G7", "Fmaj7"):
            assert spell(name, FLAT) == name

    def test_nichtakkorde_gehen_unveraendert_durch(self):
        # "N" (kein Akkord), "-" (Stille), "?" (unsicher) duerfen nicht
        # versehentlich als Notennamen umgeschrieben werden.
        for name in ("N", "-", "?"):
            assert spell(name, FLAT) == name
            assert spell(name, SHARP) == name


class TestKey:
    def test_grundton_in_der_eigenen_schreibweise(self):
        # Dieselbe Tonklasse (10), zwei Tonarten: einmal Bb, einmal A#.
        assert Key(tonic=10, minor=False, confidence=0.9).label == "Bb major"
        assert Key(tonic=10, minor=True, confidence=0.9).label == "Bb minor"
        # In H-Dur (11) waere es ein Kreuz - der Grundton selbst hat keins.
        assert Key(tonic=6, minor=False, confidence=0.9).label == "F# major"

    def test_as_dict_liefert_den_grundton_kanonisch(self):
        # Der Browser schreibt selbst - er braucht die kanonische Form.
        payload = Key(tonic=10, minor=False, confidence=0.9).as_dict()
        assert payload == {"tonic": "A#", "minor": False,
                           "acc": FLAT, "label": "Bb major"}


class TestKeyEstimator:
    def test_schweigt_bis_genug_musik_da_war(self):
        # Lieber keine Tonart als eine geratene: eine falsche Tonart schriebe
        # die Akkorde falsch und wechselte die Schreibweise mitten im Stueck.
        estimator = KeyEstimator(hop_seconds=0.25)
        for _ in range(int((MIN_KEY_SECONDS - 1.0) / 0.25)):
            estimator.add(_chroma("C", "E", "G"))
        assert estimator.key is None

    def test_meldet_nach_genug_musik(self):
        estimator = _hoere(KADENZEN["C major"], sekunden=MIN_KEY_SECONDS + 1.0)
        assert estimator.key is not None
        assert estimator.heard_seconds >= MIN_KEY_SECONDS

    @pytest.mark.parametrize("erwartet", list(KADENZEN))
    def test_erkennt_die_tonart_der_kadenz(self, erwartet):
        assert _hoere(KADENZEN[erwartet]).key.label == erwartet

    @pytest.mark.parametrize("kadenz,erwartet", [
        ("F major", FLAT), ("D minor", FLAT),   # b-Tonarten
        ("D major", SHARP), ("A minor", SHARP),  # Kreuz-Tonarten
    ])
    def test_liefert_die_schreibweise(self, kadenz, erwartet):
        assert _hoere(KADENZEN[kadenz]).key.accidental == erwartet

    def test_f_dur_schreibt_die_zehnte_tonklasse_als_bb(self):
        # Der eigentliche Zweck des ganzen Moduls: in F-Dur heisst der Akkord
        # auf Tonklasse 10 "Bb", nicht "A#".
        key = _hoere(KADENZEN["F major"]).key
        assert spell("A#", key.accidental) == "Bb"

    def test_d_dur_laesst_das_kreuz_stehen(self):
        key = _hoere(KADENZEN["D major"]).key
        assert spell("F#", key.accidental) == "F#"

    def test_stille_zaehlt_nicht_als_musik(self):
        estimator = KeyEstimator(hop_seconds=0.25)
        for _ in range(200):
            estimator.add(np.zeros(12))
        assert estimator.heard_seconds == 0.0
        assert estimator.key is None

    def test_bleibt_bei_verwandter_tonart_stabil(self):
        # C-Dur und a-Moll teilen alle Toene; ohne Traegheit flackert die
        # Erkennung zwischen beiden - und mit ihr die Schreibweise.
        estimator = _hoere(KADENZEN["C major"], sekunden=60.0)
        stabil = estimator.key.label
        gemeldet = set()
        for i in range(200):
            estimator.add(_chroma(*KADENZEN["C major"][i // 8 % 4]))
            gemeldet.add(estimator.key.label)
        assert gemeldet == {stabil}

    def test_folgt_einer_modulation(self):
        # Das Histogramm verfaellt, damit ein Stueck die Tonart wechseln darf.
        estimator = _hoere(KADENZEN["C major"], sekunden=40.0)
        assert estimator.key.label == "C major"
        for i in range(int(90.0 / 0.25)):
            estimator.add(_chroma(*KADENZEN["D major"][i // 8 % 4]))
        assert estimator.key.label == "D major"


class TestEstimateKey:
    def test_offline_ohne_verfall(self):
        # Offline zaehlt die ganze Datei gleich - nicht nur ihr Ende.
        chromas = [_chroma(*akkord)
                   for akkord in KADENZEN["F major"] for _ in range(10)]
        assert estimate_key(chromas, hop_seconds=1.0).label == "F major"

    def test_zu_wenig_material_liefert_keine_tonart(self):
        assert estimate_key([_chroma("C", "E", "G")], hop_seconds=1.0) is None

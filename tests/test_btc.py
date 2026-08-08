"""Tests fuer den BTC-NumPy-Port und die BTC-fuehrende Zeitleisten-Logik.

Das Golden-Fixture (tests/data/btc_golden_window.npz) enthaelt 108 Log-CQT-
Frames aus sting_faith.wav samt der Label-Ausgabe des ORIGINAL-Torch-Modells
(gegengeprueft, bit-exakt). Weicht der Port nach einem Refactoring auch nur in
einem Frame ab, schlaegt der Test an - ganz ohne Torch im Test-Setup.
"""

from pathlib import Path

import numpy as np
import pytest

from jampilot import btc
from jampilot.cli import _merge_model_segments

FIXTURE = Path(__file__).parent / "data" / "btc_golden_window.npz"


class TestGoldenWindow:
    def test_port_reproduziert_torch_referenz_bitgenau(self):
        z = np.load(FIXTURE)
        labels = btc.BTCModel().predict(z["features"])
        abweichend = int((labels != z["labels"]).sum())
        assert abweichend == 0, f"{abweichend}/108 Frames weichen von Torch ab"

    def test_kurzes_fenster_wird_gepolstert(self):
        # Weniger als 108 Frames: predict muss auffuellen und wieder abschneiden.
        z = np.load(FIXTURE)
        labels = btc.BTCModel().predict(z["features"][:30])
        assert labels.shape == (30,)


class TestLabelNamen:
    def test_vokabular_vollstaendig_und_kanonisch(self):
        assert len(btc.LABEL_NAMES) == 170
        assert btc.LABEL_NAMES[169] == "N"
        assert btc.LABEL_NAMES[168] == "?"
        # Stichproben: Index = root*14 + quality (min=0, maj=1, ...)
        assert btc.LABEL_NAMES[0 * 14 + 1] == "C"
        assert btc.LABEL_NAMES[0 * 14 + 0] == "Cm"
        assert btc.LABEL_NAMES[3 * 14 + 9] == "D#7"
        assert btc.LABEL_NAMES[8 * 14 + 11] == "G#m7b5"

    def test_jede_qualitaet_hat_toene(self):
        for suffix in set(btc._QUALITY_SUFFIX.values()):
            assert suffix in btc.BTC_CHORD_TONES


class TestSegmente:
    def test_flacker_segment_faellt_an_den_vorgaenger(self):
        # 1-Frame-Blip (93ms) zwischen zwei stabilen Bloecken verschwindet.
        labels = np.array([1] * 20 + [15] * 1 + [1] * 20)
        segs = btc.segments_from_labels(labels)
        assert [name for _, name in segs] == ["C"]

    def test_erstes_kurzsegment_gehoert_zum_nachfolger(self):
        labels = np.array([15] * 1 + [1] * 30)
        segs = btc.segments_from_labels(labels)
        assert segs == [(0.0, "C")]

    def test_echte_wechsel_bleiben(self):
        labels = np.array([1] * 20 + [0] * 20)   # C -> Cm
        segs = btc.segments_from_labels(labels)
        assert [name for _, name in segs] == ["C", "Cm"]
        assert segs[1][0] == pytest.approx(20 * btc.BTC_FRAME_SECONDS)


class TestMergeModelSegments:
    def test_gehoertes_bleibt_unantastbar(self):
        timeline = [(0.0, "C"), (2.0, "G")]
        # Modell widerspricht dem bereits gehoerten G - das Etikett bleibt.
        _merge_model_segments(timeline, [(0.0, "C"), (2.0, "Am")],
                              audible_pos=3.0, horizon=8.0)
        assert timeline == [(0.0, "C"), (2.0, "G")]

    def test_unerhoertes_wird_neu_aufgebaut(self):
        timeline = [(0.0, "C"), (5.0, "G")]
        _merge_model_segments(timeline, [(0.0, "C"), (5.5, "Am"), (6.5, "F")],
                              audible_pos=3.0, horizon=8.0)
        assert timeline == [(0.0, "C"), (5.5, "Am"), (6.5, "F")]

    def test_einfrierzone_schuetzt_kurz_bevorstehendes(self):
        # Onset 4.0 liegt zwar in der Zukunft, aber naeher als BTC_FREEZE_AHEAD
        # an der JETZT-Linie (3.0): diesen Chip liest der Musiker gerade.
        timeline = [(0.0, "C"), (4.0, "G")]
        _merge_model_segments(timeline, [(0.0, "C"), (4.0, "Am")],
                              audible_pos=3.0, horizon=8.0)
        assert timeline == [(0.0, "C"), (4.0, "G")]

    def test_fensterrand_wartet(self):
        timeline = [(0.0, "C")]
        _merge_model_segments(timeline, [(0.0, "C"), (7.5, "G")],
                              audible_pos=3.0, horizon=7.0)
        assert timeline == [(0.0, "C")], "Segment hinter dem Horizont darf nicht rein"

    def test_anlauf_ohne_gehoertes(self):
        timeline = []
        _merge_model_segments(timeline, [(0.0, "-"), (0.5, "C")],
                              audible_pos=-2.0, horizon=1.5)
        assert timeline == [(0.0, "-"), (0.5, "C")]

    def test_hysterese_haelt_veroeffentlichte_grenze(self):
        # Das Frameraster wandert pro Hop: dieselbe Grenze kommt etwas
        # verschoben wieder. Die veroeffentlichte Position bleibt liegen.
        timeline = [(0.0, "C"), (5.0, "G")]
        _merge_model_segments(timeline, [(0.0, "C"), (5.3, "G")],
                              audible_pos=3.0, horizon=8.0)
        assert timeline == [(0.0, "C"), (5.0, "G")]

    def test_hysterese_schnappt_nicht_auf_andere_akkorde(self):
        timeline = [(0.0, "C"), (5.0, "G")]
        _merge_model_segments(timeline, [(0.0, "C"), (5.05, "Am")],
                              audible_pos=3.0, horizon=8.0)
        assert timeline == [(0.0, "C"), (5.05, "Am")]

    def test_debounce_haelt_geister_zurueck(self):
        # Eine Grenze, die weder veroeffentlicht ist noch im vorigen Lauf
        # vorkam, wartet einen Hop.
        timeline = [(0.0, "C")]
        _merge_model_segments(timeline, [(0.0, "C"), (5.0, "G")],
                              audible_pos=3.0, horizon=8.0,
                              previous=[(0.0, "C")])
        assert timeline == [(0.0, "C")]

    def test_debounce_laesst_bestaetigtes_durch(self):
        # Der vorige Lauf sah die Grenze schon (auch jenseits des Horizonts).
        timeline = [(0.0, "C")]
        _merge_model_segments(timeline, [(0.0, "C"), (5.0, "G")],
                              audible_pos=3.0, horizon=8.0,
                              previous=[(0.0, "C"), (5.1, "G")])
        assert timeline == [(0.0, "C"), (5.0, "G")]

    def test_entfernen_braucht_auch_zwei_laeufe(self):
        # Der neue Lauf laesst G weg, der vorige sah es noch: Der Chip bleibt
        # einen Hop stehen, statt wegzublinken.
        timeline = [(0.0, "C"), (5.0, "G")]
        _merge_model_segments(timeline, [(0.0, "C")],
                              audible_pos=3.0, horizon=8.0,
                              previous=[(0.0, "C"), (5.05, "G")])
        assert timeline == [(0.0, "C"), (5.0, "G")]

    def test_bestaetigtes_entfernen_raeumt_ab(self):
        # Zwei Laeufe nacheinander ohne G: jetzt darf der Chip verschwinden.
        timeline = [(0.0, "C"), (5.0, "G")]
        _merge_model_segments(timeline, [(0.0, "C")],
                              audible_pos=3.0, horizon=8.0,
                              previous=[(0.0, "C")])
        assert timeline == [(0.0, "C")]

    def test_revision_ersetzt_ohne_luecke(self):
        # Bestaetigte Umbenennung: der Platz wird ersetzt, nicht erst geleert.
        timeline = [(0.0, "C"), (5.0, "G")]
        _merge_model_segments(timeline, [(0.0, "C"), (5.0, "Am")],
                              audible_pos=3.0, horizon=8.0,
                              previous=[(0.0, "C"), (5.0, "Am")])
        assert timeline == [(0.0, "C"), (5.0, "Am")]


class TestRefineBoundary:
    def _zwei_akkorde(self, sr=22050, wechsel=3.0, dauer=6.0):
        # C-Dur -> F-Dur, additiv, mit deutlichem Anschlag am Wechsel.
        t = np.arange(int(dauer * sr)) / sr
        y = np.zeros(len(t), dtype=np.float32)
        for f in (261.6, 329.6, 392.0):                    # C E G
            y += (np.sin(2 * np.pi * f * t) * (t < wechsel)).astype(np.float32)
        for f in (349.2, 440.0, 523.3):                    # F A C
            y += (np.sin(2 * np.pi * f * t) * (t >= wechsel)).astype(np.float32)
        return 0.2 * y, sr

    def test_zieht_versetzte_grenze_auf_den_wechsel(self):
        y, sr = self._zwei_akkorde(wechsel=3.0)
        for falsch in (2.8, 3.2):
            fein = btc.refine_boundary(y, sr, falsch, "C", "F")
            assert abs(fein - 3.0) < 0.07, f"aus {falsch} wurde {fein}"

    def test_unbekannte_namen_bleiben_unveraendert(self):
        y, sr = self._zwei_akkorde()
        assert btc.refine_boundary(y, sr, 3.2, "-", "F") == 3.2
        assert btc.refine_boundary(y, sr, 3.2, "C", "?") == 3.2

    def test_randlage_bleibt_unveraendert(self):
        y, sr = self._zwei_akkorde()
        assert btc.refine_boundary(y, sr, 0.2, "C", "F") == 0.2

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
        timeline = [(0.0, "C"), (4.0, "G")]
        _merge_model_segments(timeline, [(0.0, "C"), (4.5, "Am"), (6.0, "F")],
                              audible_pos=3.0, horizon=8.0)
        assert timeline == [(0.0, "C"), (4.5, "Am"), (6.0, "F")]

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

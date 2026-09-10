"""Golden-Test fuer die Beat-This!-Referenz (tests/reference/beat_this_referenz.py).

Das Fixture (tests/data/beat_golden_window.npz) enthaelt ein 10-s-Fenster aus
tests/reference/eight_days_a_week.mp3 (30-40 s) samt Log-Mel-Spektrogramm,
Beat-/Downbeat-Logits (small0) und Peak-Picking-Ausgabe des ORIGINALS
(beat_this, Torch) - erzeugt und gegengeprueft in JamPilotML
(scripts/beat_golden_fixture.py). Weicht die NumPy-Vorverarbeitung, das
ONNX-Modell oder das Peak-Picking davon ab, schlaegt der Test an - ohne
Torch im Test-Setup. Der ONNX-Teil laeuft nur, wenn onnxruntime installiert
ist; alles andere braucht nur NumPy und librosa.
"""

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent / "reference"))
import beat_this_referenz as R  # noqa: E402

FIXTURE = Path(__file__).parent / "data" / "beat_golden_window.npz"
ONNX = Path(__file__).resolve().parents[1] / "jampilot" / "data" / \
    "beat_this_small0.onnx"


@pytest.fixture(scope="module")
def golden():
    return np.load(FIXTURE)


class TestVorverarbeitung:
    def test_log_mel_wie_torchaudio(self, golden):
        spect = R.log_mel(golden["samples"])
        assert spect.shape == golden["spect"].shape == (501, 128)
        assert np.abs(spect - golden["spect"]).max() < 1e-3

    def test_pad_und_strip_sind_invers(self, golden):
        s = golden["spect"]
        assert R.pad_chunk(s).shape == (513, 128)
        assert np.array_equal(R.strip_border(R.pad_chunk(s)), s)


class TestPeakPicking:
    def test_wie_original_postprocessor(self, golden):
        beats, downs = R.pick_peaks(golden["beat_logits"],
                                    golden["downbeat_logits"])
        assert np.allclose(beats, golden["beats"])
        assert np.allclose(downs, golden["downbeats"])
        assert len(beats) == 23 and len(downs) == 5

    def test_downbeats_sind_beats(self, golden):
        beats, downs = R.pick_peaks(golden["beat_logits"],
                                    golden["downbeat_logits"])
        assert set(downs) <= set(beats)

    def test_leer_ohne_peaks(self):
        b, d = R.pick_peaks(np.full(100, -5.0), np.full(100, -5.0))
        assert len(b) == 0 and len(d) == 0


class TestOnnx:
    @pytest.fixture(scope="class")
    def session(self):
        ort = pytest.importorskip("onnxruntime")
        assert ONNX.exists(), "jampilot/data/beat_this_small0.onnx fehlt"
        return ort.InferenceSession(str(ONNX),
                                    providers=["CPUExecutionProvider"])

    def test_modell_ist_das_des_fixtures(self, golden):
        assert hashlib.sha256(ONNX.read_bytes()).hexdigest() == \
            str(golden["onnx_sha256"])

    def test_logits_wie_torch(self, golden, session):
        chunk = R.pad_chunk(golden["spect"])[None]
        beat, down = session.run(None, {"spect": chunk})
        assert np.abs(R.strip_border(beat[0]) - golden["beat_logits"]).max() < 1e-3
        assert np.abs(R.strip_border(down[0]) - golden["downbeat_logits"]).max() < 1e-3

    def test_run_window_ende_zu_ende(self, golden, session):
        beats, downs = R.run_window(session, golden["samples"])
        assert np.allclose(beats, golden["beats"], atol=1e-6)
        assert np.allclose(downs, golden["downbeats"], atol=1e-6)

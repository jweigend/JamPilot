"""Beat und Takt (jampilot/beats.py).

Drei Schichten, drei Testklassen-Gruppen:

  1. Rund um das Modell - Golden-Test gegen das ORIGINAL (beat_this, Torch):
     tests/data/beat_golden_window.npz enthaelt ein 10-s-Fenster aus
     tests/reference/eight_days_a_week.mp3 (30-40 s) samt Log-Mel-Spektrogramm,
     Beat-/Downbeat-Logits (small0) und Peak-Picking-Ausgabe, erzeugt und
     gegengeprueft in JamPilotML (scripts/beat_golden_fixture.py). Weicht die
     NumPy-Vorverarbeitung, das ONNX-Modell oder das Peak-Picking davon ab,
     schlaegt der Test an - ohne Torch im Test-Setup. Der ONNX-Teil laeuft
     nur mit onnxruntime; alles andere braucht nur NumPy und librosa.
  2. Das Raster (BeatGrid): Commit-Zone, Mitteln, publish-once, Tempo-Gate,
     Takt-Phase mit Hysterese, Viertel-Snap.
  3. Der Thread (BeatTracker) mit einem Fake-Modell.
"""

import hashlib
import threading
import time
from pathlib import Path

import numpy as np
import pytest

from jampilot import beats as B

FIXTURE = Path(__file__).parent / "data" / "beat_golden_window.npz"


@pytest.fixture(scope="module")
def golden():
    return np.load(FIXTURE)


class TestVorverarbeitung:
    def test_log_mel_wie_torchaudio(self, golden):
        spect = B.log_mel(golden["samples"])
        assert spect.shape == golden["spect"].shape == (501, 128)
        assert np.abs(spect - golden["spect"]).max() < 1e-3

    def test_pad_und_strip_sind_invers(self, golden):
        s = golden["spect"]
        assert B.pad_chunk(s).shape == (513, 128)
        assert np.array_equal(B.strip_border(B.pad_chunk(s)), s)


class TestPeakPicking:
    def test_wie_original_postprocessor(self, golden):
        beats, downs = B.pick_peaks(golden["beat_logits"],
                                    golden["downbeat_logits"])
        assert np.allclose(beats, golden["beats"])
        assert np.allclose(downs, golden["downbeats"])
        assert len(beats) == 23 and len(downs) == 5

    def test_downbeats_sind_beats(self, golden):
        beats, downs = B.pick_peaks(golden["beat_logits"],
                                    golden["downbeat_logits"])
        assert set(downs) <= set(beats)

    def test_leer_ohne_peaks(self):
        b, d = B.pick_peaks(np.full(100, -5.0), np.full(100, -5.0))
        assert len(b) == 0 and len(d) == 0


class TestOnnx:
    @pytest.fixture(scope="class")
    def model(self):
        pytest.importorskip("onnxruntime")
        assert Path(B.MODEL_PATH).exists(), "jampilot/data/beat_this_small0.onnx fehlt"
        return B.BeatModel()

    def test_modell_ist_das_des_fixtures(self, golden):
        assert hashlib.sha256(Path(B.MODEL_PATH).read_bytes()).hexdigest() == \
            str(golden["onnx_sha256"])

    def test_logits_wie_torch(self, golden, model):
        chunk = B.pad_chunk(golden["spect"])[None]
        beat, down = model._session.run(None, {"spect": chunk})
        assert np.abs(B.strip_border(beat[0]) - golden["beat_logits"]).max() < 1e-3
        assert np.abs(B.strip_border(down[0]) - golden["downbeat_logits"]).max() < 1e-3

    def test_run_ende_zu_ende(self, golden, model):
        beats, downs = model.run(golden["samples"])
        assert np.allclose(beats, golden["beats"], atol=1e-6)
        assert np.allclose(downs, golden["downbeats"], atol=1e-6)

    def test_cpu_ist_immer_der_rueckfall(self):
        class Ort:
            @staticmethod
            def get_available_providers():
                return ["CUDAExecutionProvider", "CPUExecutionProvider",
                        "AzureExecutionProvider"]
        assert B._providers(Ort) == ["CUDAExecutionProvider", "CPUExecutionProvider"]


# ---------------------------------------------------------------------------
# 2. Das Raster


def fenster(grid, window_end, beats, downs=(), window_start=None):
    """Ein Modellfenster ins Raster: Beats in STREAM-Sekunden angeben."""
    start = window_end - B.BEAT_WINDOW if window_start is None else window_start
    grid.absorb(np.asarray(beats) - start, np.asarray(downs) - start,
                start, window_end)


def viertel(grid, bis, ab=0.0, periode=0.5, eins_alle=4, phase=0):
    """Ein Takt-Raster durch das Raster: Fenster im 1-s-Takt, Beats alle
    `periode` s, jede `eins_alle`-te Eins ab `phase`, committet bis `bis`."""
    alle = np.arange(ab, bis + B.BEAT_WINDOW, periode)
    downs = alle[(np.arange(len(alle)) - phase) % eins_alle == 0]
    for ende in np.arange(B.BEAT_WINDOW, bis + B.ZONE_BACK + 1.0, 1.0):
        fenster(grid, ende, alle, downs)
        grid.commit(ende - B.ZONE_BACK)


class TestCommitZone:
    def test_nur_die_zone_wird_uebernommen(self):
        g = B.BeatGrid()
        fenster(g, 20.0, [16.9, 17.0, 18.0, 18.99, 19.0, 19.5])
        g.commit(100.0)
        assert [e["at"] for e in g.events] == [17.0, 18.0, 18.99]

    def test_zwei_fenster_mitteln_denselben_beat(self):
        # Fenster im 1-s-Takt: die Zonen [17, 19) und [18, 20) ueberlappen
        # in [18, 19) - dort sieht jeder Beat zwei Fenster.
        g = B.BeatGrid()
        fenster(g, 20.0, [17.0, 18.02])
        fenster(g, 21.0, [18.06, 19.0])
        g.commit(100.0)
        assert [e["at"] for e in g.events] == [17.0, 18.04, 19.0]

    def test_weiter_auseinander_sind_zwei_beats(self):
        g = B.BeatGrid()
        fenster(g, 20.0, [18.0])
        fenster(g, 21.0, [18.2])
        g.commit(100.0)
        assert [e["at"] for e in g.events] == [18.0, 18.2]

    def test_die_eins_wird_gezaehlt(self):
        g = B.BeatGrid()
        fenster(g, 20.0, [18.0, 18.5], downs=[18.0])
        fenster(g, 21.0, [18.0, 18.5], downs=[18.5])   # uneins: 1 von 2
        g.commit(100.0)
        assert [e["n"] for e in g.events] == [1, 2]   # 0,5 zaehlt als Votum


class TestPublishOnce:
    def test_ein_beat_wird_genau_einmal_ausgeliefert(self):
        g = B.BeatGrid()
        fenster(g, 20.0, [17.0, 18.0, 18.9])
        assert [e["at"] for e in g.commit(18.5)] == [17.0, 18.0]
        assert g.commit(18.5) == []
        assert [e["at"] for e in g.commit(19.5)] == [18.9]
        assert [e["at"] for e in g.events] == [17.0, 18.0, 18.9]

    def test_spaete_fenster_werden_nachgeliefert(self):
        # Der Worker liefert ein Fenster erst, nachdem die Commit-Grenze
        # schon darueber hinweg ist: Die Beats hinter dem letzten committeten
        # kommen beim naechsten Commit nach, nicht in den Papierkorb.
        g = B.BeatGrid()
        fenster(g, 20.0, [17.0, 17.5])
        g.commit(19.5)                                   # Grenze schon bei 19,5
        fenster(g, 21.0, [18.0, 18.5, 19.0, 19.5])       # Zone [18, 20), spaet
        assert [e["at"] for e in g.commit(19.75)] == [18.0, 18.5, 19.0, 19.5]

    def test_ein_spaeteres_fenster_aendert_committetes_nicht(self):
        g = B.BeatGrid()
        fenster(g, 20.0, [17.0, 18.0])
        g.commit(18.5)
        fenster(g, 21.0, [17.05, 18.05, 19.0])         # sieht sie leicht anders
        g.commit(21.0)
        assert [e["at"] for e in g.events] == [17.0, 18.0, 19.0]

    def test_mindestabstand(self):
        g = B.BeatGrid()
        fenster(g, 20.0, [17.0, 17.1, 18.0])
        g.commit(100.0)
        assert [e["at"] for e in g.events] == [17.0, 18.0]

    def test_prune_haelt_den_rueckhalt(self):
        g = B.BeatGrid()
        fenster(g, 20.0, [17.0, 17.5, 18.0, 18.5])
        g.commit(100.0)
        g.prune(heard_pos=20.0)
        assert [e["at"] for e in g.events] == [18.5]
        g2 = B.BeatGrid()
        fenster(g2, 20.0, [17.0, 17.5, 18.0, 18.5])
        g2.commit(100.0)
        g2.prune(heard_pos=20.0, rueckhalt=60.0)
        assert len(g2.events) == 4

    def test_window_schneidet_wie_committed(self):
        g = B.BeatGrid()
        fenster(g, 20.0, [17.0, 17.5, 18.0, 18.5])
        g.commit(100.0)
        assert [e["at"] for e in g.window(17.4, 18.1)] == [17.5, 18.0]


class TestTempoGate:
    def test_gleichmaessiges_raster_geht_durch(self):
        g = B.BeatGrid()
        viertel(g, bis=30.0)
        abstaende = np.diff([e["at"] for e in g.events])
        assert len(g.events) >= 40 and np.allclose(abstaende, 0.5)
        assert g.tempo() == pytest.approx(120.0)

    def test_ausreisser_bekommt_keinen_strich(self):
        g = B.BeatGrid()
        raster = list(np.arange(0.0, 30.0, 0.5))
        raster.insert(raster.index(20.0), 19.8)         # ein Geisterbeat
        for ende in np.arange(10.0, 27.0, 1.0):
            fenster(g, ende, raster)
            g.commit(ende - B.ZONE_BACK)
        ats = [e["at"] for e in g.events]
        assert 19.8 not in ats and 19.5 in ats and 20.0 in ats

    def test_rubato_liefert_kaum_striche(self):
        g = B.BeatGrid()
        rng = np.random.default_rng(3)
        unruhig = np.cumsum(rng.uniform(0.3, 0.9, 60))   # +-50 % Streuung
        for ende in np.arange(10.0, 27.0, 1.0):
            fenster(g, ende, unruhig)
            g.commit(ende - B.ZONE_BACK)
        gesehen = [b for b in unruhig if 7.0 <= b <= 24.0]
        assert len(g.events) < 0.6 * len(gesehen)

    def test_nach_einer_pause_zaehlt_der_takt_neu(self):
        g = B.BeatGrid()
        vor = np.arange(0.0, 12.0, 0.5)
        nach = np.arange(16.0, 40.0, 0.5)
        alle = np.concatenate([vor, nach])
        downs = np.concatenate([vor[::4], nach[1::4]])   # andere Phase danach
        for ende in np.arange(10.0, 40.0, 1.0):
            fenster(g, ende, alle, downs)
            g.commit(ende - B.ZONE_BACK)
        n_nach = {e["at"]: e["n"] for e in g.events if e["at"] >= 16.0}
        assert n_nach[16.5] == 1 and n_nach[18.5] == 1


class TestTaktPhase:
    def test_vierviertel_zaehlt_eins_bis_vier(self):
        g = B.BeatGrid()
        viertel(g, bis=30.0)
        ns = [e["n"] for e in g.events]
        # Nach dem Anlauf (erste Eins) zaehlt es 1 2 3 4 durch.
        erste = ns.index(1)
        assert ns[erste:erste + 12] == [1, 2, 3, 4] * 3
        assert g._meter == 4

    def test_dreiviertel_wird_erkannt(self):
        g = B.BeatGrid()
        viertel(g, bis=30.0, eins_alle=3)
        ns = [e["n"] for e in g.events]
        erste = ns.index(1)
        assert ns[erste:erste + 9] == [1, 2, 3] * 3
        assert g._meter == 3

    def test_ohne_eins_votum_wird_fortgeschrieben_dann_verloren(self):
        g = B.BeatGrid()
        alle = np.arange(0.0, 40.0, 0.5)
        downs = alle[::4][:8]                            # Voten nur bis 14 s
        for ende in np.arange(10.0, 40.0, 1.0):
            fenster(g, ende, alle, downs)
            g.commit(ende - B.ZONE_BACK)
        n = {e["at"]: e["n"] for e in g.events}
        assert n[14.0] == 1                              # letzte gevotete Eins
        assert n[16.0] == 1 and n[18.0] == 1             # zwei Takte fortgeschrieben
        assert n[20.0] == 0 and n[24.0] == 0             # dann ehrlich: unbekannt
        assert all(n[t] == 0 for t in np.arange(20.0, 30.0, 0.5))

    def test_ein_einzelnes_halbtakt_votum_kippt_die_phase_nicht(self):
        g = B.BeatGrid()
        alle = np.arange(0.0, 40.0, 0.5)
        downs = np.append(alle[::4], 21.0)               # eine falsche "Eins" auf der 3
        for ende in np.arange(10.0, 40.0, 1.0):
            fenster(g, ende, alle, np.sort(downs))
            g.commit(ende - B.ZONE_BACK)
        n = {e["at"]: e["n"] for e in g.events}
        assert n[21.0] == 3 and n[22.0] == 1 and n[24.0] == 1

    def test_zwei_voten_in_folge_kippen_die_phase(self):
        g = B.BeatGrid()
        alle = np.arange(0.0, 40.0, 0.5)
        # Bis 20 s die Eins auf 0, 2, 4 ...; danach konsequent auf 21, 23, 25 ...
        downs = np.concatenate([np.arange(0.0, 20.0, 2.0), np.arange(21.0, 40.0, 2.0)])
        for ende in np.arange(10.0, 40.0, 1.0):
            fenster(g, ende, alle, downs)
            g.commit(ende - B.ZONE_BACK)
        n = {e["at"]: e["n"] for e in g.events}
        assert n[20.0] == 1                              # fortgeschrieben
        assert n[21.0] == 3                              # erstes Votum: verworfen
        assert n[23.0] == 1 and n[25.0] == 1             # zweites: uebernommen
        assert n[23.5] == 2 and n[24.0] == 3 and n[24.5] == 4

    def test_ein_verpasster_beat_verschiebt_die_eins_nicht_dauerhaft(self):
        g = B.BeatGrid()
        alle = list(np.arange(0.0, 40.0, 0.5))
        alle.remove(19.5)                                # das Modell verpasst einen
        alle = np.asarray(alle)
        downs = np.arange(0.0, 40.0, 2.0)
        for ende in np.arange(10.0, 40.0, 1.0):
            fenster(g, ende, alle, downs)
            g.commit(ende - B.ZONE_BACK)
        n = {e["at"]: e["n"] for e in g.events}
        assert 19.5 not in n and n[19.0] == 3
        assert n[20.0] == 1 and n[22.0] == 1 and n[24.0] == 1

    def test_ein_geisterbeat_reisst_den_naechsten_nicht_mit(self):
        g = B.BeatGrid()
        alle = sorted(list(np.arange(0.0, 40.0, 0.5)) + [19.8])
        downs = np.arange(0.0, 40.0, 2.0)
        for ende in np.arange(10.0, 40.0, 1.0):
            fenster(g, ende, alle, downs)
            g.commit(ende - B.ZONE_BACK)
        n = {e["at"]: e["n"] for e in g.events}
        assert 19.8 not in n
        assert n[19.5] == 4 and n[20.0] == 1 and n[20.5] == 2 and n[22.0] == 1


class TestSnap:
    def test_naechster_beat(self):
        g = B.BeatGrid()
        viertel(g, bis=20.0)
        assert g.snap(17.2) == 17.0
        assert g.snap(17.3) == 17.5

    def test_auch_offene_beats_zaehlen(self):
        g = B.BeatGrid()
        fenster(g, 20.0, [17.0, 17.5, 18.0, 18.5])       # nichts committet
        assert g.snap(18.4) == 18.5

    def test_ohne_raster_kein_snap(self):
        assert B.BeatGrid().snap(5.0) is None

    def test_nicht_ueber_loecher_hinweg(self):
        g = B.BeatGrid()
        viertel(g, bis=20.0)
        assert g.snap(30.0) is None                      # weit hinter dem Raster
        assert g.snap(17.0 + 0.29) == 17.5               # 0,6 Schlag Reichweite
        g2 = B.BeatGrid()
        fenster(g2, 20.0, [17.0])                        # ein einzelner Beat
        assert g2.snap(17.4) == 17.0 and g2.snap(17.6) is None


# ---------------------------------------------------------------------------
# 3. Der Thread


class FakeModel:
    """Findet den Puls per Konstruktion: Beats alle 0,5 s ab Fensteranfang."""
    provider = "FakeExecutionProvider"

    def run(self, samples):
        n = len(samples) / B.SR
        beats = np.arange(0.0, n, 0.5)
        return beats, beats[::4]


def warte_bis(bedingung, sekunden=5.0):
    ende = time.monotonic() + sekunden
    while not bedingung():
        assert time.monotonic() < ende, "Timeout"
        time.sleep(0.01)


class TestTracker:
    def test_fenster_landen_im_raster_in_stream_sekunden(self):
        t = B.BeatTracker(model_factory=FakeModel)
        try:
            warte_bis(lambda: t.ready)
            assert t.provider == "FakeExecutionProvider"
            audio = np.zeros(int(10 * 48000), dtype=np.float32)
            assert t.submit(audio, 48000, window_start=10.0, window_end=20.0)
            warte_bis(lambda: t.runs == 1)
            warte_bis(lambda: t.poll() > 0)
            t.grid.commit(100.0)
            ats = [e["at"] for e in t.grid.events]
            assert ats[0] == 17.0 and ats[-1] == 18.5     # Commit-Zone [17, 19)
        finally:
            t.stop()

    def test_beschaeftigter_worker_laesst_ein_fenster_aus(self):
        block = threading.Event()

        class Langsam(FakeModel):
            def run(self, samples):
                block.wait()
                return super().run(samples)

        t = B.BeatTracker(model_factory=Langsam)
        try:
            warte_bis(lambda: t.ready)
            audio = np.zeros(int(10 * B.SR), dtype=np.float32)
            assert t.submit(audio, B.SR, 0.0, 10.0)
            warte_bis(lambda: not t.busy())          # der Worker hat es geholt
            assert t.submit(audio, B.SR, 1.0, 11.0)  # ein Platz ist frei
            assert not t.submit(audio, B.SR, 2.0, 12.0)   # der zweite faellt aus
            block.set()
            warte_bis(lambda: t.runs == 2)
        finally:
            block.set()
            t.stop()

    def test_kaputtes_modell_meldet_sich_statt_zu_haengen(self):
        def kaputt():
            raise RuntimeError("no such file")
        t = B.BeatTracker(model_factory=kaputt)
        warte_bis(lambda: t.error is not None)
        assert "no such file" in t.error and not t.ready
        assert not t.submit(np.zeros(10), B.SR, 0.0, 10.0)

    def test_ohne_onnxruntime_gibt_es_keinen_tracker(self, monkeypatch):
        monkeypatch.setattr(B, "onnxruntime_available", lambda: False)
        assert B.BeatTracker.create() is None


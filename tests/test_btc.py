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


def _akkord_strom(sr: int, seconds: float = 24.0) -> np.ndarray:
    """C - F - G - Am im 3-s-Takt, Obertongemisch plus etwas Rauschen."""
    rng = np.random.default_rng(7)
    t = np.arange(int(seconds * sr)) / sr
    chords = [(48, 52, 55), (53, 57, 60), (55, 59, 62), (57, 60, 64)]
    y = np.zeros_like(t)
    for seg in range(int(seconds // 3) + 1):
        m = (t >= seg * 3.0) & (t < (seg + 1) * 3.0)
        for midi in chords[seg % 4]:
            f = 440.0 * 2 ** ((midi - 69) / 12)
            for k, amp in ((1, 1.0), (2, 0.5), (3, 0.3), (4, 0.15)):
                y[m] += amp * np.sin(2 * np.pi * f * k * t[m] + seg + k)
    y += 0.02 * rng.standard_normal(len(t))
    return (0.15 * y).astype(np.float32)


class TestIncrementalCQT:
    """Der inkrementelle Live-Pfad muss der Vollrechnung entsprechen.

    Referenz ist die CQT ueber den GANZEN Stream auf demselben Absolutraster -
    der Idealfall ohne jede Fenster- oder Chunkgrenze. Kleine Abweichungen
    sind Resampler-/Randeffekte der Slices; entscheidend ist, dass das Modell
    dieselben Labels liefert (gemessen: 0 Abweichungen ueber 22/44.1/48 kHz).
    """

    SR = 48000     # schlechtester Fall: echtes Resampling mit krummem Faktor

    @staticmethod
    def _referenz(stream: np.ndarray, sr: int, end: int, w0: int, n: int) -> np.ndarray:
        import librosa

        y = stream[:end].astype(np.float32)
        if sr != btc.BTC_SR:
            y = librosa.resample(y, orig_sr=sr, target_sr=btc.BTC_SR)
        c = librosa.cqt(y, sr=btc.BTC_SR, n_bins=btc.BTC_N_BINS,
                        bins_per_octave=btc.BTC_BINS_PER_OCTAVE,
                        hop_length=btc.BTC_HOP)
        return np.log(np.abs(c) + 1e-6).T.astype(np.float32)[w0 : w0 + n]

    @staticmethod
    def _hops(inc, stream, sr, bis, von=2.0, jeder=1):
        hop, window = int(0.25 * sr), int(10 * sr)
        out = None
        for i, end in enumerate(range(int(von * sr), int(bis * sr) + 1, hop)):
            if i % jeder == 0:
                out = inc.features(stream[max(0, end - window):end], sr, end)
        return out

    def test_stabile_frames_und_labels_wie_vollrechnung(self):
        stream = _akkord_strom(self.SR)
        feats, start = self._hops(btc.IncrementalCQT(), stream, self.SR, 24.0)
        w0 = int(round(start / btc.BTC_FRAME_SECONDS))
        ref = self._referenz(stream, self.SR, len(stream), w0, len(feats))
        schwanz = int(btc._STABLE_SECONDS / btc.BTC_FRAME_SECONDS) + 1
        d = np.abs(feats - ref)
        assert d[:-schwanz].max() < 0.35     # gemessen: 0.22
        assert d[:-schwanz].mean() < 0.005   # gemessen: 0.001
        assert d[-schwanz:].max() < 0.5      # Schwanz ist noch instabil
        model = btc.BTCModel()
        abweichend = int((model.predict(feats) != model.predict(ref)).sum())
        assert abweichend <= 2, f"{abweichend}/108 Labels weichen ab"

    def test_hop_pfad_unabhaengig(self):
        # Eingefrorene Frames duerfen nicht davon abhaengen, in welchem
        # Rhythmus die Analyse vorbeikam (z.B. nach einem langsamen Hop).
        stream = _akkord_strom(self.SR)
        dicht, duenn = btc.IncrementalCQT(), btc.IncrementalCQT()
        self._hops(dicht, stream, self.SR, 24.0)
        self._hops(duenn, stream, self.SR, 24.0, jeder=4)
        lo = max(dicht._f0, duenn._f0)
        hi = min(dicht._f0 + len(dicht._cache), duenn._f0 + len(duenn._cache))
        assert hi - lo > 50
        d = np.abs(dicht._cache[lo - dicht._f0 : hi - dicht._f0]
                   - duenn._cache[lo - duenn._f0 : hi - duenn._f0])
        assert d.max() < 0.35                # gemessen: 0.18

    def test_startzeit_liegt_auf_absolutem_raster(self):
        stream = _akkord_strom(self.SR, seconds=13.0)
        inc = btc.IncrementalCQT()
        hop, window = int(0.25 * self.SR), int(10 * self.SR)
        starts = []
        for end in range(2 * self.SR, len(stream) + 1, hop):
            feats, start = inc.features(stream[max(0, end - window):end],
                                        self.SR, end)
            assert len(feats) <= btc.BTC_TIMESTEP
            raster = start / btc.BTC_FRAME_SECONDS
            assert abs(raster - round(raster)) < 1e-6
            starts.append(start)
        assert starts == sorted(starts)      # Fenster wandert nur vorwaerts

    def test_reset_nach_stillstand(self):
        # 15 s Analyse-Luecke: Cache passt nicht mehr ans Fenster, Neuaufbau.
        # Nur die ersten ~_PAD_FRAMES Frames verlieren ihren Links-Kontext
        # (das Audio davor ist weg - dem alten Voll-Fenster-Pfad ging es an
        # seinem Fensteranfang genauso); der Rest sitzt wieder exakt.
        stream = _akkord_strom(self.SR, seconds=26.0)
        inc = btc.IncrementalCQT()
        self._hops(inc, stream, self.SR, 8.0)
        end = 26 * self.SR
        feats, start = inc.features(stream[end - 10 * self.SR : end], self.SR, end)
        w0 = int(round(start / btc.BTC_FRAME_SECONDS))
        ref = self._referenz(stream, self.SR, end, w0, len(feats))
        d = np.abs(feats - ref)
        assert d[btc._PAD_FRAMES + 2 :].max() < 0.05   # gemessen: 0.004

    def test_kurzer_anlauf(self):
        # Erster Aufruf mit nur 2 s Audio ab Streamanfang.
        stream = _akkord_strom(self.SR, seconds=2.0)
        feats, start = btc.IncrementalCQT().features(stream, self.SR, len(stream))
        assert start == 0.0
        assert 18 <= len(feats) <= 22        # ~21 Frames in 2 s

    def test_gecachte_filterbank_bleibt_unverfaelscht(self):
        # vqt skaliert die Filterbasis in place; gaebe der Cache das Original
        # statt einer Kopie heraus, waere der zweite Aufruf verfaelscht.
        import librosa

        btc._speed_up_librosa_cqt()
        y = _akkord_strom(btc.BTC_SR, seconds=3.0)
        args = dict(sr=btc.BTC_SR, n_bins=btc.BTC_N_BINS,
                    bins_per_octave=btc.BTC_BINS_PER_OCTAVE,
                    hop_length=btc.BTC_HOP)
        a = librosa.cqt(y, **args)
        b = librosa.cqt(y, **args)           # Basis kommt jetzt aus dem Cache
        assert np.array_equal(a, b)


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

    def test_hysterese_erkennt_verfeinerte_fruehere_grenze(self):
        # Eine verfeinerte Grenze liegt bis REFINE_BACK VOR der rohen
        # Modellgrenze - sie muss trotzdem als dieselbe erkannt werden.
        timeline = [(0.0, "C"), (5.0, "G")]        # 5.0 = verfeinert
        _merge_model_segments(timeline, [(0.0, "C"), (5.38, "G")],
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

    def test_zieht_spaete_grenze_zurueck_auf_den_wechsel(self):
        # Der Normalfall: Die Modellgrenze laeuft nach, die Suche zieht zurueck.
        y, sr = self._zwei_akkorde(wechsel=3.0)
        for falsch in (3.15, 3.3):
            fein = btc.refine_boundary(y, sr, falsch, "C", "F")
            assert abs(fein - 3.0) < 0.07, f"aus {falsch} wurde {fein}"

    def test_nach_hinten_ist_gedeckelt(self):
        # Bewusst asymmetrisch: auf einer chaotischen Eins darf die Suche die
        # Grenze nicht Richtung Zwei schieben (max REFINE_FORWARD nach hinten).
        y, sr = self._zwei_akkorde(wechsel=3.0)
        fein = btc.refine_boundary(y, sr, 2.8, "C", "F")
        assert fein <= 2.8 + btc.REFINE_FORWARD + 0.001

    def test_unbekannte_namen_bleiben_unveraendert(self):
        y, sr = self._zwei_akkorde()
        assert btc.refine_boundary(y, sr, 3.2, "-", "F") == 3.2
        assert btc.refine_boundary(y, sr, 3.2, "C", "?") == 3.2

    def test_randlage_bleibt_unveraendert(self):
        y, sr = self._zwei_akkorde()
        assert btc.refine_boundary(y, sr, 0.2, "C", "F") == 0.2

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
from jampilot import cli
from jampilot.cli import _merge_model_segments

FIXTURE = Path(__file__).parent / "data" / "btc_golden_window.npz"

# Die Referenz-Labels im Golden-Fixture gelten fuer GENAU diese Gewichte. Mit
# experimentellen Gewichten (MERT-Pseudo-Labeling) waere ein Fehlschlag keine
# Aussage ueber den Port - dann wartet der Test, statt rot zu sein. Bleibt ein
# neues Modell, wird das Fixture neu erzeugt und der Hash hier nachgezogen.
_GOLDEN_WEIGHTS_SHA256 = \
    "e839c4e215ab222c942c224cb608eb7c7f54af9f9900f46b871a1bc5d697b862"


def _original_weights():
    import hashlib
    return hashlib.sha256(
        btc._WEIGHTS_PATH.read_bytes()).hexdigest() == _GOLDEN_WEIGHTS_SHA256


class TestGoldenWindow:
    @pytest.mark.skipif(not _original_weights(),
                        reason="experimentelle Gewichte - Golden-Fixture passt "
                               "nur zu den Original-BTC-Gewichten")
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

    def test_live_nichtstilles_n_leert_die_anzeige_nicht(self):
        frames, sr = 26, 1000
        audio = np.full(int(round(frames * btc.BTC_FRAME_SECONDS * sr)),
                        1e-2, dtype=np.float32)
        labels = np.array([1] * 10 + [169] * 6 + [1] * 10)   # C - N - C
        segs = btc.live_segments_from_labels(labels, audio, sr)
        assert segs == [(0.0, "C")]

    def test_live_stille_bleibt_trotz_modell_chord_stille(self):
        frames, sr = 6, 1000
        audio = np.full(int(round(frames * btc.BTC_FRAME_SECONDS * sr)),
                        1e-2, dtype=np.float32)
        grenze = int(round(3 * btc.BTC_FRAME_SECONDS * sr))
        audio[:grenze] = 0.0
        labels = np.array([1] * frames)          # Modell halluziniert C durchgehend
        segs = btc.live_segments_from_labels(labels, audio, sr)
        assert len(segs) == 2
        assert segs[0] == (0.0, "-")
        assert segs[1][0] == pytest.approx(3 * btc.BTC_FRAME_SECONDS)
        assert segs[1][1] == "C"


class TestFilterbankMemo:
    """Die memoisierte librosa-Filterbank veraendert kein Ergebnis."""

    def _signal(self, seconds, freqs):
        sr = btc.BTC_SR
        t = np.arange(int(seconds * sr)) / sr
        return sum(np.sin(2 * np.pi * f * t) for f in freqs).astype(np.float32)

    def test_gecachte_filterbank_bleibt_unverfaelscht(self):
        # vqt skaliert die Filterbasis in place; gaebe der Cache das Original
        # statt einer Kopie heraus, waere der zweite Aufruf verfaelscht.
        import librosa

        btc._speed_up_librosa_cqt()
        y = self._signal(3.0, (130.8, 164.8, 196.0))
        args = dict(sr=btc.BTC_SR, n_bins=btc.BTC_N_BINS,
                    bins_per_octave=btc.BTC_BINS_PER_OCTAVE, hop_length=btc.BTC_HOP)
        a = librosa.cqt(y, **args)
        b = librosa.cqt(y, **args)           # Basis kommt jetzt aus dem Cache
        assert np.array_equal(a, b)

    def test_features_mit_und_ohne_memo_bitgleich(self):
        import librosa.core.constantq as constantq

        y = self._signal(4.0, (110.0, 277.2))
        with_memo = btc.features_from_audio(y, btc.BTC_SR)
        # getattr/setattr: in einer Klasse wuerde `constantq.__vqt...`
        # namensverstuemmelt.
        cached = getattr(constantq, "__vqt_filter_fft")
        original = getattr(cached, "_jampilot_original", None)
        if original is None:
            pytest.skip("librosa ohne private Filterbank-API: kein Memo aktiv")
        setattr(constantq, "__vqt_filter_fft", original)
        try:
            without = btc.features_from_audio(y, btc.BTC_SR)
        finally:
            setattr(constantq, "__vqt_filter_fft", cached)
        assert np.array_equal(with_memo, without)


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
                              audible_pos=2.5, horizon=8.0)
        assert timeline == [(0.0, "C"), (5.5, "Am"), (6.5, "F")]

    def test_commit_grenze_schuetzt_kurz_bevorstehendes(self):
        # Onset 4.0 liegt zwar in der Zukunft, aber naeher als BTC_COMMIT_AHEAD
        # an der JETZT-Linie (3.0): dieser Eintrag ist bereits als Event
        # ausgeliefert und darf sich nicht mehr aendern.
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
                              audible_pos=2.5, horizon=8.0)
        assert timeline == [(0.0, "C"), (5.0, "G")]

    def test_hysterese_erkennt_verfeinerte_fruehere_grenze(self):
        # Eine verfeinerte Grenze liegt bis REFINE_BACK VOR der rohen
        # Modellgrenze - sie muss trotzdem als dieselbe erkannt werden.
        timeline = [(0.0, "C"), (5.0, "G")]        # 5.0 = verfeinert
        _merge_model_segments(timeline, [(0.0, "C"), (5.38, "G")],
                              audible_pos=2.5, horizon=8.0)
        assert timeline == [(0.0, "C"), (5.0, "G")]

    def test_hysterese_schnappt_nicht_auf_andere_akkorde(self):
        timeline = [(0.0, "C"), (5.0, "G")]
        _merge_model_segments(timeline, [(0.0, "C"), (5.05, "Am")],
                              audible_pos=2.5, horizon=8.0)
        assert timeline == [(0.0, "C"), (5.05, "Am")]

    def test_debounce_haelt_geister_zurueck(self):
        # Eine Grenze, die weder veroeffentlicht ist noch im vorigen Lauf
        # vorkam, wartet einen Hop.
        timeline = [(0.0, "C")]
        _merge_model_segments(timeline, [(0.0, "C"), (5.0, "G")],
                              audible_pos=2.5, horizon=8.0,
                              previous=[(0.0, "C")])
        assert timeline == [(0.0, "C")]

    def test_debounce_laesst_bestaetigtes_durch(self):
        # Der vorige Lauf sah die Grenze schon (auch jenseits des Horizonts).
        timeline = [(0.0, "C")]
        _merge_model_segments(timeline, [(0.0, "C"), (5.0, "G")],
                              audible_pos=2.5, horizon=8.0,
                              previous=[(0.0, "C"), (5.1, "G")])
        assert timeline == [(0.0, "C"), (5.0, "G")]

    def test_entfernen_braucht_auch_zwei_laeufe(self):
        # Der neue Lauf laesst G weg, der vorige sah es noch: Der Chip bleibt
        # einen Hop stehen, statt wegzublinken.
        timeline = [(0.0, "C"), (5.0, "G")]
        _merge_model_segments(timeline, [(0.0, "C")],
                              audible_pos=2.5, horizon=8.0,
                              previous=[(0.0, "C"), (5.05, "G")])
        assert timeline == [(0.0, "C"), (5.0, "G")]

    def test_bestaetigtes_entfernen_raeumt_ab(self):
        # Zwei Laeufe nacheinander ohne G: jetzt darf der Chip verschwinden.
        timeline = [(0.0, "C"), (5.0, "G")]
        _merge_model_segments(timeline, [(0.0, "C")],
                              audible_pos=2.5, horizon=8.0,
                              previous=[(0.0, "C")])
        assert timeline == [(0.0, "C")]

    def test_uebermaltes_kurzsegment_verschluckt_die_rueckkehr_nicht(self):
        # D - A - D, und das Modell uebermalt das gehoerte A rueckwirkend mit
        # durchgehendem D: Es gibt nie wieder eine neue Grenze. Ohne Korrektur
        # zeigte die Anzeige A, bis das Stueck real wechselt (JJ-Cale-Bug).
        timeline = [(0.0, "D"), (2.0, "A")]
        _merge_model_segments(timeline, [(0.0, "D")],
                              audible_pos=5.0, horizon=10.0,
                              previous=[(0.0, "D")])
        # base = 5.0 + BTC_COMMIT_AHEAD: ab dort gilt wieder D.
        assert timeline == [(0.0, "D"), (2.0, "A"), (7.0, "D")]

    def test_spaete_grenze_unter_dem_commit_schreibt_ab_der_grenze(self):
        # Die Rueckkehr zu D wird erst erkannt, als ihre Grenze (6.0) schon
        # unter der Commit-Grenze liegt - sie darf nicht verlorengehen.
        timeline = [(0.0, "D"), (2.0, "A")]
        segs = [(0.0, "D"), (2.0, "A"), (6.0, "D")]
        _merge_model_segments(timeline, segs,
                              audible_pos=5.0, horizon=10.0, previous=segs)
        assert timeline == [(0.0, "D"), (2.0, "A"), (7.0, "D")]

    def test_grenze_die_knapp_unter_den_commit_rutscht_bleibt_nicht_haengen(self):
        # Der vorige Lauf sah G noch knapp NACH der Commit-Grenze, der neue
        # knapp DAVOR. Das ist dieselbe bestaetigte Grenze; ihr Anfang darf
        # nicht verschluckt werden, sonst bliebe C einen Hop zu lang stehen.
        timeline = [(0.0, "C"), (7.2, "G")]
        _merge_model_segments(timeline, [(0.0, "C"), (6.95, "G")],
                              audible_pos=5.0, horizon=10.0,
                              previous=[(0.0, "C"), (7.2, "G")])
        assert timeline == [(0.0, "C"), (7.0, "G")]

    def test_bestaetigte_grenze_aus_dem_vorigen_lauf_schreibt_ab_commit(self):
        # Dieselbe Kante kann im vorigen Lauf noch jenseits des Horizonts
        # gelegen haben und deshalb noch gar nicht in `timeline` stehen.
        # Rueckt sie im naechsten Lauf knapp unter den Commit, muss sie ab der
        # Commit-Grenze gelten - auch ohne vorher veroeffentlichten Chip.
        timeline = [(0.0, "C")]
        _merge_model_segments(timeline, [(0.0, "C"), (6.95, "G")],
                              audible_pos=5.0, horizon=10.0,
                              previous=[(0.0, "C"), (7.15, "G")])
        assert timeline == [(0.0, "C"), (7.0, "G")]

    def test_revision_unter_den_commit_braucht_zwei_laeufe(self):
        # Der vorige Lauf sah an der Hoergrenze noch A: Ein-Hop-Launen des
        # Modells duerfen das laufende Etikett nicht umschreiben.
        timeline = [(0.0, "D"), (2.0, "A")]
        _merge_model_segments(timeline, [(0.0, "D")],
                              audible_pos=5.0, horizon=10.0,
                              previous=[(0.0, "D"), (2.0, "A")])
        assert timeline == [(0.0, "D"), (2.0, "A")]

    def test_korrigiertes_etikett_bleibt_im_folgelauf_stabil(self):
        # Nach der Korrektur ist (7.0, D) committet; der naechste Lauf mit
        # demselben Modellbild darf keine weitere Grenze anhaengen.
        timeline = [(0.0, "D"), (2.0, "A"), (7.0, "D")]
        _merge_model_segments(timeline, [(0.0, "D")],
                              audible_pos=5.25, horizon=10.25,
                              previous=[(0.0, "D")])
        assert timeline == [(0.0, "D"), (2.0, "A"), (7.0, "D")]

    def test_korrektur_haelt_abstand_zum_eben_committeten(self):
        # Das Modell flackert genau an einer Grenze: F bei 6.98 ist eben
        # committet, jetzt sagt es dort (zweimal in Folge) G. Die Korrektur
        # darf nicht 0.02 s hinter das F fallen - sie rueckt auf
        # MIN_EVENT_GAP nach und wird einen Hop spaeter committet.
        timeline = [(0.0, "C"), (6.98, "F")]
        segs = [(0.0, "C"), (6.98, "G")]
        _merge_model_segments(timeline, segs,
                              audible_pos=5.0, horizon=10.0, previous=segs)
        assert timeline == [(0.0, "C"), (6.98, "F"),
                            (pytest.approx(6.98 + cli.MIN_EVENT_GAP), "G")]

    def test_revision_ersetzt_ohne_luecke(self):
        # Bestaetigte Umbenennung: der Platz wird ersetzt, nicht erst geleert.
        timeline = [(0.0, "C"), (5.0, "G")]
        _merge_model_segments(timeline, [(0.0, "C"), (5.0, "Am")],
                              audible_pos=2.5, horizon=8.0,
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


class TestModeVotes:
    def test_eindeutige_qualitaeten_stimmen_der_rest_enthaelt_sich(self):
        idx = {name: i for i, name in enumerate(btc.LABEL_NAMES)}
        labels = np.array([idx["Gm"], idx["Gm7"], idx["G"], idx["Gsus4"],
                           idx["Gdim"], idx["N"]])
        votes = btc.label_mode_votes(labels)
        g = 7
        assert votes[g][1] == 2.0     # Moll: Gm, Gm7
        assert votes[g][0] == 1.0     # Dur: G
        assert votes.sum() == 3.0     # sus/dim/N enthalten sich

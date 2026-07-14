"""Bassnote messen: Tonklasse aus dem Tiefband-Chroma, Zuordnung zur Zeitleiste.

Gemessen wird im Tiefband-Chroma, das `analyze_window` ohnehin berechnet. Ein
erster Versuch mit YIN (wie es die Bass-Transkriptionsliteratur empfiehlt) ist
an dichten Voicings gescheitert - `test_dichtes_voicing_der_fall_der_yin_zerlegt_hat`
haelt genau den Fall fest. Die Begruendung steht in bass.py.
"""

import numpy as np
import pytest

from jampilot.bass import BassTrack, chord_root, dominant, name, slash
from jampilot.chroma import FRAME_SECONDS, HAVE_LIBROSA, NOTE_NAMES, analyze_window
from jampilot.selftest import SAMPLERATE, _chord, _drums

pytestmark = pytest.mark.skipif(not HAVE_LIBROSA, reason="librosa fehlt")

E1 = 28   # tiefste Saite eines Basses


def _messe(midi_noten) -> int | None:
    """Bassnote so messen, wie die Pipeline es tut: aus den Tiefband-Frames.

    Mit Schlagzeug - die Bassdrum ist der einzige ernsthafte Mitbewohner im
    Tiefband.
    """
    audio = _chord(midi_noten, 1.5)
    rng = np.random.default_rng(5)
    audio = (audio + 0.8 * _drums(1.5, rng)[: len(audio)]).astype(np.float32)
    audio = (audio / np.abs(audio).max()).astype(np.float32)
    return dominant(analyze_window(audio, SAMPLERATE).bass_frames)


class TestBassnote:
    """Der Bass ist der TIEFSTE Ton - egal, welcher Akkord darueber steht."""

    @pytest.mark.parametrize("halbton", range(12))
    def test_akkord_zwei_oktaven_darueber(self, halbton):
        bass = E1 + halbton
        assert _messe([bass, bass + 24, bass + 28, bass + 31]) == bass % 12

    @pytest.mark.parametrize("halbton", range(12))
    def test_enge_lage_direkt_darueber(self, halbton):
        bass = E1 + halbton
        assert _messe([bass, bass + 12, bass + 15, bass + 19]) == bass % 12

    @pytest.mark.parametrize("halbton", range(12))
    def test_dichtes_voicing_der_fall_der_yin_zerlegt_hat(self, halbton):
        # Hier ist der YIN-Ansatz eingebrochen (4/12): die Akkordtoene liegen so
        # dicht ueber dem Bass, dass ihre Periodizitaet die Periodenschaetzung
        # wegzieht - gemessen wurden 56.6 Hz fuer ein A1 (55.0 Hz), also ein
        # halber Halbton daneben, der zur Haelfte auf A# rundet. Das
        # Tiefband-Chroma hat das Problem nicht: es misst spektral, nicht
        # periodisch, und die CQT nimmt unten lange Fenster.
        bass = E1 + halbton
        assert _messe([bass, bass + 12, bass + 15, bass + 20]) == bass % 12

    @pytest.mark.parametrize("halbton", range(12))
    def test_umkehrung_bass_ist_die_terz(self, halbton):
        # Der eigentliche Zweck: bei C/E liegt die TERZ unten, nicht der Grundton.
        bass = E1 + halbton
        assert _messe([bass, bass + 9, bass + 12, bass + 17]) == bass % 12

    def test_stille_liefert_keine_note(self):
        stille = np.zeros(int(1.5 * SAMPLERATE), dtype=np.float32)
        assert dominant(analyze_window(stille, SAMPLERATE).bass_frames) is None


class TestUmkehrungAmSignal:
    """Der Befund, der den BASS_BONUS gekippt hat - am echten Signal.

    Ein Chroma-Test allein wuerde das verfehlen: Der Bonus griff erst, wenn ein
    Bass-Chroma dabei war, also nur in der vollen Pipeline. Deshalb hier vom
    Audio bis zum angezeigten Namen.
    """

    @staticmethod
    def _anzeige(midi_noten) -> str:
        """Genau das, was die Anzeige zeigt: Akkord aus dem Chroma, Bass gemessen."""
        from jampilot.chords import match_chord

        audio = _chord(midi_noten, 1.5)
        analyse = analyze_window(audio, SAMPLERATE)
        akkord = match_chord(analyse.chroma, cqt=analyse.cqt).name
        frames = analyse.bass_frames
        juengere = frames[:, frames.shape[1] // 2:]
        return slash(akkord, name(dominant(juengere)))

    def test_f_dur_mit_a_im_bass_ist_nicht_am(self):
        # A1 unten, F-Dur darueber. Der BASS_BONUS zog den Grundton auf das A und
        # machte daraus ein Am - ein Akkord, der ein E verspricht, das hier nicht
        # klingt. Wer danach greift, spielt daneben.
        assert self._anzeige([33, 53, 57, 60]) == "F/A"

    def test_c_dur_mit_e_im_bass_ist_nicht_em(self):
        # Dieselbe Falle eine Stufe weiter: E1 unten, C-Dur darueber -> frueher Em,
        # das ein H verspricht, das nirgends klingt.
        assert self._anzeige([28, 48, 52, 55]) == "C/E"

    def test_grundstellung_bleibt_ohne_slash(self):
        # Die Gegenprobe: Liegt der Grundton unten, darf kein Slash erscheinen.
        assert self._anzeige([36, 48, 52, 55]) == "C"


class TestDominant:
    def test_klarer_gewinner(self):
        pooled = np.zeros((12, 3))
        pooled[4] = 1.0
        assert dominant(pooled) == 4

    def test_ohne_klaren_vorsprung_wird_nicht_geraten(self):
        # Zwei gleich starke Toene unten heissen: kein klarer Basston. Dann lieber
        # nichts anzeigen als raten - dieselbe Haltung wie im ChordSmoother.
        pooled = np.zeros((12, 2))
        pooled[4] = 1.0
        pooled[7] = 0.95
        assert dominant(pooled) is None

    def test_stille_liefert_nichts(self):
        assert dominant(np.zeros((12, 4))) is None

    def test_ohne_frames_liefert_nichts(self):
        assert dominant(None) is None


class TestBassTrack:
    @staticmethod
    def _fuellen(track, pitch_class, start, sekunden):
        anzahl = int(sekunden / FRAME_SECONDS)
        frames = np.zeros((12, anzahl), dtype=np.float32)
        frames[pitch_class] = 1.0
        track.add(frames, start)

    def test_findet_die_note_im_intervall(self):
        track = BassTrack(10.0)
        self._fuellen(track, 4, start=0.0, sekunden=2.0)
        assert track.note_between(0.5, 1.5) == 4

    def test_trennt_zwei_segmente(self):
        # Genau das braucht die Zeitleiste: pro Akkord-Segment die eigene Bassnote.
        track = BassTrack(10.0)
        self._fuellen(track, 4, start=0.0, sekunden=2.0)
        self._fuellen(track, 7, start=2.0, sekunden=2.0)
        assert track.note_between(0.3, 1.8) == 4
        assert track.note_between(2.3, 3.8) == 7

    def test_ohne_material_keine_note(self):
        assert BassTrack(10.0).note_between(0.0, 1.0) is None

    def test_intervall_hinter_dem_material_liefert_nichts(self):
        track = BassTrack(10.0)
        self._fuellen(track, 4, start=0.0, sekunden=1.0)
        assert track.note_between(5.0, 6.0) is None

    def test_ohne_frames_passiert_nichts(self):
        track = BassTrack(10.0)       # FFT-Fallback liefert keine Bass-Frames
        track.add(None, 0.0)
        assert track.note_between(0.0, 1.0) is None


class TestSlash:
    def test_bass_gleich_grundton_bleibt_der_akkord(self):
        assert slash("C", "C") == "C"
        assert slash("Am7", "A") == "Am7"

    def test_umkehrung_wird_sichtbar(self):
        assert slash("C", "E") == "C/E"
        assert slash("F", "A") == "F/A"
        assert slash("A#m7", "C#") == "A#m7/C#"

    def test_ohne_bass_bleibt_der_akkord(self):
        assert slash("C", None) == "C"

    def test_nichtakkorde_bleiben(self):
        for nichtakkord in ("-", "?", "N"):
            assert slash(nichtakkord, "E") == nichtakkord

    def test_grundton_aus_der_kanonischen_id(self):
        assert chord_root("A#m7") == 10
        assert chord_root("C") == 0
        assert chord_root("-") is None


class TestName:
    def test_kanonisch_mit_kreuz(self):
        # Wie beim Akkord: der Server liefert die ID, die Schreibweise entscheidet
        # spaeter die Tonart im Browser.
        assert name(10) == "A#"
        assert name(None) is None

    def test_deckt_sich_mit_den_notennamen(self):
        assert [name(i) for i in range(12)] == NOTE_NAMES

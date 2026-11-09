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
    def test_register_laeuft_parallel_mit(self):
        track = BassTrack(10.0, frame_seconds=0.1, edge=0)
        frames = np.zeros((12, 20), dtype=np.float32); frames[9] = 1.0    # A im Tiefband
        register = np.zeros((12, 20), dtype=np.float32); register[9, :10] = 0.5
        track.add(frames, 0.0, register=register)
        assert track.pooled_between(0.0, 2.0)[9] == pytest.approx(20.0)
        assert track.register_between(0.0, 1.0)[9] == pytest.approx(5.0)
        assert track.register_between(1.0, 2.0)[9] == pytest.approx(0.0)

    def test_ohne_register_kommt_none(self):
        track = BassTrack(10.0, frame_seconds=0.1, edge=0)
        track.add(np.ones((12, 20), dtype=np.float32), 0.0)
        assert track.pooled_between(0.0, 2.0) is not None
        assert track.register_between(0.0, 2.0) is None

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


class TestSlashNote:
    """Die konservative Slash-Entscheidung (BTC-Pfad): drei Huerden, bevor
    etwas anderes als der Grundton behauptet wird."""

    def _pooled(self, **energie):
        pooled = np.zeros(12)
        for pc, wert in energie.items():
            pooled[int(pc)] = wert
        return pooled

    def test_grundton_kommt_ohne_ratio_huerde_zurueck(self):
        from jampilot.bass import slash_note
        pooled = self._pooled(**{"7": 10.0, "2": 1.0})    # G dominiert
        assert slash_note(pooled, "G") == 7

    def test_echte_umkehrung_terz_im_bass(self):
        from jampilot.bass import slash_note
        # G/B: B (11) klar staerkster Ton, Grundton G (7) schwach.
        pooled = self._pooled(**{"11": 10.0, "7": 2.0})
        assert slash_note(pooled, "G") == 11

    def test_laute_quinte_erfindet_keinen_slash(self):
        from jampilot.bass import slash_note
        # D (2) gewinnt die Mehrheit, aber nicht 2x gegen den Grundton G (7).
        pooled = self._pooled(**{"2": 10.0, "7": 6.0})
        assert slash_note(pooled, "G") is None

    def test_rauschgewinner_ist_kein_akkordton(self):
        from jampilot.bass import slash_note
        # G# (8) ist kein Ton von G-Dur - wird nicht behauptet.
        pooled = self._pooled(**{"8": 10.0, "7": 1.0})
        assert slash_note(pooled, "G") is None

    def test_ohne_mehrheit_keine_aussage(self):
        from jampilot.bass import slash_note
        pooled = self._pooled(**{"11": 5.0, "7": 4.5})
        assert slash_note(pooled, "G") is None

    # Die vierte Huerde: die Quinte braucht eine Bassstimme im Register.
    # If This Is Goodbye, Strophe 1: offener D-Griff ohne Bass, die A-Saite ist
    # der tiefste Ton, D fehlt im Tiefband ganz - kein D/A, sondern D.

    def test_quinte_ohne_register_ist_grundton_lage(self):
        from jampilot.bass import slash_note
        pooled = self._pooled(**{"9": 90.0, "2": 4.0})      # D-Griff: A2 laut, D fehlt
        assert slash_note(pooled, "D") == 2                 # Grundton, kein Slash
        assert slash_note(pooled, "D", register=None) == 2

    def test_quinte_nur_in_der_gitarre_bleibt_grundton(self):
        from jampilot.bass import slash_note
        pooled = self._pooled(**{"9": 90.0, "2": 4.0})
        register = self._pooled(**{"9": 1.5, "2": 2.0})     # unter E2 nichts (1-2 %)
        assert slash_note(pooled, "D", register) == 2

    def test_quinte_mit_bassstimme_ist_umkehrung(self):
        from jampilot.bass import slash_note
        # Goodbye 240 s: der Bass haelt A1 (55 Hz) unter D -> D/A ist echt.
        pooled = self._pooled(**{"9": 516.0, "2": 73.0})
        register = self._pooled(**{"9": 351.0, "2": 33.0})  # 68 % im Register
        assert slash_note(pooled, "D", register) == 9

    def test_terz_braucht_kein_register(self):
        from jampilot.bass import slash_note
        # Let It Be Em/G: Terz im Bass, Register leer - bleibt Umkehrung.
        pooled = self._pooled(**{"7": 10.0, "4": 2.0})
        assert slash_note(pooled, "Em", register=self._pooled()) == 7
        assert slash_note(pooled, "Em") == 7


class TestDurchgangsbass:
    """bass.passing_note: Durchgangston am Segmentende (G - F# - Em)."""

    @staticmethod
    def _frames(noten, staerke=1.0):
        """12 x F: je Frame eine klare Tonklasse (Rest leises Rauschen)."""
        from jampilot.bass import chord_root
        out = np.full((12, len(noten)), 0.02, dtype=float)
        for i, n in enumerate(noten):
            if n is not None:
                out[chord_root(n), i] = staerke
        return out

    def test_g_fis_vor_em_wird_gefunden(self):
        from jampilot.bass import passing_note
        frames = self._frames(["G"] * 15 + ["F#"] * 5)
        assert passing_note(frames, chord_root("G"), chord_root("Em")) == (15, chord_root("F#"))

    def test_aufwaerts_geht_auch(self):
        from jampilot.bass import passing_note
        frames = self._frames(["C"] * 10 + ["D"] * 4)
        assert passing_note(frames, chord_root("C"), chord_root("E")) == (10, chord_root("D"))

    def test_zu_kurzer_lauf(self):
        from jampilot.bass import passing_note
        frames = self._frames(["G"] * 15 + ["F#"] * 2)
        assert passing_note(frames, chord_root("G"), chord_root("Em")) is None

    def test_lauf_muss_das_segment_beenden(self):
        from jampilot.bass import passing_note
        frames = self._frames(["G"] * 5 + ["F#"] * 5 + ["G"] * 8)
        assert passing_note(frames, chord_root("G"), chord_root("Em")) is None

    def test_kein_schritt_zwischen_den_grundtoenen(self):
        from jampilot.bass import passing_note
        # D - B - G: die Terz unter D ist kein Durchgang (Eight Days a Week)
        frames = self._frames(["D"] * 10 + ["B"] * 5)
        assert passing_note(frames, chord_root("D"), chord_root("G")) is None
        # Quinte als Lauf: A zwischen D und D ist kein Wechsel
        assert passing_note(self._frames(["D"] * 10 + ["A"] * 5), chord_root("D"), chord_root("D")) is None

    def test_grundtoene_selbst_sind_kein_durchgang(self):
        from jampilot.bass import passing_note
        frames = self._frames(["G"] * 10 + ["E"] * 5)   # der Bass geht frueh auf E
        assert passing_note(frames, chord_root("G"), chord_root("Em")) is None

    def test_grundton_ratio_gilt_ueber_den_lauf(self):
        from jampilot.bass import passing_note
        frames = self._frames(["G"] * 10 + ["F#"] * 5)
        frames[chord_root("G"), 10:] = 0.5              # G klingt unter dem F# weiter
        assert passing_note(frames, chord_root("G"), chord_root("Em")) is None

    def test_unklare_frames_brechen_den_lauf(self):
        from jampilot.bass import passing_note
        frames = self._frames(["G"] * 10 + ["F#"] * 5)
        frames[chord_root("F"), 12] = 1.0               # ein Frame ohne Mehrheit
        assert passing_note(frames, chord_root("G"), chord_root("Em")) is None

    def test_ohne_grundton_nichts(self):
        from jampilot.bass import passing_note
        frames = self._frames(["G"] * 10 + ["F#"] * 5)
        assert passing_note(frames, None, chord_root("Em")) is None
        assert passing_note(None, chord_root("G"), chord_root("Em")) is None

    def test_frames_between_liefert_verlauf_und_startzeit(self):
        track = BassTrack(10.0, frame_seconds=0.1, edge=0)
        frames = np.zeros((12, 20), dtype=np.float32)
        frames[chord_root("G"), :10] = 1.0
        frames[chord_root("F#"), 10:] = 1.0
        track.add(frames, 3.0)
        got = track.frames_between(3.0, 5.0)
        assert got is not None
        verlauf, erster = got
        assert erster == pytest.approx(3.0)
        assert verlauf.shape == (12, 20)
        assert verlauf.argmax(axis=0).tolist() == [chord_root("G")] * 10 + [chord_root("F#")] * 10
        assert track.frame_seconds == pytest.approx(0.1)


class TestOktave:
    """Die LAGE aus den drei Oktavbins einer Tonklasse (bass.octave):
    tiefste Oktave mit mindestens OCTAVE_SHARE des staerksten Bins."""

    @staticmethod
    def _bins(**oktaven):
        from jampilot.bass import OCTAVES
        out = np.zeros(12 * OCTAVES)
        for k, v in oktaven.items():            # "e1" -> Zeile 4, "e2" -> 16
            pc, o = NOTE_NAMES.index(k[:-1].upper()), int(k[-1])
            out[(o - 1) * 12 + pc] = v
        return out

    def test_grundton_unten_ist_oktave_eins(self):
        from jampilot.bass import octave
        assert octave(self._bins(e1=1.0, e2=0.6, e3=0.2), 4) == 1

    def test_schwacher_grundton_zaehlt_trotzdem(self):
        # Der Grundton eines E-Basses ist im Mix oft schwaecher als sein
        # erster Oberton - "staerkster Bin" waere eine Oktave zu hoch.
        from jampilot.bass import octave
        assert octave(self._bins(e1=0.4, e2=1.0, e3=0.3), 4) == 1

    def test_leck_unter_der_schwelle_zaehlt_nicht(self):
        from jampilot.bass import OCTAVE_SHARE, octave, pitch
        bins = self._bins(e1=0.5 * OCTAVE_SHARE, e2=1.0, e3=0.5)
        assert octave(bins, 4) == 2
        assert pitch(bins, 4) == 40                      # E2

    def test_hohe_lage(self):
        from jampilot.bass import octave
        assert octave(self._bins(e1=0.01, e2=0.05, e3=1.0), 4) == 3

    def test_frames_werden_gepoolt(self):
        from jampilot.bass import octave
        frames = np.stack([self._bins(e1=1.0), self._bins(e2=1.0)], axis=1)   # (36, 2)
        assert octave(frames, 4) == 1

    def test_ohne_ton_oder_tonklasse_keine_lage(self):
        from jampilot.bass import octave, pitch
        assert octave(None, 4) is None
        assert octave(self._bins(), 4) is None
        assert octave(self._bins(e2=1.0), None) is None
        assert pitch(None, 4) is None

    def test_bass_track_fuehrt_die_notenbins_mit(self):
        track = BassTrack(10.0, frame_seconds=0.1, edge=0)
        frames = np.zeros((12, 20), dtype=np.float32); frames[4] = 1.0
        pitches = np.zeros((36, 20), dtype=np.float32); pitches[16, :10] = 1.0   # E2
        track.add(frames, 0.0, pitches=pitches)
        assert track.pitches_between(0.0, 1.0)[16] == pytest.approx(10.0)
        assert track.pitches_between(1.0, 2.0)[16] == pytest.approx(0.0)

    def test_ohne_notenbins_kommt_none(self):
        track = BassTrack(10.0, frame_seconds=0.1, edge=0)
        track.add(np.ones((12, 20), dtype=np.float32), 0.0)
        assert track.pitches_between(0.0, 2.0) is None


class TestOktaveAmSignal:
    """E1, E2, E3 mit Akkord darueber und Schlagzeug - durch die BTC-CQT."""

    @pytest.mark.parametrize("halbton", [0, 3, 7])          # bis B3, hoeher reicht der Hals nicht
    @pytest.mark.parametrize("oktave", [1, 2, 3])
    def test_lage_wird_erkannt(self, halbton, oktave):
        from jampilot.bass import octave
        from jampilot.btc import bass_pitches, features_from_audio
        from jampilot.selftest import _chord, _drums

        bass = E1 + 12 * (oktave - 1) + halbton
        audio = _chord([bass, bass + 12, bass + 16, bass + 19], 2.0)
        audio = audio + 0.8 * _drums(2.0, np.random.default_rng(5))[: len(audio)]
        audio = (audio / np.abs(audio).max()).astype(np.float32)
        pitches = bass_pitches(features_from_audio(audio, SAMPLERATE))[:, 4:-4]
        assert octave(pitches, bass % 12) == (bass - 24) // 12 + 1

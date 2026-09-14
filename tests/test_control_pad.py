"""Die Kontrollflaeche macht Akkordfehler hoerbar, ohne Begleitautomat zu sein."""

import numpy as np

from jampilot.control_pad import (
    ATTACK_SECONDS,
    CONTROL_GAIN,
    PAD_SECONDS,
    PLAYBACK_GAIN,
    RELEASE_SECONDS,
    _midi_voicing,
    release_envelope,
    render,
)


def test_rendert_dur_und_moll_als_stereoflaeche():
    major = render("A", 8000)
    minor = render("Am", 8000)
    assert major.ndim == 2 and major.shape[1] == 2
    assert major.shape[0] == int(PAD_SECONDS * 8000)
    assert minor.shape == major.shape
    assert np.any(major != 0)
    assert not np.array_equal(major, minor)       # die kritische Terz ist hoerbar


def test_flaeche_steht_bis_zum_ende_des_caches():
    sound = render("C", 8000)
    # Eingeschwungen: die letzte Sekunde ist so laut wie die Mitte - der
    # Ausklang kommt erst beim Mischen (release_envelope), nicht im Cache.
    mitte = np.sqrt(np.mean(sound[4 * 8000:5 * 8000] ** 2))
    ende = np.sqrt(np.mean(sound[-8000:] ** 2))
    assert abs(mitte - ende) < 0.15 * mitte


def test_langsamer_einschwinger():
    sound = render("G", 8000)
    n_att = int(ATTACK_SECONDS * 8000)
    assert np.max(np.abs(sound[: n_att // 4])) < 0.3 * np.max(np.abs(sound))


def test_kontrollflaeche_bleibt_leise():
    sound = render("C7", 8000)
    assert np.max(np.abs(sound)) <= CONTROL_GAIN + 1e-6


def test_diagnose_mix_laesst_das_original_hoerbar():
    assert 0.1 <= CONTROL_GAIN <= 0.3
    assert 0.5 <= PLAYBACK_GAIN <= 0.7


def test_stille_und_unbekanntes_erzeugen_keinen_ton():
    assert render("-", 8000) is None
    assert render("?", 8000) is None
    assert render("Cblub", 8000) is None       # wirklich unbekannte Qualitaet


def test_btc_vokabular_wird_gespielt():
    for chord in ("Csus4", "Adim7", "G6", "Em7b5", "Faug", "DmMaj7"):
        assert render(chord, 8000) is not None, chord


def test_slash_spielt_den_akkord():
    assert np.array_equal(render("G/F#", 8000), render("G", 8000))


def test_voicing_liegt_in_der_keyboard_mitte_mit_grundton_unten():
    notes = _midi_voicing(0, "")                   # C-Dur
    assert notes == [48, 60, 64, 67]               # C3 unter C4 E4 G4
    assert all(48 <= n <= 83 for n in _midi_voicing(11, "maj7"))


def test_safe_voicing_spielt_bei_dur_moll_unsicherheit_nur_powerchord():
    notes = _midi_voicing(9, "", safe_pcs=(9, 4))
    assert {note % 12 for note in notes} == {9, 4}     # kein C# hinzugefuegt


def test_release_envelope_nur_am_segmentende():
    sr = 8000
    length = 2 * sr
    assert release_envelope(length, sr, 0, 64) is None          # weit vor dem Ende
    n_rel = int(RELEASE_SECONDS * sr)
    env = release_envelope(length, sr, length - n_rel - 32, 64)
    assert env.shape == (64,)
    assert np.all(env[:32] == 1.0)                              # vor dem Ausklang
    assert env[32] > env[-1]                                    # faellt
    ende = release_envelope(length, sr, length - 8, 8)
    assert ende[-1] < 0.01                                      # geht auf null

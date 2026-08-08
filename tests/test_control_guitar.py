"""Die Kontrollgitarre macht Akkordfehler hoerbar, ohne Begleitautomat zu sein."""

import numpy as np

from jampilot.control_guitar import (
    CONTROL_GAIN,
    PLAYBACK_GAIN,
    _midi_voicing,
    render,
)


def test_rendert_dur_und_moll_als_stereoanschlag():
    major = render("A", 8000)
    minor = render("Am", 8000)
    assert major.ndim == 2 and major.shape[1] == 2
    assert minor.shape == major.shape
    assert np.any(major != 0)
    assert not np.array_equal(major, minor)       # die kritische Terz ist hoerbar


def test_kontrollanschlag_bleibt_leise():
    sound = render("C7", 8000)
    assert np.max(np.abs(sound)) <= CONTROL_GAIN + 1e-6


def test_diagnose_mix_hebt_gitarre_gegenueber_playback_hervor():
    assert CONTROL_GAIN >= .3
    assert PLAYBACK_GAIN <= .6


def test_stille_und_unbekanntes_erzeugen_keinen_ton():
    assert render("-", 8000) is None
    assert render("?", 8000) is None
    assert render("Cblub", 8000) is None       # wirklich unbekannte Qualitaet


def test_btc_vokabular_wird_angeschlagen():
    # Seit dem BTC-Vokabular sind auch sus/dim/6 spielbar - volle Akkorde.
    for chord in ("Csus4", "Adim7", "G6", "Em7b5", "Faug", "DmMaj7"):
        assert render(chord, 8000) is not None, chord


def test_safe_voicing_spielt_bei_dur_moll_unsicherheit_nur_powerchord():
    notes = _midi_voicing(9, "", safe_pcs=(9, 4))
    assert {note % 12 for note in notes} == {9, 4}     # kein C# hinzugefuegt
    assert len(notes) == 3                             # A E A

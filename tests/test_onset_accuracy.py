"""Regressionswaechter fuer die Timing-Genauigkeit.

Der ganze Sinn der Anzeige steht und faellt damit, dass der gemeldete
Akkordwechsel dort liegt, wo er im Signal tatsaechlich stattfindet. Frueher
wurde er aus einer konstanten Latenz zurueckgerechnet (Fehler bis ~200 ms und
stark schwankend); heute wird er im Frame-Chroma gesucht. Dieser Test haelt das
fest - er schlaegt an, sobald jemand am Fenster, am Pooling oder an der
Onset-Suche dreht.
"""

import numpy as np
import pytest

from jampilot.chords import ChordSmoother, find_onset_frame, match_chord
from jampilot.chroma import FRAME_SECONDS, HAVE_LIBROSA, analyze_window
from jampilot.selftest import SAMPLERATE, _realistic

pytestmark = pytest.mark.skipif(not HAVE_LIBROSA,
                                reason="Onset-Suche braucht das CQT-Frame-Chroma")

WINDOW = 1.5
NOTEN = {
    "C": [36, 48, 52, 55, 60],
    "G": [31, 43, 47, 50, 55],
    "Am": [33, 45, 48, 52, 57],
    "F": [29, 41, 45, 48, 53],
}


def _fenster_mit_wechsel(vorher: str, nachher: str, wechsel_bei: float, seed: int = 7):
    """Ein WINDOW langes Fenster, in dem bei `wechsel_bei` (Sekunden ab
    Fensteranfang) der Akkord wechselt - mit Drums und Melodie wie in echt."""
    rng = np.random.default_rng(seed)
    links = _realistic(NOTEN[vorher], rng)[: int(wechsel_bei * SAMPLERATE)]
    rest = int(WINDOW * SAMPLERATE) - len(links)
    rechts = _realistic(NOTEN[nachher], rng)[:rest]
    return np.concatenate([links, rechts]).astype(np.float32)


def _gemessener_onset(vorher, nachher, wechsel_bei, seed=7):
    audio = _fenster_mit_wechsel(vorher, nachher, wechsel_bei, seed)
    analyse = analyze_window(audio, SAMPLERATE)
    index = find_onset_frame(analyse.frames, vorher, nachher)
    assert index is not None
    # Frame k ist der erste des neuen Akkords; die Grenze liegt ein halbes
    # Frame davor (Frame-Mitte vs. Frame-Anfang).
    return max(index - 0.5, 0.0) * FRAME_SECONDS


@pytest.mark.parametrize("vorher,nachher", [
    ("C", "G"), ("G", "Am"), ("Am", "F"), ("F", "C"), ("C", "Am"),
])
@pytest.mark.parametrize("wechsel_bei", [0.6, 0.9, 1.1])
def test_onset_wird_auf_unter_100ms_genau_gefunden(vorher, nachher, wechsel_bei):
    gemessen = _gemessener_onset(vorher, nachher, wechsel_bei)
    fehler = abs(gemessen - wechsel_bei)
    assert fehler < 0.100, (
        f"{vorher}->{nachher} bei {wechsel_bei}s: gemessen {gemessen:.3f}s "
        f"(Fehler {fehler * 1000:.0f} ms)")


def test_onset_streut_kaum():
    """Nicht nur genau, sondern auch STABIL - die alte Schaetzung war im Mittel
    brauchbar, schwankte aber um mehrere hundert Millisekunden. Genau das war
    als 'mal passt es, mal ist es stark verzoegert' spuerbar."""
    fehler = []
    for seed in range(6):
        for vorher, nachher in [("C", "G"), ("G", "Am"), ("Am", "F")]:
            gemessen = _gemessener_onset(vorher, nachher, 0.9, seed=seed)
            fehler.append(gemessen - 0.9)

    streuung = float(np.std(fehler))
    spannweite = float(np.max(fehler) - np.min(fehler))
    assert streuung < 0.050, f"Streuung {streuung * 1000:.0f} ms zu gross"
    assert spannweite < 0.150, f"Spannweite {spannweite * 1000:.0f} ms zu gross"


def test_erkennung_und_onset_greifen_ineinander():
    """Was der Glaetter meldet, muss zum gefundenen Zeitpunkt passen."""
    audio = _fenster_mit_wechsel("C", "G", 0.8)
    analyse = analyze_window(audio, SAMPLERATE)

    # Gepoolt wird die juengere Fensterhaelfte -> dort klingt bereits G.
    assert match_chord(analyse.chroma, cqt=analyse.cqt).name == "G"

    smoother = ChordSmoother(window=3)
    for _ in range(3):
        name = smoother.update(match_chord(analyse.chroma, cqt=analyse.cqt))
    assert name == "G"

    index = find_onset_frame(analyse.frames, "C", "G")
    assert 0.8 - 0.1 < index * FRAME_SECONDS < 0.8 + 0.1

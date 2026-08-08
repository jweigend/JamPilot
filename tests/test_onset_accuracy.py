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
from jampilot.chroma import FRAME_SECONDS, HAVE_LIBROSA, FrameHistory, analyze_window
from jampilot.cli import (ANALYSIS_HOP, ANALYSIS_WINDOW, MAX_ONSET_SEARCH,
                          _commit, _locate_onset)
from jampilot.selftest import SAMPLERATE, _drums, _realistic

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


# --- Breaks vor dem Wechsel ------------------------------------------------
#
# Der Fall, an dem die Anzeige beim Mitspielen unbrauchbar wurde: Die Band setzt
# vor der Eins ab, und die Anzeige zeigt den Zielakkord schon im Break - man
# greift ihn, und er kommt erst einen Schlag spaeter.
#
# Die Ursache lag in der Onset-Suche: Sie schnitt rein RELATIV ("passt neu
# besser als alt"). Im Break faellt der alte Score zusammen, der Gewinn wird
# positiv, und der Schnitt rutscht an den Anfang des Breaks - umso weiter, je
# laenger der Break. Gemessen: 0.5s Break -240 ms, 2s Break -693 ms, also mehr
# als ein ganzer Schlag bei langsamem Tempo.
#
# Der Waechter prueft deshalb nicht nur einen Betrag, sondern die EIGENSCHAFT,
# die vorher fehlte: Der Fehler darf mit der Laenge des Breaks nicht mitwachsen.


def _mit_break(vorher: str, nachher: str, break_sekunden: float,
               vor: float = 3.0, nach: float = 3.0, seed: int = 3):
    """[Akkord | Break nur mit Drums | Akkord] - und die Stelle des Wechsels."""
    rng = np.random.default_rng(seed)

    def strecke(chord, sekunden):
        stueck = _realistic(NOTEN[chord], rng)
        laenge = int(sekunden * SAMPLERATE)
        while len(stueck) < laenge:
            stueck = np.concatenate([stueck, _realistic(NOTEN[chord], rng)])
        return stueck[:laenge]

    drums = _drums(break_sekunden, rng) if break_sekunden else np.zeros(0)
    if len(drums):
        drums = drums / np.abs(drums).max() * 0.4
    audio = np.concatenate([strecke(vorher, vor), drums, strecke(nachher, nach)])
    return audio.astype(np.float32), vor + break_sekunden


def _lauf(audio, nachher):
    """Der Onset, den der LIVE-Pfad meldet - Frame-Historie, Suche, Zeitleiste.

    Die fensterweise Messung reicht hier nicht: Ein Break ist laenger als ein
    Analysefenster, und genau die Suche ueber die Historie hinweg war der Weg,
    auf dem der Fehler beliebig gross werden konnte.
    """
    fenster = int(ANALYSIS_WINDOW * SAMPLERATE)
    hop = int(ANALYSIS_HOP * SAMPLERATE)
    smoother = ChordSmoother(window=3)
    history = FrameHistory(MAX_ONSET_SEARCH + ANALYSIS_WINDOW + 1.0)
    timeline, aktuell = [], None

    for ende in range(fenster, len(audio) + 1, hop):
        analyse = analyze_window(audio[ende - fenster : ende], SAMPLERATE)
        history.add(analyse.frames, (ende - fenster) / SAMPLERATE)
        akkord = smoother.update(match_chord(analyse.chroma, cqt=analyse.cqt))
        if akkord in ("?", "N", aktuell):
            continue
        gefunden = _locate_onset(akkord, aktuell, history, ende / SAMPLERATE,
                                 timeline[-1][0] if timeline else None)
        # audible_pos weit zurueck: im Betrieb liegt der Vorlauf vor der Ausgabe,
        # jedes frische Segment ist also noch ruecknehmbar.
        _commit(timeline, gefunden, akkord, ende / SAMPLERATE - 4.0)
        aktuell = timeline[-1][1] if timeline else akkord

    treffer = [pos for pos, name in timeline if name == nachher]
    return treffer[0] if treffer else None


# Ein Durchlauf kostet ein paar Sekunden CQT - der Waechter unten braucht
# dieselben Faelle noch einmal, also einmal rechnen und aufheben.
_GEMESSEN: dict[tuple, float | None] = {}


def _fehler(vorher, nachher, break_sekunden):
    """Wie weit vor (negativ) oder hinter dem echten Wechsel der Onset landet."""
    schluessel = (vorher, nachher, break_sekunden)
    if schluessel not in _GEMESSEN:
        audio, wechsel = _mit_break(vorher, nachher, break_sekunden)
        gemeldet = _lauf(audio, nachher)
        _GEMESSEN[schluessel] = None if gemeldet is None else gemeldet - wechsel
    return _GEMESSEN[schluessel]


@pytest.mark.parametrize("break_sekunden", [0.5, 2.0])
@pytest.mark.parametrize("vorher,nachher", [("C", "G"), ("Am", "F")])
def test_break_zieht_den_onset_nicht_vor(vorher, nachher, break_sekunden):
    fehler = _fehler(vorher, nachher, break_sekunden)
    assert fehler is not None, f"{nachher} gar nicht gefunden"
    # Was bleibt, ist der Vorausblick der CQT selbst: ihr tiefstes Filter ist
    # 786 ms lang und liegt mittig, ein Akkord ist darin ~165 ms vor dem
    # Anschlag sichtbar. Frueher als das darf die Suche nicht schneiden.
    assert fehler > -0.300, (
        f"{vorher}->{nachher} mit {break_sekunden}s Break: {fehler * 1000:.0f} ms "
        f"zu frueh - der Break zieht den Onset wieder vor")


def test_fehler_waechst_nicht_mit_der_breaklaenge():
    """Der eigentliche Regressionswaechter: ein viermal so langer Break darf den
    Onset nicht weiter vorziehen. Genau das tat die rein relative Suche - und
    dadurch war der Fehler nach oben offen.

    Verglichen wird der SCHLECHTESTE Fall je Breaklaenge, nicht ein einzelnes
    Akkordpaar. Bei der alten Formel wuchs der Fehler naemlich nicht ueberall
    gleich: C->G blieb bei ~-200 ms, waehrend Am->F auf -693 ms auslief. Ein
    Waechter, der nur ein Paar ansieht, erwischt je nach Paar gar nichts - und
    liesse den Fehler wieder herein.
    """
    def schlechtester(break_sekunden):
        gemessen = [_fehler(v, n, break_sekunden)
                    for v, n in (("C", "G"), ("Am", "F"))]
        assert all(f is not None for f in gemessen)
        return min(gemessen)

    kurz, lang = schlechtester(0.5), schlechtester(2.0)
    assert lang > kurz - 0.100, (
        f"Break 0.5s: {kurz * 1000:.0f} ms, Break 2.0s: {lang * 1000:.0f} ms - "
        f"der Fehler waechst mit der Breaklaenge")

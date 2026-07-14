"""Die Bassnote MESSEN, statt sie aus dem Akkord zu erraten.

Der Akkordname enthaelt nicht, was der Bassist spielt. Bei C/E steht im Akkord
ein C, und unten liegt ein E. Diese Information ist genau das, was ein Bassist
wissen will - und ausgerechnet ueber sie sind sich menschliche Annotatoren am
wenigsten einig (Koops et al. 2019: Umkehrungen sind der groesste Streitpunkt).

Gemessen wird im TIEFBAND-CHROMA, das die Pipeline ohnehin berechnet:
`chroma.analyze_window` zieht eine zweite CQT ueber 32..260 Hz (`bass_frames`).
Bisher wurde sie gepoolt, auf ein einziges Skalar eingedampft und dann
weggeworfen. Sie aufzuheben kostet Speicher, aber KEINE Rechenzeit - die CQT
laeuft so oder so.

Dieses Skalar war ein BASS_BONUS in der Akkordwahl: Akkorde, deren Grundton
unten klang, bekamen Punkte dazu. Das war der Versuch, aus dem Bass auf den
Akkord zu schliessen - und er ging bei jeder Umkehrung schief, weil dort unten
gerade NICHT der Grundton liegt (aus C/E wurde Em, aus F/A ein Am). Mit der
Messung ist er ersatzlos entfallen: Der Akkord kommt aus der Tonklassen-Menge,
die Bassnote aus dem Tiefband, und der Slash-Name setzt beides zusammen. Zwei
Fragen, zwei Signale - statt eines Signals, das beide Fragen halb beantwortet.

Warum nicht pYIN/YIN, wie es die Bass-Transkriptionsliteratur empfiehlt?
Ausprobiert und verworfen, mit Zahlen:

  Verfahren                        Trefferquote (Bass-Tonklasse, 60 Faelle
                                   mit Schlagzeug, verschiedene Voicings)
  -------------------------------------------------------------------------
  Tiefband-Chroma (CQT)            60/60      und kostet 0 ms (faellt eh an)
  YIN auf dem Tiefband             50/60      und kostet 4.2 ms

  Beim dichten Voicing - Akkordtoene direkt ueber dem Bass, also dem
  Normalfall in echter Musik - bricht YIN auf 4/12 ein.

Der Grund ist strukturell: YIN schaetzt die Periodendauer der MISCHUNG. Liegen
Akkordtoene nah ueber dem Bass, zieht ihre Periodizitaet die Schaetzung weg -
gemessen wurden z.B. 56.6 Hz fuer ein A1 (55.0 Hz), also ein halber Halbton
daneben, was zur Haelfte auf A# rundet. Die CQT hat dieses Problem nicht: Sie ist
ein spektrales Verfahren (Polyphonie stoert sie nicht) und benutzt bei tiefen
Frequenzen lange Fenster - genau dafuer ist sie gebaut. Die schlechte
Frequenzaufloesung im Sub-Bass, vor der die Literatur warnt, ist ein Problem der
FFT mit fester Fensterlaenge, nicht der CQT.

Die pYIN-Empfehlung aus der Literatur gilt einem anderen Problem: der
monophonen Bass-Transkription aus einem ISOLIERTEN Stem (Note + Oktave). Wir
brauchen die TONKLASSE im MIX. Anderes Problem, anderes Werkzeug.
"""

import numpy as np

from .chroma import NOTE_NAMES

# Die staerkste Tonklasse muss die zweitstaerkste um diesen Faktor schlagen.
# Sonst liegt unten kein klarer Ton (Uebergang, Glissando, Rauschen) - und dann
# wird nichts angezeigt statt geraten. Dieselbe Haltung wie im ChordSmoother.
MIN_DOMINANCE = 1.25

# Darunter klingt im Tiefband nichts.
BASS_SILENCE = 1e-6


def dominant(bass_frames: np.ndarray | None) -> int | None:
    """Die vorherrschende Tonklasse im Tiefband - oder None.

    `bass_frames` ist 12 x F (CQT-Chroma, 32..260 Hz). Ueber die Frames wird
    aufsummiert; gewinnt niemand deutlich, gibt es keine Antwort.
    """
    if bass_frames is None or bass_frames.size == 0:
        return None
    pooled = np.asarray(bass_frames, dtype=float)
    if pooled.ndim == 2:
        pooled = pooled.sum(axis=1)
    if pooled.sum() < BASS_SILENCE:
        return None

    rang = np.argsort(pooled)[::-1]
    bester, zweiter = pooled[rang[0]], pooled[rang[1]]
    if zweiter > 0 and bester < MIN_DOMINANCE * zweiter:
        return None                      # kein klarer Gewinner -> nicht raten
    return int(rang[0])


class BassTrack:
    """Rollendes Tiefband-Chroma in Stream-Koordinaten.

    Dasselbe Prinzip wie FrameHistory: Die Frames fallen ohnehin an; hier werden
    sie aufgehoben, damit sich die Bassnote jedem Segment der Zeitleiste
    zuordnen laesst - auch einem, das noch niemand gehoert hat. Der Vorlauf gilt
    fuer den Bass genauso wie fuer den Akkord.
    """

    EDGE = 6   # wie FrameHistory: die Randframes verfaelscht das CQT-Padding

    def __init__(self, seconds: float):
        from .chroma import FRAME_SECONDS

        self._frame_seconds = FRAME_SECONDS
        self.size = max(int(seconds / FRAME_SECONDS), 1)
        self._data = np.zeros((12, self.size), dtype=np.float32)
        self.end = 0

    def add(self, bass_frames: np.ndarray | None, window_start: float):
        if bass_frames is None or bass_frames.shape[1] <= 2 * self.EDGE:
            return
        innen = bass_frames[:, self.EDGE : bass_frames.shape[1] - self.EDGE]
        erster = int(round(window_start / self._frame_seconds)) + self.EDGE
        ziel = np.arange(erster, erster + innen.shape[1]) % self.size
        self._data[:, ziel] = innen
        self.end = max(self.end, erster + innen.shape[1])

    def note_between(self, start: float, end: float) -> int | None:
        """Die vorherrschende Bass-Tonklasse im Intervall - oder None."""
        von = max(int(round(start / self._frame_seconds)), self.end - self.size)
        bis = min(int(round(end / self._frame_seconds)), self.end)
        if bis - von < 2:
            return None
        index = np.arange(von, bis) % self.size
        return dominant(self._data[:, index])


def name(pitch_class: int | None) -> str | None:
    """Kanonischer Notenname (immer mit Kreuz) - die Schreibweise entscheidet
    spaeter die Tonart, genau wie beim Akkord."""
    return None if pitch_class is None else NOTE_NAMES[pitch_class]


def chord_root(chord: str) -> int | None:
    """Tonklasse des Akkord-Grundtons aus der kanonischen ID ("A#m7" -> 10)."""
    if not chord or chord[0] not in "ABCDEFG":
        return None                      # "N", "-", "?"
    root = chord[:2] if len(chord) > 1 and chord[1] == "#" else chord[:1]
    return NOTE_NAMES.index(root)


def slash(chord: str, bass_name: str | None) -> str:
    """C mit Bass E ergibt C/E - aber nur, wenn der Bass NICHT der Grundton ist.

    Das ist der ganze Sinn der Messung: Liegt unten etwas anderes als der
    Grundton, steht das im Akkordnamen nicht drin.
    """
    if not bass_name:
        return chord
    root = chord_root(chord)
    if root is None or NOTE_NAMES[root] == bass_name:
        return chord
    return f"{chord}/{bass_name}"

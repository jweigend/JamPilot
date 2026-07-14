"""Akkorderkennung per Template-Matching auf Chroma-Vektoren."""

from dataclasses import dataclass

import numpy as np

from .chroma import NOTE_NAMES

# Intervallstrukturen relativ zum Grundton (Halbtonschritte).
CHORD_TYPES = {
    "": (0, 4, 7),        # Dur
    "m": (0, 3, 7),       # Moll
    "7": (0, 4, 7, 10),   # Dominantsept
    "maj7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10),
}

# Unterhalb dieser Cosinus-Aehnlichkeit gilt der Klang als "kein Akkord".
MATCH_THRESHOLD = 0.55

# Obertoene erzeugen scheinbare Septimen; Vierklaenge muessen die Triade
# deshalb um eine Marge pro Zusatzton schlagen. Das rohe FFT-Chroma braucht
# eine deutlich hoehere Marge als das sauberere HPSS+CQT-Chroma (per
# Parametersweep im Selbsttest kalibriert).
COMPLEXITY_PENALTY_FFT = 0.08
COMPLEXITY_PENALTY_CQT = 0.02

# Bonus, wenn der Akkord-Grundton auch die staerkste Bassnote ist -
# unterscheidet z.B. C von Am7 (gleiche Tonklassen C-E-G-A).
BASS_BONUS = 0.12

# Unterhalb dieses RMS-Pegels gilt das Signal als Stille.
SILENCE_RMS = 1e-4


@dataclass
class ChordResult:
    name: str        # z.B. "G", "Am", "C7" - oder "N" fuer kein Akkord
    confidence: float

    @property
    def is_chord(self) -> bool:
        return self.name != "N"


def _build_templates():
    templates = []
    for root in range(12):
        for suffix, intervals in CHORD_TYPES.items():
            vec = np.zeros(12)
            for k, interval in enumerate(intervals):
                # Grundton leicht staerker gewichten als Terz/Quinte/Septime.
                vec[(root + interval) % 12] = 1.0 if k == 0 else 0.8
            vec /= np.linalg.norm(vec)
            extra_notes = len(intervals) - 3
            templates.append((NOTE_NAMES[root] + suffix, vec, extra_notes, root))
    return templates


_TEMPLATES = _build_templates()


def match_chord(chroma: np.ndarray, bass_chroma: np.ndarray | None = None) -> ChordResult:
    """Findet den Akkord-Template mit der hoechsten Cosinus-Aehnlichkeit.

    Mit `bass_chroma` bekommen Akkorde einen Bonus, deren Grundton im Bass
    tatsaechlich klingt (Grundton-Fehler waren das Hauptproblem der V1).
    """
    norm = np.linalg.norm(chroma)
    if norm < 1e-9:
        return ChordResult("N", 0.0)
    unit = chroma / norm

    bass = None
    if bass_chroma is not None and bass_chroma.max() > 1e-9:
        bass = bass_chroma / bass_chroma.max()

    # Bass-Chroma gibt es nur in der CQT-Pipeline; sie liefert auch das
    # sauberere Chroma und kommt daher mit der kleineren Marge aus.
    penalty_rate = COMPLEXITY_PENALTY_FFT if bass is None else COMPLEXITY_PENALTY_CQT

    best_name, best_score = "N", 0.0
    for name, template, extra_notes, root in _TEMPLATES:
        score = float(np.dot(unit, template)) - penalty_rate * extra_notes
        if bass is not None:
            score += BASS_BONUS * float(bass[root])
        if score > best_score:
            best_name, best_score = name, score

    if best_score < MATCH_THRESHOLD:
        return ChordResult("N", best_score)
    return ChordResult(best_name, best_score)


class ChordSmoother:
    """Mehrheitsentscheid ueber die letzten N Erkennungen gegen Flackern.

    Liefert "?" bis das Fenster gefuellt ist - unterdrueckt Fehlgriffe auf
    Attack-Transienten direkt nach Start oder Stille.
    """

    def __init__(self, window: int = 3):
        self.window = window
        self._history: list[str] = []

    def reset(self):
        self._history.clear()

    def update(self, result: ChordResult) -> str:
        self._history.append(result.name)
        if len(self._history) > self.window:
            self._history.pop(0)
        if len(self._history) < self.window:
            return "?"
        return max(set(self._history), key=self._history.count)

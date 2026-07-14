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

# Hier stand ein BASS_BONUS: Akkorde, deren Grundton die staerkste Bassnote war,
# bekamen 0.12 auf den Score. Er sollte C von Am7 unterscheiden (gleiche
# Tonklassen C-E-G-A) - und tat das, indem er den Grundton auf die Bassnote zog.
# Genau das ist bei jeder UMKEHRUNG falsch: Der Bassist spielt dort einen
# Akkordton, der nicht der Grundton ist. Gemessen (Selbsttest, Gruppe
# "inversions"): Der Bonus machte aus C/E ein Em und aus Bm/D ein D - Namen, die
# Toene versprechen, die im Stueck nicht klingen (das H in Em, das A in D). Wer
# danach greift, spielt daneben.
#
# Die Rechtfertigung des Bonus ist mit der Bassmessung weggefallen. Er sollte
# eine Information ins Matching holen, die dort gar nicht hingehoert: WELCHE Note
# unten liegt. Die messen wir jetzt direkt (bass.py) und schreiben sie in den
# Slash-Namen. Das Chroma darf sich wieder auf das beschraenken, was es kann -
# die Tonklassen-MENGE - und der Bass sagt, welche davon unten liegt.
#
# Der Fall, fuer den der Bonus gebaut war, verliert dabei nichts: C6 und Am7
# bestehen aus DENSELBEN Tonklassen. Faellt die Wahl auf Am7 und liegt ein C
# unten, steht "Am7/C" da - dieselben Toene, dieselbe Bassnote, andere
# Schreibweise. Kein Falschton. Nachgemessen: 0 Falschtoene in der Gruppe
# "ambiguous", mit und ohne Bonus.

# Unterhalb dieses RMS-Pegels gilt das Signal als Stille.
SILENCE_RMS = 1e-4


@dataclass
class ChordResult:
    """Was klingt - als Tonklasse plus Akkordart, nicht als Notenname.

    Die Signalstufe kann gar nicht wissen, ob Tonklasse 10 in diesem Stueck
    "A#" oder "Bb" heisst: das entscheidet die Tonart, und die steht erst nach
    Sekunden fest (siehe tonality.py). `root` ist deshalb die Zahl 0..11, und
    `name` ist eine kanonische ID - immer mit Kreuz geschrieben, damit sie
    stabil vergleichbar ist (Zeitleiste, Onset-Suche, Uebertragung zum
    Browser). `name` ist NICHT die Anzeige. Angezeigt wird, was
    tonality.spell() daraus in der erkannten Tonart macht.
    """

    name: str        # kanonische ID: "G", "Am", "A#m7" - oder "N" (kein Akkord)
    confidence: float
    root: int | None = None   # Tonklasse 0..11, None bei "N"
    quality: str = ""         # "", "m", "7", "maj7", "m7"

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
            templates.append((NOTE_NAMES[root] + suffix, vec, extra_notes, root, suffix))
    return templates


_TEMPLATES = _build_templates()
_TEMPLATE_BY_NAME = {name: vec for name, vec, _, _, _ in _TEMPLATES}


def find_onset_frame(frames: np.ndarray, prev_name: str | None, new_name: str) -> int | None:
    """Frame-Index im Fenster, ab dem `new_name` klingt - oder None.

    Wann ein Akkord einsetzt, laesst sich nicht aus dem Zeitpunkt der Erkennung
    ableiten: die Erkennung braucht erst genug neues Material, um die Pooling-
    Mehrheit zu kippen, und das dauert je nach Signal unterschiedlich lang. Der
    Wechsel wird deshalb im Fenster *gesucht*: gesucht ist der Schnitt k, der
    die Frames am besten in "davor = prev" / "ab hier = new" teilt. Damit liegt
    die Aufloesung beim Frame-Raster (~23 ms) statt beim Analysetakt (~500 ms).
    """
    new_template = _TEMPLATE_BY_NAME.get(new_name)
    if new_template is None or frames is None or frames.shape[1] < 4:
        return None

    unit = frames / (np.linalg.norm(frames, axis=0, keepdims=True) + 1e-9)
    score_new = new_template @ unit

    prev_template = _TEMPLATE_BY_NAME.get(prev_name) if prev_name else None
    if prev_template is not None:
        gain = score_new - prev_template @ unit
    else:
        # Kein Vorgaenger (Programmstart, nach Stille): gegen die Schwelle
        # schneiden statt gegen ein Template. Traegt der Akkord schon das ganze
        # Fenster, wird k=0 - der Einsatz lag vor dem Fenster, frueher koennen
        # wir ihn nicht gesehen haben. Das ist die ehrliche Antwort; ein Schnitt
        # gegen den eigenen Mittelwert wuerde hier einen Wechsel erfinden.
        gain = score_new - MATCH_THRESHOLD

    # k maximiert sum(gain[k:]): ab dort traegt der neue Akkord das Fenster.
    suffix_sums = np.concatenate([np.cumsum(gain[::-1])[::-1], [0.0]])
    return int(np.argmax(suffix_sums))


def match_chord(chroma: np.ndarray, cqt: bool = False) -> ChordResult:
    """Findet den Akkord-Template mit der hoechsten Cosinus-Aehnlichkeit.

    Entscheidet allein ueber die Tonklassen-MENGE. Welche Note davon unten
    liegt, ist eine andere Frage und wird anderswo beantwortet - gemessen im
    Tiefband (bass.py), nicht aus dem Akkord erraten. Solange die Bassnote hier
    mitzureden hatte, riss sie den Grundton bei jeder Umkehrung an sich (siehe
    den Block oben, wo der BASS_BONUS stand).

    `cqt` sagt, ob das sauberere librosa-Chroma vorliegt - dann genuegt die
    kleinere Komplexitaetsmarge.
    """
    norm = np.linalg.norm(chroma)
    if norm < 1e-9:
        return ChordResult("N", 0.0)
    unit = chroma / norm

    penalty_rate = COMPLEXITY_PENALTY_CQT if cqt else COMPLEXITY_PENALTY_FFT

    best = None
    best_score = 0.0
    for name, template, extra_notes, root, suffix in _TEMPLATES:
        score = float(np.dot(unit, template)) - penalty_rate * extra_notes
        if score > best_score:
            best, best_score = (name, root, suffix), score

    if best is None or best_score < MATCH_THRESHOLD:
        return ChordResult("N", best_score)
    name, root, suffix = best
    return ChordResult(name, best_score, root=root, quality=suffix)


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

        best = max(self._history, key=self._history.count)
        # Ohne echte Mehrheit nicht raten. Ein `max(set(...))` lieferte hier je
        # nach Hash-Seed einen beliebigen der Kandidaten - und ein solcher
        # Phantomakkord erzeugt in der Zeitleiste ein Segment mit erfundenem
        # Onset, das die nachfolgenden echten Onsets mitverschiebt. "?" heisst
        # "unsicher": der Aufrufer behaelt den letzten stabilen Akkord bei.
        if self._history.count(best) * 2 <= self.window:
            return "?"
        return best

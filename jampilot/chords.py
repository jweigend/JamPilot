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

# Die grosse Terz (Intervall 4) erzeugt ihren 3. Teilton eine Oktave+Quinte
# hoeher - das faellt auf die grosse Septime (4 + 7 = 11). Dadurch trug schon ein
# reiner Dur-Dreiklang UND ein Dominantseptakkord Scheinenergie auf der maj7-Note,
# und das maj7-Template gewann: aus jedem Dur wurde ein "maj7", aus jedem "7" ein
# "maj7". Der Dominant-b7 (Intervall 10) entsteht aus KEINEM Terzoberton - die
# Verwechslung war deshalb einseitig (7 -> maj7, nie umgekehrt).
#
# Gegenmittel: diese erwartete Scheinenergie in die Dur-Terz-Templates ("" und
# "7") einbauen. Sie "erklaeren" ihren eigenen Oberton auf 11 selbst und werden
# nicht mehr vom maj7 geschlagen - ein ECHTES maj7 (mit starkem, gespieltem 11)
# gewinnt weiterhin. Wert per Sweep ueber vier Real-Aufnahmen kalibriert (Sting -
# If I Ever Lose My Faith, Steely Dan - Peg, Misty x2): der maj7-Anteil faellt von
# ~40% auf ~20%, dom7 steigt, und die Grundtoene bleiben zu >=95% unveraendert -
# der Fix korrigiert die Qualitaet, nicht den Grundton.
#
# Fuer die Moll-Terz (deren Oberton auf 10 = b7 faellt, m -> m7) wird das BEWUSST
# NICHT gemacht: dieselbe Korrektur fraesse dort echte m7-Akkorde weg, die in
# Jazz-Material (Misty: Fm7, Cm7, Bbm7 ...) haeufig und richtig sind. Der
# dokumentierte Bias war der maj7, nicht der m7.
THIRD_OVERTONE = 0.28

# Unterhalb dieses RMS-Pegels gilt das Signal als Stille.
SILENCE_RMS = 1e-4


@dataclass
class ChordCandidate:
    """Eine Audio-Hypothese, bevor musikalischer Kontext sie bewertet."""

    name: str
    score: float
    root: int
    quality: str


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
    candidates: tuple[ChordCandidate, ...] = ()

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
            # Obertonerwartung der grossen Terz auf der maj7-Note (siehe
            # THIRD_OVERTONE) - nur wo die 11 nicht ohnehin Akkordton ist, also
            # bei Dur und Dominantsept, nicht bei maj7 selbst.
            if 4 in intervals:
                idx = (root + 11) % 12
                if vec[idx] == 0.0:
                    vec[idx] = THIRD_OVERTONE
            vec /= np.linalg.norm(vec)
            extra_notes = len(intervals) - 3
            templates.append((NOTE_NAMES[root] + suffix, vec, extra_notes, root, suffix))
    return templates


_TEMPLATES = _build_templates()
_TEMPLATE_BY_NAME = {name: vec for name, vec, _, _, _ in _TEMPLATES}


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

    candidates = []
    for name, template, extra_notes, root, suffix in _TEMPLATES:
        score = float(np.dot(unit, template)) - penalty_rate * extra_notes
        candidates.append(ChordCandidate(name, score, root, suffix))

    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    best = candidates[0]
    # Mehrere plausible Antworten bleiben erhalten. Erst dadurch kann eine
    # spaetere harmonische Stufe eine knappe Fehlentscheidung korrigieren,
    # ohne das Audiosignal ein zweites Mal analysieren zu muessen.
    plausible = tuple(candidates[:5])

    if best.score < MATCH_THRESHOLD:
        return ChordResult("N", best.score, candidates=plausible)
    return ChordResult(best.name, best.score, root=best.root,
                       quality=best.quality, candidates=plausible)

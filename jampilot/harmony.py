"""Musikalischen Kontext auf die Audio-Hypothesen anwenden.

Der Matcher in :mod:`chords` beantwortet absichtlich nur die Signalfrage:
welches Template passt zu den gemessenen Tonklassen? Hier folgt die fuer einen
Spieler wichtigere Frage: Welche der fast gleich guten Lesarten ist in der
laufenden Tonart sinnvoll? Die Tonart ist ein weicher Prior, kein Verbot -- ein
klar gemessener chromatischer Akkord muss weiterhin gewinnen koennen.
"""

from .chords import CHORD_TYPES, ChordCandidate, ChordResult
from .tonality import Key

# Maximale Korrektur durch den Kontext. Liegt eine Alternative im Audioscore
# weiter zurueck, bleibt der rohe Gewinner stehen. Das schuetzt Modulationen,
# Borrowed Chords und andere echte chromatische Harmonik.
KEY_PENALTY_PER_FOREIGN_TONE = 0.055
MAX_AUDIO_DISTANCE = 0.09
# Enger als die Interpretationsgrenze: Jede fast gleich gute Lesart muss einen
# Ton tragen, bevor wir dem Gitarristen empfehlen, ihn wirklich mitzuspielen.
SAFE_AUDIO_DISTANCE = 0.05

_MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
_MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10)


def _foreign_tones(candidate: ChordCandidate, key: Key) -> int:
    scale = _MINOR_SCALE if key.minor else _MAJOR_SCALE
    allowed = {(key.tonic + interval) % 12 for interval in scale}

    # Die Dur-/Dominantform der V. Stufe gehoert zur funktionalen Mollharmonik:
    # in a-Moll ist E bzw. E7 mit G# kein Fehler, obwohl G# nicht in
    # natuerlich Moll liegt.
    dominant = (key.tonic + 7) % 12
    if key.minor and candidate.root == dominant and candidate.quality in ("", "7"):
        return 0

    return sum((candidate.root + interval) % 12 not in allowed
               for interval in CHORD_TYPES[candidate.quality])


def interpret_chord(result: ChordResult, key: Key | None) -> ChordResult:
    """Waehlt unter nahen Audio-Hypothesen die tonal plausibelste Lesart.

    Ohne stabile Tonart oder Kandidaten bleibt das Matchergebnis exakt
    unveraendert. Kontext darf nur Kandidaten innerhalb ``MAX_AUDIO_DISTANCE``
    betrachten und kann daher starke akustische Evidenz nie ueberstimmen.
    """
    if key is None or not result.is_chord or not result.candidates:
        return result

    # Der bestehende Detektor trifft die Grundtoene deutlich verlaesslicher als
    # die Akkordqualitaet. Diese erste Ausbaustufe korrigiert deshalb nur die
    # Lesart desselben Grundtons (A <-> Am, 7 <-> maj7), niemals die harmonische
    # Landkarte selbst. Grundtonkorrekturen brauchen Progressions-/Basskontext.
    near = [candidate for candidate in result.candidates
            if candidate.root == result.root
            and result.confidence - candidate.score <= MAX_AUDIO_DISTANCE]
    if not near:
        return result

    def contextual_score(candidate: ChordCandidate) -> float:
        # Bei unsicherer Tonart schrumpft der Prior automatisch. Die
        # Korrelation kann in der Praxis auch leicht negativ sein.
        strength = max(0.0, min(1.0, key.confidence))
        return (candidate.score
                - strength * KEY_PENALTY_PER_FOREIGN_TONE
                * _foreign_tones(candidate, key))

    chosen = max(near, key=contextual_score)
    if chosen.name == result.name:
        return result
    return ChordResult(chosen.name, chosen.score, root=chosen.root,
                       quality=chosen.quality, candidates=result.candidates)


def safe_pitch_classes(result: ChordResult) -> tuple[int, ...]:
    """Tonklassen, die alle nahen Lesarten desselben Grundtons gemeinsam haben.

    A gegen Am ergibt dadurch A+E; A7 gegen A ergibt den Dur-Dreiklang. Ist die
    Audioevidenz eindeutig, bleibt der vollstaendige erkannte Akkord erhalten.
    """
    if not result.is_chord or result.root is None:
        return ()
    plausible = [candidate for candidate in result.candidates
                 if candidate.root == result.root
                 and result.confidence - candidate.score <= SAFE_AUDIO_DISTANCE]
    if not plausible:
        plausible = [ChordCandidate(result.name, result.confidence,
                                     result.root, result.quality)]

    sets = [{(candidate.root + interval) % 12
             for interval in CHORD_TYPES[candidate.quality]}
            for candidate in plausible]
    common = set.intersection(*sets)
    # Musikalische Reihenfolge relativ zum Grundton, stabil fuer Payload/Tests.
    return tuple(sorted(common, key=lambda pc: (pc - result.root) % 12))

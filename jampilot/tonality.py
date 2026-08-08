"""Tonart-Erkennung - und daraus die Schreibweise: Kreuz oder b.

Die Akkorderkennung liefert Tonklassen, keine Notennamen. Tonklasse 10 ist
"A#" ODER "Bb" - beides ist derselbe Klang, aber nur eine der beiden
Schreibweisen ist im jeweiligen Stueck richtig: in D-Dur steht ein A#, in
F-Dur ein Bb. Welche gemeint ist, entscheidet die Tonart, und die steht nicht
im einzelnen Akkord, sondern erst in dem, was ueber laengere Zeit klingt.

Deshalb wird hier ueber viele Analysefenster ein Tonklassen-Histogramm
gesammelt und nach Krumhansl-Schmuckler gegen die 24 Dur-/Moll-Profile
korreliert. Vor MIN_KEY_SECONDS an Musik gibt es bewusst KEINE Antwort:
ein Histogramm aus zwei Akkorden korreliert mit einem halben Dutzend Tonarten
gleich gut, und eine geratene Tonart waere schlimmer als gar keine - sie
schriebe die Akkorde falsch und wechselte die Schreibweise mitten im Stueck.
Bis dahin gelten Kreuze (die Vorgabe ohne Vorzeichen).
"""

from dataclasses import dataclass

import numpy as np

from .chroma import NOTE_NAMES

# Empirische Tonhoehen-Profile (Krumhansl/Kessler): wie stark jede Stufe in
# einer Dur- bzw. Moll-Tonart gewichtet ist, gemessen an Hoererurteilen.
# Index 0 ist der Grundton, 1 die kleine Sekunde usw.
MAJOR_PROFILE = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

# So viel Musik (nicht Wanduhr-Zeit - Stille zaehlt nicht) muss gehoert sein,
# bevor eine Tonart gemeldet wird.
MIN_KEY_SECONDS = 12.0

# Halbwertszeit des Histogramms: das Stueck darf modulieren, ohne dass der
# Anfang die Tonart auf ewig festnagelt.
KEY_HALF_LIFE = 30.0

# Eine schon gemeldete Tonart wird nur abgeloest, wenn die neue DEUTLICH besser
# passt. Ohne diese Schwelle springt die Erkennung zwischen verwandten Tonarten
# (C-Dur/a-Moll, F-Dur/d-Moll) hin und her - und mit ihr die Schreibweise:
# derselbe Akkord hiesse abwechselnd A# und Bb. Lieber traege als flatternd.
SWITCH_MARGIN = 0.05

# So lange muss eine NEUE Schreibweise durchhalten, bevor sie die alte abloest -
# gemessen in klingender Musik, nicht in Wanduhr-Zeit.
#
# Warum ueberhaupt eine zweite Traegheit, wo SWITCH_MARGIN doch schon bremst:
# Die Tonart darf und soll dem Stueck folgen, denn an ihr haengt der
# Akkord-Prior. Die Schreibweise ist das genaue Gegenteil - sie ist reine
# Anzeige, und sie wird RUECKWIRKEND angewandt: Der Browser schreibt bei jeder
# Aenderung die ganze Zeitleiste neu. Aus G# wird dann auch dort ein Ab, wo der
# Ton schon gespielt ist. Wer mitspielt, liest also mitten im Griff einen neuen
# Namen fuer denselben Bund - beim Bass, wo genau ein Ton dasteht, faellt das
# am haertesten auf.
#
# Die Groesse ist bewusst MIN_KEY_SECONDS: Ein Wechsel der Schreibweise soll
# mindestens so gut belegt sein wie die erste Tonart ueberhaupt. Eine echte
# Modulation haelt das aus (sie kommt dann eben eine Viertelminute spaeter an,
# und einmal statt fuenfmal), ein wanderndes Histogramm nicht.
ACCIDENTAL_SETTLE = MIN_KEY_SECONDS

SHARP = "sharp"
FLAT = "flat"

# Zu jeder Tonklasse mit Vorzeichen die b-Schreibweise. Die Kreuz-Schreibweise
# ist NOTE_NAMES selbst - sie ist die kanonische Form im ganzen Programm.
FLAT_NAMES = {"C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb"}

# Dur-Tonarten, deren Vorzeichen Kreuze sind (Quintenzirkel im Uhrzeigersinn:
# C G D A E B F#). Alles andere - F Bb Eb Ab Db - hat b-Vorzeichen. Moll erbt
# das Vorzeichen seiner Paralleltonart, siehe `accidental_for_key`.
_SHARP_MAJOR_TONICS = {0, 2, 4, 6, 7, 9, 11}


def accidental_for_key(tonic: int, minor: bool) -> str:
    """SHARP oder FLAT fuer die Tonart mit Grundton `tonic` (0=C..11=B)."""
    # a-Moll schreibt sich wie C-Dur, d-Moll wie F-Dur: die Paralleltonart
    # liegt eine kleine Terz hoeher und traegt dieselben Vorzeichen.
    relative_major = (tonic + 3) % 12 if minor else tonic % 12
    return SHARP if relative_major in _SHARP_MAJOR_TONICS else FLAT


def spell(name: str, accidental: str) -> str:
    """Akkordnamen in der gewuenschten Schreibweise.

    Erwartet die kanonische Kreuz-Form ("A#m7") und liefert bei FLAT die
    b-Form ("Bbm7"). Nicht-Akkorde ("N", "-", "?") gehen unveraendert durch.

    Ein Slash-Akkord traegt ZWEI Notennamen ("C#/A#"), und beide muessen
    umgeschrieben werden - sonst stuende in F-Dur ein halb richtiges "Db/A#" da.
    """
    if "/" in name:
        return "/".join(spell(teil, accidental) for teil in name.split("/"))
    if accidental != FLAT or len(name) < 2 or name[1] != "#":
        return name
    return FLAT_NAMES[name[:2]] + name[2:]


@dataclass(frozen=True)
class Key:
    tonic: int          # Tonklasse des Grundtons, 0=C .. 11=B
    minor: bool
    confidence: float   # Korrelation mit dem Profil, 0..1

    @property
    def accidental(self) -> str:
        return accidental_for_key(self.tonic, self.minor)

    @property
    def tonic_name(self) -> str:
        """Grundton in der Schreibweise der eigenen Tonart: Bb-Moll, nie A#-Moll."""
        return spell(NOTE_NAMES[self.tonic], self.accidental)

    def label_in(self, accidental: str) -> str:
        """Label in einer VORGEGEBENEN Schreibweise.

        Solange die Schreibweise noch nachzieht (ACCIDENTAL_SETTLE), muss das
        Label mitgehen: "Db major" ueber lauter Akkorden mit Kreuzen sieht wie
        ein Fehler aus, obwohl C# und Db derselbe Ton sind.
        """
        return (f"{spell(NOTE_NAMES[self.tonic], accidental)} "
                f"{'minor' if self.minor else 'major'}")

    @property
    def label(self) -> str:
        return self.label_in(self.accidental)

    def as_dict(self, accidental: str | None = None) -> dict:
        # Was der Browser braucht: den Grundton kanonisch (er schreibt selbst),
        # die Tonart-Vorzeichen (fuer den Automatik-Modus) und das Label.
        acc = accidental or self.accidental
        return {
            "tonic": NOTE_NAMES[self.tonic],
            "minor": self.minor,
            "acc": acc,
            "label": self.label_in(acc),
        }


def _profile_matrix() -> np.ndarray:
    """Die 24 Tonarten als zentrierte Einheitsvektoren (Zeile = Tonart).

    Zentriert und normiert, damit ein Skalarprodukt gegen ein ebenso
    aufbereitetes Histogramm direkt die Pearson-Korrelation ist.
    """
    rows = []
    for minor in (False, True):
        profile = MINOR_PROFILE if minor else MAJOR_PROFILE
        for tonic in range(12):
            # Profilstufe s beschreibt die Tonklasse (tonic + s): rollen.
            rotated = np.roll(profile, tonic)
            centered = rotated - rotated.mean()
            rows.append(centered / np.linalg.norm(centered))
    return np.array(rows)


_PROFILES = _profile_matrix()


def correlate(histogram: np.ndarray) -> np.ndarray:
    """Korrelation des Tonklassen-Histogramms mit allen 24 Tonarten.

    Reihenfolge wie `_profile_matrix`: erst 12x Dur (C..B), dann 12x Moll.
    """
    centered = histogram - histogram.mean()
    norm = np.linalg.norm(centered)
    if norm < 1e-9:
        return np.zeros(24)
    return _PROFILES @ (centered / norm)


class KeyEstimator:
    """Sammelt Chroma ueber die Zeit und leitet daraus die Tonart ab.

    `hop_seconds` ist der Abstand zwischen zwei `add`-Aufrufen; daraus ergibt
    sich, wie viel Musik gehoert wurde und wie schnell Altes verfaellt. Mit
    `half_life=None` verfaellt nichts - das ist der Offline-Fall, in dem eine
    ganze Datei zu EINER Tonart ausgewertet wird.
    """

    def __init__(self, hop_seconds: float, half_life: float | None = KEY_HALF_LIFE):
        self._hop = hop_seconds
        self._decay = 1.0 if half_life is None else 0.5 ** (hop_seconds / half_life)
        self._histogram = np.zeros(12)
        self._heard = 0.0
        self._key: Key | None = None
        self._accidental: str | None = None     # None = noch nie festgelegt
        self._pending: str | None = None        # Schreibweise, die gerade anklopft
        self._pending_seconds = 0.0

    @property
    def heard_seconds(self) -> float:
        """Wie viel *klingende* Musik bisher eingegangen ist."""
        return self._heard

    @property
    def key(self) -> Key | None:
        """Die erkannte Tonart - oder None, solange zu wenig Musik da war."""
        return self._key

    @property
    def accidental(self) -> str:
        """Die Schreibweise fuer die ANZEIGE - traeger als die Tonart.

        Nicht `key.accidental` benutzen, wo etwas dargestellt wird: Das ist die
        Schreibweise der gerade besten Tonart, und die darf wandern. Diese hier
        wandert erst, wenn die neue sich ACCIDENTAL_SETTLE lang durchgesetzt hat.
        """
        return self._accidental or SHARP

    def add(self, chroma: np.ndarray):
        """Ein Analysefenster einbringen. Nur mit klingendem Chroma aufrufen -
        Stille traegt nichts zur Tonart bei und wuerde nur die Uhr weiterdrehen."""
        total = float(chroma.sum())
        if total < 1e-9:
            return
        # Jedes Fenster zaehlt gleich viel, egal wie laut es war.
        self._histogram = self._histogram * self._decay + chroma / total
        self._heard += self._hop
        self._update()

    def _update(self):
        if self._heard < MIN_KEY_SECONDS:
            return

        scores = correlate(self._histogram)
        ranked = scores.copy()
        if self._key is not None:
            # Amtsbonus fuer die laufende Tonart - siehe SWITCH_MARGIN.
            ranked[self._key.tonic + (12 if self._key.minor else 0)] += SWITCH_MARGIN

        best = int(np.argmax(ranked))
        # Gemeldet wird die ungeschoente Korrelation, nicht die mit Bonus.
        self._key = Key(tonic=best % 12, minor=best >= 12,
                        confidence=float(scores[best]))
        self._settle_accidental(self._key.accidental)

    def _settle_accidental(self, wanted: str):
        """Die Schreibweise nachziehen - aber erst nach ACCIDENTAL_SETTLE.

        Die ERSTE gilt sofort: Bis hierhin gab es ueberhaupt keine Tonart, und
        bis dahin galten Kreuze als Vorgabe. Sie noch einmal zu verzoegern
        verschoebe den einen unvermeidlichen Wechsel nur nach hinten.
        """
        if self._accidental is None or wanted == self._accidental:
            self._accidental = self._accidental or wanted
            self._pending, self._pending_seconds = None, 0.0
            return

        if wanted != self._pending:
            self._pending, self._pending_seconds = wanted, 0.0
        # Zeit zaehlt in klingender Musik: Eine Pause soll den Wechsel nicht
        # aussitzen, sondern anhalten - sonst kippt die Schreibweise nach einer
        # langen Stille auf Material, das laengst nicht mehr laeuft.
        self._pending_seconds += self._hop
        if self._pending_seconds >= ACCIDENTAL_SETTLE:
            self._accidental = wanted
            self._pending, self._pending_seconds = None, 0.0


def estimate_key(chromas, hop_seconds: float = 1.0) -> Key | None:
    """Tonart eines kompletten Materials (Offline-Auswertung, kein Verfall)."""
    estimator = KeyEstimator(hop_seconds, half_life=None)
    for chroma in chromas:
        estimator.add(chroma)
    return estimator.key

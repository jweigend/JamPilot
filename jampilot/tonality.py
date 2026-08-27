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

# --- Zwei-Skalen-Betrieb (Live-Pfad) ----------------------------------------
# Ein einzelner Zeithorizont ist lose-lose, gemessen an 9 Realaudio-Tracks
# (tests/realaudio/REPORT_key_window.md): kurz (30 s) springt die Tonika
# 27-mal und verpasst trotzdem Modulationen, lang ist ruhig, braucht fuer
# einen Halbton-Wechsel aber Minuten - oder sieht ihn nie. Deshalb zwei
# Histogramme: das lange bestimmt die Tonart, das kurze detektiert nur.

# Das lange Histogramm. 120 s druecken die Tonika-Spruenge von 27 auf 4;
# 240 s und mehr bringen nichts zusaetzlich.
KEY_LONG_HALF_LIFE = 120.0

# Das kurze Detektor-Histogramm. 10 s waren zu nervoes (Fehl-Resets auf
# Ambiguitaeten), 25 s tragen genug Kontext fuer eine belastbare Korrelation.
KEY_DETECT_HALF_LIFE = 25.0

# Reset nur, wenn der Herausforderer im Kurzfenster DEUTLICH besser
# korreliert als die amtierende Tonika (inkl. deren Parallel-Lesart). Der
# grosse Vorsprung ist der Diskriminator: Nach echter Modulation korreliert
# die neue Tonart ~0.9 gegen ~0.3 der alten; blosse Ambiguitaet
# (Parallel-Moll, mixolydische Strophen) kommt nicht ueber ~0.15.
KEY_DETECT_MARGIN = 0.20

# ... und erst, wenn DIESELBE fremde Tonika so lange durchhaelt - gemessen
# in klingender Musik. Eine echte Modulation traegt den Rest des Stuecks,
# die kann das warten; ein Zwischenteil kann es nicht.
KEY_DETECT_SUSTAIN = 15.0

# --- Stille-Reset (Songwechsel) ---------------------------------------------
# Der Estimator lebt pro Session, nicht pro Song. Die Luecke zwischen zwei
# Playlist-Titeln ist das Signal, die Statistik ehrlich neu zu beginnen -
# sonst zeigt das lange Histogramm minutenlang die Tonart des vorigen Stuecks.
SILENCE_RESET_SECONDS = 2.0

# Quasi-Stille: unter diesem absoluten Boden (digitale Stille liegt bei
# ~1.4e-4 Chroma-Summe, Musik bei 17-150) ODER unter 1 % des mitlaufenden
# Referenzpegels. Kalibriert an den 9 Referenztracks: feuert dort nur in der
# Schlussstille, nie mitten im Song (REPORT_key_window.md).
SILENCE_ABS_FLOOR = 0.05
SILENCE_REL_FLOOR = 0.01
SILENCE_LEVEL_HALF_LIFE = 60.0

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

# --- Geschlechts-Votum aus den Akkordlabels ---------------------------------
# Das Chroma waehlt die TONIKA am besten, verwechselt aber Dur und Moll, wenn
# die Terz im Klangbild schwach ist (terzlose Voicings, dorische Faerbung).
# Die Akkordlabels des Modells sind dort der bessere Zeuge: Gemessen kippt
# das Votum kein Dur-Stueck, repariert aber zwei Moll-Faelle von 0 auf
# ~100 % (tests/realaudio/REPORT_key_labels.md, Nachtrag 2026-08-27). Es
# entscheidet NUR ueber Dur/Moll der gewaehlten Tonika - die Tonika-Wahl
# selbst bleibt beim Chroma (der volle Label-Hybrid ist gemessen und
# verworfen, siehe derselbe Report).
MODE_HALF_LIFE = 120.0
# Unter so vielen Frame-Stimmen entscheidet weiter das Chroma allein.
MODE_MIN_FRAMES = 3.0

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
        self._mode_decay = (1.0 if half_life is None
                            else 0.5 ** (hop_seconds / MODE_HALF_LIFE))
        self._mode_hist = np.zeros((12, 2))   # je Tonika: [Dur-, Moll-Stimmen]
        self._heard = 0.0
        self._key: Key | None = None
        self._accidental: str | None = None     # None = noch nie festgelegt
        self._fallback = SHARP                  # Anzeige, solange keine feststeht
        self._pending: str | None = None        # Schreibweise, die gerade anklopft
        self._pending_seconds = 0.0

    @property
    def heard_seconds(self) -> float:
        """Wie viel *klingende* Musik bisher eingegangen ist."""
        return self._heard

    @property
    def key(self) -> Key | None:
        """Die erkannte Tonart - oder None, solange zu wenig Musik da war.

        Das Geschlecht kommt aus dem Label-Votum, sobald genug Stimmen fuer
        die gewaehlte Tonika vorliegen (add_mode_votes) - intern rechnet die
        Tonika-Wahl weiter mit dem reinen Chroma-Urteil.
        """
        return self._voted(self._key)

    def _voted(self, key: Key | None) -> Key | None:
        if key is None:
            return None
        dur, moll = self._mode_hist[key.tonic]
        # bool(): numpy.bool_ wuerde bis in key.as_dict() durchsickern und
        # dort json.dumps zum Absturz bringen.
        voted = bool(moll > dur)
        if dur + moll < MODE_MIN_FRAMES or voted == key.minor:
            return key
        return Key(tonic=key.tonic, minor=voted, confidence=key.confidence)

    @property
    def accidental(self) -> str:
        """Die Schreibweise fuer die ANZEIGE - traeger als die Tonart.

        Nicht `key.accidental` benutzen, wo etwas dargestellt wird: Das ist die
        Schreibweise der gerade besten Tonart, und die darf wandern. Diese hier
        wandert erst, wenn die neue sich ACCIDENTAL_SETTLE lang durchgesetzt hat.
        """
        return self._accidental or self._fallback

    def reset(self):
        """Alles Gehoerte vergessen - der Songwechsel (Stille-Reset).

        Zurueck auf den Startzustand: keine Tonart, bis das neue Stueck
        MIN_KEY_SECONDS geliefert hat. Nur die Schreibweise bleibt als
        Anzeige-Fallback stehen - die noch sichtbare alte Zeitleiste soll
        nicht grundlos auf Kreuze zurueckkippen. Die erste Tonart des neuen
        Stuecks legt sie dann sofort neu fest (wie beim Programmstart).
        """
        self._fallback = self._accidental or self._fallback
        self._histogram = np.zeros(12)
        self._mode_hist = np.zeros((12, 2))
        self._heard = 0.0
        self._key = None
        self._accidental = None
        self._pending, self._pending_seconds = None, 0.0

    def adopt(self, histogram: np.ndarray):
        """Das Histogramm hart ersetzen und die Tonart neu bestimmen.

        Fuer den Modulations-Reset des Zwei-Skalen-Estimators: Das Stueck ist
        nachweislich woanders angekommen, die alte Statistik zaehlt nicht mehr.
        Anders als `reset` bleibt die Tonart lueckenlos gemeldet - es IST ja
        eine da, nur eben die aus dem uebergebenen (kurzen) Material.
        """
        self._histogram = histogram.copy()
        self._update()

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

    def add_mode_votes(self, votes: np.ndarray):
        """Dur/Moll-Stimmen je Grundton (12x2) aus den Akkordlabels.

        Ein Aufruf pro Hop (btc.label_mode_votes der neuen Frames). Die
        Stimmen entscheiden ausschliesslich das GESCHLECHT der vom Chroma
        gewaehlten Tonika - siehe MODE_HALF_LIFE.
        """
        self._mode_hist = self._mode_hist * self._mode_decay + votes

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
        # Die Schreibweise folgt dem GEMELDETEN Geschlecht: g-Moll schreibt
        # mit b, auch wenn das Chroma intern G-Dur (Kreuze) sieht.
        self._settle_accidental(self._voted(self._key).accidental)

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


class TwoScaleKeyEstimator:
    """Tonart auf zwei Zeitskalen: ruhig UND modulationsfaehig.

    Schnittstelle wie KeyEstimator (add/key/accidental/heard_seconds), gedacht
    fuer den Live-Pfad, wo an der Tonart die Anzeige haengt (Badge,
    Schreibweise, Nashville-Stufen - Letztere schreibt jeder Tonika-Sprung
    komplett um). Messwerte und Herleitung: tests/realaudio/REPORT_key_window.md.

     - Das LANGE Histogramm (KEY_LONG_HALF_LIFE) bestimmt die Tonart.
     - Das KURZE (KEY_DETECT_HALF_LIFE) detektiert nur: Haelt dort dieselbe
       fremde Tonika KEY_DETECT_SUSTAIN Sekunden lang KEY_DETECT_MARGIN
       Korrelationsvorsprung vor der amtierenden, uebernimmt es das lange
       Histogramm - das Stueck hat moduliert (typisch: Pop, Halbton rauf).
     - Quasi-Stille ueber SILENCE_RESET_SECONDS ist ein Songwechsel:
       kompletter Reset, ehrlich zurueck auf "keine Tonart", statt
       minutenlang die Tonart des vorigen Titels zu zeigen.
    """

    def __init__(self, hop_seconds: float):
        self._main = KeyEstimator(hop_seconds, half_life=KEY_LONG_HALF_LIFE)
        self._hop = hop_seconds
        self._short = np.zeros(12)
        self._short_decay = 0.5 ** (hop_seconds / KEY_DETECT_HALF_LIFE)
        self._level_decay = 0.5 ** (hop_seconds / SILENCE_LEVEL_HALF_LIFE)
        self._level = 0.0                  # mitlaufender Referenzpegel
        self._silence_seconds = 0.0
        self._challenger: int | None = None    # Tonika, die gerade anklopft
        self._challenger_seconds = 0.0

    @property
    def key(self) -> Key | None:
        return self._main.key

    @property
    def accidental(self) -> str:
        return self._main.accidental

    @property
    def heard_seconds(self) -> float:
        return self._main.heard_seconds

    def add(self, chroma: np.ndarray):
        """Ein Analysefenster einbringen - anders als beim rohen KeyEstimator
        AUCH in Stille: Der Live-Pfad ruft jeden Hop, und genau die Stille
        traegt hier Information (Songwechsel)."""
        total = float(chroma.sum())
        self._level = max(self._level * self._level_decay, total)
        if total < max(SILENCE_ABS_FLOOR, SILENCE_REL_FLOOR * self._level):
            self._silence_seconds += self._hop
            # heard_seconds > 0 statt eines Feuer-Flags: Nach dem Reset ist
            # nichts mehr gehoert, die anhaltende Stille feuert also nur
            # einmal - und auch ein tonartloser Anspiel-Fetzen vor der Luecke
            # zaehlt nicht ins naechste Stueck hinein.
            if (self._silence_seconds >= SILENCE_RESET_SECONDS
                    and self._main.heard_seconds > 0.0):
                self._main.reset()
                self._short = np.zeros(12)
                self._challenger, self._challenger_seconds = None, 0.0
            return
        self._silence_seconds = 0.0
        self._short = self._short * self._short_decay + chroma / total
        self._main.add(chroma)
        self._detect_modulation()

    def add_mode_votes(self, votes: np.ndarray):
        """Geschlechts-Stimmen durchreichen; der Stille-Reset des
        Haupt-Estimators leert auch dieses Histogramm."""
        self._main.add_mode_votes(votes)

    def _detect_modulation(self):
        key = self._main.key
        if key is None:
            self._challenger, self._challenger_seconds = None, 0.0
            return
        scores = correlate(self._short)
        best = int(np.argmax(scores))
        best_tonic = best % 12
        # Die Parallel-Lesart verteidigt das Amt mit: C-Dur soll nicht
        # fallen, nur weil das Kurzfenster gerade a-Moll besser findet -
        # fuer die Stufen (und die Schreibweise) ist das dieselbe Welt.
        incumbent = max(scores[key.tonic], scores[key.tonic + 12])
        if best_tonic == key.tonic or scores[best] - incumbent <= KEY_DETECT_MARGIN:
            self._challenger, self._challenger_seconds = None, 0.0
            return
        if best_tonic != self._challenger:
            self._challenger, self._challenger_seconds = best_tonic, 0.0
        self._challenger_seconds += self._hop
        if self._challenger_seconds >= KEY_DETECT_SUSTAIN:
            self._main.adopt(self._short)
            self._challenger, self._challenger_seconds = None, 0.0


def estimate_key(chromas, hop_seconds: float = 1.0) -> Key | None:
    """Tonart eines kompletten Materials (Offline-Auswertung, kein Verfall)."""
    estimator = KeyEstimator(hop_seconds, half_life=None)
    for chroma in chromas:
        estimator.add(chroma)
    return estimator.key

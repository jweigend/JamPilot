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
# wird nichts angezeigt statt geraten.
MIN_DOMINANCE = 1.25

# Darunter klingt im Tiefband nichts.
BASS_SILENCE = 1e-6

# Ein SLASH wird nur angezeigt, wenn der gemessene Ton den Grundton im Tiefband
# um diesen Faktor schlaegt. Bei einer echten Umkehrung fehlt der Grundton
# unten gerade - bei Grundton-Bass gewinnt sonst gern die (laute) Quinte die
# Mehrheit und die Anzeige erfaende ein "C/G". Gegen die Isophonics-Slash-
# Annotationen kalibriert: mit 2,0 auf der alten Faltung falsche Slashes
# 8%->2% bei 13/27 Umkehrungen. Seit die Faltung nur die Notenbins nimmt
# (btc.fold_bass_chroma, 2026-09-12) kommt viel oefter ueberhaupt ein Ton
# durch, und 2,0 liess live die Quinte als Slash durch (32 falsche auf 5
# Titeln); 3,0: offline 0,3 % falsche Slashes bei 11/27 Umkehrungen, live
# 17 falsche bei doppelt so vielen gesetzten Baessen (README, Bass-Abschnitt).
SLASH_ROOT_RATIO = 3.0


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

    Die Frames fallen ohnehin an; hier werden
    sie aufgehoben, damit sich die Bassnote jedem Segment der Zeitleiste
    zuordnen laesst - auch einem, das noch niemand gehoert hat. Der Vorlauf gilt
    fuer den Bass genauso wie fuer den Akkord.
    """

    EDGE = 6   # die Randframes verfaelscht das CQT-Padding

    def __init__(self, seconds: float, frame_seconds: float | None = None,
                 edge: int | None = None):
        # Default ist das 23-ms-Raster der Chroma-Pipeline. Der BTC-Pfad liefert
        # 93-ms-Frames und uebergibt sein Raster explizit - dort schrumpft auch
        # der Randbeschnitt (EDGE zaehlt Frames, nicht Sekunden).
        if frame_seconds is None:
            from .chroma import FRAME_SECONDS
            frame_seconds = FRAME_SECONDS
        if edge is not None:
            self.EDGE = edge
        self._frame_seconds = frame_seconds
        self.size = max(int(seconds / frame_seconds), 1)
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

    def pooled_between(self, start: float, end: float) -> np.ndarray | None:
        """Aufsummiertes Tiefband-Chroma (12,) im Intervall - oder None."""
        von = max(int(round(start / self._frame_seconds)), self.end - self.size)
        bis = min(int(round(end / self._frame_seconds)), self.end)
        if bis - von < 2:
            return None
        index = np.arange(von, bis) % self.size
        return self._data[:, index].sum(axis=1)

    @property
    def frame_seconds(self) -> float:
        return self._frame_seconds

    def note_between(self, start: float, end: float) -> int | None:
        """Die vorherrschende Bass-Tonklasse im Intervall - oder None."""
        return dominant(self.pooled_between(start, end))

    def frames_between(self, start: float, end: float) -> tuple[np.ndarray, float] | None:
        """Die einzelnen Tiefband-Frames (12 x F) im Intervall und die
        Stream-Sekunde des ersten - oder None. Fuer passing_note, das den
        VERLAUF innerhalb eines Segments braucht, nicht seine Summe."""
        von = max(int(round(start / self._frame_seconds)), self.end - self.size)
        bis = min(int(round(end / self._frame_seconds)), self.end)
        if bis - von < 2:
            return None
        index = np.arange(von, bis) % self.size
        return self._data[:, index], von * self._frame_seconds


# Durchgangsbass am Segmentende (Comfortably Numb: G - F# - Em, das F# einen
# halben Schlag lang von der ganzen Band). Das Akkordmodell kennt keine
# Umkehrungen und labelt G ueber F# als G bzw. Gmaj7 - die Summe aller
# F#-Labels bleibt dort unter 0,05, ein F#-Chip kann aus dem Modell nicht
# kommen (tests/realaudio/REPORT_comfortably_numb.md). Was das Tiefband aber
# klar zeigt, ist der BASS: Ein Segment bekommt deshalb am Ende ein zweites
# Event mit gleichem Akkord und dem gemessenen Durchgangston (G/F#).
#
# Bewusst eng gefasst, sonst wird aus jedem laufenden Bass (Eight Days a
# Week: D-B-D-A) alle zwei Sekunden ein Slash-Chip: Die Note muss chromatisch
# ZWISCHEN dem laufenden und dem naechsten Grundton liegen (je hoechstens
# ein Ganzton, gleiche Richtung), der Lauf muss das Segment beenden und
# mindestens PASSING_MIN_FRAMES Frames stabil sein (Mehrheit PASSING_SHARE
# und MIN_DOMINANCE je Frame, SLASH_ROOT_RATIO ueber den Lauf). Ohne
# Akkordton-Gate - der Durchgangston ist per Definition keiner. Gemessen
# (offline, 93-ms-Frames): 7/7 Solo-Stellen in Comfortably Numb, auf den
# fuenf Referenztiteln 7 Unter-Events, davon 3 nicht annotiert (Let It Be
# Am/G -> F, F/E -> Dm7: reale Walkdowns, die Isophonics nicht schreibt).
# Die breite Variante (jeder stabile Fremdbass) lag bei 154 Unter-Events.
PASSING_MIN_FRAMES = 3
PASSING_SHARE = 0.25
PASSING_END_SLACK = 2      # Frames, die der Lauf vor dem Segmentende enden darf


def passing_note(frames: np.ndarray | None, root: int | None, next_root: int | None,
                 min_frames: int = PASSING_MIN_FRAMES) -> tuple[int, int] | None:
    """Durchgangsbass am Ende eines Segments: (Startframe, Tonklasse) - oder None.

    `frames` ist das Tiefband-Chroma 12 x F des Segments vom Onset bis zum
    naechsten Onset; `root`/`next_root` die Grundtoene beider Akkorde.
    """
    if frames is None or root is None or next_root is None or root == next_root:
        return None
    frames = np.asarray(frames, dtype=float)
    if frames.ndim != 2 or frames.shape[1] < min_frames:
        return None
    total = frames.sum(axis=0)
    dom = frames.argmax(axis=0)
    share = frames.max(axis=0) / (total + 1e-9)
    ordered = np.sort(frames, axis=0)
    dominance = ordered[-1] / (ordered[-2] + 1e-9)
    ok = (total > BASS_SILENCE) & (share >= PASSING_SHARE) & (dominance >= MIN_DOMINANCE)

    ende = frames.shape[1]
    while ende > 0 and not ok[ende - 1]:
        ende -= 1
    if ende == 0 or frames.shape[1] - ende > PASSING_END_SLACK:
        return None                      # kein klarer Ton am Segmentende
    note = int(dom[ende - 1])
    start = ende
    while start > 0 and ok[start - 1] and dom[start - 1] == note:
        start -= 1
    if ende - start < min_frames or note in (root, next_root):
        return None
    abwaerts = (root - note) % 12 <= 2 and (note - next_root) % 12 <= 2
    aufwaerts = (note - root) % 12 <= 2 and (next_root - note) % 12 <= 2
    if not (abwaerts or aufwaerts):
        return None                      # kein Schritt zwischen den Grundtoenen
    pooled = frames[:, start:ende].sum(axis=1)
    if pooled[note] < SLASH_ROOT_RATIO * pooled[root]:
        return None
    return start, note


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


def chord_tone_classes(chord: str) -> set[int] | None:
    """Tonklassen der kanonischen Akkord-ID - None bei unbekannter Qualitaet."""
    from .btc import BTC_CHORD_TONES

    root = chord_root(chord)
    if root is None:
        return None
    root_name = chord[:2] if len(chord) > 1 and chord[1] == "#" else chord[:1]
    quality = chord[len(root_name):].split("/")[0]
    if quality not in BTC_CHORD_TONES:
        return None
    return {(root + iv) % 12 for iv in BTC_CHORD_TONES[quality]}


def slash_note(pooled: np.ndarray | None, chord: str) -> int | None:
    """Bass-Tonklasse fuer die Anzeige zu `chord` - bewusst konservativ.

    Drei Huerden, bevor etwas anderes als der Grundton behauptet wird:
    Mehrheit im Tiefband (MIN_DOMINANCE), Akkordton des Labels (eine Umkehrung
    IST ein Akkordton, ein Rauschgewinner meist nicht), und deutlich staerker
    als der Grundton selbst (SLASH_ROOT_RATIO - sonst erfindet die laute
    Quinte Umkehrungen). Der Grundton selbst darf ohne die letzten beiden
    Huerden zurueckkommen; slash() macht daraus dann keinen Slash.
    """
    if pooled is None:
        return None
    pooled = np.asarray(pooled, dtype=float)
    if pooled.sum() < BASS_SILENCE:
        return None
    rang = np.argsort(pooled)[::-1]
    best, zweiter = int(rang[0]), int(rang[1])
    if pooled[zweiter] > 0 and pooled[best] < MIN_DOMINANCE * pooled[zweiter]:
        return None
    root = chord_root(chord)
    if root is None:
        return None
    if best == root:
        return best
    tones = chord_tone_classes(chord)
    if tones is not None and best not in tones:
        return None
    if pooled[best] < SLASH_ROOT_RATIO * pooled[root]:
        return None
    return best


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

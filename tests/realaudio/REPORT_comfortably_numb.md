# Praxis-Report: Comfortably Numb – das verschluckte F# (G – F# – Em)

**Stück:** Pink Floyd – *Comfortably Numb* (The Wall, 1979), 6:22, ~63,5 bpm
**Datei:** `tests/realaudio/comfortably_numb.mp3` (aus ../YoutubeDownload kopiert, nach WAV 48 kHz mono)
**Stand:** main 67b7a68 (v1.4.0: v7_2b-Gewichte, ein Frame Vorwärtskorrektur, Beat-Snap, Bass über Notenbins)
**Datum:** 2026-09-13
**Beobachtung (Proberaum, Bass):** Im Gitarrensolo am Ende spielt die ganze Band
G – F# – E; JamPilot zeigt meist G – E – E, nur an zwei, drei Stellen das F#.

---

## 1. Was klingt (Ground Truth aus dem Audio)

Progression der Strophen und des Schlusssolos: **Bm – A – G – Em – Bm**, ein
Takt je Akkord, G und Em teilen sich einen Takt. Der Bass geht darin
**G – F# – E** hinunter: Das F# liegt auf der „und" von Zwei und dauert einen
halben Schlag (0,37–0,56 s). Darüber spielt die Band F#-Töne (F#, A, C# im
Mittel-/Hochband), also ein echter Durchgangsakkord (G/F# bzw. F#m-artig),
kein bloßes Bass-Zwischenspiel. Quellen zum Gegenlesen: Guitar Noise notiert
den Takt als „G (F#) Em", Hooktheory als Bm–A–G–Em.

F#-Dauer im Bass-Tiefband (BTC-CQT, 93-ms-Frames, dominante Tonklasse) je G→Em:

| Stelle | G-Dauer | F#-Bass | Bemerkung |
|---|---|---|---|
| 30,5 s / 45,5 s / 189 s (Strophen) | 1,4–1,9 s | 0–2 Frames (≤ 0,19 s) | Bass streift das F# nur |
| 280,0 s | 1,86 s | 3 Frames (0,28 s) | erster Solo-Durchgang |
| 295,1 / 310,2 / 325,3 / 340,5 / 355,6 / 370,7 s | 1,9–2,0 s | 4–6 Frames (0,37–0,56 s) | Solo, Band hält das F# |

Im Solo ist das F# also **an allen sieben Stellen** messbar und stabil – die
Beobachtung „die ganze Band spielt das" stimmt; in den Strophen ist es nur ein
Streifton.

## 2. Was JamPilot daraus macht

**Offline (`jampilot analyze`):** kein einziges F#-Segment im ganzen Stück.
G → Em (bzw. Em7) → Bm, sonst nichts.

**Modell frameweise (Softmax der Logits, 290–300 s):** Über dem F#-Bass steigt
die Wahrscheinlichkeit von **Gmaj7** (0,05 → 0,23), G bleibt führend, und bei
297,0 s springt es direkt auf Em7. Die Summe aller F#-Labels (F#, F#m, F#7, …)
bleibt bei 0,03; über den ganzen Song 8 Frames mit p(F#) > 0,2, ein einziger
Frame mit F# als Argmax (bei 372 s, 0,415). Das Modell **sieht** das F#, deutet
es aber als Septime unter G – genau die Konvention seiner Trainingsdaten
(Isophonics/large-voca kennt keine Umkehrungen, G/F# ist dort `G:maj/7`, d. h.
Label G). Ein F#-Chip kann aus diesem Modell nicht kommen, auch mit anderen
Gewichten nicht, solange die Referenz so annotiert.

**Live-Pfad (Simulation `messung_live_pfad.lauf`, 262–382 s, --delay 5):**

```
 295.16s  G      bass=G     dur=1.90  beat 1
 297.06s  Em7    bass=E     dur=0.94  beat 1
 298.00s  Em     bass=E     dur=0.94
 298.94s  Bm     bass=B     dur=7.54  beat 1
```

Das ist das gemeldete **G – E – E**: Der Bass des G-Segments wird 2 s ab Onset
gepoolt (1,45 s G gegen 0,45 s F#) und bleibt G; das F# hat keinen eigenen
Eintrag. Der zweite E-Chip ist ein Label-Flackern Em7 → Em innerhalb desselben
Akkords (drei der sieben Solo-Durchgänge: 280, 295, 325 s), das der Ledger als
neues Event durchreicht.

Die „zwei, drei Stellen, an denen es stimmt" sind mit hoher Wahrscheinlichkeit
Zufallstreffer der Hop-Phase, kein funktionierender Pfad: In der Simulation
entsteht bei 357,5 s ein 0,25-s-Chip `Bm` mit Bass **F#** (die Grenzverfeinerung
zieht die Em-Grenze vor, die Zeitleiste vermischt Bm/G/Em), im Bass-Modus steht
dann ein großes F# „over Bm". Je nach Hop-Phase im echten Lauf passiert das an
anderen Stellen oder gar nicht.

## 3. Woran es nicht liegt

- **Nicht** an der Bass-Notenbin-Faltung (12.09.): Das Tiefband zeigt das F# an
  allen Solo-Stellen klar (Anteil 0,30–0,50, Grundton G dabei ≤ 0,12, Ratio > 3).
- **Nicht** an `MIN_SEGMENT_SECONDS`/`MIN_EVENT_GAP`: Es gibt kein F#-Segment,
  das verschmolzen werden könnte – das Modell erzeugt keins.
- **Nicht** an der Tonart-/Stufenlogik: Key D-Dur/B-Moll ist korrekt.

## 4. Was das F# liefern kann: der gemessene Bass (Prototyp, offline gemessen)

Idee: Ein Modellsegment wird **am Ende geteilt**, wenn das Tiefband dort einen
stabilen Lauf einer anderen Note zeigt. Zwei Varianten gemessen
(`fold_bass_chroma`, Mehrheit ≥ 0,25 und `MIN_DOMINANCE` je Frame,
`SLASH_ROOT_RATIO` 3,0 über den Lauf):

**A – jeder stabile Fremdbass im Segment** (Akkordton-Gate wie in
`bass.slash_note` gelockert, sonst fällt F# unter G durch):

| Mindestlauf | Comfortably Numb G/F# (von 7 im Solo) | Unter-Events Referenzset (5 Titel) | davon gegen die Annotation |
|---|---|---|---|
| 3 Frames (0,28 s) | 7 | 154 | 145 |
| 4 Frames (0,37 s) | 6 | 49 | 44 |
| 5 Frames (0,46 s) | 3 | 11 | 7 |

Unbrauchbar: Eight Days a Week (laufender Bass D–B–D–A) liefert alle 2 s einen
Slash-Chip; die annotierten Nur-Bass-Wechsel (Let It Be 9, Something 12) trifft
die Regel trotzdem fast nie.

**B – Durchgangsbass am Segmentende:** Note liegt chromatisch **zwischen** dem
laufenden und dem nächsten Grundton (je höchstens ein Ganzton, gleiche
Richtung), der Lauf endet mit dem Segment, kein Akkordton-Gate:

| Mindestlauf | Comfortably Numb G/F# (von 7) | Unter-Events Referenzset | davon gegen die Annotation |
|---|---|---|---|
| 2 Frames (0,19 s) | 7 | 12 | 8 |
| **3 Frames (0,28 s)** | **7** | **7** | **3** |
| 4 Frames (0,37 s) | 6 | 3 | 0 |

Die sieben Referenz-Unter-Events bei 3 Frames: Something 3 (alle annotiert,
Em/D → C7 usw.), Let It Be 3 (Am/G → F, F/E → Dm7, C/B → Am – musikalisch
die bekannten Walkdowns, die Annotation schreibt dort den reinen Akkord),
Crazy Little Thing 1 (Gm/F → D#, fraglich). Also rund ein Slash-Chip je drei
Minuten außerhalb des Zielfalls, überwiegend echt.

## 5. Empfehlung

Variante B mit 3 Frames als **Bass-Unterereignis**: Das G-Segment bekommt am
Ende einen zweiten Ledger-Eintrag mit gleichem Akkord und Bass F#, also den
Chip **G/F#**; im Bass-Modus steht dann ein großes **F# over G**, das
Griffbrett zeigt F#. Der Gitarrenmodus bleibt bei G (dort ist der Griff G, und
das Modell gibt nichts anderes her). Die Anzeige sagt damit, was gemessen ist –
ein F#m-Chip wäre gegen das Modell erfunden.

Umsetzungsskizze im Live-Pfad (nicht gebaut):
- `_bass_per_segment` liefert je Zeitleisteneintrag zusätzlich den Durchgangs-
  Lauf am Segmentende (Note, Laufstart), gemessen aus `BassTrack` bis zum
  nächsten Onset; Bedingung wie B, nächster Onset muss bekannt sein (ist er:
  Horizont liegt 2 s hinter der Commit-Grenze).
- Der `EventLedger` führt für den Lauf einen eigenen Streak, geschlüsselt am
  **Segment-Onset plus Note**, nicht an der Laufposition (das 93-ms-Raster
  wandert je Hop um einen Frame); Commit mit `BASS_COMMIT_HOPS` wie der Bass
  selbst, Onset = Laufstart (ggf. Viertel-Snap), Mindestabstand
  `MIN_EVENT_GAP` ist mit 0,28 s Laufdauer gerade eingehalten.
- Kontrollgitarre unverändert (spielt G).

Zweiter, kleinerer Punkt: der Em7 → Em-Doppelchip. Ein Event, das nur die
Septime seines Vorgängers ändert (gleicher Grundton, gleiches Geschlecht,
gleicher Bass), könnte als „dieselbe Aussage" durchgehen wie heute gleicher
Name + gleicher Bass. Nicht gemessen, ob das anderswo echte Wechsel schluckt
(C → Cmaj7 als Farbwechsel ist in Jazzstandards ein Ereignis) – Nutzerentscheid.

## 6. Umsetzung (Branch feature/durchgangsbass, 2026-09-13)

Variante B mit 3 Frames ist gebaut: `bass.passing_note` misst den Lauf am
Segmentende aus dem `BassTrack` (`frames_between`), `cli._passing_per_segment`
liefert je Zeitleisteneintrag `(Laufstart, Note)`, und der `EventLedger`
committet ihn nach `PASSING_COMMIT_HOPS` (2) Hops mit derselben Note genau
einmal je Segment als Event mit gleichem Akkord und dieser Bassnote – hinter
dem eigenen Segment, nie hinter dem schon committeten Nachfolger, ohne
Viertel-Snap. Streak-Schlüssel ist der Segment-Onset plus Note, weil der
Laufstart mit dem 93-ms-Raster je Hop um einen Frame wandert.

**Live-Simulation Solo (262–382 s, --delay 5), vorher → nachher:**

```
 295.16s  G      bass=G     dur=1.90        295.16s  G      bass=G     dur=1.49
                                            296.64s  G      bass=F#    dur=0.41
 297.06s  Em7    bass=E     dur=0.94        297.06s  Em7    bass=E     dur=0.94
```

G/F# erscheint an **sechs der sieben** Solo-Stellen (281,6 / 296,6 / 311,6 /
326,7 als Gmaj7/F# / 342,0 / 372,2 s), Dauer 0,32–0,56 s, jeweils direkt vor
dem Em. Die siebte (355,7 s) fehlt weiterhin: Dort zerlegt das Modell die
Grenze selbst in Bm/G/Em-Splitter von 0,25 s, die Regel findet kein
G-Segment mit Em-Nachfolger. Im Bass-Modus steht an den sechs Stellen ein
großes **F# over G**, der Chip heißt `G/F#`. Alle anderen Events sind
unverändert (49 statt 43 Events im Ausschnitt).

**Referenzset im Live-Pfad (fünf Isophonics-Titel, mit Beat-Tracker), ohne
→ mit Regel:** Timing, Schlagtreffer und Eventzahl sind bis auf die neuen
Events identisch. Fünf Durchgangs-Events auf 14 Minuten Musik:

| Titel | Events ohne → mit | Durchgangs-Events | Annotation dort |
|---|---|---|---|
| Let It Be | 152 → 154 | 38,5 s C/B, 146,5 s C/B | `C/7` ✓, `C` |
| Eight Days a Week | 89 → 89 | – | – |
| Something | 136 → 138 | 18,9 s F/E, 99,2 s C/B | `C/3` (Bass E ✓), `C/7` ✓ |
| It's Too Late | 156 → 156 | – | – |
| Crazy Little Thing | 133 → 134 | 50,6 s A#/A | `Bb:maj` |

Drei der fünf tragen den annotierten Basston, bei Something steigt der
Nur-Bass-Treffer von 25 auf 33 %. Die zwei ohne Annotation (Let It Be 146 s
C/B, Crazy Little Thing A#/A) sind je ein Chip von 0,3 s. Der laufende Bass
von Eight Days a Week bleibt unangetastet.

Messskripte dieser Analyse liegen nicht im Repo (Session-Scratch); die
Kernstücke sind `btc.fold_bass_chroma` + `segments_from_labels` über die ganze
Datei und `tests/reference/messung_live_pfad.lauf` über 262–382 s.

## 6. Nachtrag 2026-10-13: PULSE-Liveversion, Stand b7f9e57

**Datei:** `tests/realaudio/comfortably_numb.mp3` ist jetzt die PULSE-Version
(Restored & Re-Edited, 9:35), nicht mehr die Studioversion von oben.
**Beobachtung (Proberaum):** Das F# im Solo fehlt meist – Verdacht auf die
Merge-Korrektur vom selben Tag (REPORT_sailing_to_philadelphia.md).

**Nicht die Ursache.** Live-Pfad (`messung_live_pfad.lauf`, ganzes Stück)
mit 0cb2825 und b7f9e57: identische Event-Folge (176 Events), dieselben vier
G/F#-Durchgangsevents (294,1 / 324,9 / 477,2 / 507,3 s); der neue Stand setzt
zusätzlich bei 16 Events einen Grundton-Bass, wo vorher keiner stand.

**Auf dieser Aufnahme trifft der Durchgangsbass 4 von 13 Solo-Übergängen.**
Hürden von `bass.passing_note` je Stelle:

| Grund | Stellen |
|---|---|
| F#-Lauf nur 1–2 stabile Frames (Mehrheit < 0,25 oder Dominanz < 1,25) oder Ratio F#/G < 3 | 307,9 · 354,2 · 384,6 · 460,5 · 520,9 s (520,9: 5 Frames, Ratio 2,4) |
| Modell labelt den Folgeakkord Bm oder F#m statt Em – F# liegt nicht zwischen den Grundtönen | 399,6 · 414,9 · 430,2 · 445,4 · 468,0 s (430,2: Lauf 4 Frames, Ratio 3,6 – wäre sauber) |
| Verfeinerung zieht den Em-Onset auf den F#-Anschlag vor (340,70 → 340,48 s), der Lauf gehört dann nicht mehr zum G-Segment; offline sagt die Regel dort F# | 338,7 s |

Der Live-Bass streift das F# kürzer als im Studio, und das Modell hört den
Em-Takt öfter als Bm. Vergleich mit Moises (Offline-Analyse des ganzen
Audios): zeigt dort ebenfalls nur G → Em, kein F#.

**Entscheidung:** so lassen. Mögliche Stellschrauben mit bekanntem Preis:
Mindestlauf 2 Frames (September-Messung: 12 statt 7 Unter-Events auf dem
Referenzset, 8 gegen die Annotation), Ratio unter 3, oder in der
Verfeinerung einen Zwischenton-Lauf nicht als Anschlag des neuen Akkords
werten (träfe auch die Sailing-Kette an der Wurzel; eigene Messung gegen die
Isophonics-Grenzen nötig).

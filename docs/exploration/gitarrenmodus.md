# Gitarrenmodus: das Griffbild zum Akkord

*Explorationsdokument. Status: Entwurf mit Entscheidungen und Umsetzungsplan —
Grundlage für die Implementierung im selben Zweig.*

---

## Das Ziel

JamPilot zeigt den klingenden Akkord groß und als Laufband — der Name sagt einem
*Pianisten* oder einem, der Harmonielehre kann, sofort, was zu greifen ist. Einem
**Gitarrenanfänger** sagt „F#m7" wenig: Er weiß nicht ohne Nachschlagen, wo seine
Finger hingehören. Der Gitarrenmodus schließt genau diese Lücke — er zeigt links
oben ein **Griffbild** (Griffbrett mit Bünden und Fingerpunkten) zum gerade
klingenden Akkord, damit man ihn *sieht* statt ihn zu übersetzen.

Analog zum **Bassmodus**: Dort wird die gemessene Bassnote groß und der Akkord
zum Kontext — eine andere Sicht auf dieselben Daten, allein im Browser
umgeschaltet. Der Gitarrenmodus ist die dritte Sicht: derselbe Akkord, als
Griffbild.

## Wo das Feature lebt

Die Anzeige ist vollständig die Webseite (`web.py`, die eingebettete `PAGE`). Der
Instrument-Umschalter (`chords | bass`) ist bereits ein reiner Browser-Zustand
(`localStorage`, `setzeInstrument`, `document.body.classList`). Der Server schickt
die Akkorde ohnehin **kanonisch** mit (`{c, at, b}`, immer mit Kreuz) — alles,
was ein Griffbild braucht, ist schon da.

**Konsequenz: Der Gitarrenmodus ist ein reines Frontend-Feature.** Keine Änderung
an der Audio-Analyse, an `chords.py`, am Protokoll oder am Kontrollfenster
(`gui.py` zeigt nur Steuerung, keine Akkorde). Das hält das Risiko klein und die
Änderung auf `web.py` (plus Tests) begrenzt.

## Die Kernfrage: vom Akkordnamen zum Griff

Ein Griffbild braucht pro Saite: gegriffener Bund, leere Saite (O) oder
abgedämpft (X). Das Vokabular des Erkenners ist überschaubar — `Dur, m, 7, maj7,
m7` (siehe `chords.py`) — also fünf Akkordqualitäten über zwölf Grundtönen, plus
Slash-Akkorde (gemessener Bass).

Zwei Wege:

1. **Feste Griff-Bibliothek** (60 einzeln hinterlegte Formen). Musikalisch exakt,
   aber viel Datenpflege und inkonsistent (mal offen, mal Barré).
2. **Bewegliche Formen (CAGED / E- und A-Form).** Zwei Barré-Schablonen pro
   Qualität — eine mit Grundton auf der tiefen E-Saite (Saite 6), eine auf der
   A-Saite (Saite 5) — werden am Griffbrett verschoben. Aus zehn Schablonen
   entstehen alle 60 Akkorde, **konsistent und lehrbar**: Der Lernende sieht immer
   dieselbe Handform, nur an anderer Position. Genau so lernt man Gitarre.

**Entscheidung: bewegliche E-/A-Form.** Sie ist kompakt, konsistent und
pädagogisch richtig (eine Form, viele Akkorde). Offene Akkorde fallen als
Sonderfall automatisch an: Sitzt der Grundton am Nullbund (Barré-Bund 0), *ist*
die E-Form von E-Dur der offene E-Dur-Griff, die A-Form von A-Dur der offene
A-Griff.

### Die Schablonen (Bünde relativ zum Grundtonbund R, Saiten 6→1)

E-Form (Grundton auf Saite 6):

| Qualität | 6 | 5 | 4 | 3 | 2 | 1 | offener Prototyp |
|---|---|---|---|---|---|---|---|
| Dur   | R | R+2 | R+2 | R+1 | R | R | E-Dur (0 2 2 1 0 0) |
| m     | R | R+2 | R+2 | R | R | R | Em (0 2 2 0 0 0) |
| 7     | R | R+2 | R | R+1 | R | R | E7 (0 2 0 1 0 0) |
| maj7  | R | R+2 | R+1 | R+1 | R | R | Emaj7 (0 2 1 1 0 0) |
| m7    | R | R+2 | R | R | R | R | Em7 (0 2 0 0 0 0) |

A-Form (Grundton auf Saite 5, Saite 6 abgedämpft = X):

| Qualität | 6 | 5 | 4 | 3 | 2 | 1 | offener Prototyp |
|---|---|---|---|---|---|---|---|
| Dur   | X | R | R+2 | R+2 | R+2 | R | A-Dur (x 0 2 2 2 0) |
| m     | X | R | R+2 | R+2 | R+1 | R | Am (x 0 2 2 1 0) |
| 7     | X | R | R+2 | R | R+2 | R | A7 (x 0 2 0 2 0) |
| maj7  | X | R | R+2 | R+1 | R+2 | R | Amaj7 (x 0 2 1 2 0) |
| m7    | X | R | R+2 | R | R+1 | R | Am7 (x 0 2 0 1 0) |

### Positionswahl

Leersaiten-Tonklassen (Standardstimmung): Saite 6 = E (4), Saite 5 = A (9).
Für Grundton-Tonklasse `pc`:

- E-Form-Bund `R_E = (pc − 4) mod 12`
- A-Form-Bund `R_A = (pc − 9) mod 12`

Gewählt wird die Form mit dem **kleineren** Bund (tiefer am Hals = leichter, und
Bund 0 = offener Griff). Rechnerisch liegt das Minimum immer bei **Bund 0–6** —
kein Akkord landet höher, das Griffbild bleibt immer im ersten Lagenfenster.
Gleichstand → E-Form (vollerer Klang, Grundton im Bass).

### Slash-Akkorde / Umkehrungen

Der Server misst den Bass separat (`b`). Fürs Griffbild wird zunächst die
**Grundform** gezeigt (der Akkord, nicht die Umkehrung) — musikalisch ist das der
richtige Griff; welche Note der Bassist unten spielt, ist eine andere Frage. Der
volle Slash-Name (`C/E`) steht weiterhin im Namen/Laufband. (Spätere Ausbaustufe:
den Basston im Griffbild markieren.)

## Darstellung

- **Griffbild-Box links oben**, unterhalb der Kopfzeile (Marke/Tonart), nur
  sichtbar bei `body.guitar`. Der große Akkordname bleibt zentriert — Name *und*
  Griff zusammen, das ist der Lerneffekt.
- Gerendert als **SVG**: sechs Saiten (senkrecht), fünf Bünde (waagerecht), dicker
  Sattel bei Bundlage 0, Fingerpunkte, O/X über den Saiten, Bundlagen-Ziffer
  („5fr"), wenn nicht am Sattel. Erkennbarer **Barré** (mehrere Saiten auf demselben
  Bund R) wird als Balken gezeichnet.
- Self-contained, kein CDN — wie die ganze Seite. Themenfarben aus dem Bestand
  (`#6ea8ff` als Akzent).

## Umschalter

Dritte Option im „Your instrument"-Dialog neben *Chords* und *Bass*: **Guitar**,
Glyphe 🎸/♬, Beschreibung „Das Griffbild zum Akkord — sehen statt übersetzen."
Auswahl wird wie die anderen in `localStorage` gemerkt.

## Was geprüft wird

- **JS-Unit-Test der Griff-Logik** (node ist vorhanden): Für bekannte Grundtöne
  müssen die offenen Prototypen exakt herauskommen (E→E-Dur offen, A→A-Dur offen,
  E→Em7 = 0 2 0 0 0 0 usw.), und alle 60 Kombinationen müssen im Fenster Bund 0–8
  liegen und die richtigen Tonklassen enthalten.
- **PAGE-Tests** (wie die bestehenden in `test_web.py`): Die Guitar-Option, das
  Griffbild-Element und die Shape-Funktion stehen in der Seite.
- **Regression**: die volle Suite bleibt grün; `?demo` zeigt das Griffbild live
  (manuelle QS durch den Autor).

## Nicht-Ziele (bewusst offen)

- Kein Fingersatz (welcher Finger auf welchem Punkt) — das Griffbild zeigt die
  Positionen, die Fingerwahl ist Standard.
- Keine alternativen Voicings/Lagen zur Auswahl — eine konsistente Form pro
  Akkord.
- Kein Markieren des gemessenen Basstons im Griff (spätere Stufe).

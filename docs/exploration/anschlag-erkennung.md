# Nachschlag desselben Akkords: der Anschlag aus der Akkord-Energie

Stand: 2026-10-15 · Branch `exploration-anschlag-erkennung` · Status:
**verworfen.** Zwei Wege gebaut und im Proberaum getestet, beide machen die
Zeitleiste unruhig statt nuetzlich. Der Code (restrike.py, Ledger-Anbindung,
Chip-Markierung, Messskript `messung_anschlag.py`, Tests) liegt vollstaendig
im Git-Verlauf: Commit 8396cb7 (Energie-Weg) und der Arbeitsstand des
Takt-Wegs in Abschnitt 7. Im Code ist nichts davon geblieben.

## 1. Die Frage

Die Zeitleiste zeigt von `D D D D D` nur das erste D. Das ist gewollt: Der
Publish-once-Kanal verschluckt jede Wiederholung derselben Aussage (gleicher
Akkord, gleicher Bass), damit das Laufband ruhig bleibt. Eine Sache fehlt
dabei: Klingt das D nur noch aus und wird dann **kräftig neu angeschlagen**,
sieht man davon nichts - für den Mitspieler ist dieser Anschlag aber ein
Ereignis ("jetzt wieder"), auf das er sich einstellen will.

Das Akkordmodell kann das nicht liefern: Seine Labels sagen D vor und nach
dem Anschlag, eine Grenze gibt es nicht. Die Energie dagegen ist da - in
denselben Log-CQT-Frames (`btc.features_from_audio`, 93-ms-Raster), die das
Modell jeden Hop bekommt. Die Frage dieser Exploration: Lässt sich der
Nachschlag daraus lesen, **ohne** dass Schlagzeug und blosses Durchschlagen
(jeder Schlag ein Anschlag) die Zeitleiste wieder füllen?

## 2. Das Verfahren (`jampilot/restrike.py`)

Je Frame drei Pegel in dB aus den CQT-Magnituden: die Energie der
**Akkordtöne** des gerade erkannten Akkords (alle Oktaven), die der übrigen
Tonklassen, und die Gesamtenergie. Ein Nachschlag ist ein Frame, in dem

1. die Akkordton-Energie gegenüber dem Minimum der zwei Frames davor um
   mindestens **6 dB** springt (`RISE_DB`; zwei Frames, weil ein Anschlag das
   Raster straddelt - zusammenhängende Anschlagframes sind ein Anschlag, er
   liegt auf dem grössten Sprung),
2. der Sprung **harmonisch** ist: Die Akkordtöne steigen um mindestens
   **2 dB mehr** als die übrigen Tonklassen (`HARM_DB`) - ein
   Schlagzeugschlag hebt alle gleich,
3. das Etikett drei Frames vor und nach dasselbe ist (`GUARD_FRAMES`; ein
   Wechsel ist kein Nachschlag, den liefert das Modell),
4. und davor eine **Klingzeit** lang kein harmonischer Anschlag war - auch
   kein kleiner: Schon **3 dB** (`RESET_DB`) unterbrechen das Klingen. Wer
   jeden Schlag durchschlägt, hält den Akkord laut; die einzelnen Schläge
   heben ihn nur um 2-4 dB. Ohne diese zweite Schwelle kam jeder Akzent im
   Durchschlagen als Nachschlag durch (Eight Days a Week: 12 je Minute).

Die Klingzeit hängt am Tempo: **zwei Schläge** des Beat-Rasters (`RING_BEATS`,
begrenzt auf 0,75-2,5 s), ohne Raster 1,0 s. Eine feste Sekunde liesse bei
70 bpm das Durchschlagen durch (fast eine Sekunde je Schlag) und verschluckte
bei 140 bpm den echten Nachschlag nach einem Takt.

Schlagzeug zählt bewusst NICHT als Anschlag - auch nicht für die Klingzeit.
Sonst könnte mit Schlagzeug nie ein Nachschlag entstehen (jeder Schlag ein
"Anschlag", nichts klingt je zwei Schläge). Das war der erste Fehler des
Prototyps: das synthetische Kontrollsignal mit Rauschbursts fand den
Nachschlag nicht.

Ein Tiefband-Kriterium (Akkordtöne unter C4 müssen mitsteigen, `LOW_DB`;
Idee: eine Stimme hat dort wenig, ein Griff seine tiefen Saiten) wurde
mitgemessen und bringt nichts - es steht auf 0.

## 3. Messung offline (`tests/reference/messung_anschlag.py`)

Ground Truth für einen Nachschlag gibt es nicht. Gemessen wird deshalb
indirekt, über den ganzen Titel mit den Modell-Segmenten von `jampilot
analyze`, Nachschläge näher als 0,35 s an einem Wechsel abgezogen:

- **Nachschläge je Minute** - wie viele Chips kämen dazu;
- Anteil auf einem annotierten **Schlag** (±120 ms: 70 ms Toleranz plus
  halbes Frame) - ein Anschlag, der keinen Schlag trifft, ist verdächtig;
- **Phrasensplits** der Isophonics-Annotation (C nach C an einer
  Phrasengrenze) mit Nachschlag innerhalb ±250 ms - das Einzige in den
  Annotationen, das einen Nachschlag desselben Akkords überhaupt markiert;
- bei den **Echoes-Stems**: Nachschläge im vollen Mix, die auch im
  harmonischen Mix (ohne Schlagzeug und Gesang) stehen - der Rest kommt
  aus Schlagzeug oder Gesang.

### 3.1 Synthetisch (Karplus-Strong-D, Rauschbursts alle 0,5 s ab 2 s)

D bei 0 s, Nachschlag bei 3 s, ab 6 s jeden halben Schlag durchgeschlagen,
ab 10 s ausklingend. Ergebnis für jeden gemessenen Parametersatz der
Akkordton-Variante: **3,07 s und 6,13 s** - der Nachschlag und der erste
Anschlag des Durchschlagens (nach drei Sekunden Klingen zu Recht ein
Nachschlag); kein Treffer auf einem Rauschburst, keiner im Durchschlagen.
Die Vollband-Variante findet zusätzlich die Bursts bei 2,5 / 12,0 / 13,0 s.

### 3.2 Referenzset und Proberaum-Material

Nachschläge je Minute (in Klammern: Anteil auf einem Schlag), jeweils
rise 6, harm 2, reset 3:

| Titel | Charakter | Klingzeit 1,0 s | **2 Schläge** | 2 Schläge, rise 8 |
|---|---|---|---|---|
| Let It Be (73 bpm) | Klavier auf jedem Schlag | 2,2 (33 %) | **0,5** (50 %) | 0,5 |
| Eight Days a Week (140 bpm) | Durchschlagen, Gesang | 8,0 (82 %) | **9,1** (80 %) | 6,9 |
| Something (66 bpm) | | 4,6 (36 %) | **1,0** (67 %) | 0,7 |
| It's Too Late | Klavier | 6,2 | **6,2** | 4,4 |
| Crazy Little Thing | | 1,5 | **1,5** | 0,4 |
| Comfortably Numb (Proberaum) | lange Akkorde | 1,8 | **1,8** | 0,3 |
| Sailing to Philadelphia (Proberaum) | | 1,8 | **1,8** | 0,2 |

(Für die Titel ohne Beat-Annotation gilt die Klingzeit 1,0 s als "2 Schläge".)
Ohne Klingzeit und Reset lagen alle Titel bei 7-15 je Minute - das wären
die Chips, die die Zeitleiste wieder füllen; die Klingzeit ist der Hebel.

Die Phrasensplits trifft das Verfahren mit der tempo-relativen Klingzeit
praktisch nicht mehr (Let It Be 0 von 24): Das Klavier schlägt dort auf
jedem Schlag, der Phrasenanfang ist kein Nachschlag nach Klingen. Das ist
richtig so - genau diese Chips sollen nicht kommen.

**Eight Days a Week** bleibt der Ausreisser: 9 je Minute trotz
Durchschlagen, 80 % davon auf einem Schlag. Das Durchschlagen selbst hebt
die Akkordtöne um weniger als 3 dB (der Akkord ist durchgehend laut), die
≥ 6-dB-Sprünge alle ~7 s sind nach Lage der Dinge die Gesangseinsätze
(zweistimmig, auf Akkordtönen) - siehe 3.3.

### 3.3 Echoes-Stems: woher die Nachschläge kommen

Erste 360 s von Pink Floyd - Echoes (Stem-Trennung, s.
[lagenkorrekte-bassanzeige.md](lagenkorrekte-bassanzeige.md)), ein Etikett
aus dem vollen Mix für alle Mischungen, Klingzeit 2 Schläge bei 70 bpm:

| Parameter | voll | harmonisch (ohne Drums/Gesang) | + Drums | + Gesang | im harm. Mix bestätigt |
|---|---|---|---|---|---|
| rise 6, harm 2, Klingzeit 1,0 s | 38 (6,3/min) | 31 | 37 | 31 | 71 % |
| **rise 6, harm 2, 2 Schläge** | **28 (4,7/min)** | 20 | 28 | 23 | 57 % |
| rise 6, harm 4, 2 Schläge | 20 | 16 | 18 | 17 | 65 % |
| rise 8, harm 2, 2 Schläge | 20 | 15 | 19 | 17 | 60 % |

Lesart: Von den 28 Nachschlägen im vollen Mix stehen 16 auch im
harmonischen Mix; das Schlagzeug bringt etwa 8 dazu (28 gegen 20 - nicht
als Anschlag, sondern weil ein Schlag auf einen leisen harmonischen
Anschlag fällt und ihn über die Schwelle hebt), der Gesang etwa 3. Wie
viele der 20 harmonischen Nachschläge *musikalisch* Nachschläge sind,
sagt die Messung nicht - das kann nur das Ohr.

## 4. Eingebaut

- `restrike.detect` je Hop auf den Fenster-Features mit den rohen
  Modell-Labels als Etikett je Frame (`names_per_frame`), Klingzeit aus
  `raster.interval()` (`ring_for`). Kandidaten jenseits des Horizonts
  warten; bestätigt wird, was zwei Läufe in Folge an derselben Stelle sehen
  (`Restrikes`, ±0,15 s - das Raster wandert je Hop um einen Frame), und
  ein bestätigter Anschlag behält seine erste Position.
- `EventLedger.advance(restrikes=...)`: Ein bestätigter Nachschlag, der die
  Commit-Grenze passiert, wird in Zeitfolge mit den Zeitleisteneinträgen
  als Event eingereiht - gleicher Akkord, gleicher Bass und Lage wie das
  letzte Event, `restrike: True` -, sofern das letzte Event diesen Akkord
  führt und mindestens `RESTRIKE_MIN_AFTER` (0,75 s) zurückliegt. Nicht
  geschnappt (am Audio gemessen), eigene Wasserlinie, genau einmal. Stille
  und Unbekannt haben keinen Nachschlag.
- `index.html`: der Chip trägt die Klasse `restrike` - leiserer Name, ein
  Anschlagstrich an der linken Kante. Der grosse Akkord ändert sich nicht.
- `jampilot analyze` listet Nachschläge als `again`-Zeilen zwischen den
  Segmenten (feste Klingzeit, kein Raster).
- `restrike.ENABLED` schaltete alles ab, für den Vergleich im Proberaum.

Live-Simulation (`messung_live_pfad.lauf`, --delay 5, mit Beat-Tracker),
Nachschlag an gegen aus: die übrigen Events sind identisch (Onset, Akkord,
Bass), es kommen nur Nachschlag-Events dazu - Zahlen in Abschnitt 5.

## 5. Live-Simulation

`messung_live_pfad.lauf` (--delay 5, mit Beat-Tracker), Nachschlag an gegen
aus. Die uebrigen Events (Onset, Akkord, Bass) sind auf allen drei Titeln
identisch; es kommen nur Nachschlag-Events dazu:

| Titel | Events aus | Events an | Nachschläge | Stellen |
|---|---|---|---|---|
| Let It Be | 145 | 149 | 4 (1,0/min) | 14,2 C · 46,0 C · 54,5 G · 119,3 C |
| Comfortably Numb | 176 | 186 | 10 (1,0/min) | 7,1 B · 101,6 D · 117,0 C · 122,5 G · 175,2 D · 190,6 Bm · 225,2 C · 252,3 A · 263,9 C · 269,1 G |
| Sailing to Philadelphia | 146 | 155 | 9 (1,6/min) | 25,1 F#m7 · 78,4 E · 230,9 F#m7 · 246,5 A · 250,2 F#m7 · 269,6 F#m7 · 302,3 A · 308,3 F#m7 · 324,7 A |

Live kommen weniger durch als offline (Comfortably Numb 10 statt 15,
Sailing 9 statt 10): Die Bestaetigung ueber zwei Laeufe und die
tempo-relative Klingzeit aus dem Raster filtern zusaetzlich.

### 5.1 Proberaum (2026-10-15)

Erster Mitspieltest: **nicht hilfreich.** Wann ein Nachschlag-Chip kommt,
wirkt nicht deterministisch; die Schwelle ist offenbar stark songabhaengig.
Drei Ursachen, die zur Messung passen:

- **Absolute dB-Schwellen haengen am Mix.** In einer dichten Stelle halten
  Bass, Keys und Gesang die Akkordtoene laut, ein Nachschlag hebt sie nur
  um 2-3 dB; in einer duennen Stelle springt derselbe Griff um 15 dB.
- **Der Bass setzt die Klingzeit zurueck.** Die Akkordtoene werden ueber
  alle Oktaven gemessen; jede Bassnote ist ein Akkordton und damit ein
  "kleiner harmonischer Anschlag" ueber RESET_DB. Ob ein Nachschlag
  durchkommt, haengt davon ab, ob der Bass gerade eine Pause hatte.
- **Das 93-ms-Raster wandert je Hop.** Der Sprung ueber zwei Frames faellt
  je nach Lage des Anschlags im Raster mal auf 6,2 und mal auf 5,8 dB; die
  Bestaetigung ueber zwei Laeufe kippt dann zufaellig.

Naechste Wege, in dieser Reihenfolge:

1. **Takt-synchrone Nachschlaege mit Audio-Bestaetigung.** Kandidaten sind
   nur die Taktanfaenge aus dem Beat-Raster innerhalb eines langen
   Segments. An jeder Eins: Gibt es dort einen harmonischen Anschlag,
   mindestens ~60 % so stark wie der Anschlag am Anfang dieses Segments?
   Der Segmentanfang ist die Referenz dafuer, wie ein echter Anschlag
   dieses Akkords in diesem Song klingt - kalibriert sich je Segment
   selbst. Gemessen wie die Grenzverfeinerung: HPSS-Harmonikanteil,
   Onset-Staerke im 23-ms-Raster, festes Raster. Zeitlich deterministisch,
   ein Chip landet immer auf einer Taktlinie; Nachschlaege zwischen den
   Taktlinien entfallen bewusst.
2. **Nur Zeitstruktur, ohne Audio.** Ein Akkord ueber mehr als zwei Takte
   bekommt an jedem weiteren Taktanfang einen leisen Fortsetzungs-Chip.
   Voellig vorhersagbar, zeigt aber nicht den Anschlag, nur "geht weiter".
3. **Den jetzigen Detektor reparieren**: Akkordtoene nur oberhalb des
   Bassregisters, Schwelle relativ zum Segment-Maximum, Feinraster statt
   Hop-Raster. Bleibt ein Schwellenverfahren.

## 6. Offen

- **Gesang.** Eine Stimme, die auf einem Akkordton einsetzt, ist für diese
  Messung ein harmonischer Anschlag. Mit den CQT-Frames allein ist sie von
  einem Griff nicht zu trennen (Tiefband bringt nichts, s. oben). Bei
  Proberaum-Material ohne Gesangsspur (Backing-Tracks) stellt sich die
  Frage nicht; bei Aufnahmen mit Gesang kommen auf dichte Titel 1-3
  Chips je Minute dazu, die keine Anschläge sind.
- **Keine Ground Truth.** Ob die Nachschläge in Comfortably Numb (15 in
  neuneinhalb Minuten, z. B. 122,5 G, 175,2 D, 190,6 Bm) die Stellen sind,
  an denen die Band den Akkord wirklich neu setzt, entscheidet das Ohr im
  Proberaum. Die Schwellen (6 dB, 2 Schläge) sind erste Werte, nicht
  kalibriert.
- Die Kontrollfläche spielt weiter aus der Zeitleiste, nicht aus den
  Events - ein Nachschlag löst sie nicht neu aus. Wäre als akustische
  Bestätigung denkbar.
- Das 93-ms-Raster: Der Anschlag liegt bis zu einem Frame hinter dem
  Audio-Ereignis. Eine Feinsuche wie `refine_boundary` (23-ms-Raster,
  Onset-Stärke) wäre möglich, kostet aber je Nachschlag ~100 ms Rechenzeit.

## 7. Zweiter Weg: takt-synchron mit Audio-Bestätigung - auch verworfen

Gebaut nach 5.1, Weg 1: Kandidaten sind nur die Einsen des Beat-Rasters
innerhalb eines laufenden Segments (mindestens 0,75 s nach dem Onset, 0,35 s
vor der nächsten Grenze). Bestätigt wird eine Eins, wenn die harmonische
Anschlagstärke dort (HPSS-Harmonikanteil, Onset-Stärke im 23-ms-Raster,
±120 ms um die Taktlinie, wie `btc.refine_boundary`) mindestens 60 % der
Stärke am Anfang desselben Segments erreicht - der Segmentanfang als
Referenz, die sich je Song und Segment selbst kalibriert. Eine Messung
kostet ~140 ms, einmal je Eins und einmal je Segmentanfang.

Offline gegen die Phrasensplits (C nach C an Taktanfängen) sah das gut aus:

| Titel | Einsen in laufenden Segmenten | davon Phrasensplits | Verhältnis zum Segmentanfang |
|---|---|---|---|
| Let It Be | 15 | 15 | Median 1,17 |
| Eight Days a Week | 13 | 7 (übrige 6: 0,96) | Median 1,05 |
| Something | 2 | 1 | 0,84 |

Das Verhältnis liegt an Taktanfängen fast immer bei ~1: **Die Band spielt
an jeder Eins so stark wie am Segmentanfang.** Genau das war im Proberaum
das Problem (Sailing to Philadelphia, Teile mit Wechselbass): An jeder Eins
kam der Grundakkord als Chip, "extrem unruhig". Offline bestätigt: 138 der
263 Einsen des Beat-Modells liegen in laufenden Segmenten, 134 davon
bestehen die Schwelle 0,6 (24 je Minute). Dazu zwei Befunde:

- Das Beat-Modell setzt in Sailing die Eins **alle zwei Schläge** (263 Einsen
  in 330 s bei 99 bpm) - der halbe Puls des Stücks. Kandidaten gibt es damit
  doppelt so oft wie Takte.
- Die Bassnote auf der Eins bestätigt den Anschlag: Die Onset-Stärke
  enthielt das Bassregister, und mit Wechselbass ist auf jeder Eins ein
  kräftiger harmonischer Anschlag - des Basses, nicht des Akkords.

Nachgebaut wurde daraufhin die ursprüngliche Klingbedingung: Seit dem
letzten Anschlag des Segments (Onset oder voriger Nachschlag) mindestens
drei Schläge, und in dieser Zeit die Akkordton-Energie oberhalb des
Bassregisters (ab C3) nie um 3 dB gesprungen; die Anschlagstärke ebenfalls
erst ab C3 gemessen. Damit blieben in Sailing 18 von 134 (3,3 je Minute),
in Let It Be 2 von 15 - die Phrasensplits fallen zu Recht weg, dort spielt
das Klavier jeden Schlag. Der Proberaum-Eindruck: **schlechter**, nicht
besser. Die übrigen Treffer sind Stellen, an denen Gitarre und Keys gerade
leise sind und der Bass die Eins setzt - musikalisch kein Nachschlag des
Akkords, aber für jede Messung an diesem Signal einer.

### Warum die Idee nicht trägt

Der Nachschlag, den man zeigen wollte - der Akkord klingt aus, dann ein
bewusster neuer Anschlag -, kommt in Bandmusik mit Bass und Schlagzeug
fast nicht vor: Irgendwer spielt immer auf der Eins. Jede Messung findet
deshalb entweder jede Eins (unruhig) oder, mit Klingbedingung, die
Stellen, an denen zufällig nur der Bass spielt (falsch). Die einzige
Information, die der Spieler wirklich brauchte, steht schon da: der
Akkordwechsel. Für lange Akkorde bleibt die Zeitstruktur sichtbar - die
Taktstriche laufen weiter.

Was aus der Exploration bleibt: die Messmethodik (Phrasensplits als
Ground Truth für Wiederholungen, Stems zur Zuordnung Schlagzeug/Gesang,
Segmentanfang als song-eigene Referenz für Anschlagstärke) und die
Erkenntnis, dass das Beat-Modell bei halbem Puls die Eins alle zwei
Schläge setzt - das betrifft auch die Taktstriche der Anzeige.

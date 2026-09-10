# Tempo und Takt: Wie aufwaendig sind dezente Taktstriche in der Zeitleiste?

Stand: 2026-09-10 · Status: **Exploration mit zwei Machbarkeitsmessungen,
kein Produktcode geaendert.** Baut auf
[zeitleiste-redesign.md](zeitleiste-redesign.md) (Publish-once-Kanal) und
dem Timing-Abschnitt in [tests/reference/README.md](../../tests/reference/README.md)
auf.

> **Antwort in einem Satz:** Das *Tempo* ist billig und bei geradem Pop/Rock
> stabil (~30 ms je Hop, librosa reicht); der *Takt* - also wo die Eins liegt -
> ist der teure Teil, laesst sich aber fuer eine erste Fassung aus den schon
> vorhandenen Akkordwechseln abstimmen, und die Taktstriche selbst sind eine
> zweite Chip-Art auf dem bestehenden Laufband. Grob: 2-3 Tage fuer ein
> Beat-Raster, 4-6 Tage bis zu vertrauenswuerdigen Taktstrichen mit
> Messgeschirr - unter der Bedingung, dass Taktstriche bei Unsicherheit
> *weggelassen* werden statt falsch zu stehen.

---

## 1. Das Beduerfnis

Wer ohne Leadsheet einsteigt, braucht zwei Dinge: den Akkord und die Stelle
im Takt, an der man ihn setzt. Den Akkord liefert das Laufband mit Vorlauf.
Die Eins muss man bisher selbst hoeren - was mit Vorlauf paradox ist: Der
Chip sagt "G in 1.3 s", aber ob das die Eins des naechsten Taktes oder ein
Wechsel auf der Drei ist, sieht man nicht. Dezente Taktstriche im Laufband
beantworten genau das, ohne ein zweites Display und ohne Zaehlen.

Produktpruefung gegen das Prinzip "minimales Jam-Tool, null Anlauf": Taktstriche
dienen dem Mitspiel-Fluss (A), nicht dem Lernen (B) - **wenn** sie nie in die
Irre fuehren. Ein falscher Taktstrich ist schlimmer als keiner, weil man ihm
beim Einstieg blind vertraut. Daraus folgt die wichtigste Entwurfsregel unten:
**Konfidenz-Gate, sonst nichts zeichnen.**

Der Wunsch steht seit dem ersten Entwurf in der Liste
([first-draft.md](first-draft.md): "Taktanzeige", "Takt", "Tempo") und ist
im Gitarrenmodus bewusst als Nicht-Versprechen gefuehrt
([gitarrenmodus.md](../gitarrenmodus.md): "keine Rhythmus- oder
Takterkennung"). Der harmonische Interpreter hat Beat/Taktposition als
"Aufwand hoch, Nutzen mittel" eingestuft - dort als Erkennungs-Kontext. Hier
geht es um etwas anderes: **Anzeige**, nicht Akkordqualitaet.

## 2. Drei Fragen, drei Schwierigkeitsgrade

Das Feature zerfaellt in drei Teilprobleme mit sehr verschiedenem Preis:

| Teilproblem | Was gebraucht wird | Schwierigkeit |
|---|---|---|
| **Tempo** (Periode) | Beats pro Minute im aktuellen Fenster | leicht - Standard-Signalverarbeitung, laeuft in librosa |
| **Beat-Phase** | wo genau die Schlaege liegen | mittel - librosa liefert sie, aber ~110-190 ms neben den Akkordwechseln (gemessen, s. §4) |
| **Takt** (Eins, Taktart) | welcher Schlag die Eins ist; 4/4, 3/4, 6/8 | schwer - klassisch ein eigenes neuronales Modell (Downbeat-Tracking) |

Fuer *Taktstriche* braucht es alle drei. Fuer *Beat-Striche* (jeder Schlag ein
Strich, ohne Betonung) nur die ersten zwei - das ist die Rueckfallstufe.

## 3. Was schon da ist

- **Onset-Staerke** wird in `btc.refine_boundary` bereits berechnet
  (`librosa.onset.onset_strength`), allerdings nur auf einem 1,5-s-Ausschnitt
  um eine frische Grenze. Die Beat-Verfolgung braucht dieselbe Huellkurve
  ueber das ganze 10-s-Fenster; das ist ein Aufruf (19 ms, s. §4).
- **Der Analysetakt** (`ANALYSIS_HOP` 0,25 s, Fenster 10 s) ist fuer
  Beat-Tracking komfortabel: 10 s sind 15-25 Takte, genug fuer eine stabile
  Periode.
- **Akkordwechsel mit Onset** liegen in der Zeitleiste (`timeline`) und im
  Ledger - sie sind das billigste Downbeat-Signal ueberhaupt, s. §4.2.
- **Der Publish-once-Kanal** und das Laufband: Chips werden aus `at` per
  `transform` positioniert (`animate()` in index.html). Ein Taktstrich ist
  ein Chip ohne Text - dieselbe Uhr, dieselbe Formel, derselbe Horizont.
- **Hop-Budget** (audio-aussetzer-analyse.md): Hop gesamt 170 ms auf dem
  Entwicklungsrechner, 265 ms mit Verfeinerung; das 250-ms-Raster reisst
  dort schon gelegentlich. 30 ms mehr sind tragbar, aber nicht gratis - auf
  dem Z820 ist die Reihenfolge Puffer -> gc.freeze -> refine-Thread erst
  einmal wichtiger (s. dort).

## 4. Machbarkeitsmessungen (2026-09-10)

Zwei Skripte, beide gegen das Referenzset und drei Realaudio-Dateien:

- [tests/reference/messung_tempo_fenster.py](../../tests/reference/messung_tempo_fenster.py):
  gleitende 10-s-Fenster im 1-s-Raster (wie der Live-Pfad sie sieht),
  `librosa.beat.beat_track` (dynamische Programmierung) und
  `librosa.feature.tempo` (Tempogramm). Rechenzeit, Streuung, Oktavfehler.
- [tests/reference/messung_takt_eins.py](../../tests/reference/messung_takt_eins.py):
  annotierte Akkordwechsel (Isophonics, Chroma-Korrelations-Offsets) auf ein
  librosa-Beat-Raster gelegt; Abstimmung "Wechsel-Index mod 4" als
  Eins-Schaetzer, global und in 10-s-Fenstern.

Alle Zahlen vom Entwicklungsrechner (2x Xeon E5-2690 v3). Kein Beat-Ground-
Truth vor Ort - die Tempo-Spalte ist Plausibilitaet, keine Trefferquote.

### 4.1 Tempo aus 10-s-Fenstern

| Datei | Median bpm | IQR | Fenster innerhalb 4 % | Oktavkipper | ms/Hop (Huellkurve + Tracker) |
|---|---|---|---|---|---|
| eight_days_a_week | 136,0 | 0,0 | 99 % | 0 % | 19 + 9 |
| its_too_late | 103,4 | 0,0 | 94 % | 0 % | 19 + 10 |
| peg | 117,5 | 0,0 | 100 % | 0 % | 20 + 9 |
| sting_faith | 99,4 | 0,0 | 100 % | 0 % | 19 + 9 |
| let_it_be | 143,6 | 7,6 | 54 % | 2 % | 19 + 9 |
| something | 136,0 | 1,7 | 63 % | 0 % | 41 + 9 |
| crazy_little_thing | 152,0 | 44,3 | 74 % | 25 % | 19 + 9 |
| misty (Trio, rubato) | 129,2 | 26,1 | 19 % | 0 % | 19 + 10 |

Lesart:

- **Kosten sind kein Thema.** ~30 ms je Hop fuer Huellkurve plus Tracker; die
  Huellkurve liesse sich rollend fuehren (nur die neuen 0,25 s rechnen), dann
  bleiben ~10 ms. Tempogramm und DP-Tracker liefern dieselben Medianwerte,
  der Tracker liefert die Beat-Phase gleich mit.
- **Gerader Pop/Rock ist stabil:** vier Titel ohne jede Streuung ueber 140
  Fenster.
- **Balladen kippen in die Oktave, und zwar konsistent:** Let It Be (gefuehlt
  ~72) und Something (gefuehlt ~66) werden durchgehend doppelt gemeldet. Fuer
  Taktstriche ist das doppelt fatal - ein Takt wird zu zweien. Crazy Little
  Thing zeigt das Gegenteil: 152 bpm in 150-s-Fenstern, 76 bpm ueber die
  ganze Datei (zweites Skript). Die Oktave ist die **Hauptfehlerquelle**, nicht
  die Periode.
- **Rubato (Misty) ist unbrauchbar** und wird es mit jedem Verfahren bleiben.
  Das ist der Fall fuer das Konfidenz-Gate.

### 4.2 Die Eins aus Akkordwechseln

| Track | bpm (global) | Wechsel auf Beat (±100 ms) | median \|dt\| | Stimmen je Schlagklasse | Konzentration | 10-s-Fenster einig mit global |
|---|---|---|---|---|---|---|
| something | 136 | 73 % | 60 ms | [15, 4, **76**, 2] | 78 % | 98 % |
| let_it_be | 144 | 48 % | 111 ms | [**107**, 11, 16, 25] | 67 % | 72 % |
| eight_days_a_week | 136 | 44 % | 111 ms | [**64**, 3, 7, 26] | 64 % | 76 % |
| its_too_late | 103 | 16 % | 187 ms | [**61**, 1, 4, 33] | 62 % | 58 % |
| crazy_little_thing | 76 | 0 % | 351 ms | [19, 18, 20, 35] | 38 % | 18 % |

Lesart:

- **Wo das Beat-Raster stimmt, sitzt die Eins.** Drei Titel konzentrieren
  zwei Drittel bis drei Viertel aller Wechsel auf *eine* Schlagklasse; die
  Abstimmung aus einem 10-s-Fenster trifft die globale Eins in 72-98 % der
  Fenster. Das ist die Papadopoulos-&-Peeters-Beobachtung (Akkordwechsel
  fallen auf Downbeats) mit dem Signal, das JamPilot ohnehin hat.
- **Die Konzentration ist ein eingebautes Konfidenzmass.** Crazy Little Thing
  mit 38 % (Zufall waere 25 %) darf keinen Taktstrich bekommen - und muss es
  auch nicht: dort ist schon die Beat-Phase falsch (0 % der Wechsel auf einem
  Beat, Median 351 ms daneben). Ein Gate bei ~60 % Konzentration trennt die
  Faelle in dieser Stichprobe sauber.
- **Die Beat-Phase von librosa ist das schwaechere Glied.** 16-73 % der
  annotierten Wechsel liegen innerhalb 100 ms eines Beats, der Median-Abstand
  60-190 ms. Das deckt sich mit dem frueheren Befund im Referenz-README
  ("librosas Beat-Phase liegt selbst ~160 ms neben den GT-Wechseln", weshalb
  Beat-Snap fuer Akkordgrenzen verworfen wurde). Fuer *Striche* ist das
  weniger schlimm als fuer Grenzen - 100 ms sind bei 120 bpm ein Fuenftel
  Schlag - aber die Phase muss gegen die Akkord-Onsets nachgezogen werden,
  nicht umgekehrt (s. §5, Schritt 2).
- Vorbehalt: 5 Titel, alle in-domain (60er-70er Pop/Rock, wie das BTC-Set);
  Alignment-Unsicherheit ±50 ms; keine echten Beat-Annotationen.
  Isophonics stellt fuer die Beatles-Titel auch Beat- und Downbeat-
  Annotationen bereit - das waere das Messgeschirr fuer die Umsetzung.

## 5. Umsetzungsskizze in Stufen

Jede Stufe ist fuer sich ausliefer- und messbar; keine setzt eine neue
Abhaengigkeit voraus.

### Stufe 1: Beat-Raster (Tempo + Phase), ~2-3 Tage

**Server** (`_display_loop`): je Hop `onset_strength` ueber das 10-s-Fenster,
`beat_track` darauf; daraus Periode und Phase des juengsten stabilen Bereichs
(nicht der Fensterrand - wie beim Edge-Guard fehlt dort Kontext). Ein kleiner
Zustand `BeatGrid` mit Tempo-Glaettung ueber Hops (Median der letzten ~8) und
Oktav-Regel (s. u.). Ausgabe: Beat-Zeitpunkte in Stream-Sekunden.

**Publish-once auch fuer Beats.** Beats, die unter die Commit-Grenze
rutschen, werden wie Events genau einmal committet (`ledger`-Nachbar, gleiche
`frontier`) und nie mehr verschoben. Zieht der Tracker die Phase nach, folgen
erst die *naechsten* Striche - ein einzelner unregelmaessiger Abstand ist
sichtbar und ehrlich, ein wandernder Strich waere Flackern durch die
Hintertuer. Das ist dieselbe Entscheidung wie beim Redesign der Zeitleiste;
sie muss nicht neu getroffen werden. Protokoll: ein weiteres Feld
`"beats": [{"at": 107.05, "n": 1}, ...]` im Fenster um die hoerbare Position,
geschnitten wie `committed`; `n` ist die Schlagnummer im Takt (Stufe 1: immer
0 = unbekannt).

**Oktav-Regel aus dem Akkordsignal:** Mittlere Akkorddauer im Fenster gegen die
Taktlaenge halten. Pop/Rock wechselt typisch alle 1-2 Takte; liegt die
mittlere Akkorddauer bei 4+ "Takten", ist das Tempo doppelt zu schnell,
Periode verdoppeln. Das ist eine Heuristik mit klarer Gegenprobe (Let It Be,
Something) und muss gemessen werden, bevor sie bleibt.

**Client** (index.html): eine zweite Chip-Art `.beat` - ein 1 px breiter,
sehr dunkler Strich (Ton wie `#nowlabel`, `#444` oder dunkler) in der
unteren Haelfte der Spur, unterhalb der Chips (die laufen auf 42 % Hoehe,
darunter ist frei - der Credits-Kommentar beschreibt genau diese Zone).
Position ueber dieselbe Formel wie die Chips (`NOW_PCT`, `horizon`), z-index
unter den Chips, `will-change: transform`. Kein Text, keine Zahl.

**Tests:** Synthetischer Klick-Track mit bekanntem Tempo/Phase durch
`_display_loop` (die Simulations-Infrastruktur aus 1.3.1 traegt das);
Beat-Commit-Semantik im Ledger-Stil (append-only, Mindestabstand).

### Stufe 2: Taktstriche (Eins), ~2-3 Tage zusaetzlich

- **Eins-Abstimmung** wie in §4.2: Akkord-Onsets der Zeitleiste (nicht nur
  des Ledgers, damit auch der Vorlauf mitzaehlt) auf das Beat-Raster legen,
  Index mod 4 zaehlen, mit Vergessensfaktor ueber Hops. Konzentration unter
  ~60 % -> keine Taktstriche, nur Beat-Striche (oder gar nichts, s. §6).
- **Phase an die Akkord-Onsets nachziehen:** Wo die Abstimmung eindeutig ist,
  liegt der wahre Downbeat auf dem (verfeinerten) Akkord-Onset, nicht auf
  librosas Beat. Der mittlere Versatz Beat->Onset korrigiert die Phase des
  Rasters. Das dreht die im README verworfene Richtung um: nicht Grenzen auf
  Beats schnappen, sondern Beats auf Grenzen.
- **Taktart:** 4/4 als Annahme. 3/4 und 6/8 kommen in Stufe 2 nicht - ein
  Walzer bekommt dann eine Abstimmung mit schwacher Konzentration (Wechsel
  landen auf 1 und 4 im 4er-Zyklus) und faellt sauber durchs Gate.
- **Anzeige:** Die Eins als etwas laengerer, etwas hellerer Strich; die
  anderen Schlaege bleiben Stufe-1-Striche oder werden ganz weggelassen
  ("dezent" spricht fuer: nur Taktstriche, keine Beat-Striche).
- **Messgeschirr:** Isophonics-Beat/Downbeat-Annotationen der Beatles-Titel
  laden, `messung_takt_eins.py` darauf umstellen: Downbeat-F-Measure (±70 ms,
  die MIREX-Konvention) statt Konzentration. Ohne diese Zahl bleibt Stufe 2
  ein Playtest-Gefuehl.

### Stufe 3: echter Downbeat-Tracker, Wochen

Fuer Taktarten jenseits 4/4, Balladen mit Halftime-Feel und schwach
akzentuierte Musik braucht es ein gelerntes Modell. Kandidaten und ihr Preis:

| Modell | Art | Echtzeit | Preis fuer JamPilot |
|---|---|---|---|
| madmom (RNN/TCN-Downbeat, Boeck) | Python/Cython, lange Referenz | offline; Online-Varianten vorhanden | **nicht installierbar** in der aktuellen Umgebung (NumPy 2, Python 3.12; letztes Release 2018) - muesste aus Git gebaut oder portiert werden |
| BeatNet (Heydari 2021) | CRNN + Partikelfilter, fuer *Online*-Betrieb gebaut | ja | PyTorch-Abhaengigkeit - dasselbe Bundling-Problem, das beim BTC mit dem NumPy-Port geloest wurde; Port waere die gleiche Groessenordnung Arbeit |
| Beat This! (Foscarin et al., ISMIR 2024) | Transformer, Stand der Technik | offline, Fensterbetrieb moeglich | PyTorch, ~20 M Parameter; NumPy-Port wie BTC denkbar, deutlich teurer |

Alle drei bringen den Downbeat direkt und wuerden §4.2 ueberfluessig machen.
Keiner ist ohne Port bundelbar. Stufe 3 lohnt nur, wenn Stufe 2 im Proberaum
an der Oktave oder an Nicht-4/4 scheitert - und das ist zuerst zu beobachten.

## 6. Entwurfsregeln, die vor dem Code feststehen sollten

1. **Kein Strich ist besser als ein falscher.** Konfidenz-Gate auf allen
   Ebenen: Tempo-Streuung ueber Hops, Konzentration der Eins-Abstimmung,
   Rubato-Erkennung (IQR). Misty bekommt nichts, und das ist richtig.
2. **Publish-once gilt auch fuer Striche.** Committete Beats stehen. Kein
   Client-Raster, das aus `bpm` und `phase` extrapoliert - das driftete
   sichtbar gegen die Chips und waere die Client-Uhrlogik, die das Redesign
   gerade abgeschafft hat.
3. **Dezent heisst: unter den Chips, ohne Text, ohne Zaehler.** Kein "1 2 3
   4", keine Tempo-Zahl im Laufband. Die Tempo-Zahl kann in die graue
   Statuszeile des Kontrollfensters, wenn ueberhaupt - dort steht heute
   "Now playing … · next G in 1.3 s", eine Tempozahl passt in dieselbe Zeile.
4. **Abschaltbar, wie das Griffbrett.** Wer die Eins hoert, will die Striche
   nicht; ein Schalter im Zahnrad, per Geraet, wie Instrument und Stufen.
5. **Record-Modus:** Beats gehoeren zum Mitschnitt wie die Events - gleicher
   Rueckhalt, gleiche Uhr, gleicher Sprung bei `epoch`. Kein Sonderfall, wenn
   die Beats durch denselben Ledger-Mechanismus laufen.

## 7. Aufwand, zusammengefasst

| Stufe | Ergebnis | Aufwand | Risiko |
|---|---|---|---|
| 1 | Beat-Striche, Tempo im Kontrollfenster | 2-3 Tage | Oktave bei Balladen; Phase ~100 ms neben dem Gefuehl |
| 2 | Taktstriche mit Eins, 4/4, Gate | +2-3 Tage, +1 Tag Messgeschirr | Eins-Abstimmung braucht Akkordwechsel - statische Passagen (ein Akkord ueber 16 Takte) verlieren die Eins; dann Rasterfortschreibung aus dem letzten sicheren Takt |
| 3 | Downbeat-Modell, alle Taktarten | Wochen (Port) | Bundling, Hop-Budget, Genre-Sensitivitaet wie beim BTC |

Zum Vergleich: Der Publish-once-Umbau der Zeitleiste war groesser als Stufe 1
und 2 zusammen, weil er die Semantik geaendert hat. Hier aendert sich keine
Semantik - es kommt eine zweite Ereignisart durch einen bestehenden Kanal.

## 8. Was ich *nicht* empfehlen wuerde

- **Tempo/Phase als Parameter an den Client** (`bpm`, `phase`) statt
  committeter Beats - s. Regel 2.
- **Beat-Raster gleich fuer die Akkordgrenzen nutzen** (der Vorecho-Rest von
  ~165 ms CQT-Vorecho, Befund aus der verworfenen Onset-Marge): Erst wenn die Phase in Stufe 2 an den
  Onsets haengt, ist das Raster besser als die Grenzen - vorher waere es die
  bereits verworfene Beat-Snap-Idee in neuem Gewand. Eigener Zweig, eigene
  Messung.
- **Mit Stufe 3 anfangen.** Das Downbeat-Modell loest die Oktave und die
  Taktart, aber die Anzeige-, Commit- und Gate-Fragen sind dieselben - und
  die klaert Stufe 1 fuer einen Bruchteil des Preises.

## 9. Naechste Schritte, falls es weitergeht

1. Isophonics-Beat-Annotationen fuer die vier Beatles-Titel besorgen und
   `messung_takt_eins.py` auf Downbeat-F-Measure umstellen (½ Tag). Das
   liefert die Zahl, an der Stufe 2 spaeter gemessen wird.
2. Oktav-Regel (Akkorddauer vs. Taktlaenge) auf den acht Dateien pruefen: Kippt
   sie Let It Be und Something richtig, ohne die vier stabilen zu verderben?
3. Stufe 1 im Zweig bauen, Hop-Budget auf dem Z820 nachmessen
   (erst Histogramm auf der Zielhardware, dann aendern, dann neu messen).
4. Proberaum: Beat-Striche eine Session lang an, mit der Frage "stoeren sie,
   wenn sie falsch sind?" - das entscheidet, ob Beat-Striche ohne Eins
   ueberhaupt ausgeliefert werden oder erst Stufe 2 sichtbar wird.

# Tempo und Takt: Wie aufwaendig sind dezente Taktstriche in der Zeitleiste?

Stand: 2026-09-10 · Status: **Exploration mit vier Messungen (zwei davon
gegen Isophonics-Beat-Ground-Truth), kein Produktcode geaendert.** Baut auf
[zeitleiste-redesign.md](zeitleiste-redesign.md) (Publish-once-Kanal) und
dem Timing-Abschnitt in [tests/reference/README.md](../../tests/reference/README.md)
auf.

> **Antwort in einem Satz:** Das *Tempo* ist billig (~30 ms je Hop); die
> *Eins* faellt, sobald ein korrektes Beat-Raster da ist, praktisch gratis aus
> den vorhandenen Akkordwechseln (Downbeat-F 1,00 auf Oracle-Beats); und ein
> korrektes Raster wuerde obendrein die Akkordgrenzen um mehr verbessern als
> alles bisher Gemessene (median 150 -> 60 ms, Viertel-Quantisierung). **Der
> Engpass ist das Raster selbst:** librosas Beat-Tracker trifft auf den
> Beatles-Titeln nur 23-54 % der Beats (F-Measure, ±70 ms) und liegt in der
> Phase 100-200 ms daneben - damit tragen weder Taktstriche noch
> Quantisierung. Der Aufwand haengt deshalb an einem echten Beat-Tracker
> (Stufe 3, Wochen), nicht an der Anzeige (Tage).

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

Vier Skripte. Die ersten beiden (vormittags) gegen Referenzset und drei
Realaudio-Dateien ohne Beat-Ground-Truth, das dritte (§4.3/4.4) gegen die am
selben Tag geholten Isophonics-Beat-Annotationen:

- [tests/reference/messung_tempo_fenster.py](../../tests/reference/messung_tempo_fenster.py):
  gleitende 10-s-Fenster im 1-s-Raster (wie der Live-Pfad sie sieht),
  `librosa.beat.beat_track` (dynamische Programmierung) und
  `librosa.feature.tempo` (Tempogramm). Rechenzeit, Streuung, Oktavfehler.
- [tests/reference/messung_takt_eins.py](../../tests/reference/messung_takt_eins.py):
  annotierte Akkordwechsel (Isophonics, Chroma-Korrelations-Offsets) auf ein
  librosa-Beat-Raster gelegt; Abstimmung "Wechsel-Index mod 4" als
  Eins-Schaetzer, global und in 10-s-Fenstern.

Alle Zahlen vom Entwicklungsrechner (2x Xeon E5-2690 v3). In §4.1/4.2 gibt
es noch keine Beat-Ground-Truth - die Tempo-Spalte dort ist Plausibilitaet;
§4.3 holt die Trefferquote nach.

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
  Alignment-Unsicherheit ±50 ms. Die Beat-Ground-Truth kam am selben Tag
  dazu (§4.3), sie bestaetigt die Lesart und verschaerft sie.

### 4.3 Gegen Isophonics-Beat-Annotationen (Beatles, drei Titel)

Isophonics liefert Beat- und Downbeat-Annotationen nur fuer die Beatles;
Queen und Carole King haben keine. Die drei Dateien liegen jetzt als
`tests/reference/<track>.beats` bei (Format `zeit schlagnummer`, 1 = Eins;
Quelle isophonics.net, dieselbe Zeitbasis wie die `.lab` - die Chordlabs im
Tarball sind byte-identisch mit den Repo-Kopien, die Chroma-Offsets gelten
also auch fuer die Beats). Skript:
[tests/reference/messung_takt_quantisierung.py](../../tests/reference/messung_takt_quantisierung.py).
librosa lief hier ueber den GANZEN Track - die besten Bedingungen, die es
bekommen kann; live (10-s-Fenster) wird es nicht besser.

**A/B - Tempo und Beats:**

| Track | GT bpm | librosa bpm | Verhaeltnis | Beat-F (±70 ms) | Phase median \|dt\| |
|---|---|---|---|---|---|
| let_it_be | 69,8 | 143,6 | ×2,06 | **0,23** | 211 ms |
| eight_days_a_week | 139,5 | 136,0 | ×0,97 | **0,39** | 94 ms |
| something | 66,3 | 136,0 | ×2,05 | **0,54** | 107 ms |

Ein Beat-Tracker nach Stand der Technik liegt auf solchem Material bei
F ≈ 0,9 und Phasenfehlern von 20-40 ms (Beat This!, ISMIR 2024; madmom-TCN).
librosa ist davon weit entfernt. Die Oktavkipper aus §4.1 sind gegen die
Ground Truth bestaetigt: exakt ×2 auf beiden Balladen. Und Eight Days a Week
zeigt, dass ein Tempo-Prior (z. B. "unter 120 bpm") das nicht loest: 136 bpm
sind dort *richtig*, bei Something *doppelt* - dieselbe Zahl, zwei
Wahrheiten. Die Oktave ist nur aus dem Metrum zu entscheiden, nicht aus dem
Tempo.

**C - Die Eins aus den ERKANNTEN BTC-Onsets** (nicht mehr aus GT-Wechseln wie
in §4.2, also das Signal, das live vorliegt):

| Track | Raster | Takt = 4 Beats: Konz / Downbeat-F | Takt = 8 Beats: Konz / Downbeat-F |
|---|---|---|---|
| let_it_be | librosa (×2) | 69 % / 0,23 | 35 % / 0,01 |
| let_it_be | Oracle-GT | 45 % / 0,00 | 26 % / 0,67 |
| eight_days_a_week | librosa | 78 % / 0,36 | 39 % / 0,23 |
| eight_days_a_week | Oracle-GT | 68 % / **1,00** | 35 % / 0,66 |
| something | librosa (×2) | 59 % / 0,53 | 40 % / **0,78** |
| something | Oracle-GT | 44 % / **1,00** | 24 % / 0,66 |

Lesart:

- **Mit korrektem Raster ist die Eins gratis.** Auf den GT-Beats trifft die
  Abstimmung aus den erkannten Akkord-Onsets bei Eight Days und Something
  *jede* Eins (F 1,00). Die Idee aus §4.2 traegt also auch mit dem Live-Signal
  - vorausgesetzt, das Raster stimmt.
- **Let It Be ist ein ehrlicher Sonderfall:** Die Wechsel liegen auf 1 *und*
  3 (C G Am F, je zwei Schlaege), die Abstimmung ist zwischen beiden
  unentschieden (45 %) und waehlt die Drei. Halbtakt-Ambiguitaet ist mit
  Akkordwechseln allein nicht loesbar; da hilft nur ein Downbeat-Modell -
  oder das Gate, das bei 45 % ohnehin zumacht.
- **Auf dem librosa-Raster ist die Downbeat-F genau so gut wie das Raster
  selbst** (0,23 / 0,36 / 0,53 gegen Beat-F 0,23 / 0,39 / 0,54). Die
  Abstimmung verliert nichts, das Raster ist der Deckel. Bei Something
  rettet die Takt=8-Hypothese den Oktavfehler (0,78), bei Let It Be nicht.

### 4.4 Quantisierung der Akkordgrenzen auf das Raster

Die Frage aus der Diskussion: Wenn der Takt steht, koennte man die
Akkordwechsel auf Achtel quantisieren und so den Zeitpunkt genauer machen.
Gemessen mit den BTC-Grenzen der Offline-Pipeline (roh = 93-ms-Raster,
fein = `refine_boundary` wie heute) gegen die annotierten Wechsel; geschnappt
wird auf den naechsten Rasterpunkt. Oracle = Raster aus den GT-Beats (die
Obergrenze, die ein perfekter Tracker erreichen wuerde).

| Track | Verfahren | median \|dt\| | ≤50 ms | ≤93 ms |
|---|---|---|---|---|
| let_it_be | heute (fein) | 157 ms | 20 % | 29 % |
| | fein → Viertel, Oracle | **64 ms** | 28 % | **79 %** |
| | fein → Achtel, Oracle | 75 ms | 19 % | 55 % |
| | fein → 16tel, Oracle | 124 ms | 12 % | 35 % |
| | fein → Viertel, librosa | 157 ms | 21 % | 31 % |
| | fein → Achtel, librosa | 168 ms | 19 % | 30 % |
| eight_days_a_week | heute (fein) | 149 ms | 14 % | 26 % |
| | fein → Viertel, Oracle | **41 ms** | **54 %** | **66 %** |
| | fein → Achtel, Oracle | 197 ms | 26 % | 33 % |
| | fein → 16tel, Oracle | 148 ms | 14 % | 35 % |
| | fein → Viertel, librosa | 156 ms | 21 % | 34 % |
| | fein → Achtel, librosa | 190 ms | 14 % | 32 % |
| something | heute (fein) | 105 ms | 20 % | 48 % |
| | fein → Viertel, Oracle | **58 ms** | 40 % | **80 %** |
| | fein → Achtel, Oracle | 70 ms | 34 % | 65 % |
| | fein → 16tel, Oracle | 82 ms | 30 % | 52 % |
| | fein → Viertel, librosa | 72 ms | 38 % | 63 % |
| | fein → Achtel, librosa | 118 ms | 28 % | 47 % |

(Die rohen 93-ms-Grenzen schneiden nach dem Schnappen durchweg schlechter ab
als die verfeinerten - die Verfeinerung bleibt also auch mit Raster noetig;
vollstaendige Zahlen im Skript-Output.)

Drei Befunde, alle drei mit Konsequenz:

1. **Ein korrektes Raster waere der groesste Timing-Hebel, den es je gab.**
   Viertel-Quantisierung auf Oracle-Beats drueckt den Median von ~150 auf
   40-64 ms und hebt den Anteil ≤93 ms von 26-48 % auf 66-80 %. Zum Vergleich:
   die asymmetrische Verfeinerung, der bislang beste Schritt, brachte
   187 → 117 ms. Der "CQT-Vorecho-Rest" von ~165 ms, der als "nur per
   Beat-Grid zu holen" notiert war, ist damit bestaetigt - er *ist* per
   Beat-Grid zu holen.
2. **Achtel sind zu fein, Viertel sind das richtige Raster - heute.** Der
   Grenzfehler liegt bei ~150 ms; ein Achtel bei 140 bpm ist 215 ms. Wer auf
   Achtel schnappt, landet regelmaessig auf dem *falschen* Achtel: Eight Days
   wird mit Achteln (197 ms) *schlechter als ohne Quantisierung* (149 ms).
   Sechzehntel sind Rauschen. Regel: Das Raster muss groeber sein als der
   Fehler, den es korrigieren soll. Erst wenn die Grenzen selbst unter ~80 ms
   liegen (was die Viertel-Quantisierung liefern wuerde), lohnt ein zweiter
   Schritt auf Achtel fuer Wechsel, die deutlich neben dem Viertel liegen
   (Vorhalte, Synkopen) - als Sonderfall mit Schwelle, nicht als Default.
3. **Mit dem librosa-Raster bringt Quantisierung nichts** (Let It Be, Eight
   Days: identisch zu heute; nur Something gewinnt, dessen Raster mit F 0,54
   das beste der drei ist). Das ist der im Referenz-README verworfene
   Beat-Snap, nun mit Ground Truth erklaert: nicht die Idee war falsch,
   sondern das Raster.

**Geht es ohne Modell? Phase aus den eigenen Onsets - gemessen, nein.**
Die naheliegende Abkuerzung: Periode von librosa (bei Pop/Rock stabil), die
Phase aber nicht von librosa, sondern als lokaler Median der Abweichung der
verfeinerten Akkord-Onsets zum naechsten Beat (±5 s) - das Raster wuerde sich
an die eigenen Grenzen haengen, die Quantisierung waere dann ein Entrauschen
ueber viele Onsets. Skript:
[tests/reference/messung_phase_aus_onsets.py](../../tests/reference/messung_phase_aus_onsets.py).

| Track | heute | Oracle-Beats | Oracle-Periode, Phase aus Onsets | librosa-Periode, Phase aus Onsets | dito, Spaet-Bias 50 ms raus |
|---|---|---|---|---|---|
| let_it_be | 157 ms / 29 % | 64 ms / 79 % | 150 ms / 36 % | 150 ms / 32 % | 116 ms / 43 % |
| eight_days_a_week | 149 ms / 26 % | 41 ms / 66 % | 171 ms / 26 % | 145 ms / 28 % | 134 ms / 37 % |
| something | 105 ms / 48 % | 58 ms / 80 % | 91 ms / 51 % | 86 ms / 52 % | 73 ms / 62 % |

Selbst mit der *richtigen* Periode (GT-Beats, absichtlich um 150 ms
verschoben) findet die Phase aus den Onsets den Beat nicht wieder: Die
Grenzfehler sind kein symmetrisches Rauschen um den Beat, sondern ein
breiter Nachlauf (Median +50 ms, Ausreisser bis 300 ms), und der Median der
Nachbarn zieht das Raster in denselben Nachlauf. Die Bias-Korrektur holt ein
Drittel des Weges, mehr nicht. **Die Phase muss aus dem Audio kommen**
(Schlagzeug, Anschlaege) - das ist genau das, was ein Beat-Tracker tut, und
was librosas Tracker auf diesem Material nur zu 23-54 % schafft.

Was 1-3 zusammen bedeuten: **Die Quantisierung macht den echten Beat-Tracker
zum lohnenden Investment.** Ohne sie war Stufe 3 "nur fuer Taktarten und
Balladen"; mit ihr ist sie der Weg zu Akkordgrenzen, die doppelt so genau
sind wie heute - und Taktstriche sind dann ein Nebenprodukt.

Vorbehalte: drei Titel; Oracle-Zahlen sind Obergrenzen (ein realer Tracker
mit 30 ms Phasenfehler landet dazwischen); Wechsel, die musikalisch *nicht*
auf dem Viertel liegen, werden durch Quantisierung falsch - der Anteil ≤93 ms
von "nur" 66-80 % auf Oracle ist zum Teil genau das, und ein Musiker moechte
den Vorhalt auf der Vier-und vielleicht sehen. Achtel-Schwelle, s. Befund 2.

## 5. Umsetzungsskizze in Stufen

Jede Stufe ist fuer sich ausliefer- und messbar; keine setzt eine neue
Abhaengigkeit voraus.

### Stufe 1: Beat-Raster (Tempo + Phase), ~2-3 Tage

**Server** (`_display_loop`): je Hop `onset_strength` ueber das 10-s-Fenster,
`beat_track` darauf; daraus Periode und Phase des juengsten stabilen Bereichs
(nicht der Fensterrand - wie beim Edge-Guard fehlt dort Kontext). Ein kleiner
Zustand `BeatGrid` mit Tempo-Glaettung ueber Hops (Median der letzten ~8) und
Oktav-Frage s. u. Ausgabe: Beat-Zeitpunkte in Stream-Sekunden.

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

**Oktav-Regel:** Urspruenglich war hier eine Heuristik aus Akkorddauer gegen
Taktlaenge vorgesehen. Nach §4.3 ist sie verworfen: Eight Days a Week (136 bpm
richtig) und Something (136 bpm, doppelt) sind aus Tempo und Akkorddauer
nicht zu unterscheiden. In Stufe 1 bleibt die Oktave ungeloest - Beat-Striche
auf einer Ballade erscheinen doppelt so dicht. Das Gate (§6) muss das
zulassen oder Balladen ganz ausblenden (Tempo > 120 und Konzentration der
Takt=8-Abstimmung hoch = Verdacht auf Halftime).

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

### Stufe 3: echter Beat-/Downbeat-Tracker, Wochen - nach §4.3/4.4 der eigentliche Weg

Fuer die Oktave, fuer Taktarten jenseits 4/4 und vor allem fuer ein Raster,
das die Quantisierung (§4.4) traegt, braucht es ein gelerntes Modell - librosa
liefert weder die Phase (100-200 ms) noch die Oktave. Kandidaten und ihr Preis:

| Modell | Art | Echtzeit | Preis fuer JamPilot |
|---|---|---|---|
| madmom (RNN/TCN-Downbeat, Boeck) | Python/Cython, lange Referenz | offline; Online-Varianten vorhanden | **nicht installierbar** in der aktuellen Umgebung (NumPy 2, Python 3.12; letztes Release 2018) - muesste aus Git gebaut oder portiert werden |
| BeatNet (Heydari 2021) | CRNN + Partikelfilter, fuer *Online*-Betrieb gebaut | ja | PyTorch-Abhaengigkeit - dasselbe Bundling-Problem, das beim BTC mit dem NumPy-Port geloest wurde; Port waere die gleiche Groessenordnung Arbeit |
| Beat This! (Foscarin et al., ISMIR 2024) | Transformer, Stand der Technik | offline, Fensterbetrieb moeglich | PyTorch, ~20 M Parameter; NumPy-Port wie BTC denkbar, deutlich teurer |

Alle drei bringen den Downbeat direkt und wuerden die Eins-Abstimmung zur
Plausibilitaetspruefung degradieren. Keiner ist ohne Port bundelbar. Der
naheliegende Weg ist derselbe wie beim BTC: Modell in PyTorch evaluieren
(scratch-venv, nicht im Projekt), dann NumPy-Port der Inferenz - Beat This!
ist ein Transformer wie BTC, das Port-Rezept existiert. Vor dem Port steht
eine Messung: liefert das Modell auf den drei Beatles-Titeln Beat-F > 0,9 und
Phase < 50 ms, und was kostet ein 10-s-Fenster auf CPU? Erst diese zwei Zahlen
entscheiden, ob Wochen gut angelegt sind.

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
| 3 | Downbeat-Modell, alle Taktarten, **Grundlage fuer Viertel-Quantisierung der Akkordgrenzen** | Wochen (Port), davor 1-2 Tage Evaluierung | Bundling, Hop-Budget, Genre-Sensitivitaet wie beim BTC |
| 3b | Viertel-Quantisierung der Grenzen auf das Modell-Raster | 2-3 Tage (Ledger-nah, wie refine) | erwarteter Gewinn median ~150 → 40-70 ms (Oracle-Obergrenze); Synkopen brauchen Schwelle |

Stufe 1 und 2 auf librosa-Basis liefern *Striche*, aber weder verlaessliche
Taktstriche (Downbeat-F 0,23-0,53) noch einen Quantisierungsgewinn. Sie sind
als Wegstueck zu Stufe 3 sinnvoll (Anzeige, Commit-Semantik, Gate, Tests
bleiben gleich), nicht als Endpunkt.

Zum Vergleich: Der Publish-once-Umbau der Zeitleiste war groesser als Stufe 1
und 2 zusammen, weil er die Semantik geaendert hat. Hier aendert sich keine
Semantik - es kommt eine zweite Ereignisart durch einen bestehenden Kanal.

## 8. Was ich *nicht* empfehlen wuerde

- **Tempo/Phase als Parameter an den Client** (`bpm`, `phase`) statt
  committeter Beats - s. Regel 2.
- **Das librosa-Raster fuer die Akkordgrenzen nutzen.** §4.4 zeigt: kein
  Gewinn, weil die Phase 100-200 ms daneben liegt - dieselbe verworfene
  Beat-Snap-Idee. Mit einem Modell-Raster ist es dagegen der groesste
  Timing-Hebel; dann aber auf *Viertel*, nicht auf Achtel (Befund 2).
- **Mit Stufe 3 anfangen.** Das Downbeat-Modell loest die Oktave und die
  Taktart, aber die Anzeige-, Commit- und Gate-Fragen sind dieselben - und
  die klaert Stufe 1 fuer einen Bruchteil des Preises.

## 9. Naechste Schritte, falls es weitergeht

1. ~~Isophonics-Beat-Annotationen besorgen~~ - erledigt (§4.3), drei Titel.
2. **Beat This! (und ggf. BeatNet) in einem Scratch-venv mit PyTorch
   evaluieren:** Beat-F, Downbeat-F, Phase auf den drei Beatles-Titeln plus
   den Realaudio-Dateien; CPU-Zeit je 10-s-Fenster. Ein Tag. Das ist die
   Entscheidungszahl fuer Stufe 3.
3. Faellt sie gut aus: Quantisierungsmessung (§4.4) mit dem *Modell*-Raster
   statt Oracle wiederholen - dann steht der reale Gewinn fest, bevor
   irgendetwas portiert wird.
4. Erst danach Port und Einbau; Anzeige (Stufe 1/2-Teile: Beat-Chips,
   Commit-Semantik, Gate) laesst sich parallel und tracker-unabhaengig
   bauen.
5. Oktav-Regel aus Stufe 1 (Akkorddauer vs. Taktlaenge) ist nach §4.3
   **verworfen**: Eight Days (136 richtig) und Something (136 doppelt) sind
   aus Tempo und Akkorddauer nicht zu trennen.

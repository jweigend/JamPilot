# Meilenstein-Vergleich: vor Modell-Optimierung, mit Modell-Optimierung, mit Takt

**Stand:** 2026-09-11 · Live-Simulation (`_display_loop` hop fuer hop, --delay 5)
auf den fuenf Isophonics-Referenztracks (`tests/reference/`) und dem Outro
von Telegraph Road (Dire Straits, 10:45-13:30, nicht im Repo) · Skripte
[`tests/reference/messung_meilensteine.py`](../../tests/reference/messung_meilensteine.py)
(Lauf) und
[`messung_meilensteine_auswertung.py`](../../tests/reference/messung_meilensteine_auswertung.py)
(Auswertung).

## 1. Was verglichen wurde

Die BTC-Gewichte sind Drop-ins, deshalb lassen sich **Modell** und
**Pipeline** als getrennte Achsen messen. Drei Gewichtssaetze, drei
Pipelines, sechs Kombinationen:

| Kuerzel | Gewichte (`btc_large_voca.npz`) | Pipeline |
|---|---|---|
| **p0+w0** = *vor Modell-Optimierung* | Original-BTC (7d8cb69, 08.08.) | Stand 23.08. (02cdb26): Zeitleiste VOR Publish-once, Einfrierzone 1,5 s |
| **p1+w1** = *mit Modell-Optimierung* (Releases 1.1.0-1.3.1) | iso-only (e7ad6f1, 25.08., MERT-Kampagne) | main (6d97c1e): Publish-once-Kanal, Mindestabstand, Verfeinerung 1.3.1 |
| **p2+w2** = *mit Takt* (heute) | v7 (b9cf896, 10.09.) | analysis/tempo-und-takt (ff0df29): Beat This!, Viertel-Snap, Vorwaertskorrektur 2 Frames, symmetrische Verfeinerung |
| p1+w0, p1+w2, p2+w1 | Zurechnung: was kommt vom Modell, was von der Pipeline |

Vier Dimensionen, jeweils das, was der Musiker sieht:

- **Akkordgenauigkeit**: der angezeigte Akkord je Hop (0,25 s) gegen die
  Annotation; Root, Triade, exakt; dazu die "stabile Mitte" (> 0,5 s von
  jedem annotierten Wechsel entfernt), die den Timing-Einfluss herausnimmt.
- **Flackern**: angezeigte Wechsel je Minute gegen annotierte Wechsel je
  Minute, Kurzsegmente unter 0,6 s je Minute, und Revisionen der
  *sichtbaren* Vorschau (wie oft das Label fuer eine feste kuenftige Zeit
  ueber die Hops umgeschrieben wird).
- **Rhythmische Genauigkeit**: finale Event-Onsets gegen die annotierten
  Wechsel (median |dt|, Anteil <= 93 ms, median dt als Vorzeichen), bei
  den drei Beatles-Titeln mit Beat-Annotation der Anteil der Wechsel, deren
  Event auf demselben Beat liegt wie der annotierte Wechsel; bei Telegraph
  Road der Anteil der Events, deren naechster Beat eine Taktlinie ist
  (Beat-Grid aus dem p2+w2-Lauf, fuer alle Konfigurationen dasselbe).
- **Tonart**: Anteil der Hops mit korrekter Tonart, Zeitpunkt der ersten
  korrekten, Anzahl der Tonartwechsel im Lauf.

## 2. Kernbefunde

**Rhythmus - die Modell-Optimierung hat einen Vorlauf eingebaut, der Takt
holt ihn zurueck.** Mit den Originalgewichten liegen die Grenzen nahe am
Wechsel (median dt -13 bis +39 ms auf vier von fuenf Titeln). Die
nachtrainierten Gewichte (iso-only, v7) setzen sie 100-230 ms **zu frueh**
(median dt -93 bis -229 ms). Synthetisch nachgemessen (Wechsel bei exakt
bekannter Zeit, gleitende 10-s-Fenster): Original -56 bis -127 ms,
iso-only/v7 -220 bis -277 ms. Ursache (Nachtrag, nach Ausschluss der
Chroma-Offsets - deren Beat-Residuen liegen bei median -41 ms, also nicht
frueh): **die gestueckelte CQT in `features_from_audio` driftet.** Ein
10-s-Chunk liefert 108 Frames, 108 Frames sind aber 10,031 s; die
Feature-Zeitachse laeuft der Audio-Zeit um +31 ms je Chunk davon, +558 ms
am Ende eines 3-Minuten-Titels. Das ML-Repo trainiert mit derselben
Funktion und rasterisiert die Labels auf der echten Zeitachse - das Label
hinkt dem Feature zum Songende hin bis zu 0,5 s hinterher, und ein Modell,
das das im Mittel ausgleicht, setzt seine Grenzen zu frueh. Der Live-Pfad
ist nicht betroffen (ein Fenster = ein Chunk mit korrektem Offset),
`jampilot analyze` und alle Offline-Timing-Messungen sind es: Eight Days,
dieselben Gewichte, Chunks ab 0 gegen gleitende Fenster - Original +136
gegen -63 ms, iso-only -21 gegen -243 ms. Der im Referenz-README
dokumentierte "Nachlauf der rohen BTC-Grenze" war dieser Drift. Die
Vorwaertskorrektur um zwei Frames im Takt-Stand ist damit die Kompensation
eines Trainingsartefakts. Sie wirkt:
median |dt| ueber die fuenf Titel 138 ms (p1+w1) -> 72 ms (p2+w2), auf
Eight Days 198 -> 35 ms; Anteil auf demselben GT-Beat 58 -> 85 %.

| median \|dt\| in ms | p0+w0 | p1+w0 | p1+w1 | p1+w2 | p2+w1 | p2+w2 |
|---|---|---|---|---|---|---|
| Crazy Little Thing | 63 | 68 | 140 | 152 | 36 | **42** |
| Eight Days a Week | 127 | 119 | 198 | 235 | 40 | **35** |
| It's Too Late | 156 | 125 | **106** | 106 | 215 | 169 |
| Let It Be | 96 | 87 | 127 | 120 | 73 | **73** |
| Something | 70 | 59 | 120 | 134 | 42 | **42** |
| Mittel | 102 | 92 | 138 | 149 | 81 | **72** |

| gleicher GT-Beat / Telegraph naechster Beat = Taktlinie | p0+w0 | p1+w0 | p1+w1 | p1+w2 | p2+w1 | p2+w2 |
|---|---|---|---|---|---|---|
| Eight Days a Week | 87 % | 88 % | 58 % | 51 % | 84 % | 85 % |
| Let It Be | 90 % | 91 % | 88 % | 89 % | 93 % | 93 % |
| Something | 97 % | 97 % | 92 % | 90 % | 95 % | 93 % |
| Telegraph Road (Taktlinie / Schlag davor) | 58 / 42 | 70 / 30 | 49 / 51 | 56 / 44 | 58 / 42 | 62 / 38 |

Lesart: Die Releases 1.1.0-1.3.1 (p1+w1) waren rhythmisch die *schwaechste*
Etappe - schlechter als der Stand vor der Modell-Optimierung (p1+w0 mit
denselben Pipeline-Regeln: 92 ms). Der Takt-Stand ist die beste, mit einer
Ausnahme: It's Too Late (Klavierballade, weiche Einsaetze) liegt schon mit
nachtrainierten Gewichten *spaet* (+140 ms) und wird durch die Korrektur
spaeter. Der Bias ist materialabhaengig.

**Flackern - Publish-once hat die Vorschau beruhigt, der Takt die
Kurzsegmente.** Die Zeitleiste vor Publish-once schrieb die sichtbare
Vorschau 17-82 mal je Minute um (Telegraph 68); seit dem Publish-once-Kanal
sind es null - was steht, bleibt. Dafuer erzeugte der Kanal mehr
Kurzsegmente unter 0,6 s (Mindestabstand 0,25 s statt Einfrierzone):
7-22 je Minute gegen 0,4-6 davor. Der Takt-Stand halbiert das wieder
(3-9 je Minute) und liegt mit den angezeigten Wechseln je Minute am
naechsten an der Annotation.

| Kurzsegmente < 0,6 s je Minute | p0+w0 | p1+w0 | p1+w1 | p1+w2 | p2+w1 | p2+w2 |
|---|---|---|---|---|---|---|
| Crazy Little Thing | 6 | 17 | 16 | 16 | 12 | 9 |
| Eight Days a Week | 0,4 | 8 | 7 | 6 | 3 | 3 |
| It's Too Late | 0,5 | 14 | 12 | 11 | 9 | 9 |
| Let It Be | 2 | 12 | 7 | 7 | 5 | 3 |
| Something | 3 | 18 | 22 | 9 | 9 | 8 |
| Telegraph Road | 2 | 22 | 12 | 9 | 10 | 7 |

| angezeigte Wechsel je Minute (Annotation) | p0+w0 | p1+w1 | p2+w2 |
|---|---|---|---|
| Crazy Little Thing (35) | 40 | 48 | 43 |
| Eight Days a Week (33) | 29 | 36 | 33 |
| It's Too Late (25) | 26 | 37 | 35 |
| Let It Be (39) | 33 | 38 | 36 |
| Something (32) | 33 | 49 | 36 |

Die niedrigen Kurzsegment-Zahlen von p0 sind kein Verdienst: Die alte
Zeitleiste zeigte weniger Wechsel als annotiert (Eight Days 29 gegen 33)
und schrieb die Vorschau laufend um - die Ruhe des JETZT-Akkords war mit
Revisionen im Vorlauf erkauft.

**Akkordgenauigkeit - im Ganzen gleich, in der stabilen Mitte besser,
mit einer Regression bei v7.** Root-Accuracy des angezeigten Akkords ueber
die fuenf Titel: p0+w0 86 %, p1+w1 82 %, p2+w2 86 %. Die nachtrainierten
Gewichte verloren in p1 an den Grenzen (der fruehe Vorlauf zeigt den neuen
Akkord, bevor er klingt); in der stabilen Mitte sind sie besser (Crazy
Little Thing Root 87 -> 93 %, exakt 82 -> 91 %). Mit der Korrektur im
Takt-Stand kommt der Gesamtwert zurueck auf das Niveau von p0, bei
besserer Mitte. **Regression:** v7 vereinfacht auf It's Too Late reiche
Qualitaeten zu Dur - exakt 73 -> 62 % (stabile Mitte 80 -> 68 %),
Verwechslungen 6 -> Dur 66 -> 136 Hops, maj7 -> Dur 39 -> 55. Root bleibt
gleich (87-89 %). Das ist der im Nachtrainings-Bericht befuerchtete
Vereinfachungs-Bias der Charts, auf Klavier-Jazzpop sichtbar.

| Root-Acc / exakt (angezeigt, alle Hops) | p0+w0 | p1+w0 | p1+w1 | p1+w2 | p2+w1 | p2+w2 |
|---|---|---|---|---|---|---|
| Crazy Little Thing | 84 / 78 | 85 / 78 | 78 / 73 | 79 / 75 | 85 / 80 | 84 / 80 |
| Eight Days a Week | 94 / 90 | 91 / 88 | 86 / 82 | 85 / 83 | 94 / 91 | 95 / 93 |
| It's Too Late | 89 / 76 | 87 / 75 | 89 / 73 | 88 / 63 | 87 / 71 | 87 / 62 |
| Let It Be | 85 / 82 | 86 / 82 | 82 / 79 | 82 / 79 | 85 / 81 | 86 / 82 |
| Something | 80 / 71 | 80 / 70 | 76 / 69 | 79 / 72 | 79 / 72 | 80 / 73 |

| Root-Acc / exakt, stabile Mitte | p0+w0 | p1+w1 | p2+w2 |
|---|---|---|---|
| Crazy Little Thing | 87 / 82 | 91 / 86 | 93 / 91 |
| Eight Days a Week | 100 / 97 | 100 / 96 | 100 / 99 |
| It's Too Late | 98 / 83 | 99 / 80 | 98 / 68 |
| Let It Be | 89 / 89 | 88 / 87 | 89 / 89 |
| Something | 88 / 77 | 86 / 78 | 88 / 79 |

**Tonart - seit der Modell-Optimierung stabil, ein Titel in allen
Versionen falsch.** Der Stand vor Publish-once (Ein-Skalen-Schaetzer)
sprang: Crazy Little Thing 42 % korrekte Hops bei 8 Tonartwechseln, It's
Too Late 33 % bei 6 (erste korrekte Tonart nach 28 s). Seit dem
Zwei-Skalen-Schaetzer mit Label-Votum (1.1.0) sind es 98-100 % ohne einen
Wechsel, auf allen Staenden danach identisch - die Gewichte spielen keine
Rolle. Eight Days a Week (D-Dur) zeigt in *jeder* Version E-Dur bzw.
h-Moll: Der E-Dur-Akkord der Strophe (D - E - G - D) zieht den Schaetzer
zur Doppeldominante. Kein Versionsunterschied, eine bekannte Schwaeche.

| Tonart korrekt (Anteil Hops) / Wechsel | p0+w0 | p1+w1 | p2+w2 |
|---|---|---|---|
| Crazy Little Thing (D-Dur) | 42 % / 8 | 98 % / 0 | 98 % / 0 |
| Eight Days a Week (D-Dur) | 6 % / 4 | 3 % / 2 | 3 % / 2 |
| It's Too Late (a-Moll) | 33 % / 6 | 99 % / 0 | 99 % / 0 |
| Let It Be (C-Dur) | 100 % / 0 | 100 % / 0 | 100 % / 0 |
| Something (C-Dur) | 93 % / 2 | 99 % / 0 | 99 % / 0 |

## 3. Die drei Versionen in einem Satz

- **Vor Modell-Optimierung (p0+w0):** rhythmisch ordentlich (102 ms), Akkorde
  auf heutigem Niveau, aber eine Vorschau, die sich staendig umschrieb, und
  eine Tonart, die auf zwei von fuenf Titeln sprang.
- **Mit Modell-Optimierung (1.1.0-1.3.1, p1+w1):** Vorschau und Tonart
  ruhig, in der stabilen Mitte genauere Qualitaeten - aber die
  nachtrainierten Gewichte brachten einen Vorlauf von 100-230 ms mit, der
  Timing (138 ms) und Grenzgenauigkeit kostete und mehr Kurzsegmente
  hinterliess.
- **Mit Takt (p2+w2):** rhythmisch die beste Etappe (72 ms, 85-93 % auf dem
  richtigen Beat), Kurzsegmente halbiert, Akkorde im Ganzen wie vor der
  Optimierung und in der Mitte besser, Tonart wie 1.1.0. Offen: v7s
  Vereinfachung reicher Qualitaeten (It's Too Late) und der spaete Bias auf
  weichem Material.

## 4. Konsequenzen

1. **CQT am Stueck (oder Frame-Zeiten chunkweise korrekt abbilden),
   dann nachtrainieren.** Uebergeben an das ML-Repo:
   `../JamPilotML/docs/rueckmeldung-jampilot-2026-09-11.md`. In JamPilot
   selbst betrifft der Drift `jampilot analyze` und die Offline-Messungen
   (tests/reference/README.md, Timing-Tabellen) - die Live-Zahlen nicht.
   Ein ohne Drift trainiertes Modell braeuchte die Vorwaertskorrektur
   (vermutlich) nur noch zum Teil - dann `BTC_ONSET_SHIFT` neu messen.
2. **v7 gegen iso-only auf reichen Qualitaeten pruefen** (It's Too Late
   exakt 73 -> 62 %), bevor v7 als Gewinn gilt; Root ist gleich, das
   Timing ist gleich, der Unterschied liegt in 6/maj7 -> Dur.
3. **Eight Days a Week als Tonart-Testfall** (Doppeldominante in der
   Strophe) - in keiner Version richtig.

## 5. Nachtrag: Ergebnis (2026-09-11, abends)

- **CQT am Stueck** in beiden Repos (`chordml.features` und
  `jampilot.btc.features_from_audio`, bitgleich). Nachtraining im ML-Repo
  auf korrekter Achse: der Vorlauf ist weg (Grenzen +19 … +40 ms median),
  das Isophonics-Nachtraining bringt auf korrekter Achse nichts mehr
  (`iso_only_2` = Original ± 0), die Destillation `v7_2b` gewinnt den
  Bibliotheks-Radar (52,1 % gegen Original 48,1 %, `iso_only_2` 49,6 %)
  und maj7/m7, verliert aber Sextakkorde (0,16 gegen 0,47) - Punkt 2 oben
  ist damit beantwortet: der Bias kommt vom Teacher, nicht vom Drift.
- **JamPilot:** `v7_2b` als Drop-in, `BTC_ONSET_SHIFT` ein Frame statt
  zwei (Messmatrix in tests/reference/README.md, Abschnitt
  "Nachtrainierte Gewichte auf zeittreuer CQT"). Im Live-Pfad sind alle drei
  Kandidaten beim Timing gleich; Telegraph Road 69 -> 83 % auf der Linie.
- **Offen:** Proberaum; Eight Days als Tonart-Testfall (Punkt 3).

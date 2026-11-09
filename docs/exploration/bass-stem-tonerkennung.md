# Bass-Stem fuer die Tonerkennung? Messung und Uebergabe (2026-11-09)

Branch `exploration-bass-stem` (zweigt von `feature/wellenform-laufband`
ab). Stand: Der Open-Unmix-Stem speist **nur die Huellkurve** unter dem
Laufband (stems.py, `docs/exploration/bass-stem-huellkurve.md`). Die
Basston-Erkennung (`bass.slash_note` auf dem Tiefband-Chroma der BTC-CQT,
`cli.py` -> `BassTrack`) arbeitet unveraendert auf dem **Mix**. Diese Notiz
misst, was der Stem fuer die Erkennung braechte - und was offen ist, bevor
man ihn dort einbaut. **Nicht einfach einbauen:** die Zahlen unten stammen
aus sieben Titeln; auf dem Arbeits-PC liegt deutlich mehr Material, damit
zuerst breiter messen.

## 1. Was gemessen wurde

`tests/reference/messung_bass_stem_tonerkennung.py` - dieselbe Kette wie in
der Pipeline, einmal mit der CQT des Mixes, einmal mit der CQT des
getrennten Stems (UMX-HQ int8 aus `jampilot/data`, 6-s-Bloecke mit 1 s
Rand bei 44,1 kHz, fuer die CQT auf 22,05 kHz). Die Akkordlabels kommen in
beiden Faellen aus derselben Quelle, nur das Bass-Chroma wechselt.

    .venv/bin/python tests/reference/messung_bass_stem_tonerkennung.py gt [--detail] [titel ...]
    .venv/bin/python tests/reference/messung_bass_stem_tonerkennung.py oktave <mix.mp3> <bass-stem.mp3>
    .venv/bin/python tests/reference/messung_bass_stem_tonerkennung.py oktave --stems <ordner>

Drei Referenzen:

- **pYIN auf der echten isolierten Bassspur** (wie messung_bass_oktave.py):
  Sailing to Philadelphia (305 Noten >= 280 ms), Echoes (488 Noten).
  Tonklasse je Note mit `bass.dominant`, Oktave mit der Regel "tiefste
  Oktave >= 30 % des staerksten Oktavbins" (hier nachgebaut - s. §4).
- **Isophonics-Slashes** (5 Titel in tests/reference, Pooling 2 s ab Onset,
  Akkord aus der Annotation, wie messung_bass_gt.py).

## 2. Ergebnisse

### Je Referenznote (pYIN auf dem echten Stem)

| | Sailing Mix | Sailing Stem | Echoes Mix | Echoes Stem |
|---|---|---|---|---|
| Tonklasse richtig | 94,1 % | **98,0 %** | 94,7 % | **97,7 %** |
| leer (kein klarer Gewinner) | 4,9 % | 1,6 % | 4,5 % | 2,0 % |
| falsch | 1,0 % | 0,3 % | 0,8 % | 0,2 % |
| Oktave richtig (bei richtiger Tonklasse) | 100 % | 100 % | 96,5 % | 96,4 % |

### Segmentweise durch die Kette (BTC-Labels aus dem Mix, slash_note, Pooling 2 s)

| | Sailing Mix | Sailing Stem | Echoes Mix | Echoes Stem |
|---|---|---|---|---|
| BTC-Segmente | 148 | 148 | 501 | 501 |
| davon mit Bassnote | 103 | **132** | 318 | 326 |
| davon mit Referenz | 102 | 131 | 248 | 264 |
| Tonklasse richtig | 98 % | 98 % | 96 % | 97 % |
| Oktave richtig | 98 % | 98 % | 92 % | 94 % |

### Isophonics (385 Grundton-Segmente, 27 Umkehrungs-Segmente)

| | Mix | Stem |
|---|---|---|
| falsche Slashes auf Grundton-Segmenten | 1 (Eight Days, D/A) | **0** |
| leer auf Grundton-Segmenten | 35 % | **29 %** |
| Umkehrungen gefunden | 11/27 | 11/27 |
| falscher Ton auf Umkehrungs-Segmenten | 3/27 | 6/27 |

Die sechs "falschen Toene" des Stems, alle in *Something* (`--detail`):
drei Em/B, die Mix UND Stem als G messen (kein Stem-Problem); zwei C/G, wo
der Mix G sagt (wie annotiert - mutmasslich die Gitarre) und der Stem C,
also den Grundton (Anzeige dann "C" statt "C/G", kein falscher Slash); ein
Em/B, das der Stem als G liefert, wo der Mix leer blieb. Dagegen findet der
Stem die G/B-Umkehrung viermal statt zweimal; in *Let It Be* bleibt eine
von sieben Em/G-Umkehrungen auf dem Stem leer.

### Lesart

Der Gewinn liegt weniger in der Trefferquote (die ist auf dem Mix schon
hoch) als in der **Ausbeute**: Die Dominanzhuerde (`MIN_DOMINANCE`) faellt
auf dem Stem deutlich seltener durch - 29 Segmente mehr mit Bassnote bei
Sailing, ein Drittel weniger leere Grundton-Segmente bei Isophonics, bei
gleicher oder leicht besserer Fehlerrate. Die Oktave aendert sich nicht
messbar. Wo der Stem "anders" liegt als die Annotation, hoert er den
Bassisten, nicht die Gitarre - was fuer den Bass-Modus gerade richtig ist,
fuer Slash-Namen aber ein Zielkonflikt bleibt (Isophonics annotiert die
Harmonie, nicht den Bassisten).

## 3. Was fuer den Einbau zu klaeren waere

1. **Breiter messen.** Mehr Titel, vor allem solche mit lautem Schlagzeug,
   Synth-Bass, Kontrabass, Doppelungen (Gitarre spielt den Bass mit) und
   Stellen ohne Bass (dort darf der Stem nichts erfinden - `leak` in
   bass-stem-huellkurve.md lag bei 0,33 fuer Sailing). Das
   Isophonics-Skript nimmt weitere `.lab`-Titel ohne Aenderung auf
   (TRACKS-Tabelle mit Offset).
2. **Zeitliche Lage.** `BassTrack` braucht Frames bis zur Analysefront;
   der Stem endet 0,5 s Kontext plus eine Hop-Laufzeit davor (stems.py).
   Entweder der Bass zum Akkord-Onset wird erst einen Hop spaeter gesetzt
   (das Nachruecken `b_up` gibt es schon), oder der Kontext rechts wird
   kleiner - gemessen kostete 0,5 -> 0,25 s Kontext bei der Huellkurve
   wenig, fuer die CQT ist das nicht gemessen.
3. **Rechenweg.** Heute faellt das Bass-Chroma aus der BTC-CQT des Mixes
   ab (0 ms). Mit Stem braucht es eine zweite CQT auf dem Stem (Tiefband
   reicht: 72 Bins), ~10-20 ms je Hop, im Stem-Thread oder im
   Analyse-Thread.
4. **Mischform pruefen:** Stem nur fuer die Dominanz-Entscheidung
   (leer/nicht leer) und Mix fuer den Ton, oder umgekehrt; und ob
   `MIN_DOMINANCE` auf dem Stem anders zu setzen ist.
5. **Register/Quinten-Regel** (`fold_bass_register`, `FIFTH_REGISTER_SHARE`)
   auf dem Stem neu bewerten - sie wurde gegen Gitarrenvoicings im Mix
   kalibriert.

## 4. Branch-Hinweis

`feature/wellenform-laufband` (und damit dieser Branch) zweigt **vor** dem
Merge der lagenkorrekten Bassanzeige ab (`d9f8d2e`, bass.py/btc.py/
cli.py/index.html, `tests/reference/messung_bass_oktave.py`). Die
Oktavregel ist hier deshalb im Messskript nachgebaut. Vor dem Weiterarbeiten
an der Erkennung `main` in diesen Branch mergen und die Oktav-Spalten mit
der echten Pipeline-Funktion nachmessen.

## 5. Dateien auf diesem Branch

- `jampilot/stems.py`, `jampilot/data/umxhq_bass_int8.onnx` (9 MB, Gewichte MIT)
- `jampilot/envelope.py` (asynchrone Bass-Kurve), `jampilot/cli.py` (Worker im Anzeigepfad)
- `tests/test_stems.py`
- `tests/reference/export_umx_bass.py`, `messung_bass_stem.py`,
  `messung_bass_stem_hopweise.py`, `messung_bass_stem_tonerkennung.py`
- `docs/exploration/bass-stem-huellkurve.md` (Huellkurve), diese Notiz (Erkennung)

## 6. Breite Messung: 193 Isophonics-Titel (2026-11-09, Arbeits-PC)

`tests/reference/messung_bass_stem_isophonics.py`. Referenz: die Isophonics-
Slashes aller Beatles-Alben (180 Titel), Queen (20) und Carole King (7);
Zuordnung Lab -> CD-Rip und Zeitversatz aus dem ML-Repo
(`chordml.isophonics.build_matching`, Chroma-Korrelation), als
`tests/reference/isophonics_matching.csv` eingecheckt. Genommen wurden die
193 Titel mit Korrelations-Score >= 0,5 und Versatz innerhalb des Sweeps.
Gleiche Kette wie in §1: Stem aus UMX-HQ int8 (6-s-Bloecke, 1 s Rand), BTC-
CQT auf Mix und Stem, `bass.slash_note` je Segment >= 1 s, Pooling 2 s ab
Onset, Akkord aus der Annotation. 11 384 Grundton-Segmente, 1 175
Umkehrungen. Stufe 1 (Trennung + CQT, 16 Prozesse) 2,4 min, Cache im
ML-Repo (`data/cache/stems_iso`), Stufe 2 Sekunden. `main` (Lagen-Merge
d9f8d2e) ist seit dieser Messung in den Branch gemergt.

**Vorher keine echten Bass-Stems auf diesem Rechner** - der pYIN-Teil aus
§2 (Tonklasse/Oktave je Note) liess sich hier nicht verbreitern. Die
Isophonics-Referenz ist die Harmonie-Annotation, nicht der Bassist.

### Ergebnis

| Variante | falsche Slashes (Grundton-Seg.) | leer (Grundton-Seg.) | Umkehrung gefunden | falscher Ton (Umk.) | leer (Umk.) |
|---|---|---|---|---|---|
| **Mix** (Pipeline heute) | **48 = 0,4 %** | 4213 = 37 % | 383 = 33 % | 124 | 668 |
| **Stem** | **169 = 1,5 %** | **3464 = 30 %** | **469 = 40 %** | 189 | 517 |
| Stem, MIN_DOMINANCE 1,5 | 146 = 1,3 % | 4530 = 40 % | 454 = 39 % | 163 | 558 |
| Dom:Stem (Stem entscheidet leer, Ton aus Mix) | 44 = 0,4 % | 4714 = 41 % | 375 = 32 % | 109 | 691 |
| Dom:Mix (Mix entscheidet leer, Ton aus Stem) | 121 = 1,1 % | 4586 = 40 % | 435 = 37 % | 151 | 589 |
| Stem, SLASH_ROOT_RATIO 5 | 84 = 0,7 % | 3625 = 32 % | 415 = 35 % | 173 | 587 |
| Stem, Quinte nie als Slash | 75 = 0,7 % | 3464 = 30 % | 289 = 25 % | 369 | 517 |
| Stem nur ohne Widerspruch des Mixes | 157 = 1,4 % | 3483 = 31 % | 460 = 39 % | 154 | 561 |
| Mix, Pooling 1 s | 53 = 0,5 % | 3585 = 31 % | 409 = 35 % | 118 | 648 |
| Stem, Pooling 1 s | 164 = 1,4 % | 2867 = 25 % | 496 = 42 % | 171 | 508 |
| Stem, Pooling 0,5 s | 202 = 1,8 % | 2438 = 21 % | 522 = 44 % | 184 | 469 |

Je Kuenstler (Mix -> Stem): Beatles falsche Slashes 0,4 -> 1,5 %, leer
39 -> 32 %, Umkehrungen 30 -> 37 %; Queen 0,5 -> 0,9 %, 28 -> 20 %,
47 -> 60 %; Carole King 1,2 -> 2,2 %, 19 -> 13 %, 22 -> 26 %.

### Falsche Slashes nach Intervall zum Grundton

| Variante | Terz | kl. Terz | **Quinte** | kl. Sept | andere | betroffene Titel |
|---|---|---|---|---|---|---|
| Mix | 11 | 3 | 22 | 1 | 11 | 31 |
| Stem | 36 | 17 | **94** | 3 | 19 | 66 |
| Stem, Ratio 5 | 21 | 4 | 45 | 1 | 13 | 39 |
| Mix, Pooling 1 s | 12 | 15 | 15 | 1 | 10 | 27 |

Typische Stem-Fehler: *Can't Buy Me Love* C7 -> G (zehnmal), *Roll Over
Beethoven* D -> F#, *Who Wants to Live Forever* Cmaj7 -> E, *For You Blue*
(9 falsche, Mix 0). Das ist der Bassist: Walking- und Wechselbass spielen
Quinte und Terz, der Mix haelt mit Gitarre und Klavier den Grundton oben,
der Stem nicht mehr. Die Quinten-Regel (`FIFTH_REGISTER_SHARE`) greift auf
dem Stem nicht - dort klingt die Quinte im Bassregister, weil sie der Bass
wirklich spielt.

### Lesart

Das Bild der fuenf Titel aus §2 (Stem: ein falscher Slash weniger, ein
Drittel weniger leer) haelt in der Breite **nicht**. Der Gewinn an
Ausbeute bleibt (leer 37 -> 30 %, Umkehrungen 33 -> 40 %), aber die
falschen Slashes verdreieinhalbfachen sich (48 -> 169) und treten auf
doppelt so vielen Titeln auf (31 -> 66). Keine der Mischformen holt das
zurueck: Entscheidet der Stem nur ueber leer/nicht leer, bleibt es der Mix
(44 falsch, aber auch 41 % leer); die hoehere Grundton-Ratio ist der beste
Kompromiss (84 falsch, 32 % leer, 35 % Umkehrungen) und liegt immer noch
75 % ueber dem Mix. Die Quinte zu verbieten tauscht falsche Slashes gegen
verlorene echte Quint-Umkehrungen (289 statt 383 gefunden).

Der Zielkonflikt aus §2 ist damit kein Randfall, sondern der Hauptbefund:
**Der Stem hoert den Bassisten, die Slash-Annotation meint die Harmonie.**
Fuer den Akkordnamen (C/G) ist der Mix die richtige Quelle, und sie bleibt
es. Fuer die *Bass-Ansicht* (was spielt der Bassist gerade) waere der Stem
die richtige Quelle - aber dafuer ist Isophonics die falsche Referenz, das
braucht echte Stems (§2, zwei Titel, dort +3-4 Punkte Tonklasse). Beide
Fragen aus einem Urteil zu beantworten geht nicht mehr, sobald der Stem im
Spiel ist.

**Nebenbefund, unabhaengig vom Stem:** Pooling 1 s statt 2 s auf dem Mix
senkt leer von 37 auf 31 % und hebt die Umkehrungen von 33 auf 35 % bei
48 -> 53 falschen Slashes (die kleinen Terzen steigen 3 -> 15). Der Bassist
spielt den Grundton auf die Eins und wechselt danach - die erste Sekunde ist
die ehrlichere. Nicht eingebaut, waere eine eigene kleine Aenderung an
`BASS_POOL_SECONDS` mit Realaudio-Gegenprobe.

### Ohne Bassgitarre: erfindet der Stem etwas?

Neun Beatles-Titel ohne Bassgitarre (Yesterday, Blackbird, Julia, Mother
Nature's Son, Eleanor Rigby, Her Majesty, Within You Without You, Good
Night, Love You To): 331 Grundton-Segmente. Falsche Slashes Mix 0, Stem 3;
leer Mix 45 %, Stem 37 %. Stem-Energie relativ zum Mix (Median je Titel;
Titel MIT Bass: Median 0,36, 10-%-Quantil 0,21):

| Titel | Stem/Mix |
|---|---|
| Mother Nature's Son, Love You To | 0,02 |
| Good Night (Orchester) | 0,13 |
| Eleanor Rigby (Streicher) | 0,16 |
| Yesterday | 0,19 |
| Julia | 0,35 |
| Her Majesty (nur Gitarre) | 0,57 |

Bei reiner Gitarre nimmt der Stem die Gitarre als Bass (Her Majesty liegt
ueber dem Median der Titel mit Bass), bei Streichern und Orchester bleibt
er leise. Als "spielt hier ein Bass?"-Detektor taugt er fuer Gitarrenstuecke
nicht - genau die Faelle von If This Is Goodbye (§3 Punkt 1, `leak`).

### Hopweise wie live (§3 Punkt 2)

14 Titel (die fuenf Referenztitel, Come Together, Taxman, Hey Jude, Penny
Lane, Yesterday, Here Comes the Sun, Dear Prudence, I Feel the Earth Move,
You've Got a Friend, We Will Rock You), Trennung mit Kern 0,25 s, 1,0 s
Kontext davor, 0,5 s dahinter (`--hopweise`) gegen 6-s-Bloecke:

| | falsche Slashes | leer | Umkehrungen | falscher Ton (Umk.) |
|---|---|---|---|---|
| Mix | 5/775 | 31 % | 31/172 | 31 |
| Stem, 6-s-Block | 7/775 | 27 % | 47/172 | 49 |
| Stem, hopweise | 8/775 | 27 % | 46/172 | 47 |

Die Live-Konfiguration liefert fuer die CQT dasselbe wie die Trennung am
Stueck. Die zeitliche Lage (Stem endet 0,5 s + eine Hop-Laufzeit vor der
Analysefront) bleibt ein Einbau-Thema, ist aber kein Qualitaetsthema.

### Stand nach der Messung - und der Bass-Ansicht (Nachtrag, gleicher Tag)

Der Gedanke "fuer die Bass-Ansicht waere der Stem die richtige Quelle" ist
beim zweiten Hinsehen falsch, und zwar aus demselben Grund wie oben. Beim
Country-Wechselbass spielt der Bassist C, G, C, G ueber C-Dur. Die
Bass-Ansicht soll dem Mitspieler sagen, auf welchem Ton er landet - das
ist der Grundton, und nur bei einer echten Umkehrung (Bass liegt den ganzen
Akkord lang auf Terz oder Quinte) der Slash-Ton. Eine Transkription des
gerade gezupften Tons waere zum Mitspielen falsch. Das ist eine harmonische
Frage, keine akustische; die drei Huerden in `slash_note` SIND dieser
harmonische Filter, und sie funktionieren auf dem Mix, weil Gitarre und
Klavier den Grundton mittragen. Die 94 Quinten-Fehler des Stems sind der
Wechselbass in Zahlen. (README: "Harmony, not transcription" - gilt auch
fuer den Bass.)

- Stem fuer Slash-Namen UND Bass-Ansicht: **nicht einbauen.** Nette Idee,
  falsche Konsequenz: Der Stem beantwortet die Frage "was spielt der
  Bassist", die Anzeige stellt die Frage "wo liegt der Bass der Harmonie".
  Die Erkennungsfrage ist damit geschlossen.
- Der Stem bleibt, wo er ist: in der Huellkurve (bass-stem-huellkurve.md).
  Echte Stems (Moises o. ae.) haetten fuer die Erkennung nur noch bestaetigt,
  dass der Stem den Bassisten trifft. Mehrwert haetten sie allein fuer die
  Huellkurve (Kick-Anteil, laute Mixe; bisher zwei Titel) und allenfalls die
  Lage (Oktave auf dem Mix schon bei 96-100 %). Beides Kuer.
- Pooling 1 s auf dem Mix: eigener kleiner Kandidat, aber gerade am
  Wechselbass gegenzupruefen - bei langsamem Tempo faellt die Quinte schon
  in die erste Sekunde, und die kleinen Terzen stiegen 3 -> 15.
- Punkte 2-5 aus §3 sind damit gegenstandslos.

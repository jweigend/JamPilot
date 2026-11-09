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

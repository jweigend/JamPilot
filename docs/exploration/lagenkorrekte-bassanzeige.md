# Lagenkorrekte Bassanzeige: die Oktave messen statt raten

Stand: 2026-10-14 · Status: **Exploration mit Messung gegen zwei isolierte
Bassspuren (Echoes, Sailing to Philadelphia). Machbar; der Entwurf in §5 ist
am selben Tag eingebaut (`bass.octave`, `btc.bass_pitches`, Eventfeld `p`,
Griffbrett-Filter in index.html; Nachtrag in
[tests/reference/README.md](../../tests/reference/README.md)).** Baut auf dem Bass-Abschnitt in
[tests/reference/README.md](../../tests/reference/README.md) und
[lagenwahl-im-record-modus.md](lagenwahl-im-record-modus.md) auf.
Messskript: [tests/reference/messung_bass_oktave.py](../../tests/reference/messung_bass_oktave.py).

> **Antwort in einem Satz:** Ja. Die BTC-CQT, die ohnehin läuft, enthält die
> Oktave des Basses, und eine Regel mit einer Zahl („tiefste Oktave, deren
> Notenbin mindestens 30 % des stärksten Oktavbins dieser Tonklasse hat")
> trifft sie segmentweise in 98 % (Sailing) bzw. 92 % (Echoes) der Fälle –
> der heutige Planer, der nur den Handweg kennt, liegt auf denselben Events
> in 72–73 % in der richtigen Oktave und sonst fast immer eine zu tief.

---

## 1. Das Problem

Der Bass-Modus kennt nur die **Tonklasse** des gemessenen Basstons (`bass.py`:
Tiefband-Chroma, 12 Klassen). Welche **Lage** der Hals zeigt – E auf der
leeren E-Saite (E1), auf der A-Saite im 7. Bund (E2) oder auf der G-Saite im
9. Bund (E3) – entscheidet `planBassLine` in index.html allein nach
Handweg und einer Vorliebe für dicke Saiten und tiefe Bünde.

Das ist musikalisch oft falsch: Ein Bassist spielt die Strophe gern hoch
und den Refrain tief, oder umgekehrt, und genau dieser Registerwechsel ist
eine Aussage des Arrangements, die der Planer nicht kennen kann. Beide
Referenzstücke zeigen das: In Sailing schwankt der Anteil der Noten in
Oktave 1 je 30-s-Block zwischen 27 % und 65 % (Intro 58 %, Strophen ~30 %,
Schluss 65 %), in Echoes zwischen 0 % (Funk-Teil, 500–660 s: alles Oktave 2)
und 48 %.

Die Frage war: Steckt die Oktave im Signal, das wir ohnehin berechnen, und
lässt sie sich im Mix – nicht auf einem isolierten Stem – verlässlich lesen?

## 2. Referenz: isolierte Bassspuren

Isophonics annotiert den Bass nur als Stufe, ohne Oktave. Referenz sind
deshalb zwei Stem-Trennungen:

| Stück | Dauer | Mix | Bassspur | Referenznoten (≥ 280 ms) |
|---|---|---|---|---|
| Pink Floyd – Echoes | 23:36 | Summe aller Stems (ohne Metronom) | `~/Documentos/Pink Floyd - Echoes …/…-bass-….mp3` | 488: O1 131 · O2 329 · O3 28 |
| Mark Knopfler – Sailing to Philadelphia | 5:30 | `tests/realaudio/sailing_to_philadelphia.mp3` | `tests/realaudio/Mark Knopfler - Sailing to Philadelphia-bass-….mp3` (gitignored) | 305: O1 126 · O2 179 · O3 0 |

Die Referenz-Tonhöhe je 93-ms-Frame kommt aus pYIN auf der Bassspur (28–500
Hz, nur stimmhafte Frames über 5 % der Spur-Lautstärke, C1..B3). Der Stem
wird per Kreuzkorrelation am Mix ausgerichtet (Sailing: −25 ms). Dass die
Referenz trägt, zeigt der Gegencheck: Dieselbe Oktavregel auf der
**isolierten** Spur stimmt mit pYIN in 97,7 % (Echoes) bzw. 100 % (Sailing)
der Noten überein – die Abweichungen sind kurze C#2/C#3-Noten, bei denen
beide Verfahren unsicher sind.

Nebenbefund zur Tonklasse: Die heutige Faltung (`fold_bass_chroma`,
`MIN_DOMINANCE`) liefert je Frame in 10–13 % keine Note und ist bei den
übrigen in 96 % richtig – auf beiden Stücken. Die Tonklassenmessung ist also
verlässlich genug, dass die Oktave die einzige fehlende Information ist.

## 3. Was im Signal steckt

Die BTC-CQT beginnt bei C1 mit zwei Bins je Halbton und reicht bis C7. Die
Notenbins C1..B3 (Bins 0, 2, …, 70) sind 36 Werte je Frame: drei Oktaven ×
zwölf Tonklassen. `fold_bass_chroma` summiert davon heute die drei Oktaven zu
einem Zwölfer; `fold_bass_register` hält nur C1..D#2 getrennt (für den
Quinten-Nachweis). Die Oktave braucht nichts Neues: **die 36 Notenbins
ungefaltet aufheben** – 36 Floats je Frame, null zusätzliche Rechenzeit.

Drei Schätzer, je Note über die Frames gemittelt, auf dem **Mix**:

| Regel | Echoes (488 Noten) | Sailing (305 Noten) |
|---|---|---|
| tiefste Oktave mit Bin ≥ 0,2 × Maximum | 94,1 % | 100 % |
| **tiefste Oktave mit Bin ≥ 0,3 × Maximum** | **94,3 %** (O1 127/131 · O2 317/329 · O3 16/28) | **100 %** |
| tiefste Oktave mit Bin ≥ 0,5 × Maximum | 94,1 % (O1 116/131) | 98,0 % |
| von unten: Oktave gilt, wenn Bin ≥ 1,0 × Bin der Oktave darüber | 83,0 % (O1 61/131) | 93,8 % |
| harmonische Summe (6 Teiltöne, Gewicht 0,8^k) | 91,0 % | 97,4 % |

Je Frame statt je Note sieht es gleich aus (Echoes 94,8 %, Sailing 99,0 %
bei 0,3).

Zwei Befunde daraus:

- **Der Grundton ist oft schwächer als sein erster Oberton.** Die Regel „Oktave
  gilt, wenn ihr Bin mindestens so stark ist wie der darüber" verliert die
  Hälfte der Oktave-1-Noten (61/131) – selbst auf der isolierten Bassspur
  (66/131). Ein E-Bass durch Verstärker und Mix hat bei E1 (41 Hz) weniger
  Energie als bei E2 (82 Hz). Deshalb darf die Regel nicht „stärkster Bin"
  heißen, sondern „**tiefster deutlich vorhandener** Bin". Mit 30 % des
  Maximums ist die Schwelle weit genug unter dem Oberton und weit genug über
  dem Leck.
- **Die harmonische Summe ist schlechter als die einfache Regel.** Sie
  summiert Obertöne, die im Mix allen gehören (Gitarre, Keys auf denselben
  Tonklassen), und zieht die Oktave-2-Noten nach unten (Echoes O2 308/329).
  Keine Templates, keine Gewichte – ein Vergleich dreier Bins genügt.

## 4. Segmentweise, wie die Pipeline es zeigen würde

Das Gleiche durch die echte Kette: BTC-Labels → Segmente → Pooling der ersten
`BASS_POOL_SECONDS` (2 s) → `slash_note` (Mehrheit, Akkordton, Grundton-Ratio,
Quinten-Register) → Tonklasse; dann die Oktavregel auf den gepoolten
Notenbins **dieser** Tonklasse. Referenz je Segment ist die Mehrheitsoktave
der Referenzframes mit derselben Tonklasse.

| | Echoes | Sailing |
|---|---|---|
| Segmente / mit Bassnote / davon mit Referenz | 501 / 318 / 238 | 148 / 103 / 101 |
| Oktave richtig, Schwelle 0,2 | 90 % | 98 % |
| **Oktave richtig, Schwelle 0,3** | **92 %** (220/238) | **98 %** (99/101) |
| Oktave richtig, Schwelle 0,5 | 91 % | 97 % |
| **Heutiger Planer** auf denselben Events: gleiche Oktave | **73 %** (27 % zu tief) | **72 %** (21 % zu tief, 8 % zu hoch) |

Der Planer wurde dafür in Python nachgebaut (`bassPositions`, `bassNodeCost`,
`bassTransCost`, Viterbi mit Lookahead 5, publish-once), über dieselbe
Eventfolge. Auf der reinen Notenfolge der Referenz (ohne Segmentierung) liegt
er bei 72 % (Echoes) und 62 % (Sailing: 18 % zu tief, 21 % zu hoch).

### Die Fehler

Echoes, 18 von 238 Segmenten bei 0,3:

- **12 × G# (und 2 × A) in Oktave 1 statt 2**, alle im lauten Schlussteil ab
  1150 s und bei 256–366 s. Der Mix hat dort am G#1-Bin 30–50 % des
  G#2-Bins, die Bassspur allein 0–16 %: Ein anderes Instrument (Orgelpedal
  oder die Trennung selbst) liegt eine Oktave unter dem Bass. Der Hals zeigt
  dann den tiefsten G#, der wirklich klingt – für den Bassisten eine
  vertretbare Antwort, keine Erfindung.
- **4 × C#2/C#3** vertauscht, Noten von 0,3–0,5 s: Die CQT-Fenster sind bei
  C2 rund eine halbe Sekunde lang, bei kurzen Noten verschmiert der tiefe
  Bin; dieselben Stellen sind auch auf der isolierten Spur unsicher.

Sailing, 2 von 101: zweimal E1 statt E2 (89 s, 196 s), der E1-Bin hat im
Mix 30 % – Kick oder Tiefton eines anderen Instruments. Alle 55 Segmente in
Oktave 1 richtig.

**Oktave 3 ist die schwache Stelle:** In Echoes 16/28 Noten, segmentweise
0/2. Energie eine Oktave *unter* einer O3-Note kommt im Mix häufig vor
(Gitarre spielt dieselbe Tonklasse), und 28 Noten sind wenig Material. Auf
dem Bass-Hals ist Oktave 3 selten (G-Saite ab dem 5. Bund); die heutige
Vorliebe des Planers für tiefe Lagen hält sie ohnehin auf Abstand.

## 5. Entwurf

**Server (nur BTC-Pfad: `analyze` und Live).**

1. `btc._fold_note_bins` liefert zusätzlich die ungefalteten Notenbins
   C1..B3, Form (36, T); `BassTrack` hält sie neben `_data` und `_register`
   im selben Ring (`pitches_between(start, end)` → (36,) Summe).
2. `bass.octave(pitches, pc, tau=0.3) -> int | None`: tiefste Oktave 1..3,
   deren Bin ≥ tau × Maximum der drei Bins dieser Tonklasse. Eine Zahl, eine
   Regel, dokumentiert wie `SLASH_ROOT_RATIO`.
3. Wo heute `slash_note` die Tonklasse liefert (cli `_basslinie`, `cmd_analyze`,
   Durchgangsbass in `passing_note`), bekommt das Event ein zweites Feld:
   `"p": MIDI` (E1 = 28, E2 = 40, E3 = 52), `None` wenn `b` leer ist. `b`
   bleibt, damit Chip, Slash-Name und Schreibweise unverändert laufen.
4. Dieselbe Monotonie wie `b`: Oktave und Note werden im selben Hop aus
   demselben Pooling bestimmt und zusammen committet (`BASS_COMMIT_HOPS`
   zählt Paare, nicht Namen). Ein gesetztes `p` wird nie wieder angefasst.

**Frontend (`index.html`).**

5. `bassPositions(pc, midi)`: Ist `midi` da und liegt es im Fenster der
   zwölf Bünde (28..54), bleiben nur die Positionen mit genau dieser
   Tonhöhe übrig – E1 eine (E leer), E2 zwei (A 7 / D 2), E3 eine (G 9).
   Fehlt `p` oder liegt die Tonhöhe außerhalb, gelten wie heute alle vier.
6. `planBassLine` bleibt, wie er ist: Zwischen A 7 und D 2 entscheidet weiter
   der Handweg, und der Anker aus dem Record-Modus überstimmt weiter alles.
   Der Vorlauf nutzt `p` der kommenden Events genauso – die Linie ist dann
   nicht nur zusammenhängend, sondern liegt im richtigen Register.
7. Keyboard-Ansicht: Der orangene Bass-Punkt sitzt heute auf der tiefsten
   passenden Taste (`KEY_LOW + pc`); mit `p` auf der richtigen.

Kosten: 36 Floats je Frame im Ring, drei Vergleiche je Segment, ein Feld im
Event. Kein neues Modell, keine neue CQT.

## 6. Proberaum

Erster Test mit Sailing to Philadelphia am 2026-10-14 (Bass): Die Anzeige
ist mit der gemessenen Lage deutlich sinnvoller und hilft genau dort, wo es
nach oben geht.

**Nicht-Ziel, bewusst:** Dieselbe Tonhöhe liegt auf dem Bass oft doppelt –
A1 als leere A-Saite oder auf der E-Saite im 5. Bund. Das ist derselbe Ton,
aber ein anderer Griff für die Quinten und ein anderer Klang. Welche der
beiden ein Bassist nimmt, ist seine Entscheidung und steckt nicht im Signal;
das Tool soll sie nicht ermitteln. Zwischen den Doppelpositionen entscheidet
weiter der Handweg, und wer es anders will, setzt im Record-Modus den Anker
(alle vier Saiten bleiben wählbar).

## 7. Offen

- **Schwelle und Oktave 3.** 0,3 ist auf beiden Stücken optimal oder
  gleichauf; die O3-Fälle (16/28) könnten eine eigene, höhere Schwelle für
  den Schritt von O2 nach O3 brauchen. Erst mit einem dritten Stem messen,
  der Oktave 3 wirklich enthält (Walking Bass, Solo).
- **Tiefton anderer Instrumente.** Orgelpedal, Synth-Bass, Kick in der Nähe
  von 41 Hz liefern Oktave-1-Energie unter einem Oktave-2-Bass. In den
  Referenzen 2–6 % der Segmente; das Register-Gate der Quinte
  (`FIFTH_REGISTER_SHARE`) hat dieselbe Quelle und lebt damit.
- **Live-Pfad.** Die Messung hier poolt wie der Live-Pfad (2 s ab Onset),
  aber offline mit zeittreuer Grenze. Vor dem Einbau einmal
  `messung_live_pfad` auf Sailing mit Oktave und ein Proberaum-Test – wie
  bei der Quinten-Regel.
- **Referenzqualität.** Zwei Stücke, zwei Stem-Trennungen, pYIN als
  Referenz. Das reicht für „machbar", nicht für eine Schwellenkalibrierung
  auf die zweite Stelle.

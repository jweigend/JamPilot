# Referenz-Set mit zeitgestempelter Ground Truth (Isophonics)

Fünf Tracks, deren Akkordwechsel **sekundengenau handannotiert** sind
(Isophonics-Referenzannotationen, Harte et al. — dieselben Daten, auf denen
BTC trainiert wurde). Damit sind erstmals harte Timing-Messungen möglich,
die mit den Prosa-Ground-Truths in `tests/realaudio/` nicht gingen.

`.lab`-Format: `start ende akkord` (Harte-Syntax, z. B. `A:min/b7`).
Quelle der Labels: http://isophonics.net/datasets · Audio: eigene Käufe/Downloads.

## Versions-Verifikation (2026-08-08, BTC-NumPy-Port, Offset-Sweep ±1.5 s)

Offset = konstanter Zeitversatz Audio vs. Annotation (Decoder-Delay +
Versions-Stille); bei Auswertungen zu den `.lab`-Zeiten ADDIEREN.

| Track | Version | Offset | Root-Treffer | Urteil |
|---|---|---|---|---|
| let_it_be | Album 1970 | +0.36s | 76.9% | ✅ passt |
| eight_days_a_week | 2023 Mix (Giles Martin) | +0.03s | 86.6% | ✅ passt |
| something | 2019 Mix (Giles Martin) | +0.22s | 76.6% | ✅ passt |
| its_too_late | Tapestry Album | +0.40s | 86.1% | ✅ passt |
| crazy_little_thing | Greatest Hits I | +0.13s | 74.5% | ✅ passt |

Eine falsche Version läge bei ~10 % (Zufallsniveau). Auch die 2019/2023-Mixe
decken sich zeitlich mit den Annotationen der Originalmaster (konstanter
Offset, keine Drift — die Treffer wären sonst zum Songende hin eingebrochen).

## Offset-Revision (wichtig fuer alle Timing-Zahlen)

Die urspruenglichen Offsets oben stammen aus einem Frame-Agreement-Sweep
(93-ms-Aufloesung) - fuer den Versions-NACHWEIS ausreichend, fuer
Timing-Messungen zu grob (drei Schaetzer wichen bis zu 300 ms voneinander ab).
Der verlaesslichste Schaetzer ist die **Chroma-Korrelation** (GT-Akkordtemplates
gegen 23-ms-HPSS-Chroma, 10-ms-Sweep ueber den ganzen Track):

| Track | Timing-Offset (Chroma-Korrelation) |
|---|---|
| let_it_be | +0.08s |
| eight_days_a_week | -0.15s |
| something | -0.06s |
| its_too_late | +0.05s |
| crazy_little_thing | -0.05s |

Fuer Timing-Auswertungen DIESE Offsets verwenden. Absolute Fehlerzahlen tragen
trotzdem eine Alignment-Unsicherheit von grob +-50 ms; belastbar sind vor allem
RELATIVE Vergleiche unter festgehaltenen Offsets.

## Timing-Messung (unter Chroma-Korrelations-Offsets)

| Verfahren | median \|dt\| | ≤93ms | ≤250ms | median dt | Schiebungen nach hinten |
|---|---|---|---|---|---|
| BTC roh (93-ms-Raster) | 187ms | 25% | 65% | +138ms | - |
| + `refine_boundary` symmetrisch ±0.3s | 128ms | 43% | 74% | +72ms | 50 |
| + `refine_boundary` asymmetrisch (**aktiv**) | **117ms** | **43%** | **75%** | **+50ms** | **0** |

`btc.refine_boundary`: Akkordton-Schnitt im HPSS-Chroma (23-ms-Raster),
Onset-Staerke gewichtet mit - Wechsel fallen auf Anschlaege. Das Suchfenster
ist ASYMMETRISCH (-0.40s/+0.05s): Der wahre Wechsel liegt fast immer VOR der
Modellgrenze, und auf einer chaotischen Eins (Beckencrash, Bassdrum, Gesang)
schob die symmetrische Suche die Grenze nach hinten - im Praxistest bis auf
die Zwei des Taktes (Musiktest-Befund, durch die 50 Schiebungen bestaetigt).
Verworfen wurden: reiner Onset-Snap (schnappt auf Schlagzeug/Melodie,
verschlechtert), Logit-Kreuzung des Modells (kein Gewinn), Beat-Raster-Snap
(librosas Beat-Phase liegt selbst ~160 ms neben den GT-Wechseln),
Klarheitsgewichtung (kein Gewinn).

## Historische erste Messung (unter den alten Frame-Agreement-Offsets)

Abstand der erkannten Segmentgrenzen zum annotierten Wechsel (406 Wechsel,
Treffer = nächste Grenze innerhalb ±0.5 s):

| Track | getroffen | median \|dt\| | median dt | ≤93ms | ≤250ms |
|---|---|---|---|---|---|
| let_it_be | 80% | 227ms | +17ms | 21% | 54% |
| eight_days_a_week | 88% | 208ms | +57ms | 22% | 61% |
| something | 93% | 180ms | +28ms | 24% | 66% |
| its_too_late | 93% | 255ms | +47ms | 15% | 48% |
| crazy_little_thing | 89% | 100ms | +23ms | 46% | 84% |
| **gesamt** | **88%** | **195ms** | **+28ms** | **25%** | **62%** |

Zwei Lesarten:
- **Kein systematischer Vorlauf**: median dt ≈ +28 ms, also praktisch
  unverzerrt (Vorsicht: der Offset-Sweep absorbiert einen Teil systematischer
  Verschiebung). Das CQT-Vorecho-Problem des Template-Pfads (~165 ms zu früh)
  hat BTC nicht — es hat Grenzplatzierung von menschlichen Annotationen gelernt.
- **Streuung ~±200 ms** um den Wechsel, begrenzt durch das 93-ms-Frameraster
  und die Annotationstoleranz selbst. Für den Mitspiel-Fluss laut Musiktest
  ausreichend; wer es enger will, braucht ein feineres Zeitraster (z. B.
  Grenz-Verfeinerung im Onset-Stil INNERHALB des BTC-Segments — der
  stillgelegte `find_onset_frame`-Pfad wäre dafür der Kandidat).

## Slash-Bass-Messung gegen die Isophonics-Bass-Annotationen

Die `.lab`-Labels annotieren auch den Bass (`A:min/b7` = Umkehrung). Damit
wurde die reaktivierte Bassmessung (Tiefband aus der BTC-CQT, `bass.slash_note`)
kalibriert - Segmente >= 1 s, 414 Faelle:

| Regelwerk | falsche Slashes (387 Grundton-Seg.) | echte Umkehrungen gefunden (27) |
|---|---|---|
| nur Mehrheit (wie Template-Pfad) | 10% | 15 (56%) |
| + Akkordton-Gating | 8% | 15 (56%) |
| + Grundton-Ratio 2.0 (**aktiv**) | **2%** | **13 (48%)** |

Die Grundton-Ratio-Huerde (`SLASH_ROOT_RATIO`): ein Slash wird nur behauptet,
wenn der gemessene Ton den Grundton im Tiefband klar schlaegt - bei echten
Umkehrungen fehlt der Grundton unten gerade, bei Grundton-Bass gewinnt sonst
gern die laute Quinte. Praxis-Check Peg: `G/B` bleibt (9 Stellen), der
fruehere Fehlgriff `Cmaj7/B` verschwindet.

### Nachtrag 2026-09-12: der Bass fehlte, er war nicht falsch

Die Kalibrierung oben zaehlte falsche Slashes und gefundene Umkehrungen,
nie die Leerquote. Live (v7_2b, ein Frame, Snap) war der Bass bei 60-90 %
der Events leer - im Bass-Modus steht dann der Akkordname statt der Note,
das Griffbrett zeigt den Grundton. Ursache: die Faltung des BTC-Tiefbands
summierte beide Bins je Halbton, auch den bei +50 Cent, der das Leck der
Nachbarnote traegt; `bass.MIN_DOMINANCE` fiel durch. Der bis 08.08. aktive
chroma_cqt-Pfad (36 Bins je Oktave, Mittelbin je Halbton) hatte das Problem
nicht. Publish-once/Persistenz verlieren nur 3-4 Baesse je Titel.

Anteil Segmente >= 1 s ohne Bass, offline gegen die Annotation (2-s-Pooling):

| | Let It Be | Something | It's Too Late | Eight Days | Crazy |
|---|---|---|---|---|---|
| alter chroma_cqt-Pfad | 11 % | 32 % | 16 % | 76 % | 88 % |
| BTC-Tiefband, beide Bins (bis 12.09.) | 23 % | 78 % | 89 % | 75 % | 86 % |
| BTC-Tiefband, nur Notenbins (**aktiv**) | 13 % | 25 % | 16 % | 71 % | 77 % |

Eight Days und Crazy Little Thing bleiben in jeder Variante leer (dichtes
Rock-Tiefband, kein klarer Gewinner); die Stimmung der Aufnahmen liegt
innerhalb von 15 Cent und ist es nicht. Mit den Notenbins liess
`SLASH_ROOT_RATIO` 2,0 live die Quinte als Slash durch (32 falsche auf fuenf
Titeln, D/A ueber jedem D in Eight Days), 3,0 haelt sie: offline 0,3 %
falsche Slashes bei 11/27 Umkehrungen (`messung_bass_gt.py`). Live, Events
mit richtigem Grundton, Bass gegen die Annotation:

| | gesetzt und richtig | gesetzt und falsch | leer |
|---|---|---|---|
| vorher (beide Bins, Ratio 2,0) | 143 | 12 | 332 |
| Notenbins, Ratio 2,0 | 287 | 32 | 166 |
| **Notenbins, Ratio 3,0** | **287** | **17** | **179** |

Elf der 17 falschen sitzen in It's Too Late und sind systematisch (D/A ueber
jedem D6, Fmaj7/E ueber jedem Fmaj7) - Quinte bzw. Septime als Oberwelle,
oder der Bassist spielt es wirklich; das entscheidet das Ohr. Die
chromatische Basslinie in der Bridge von Something (Umkehrungen 16 von 18
weiter leer) loest das nicht: ein Event traegt einen Bass, Durchgangstoene
innerhalb eines Akkords sind nicht vorgesehen. Proberaum-Test offen.

Messskripte: Session-Scratchpad `verify_reference.py` (Versions-Check),
Timing- und Bass-Auswertung; alle nutzen nur `jampilot.btc` + librosa.

### Nachtrag 2026-09-13: Durchgangsbass am Segmentende

Comfortably Numb (tests/realaudio/REPORT_comfortably_numb.md): Vor jedem Em
haelt die Band einen halben Schlag F# im Bass, das Modell labelt G ueber F#
als G/Gmaj7 (Trainingskonvention, Summe der F#-Labels < 0,05). Seit dem
Branch feature/durchgangsbass bekommt ein Segment ein zweites Event mit
gleichem Akkord und gemessenem Bass (G/F#), wenn das Tiefband am Segmentende
>= 3 Frames stabil eine Note zeigt, die chromatisch ZWISCHEN laufendem und
naechstem Grundton liegt (`bass.passing_note`, `cli.PASSING_COMMIT_HOPS`).
Live-Pfad mit Beat-Tracker, ohne -> mit: Timing und Eventzahl sonst
identisch; Let It Be 152 -> 154 Events (C/B bei 38,5 s = annotiert `C/7`,
146,5 s nicht annotiert), Something 136 -> 138 (F/E ueber `C/3`, C/B =
`C/7`; Nur-Bass-Treffer 25 -> 33 %), Crazy Little Thing 133 -> 134 (A#/A
ueber `Bb:maj`), Eight Days und It's Too Late unveraendert. Comfortably Numb
Solo: 6 von 7 Stellen mit G/F#. Die breite Variante (jeder stabile Fremdbass
im Segment, ohne Akkordton-Gate) wurde verworfen: 154 Unter-Events offline,
Eight Days a Week alle 2 s ein Slash-Chip.

### Nachtrag 2026-10-09: die Quinte braucht eine Bassstimme

If This Is Goodbye (tests/realaudio/REPORT_if_this_is_goodbye.md): In der
ersten Strophe spielt kein Bass, der tiefste Ton unter dem D-Griff ist die
A-Saite (110 Hz), das D der Gitarre liegt erst bei D4 ueber der
Tiefband-Grenze. `slash_note` sagte A (A/D im Tiefband 12-38x), live stand
jedes D der Strophe als D/A - dieselbe Klasse wie D/A ueber jedem D in Eight
Days (Ratio 2,0) und D6/A in It's Too Late. Die Ratio-Huerde kann hier nicht
greifen, der Grundton fehlt unten ganz.

Seit Branch feature/quinte-bassregister braucht die QUINTE im Bass einen
Nachweis, den eine Gitarre nicht liefern kann: mindestens 5 % ihrer
Tiefband-Energie im Bassregister C1..D#2 (32,7-77,8 Hz, unter E2;
`btc.fold_bass_register`, `bass.FIFTH_REGISTER_SHARE`). Terz, Septime und
Fremdtoene bleiben wie bisher. Ohne Nachweis gilt Grundton-Lage.

Offline (Metrik oben, 2-s-Pooling): falsche Slashes 1/385 und 11/27
Umkehrungen unveraendert; Goodbye Strophe 1 acht von acht D/A weg, das echte
A-Pedal des Basses bei 240 s (A1, 55 Hz, Register-Anteil 57 %) bleibt. Ein
allgemeines Register-Gate fuer alle Slash-Toene wurde verworfen: Es kostet
bei 25 % Anteil 10 der 11 Umkehrungen (Let It Be alle sieben Em/G), weil die
Bass-Fundamentale der 60er-Aufnahmen kaum unter E2 liegen.

Live-Pfad (`messung_live_pfad.lauf`, mit Tracker), Quinten-Slash-Events ohne
-> mit Regel: Goodbye 11 -> 2 (bleiben: 207 s, 240 s), Let It Be 7 -> 5 (das
Modell labelt dort C statt Em/G, der Bass G war richtig: 40,5 s und 182,0 s
verlieren ihn), Something 8 -> 7 (127,7 s C/G), It's Too Late 10 -> 10 (D/A, D6/A, Fmaj7/C:
dort spielt ein Bass, die Quinte klingt im Register - ob Pedal oder
Oberwelle, entscheidet weiter das Ohr). Eventzahl, Timing und
Nur-Bass-Treffer unveraendert.

### Nachtrag 2026-10-14: die Lage (Oktave) wird gemessen

Isophonics annotiert den Bass ohne Oktave; Referenz sind deshalb zwei
isolierte Bassspuren (Stem-Trennungen, pYIN je Frame): Echoes (23:36,
Mix = Summe der Stems) und Sailing to Philadelphia (Bass-Stem unter
tests/realaudio, gitignored). `messung_bass_oktave.py` richtet den Stem per
Kreuzkorrelation am Mix aus und misst auf dem MIX.

Regel (`bass.octave`, `btc.bass_pitches`): von den drei Oktavbins einer
Tonklasse (C1..B3, ungefaltete Notenbins der BTC-CQT) die TIEFSTE, deren
Bin >= 30 % des staerksten hat (`OCTAVE_SHARE`). Nicht der staerkste Bin:
Der Grundton ist im Mix oft schwaecher als der erste Oberton - "Grundton
mindestens so stark wie die Oktave darueber" verliert die Haelfte der
Oktave-1-Noten, selbst auf der isolierten Spur.

Segmentweise durch die ganze Kette (BTC-Segmente, 2-s-Pooling,
`slash_note`): Echoes 220/238 richtig (92 %), Sailing 99/101 (98 %). Der
reine Handweg-Planer der Anzeige lag auf denselben Events bei 73 % bzw.
72 % (Rest fast immer eine Oktave zu tief). Fehlerklassen: anderes
Instrument eine Oktave unter dem Bass (Echoes-Schlussteil, G#1 unter G#2)
und kurze Noten (0,3-0,5 s) im C2/C3-Bereich. Einzelheiten, Varianten
(0,2 / 0,5, harmonische Summe) und der Entwurf:
docs/exploration/lagenkorrekte-bassanzeige.md.

Eingebaut: Das Event traegt `p` (MIDI, E1 = 28) neben `b`; Note und Lage
muessen zusammen BASS_COMMIT_HOPS stabil sein, gleicher Akkord mit
gleicher Note in anderer Lage ist ein eigenes Event. Das Griffbrett
filtert die Saitenlagen auf die gemessene Tonhoehe, der Handweg
entscheidet nur noch dazwischen (E2: A 7 oder D 2); der Anker im
Record-Modus bietet weiter alle vier.

## Publish-once-Messungen (2026-08-27, eingecheckt)

Fuer das Zeitleisten-Redesign (docs/exploration/zeitleiste-redesign.md)
liegen zwei Skripte direkt hier:

- `messung_einfrieren.py` - simuliert das gleitende 10-s-Fenster und misst,
  wie viel Root-Accuracy das Einfrieren an der Commit-Grenze gegenueber dem
  Endurteil kostet (Ergebnis: ~1 Punkt bei 2 s Verstehzeit).
- `messung_bass_gt.py` - misst `slash_note` gegen die Isophonics-Bass-
  Annotationen bei 2 s / 3 s / Vollsegment-Pooling (Ergebnis: Urteil ab 2 s
  identisch zum Vollsegment; die Instabilitaet kam vom beweglichen
  Intervallende, daher jetzt `BASS_POOL_SECONDS`).


## Beat-Annotationen (2026-09-10)

Fuer die drei Beatles-Titel liegen die Isophonics-Beat-/Downbeat-Annotationen
als `<track>.beats` bei (`zeit schlagnummer`, 1 = Eins; Quelle
isophonics.net, "The Beatles Annotations"). Queen und Carole King haben bei
Isophonics keine Beat-Annotationen. Die Chordlabs des Tarballs sind
byte-identisch mit den `.lab` hier - die Chroma-Korrelations-Offsets oben
gelten also auch fuer die Beats.

Messung `messung_takt_quantisierung.py` (librosa ueber den ganzen Track,
BTC-Grenzen der Offline-Pipeline; Details und Lesart in
docs/exploration/tempo-und-takt.md §4.3/4.4):

| Track | GT bpm | librosa bpm | Beat-F (±70 ms) | Phase med \|dt\| | Downbeat-F (Eins-Abstimmung auf GT-Beats) |
|---|---|---|---|---|---|
| let_it_be | 69,8 | 143,6 (×2) | 0,23 | 211 ms | 0,00 (Wechsel auf 1 und 3, unentscheidbar) |
| eight_days_a_week | 139,5 | 136,0 | 0,39 | 94 ms | 1,00 |
| something | 66,3 | 136,0 (×2) | 0,54 | 107 ms | 1,00 |

Quantisierung der verfeinerten Akkordgrenzen auf ein **Oracle**-Raster
(GT-Beats), median |dt| / Anteil ≤93 ms:

| Track | heute | → Viertel | → Achtel | → 16tel |
|---|---|---|---|---|
| let_it_be | 157 ms / 29 % | **64 ms / 79 %** | 75 ms / 55 % | 124 ms / 35 % |
| eight_days_a_week | 149 ms / 26 % | **41 ms / 66 %** | 197 ms / 33 % | 148 ms / 35 % |
| something | 105 ms / 48 % | **58 ms / 80 %** | 70 ms / 65 % | 82 ms / 52 % |

Auf dem librosa-Raster bringt dasselbe Schnappen nichts (Let It Be, Eight
Days identisch zu heute) - der frueher verworfene Beat-Snap scheiterte am
Raster, nicht an der Idee. Achtel sind bei ~150 ms Grenzfehler zu fein
(Eight Days wird schlechter als ohne); das Raster muss groeber sein als der
Fehler.

## Live-Pfad-Messung mit Beat-Tracker (2026-09-10)

`messung_live_pfad.py` laesst `_display_loop` hop fuer hop ueber die drei
Beatles-Titel laufen (Fake-Loop statt Soundkarte, Tracker synchron) und
misst die COMMITTETEN Events - das, was die Anzeige zeigt - gegen die
annotierten Wechsel, einmal ohne Beat-Tracker (Verfeinerung wie 1.3.1) und
einmal mit Viertel-Snap; dazu die committeten Beats gegen die `.beats`.

**Referenzkorrektur:** Die Isophonics-Beats driften gegen die Rips hier
(Eight Days ~0,3 s ueber den Titel; mit festem Offset Beat-F 0,36, segment-
weise 0,95). Das Skript traegt deshalb je Titel einen linearen Fit
(Skalierung + Versatz, aus den Modell-Beats, Familie am Chroma-Offset
verankert; `--fit` rechnet ihn neu):

| Track | scale | shift | Versatz Titelmitte | Chroma-Offset oben |
|---|---|---|---|---|
| let_it_be | 1,00135 | -0,090 s | +0,07 s | +0,08 |
| eight_days_a_week | 1,00210 | -0,208 s | -0,04 s | -0,15 |
| something | 1,00040 | -0,100 s | -0,06 s | -0,06 |

Bei Eight Days liegen die beiden Referenzen 0,1 s auseinander; Zahlen gegen
den Chroma-Offset sind fuer diesen Titel nicht belastbar. Ergebnisse
(Gewichte iso-only) und Lesart: docs/exploration/beat-tracking-ergebnisse.md
§8.3. Mit den v7-Gewichten (seit 2026-09-10), median |dt| / Anteil <= 93 ms,
driftkorrigiert, ohne Tracker -> mit Viertel-Snap:

| Track | Events | ohne Tracker | mit Snap | Beat-F | Downbeat-F |
|---|---|---|---|---|---|
| let_it_be | 158 | 120 ms / 39 % | **70 ms / 71 %** | 0,96 | 0,65 (Modell zaehlt Halbtakte) |
| eight_days_a_week | 99 | 226 ms / 14 % | **79 ms / 51 %** | 0,99 | 0,995 |
| something | 109 | 137 ms / 30 % | **54 ms / 74 %** | 0,85 | 0,66 |

## Vorwaertskorrektur der Modellgrenze (2026-09-11)

Ausloeser: Telegraph Road (Dire Straits, Outro ab 11:09, D-F-G-D sauber auf
der Eins) - JamPilot zeigte einen Teil der Wechsel einen Schlag VOR der
Taktlinie. Diagnose mit dem Beat-This-Raster als Zeitreferenz (Klicks
+12 ms, Onset-Peaks -31 ms): Die rohe BTC-Grenze liegt live im Median
**184 ms vor** der Taktlinie; ein synthetischer Wechsel bei exakt 5,000 s
kommt bei 4,737 s heraus (-263 ms, in jeder Tonlage gleich - kein
CQT-Vorecho, ein Bias des Modells). Kein Fenster-Drift: gleitende Fenster
liefern -170..-330 ms, der Rest ist das 93-ms-Frame-Dither. Die
Verfeinerung (bis dahin -0,40/+0,05 s) konnte nicht nach vorn und zog die
Grenze mit dem Onset-Gewicht auf den Anschlag des VORIGEN Schlags (median
weitere -170 ms), der Viertel-Snap nahm dann diesen Schlag.

Das relativiert die Timing-Messung oben - und der Grund ist inzwischen
gefunden (Meilenstein-Vergleich, docs/exploration/meilenstein-vergleich-
2026-09.md): `features_from_audio` rechnet die CQT in 10-s-Chunks zu je
108 Frames, 108 Frames sind aber 10,031 s. Die Offline-Zeitachse driftet
+31 ms je Chunk (+558 ms nach drei Minuten); der "Nachlauf der rohen
BTC-Grenze" von +138 ms war dieser Drift. Der Live-Pfad (ein Fenster = ein
Chunk) ist nicht betroffen, `jampilot analyze` und alle Offline-Zahlen in
diesem README sind es. Das ML-Repo trainiert mit derselben Funktion - die
nachtrainierten Gewichte haben den Versatz als Vorlauf gelernt (Uebergabe:
../JamPilotML/docs/rueckmeldung-jampilot-2026-09-11.md).

Varianten im Live-Pfad (`messung_onset_shift.py`; A = `cli.BTC_ONSET_SHIFT`,
B = `btc.REFINE_FORWARD` 0,40 statt 0,05):

| Track / Mass | heute | B | A +0,186 | A +0,186 und B |
|---|---|---|---|---|
| Telegraph Road, Hauptwechsel auf der Taktlinie | 45 % | 45 % | 59 % | **69 %** |
| Eight Days, Event auf demselben GT-Beat wie der Wechsel | 58 % | 63 % | 84 % | **84 %** |
| Eight Days, median \|dt\| | 79 ms | 70 ms | 40 ms | 40 ms |
| Something, gleicher GT-Beat | 87 % | 90 % | 91 % | **92 %** |
| Let It Be, gleicher GT-Beat | 94 % | 93 % | 94 % | 93 % |
| Crazy Little Thing, median \|dt\| | 85 ms | 83 ms | 57 ms | **55 ms** |
| It's Too Late, median \|dt\| | 203 ms | 198 ms | 194 ms | 195 ms |

A allein erzeugt mehr Kurz-Events (X-Y-X-Blips: die verfeinerte Grenze
wird committet, das Modell meldet an der Commit-Grenze noch den alten
Akkord, die Spaetgrenzen-Regel setzt ihn wieder ein); B allein drueckt sie,
bewegt das Timing aber kaum. A+B haelt die Kurz-Events auf dem alten Niveau
und ist seitdem der Default (zwei Frames; drei waren nicht besser). It's Too
Late liegt schon ohne Korrektur spaet (+111 ms) und wird spaeter (+171 ms):
der Bias ist materialabhaengig. Eine Sperre gegen die Blips in der
Merge-Regel wurde verworfen - das zweite Event des Blips lag zufaellig
richtig, ohne Blip wurde das Timing schlechter (Crazy 85 -> 211 ms).

## Nachtrainierte Gewichte auf zeittreuer CQT: v7_2b als Drop-in (2026-09-11)

Das ML-Repo hat die gestueckelte CQT durch die CQT am Stueck ersetzt und
`iso_only`/`v7` darauf neu trainiert (`../JamPilotML/docs/rueckmeldung-
jampilot-2026-09-11.md` §5-6). Dasselbe gilt seit heute fuer
`btc.features_from_audio` hier: `jampilot analyze` und alle Offline-
Messungen in diesem README laufen auf der echten Zeitachse (Frame *i* bei
*i*·93 ms; die Frames sind bitgleich zum ML-Repo, `tests/test_btc.py::
TestZeitachse`). Der Live-Pfad rechnet unveraendert (ein 10-s-Fenster =
ein Stueck). Die Offline-Timing-Zahlen weiter oben ("Nachlauf +138 ms",
Isophonics-Nachlauf) stammen noch von der driftenden Achse.

Referenz-Set im ML-Repo, korrekte Achse, 10 595 Frames (`:6` seit heute
als maj6 gelesen): Original 0,776 / 0,850, `iso_only_2` 0,775 / 0,856,
`v7_2b` 0,767 / 0,854 (exakt / Wurzel); Grenz-Timing aller drei +19 … +40 ms
median, also kein Vorlauf mehr. Bibliotheks-Radar (Urteile Modell : ChordNet,
6285 Songs): Original 48,1 %, `iso_only_2` 49,6 %, **`v7_2b` 52,1 %**
(Pop 64, Country 56, Jazz 37, R&B 52 statt 47; Welt 44 statt 49). Reiche
Qualitaeten: `v7_2b` maj7-Recall 0,81 (Original 0,76), m7 0,95, aber
Sextakkorde 0,16 (Original 0,47, `iso_only_2` 0,57) - It's Too Late stabile
Mitte 0,72 statt 0,805. Das ist der Vereinfachungs-Bias des Teachers, nicht
mehr der Drift.

Live-Simulation mit Viertel-Snap (`messung_onset_shift.py <track> <shift>
0.40 <out.pkl> <weights.npz>`, `REFINE_FORWARD` 0,40; Referenztitel
median |dt| / median dt / Event auf demselben GT-Beat, Telegraph Road
Hauptwechsel auf der Taktlinie / Schlag davor):

| Gewichte, Korrektur | Eight Days | Let It Be | Something | Crazy | It's Too Late | Telegraph |
|---|---|---|---|---|---|---|
| v7 alt, 2 Frames (Stand vorher) | 40 / -27 / 84 % | 70 / +67 / 93 % | 42 / +35 / 92 % | 55 | 195 | 69 / 29 % |
| Original, 0 | 41 / -30 / 84 % | 68 / +66 / 94 % | 43 / +32 / 92 % | 59 | 211 | 68 / 20 % |
| Original, 1 Frame | 51 / -29 / 87 % | 66 / +65 / 94 % | 42 / +36 / 93 % | 49 | 250 | 82 / 18 % |
| Original, 2 Frames | 42 / -27 / 88 % | 66 / +66 / 95 % | 41 / +36 / 94 % | 46 | 251 | 83 / 9 % |
| `iso_only_2`, 0 | 40 / -28 / 88 % | 70 / +68 / 94 % | 41 / +32 / 92 % | 55 | 201 | 64 / 32 % |
| `iso_only_2`, 1 Frame | 40 / -27 / 88 % | 67 / +65 / 93 % | 41 / +31 / 94 % | 49 | 197 | 70 / 18 % |
| `iso_only_2`, 2 Frames | 43 / -27 / 87 % | 67 / +65 / 93 % | 41 / +32 / 95 % | 49 | 229 | 72 / 21 % |
| `v7_2b`, 0 | 37 / -25 / 87 % | 70 / +69 / 94 % | 43 / +32 / 93 % | 60 | 207 | 73 / 15 % |
| **`v7_2b`, 1 Frame (heute)** | 45 / -29 / 87 % | 69 / +69 / 95 % | 41 / +33 / 92 % | 50 | 207 | **83 / 17 %** |
| `v7_2b`, 2 Frames | 43 / -29 / 90 % | 69 / +69 / 95 % | 41 / +34 / 96 % | 48 | 244 | 80 / 7 % |

(`v7_2a`, gleiches Rezept, zweiter Lauf: praktisch dieselben Zahlen wie
`v7_2b`. Let It Be und Something zeigen median dt +65 ms bei jeder
Variante: die Events sitzen auf dem Schlag, die annotierten Wechsel liegen
dort ~60 ms vor dem Schlag.)

Lesart: Im Live-Pfad sind Original, `iso_only_2` und `v7_2b` beim Timing
nicht zu unterscheiden, der Snap schluckt die Modellgrenze bis auf den
Schlag-Entscheid. Die Vorwaertskorrektur wirkt nur noch dort, wo sie den
Schlag kippt (Telegraph, Crazy Little Thing) - ein Frame holt davon fast
alles, zwei Frames kaufen weniger "Schlag davor" bei Telegraph (17 -> 7 %)
mit einem spaeteren It's Too Late (207 -> 244 ms). Seit heute:
`jampilot/data/btc_large_voca.npz` = `run_v7_2b/last.npz`
(sha256 73d18940…), `cli.BTC_ONSET_SHIFT` = 1 Frame. Gegen den Stand davor
(v7 alt, 2 Frames) nirgends schlechter, Telegraph 69 -> 83 % auf der Linie.
Nicht gemessen: Proberaum. Offen: ob der Sextakkord-Verlust von `v7_2b`
(Klavier-Jazzpop) im Spiel auffaellt - dann ist `iso_only_2` der Kandidat
(Sext 0,57, Radar 49,6 %), Timing identisch.

## Was "kein Event" wirklich war: Messregeln seit 2026-09-12

Gegen den Schlag gerechnet fehlte bei 13 % der annotierten Wechsel ein
Event innerhalb von 0,5 s (bis 29 % bei It's Too Late). Die 72 Faelle
einzeln angesehen (v7_2b, ein Frame, mit Snap): **kein einziger geht auf
Publish-once oder den Mindestabstand zurueck.**

- 44 waren keine Akkordwechsel: 23 .lab-Zeilen mit demselben Akkord wie
  davor (Isophonics splittet an Phrasengrenzen), 21 aendern nur den
  Basston (C -> C/7).
- 5 lagen hinter dem Dateiende: die Simulation stoppte mit leerem Puffer,
  die letzten 5 s (Verzoegerung) wurden nie angezeigt - das Outro von Crazy
  Little Thing.
- 14 Events waren da, aber einen Schlag daneben: Let It Be 7 mal F -> C
  exakt einen Schlag frueher (das Modell nennt den Bass auf E schon C),
  It's Too Late 7 mal 0,5-0,9 s spaet (Klavier-Nachlauf).
- 13 Label-Fehler mit richtigem Grundton (D:maj6 -> D, F:maj6 -> F,
  E:sus -> Em7): der Sextakkord-Verlust des Modells.
- ~8 echt verpasst: Something Em/B (3,6 s, zweimal), C/E (dreimal), die
  chromatische Passage ab 153 s; Crazy Little Thing ein F von 0,78 s.

Seitdem gelten in `messung_live_pfad.py` (und damit in
`messung_onset_shift.py`) vier Regeln: Phrasensplits sind keine Wechsel;
Nur-Bass-Wechsel werden getrennt gegen das Bass-Feld der Events gemessen
(`bass_treffer`); die Zuordnung Event <-> Wechsel reicht bis einen halben
Schlag (aus den GT-Beats, sonst Modell-Beats), bis anderthalb Schlaege ist
es der Nachbarschlag, dahinter fehlt es; die Simulation laeuft am Dateiende
um die Verzoegerung mit Stille nach. Die Zahlen mit diesen Regeln (v7_2b,
ein Frame, Snap, Referenz = annotierter Wechsel):

| Titel | Akkordwechsel | auf dem Schlag | Nachbarschlag | fehlt | med \|dt\| | med dt | Nur-Bass getroffen |
|---|---|---|---|---|---|---|---|
| Eight Days a Week | 93 | 81 % | 13 % | 6 % | 37 ms | -32 ms | - |
| Let It Be | 135 | 90 % | 10 % | 0 % | 65 ms | +65 ms | 0 % (n=9) |
| Something | 84 | 90 % | 8 % | 1 % | 41 ms | +35 ms | 17 % (n=12) |
| Crazy Little Thing | 92 | 77 % | 15 % | 8 % | 44 ms | -40 ms | - |
| It's Too Late | 99 | 73 % | 24 % | 3 % | 190 ms | +172 ms | - |

Uebrig bleibt, was das Modell wirklich verfehlt: der Klavier-Nachlauf bei
It's Too Late (ein Viertel der Wechsel einen Schlag spaet), Sextakkorde,
Umkehrungen mit fremdem Basston - und ein neuer Befund: **das Bass-Feld
der Events trifft den annotierten Slash-Bass fast nie** (0 von 9, 2 von 12).
Ob das an der Bassmessung oder an der Nachrueck-Regel ("nie zurueck")
liegt, ist offen.

## Blip-Sperre im Ledger (2026-09-14)

Ausloeser: Proberaum-Eindruck "wieder Flattern, unsinnig kurze Akkorde
zwischengehaengt" (Muster D - A - D bei laufendem D -> A). Meilenstein-
Vergleich (`messung_meilensteine.py`, seit heute mit Kopie der Zustaende -
alte Checkouts geben die Ledger-Liste als Referenz heraus) ueber neun
Konfigurationen, Events < 0,6 s je Minute, Summe ueber die fuenf Titel und
Telegraph Road:

| Konfiguration | kurz < 0,6 s | davon X-Y-X |
|---|---|---|
| v1.1.1 (fb508ac, iso-only) | 11,8 | 7,8 |
| v1.4.0 (67b7a68, v7_2b) | 9,6 | 5,7 |
| main 1051eac (v7_2b, ein Frame) | 9,9 | 5,7 |
| main mit iso-only (e7ad6f1) | 6,3 | 2,8 |
| main mit v7 alt (b9cf896) | 6,9 | 3,6 |
| main mit `iso_only_2` | 8,3 | 4,5 |
| main, Korrektur 0 / 2 Frames | 10,0 / 11,5 | 5,9 / 6,3 |

Gegen v1.1.1 ist main also nicht schlechter; gegen den Takt-Stand vom
11.09. (~7) kam die Haelfte dazu, mit den Gewichten v7_2b (mehr Grenzen:
Crazy Little Thing 133 statt 111 Events), nicht mit Korrektur, Mindestabstand
oder Durchgangsbass (+0,4 Nur-Bass-Events je Minute).

Mechanismus der X-Y-X-Blips (Hop-Spur It's Too Late, 11,6 s): Die
verfeinerte D-Grenze (11,67 s) wird committet, die rohe Modellgrenze liegt
bei 11,99 s; an der Commit-Grenze laeuft fuer das Modell noch Am7, die
Spaetgrenzen-Ausnahme im Merge setzt Am7 an die Grenze (Event 11,89 s),
D kommt ein zweites Mal und wird auf den Folgeschlag geschnappt (12,26 s).
Der Spieler sieht Am7 fuer einen Schlag und D einen Schlag zu spaet. In
allen Versionen vorhanden; die Sperre im Merge (11.09. verworfen) haette
den ersten D-Onset verschoben.

Regel im Ledger (`cli.EventLedger._is_blip`, `BLIP_BEATS`): Ein Event, das
den Akkord von VOR dem letzten Event zurueckbringt, kuerzer als
1,25 Schlaege (Beat-Raster; ohne Raster 0,6 s, Kappung 1,0 s) nach dem
letzten liegt UND hinter dem die Zeitleiste sofort wieder den letzten
Akkord fuehrt (A - D - A - D; der zweite D-Eintrag entsteht im selben
Merge-Lauf wie das A an der Commit-Grenze), faellt weg; die Wiederholung
des D ist dieselbe Aussage. Das erste D bleibt, kein Onset bewegt sich.
Ohne die Nachfolger-Bedingung (erste Fassung) traf die Sperre auch die
Rueckkehr nach einem kurzen Fremdchip - Comfortably Numb 309 s, A - D
(0,25 s) - A - G: das falsche D stand dann 1,4 s statt 0,25 s, und die
echten Ein-Schlag-Wechsel G - C - G bei Crazy Little Thing fielen mit
(Root 85 -> 81 %). Live-Simulation (`messung_meilensteine.py` auf dem
Branch), v7_2b, Root-Accuracy des angezeigten Akkords je Hop / median
|dt| / Kurz-Events < 0,6 s je Minute / davon X-Y-X:

| Titel | main ohne Sperre | erste Fassung | **mit Nachfolger-Bedingung** | `iso_only_2` ohne Sperre |
|---|---|---|---|---|
| Crazy Little Thing | 85 % / 36 ms / 16,5 / 7,8 | 81 % / 37 / 8,2 / 0 | **86 % / 38 / 9,8 / 1,6** | 86 % / 41 / 9,0 / 2,7 |
| Eight Days a Week | 96 % / 39 ms / 2,7 / 1,9 | 97 % / 41 / 0,8 / 0 | **97 % / 41 / 1,2 / 0,4** | 97 % / 32 / 1,6 / 1,6 |
| It's Too Late | 86 % / 197 ms / 14,0 / 9,7 | 85 % / 208 / 3,8 / 0 | **88 % / 211 / 4,6 / 1,1** | 87 % / 183 / 8,9 / 6,2 |
| Let It Be | 86 % / 73 ms / 4,6 / 2,3 | 86 % / 73 / 1,8 / 0 | **87 % / 73 / 2,3 / 0,5** | 86 % / 70 / 6,2 / 3,4 |
| Something | 80 % / 41 ms / 12,2 / 7,3 | 78 % / 47 / 3,8 / 0 | **81 % / 46 / 4,2 / 0,7** | 77 % / 41 / 11,5 / 4,9 |
| Telegraph Road (Taktlinie) | 72 % / 10,1 / 5,0 | 75 % / 5,0 / 0 | **75 % / 6,2 / 1,2** | 66 % / 12,8 / 8,1 |

Mit Nachfolger-Bedingung ist die Root-Accuracy auf jedem Titel gleich oder
besser als ohne Sperre, die Kurz-Events sinken um 55-70 %, die uebrigen
X-Y-X (rund einer je Minute) sind Rueckkehrer ohne zweites D - echte
Wechsel oder Fremdchips, die stehen bleiben sollen. Comfortably Numb
(Solo 262-382 s, `messung_live_pfad.lauf`): alle sechs G/F#-Events und
das A bei 309 s unveraendert, zwei Blips weniger (272,5 s D - Bm).
Timing unveraendert bis auf It's Too Late (+14 ms, Klavier-Nachlauf).
Der Gewichtswechsel auf `iso_only_2` nimmt nur ein Drittel der Blips und
kostet bei Something drei Punkte. Erste Fassung im Proberaum bestanden
(14.09.), die Nachfolger-Bedingung dort noch nicht gespielt.

## Onset-Korrektur statt Blip im Merge (2026-10-13)

Ausloeser: Sailing to Philadelphia im Bass-Modus, "E over F#m7" am
Formanfang (tests/realaudio/REPORT_sailing_to_philadelphia.md). Der
X-Y-X-Blip von oben hat eine zweite Wirkung, die die Blip-Sperre im Ledger
nicht erreicht: Der eingetragene Blip kappt das Bassfenster des committeten
Segments am Blip-Onset - aus 2 s werden 0,25 s, genau der Bass-Vorhalt vor
dem Downbeat. Dort ist der Vorhaltton (oder der Bass des vorigen Akkords)
die klare Mehrheit, ist er Akkordton, sagt `slash_note` ihn, und ueber
"b_up" landet er am Event - unwiderruflich.

`cli._is_onset_correction`: Die Spaetgrenzen-Ausnahme traegt nichts ein,
wenn der nachgemeldete Akkord der von vor dem letzten committeten ist, das
Modell dahinter sofort wieder den committeten fuehrt und dessen Onset
hoechstens `ONSET_HYSTERESIS + _REFINED_LOOKBACK` (0,75 s) hinter dem
committeten liegt - das ist derselbe Wechsel, vom Modell spaeter gesetzt
als von der Verfeinerung. Kein Onset bewegt sich (der Einwand gegen die
Merge-Sperre vom 11.09.).

Live-Pfad (`messung_live_pfad.py`, Baseline 0cb2825): Eventzahl, Timing,
Beats, Nur-Bass-Treffer auf allen drei Titeln unveraendert. Slash-Events
(mit Tracker), vorher -> nachher:

| Titel | Bass gesetzt | Slashes | Aenderung |
|---|---|---|---|
| Let It Be | 116 -> 124 | 7 -> 6 | C/G 236,6 s weg (nicht annotiert) |
| Eight Days a Week | 24 -> 25 | 0 -> 0 | - |
| Something | 72 -> 77 | 13 -> 14 | G/D 3,5 s neu (annotiert G/5) |
| Crazy Little Thing | 45 -> 39 | 10 -> 3 | C/E x2, G/B x5 weg (keine Slashes annotiert) |
| It's Too Late | 82 -> 95 | 15 -> 1 | D/A x6, D6/A x2, Fmaj7/E x4, Fmaj7/C x2 weg (nicht annotiert) |

Das "D/A ueber jedem D6" in It's Too Late (oben als Live-Fehlgriff gefuehrt,
von der Quinten-Regel zu Recht nicht gefiltert, weil dort ein Bass spielt)
war dieser Mechanismus: der Am7-Bass im 0,25-s-Stummel vor dem D6-Downbeat.
Eine Mindestlaenge des Bassfensters (0,3 / 0,5 s) als zweite Huerde wurde
gemessen und verworfen: nach der Merge-Korrektur ohne Nutzen, kostet
Grundtoene von Ein-Schlag-Akkorden. Proberaum-Test bestanden (13.10.,
Sailing to Philadelphia, Telegraph Road).

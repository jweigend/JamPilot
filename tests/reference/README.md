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

Messskripte: Session-Scratchpad `verify_reference.py` (Versions-Check),
Timing- und Bass-Auswertung; alle nutzen nur `jampilot.btc` + librosa.

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

Das relativiert die Timing-Messung oben: Die Chroma-Korrelations-Offsets
stammen selbst aus vorecho-behafteter `chroma_cqt`, der "Nachlauf" der
rohen BTC-Grenze ist gegen das Beat-Grid nicht zu sehen.

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

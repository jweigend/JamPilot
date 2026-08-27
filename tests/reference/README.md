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

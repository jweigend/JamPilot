# Nachtraining-Kampagnen: Ergebnisse (Aug 2026)

**Status:** Abgeschlossen. Ergebnisdokument zum Konzept
[mert-pseudo-labeling.md](mert-pseudo-labeling.md); umgesetzt im
Schwesterrepo **JamPilotML** (`../JamPilotML`, Notebooks 00–06 +
`scripts/kampagne_1000.py` / `kampagne_voll.py`).

**Stand:** 2026-08-26 · 1000-Song-Kampagne + Voll-Lauf über 6.285 Songs ·
Referenz: 5 handannotierte Isophonics-Tracks (`tests/reference/`)

**Abweichung vom Konzept:** Streitfälle wurden nicht manuell nach Gehör
geschlichtet, sondern von einem automatischen Internet-Schiedsrichter
(MusicBrainz/AcousticBrainz, Ultimate Guitar; Konsens-Regeln, nie raten).

---

## Kernzahlen

| | |
|---|---|
| Internet-Urteile pro ChordNet : pro BTC (Voll-Lauf) | **7.810 : 7.200** |
| Bestes Modell (`run_iso_only`, Isophonics-Finetune) | **exakt 0,731 / Wurzel 0,791** (Baseline 0,698 / 0,756) |
| Frame-Label-Abdeckung ChordNet-Duell vs. MERT-Duell | **68,6 %** vs. 36,7 % |
| Voll-Lauf | 6.285 Songs, 4.285 mit Chart-Suche, 3.632 mit Tonart-Konsens, 140.987 Streit-Spans (68,7 h) |
| Trainierbar nach allen Gates / Vetos | 482 / 14.528 |

Das iso-only-Modell ist seit 25.08. als `jampilot/data/btc_large_voca.npz`
im Einsatz; das Original liegt als `btc_large_voca.2026-08-25.backup.npz`
daneben. Erste Hörprobe ohne Auffälligkeiten.

## Zwei Zweitgutachter im Duell gegen BTC

| Duell gegen BTC | MERT-Head | ChordNet 2E1D |
|---|---|---|
| Einigkeit exakt / kompatibel / Wurzel | 0,367 / 0,456 / 0,575 | 0,682 / 0,768 / 0,808 |
| Internet bestätigt BTC : Herausforderer | 3001 : 2022 | **991 : 1178** |
| trainierbar / Vetos (1000er-Sample) | 106 / 4917 | 59 / 2110 |
| Tonart trifft Konsens (BTC: 52,7 %) | 42,3 % | 52,3 % |

Der MERT-Head (Isophonics-trainiert, Frame-Acc 0,48) produzierte eine
Streitliste, die zu 60 % seine eigenen Fehler waren. ChordNet (ChordMini,
MIT; Referenz 0,63 — schwächer als BTC, aber **anders irrend**: andere
Architektur, via FMA/DALI/MAESTRO sozialisiert, identisches Vokabular und
Raster) dreht die Bilanz auf 54 % gegen BTC. Lehre: **Der Zweitgutachter
muss nicht besser sein als das Modell — er muss anders irren.** MERT bleibt
nur als Tonart-Lieferant in Betrieb.

## Schiedsrichter: Plausibilisierung vor Training

Urteilsstufen: Chart belegt genau eine Seite (Wurzel+Qualität) → `btc`/`mert`;
beide belegt → `both`; nur Wurzel klar → `root_only`; nur Tonart-Indiz →
`plausible`; sonst `unresolved`. Kompatible Abweichungen („einer hört mehr",
Am ↔ Am7) sind nie Streit — Schutz vor dem Vereinfachungs-Bias der Charts.

Trainings-Gates für bestätigte Spans: ≥ 1,5 s, ≥ 80 % stabil, ≥ 2
Chart-Versionen, Sieger exakt in ≥ 2 Versionen, tonartverträglich (inkl.
Sekundärdominanten/bVII). Veto-Verteilung Voll-Lauf: überwiegend „zu kurz"
und „instabil" — kurze Streitpassagen sitzen auf Segmentgrenzen, Decay,
Vorhalten, Fehltriggern.

## Inkonsistenz-Landkarte der Bibliothek

Genre-Bilanz (Wurzel-Einigkeit · Urteile ChordNet:BTC, ≥ 80 Songs):
**Jazz 0,754 · 381:124** (die klare Wunde), World 0,744 · 99:64,
Latin 0,754 · 453:433, R&B 0,779 · 240:214, Progressive 0,825 · 876:740,
Rock 0,827 · 3923:3798 — dagegen Pop 0,870 · 414:533 und Country 0,897 ·
81:92 (bestätigen BTC).

Top-Widersprüche (Internet gegen BTC): Emerson, Lake & Palmer *Knife-Edge*
(38:3), Jobim *O Morro Não Tem Vez* (30:2), Sade *No Ordinary Love* (30:3),
Rush *Freewill* (27:2) — und **Porcupine Tree *Russia On Ice* (28:13)**:
genau der BTC-Versagensfall, der das Konzeptdokument motiviert hat,
automatisch wiedergefunden.

## Der Friedhof der Trainingsrezepte

Alle Läufe mit Referenz-Anker (bestes Modell gewinnt; kein Lauf hinterließ
je ein Modell unter der Baseline):

| Lauf | Rezept | ref-exakt | Befund |
|---|---|---|---|
| v2 / v2b | Pseudo-Einigkeit, voller Loss (± Klassenbalance) | 0,698* | Qualitäts-Erosion (Wurzel ↑, exakt ↓): Einigkeit ist dreiklanglastig, wo die Wahrheit reich ist |
| **iso-only** | **nur Isophonics (~190 eigene Rips, auto-gematcht, offsetkorrigiert), voller Loss** | **0,731** | **Champion** |
| v3 / v4 / v5 | + Pseudo-Wurzel-Loss (80 / 1000 / 6285 Songs) | 0,726 / 0,724 / 0,698* | auf drei Skalen wirkungslos — beerdigt |
| v6 | + 482 internet-verifizierte Spans, voller Loss | 0,724 | neutral — Spans sind out-of-domain fürs Referenz-Set |

\* Anker behielt die Baseline. — Externe Teacher: ChordMini-BTC 0,681,
ChordNet 0,631, MERT-Head 0,480 — **off-the-shelf existiert kein stärkerer
Akkord-Teacher als das eigene Isophonics-Finetune.**

## Warum hilft Isophonics-Finetuning, obwohl BTC darauf trainiert wurde?

Berechtigte Frage — drei Antworten, in absteigender Gewissheit:

1. **Andere Akustik, sauberes Alignment.** BTC lernte auf den Mastern der
   Isophonics-Autoren; das Finetune lief auf *unseren* Rips (2009er-Remaster,
   Giles-Martin-Mixe, mp3-Codecs) mit pro Track per Chroma-Korrelation
   gemessenen Offsets (±0,05 s validiert). Der Gewinn ist großteils
   Anpassung an Mastering/Codec/Alignment — nicht neues Harmoniewissen.
2. **Ein Checkpoint ist kein Optimum.** `btc_model_large_voca.pt` ist ein
   bestimmter Trainingsstand mit eigenem Split/Sampling; ein frisches,
   konservatives Finetune (kleine LR, untere Layer eingefroren) kann
   dieselben Daten besser ausschöpfen.
3. **Caveat der Messung:** Die 5 Referenztracks sind Trainings-Holdout,
   stammen aber von denselben Künstlern/Alben wie das Finetune-Set — ein
   Teil der +3,3 Punkte ist In-Domain-Nähe. Deshalb zählt als Gütemaß
   letztlich die Hörprobe auf fremder Musik (bisher: unauffällig gut).

## Was hat die Internet-Recherche dann gebracht?

Als *Trainingsquelle* wenig (482 Spans, v6 neutral) — als **Urteilsinstanz
alles**: Sie hat entschieden, dass MERT als Teacher untauglich ist, dass
ChordNet der bessere Detektor ist, wo die Genre-Lücke sitzt, und sie liefert
die belegte Inkonsistenz-Landkarte samt Tonart-Konsens für 3.632 Songs.
Ohne unabhängiges Urteil wüssten wir nur, *dass* sich Modelle uneinig sind —
nicht, *wer* falsch liegt. Die dünne Trainingsausbeute ist der bewusste
Preis der „nie raten"-Gates (Precision vor Recall).

**Wichtige Metrik-Warnung:** Modell-Einigkeit ist kein Gütemaß — sie misst
Ähnlichkeit zum (BTC-verwandten) Zweitgutachter. iso-only hat *niedrigere*
ChordNet-Einigkeit (0,779) als die Baseline (0,808) und ist trotzdem das
bessere Modell. Güte messen nur Referenz-Set und Hörprobe.

## Konsequenzen

1. **iso-only bleibt im Einsatz**; Hör-Checkliste für den tieferen Test:
   ELP, Jobim, Sade, Rush, Porcupine Tree (s. o.).
2. **Pseudo-Label-Training ist beerdigt** (drei Skalen, sechs Läufe).
   Weitere Modell-Gewinne nur über *neue echte Labels*: Jazz-/Klavier-
   annotierte Sets, Selbstaufnahmen bekannter Progressionen oder der
   synthetische Korpus aus `../JamPilotML/docs/technical-design.md` —
   der Klavier-Blindfleck (*It's Too Late*: alle Zweitgutachter versagen)
   zeigt dorthin.
3. **Das Inkonsistenz-Radar ist das bleibende Produkt:** Duell +
   Schiedsrichter vermessen jede künftige Modellversion bibliotheksweit in
   < 4 h (`scripts/kampagne_voll.py`), vollständig gecacht und resumierbar.

## Reproduktion

JamPilotML: Notebooks 00–06 (Doku + Fahrplan), `scripts/kampagne_1000.py`
(sample/evidence/pipeline/train/chordnet), `scripts/kampagne_voll.py`
(pipeline/train). Ergebnisdaten: `data/*.parquet`, Streit-Details je Song in
`data/cache/compare_cn/<id>.json`, Modelle in `data/runs/<name>/best.npz`
(Drop-in für `btc_large_voca.npz`, bitkompatibel validiert).

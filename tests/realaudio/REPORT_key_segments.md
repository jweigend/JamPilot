# Experiment-Report: Tonart aus Segmenten (Label + gemessener Bass + Dauer)

**Frage:** Nach dem verworfenen Frame-Label-Hybrid (REPORT_key_labels.md) der
strukturell neue Ansatz: Tonart nicht mehr primär aus rohem Chroma, sondern
aus **Segmenten** — Akkordlabel + gemessener Bass (Tiefband, `bass.dominant`
wie im Live-Pfad) + Dauer. Neu gegenüber dem Frame-Hybrid: der Bass als
Signal, und Segmentstruktur macht **Progressionskontext** (Kadenzen) möglich.
**Datum:** 2026-08-24
**Zweig:** `feature/nashville-scale-system`
**Status:** **Als Ersatz verworfen, als Erkenntnis wertvoll:** Das
Segment-Signal ist stark, aber **komplementär falsch** zum Chroma — es
repariert genau die Chroma-Fehlerklasse und bricht dafür auf Songklassen,
die das Chroma sicher kann.

## Setup

Segmente offline aus den BTC-Labels (`segments_from_labels`), Bass je Segment
aus `fold_bass_chroma` + `bass.dominant` (exakt die Produktionsmessung).
Live-simuliert im 0,25-s-Hop, Halbwertszeit 120 s, MIN 12 s, Hysterese —
vergleichbar zur Produktions-Baseline (mitgerechnet). Drei Varianten:

- **S1 histo:** Dauergewichtetes Histogramm aus Akkordtönen + Grundton
  doppelt + Bass doppelt, Krumhansl-Korrelation.
- **S2 diaton:** Kein Krumhansl — je Tonart ein Diatonik-Score pro Segment
  (Skalenzugehörigkeit von Tönen/Grundton/Bass, V7-auf-Stufe-5-Bonus,
  Tonika-Bonus). Gewichte ad hoc, erste Setzung, ungetunt.
- **S3 kadenz:** S2 + Sequenz: Quintfall-Übergänge (V7→I stark, V→I schwach)
  belohnen die Zieltonart.

Skript: Session-Scratchpad `segment_key_experiment.py` (+ `segment_cache/`).

## Ergebnis

| Variante | Tonika-Sprünge | korrekt (Mittel) |
|---|---|---|
| **Baseline (Chroma, Produktion)** | **4** | **77,9 %** |
| S1 histo | 9 | 72,1 % |
| S2 diaton | 15 | 71,7 % |
| S3 kadenz | 11 | 71,3 % |

Die Mittelwerte verdecken das Eigentliche — die **Fehlerklassen tauschen**:

| Track | Baseline | S3 kadenz |
|---|---|---|
| Eight Days (D) | 10 % (D→Bm→E) | **100 %, 0 Sprünge** |
| Peg (G) | 96,7 % (D-Einschwinger) | **100 %, sofort G** |
| Sting Faith (A) | 94,1 % | **0 %** (hält D) |
| Something (C) | 100 % | 52,9 % (pendelt C↔F) |
| It's Too Late (A/F) | 100 %, 0 Sprünge | 94,8 %, 4 Sprünge (Am↔F) |
| Misty/Garner (E♭) | 0 % (Cm) | 0 % (A♭) |

## Warum die Segment-Sicht genau dort bricht

- **Sting (mixolydisch, Strophe `A|G|D`):** G ist in A-Dur nicht
  leitereigen (♭VII). Diatonik-Scoring *muss* D-Dur bevorzugen — dort sind
  A, G und D alle leitereigen (V, IV, I). Das ist kein Gewichtungsfehler:
  auch mit ♭VII-Toleranz bliebe D vollständiger. Modal gefärbte Musik trennt
  nur die Betonung des tonalen Zentrums (Phrasenanker), nicht die Skala.
- **Something (C-Dur):** Die Signaturwendung `C → C7 → F` enthält ein echtes
  V7→I nach F — die Zwischendominante. Der Kadenz-Bonus erkennt die
  Tonikalisierung korrekt und zieht trotzdem die falsche Tonart. Dieselbe
  Fehlerklasse wie im verworfenen §4-Fix (REPORT über Zwischendominanten):
  lokale Kadenz ≠ globale Tonart.
- **Misty/Garner:** fällt in *jeder* bisher gemessenen Repräsentation
  (Chroma: Cm; Labels/Segmente: A♭). Kandidat für Phrasen-/Schlussauflösung
  als Signal — offen.

Und die Gegenrichtung: **Eight Days** (verschmiertes Chroma) wird von der
Segment-Sicht mühelos und stabil richtig gelöst — inkl. des gemessenen
Basses, der schon S1 auf 96,7 % hebt. Die Information, die das Chroma nicht
hat, ist also real und stark.

## Einordnung

1. **Als Ersatz fürs Chroma: nein** — netto schlechter (72 % / 11+ Sprünge
   gegen 78 % / 4), weil modale Songs und Zwischendominanten neue Fehler
   einführen, die das Chroma nicht macht.
2. **Die Signale scheitern auf disjunkten Songklassen.** Chroma: verliert
   bei Schmiere/Parallel-Moll. Segmente: verlieren bei Modalität und
   Zwischendominanten. Eine Kombination bräuchte einen Regime-Detektor
   („diatonisch-kadenziell“ vs. „modal-vampig“) — die naiven Kombinationen
   sind in REPORT_key_labels.md bereits negativ vermessen. Das ist ein
   Forschungsprojekt mit echtem Potenzial, kein Quick Win.
3. **Vor jedem Tuning: Referenzset vergrößern.** S2/S3 haben ≥6 freie
   Gewichte; 9 Tracks (in-domain-lastig, vgl. Genre-Report) tragen das
   nicht — Tuning darauf wäre Overfitting mit Ansage.
4. Für die Nashville-Praxis bleibt der **Key-Pin** die verlässliche
   Abdeckung der Restfehler.

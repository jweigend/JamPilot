# Fix-Report: maj7-Bias entschärft

**Datum:** 2026-07-15
**Änderung:** `jampilot/chords.py` — neue Konstante `THIRD_OVERTONE = 0.28`, eingebaut in `_build_templates()`
**Motivation:** In allen vier Realaudio-Tests (Sting, Peg, Misty×2) war die häufigste Einzelabweichung `maj7`-statt-`7`/`Dur` (siehe `REPORT_*.md`).

---

## Ursache

Die große Terz (Intervall 4) erzeugt ihren 3. Teilton eine Oktave+Quinte höher — das fällt auf **Intervall 11 = die große Septime**. Dadurch trägt schon ein reiner Dur-Dreiklang *und* ein Dominantseptakkord Schein-Energie auf der maj7-Note, und das `maj7`-Template gewann. Der Dominant-b7 (Intervall 10) entsteht aus **keinem** Terz-Oberton — die Verwechslung war deshalb einseitig (`7`→`maj7`, nie umgekehrt).

## Fix

Die erwartete Oberton-Energie auf Intervall 11 wird in die **Dur-Terz-Templates** (`""` und `"7"`) eingebaut. Sie „erklären" ihren eigenen Oberton selbst und werden nicht mehr vom `maj7` geschlagen — ein **echtes** `maj7` (mit starkem, gespieltem 11) gewinnt weiterhin.

Für die **Moll-Terz** (Oberton auf 10 = b7) bewusst **nicht** angewandt: dieselbe Korrektur fräße echte `m7`-Akkorde weg, die in Jazz-Material häufig und richtig sind (Misty: Fm7, Cm7, Bbm7).

Wert `0.28` per Parameter-Sweep über die vier Aufnahmen kalibriert (Chroma einmal gecacht, dann `match_chord`-Varianten verglichen).

---

## Verifikation

### Regression (darf nichts brechen)
| Test | Ergebnis |
|---|---|
| Selbsttest (8 Grundstellungen + 10 Umkehrungen) | ✅ CQT 8/8 clean, 8/8 noisy, Umkehrungen 10/10; `C7` bleibt `C7` |
| Volle pytest-Suite | ✅ 275 passed |

### Wirkung (Qualitäts-Verteilung, echter Code auf gecachten Chromas)
| File | maj7 vorher→nachher | dom7 vorher→nachher |
|---|---|---|
| sting | 44,3% → **26,8%** | 7,6% → **11,0%** |
| peg | 36,8% → **20,3%** | 8,1% → **20,1%** |
| misty_ab | 26,6% → **16,3%** | 8,5% → **14,5%** |
| misty_eb | 27,5% → **16,8%** | 6,2% → **10,9%** |

### Grundton-Stabilität (der Fix ändert Qualität, nicht Root)
95–98,5 % aller Frames behalten denselben Grundton wie vorher.

### End-to-End (`jampilot analyze`)
**Sting** — Tonika A-Dur (Verse), Segmente:
| | `A` | `Amaj7` | `A7` |
|---|---|---|---|
| vorher | 23 | 23 | 14 |
| nachher | **37** | 19 | 15 |

→ behebt exakt den Report-Befund: `Aadd9` (A-C#-E-**H**) erschien als `Amaj7` (A-C#-E-**G#**, falsches G#). Jetzt `A` — kein Falschton.

**Misty (clean, Eb)** — Tonart bleibt `Eb`; maj7-Segmente 85→53, dom7-Segmente 20→36; echte Tonika `Ebmaj7` überlebt (17 Segmente), überton-aufgeblähte werden zu korrektem `Eb`.

---

## Fazit
Der Fix ist **prinzipiell** (physikalisch motiviert), **kalibriert** (Sweep über echte Aufnahmen), **regressionsfrei** (Selbsttest + 275 Tests grün) und **gezielt** (Qualität korrigiert, Grundton/Skelett/Tonart unverändert, echte maj7 und m7 erhalten). Die häufigste dokumentierte Schwäche der Testreihe ist damit adressiert.

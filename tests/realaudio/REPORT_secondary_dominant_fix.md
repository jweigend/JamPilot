# Fix-Report: Zwischendominant-Ausnahme (§4-Sketch) — an Realaudio verworfen

**Datum:** 2026-07-17
**Ausgangspunkt:** `REPORT_key_prior_safe_voicings.md` §4 skizzierte einen „gezielten
Fix": `X7`-Kandidaten in Dur straffrei stellen, wenn ihr Zielgrundton (Quinte
abwärts) leitereigen ist — um echte Zwischendominanten wie `E7` in Peg (V/ii in
G-Dur) zurückzuholen, die der Tonart-Prior fälschlich nach `Em7` kippt.
**Ergebnis:** Umgesetzt, an denselben vier Aufnahmen gemessen, **verworfen**.
Der Prior in [`harmony._foreign_tones`](../../jampilot/harmony.py) bleibt
unverändert; nur ein erklärender Kommentar wurde ergänzt.

---

## 1. Die Ausnahme wurde exakt wie skizziert gebaut

`_foreign_tones` gab `0` zurück, sobald `candidate.quality == "7"` **und**
`(candidate.root + 5) % 12` (das Auflösungsziel eine Quinte abwärts) leitereigen
war. Gemessen wurde auf den gecachten Chromas des Vorreports, exakt im Live-Pfad
(interpretieren **vor** `keys.add`, rollierende Tonart mit 30-s-Halbwertszeit).

## 2. Der Fix trifft sein Ziel — und reißt eine dokumentierte Korrektur ein

Netto-Label-Änderungen gegen die bisherige Welt (voller Penalty):

| Datei | geänderte Fenster | Kernbewegung |
|---|---|---|
| **peg** (G) | 84 (9,0 %) | `Em7→E7` ×17, `Em→E7` ×6 — **das gewünschte Ziel** |
| **sting_faith** (A) | 77 (7,3 %) | `F#m7→F#7` ×39, `F#m→F#7` ×2 — **Regression** |
| misty (Ab) | 36 (5,4 %) | `Dm7→D7` ×7, `Fm7→F7` ×4 |
| misty2 (Eb) | 73 (9,0 %) | `Am7→A7` ×14, `Dm→D7` ×11 |

Peg gewinnt sein `E7` zurück — genau der §4-Wunsch. Aber Sting verliert
`F#m` (die vi der Tonart): `REPORT_sting_faith` / §3 des Vorreports zählte
`F#7/F# → F#m7/F#m` (×61) ausdrücklich als **Gewinn**. Der neue Fix macht ~40
davon rückgängig.

## 3. Warum sich das nicht auftrennen lässt

Peg und Sting stellen exakt dieselbe Aufgabe — mit gegensätzlicher Wahrheit:

| Song | Tonart | 6. Stufe | Moll-Lesart (vi) | Dom-Lesart | Ziel (Quinte ↓) | Ground Truth |
|---|---|---|---|---|---|---|
| Peg | G-Dur | E | Em7 | E7 (V/ii) | A (leitereigen) | **E7** |
| Sting | A-Dur | F# | F#m7 | F#7 (V/ii) | B (leitereigen) | **F#m** |

Beide Akkorde sitzen auf dem 6. Skalengrad, beide haben ein leitereigenes
Auflösungsziel, beide unterscheiden sich **nur in der Terz** (klein vs. groß).
Die Zielgrundton-Regel kann sie prinzipiell nicht trennen — sie flippt beide
gleich. Was sie trennt, ist allein das Terzsignal im Audio, und **das gewichtet
`match_chord` bereits**. Der Kontext-Penalty war genau der Daumen, der die
mehrdeutige vi in ihrer leitereigenen Moll-Form hielt.

## 4. Auch ein abgeschwächter Penalty rettet nichts

Statt die Zwischendominante ganz straffrei zu stellen, wurde der Fremdton-Leitton
nur diskontiert (Faktor 1,0 = alt … 0,0 = harter §4-Sketch). Gezählt: `min→dom`-
Flips (Regressionskandidat, z. B. Sting `F#m7→F#7`) vs. `maj7→dom` (erwünscht):

| discount | Sting min→dom | Peg min→dom | Peg maj7→dom |
|---|---|---|---|
| 0,00 | 68 | 55 | 11 |
| 0,55 | 30 | 18 | 2 |
| 0,85 | 9 | 2 | 2 |

Der erwünschte Peg-Effekt (`Em7→E7`) **ist** ein `min→dom`-Flip und damit
typgleich mit der Sting-Regression. Sie bewegen sich bei jedem Schwellwert
gemeinsam; kein Faktor holt Pegs `E7` zurück, ohne Stings `F#m` zu kippen.

## 5. Nebenschaden: neuer min→dom-Bias

Das Projekt bekämpft primär den maj7-Bias (7 wird als maj7 gelabelt). Der §4-Fix
tauscht ihn gegen einen **min→dom-Bias**: leitereigene ii/iii/vi kippen
systematisch in Dominantseptakkorde. Ein Bias durch einen spiegelbildlichen zu
ersetzen ist kein Fortschritt.

## 6. Fazit & was ein echter Fix bräuchte

**Verworfen.** Ein statischer Tonart-Prior kann V/ii nicht von vi unterscheiden —
das ist keine Tuning-, sondern eine Informationsfrage. Die Auflösung einer
Zwischendominante ist ein **Progressions**-Signal: erst wenn der Folgeakkord den
Zielgrundton trägt (E7 → Am), ist die Dominantfunktion belegt. Genau diese
Fähigkeit fehlt `interpret_chord` noch bewusst
([`harmony.py`](../../jampilot/harmony.py): „Grundtonkorrekturen brauchen
Progressions-/Basskontext"). Ein Fix gehört dorthin — Root-Motion/Auflösung über
zwei Fenster —, nicht in den fensterlokalen Skalen-Prior.

**Code-Stand:** `_foreign_tones` unverändert (nur Kommentar + Testnotiz).
Skripte im Session-Scratchpad (`ab_dominant_fix.py`, `sweep_discount.py`).

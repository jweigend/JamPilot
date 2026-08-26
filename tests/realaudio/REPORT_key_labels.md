# Experiment-Report: BTC-Akkordlabels als Zusatzsignal für die Tonart

**Frage:** REPORT_key_window.md ließ als Ausblick offen: Ein Histogramm aus
den BTC-*Labels* (Akkordtöne je Frame, Grundton doppelt) traf offline 7/9
Tonarten — taugt das als Quick Win (Hybrid/Re-Ranker) gegen die zwei
Restfehler des Zwei-Skalen-Estimators? Anlass: Mit den Nashville-Stufen ist
die Tonart nicht mehr „nice to have", eine falsche Tonika schreibt alle
Stufen falsch.
**Datum:** 2026-08-24
**Zweig:** `feature/nashville-scale-system`
**Status:** **Verworfen.** Keine der 15 gemessenen Varianten schlägt die
Baseline netto. Ein positiver Nebenbefund (Modulationsdetektor), s. u.

## Setup

Live-Fütterung wie im Fenster-Experiment repliziert, aber durch die
**Produktionsklasse** `TwoScaleKeyEstimator` (Baseline reproduziert exakt:
4 Tonika-Sprünge, 77,9 %). Label-Signal: je 93-ms-Frame aus dem BTC-Label
ein 12er-Vektor (Akkordtöne 1, Grundton 2; N/? leer). Zwei Einbauformen:

1. **Input-Blend:** `mix = (1−w)·chroma_norm + w·label_norm`, mit
   Chroma-Pegel reskaliert (Stille-Gate unverändert), w ∈ {0,25, 0,5, 0,75, 1}.
2. **Score-Re-Ranker:** Chroma bleibt alleiniges Histogramm-Signal; ein
   paralleles Label-Histogramm (gleiche 120-s-Halbwertszeit) gibt in der
   Entscheidung `combined = chroma_corr + β·label_corr` — immer, oder nur
   „bei knappen Fällen" (Gate: Vorsprung der besten Tonika auf die beste
   andere < 0,05/0,10). β ∈ {0,3 … 2,0}.

9 Tracks wie gehabt; dazu der synthetische Modulationstest (+1 HT ab 100 s,
Chroma UND Labels gerollt). Skripte: Session-Scratchpad
`label_hybrid_experiment.py`, `label_rerank_experiment.py` (Label-Cache dort).

## Ergebnis: kein Netto-Gewinn, nur Fehler-Tausch

| Variante | Tonika-Sprünge (Summe) | Tonika korrekt (Mittel) |
|---|---|---|
| **Baseline (Ist)** | **4** | **77,9 %** |
| Blend w=0,25 | 10 | 77,3 % |
| Blend w=0,5 | 8 | 80,1 % |
| Blend w=0,75 / 1,0 | 9 | 76,8 / 76,1 % |
| Re-Ranker β=0,3 … 0,5 (auch gated) | 10–12 | 77,5–78,1 % |
| Re-Ranker β=0,75 … 2,0 | 14–23 | 76,0–77,4 % |

Die entscheidenden Einzelbefunde:

- **Blend w=0,5 repariert Eight Days komplett** (10 → 100 %, D statt Bm/E) —
  **und zerlegt dafür Sting Faith** (94 → 30 %): die im Fenster-Report
  vorhergesagte D/A-Ambiguität der Strophe `A|G|D`. Dazu wackelt It's Too
  Late (Fehlstart D, 100 → 92,5 %). Fehler-Tausch, kein Fortschritt.
- **Der Re-Ranker schont Sting** (bei β≤0,5 sogar 94 → 98 %), **repariert
  aber Eight Days nie**: Auf Score-Ebene reicht der Label-Bonus für D nicht,
  der Estimator pendelt zwischen Bm und E (auch bei β=2,0 nur 29 %). Das
  „Bonus nur bei knappen Fällen"-Gate ändert daran nichts, erzeugt aber
  zusätzliches Flackern an der Gate-Kante (Eight Days bis 7 Sprünge).
- **Misty/Garner bleibt in jeder Variante falsch** — die Labels schieben nur
  von Cm nach A♭ (Subdominante), nie nach E♭; teils als neues
  Cm↔A♭-Pendeln. Die Parallel-/Nachbar-Ambiguität ist mit Statik nicht zu
  trennen (vgl. REPORT über Zwischendominanten: das trennt nur
  Progressionskontext).
- Fehl-Resets: 0 Adopts in allen Varianten auf allen echten Tracks; die
  Stille-Resets (7) sind die erwarteten Song-Enden.

## Positiver Nebenbefund: Labels helfen dem Modulationsdetektor

Im synthetischen Modulationstest ist der Input-Blend deutlich stärker als
die Baseline — Peg: nie → 38 s, Misty2: nie → 51 s, Crazy: 53 → 42 s
(w=0,5–0,75), ohne einen einzigen Fehl-Reset auf den echten Tracks. Das
Label-Signal entrauscht das kurze Fenster offenbar wirksam. Eine Variante
„Labels NUR ins kurze Detektor-Histogramm" wurde nicht gemessen (Achtung:
`adopt` kopiert das kurze Histogramm ins lange — das Label-Signal sickerte
beim Reset ins Hauptsignal). Eigenes Experiment, falls Modulationslatenz je
zum Pain-Point wird; Evidenz bisher nur synthetisch.

## Empfehlung

1. **Label-Hybrid als Quick Win verwerfen.** Die zwei Restfehler (Eight
   Days: Chroma-Schmiere, Misty: Parallel-Moll) sind mit dem statischen
   Label-Prior nicht billig zu heilen — dieselbe Fehlerklasse wie beim
   verworfenen Zwischendominanten-Fix: es fehlt Progressionskontext, kein
   weiteres statisches Signal.
2. **Der eigentliche Quick Win für die Nashville-Praxis liegt im Produkt,
   nicht im Signal:** eine manuelle Tonart-Festlegung (Key-Pin) in der UI.
   Beim Mitspielen ist die Tonart oft bekannt; ein Pin macht die Stufen
   sofort verlässlich und kostet keinen Erkennungs-Tradeoff. Das Springen
   selbst ist mit dem Zwei-Skalen-Estimator bereits behandelt (27 → 4).
3. Danach wie geplant der Instrument-Playtest; die Signalwege mit Substanz
   (HPSS/Tuning vor der Tonart-Faltung, Progressionskontext) sind Projekte,
   keine Quick Wins.

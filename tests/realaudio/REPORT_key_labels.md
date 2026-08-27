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

## Nachtrag 2026-08-27: Zehnter Track deckt einen Metrik-Split auf

Anlass: You and Your Friend (Dire Straits, g-Moll, terzlose Voicings; jetzt
`tests/realaudio/you_and_your_friend.mp3`) - die Produktion meldet dort
G-DUR. Messung mit identischem Setup wiederholt (Baseline w=0 exakt
reproduziert: 4 Spruenge / 77,9 % auf den alten 9 Tracks), Track als
zehnter ergaenzt, zusaetzlich Geschlecht (Dur/Moll) ausgewertet
(Skript: Session-Scratchpad `label_hybrid_10tracks.py`).

Ergebnis:

- **Die Tonika-Metrik ist auf diesem Song blind**: Tonika G stimmt in allen
  Varianten (~100 %), falsch ist nur das Geschlecht - Baseline 0 % Gm
  (durchgaengig G-Dur samt Kreuz-Schreibweise).
- **Jede Label-Beimischung repariert das Geschlecht**: w=0,25 -> 89 % Gm,
  w=0,5 -> 91 %, w=1,0 -> 96 %.
- **Das Tonika-Gesamturteil bleibt Fehler-Tausch** (w=0,5 ueber 10 Tracks:
  82,1 % vs. 80,1 %, aber 8 statt 4 Spruenge; Sting weiterhin 94 -> 30 %).
  Die Verwerfung des vollen Hybrids bleibt bestehen.

**Offene Spur (nie gemessen):** Die Labels sind schaedlich fuer die
Tonika-WAHL, aber stark fuer die Dur/Moll-ENTSCHEIDUNG. Ein schmaler Hybrid
- Tonika aus dem Chroma wie heute, nur das Geschlecht der gewaehlten Tonika
per Label-Votum - wuerde You and Your Friend reparieren, ohne den
Tonika-Pfad anzufassen, an dem Sting haengt. Sichtbar betroffen sind genau
Nashville-Label und Vorzeichen-Schreibweise.

### Messung des schmalen Hybrids (2026-08-27, gleicher Tag)

Skript: Session-Scratchpad `mode_hybrid_experiment.py`. Tonika unveraendert
aus der Produktions-Baseline; Geschlecht pro Hop per Votum aus einem
gedaempften Label-Histogramm NUR fuer die gewaehlte Tonika. Geschlechts-GT
je Track festgelegt (It's Too Late = a-dorisch -> Moll; Sting =
mixolydisch -> Dur). Bewertet nur Hops mit Tonika in der GT.

| Geschlechts-Quelle | korrekt (hop-gew.) | Track-Mittel | Umschalter |
|---|---|---|---|
| Chroma (heute) | 66,9 % | 76,4 % | 2 |
| **Akkord-Votum hl=120s** | **98,4 %** | **98,8 %** | 4 |
| Akkord-Votum hl=30s | 98,6 % | 98,9 % | 5 |
| Terz-Votum hl=120s | 97,4 % | 98,0 % | 2 |

(Akkord-Votum: Moll- vs. Dur-Masse der Labels mit Grundton == Tonika,
m/m6/m7/mMaj7 gegen ""/6/7/maj7, sus/dim/aug enthalten sich; Fallback bei
zu wenig Evidenz ist das Chroma-Urteil.)

Einzelbefunde:

- **You and Your Friend: 0 % -> 98 %** (Ziel des Experiments).
- **It's Too Late: 0 % -> 100 %** - Ueberraschungsfund: das Chroma meldet
  die a-dorische Nummer durchgaengig als A-DUR; der "unbeobachtete
  Moll-Fall" der Nashville-Stufen lag schon immer im Set, verdeckt von der
  Tonika-Metrik. ZWEI von zehn Tracks zeigten also das falsche Geschlecht.
- Kein Dur-Track kippt (alle 100 %; Crazy verbessert sich 93 -> 100 %).
- Preis: Sting (mixolydisch) 95 -> 92 %; 4 Geschlechts-Umschalter auf
  ~7900 Hops.

**Empfehlung: Akkord-Votum hl=120s produktiv machen** - Tonika-Pfad bleibt
unangetastet (die Verwerfung oben gilt weiter), nur k.minor kommt aus dem
Label-Votum. Sichtbare Wirkung: korrektes Moll-Label, b-Schreibweise und
Nashville-Stufen auf Moll-Nummern.

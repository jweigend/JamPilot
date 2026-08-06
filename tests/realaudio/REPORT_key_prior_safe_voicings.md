# Fix-Report: Tonart-Prior + sichere Tonmengen an Realaudio gemessen

**Datum:** 2026-07-16
**Änderung:** `daf5496` (key-aware interpretation) + `8ec7a03` (safe voicings), Branch `feature/control-guitar-audio`
**Methode:** Chromas einmal pro Datei gecacht (Live-Pfad exakt repliziert: 1,5-s-Fenster, 0,25-s-Hop, RMS-Stille). „Alt" = roher `match_chord`-Gewinner (Stand master nach dem `THIRD_OVERTONE`-Fix). „Neu" = `interpret_chord` mit rollierender Tonart (30-s-Halbwertszeit, interpretieren **vor** `keys.add`, wie in `cli.py`), danach `safe_pitch_classes`.

---

## 1. Invariante bestätigt

Der Prior korrigiert nur die Qualität, nie den Grundton: **0 Root-Änderungen in allen 4 465 Akkordfenstern** über alle vier Aufnahmen. Die harmonische Landkarte der bisherigen Reports bleibt exakt gültig.

## 2. Wie oft der Prior eingreift

| Datei | korrigierte Fenster | maj7-Anteil | dom7-Anteil | skalenfremder Ton im Fenster* |
|---|---|---|---|---|
| sting_faith (A) | 16,6 % | 26,8 % → **22,2 %** | 11,3 % → 6,9 % | 45,2 % → **34,9 %** |
| peg (G) | 17,9 % | 20,0 % → **15,6 %** | 20,1 % → 16,3 % | 43,7 % → **28,5 %** |
| misty (Ab) | 12,4 % | 17,4 % → **15,7 %** | 13,4 % → 11,3 % | 42,0 % → **34,7 %** |
| misty2 (Eb) | 12,1 % | 17,1 % → **16,5 %** | 10,5 % → 8,1 % | 37,8 % → **30,0 %** |

\* relativ zur stabilen Ganzdatei-Tonart. Vorsicht: Diese Metrik misst genau das, was der Prior optimiert — sie belegt für sich allein keine Korrektheit. Da aber alle vier Referenzen ausdrücklich **nicht modulieren**, ist die Richtung ein echtes Signal.

## 3. Belegte Treffer (gegen dokumentierte Fehler der bisherigen Reports)

- **Peg:** `Dmaj7` → `D` (×30) und → `D7` (×10). Genau die in `REPORT_peg.md` §5 monierte Schwäche („Dmaj7 taucht häufig auf, wo die Figur nur G/D-Anteile hat"). Fensteranteil `Dmaj7`: 4,8 % → **0,5 %**. Ebenso `Cm` → `C` (×10).
- **Sting:** `Amaj7` → `A` (×29; Tonika!), `F#7`/`F#` → `F#m7`/`F#m` (×61; vi der Tonart). Das dokumentierte maj7-Übergewicht sinkt weiter.
- **Misty:** Lehrbuch-Korrekturen: `G#m` → `G#` (Tonika-Dur), `F` → `Fm` (vi), `D#maj7` → `D#7` (die V7 — exakt der maj7-Bias).

## 4. Ehrlicher Befund: der Prior frisst echte Zwischendominanten

- **Peg:** `E7` → `Em7` (×17) und `F#` → `F#m` (×10). Die Ground-Truth hat dort **echte** `E7#9`/`F#7#9` (Zwischendominanten in G-Dur mit großer Terz). `E7`-Anteil: 4,2 % → 2,4 %. `REPORT_peg.md` lobte „`E7` exakt" — ein Teil davon geht wieder verloren.
- **Ursache:** Die Dominant-Ausnahme in `harmony._foreign_tones` gilt nur für die V. Stufe in **Moll**. Zwischendominanten in Dur (V/ii = E7 in G) tragen einen skalenfremden Leitton und verlieren knappe Entscheidungen.
- **Nachtrag 2026-07-17 — der skizzierte Fix ist verworfen:** Die naheliegende Regel (`X7` straffrei, wenn das Ziel eine Quinte abwärts leitereigen ist) wurde gebaut und an Realaudio gemessen. Sie holt Pegs `E7` zurück, reißt aber die in §3 gefeierte Sting-Korrektur `F#7→F#m7` (×61) wieder ein: V/ii (E7 in G) und vi (F#m in A) sitzen beide auf dem 6. Skalengrad mit leitereigenem Ziel und unterscheiden sich nur in der Terz — ein statischer Skalen-Prior kann sie nicht trennen, nur die Auflösung (Progressionskontext) belegt die Dominantfunktion. Details und Messung: `REPORT_secondary_dominant_fix.md`.
- **misty2:** `A#m7` → `A#7` (×11) ist ambivalent — die Referenz enthält beide (Bbm7 im Ab-gerichteten Zug, Bb7 als V7).

Größenordnung: die fraglichen Rückschritte betreffen ~1–3 % der Fenster, die belegten Treffer ~5–8 %.

## 5. Stichprobe Peg-Intro (härteste GT-Stelle)

Im chromatischen Abstieg (0–16 s) ändert der Prior **nichts** — alle acht Grundtöne stehen unverändert in richtiger Reihenfolge, `E7` bleibt dort `E7`. Die Audioevidenz ist klar genug; der Prior greift nur in den mehrdeutigen Verse/Chorus-Passagen ein. Genau so war er gemeint.

## 6. Sichere Tonmengen: Wie oft wird das Griffbild konservativ?

Anteil der Akkordfenster (bei `SAFE_AUDIO_DISTANCE = 0.05`):

| Datei | voller Akkord | X5 (Terz gesperrt) | Septime gesperrt |
|---|---|---|---|
| sting_faith | 49,5 % | 30,5 % | 20,0 % |
| peg | 50,1 % | 36,7 % | 13,2 % |
| misty | 54,7 % | 31,3 % | 14,0 % |
| misty2 | 56,1 % | 33,7 % | 10,2 % |

Sweep über den Schwellwert (X5-Rate):

| Datei | 0.02 | 0.035 | **0.05** | 0.07 |
|---|---|---|---|---|
| sting_faith | 17,9 % | 22,5 % | **30,5 %** | 44,9 % |
| peg | 18,7 % | 25,4 % | **36,7 %** | 49,3 % |
| misty | 14,2 % | 20,1 % | **31,3 %** | 40,2 % |
| misty2 | 19,8 % | 26,1 % | **33,7 %** | 42,3 % |

**Rund jedes dritte Griffbild ist bei 0.05 ein Powerchord** — auch auf den Jazz-Standards, wo Terzen und Septimen die Musik ausmachen. Die Rate hängt fast linear am Schwellwert; `0.035` wäre der nächste Kandidat, falls sich 0.05 am Instrument zu dünn anfühlt. Das ist eine Spielgefühl-, keine Messfrage.

## 7. Fazit

**Messbar besser:** kein Grundton-Schaden (Invariante hält), maj7-Bias sinkt auf allen vier Aufnahmen weiter, tonartfremde Fehlgriffe gehen deutlich zurück, und die dokumentierten Einzelfehler aus den bisherigen Reports (Dmaj7-Streuung, Amaj7-Tonika, Ebmaj7-statt-Eb7) werden real getroffen.
**Bekannter Preis:** Zwischendominanten in Dur verlieren knappe Entscheidungen (E7/F#7 in Peg) — klein, aber real. Der in §4 skizzierte Fix ist inzwischen gebaut, gemessen und **verworfen** (er kippt im Gegenzug die diatonische vi, `REPORT_secondary_dominant_fix.md`); ein echter Fix braucht Progressionskontext, nicht den statischen Prior.
**Offen:** die X5-Dosis (§6) ist am Instrument zu beurteilen, nicht an Zahlen.

**Werkzeuge:** Cache- und Auswerteskripte im Session-Scratchpad (`cache_chromas.py`, `evaluate.py`, `details.py`) — bei Bedarf ins Repo übernehmbar.

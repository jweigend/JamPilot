# Praxis-Report: JamPilot vs. Referenz-Transkriptionen (Stufe 2: komplex)

**Stück:** Steely Dan – *Peg* (Aja, 1977)
**Datei:** `tests/realaudio/Peg.mp3` (3:56, nach WAV 48 kHz mono konvertiert)
**Tool:** `jampilot analyze` (Offline, Template-Matching HPSS+CQT-Chroma, Bass separat gemessen)
**Datum:** 2026-07-15
**Vergleichsstück:** siehe `REPORT_sting_faith.md` (Pop, Stufe 1)

---

## 1. Warum dieser Song

Peg ist der bewusst gewählte Stresstest an genau **zwei** Grenzen von JamPilot:

1. **Vokabular-Decke.** Das Tool kennt nur `Dur, Moll, 7, maj7, m7` (+ Slash-Bass). Peg besteht aus maj9/6-9-Akkorden, „mu"-Voicings (Dur + add9, Terz im Bass), altered Dominanten (7#9) und Slash-Akkorden. **Kein** Akkord des Songs ist im Vokabular exakt benennbar – jeder muss approximiert werden. Kernfrage: *Bleiben die Töne trotzdem passend, oder springt der Grundton weg?*
2. **Harmonische Rhythmik.** Deutlich schnellere Wechsel als bei Sting → das 1,5-s-Fenster (0,75 s Pooling) gerät an seine Auflösungsgrenze.

**Recherche-Befunde vorab:** kein Capo (notiert = klingend); **kein Tonartwechsel** – durchgehend **G-Dur**. Die „schwebende" Tonalität kommt von Tritonus-Substituten und mu-Voicings, nicht von Modulation.

---

## 2. Ground-Truth (Konsens, auf Erkenner-Vokabular reduziert)

| Abschnitt | Voll-Voicings (Quellen) | **Reduziert (Root + Grundform)** | Status |
|---|---|---|---|
| **Intro** (chromat. Abstieg) | Gmaj9 – F#7#9 – Fmaj9 – E7#9 – Ebmaj9 – D7#9 – Cmaj7 – Gadd9/B | **Gmaj7 – F#7 – Fmaj7 – E7 – Ebmaj7 – D7 – Cmaj7 – G/B** | unstrittig (Roots) |
| **Verse** (reharm. Blues) | Cmaj7 ⇄ Gadd9/B, Fmaj7, Bm7, Gmaj7 | **Cmaj7 ⇄ G/B, Fmaj7, Bm7, Gmaj7** | unstrittig |
| **Chorus** | Cmaj7 – Gadd9/B – Am11 – E7sus4 – A/C# – C6/9 – G6 – F#7 – Bm7 – E7#9 – Am7 – C/D | **Cmaj7 – G/B – Am7 – E7 – A/C# – C – G – F#7 – Bm7 – E7 – Am7 – C/D** | unstrittig* |
| **Bridge** | F#m7 – Bm7 – Em7 – Bm7 – Cmaj7 | **F#m7 – Bm7 – Em7 – Bm7 – Cmaj7** | unstrittig |
| **Gitarrensolo** | wie Verse (Cmaj7 ⇄ G/B) + D-Dur-Lick | **Cmaj7 ⇄ G/B, D** | unstrittig |
| **Outro** | Cmaj7 – Gsus2/B Vamp (fade) | **Cmaj7 – G/B** | unstrittig |

\* *Strittig nur im Erweiterungsgrad*, für die Grundform irrelevant: Intro-Dur = maj9/6-9/**maj7** (Root+Dur-Terz unstrittig); Chorus-Slot 4 = E7sus4 vs. E7#9 (kein/anderer Terz → „soft"); mu = add9 vs. sus2 (reduziert beides auf G-Dur). **Signatur-Slash-Akkorde:** G/B (überall), A/C# (Chorus), C/D (Chorus/Turnaround).

**JamPilot hat `Key: G major` erkannt — korrekt und ohne Modulation, exakt wie die Quellen.**

---

## 3. Der Kernbefund: der Intro-Abstieg

Die schwierigste Stelle der Referenz – der chromatisch/ganztönig fallende Lauf mit altered Dominanten – ist zugleich die, an der JamPilot am deutlichsten **liefert**:

| Ground-Truth Root | Tool zeigt (0–15 s) | Root-Treffer |
|---|---|---|
| G (maj7) | `G`, `Gmaj7` | ✅ |
| F# (7#9) | `F#`, F#m7 | ✅ Root (Terz-Qualität schwankt) |
| F (maj9) | `Fmaj7`, `G7/F` | ✅ |
| E (7#9) | `E7` | ✅ **exakt** |
| Eb (maj9) | `D#` (= Eb enharm.) | ✅ **exakt** |
| D (7#9) | `D`, `Dm7` | ✅ Root |
| C (maj7) | `Cmaj7` | ✅ **exakt** |
| G/B | `G/B` | ✅ **exakt inkl. Bass** |

**G – F# – F – E – Eb – D – C – G/B: alle acht Grundtöne in richtiger Reihenfolge getroffen**, `E7`/`Cmaj7`/`G/B` sogar mit exakter Qualität, `Ebmaj9` als `D#` enharmonisch korrekt. Das ist für die harmonisch dichteste Passage des Stücks ein starkes Ergebnis.

---

## 4. Vamp, Slash-Bass, Bridge

- **Cmaj7 ⇄ G/B – die Signaturfigur** (Verse, Chorus, Solo, Outro) ist durchgehend sichtbar: `Cmaj7`↔`G`/`Gmaj7` pendelt über den ganzen Song (z. B. 15–17 s, 41–47 s, 105–109 s, 131–134 s, 205–210 s).
- **G/B – der mu-Bass** wird **wiederholt korrekt gemessen**: `G/B` bzw. `Gmaj7/B` an ~12 Stellen (14.6, 41.1, 67.1, 71.1, 157.6, 161.6, 190.1, 206.6, 210.6, 223.6, 227.6 s). Genau die Terz-im-Bass, die den Song ausmacht.
- **Fmaj7** (Verse T5–8) taucht an den richtigen Stellen auf (27.1, 115.6, 142.1, 148.1 s).
- **Bridge-Töne** F#m7 / Bm7 / Em7 / Cmaj7 sind alle im Vorrat und erscheinen im Interlude-Bereich (86–90 s: `F#m7`, `Bm`, `Em7`; 169–177 s).

**Nicht sauber gefangen:** die Slash-Bässe **A/C#** und **C/D** – dort zeigt das Tool `Amaj7`/`Amaj7/G#` bzw. `G/C` statt der notierten Umkehrung. Der Grund-Dreiklang (A-Dur, C-Dur) stimmt, der spezifische Bass nicht.

---

## 5. Wo es an die Grenze kommt (ehrlich)

Gegenüber Sting ist die Anzeige **deutlich unruhiger**, und ein Teil davon sind echte Fehlgriffe, nicht nur Zusatzinfo:

- **Fremde Akkorde in Verse/Chorus:** wiederkehrend `C#maj7` (Db) und `D#maj7`/`A#maj7`, wo die Ground-Truth in G-Dur bleibt (z. B. 19.1, 23.1, 26.6, 36.6, 51.1, 62.6 s). `C#maj7` ist in G-Dur klar fremd. *Nuance:* `D#maj7` = Ebmaj7 **ist** Song-Vokabular (Intro) – das Tool greift eine reale Klangfarbe an der falschen Stelle.
- **Terz-Fehler bei Dominanten:** `F#7#9` erscheint teils als `F#m7` (falsche Terz) – ein echter Falschton, kein Near-Miss. `E7`/`D7` dagegen richtig.
- **maj7-Übergewicht** wie bei Sting, hier durch die 6/9- und add9-Voicings noch verstärkt: `Dmaj7` taucht häufig auf, wo die Figur nur G/D-Anteile hat.
- **Ursache:** mu-/6-9-Voicings enthalten die None (add9), die der Dreiklang-Matcher als Fremdton gegen ein Nachbar-Template zieht; schnelle Wechsel verschmieren zusätzlich im 1,5-s-Fenster. Der Offline-Pfad **glättet nicht** (kein `ChordSmoother`) – live würde die 3er-Mehrheit einen Teil des Flackerns schlucken.

---

## 6. Fazit gegen die Vorgabe

> *„Wenn unser Tool mehr zeigt ist gut; keine komplett anderen Töne/Akkorde."*

Verglichen mit dem Popsong (Sting: 8/9 Abschnitte Root-exakt) liegt Peg **eine Klasse schwerer**, und das Ergebnis ist gemischt – ehrlich eingeordnet:

- **Skelett getroffen:** Der chromatische Intro-Abstieg (8/8 Roots), die Cmaj7⇄G/B-Signatur und der G/B-Bass sind sauber da. Wer den Song kennt, **erkennt ihn in der Anzeige wieder**.
- **„Mehr zeigen" – ja**, aber mit Rauschen: die 7/maj7-Farben und der mu-Bass sind Zusatzinfo, gemischt mit echten Fehlgriffen (`C#maj7`, `F#m7` statt `F#7`).
- **„Keine komplett anderen Akkorde" – hier teilweise verletzt:** in Verse/Chorus streut das Tool fremde Roots (`C#maj7`, `A#maj7`) ein, die in G-Dur nicht stehen. Das ist mehr als beim Popsong.

**Praxis-Urteil:** Als *note-for-note*-Vorlage taugt die Peg-Anzeige nicht – dafür ist die Harmonik zu dicht und zu schnell für Fenster + Vokabular. Als **harmonische Landkarte / Improvisationshilfe** dagegen sehr wohl: die tragenden Zentren (G, C, die Dominantenkette, der mu-Bass) stehen richtig da, und die „falschen" Akkorde liegen weit überwiegend im tonalen Umfeld (G-Dur-nah), nicht irgendwo. Das deckt sich exakt mit deiner Erfahrung aus dem Sting-Test: **die Töne passen zum Mitspielen, auch wenn nicht immer der wörtliche Grundton getroffen wird** – bei Peg ist dieser Effekt nur stärker, weil der Song selbst mehrdeutiger ist.

**Grenzbefund für die Entwicklung:** Peg markiert sauber, wo Zugewinn läge – ein Vokabular-Ausbau um `6/9`/`add9`/`sus` würde genau die mu-Voicings treffen, die hier das meiste Rauschen erzeugen. (Nicht als To-do, sondern als Verortung der Grenze.)

---

## Quellen (Ground-Truth)
Paul Burke (Colchester Guitar Teacher) · Jon MacLennan · Free Jazz Lessons · hakwright · Ultimate Guitar · Hooktheory · Guitar Player (Jay Graydon zum Solo) · Wikipedia. Übereinstimmend: G-Dur, kein Capo, keine Modulation; komplexe Akkorde reduzieren eindeutig auf die genannten Grundformen.

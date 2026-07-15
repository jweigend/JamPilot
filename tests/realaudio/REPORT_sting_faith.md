# Praxis-Report: JamPilot vs. Referenz-Transkriptionen

**Stück:** Sting – *If I Ever Lose My Faith In You* (Ten Summoner's Tales, 1993)
**Datei:** `tests/realaudio/Sting - If I Ever Lose My Faith In You.mp3` (4:24, nach WAV 48 kHz mono konvertiert)
**Tool:** `jampilot analyze` (Offline-Pfad, Template-Matching auf HPSS+CQT-Chroma, Bass separat im Tiefband gemessen)
**Datum:** 2026-07-15

---

## 1. Methode

1. **Recherche** der harmonischen Ground-Truth aus 5 unabhängigen Chord-Quellen (e-chords, Cifra Club, Chordie/azchords, Songsterr, GuitarTuna) plus 2 Bass-Tabs (BigBassTabs, Songsterr) und einer Modulationsanalyse (arikoinuma).
2. **Konsensbildung**: Was mehrere Quellen gleich notieren = *unstrittig*; wo sie sich widersprechen = *strittig*.
3. **Tool-Lauf**: `jampilot analyze sting_faith.wav` → Zeitleiste mit ~0,5 s Raster.
4. **Vergleich** Abschnitt für Abschnitt: Stimmen die **Grundtöne** (Roots)? Sind Qualitätsabweichungen *Zusatzinfo* (7/maj7/Slash-Bass) oder *Falschtöne* (falsche Terz, komplett anderer Akkord)?

**Wichtiger Recherche-Befund:** Keine Quelle nutzt einen **Capo** – alle notieren in klingender Tonhöhe. Die Referenz ist damit direkt vergleichbar, ohne Transposition.

**Vokabular-Grenze des Tools (fair einzuordnen):** JamPilot kennt nur `Dur, Moll, 7, maj7, m7` (+ gemessener Slash-Bass). Es kann konstruktiv **kein** `sus4`, `add9`, `6`, `dim`, `aug`, `9` ausgeben. Die Song-Voicings sind aber genau davon geprägt (Aadd9, F#7sus4, G6, D7♭5…). Das Tool bildet solche Akkorde zwangsläufig auf den nächstliegenden Dreiklang/Vierklang ab – zu bewerten ist daher: *trifft es den Grundton und die Terz?*

---

## 2. Ground-Truth (Konsens, klingend)

Der Song **moduliert** (kein einheitliches Key): Strophe zentriert auf **A** (A-mixolydisch: A–G–D), Refrain auf **E**, Bridge Richtung **F#**, Schluss-Refrain hinauf nach **B**.

| Abschnitt | Konsens-Akkorde (Voicings) | Grundton-Folge | Status |
|---|---|---|---|
| Intro | F9 – D#7♭5 – Dsus4 – Cmin6 (chromatisch fallend, "no root") | F – D# – D – C | unstrittig |
| Verse | Aadd9 – A – Gadd9 – G – Dadd9 – D (×3) | **A – G – D** | unstrittig |
| Pre-Chorus | Aadd9 – A – F#7sus4 – F#m7 | A – F#m | unstrittig |
| Chorus | Esus4 – E – F#7sus4/F#7 – G – G/A | **E – F# – G – A** | unstrittig |
| Bridge | F#m – C#sus4 – E9 – Bsus4 …; Pendel **G6 ⇄ Em** | F#m…B / G–E | teils strittig* |
| Final Chorus | Bsus4 – B – C#7sus4/C#7 – D – D/E | **B – C# – D – E** | unstrittig |
| Outro/Fade | G6 ⇄ Em | G – Em | unstrittig |

\* *Strittig nur im Detailgrad:* Songsterr/Chordie lesen volle Voicings (F#m–C#sus4–E9–Bsus4–D7♭5–F#m9), GuitarTuna/arikoinuma reduzieren auf Dreiklänge (F#m–G#(m)–A–B). Kein echter Widerspruch, sondern verschiedene Abstraktion. Einzige echte Unschärfe: **G# vs. G#m**.

**Vorkommende Slash-/Umkehrungsakkorde:** G/A (Chorus-Schluss), D/E (Final Chorus), diverse grundtonlose Voicings (`/nr`) in Intro und Bridge.

---

## 3. Abschnittsvergleich Tool ↔ Konsens

JamPilot hat **Key: A major (#)** erkannt – korrekt für das harmonische Zentrum der Strophe (der Song hat kein globales Key; A ist die beste Einzelantwort).

| Zeit (Tool) | Abschnitt | Konsens (Roots) | Tool zeigt (repräsentativ) | Root-Match | Bewertung |
|---|---|---|---|---|---|
| 0–19 s | Intro | F – D# – D – C | Am7, C, A7, C#m, F#m, Gm, G, Em7 … **Dm, D, D#, Emaj7, F7/A, D#** | teilweise | **Schwächster Teil.** Erste ~14 s daneben (sparse/perkussives Intro), ab ~14 s greift D–D#–F (= D–D#/Eb–F der fallenden Linie). |
| 20–49 s | Verse 1 | **A – G – D** | **Amaj7, A7/G, Gmaj7, Dmaj7** (Muster wiederholt) | ✅ exakt | Roots perfekt. `maj7` statt `add9` = +1 Ton (Zusatzinfo, kein Falschton). Slash-Bass A/G korrekt gemessen. |
| 49–54 s | Pre-Chorus | A – F#m | Amaj7, **F#m7**, F#maj7 | ✅ | Roots A, F#m getroffen; F#m7 statt F#7sus4 nah dran. |
| 54–79 s | Chorus 1 | **E – F# – G – A** | **Emaj7, F#7, Gmaj7, Amaj7** (dazwischen B/F#, C#m) | ✅ | Alle vier Roots da. Einschübe B/F#, C#m sind Durchgänge/Nebenlesarten, keine Fremdtöne. |
| 79–103 s | Verse 2 | **A – G – D** | Dmaj7, Amaj7, A7/G, **Gmaj7, Dmaj7** | ✅ exakt | Wie Verse 1. |
| 103–130 s | Chorus 2 | E – F# – G – A | Amaj7, F#m7, **Emaj7, F#7, Gmaj7, Amaj7** | ✅ | Roots getroffen. |
| 130–147 s | Bridge | F#m…B / **G ⇄ Em** | **Em/G, G, Em, E, Em7**, F#maj7, F#m, **G#m7, Amaj7, Bmaj7** | ✅ | G⇄Em-Pendel sauber abgebildet; F#m–G#m–A–B als Dreiklänge = GuitarTuna-Lesart. |
| 155–190 s | Verse 3 | A – G – D | Amaj7, A7/G, Gmaj7, **Dmaj7** | ✅ | Wie Verse. |
| 191–232 s | Final Chorus | **B – C# – D – E** | F#m7, Emaj7, C#m7, **C#7/B, B, C#, C#7, Dmaj7, Emaj7** | ✅ | Modulation nach B **erkannt**: B–C#–D–E alle da (C#7/B = Slash-Bass korrekt). |
| 240–264 s | Outro | **G ⇄ Em** | **Em/G, Em, E, G, Em7/G, Em** | ✅ | Pendel sauber bis zum Fade. |

---

## 4. Befunde

### Was gut läuft (Praxis: **stark**)
- **Grundtöne treffen in allen Hauptabschnitten** (Verse, Pre-Chorus, Chorus, Bridge, Final Chorus, Outro). Die tragenden Progressionen A–G–D, E–F#–G–A und B–C#–D–E stehen jeweils **vollständig und in richtiger Reihenfolge** da.
- **Modulation A → E → B** wird nachgezeichnet, obwohl das Tool nur ein einziges globales Key ausgibt – die Akkorde selbst wandern korrekt mit.
- **Slash-Bass ist ein echtes Plus**: A7/G, C#7/B, D/A, Em/G etc. sind gemessen, nicht geraten, und decken sich mit den Bass-Tabs (Verse-Bass A–G–D, Chorus-Bass E–F#–G–A).
- **G6 ⇄ Em-Pendel** in Bridge und Outro wird als Wechsel G/Em korrekt aufgelöst.

### Systematische Abweichung (kein Falschton, aber Muster)
- **maj7-Übergewicht:** Das Tool labelt sehr viele Dur-Akkorde als `maj7` (Amaj7, Gmaj7, Dmaj7, Emaj7). Ursache: Stings Voicings sind add9/maj7-farbig, und `maj7` ist im Vokabular der nächste Nachbar zu `add9`/Dur mit großer Septime. **Bewertung:** meist +1 Ton Zusatzinfo. Grenzfall: `Aadd9` (A-C#-E-**B**) → Tool `Amaj7` (A-C#-E-**G#**) – hier weicht der Zusatzton ab (G# statt H), der Dreiklang A-C#-E bleibt aber richtig. → **Near-Miss auf der Erweiterung, kein Fehlgriff auf dem Akkord.**

### Echter Schwachpunkt
- **Intro (0–~14 s):** Ground-Truth ist die chromatisch fallende, grundtonlose Linie F–D#–D–C über perkussivem/sparsamem Material. Das Tool liefert hier Am7, C, C#m, F#m, Gm, Em7 – das sind **teils fremde Roots**. Ab ~14 s (D, D#, F) fängt es sich. Das ist der einzige Abschnitt, in dem die Warngrenze „keine komplett anderen Akkorde“ **verletzt** wird – und zwar dort, wo selbst die Referenzquellen „no root“ notieren.
- **Vereinzelte Durchgangs-Fehlgriffe** (z. B. `Gm`, `F7/A` im Intro, `C#m` im Chorus): Einzel-Frames zwischen stabilen Akkorden, im Live-Betrieb würde der `ChordSmoother` (Mehrheit aus 3) die meisten davon schlucken – der Offline-`analyze`-Pfad glättet **nicht**, zeigt also mehr Rohflackern als die Live-Anzeige.

---

## 5. Fazit gegen die Vorgabe

> *„Wenn unser Tool mehr zeigt ist das gut; die Erkennung sollte aber keine komplett anderen Töne oder Akkorde zeigen.“*

- **„Mehr zeigen“ – erfüllt:** 7/maj7-Farben und gemessene Slash-Bässe gehen über die vereinfachten Charts hinaus und stimmen mit den ausführlichen Voicing-Quellen überein.
- **„Keine komplett anderen Akkorde“ – erfüllt in 8 von 9 Abschnitten.** Verse, Pre-Chorus, Chorus (×2), Bridge, Verse 3, Final Chorus und Outro treffen die Grundtöne exakt; Abweichungen sind Zusatztöne oder harmonisch benachbarte Lesarten.
- **Eine Verletzung:** das **Intro** (erste ~14 s), harmonisch ambig/grundtonlos – dort erfindet das Tool Roots. Kandidat für gezielte Nacharbeit (Stille-/Ambiguitätsgate am Songanfang) oder schlicht als bekannte Grenze dokumentieren.

**Praxis-Urteil:** Für ein Live-Mitlese-Werkzeug sehr brauchbar. Ein Gitarrist, der zu diesem Song mitspielt, würde mit der Tool-Anzeige (ab Verse) **richtig greifen** – die Zusatz-7er schaden nicht, die Bässe helfen. Einzig am ganz ruhigen Intro sollte man sich nicht auf die Anzeige verlassen.

---

## Quellen (Ground-Truth)
- e-chords · Cifra Club · Chordie/azchords · Songsterr (Chords + Bass) · GuitarTuna · BigBassTabs · arikoinuma (Modulationsanalyse). Ultimate Guitar & Hooktheory waren 403/JS-gesperrt und flossen nicht ein.

# Praxis-Report: JamPilot vs. Referenz (Stufe 3: Jazz-Ballade, erweiterte Harmonik)

**Stück:** Erroll Garner Trio – *Misty* (Standard, Garner 1954)
**Datei:** `tests/realaudio/Erroll Garner Trio - Misty.mp3` (2:56, → WAV 48 kHz mono)
**Tool:** `jampilot analyze` (Offline, HPSS+CQT-Chroma, Bass separat gemessen)
**Datum:** 2026-07-15
**Vergleichsstücke:** `REPORT_sting_faith.md` (Pop), `REPORT_peg.md` (Reharm-Jazz, uptempo)

---

## 0. Der Tonart-Befund vorweg (wichtig)

Die Recherche stellt eindeutig fest: Misty steht – Komposition **und** Garners Original – in **Eb-Dur**. Diese Aufnahmedatei misst sich aber ebenso eindeutig in **Ab-Dur** (eine Quarte höher):

| Methode | Ergebnis |
|---|---|
| JamPilots eigene Tonartschätzung | **Ab major** |
| Unabhängige Krumhansl-Schmuckler-Analyse (librosa-Chroma) | **Ab-Dur 0.80** vor Eb-Dur 0.68 |
| Harmonisches Skelett der Tool-Ausgabe | ruht/endet auf **Abmaj7**, IV = **Dbmaj7**, Backdoor = **Dbm7–Gb7** → durchgehend Ab |

Zwei unabhängige Detektoren plus die Akkordstruktur stimmen überein: **diese Datei klingt in Ab.** Die Dauer (2:56) entspricht dem Original – also *nicht* schnellergespielt; höchstwahrscheinlich ein **um eine Quarte pitch-geshifteter Upload** (verbreitet zur Copyright-Umgehung).

**Konsequenz für den Test – und ein Befund für sich:** JamPilot hat die *klingende* Tonart **korrekt** gelesen. Für den Vergleich transponiere ich die Real-Book-Changes (Eb) **+5 Halbtöne nach Ab** und prüfe gegen die klingenden Akkorde. Wer stur gegen Eb geprüft hätte, hätte dem Tool 100 % „Fehler" attestiert, obwohl es goldrichtig liegt.

---

## 1. Ground-Truth (Real-Book-Konsens, nach Ab transponiert)

Reduktionsregeln des Vokabulars (`Dur, Moll, 7, maj7, m7` + Bass): 6/9/13 → Grund-Dreiklang/-Vierklang, b9/#9 → 7, m7b5 → m7/Moll; Root bleibt.

| Formteil | Konsens in **Eb** | **klingend in Ab** (Erkenner-Ziel) | Status |
|---|---|---|---|
| A T1 | Ebmaj7 | **Abmaj7** (I) | unstrittig |
| A T2 | Bbm7 – Eb7 | **Ebm7 – Ab7** | unstrittig |
| A T3 | Abmaj7 | **Dbmaj7** (IV) | unstrittig |
| A T4 | Abm7 – Db7 | **Dbm7 – Gb7** (Backdoor) | unstrittig |
| A T5 | Ebmaj7 – Cm7 | **Abmaj7 – Fm7** | unstrittig |
| A T6 | Fm7 – Bb7 | **Bbm7 – Eb7** | unstrittig |
| A T7 | Gm7 – C7 | **Cm7 – F7** | Turnaround (strittig: vs Bbm7–Eb7) |
| Bridge | Bbm7 · Eb7 · Abmaj7 · Am7–D7 · Gm7b5–C7b9 · Fm7–Bb7 | **Ebm7 · Ab7 · Dbmaj7 · Dm7–G7 · Cm7b5–F7b9 · Bbm7–Eb7** | Kern unstrittig |
| Schluss | Eb6 | **Ab6** (= Fm7 je nach Bass) | Eb6/Cm7-Falle → Ab6/Fm7 |

Drei kritische Vokabular-Fälle (aus der Recherche, nach Ab übersetzt):
- **F7b9** (Turnaround) → soll als **F7** erscheinen (b9 entfällt).
- **Cm7b5** (Bridge) → soll als **Cm7/Cm** erscheinen; **enharmonische Warnung:** Cm7b5 = Ebm6 → das Tool kann es als **Ebm** ausgeben.
- **Ab6 = Fm7** (Schluss, identische Töne) → nur über den **Bass** trennbar: Bass Ab → `Ab`, Bass C → `Fm7`.

---

## 2. Vergleich: trifft das Tool das Ab-Skelett?

Garner spielt stark **rubato und verziert** (gerollte Akkorde, Tremoli, Grace Notes), eine taktgenaue Zeit-Zuordnung ist deshalb unscharf. Aussagekräftig ist, ob die **strukturtragenden Akkorde in richtiger Funktion** erscheinen. Ergebnis:

| Funktion (Ab) | Soll | Tool zeigt | Urteil |
|---|---|---|---|
| I | Abmaj7 | `Abmaj7`, `Ab` (1.6, 37.6, 65.6, 70.6, 80.6, 87.6, 116, 124.6, 159.6, **164.6 = Schlusston**) | ✅ tragend, ruht korrekt auf I |
| IV | Dbmaj7 | `Dbmaj7`, `Db` (10.1, 14.6, 47.1, 84–90, 118.6, 127.7) | ✅ |
| Backdoor iv | Dbm7 | `Dbm7`, `Dbm` (15.1, 52.1, 133.6, 19.1, 56.1) | ✅ **Signatur getroffen** |
| Backdoor bVII7 | Gb7 | `Gb7` (17.1, 54.1, 136.1, 137.6) | ✅ **Signatur getroffen** |
| ii | Bbm7 | `Bbm7`, `Bbm` (12.6, 24.1, 61, 89, 147, …) | ✅ |
| ii-von-IV | Ebm7 | `Ebm7`, `Ebm` (6.1, 43.1, 75.6, 105.6, 120.6, …) | ✅ (s. auch Cm7b5-Enharmonik) |
| V7 | Eb7 | `Eb7` (27.6, 37.1, 150.1) | ✅ Root; oft als `Ebmaj7` (s. u.) |
| vi | Fm7 | `Fm7`, `Fm` (12.1, 21.6, 58.6, 72.1, 96.1) | ✅ |
| iii / Turnaround | Cm7 | `Cm7`, `Cm` (19.6, 20.6, 57.6, 99.1, 139.1) | ✅ |
| VI7 (F7b9) | F7 | `F7` (31.1, 121.1, 126.6) | ✅ **b9 korrekt weggelassen** |
| Bridge ii–V | Dm7 – G7 | `Dm7/Bb` (131.1), `Gmaj7` (131.6) | ✅ Root; G7 als Gmaj7 |

**Die drei kritischen Fälle – alle wie von der Recherche vorhergesagt:**
- **F7b9 → F7:** getroffen, das b9 fällt sauber weg. ✅
- **Cm7b5 → Ebm:** Das Tool zeigt an den Bridge-/ii-V-Stellen wiederholt `Ebm`/`Ebm7` – **genau die enharmonische Ebm6-Lesart, die die Recherche als Warnung notierte.** Kein Fehler, sondern die vorhergesagte Zweitbenennung. ✅
- **Ab6 = Fm7:** Das Tool ruht am Schluss auf `Abmaj7` (Bass Ab), löst die Doppeldeutigkeit also über den gemessenen Bass korrekt zur I-Stufe auf. ✅

---

## 3. Wo es rauscht (ehrlich)

Trotz „ruhig" ist die Anzeige **nicht flackerfrei** – Garners romantische Ornamentik hält den Frame-Output beschäftigt, und zwei systematische Muster bleiben:

- **maj7-für-dom7:** Die Dominanten `Eb7`/`Gb7`/`Ab7` erscheinen häufig als `Ebmaj7`/`Dbmaj7`/`Abmaj7`. Root stimmt, aber maj7 (große Septime) statt b7 ist ein **anderer Ton** – der bekannte maj7-Bias, hier durch die dichten Voicings verstärkt.
- **Vereinzelt falsche Terz:** `Fmaj7` statt `Fm7` (101.6, 142.1) – vi als Dur, ein echter Falschton (A statt Ab). Selten.
- **Fremde Einsprengsel:** `Bbmaj7`, `Emaj7`, `A7`, `Gm/Bb` an Streustellen – nicht in Ab-Misty, klar Rauschen. Deutlich seltener als die fremden Roots bei Peg (`C#maj7`, `A#maj7`).
- **Intro (0–5 s):** Garners rubato-Flourish → `Cm`, `Abmaj7/Eb`, `Eb` – ambig, wie schon bei Sting/Peg. (Vom Nutzer als Feature akzeptiert.)
- **Kein Glätten:** Der Offline-`analyze`-Pfad hat keinen `ChordSmoother`; live würde die 3er-Mehrheit einen Teil des Flackerns schlucken.

---

## 4. Fazit gegen die Vorgabe

> *„Wenn unser Tool mehr zeigt ist gut; keine komplett anderen Töne/Akkorde."*

- **Tonart korrekt** – und zwar die *klingende* (Ab), nicht die des Notenblatts (Eb). Das ist die anspruchsvollere und richtige Antwort.
- **Vollständiges harmonisches Skelett getroffen:** I, IV, ii, V, vi, iii **plus beide Signatur-Backdoor-Akkorde** (Dbm7, Gb7) erscheinen in richtiger Funktion. Ein Pianist mit dieser Anzeige spielt die Changes.
- **Alle drei Vokabular-Grenzfälle wie vorhergesagt aufgelöst** – inklusive der enharmonischen Cm7b5→Ebm-Lesart und der bass-getrennten Ab6/Fm7-Falle. Das ist das sauberste Ergebnis der drei Tests bei der *Vokabular*-Frage.
- **„Keine komplett anderen Akkorde" – überwiegend erfüllt.** Das Rauschen ist echt, aber es sind ganz überwiegend *Qualitäts*-Fehler (maj7 statt 7) auf **richtigem Grundton**, nicht fremde Grundtöne. Die wenigen echten Fremdakkorde (Bbmaj7, Emaj7) sind seltener als bei Peg.

**Praxis-Urteil:** Von den drei Tests die **beste Balance** – die langsame Harmonik nimmt das Verschmieren raus, sodass das Vokabular isoliert sichtbar wird, und dort schlägt sich das Tool gut: Grundtöne und Akkordfunktionen sitzen, die Näherungen bleiben tonal im Rahmen. Die verbleibende Schwäche ist eindeutig benannt und **eine einzige Sache:** der maj7-Bias auf Dominanten.

---

## 5. Gesamtbild der drei Tests

| | Sting – *Faith* (Pop) | Steely Dan – *Peg* (Reharm, uptempo) | Garner – *Misty* (Ballade) |
|---|---|---|---|
| Tonart | A ✅ | G ✅ | **Ab ✅ (klingend, ≠ Notenblatt-Eb)** |
| Grundtöne / Skelett | 8/9 Abschnitte exakt | Intro-Kette 8/8 + Vamp, Mittelteil rauscht | I–IV–ii–V–vi–iii + Backdoor komplett |
| Hauptschwäche | Intro ambig (= Feature) | fremde Roots im Verse/Chorus, Tempo verschmiert | maj7-Bias auf Dominanten |
| „andere Akkorde" | nur Intro | teils verletzt (dichte mu-Voicings) | überwiegend nur Qualität, Root korrekt |

**Roter Faden über alle drei:** JamPilot trifft **Grundtöne und tonales Zentrum zuverlässig**; die Fehler liegen fast immer in der *Akkord-Qualität/Erweiterung* (v. a. der maj7-Bias), nur selten im Grundton. Das deckt sich exakt mit deiner Spielerfahrung: *die angezeigten Töne passen zum Mitspielen, auch wenn nicht immer der wörtliche Grundton/die genaue Farbe getroffen wird.* Für ein Live-Mitlese-/Improvisationswerkzeug ist das die richtige Fehler-Verteilung – ein falscher Grundton führt in die Irre, eine zu schlichte oder falsch gefärbte Septime nicht.

**Klarster Entwicklungs-Hebel (verortet, kein To-do):** der systematische maj7-für-7-Bias. Er ist die häufigste Einzelabweichung in *allen drei* Tests. Eine Dominant/maj7-Unterscheidung (b7 vs. maj7 im Chroma gewichten) würde in jedem der Stücke am meisten bringen.

---

## Quellen (Ground-Truth)
jazzguitar.be · jazz-guitar-licks.com · learnjazzstandards.com · jazzstandards.com · Wikipedia · Real Book Vol. 1 · MusicNotes. Übereinstimmend: Eb-Dur, AABA; kritische Reduktionsstellen C7b9, Gm7b5 (→ Ebm-Enharmonik nach Ab), Eb6/Cm7-Bassfalle.

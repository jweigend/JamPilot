# Praxis-Report: Misty (clean, richtige Tonart) — Kontrollvergleich

**Stück:** Beegie Adair – *Misty* (Erroll Garner) — clean Piano-Trio
**Datei:** `tests/realaudio/Jazz Piano _ Beegie Adair - Misty ... .mp3` (3:25, → WAV 48 kHz mono)
**Tool:** `jampilot analyze`
**Datum:** 2026-07-15
**Bezug:** Ground-Truth + Vokabular-Analyse siehe `REPORT_misty.md` (dort die pitch-geshiftete Garner-Aufnahme in Ab)

---

## 0. Warum diese zweite Aufnahme

Die erste Misty-Datei war **eine Quarte nach oben pitch-geshiftet** (klang in Ab statt im Real-Book-Eb). Diese Aufnahme ist **clean und in der richtigen Tonart** — das ergibt einen sauberen **Kontrollversuch**: *dasselbe Stück, dieselben Changes, nur ohne die Störfaktoren.* Damit lässt sich trennen, was am Tool liegt und was an der Quelle lag.

| Prüfung | Ergebnis |
|---|---|
| JamPilots Tonartschätzung | **Eb major** ✅ |
| Unabhängige Krumhansl-Schmuckler-Analyse | **Eb-Dur 0.89** (klar, keine Konkurrenz) |
| → Transposition nötig? | **Nein** — direkter Vergleich gegen die Real-Book-Eb-Changes |

---

## 1. Vergleich gegen die Eb-Changes (kein Transponieren)

Ground-Truth (Real-Book-Konsens, Eb): I `Ebmaj7`, ii `Fm7`, iii `Gm7`, IV `Abmaj7`, V `Bb7`, vi `Cm7`; Backdoor `Abm7–Db7`; Bridge `Am7–D7–Gmaj7` und `Gm7b5–C7`; Schluss `Eb6`.

| Funktion | Soll | Tool zeigt | Urteil |
|---|---|---|---|
| **I** | Ebmaj7 | `Ebmaj7`/`Eb` — durchgehend, ruht darauf (4.6, 32.6, 44.1, 89.1, 190.1, 197.6 …) | ✅ tragend |
| **ii** | Fm7 | `Fm7`/`Fm` (17.6, 46.1, 56.6, 126.6, 159.6, 163.6 …) | ✅ |
| **iii** | Gm7 | `Gm7`/`Gm` (10.6, 39.1, 49.6, 88.6, 115.6, 136.1 …) | ✅ |
| **IV** | Abmaj7 | `Abmaj7`/`Ab` (1.6, 24.6, 39.6, 68.1, 92.6, 124.6, 153.1 …) | ✅ |
| **V** | Bb7 | `Bb7` (31.1, 87.6, 108.6, 185.6) | ✅ **als echte Dominante** |
| **vi** | Cm7 | `Cm7`/`Cm` (20.6, 48.6, 72.6, 105.6, 162.1, 184.1 …) | ✅ |
| **Backdoor iv** | Abm7 | `Abm7`/`Abm` (15.1, 43.6, 100.1, 156.6, 189.1) | ✅ Signatur |
| **Backdoor bVII7** | Db7 | `Dbmaj7`/`Db` (16.6, 45.1, 55.6, 102.1, 119.6) | ✅ Root (als maj7, s. u.) |
| **Bridge** | Am7–D7–Gmaj7 | `Am7`→`Dmaj7` (75–78 s), `Am7`–`A7`–`D7` (131–135 s), `Gmaj7`–`G7` (142, 167 s) | ✅ **Sekundärdominanten sauber getroffen** |
| **Bridge Moll-ii-V** | Gm7b5–C7 | `Gm`/`Bbm`-Umfeld, `C7/Bb` (183.6) | ✅ (Gm7b5 als Gm/Bbm-Enharmonik) |
| **Schluss** | Eb6 (=Cm7) | ruht `Ebmaj7` (197.6), Schluss-Tag `Dbmaj7/C`→`Cm` | ✅ Eb6/Cm7-Falle sichtbar |

**Alle sechs Diatonik-Stufen + beide Backdoor-Akkorde + die komplette Bridge sind da und funktional korrekt.** Das ist das vollständigste Ergebnis aller vier Läufe.

---

## 2. Was der Kontrollversuch beweist

Direkter Vergleich der **zwei Misty-Aufnahmen** (identische Changes):

| | Garner, pitch-geshiftet (Ab) | **Beegie Adair, clean (Eb)** |
|---|---|---|
| Tonart erkannt | Ab ✅ (klingend korrekt) | **Eb ✅ (Notenblatt-korrekt)** |
| Diatonik-Skelett | komplett | **komplett** |
| Backdoor Dbm7/Gb7 bzw. Abm7/Db7 | ✅ | ✅ |
| Bridge-Sekundärdominanten | angedeutet | **klar (Am7–D7–G)** |
| **Dominanten (V)** | fast alle als maj7 | **Bb7 korrekt als 7** an mehreren Stellen |
| Fremde Streuakkorde | mäßig | **weniger** (vereinzelt Emaj7, Gbmaj7, Fmaj7) |

**Erkenntnis:** Die Qualität hängt spürbar an der **Quelle**, nicht nur am Tool. Auf der cleanen Aufnahme:
- werden **Dominanten teils korrekt** erkannt (`Bb7` statt `Bbmaj7`) — der maj7-Bias schlägt schwächer durch als auf der komprimierten/pitch-geshifteten Datei;
- ist das **Rauschen geringer** (weniger fremde Grundtöne).

Der maj7-Bias bleibt aber sichtbar: `Eb7`→`Ebmaj7`, `Db7`→`Dbmaj7`. Er ist damit — wie schon über Sting/Peg/Garner-Misty — die **quellenunabhängige** Hauptschwäche, während Rauschen und Fremdakkorde **quellenabhängig** sind.

---

## 3. Fazit gegen die Vorgabe

> *„Wenn unser Tool mehr zeigt ist gut; keine komplett anderen Töne/Akkorde."*

- **Tonart korrekt** (Eb), **Skelett vollständig**, **Bridge inkl. Sekundärdominanten getroffen** — auf sauberem Material erfüllt JamPilot die Vorgabe hier am deutlichsten.
- **„Keine komplett anderen Akkorde":** erfüllt. Die Abweichungen sind fast ausschließlich `maj7`-statt-`7` auf **richtigem Grundton**; echte Fremdakkorde sind selten und einzeln.
- **Praxis:** Ein Pianist/Gitarrist, der zu dieser Aufnahme mit der Tool-Anzeige mitspielt, bekommt die Changes von Misty **korrekt** — inklusive der kniffligen Bridge. Das ist das beste Live-taugliche Ergebnis der Testreihe.

**Bestätigt den roten Faden:** Grundton & tonales Zentrum sitzen zuverlässig; die einzige systematische, in *jedem* Test wiederkehrende Baustelle ist die **Dominant-vs-maj7-Unterscheidung**. Cleane Quelle in richtiger Tonart = bestes Ergebnis — die Testreihe zeigt sowohl die Stärke (Skelett/Funktion) als auch die eine klar umrissene Schwäche.

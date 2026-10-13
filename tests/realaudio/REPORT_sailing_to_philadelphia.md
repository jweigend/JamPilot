# Praxis-Report: Sailing to Philadelphia – E statt F# im Bass am Formanfang

**Stück:** Mark Knopfler – *Sailing to Philadelphia* (2000), 5:30, F#-Moll
**Datei:** `tests/realaudio/sailing_to_philadelphia.mp3` (aus ../YoutubeDownload kopiert, nach WAV 22,05 kHz mono)
**Stand:** feature/quinte-bassregister 0cb2825 (nach v1.4.1)
**Datum:** 2026-10-13
**Beobachtung (Proberaum, Bass-Modus):** An einigen Formanfängen steht groß **E** mit „over F#m7" darunter. Dort spielt der Bass klar F#.

---

## 1. Was klingt

Form: `F#m7 | A | F#m7 | A E | F#m7 …` (Strophe), B-Teil über `A E F#m D A C#m Bm E C#m F#m D …`.
Das Modell labelt das über das ganze Stück sauber (offline keine falschen
Slashes, einziger Slash D/F# bei 206,6 s).

Am Formanfang steht der Bass auf F#. Davor liegt aber **ein Vorhalt**: Etwa
eine halbe bis eine Sekunde vor dem Downbeat spielt der Bass ein E (nach A
als Durchgang A–E–F#, nach E einfach den Grundton des E-Akkords weiter).
FFT 30–400 Hz, relativ zum stärksten Peak:

| Stelle | vor dem Downbeat | nach dem Downbeat |
|---|---|---|
| 116,4 s (nach A) | 115,9–116,8 s: **E2 82 Hz 1,00**, C#4 0,88, E4 0,80, E3 0,45 – kein F# unten | 117,0–117,9 s: **F#1 46 Hz 1,00**, F#3 0,77, A3 0,51, F#2 0,34 |
| 156,9 s (nach E) | 156,35–156,85 s: **E2 1,00, E1 41 Hz 0,71**, E3 0,61 | 157,0–157,9 s: C#4 1,00, **F#1 0,76, F#2 0,44** |
| 247,2 s (nach A) | 246,65–247,45 s: **E2 1,00**, C#2 0,78, D#2 0,46 | 247,7–248,6 s: **F#2 1,00, F#1 0,95**, F#3 0,47 |
| 50,2 s (nach E, korrekt angezeigt) | 49,3–50,2 s: E2 1,00, E1 0,64 | 50,4–51,3 s: F#1 1,00, F#2 0,74 |
| 20,2 s (nach E, korrekt angezeigt) | 19,1–20,0 s: **B1 62 Hz** 1,00 (Bass auf der Quinte von E) | 20,2–21,1 s: F#2 1,00, F#1 0,88 |

Der Bassist hat also recht: Ab dem Downbeat liegt F# unten, und zwar tief
(F#1, also im Bassregister). Das E davor ist ein echter Basston, aber er
gehört zum Takt davor.

## 2. Was JamPilot daraus macht

**Offline (`jampilot analyze`):** alle 30 F#m-Segmente mit Bass F# bzw.
ohne Slash; kein F#m7/E. Gepoolt über 2 s ab Onset liegt E/F# bei
0,13–0,53, weit unter `SLASH_ROOT_RATIO` 3,0.

**Live-Pfad (`messung_live_pfad.lauf`, Delay 5 s, mit Beat-Tracker):** 146
Events, davon 30 F#m/F#m7: 21 mit Bass F#, 6 ohne Bass, **3 mit Bass E** –
bei 116,41 s, 156,95 s und 247,16 s. Alle drei sind nachgerückte Bässe
(`b_up`): committet wurde ohne Bass, das E kam danach über die monotone
Regel und blieb stehen. Im Bass-Modus steht dann groß E, „over F#m7".
Welche der Formanfänge es trifft, hängt von der Hop-Phase ab (ein Lauf auf
dem Ausschnitt 236–255 s zeigte 247 s korrekt mit F#).

## 3. Ursache: ein Blip in der Zeitleiste schneidet das Bassfenster auf den Vorhalt

Hop für Hop protokolliert (`_merge_model_segments` und `_bass_per_segment`),
Stelle 116,4 s; Commit-Grenze = Analysefront − 3 s:

| Analysefront | Modell sagt | Zeitleiste | Bass für F#m7 @116,44 |
|---|---|---|---|
| 118,00 | A bis 116,82, dann F#m7 | 112,18 A · **116,82 F#m7** (frisch) | – |
| 118,25 … 119,25 | A bis 116,74–116,86, dann F#m7 | 112,18 A · **116,44 F#m7** (verfeinert, 0,35 s früher) | F# (Fenster 2 s), Streak 1 … 6 |
| 119,50 (Commit-Grenze 116,50) | A bis 116,74 | 112,18 A · 116,44 F#m7 · **116,69 A · 116,74 F#m7** | **E** (Fenster nur 116,44–116,69 = 0,25 s) |
| 119,75 … 123,50 | A bis ~116,8 | unverändert | E, Streak 2 … 4 → nachgerückt |

Vier Schritte greifen ineinander:

1. **Die Verfeinerung zieht den Onset auf den Vorhalt.** Das Modell setzt
   F#m7 konsequent auf den Downbeat (116,74–116,87 s). `refine_boundary`
   sucht im Fenster ±0,4 s den Schnitt zwischen A- und F#m7-Tönen, gewichtet
   mit der Anschlagstärke – und findet den Anschlag des E-Vorhalts bei
   ~116,4 s. E ist Akkordton von F#m7 (Septime) und kein Ton von A, also
   sieht der Vorhalt für den Template-Vergleich bereits wie F#m7 aus. Der
   Zeitleisten-Onset liegt damit 0,3–0,35 s vor dem Downbeat.
2. **Das Modell widerspricht an der Commit-Grenze.** Sobald die Grenze
   (116,50) in den Bereich fällt, in dem das Modell weiterhin A sagt, greift
   die Ausnahme für „zu spät erkannte Grenzen" in `_merge_model_segments`
   (zwei Läufe in Folge ein anderer Akkord als der committete): Sie trägt
   **A bei 116,69** ein (Commit-Grenze bzw. voriger Onset + `MIN_EVENT_GAP`)
   und dahinter das F#m7 des Modells bei 116,74. Die Ausnahme ist für
   D–A–D gedacht, wo eine Grenze fehlt; hier ist es eine Onset-Korrektur um
   0,3 s, die als 50-ms-Blip des vorigen Akkords erscheint. Bei 156,9 s
   dasselbe mit E (Zeitleiste 156,67 F#m7 · 156,94 E · 156,99 F#m7).
3. **Die Blip-Sperre fängt die Events, nicht das Bassfenster.** A und das
   wiederholte F#m7 werden korrekt nicht committet (Blip-Sperre, 1.4.1). In
   der Zeitleiste stehen sie aber, und `_bass_per_segment` kappt das Fenster
   des committeten F#m7 am nächsten Zeitleisten-Onset: aus 2 s werden
   **0,25 s = 2–3 Frames, genau der Vorhalt.** Dort ist E die klare Mehrheit,
   E ist Akkordton (Septime) von F#m7, und F# fehlt ganz, also fällt auch die
   Grundton-Ratio nicht. `slash_note` sagt E. Die Quinten-Regel greift nicht,
   E ist nicht die Quinte.
4. **Nachrücken und monotone Regel.** Beim Commit (Analysefront 119,5) war
   der Streak gerade von (F#, 6) auf (E, 1) zurückgesetzt worden – committet
   wird ohne Bass. Vier Hops später ist E stabil, `b_up` setzt es ein, und
   „ein einmal gesetzter Bass wird nie wieder angefasst". Dass das volle
   Segment F# sagt, erfährt niemand mehr.

Die Messung ist in jedem Schritt physikalisch richtig. Falsch ist, dass ein
Segment, dessen Fenster durch eine spätere Revision auf einen Vorhalt
zusammenschrumpft, noch einen Bass nachliefern darf.

## 4. Eingebaut: die Onset-Korrektur ist keine fehlende Grenze (Branch feature/quinte-bassregister)

`_merge_model_segments` prüft vor der Spätgrenzen-Ausnahme, ob das Modell
nur den committeten Wechsel später setzt als die Verfeinerung
(`cli._is_onset_correction`): Der nachgemeldete Akkord ist der von VOR dem
letzten committeten, dahinter führt das Modell sofort wieder den
committeten Akkord, und dessen Modell-Onset liegt höchstens
`ONSET_HYSTERESIS + _REFINED_LOOKBACK` (0,75 s) hinter dem committeten
Onset – so weit, wie eine verfeinerte Grenze vor der rohen liegen darf.
Dann wird nichts eingetragen. Der committete Onset bewegt sich nicht (das
war der Einwand gegen die „Sperre im Merge" vom 11.09., README der
Referenz), die Zeitleiste bleibt ohne Blip, das Bassfenster bleibt 2 s. Ein
echtes D – A – D mit einem A über 0,75 s wird weiter nachgetragen.

**Sailing to Philadelphia, Live-Pfad (146 Events, unverändert):**

| | vorher | nachher |
|---|---|---|
| F#m/F#m7-Events mit Bass F# | 21 | **27** |
| … mit Bass E | 3 | **0** |
| … ohne Bass | 6 | 3 |
| andere falsche Slashes (A/C# ×4, D/F#, E/B) | 6 | **0** |
| Grundton-Bass neu gesetzt (vorher leer) | – | 9 |
| Grundton-Bass verloren (vorher gesetzt, jetzt leer) | – | 5 |

Die fünf verlorenen Grundtöne (14,7 s, 15,3 s, 32,3 s, 40,7 s, 96,4 s) sind
Ein-Schlag-Akkorde, deren Bass vorher **nur durch den Blip** zustande kam:
Das Fenster war auf die ersten 0,25–0,33 s geschnitten, dort stand der
Grundton klar; über das volle Segment (0,6–0,95 s) findet `slash_note`
keine Mehrheit, der Streak flattert zwischen Grundton und None und wird nie
vier Hops stabil. Richtig per Zufall, jetzt ehrlich leer.

**Verworfen: Mindestlänge des Bassfensters.** Als Sicherheitsnetz war
zusätzlich gemessen, Fenster unter 0,5 s bzw. 0,3 s gar nicht zu beurteilen.
Auf diesem Titel bringt das nach der Merge-Korrektur nichts mehr und kostet
weitere Grundtöne von Ein-Schlag-Akkorden (0,3 s: drei, 0,5 s: sieben – bei
~100 bpm ist ein Schlag 0,6 s, die Hürde liegt mitten im Normalfall). Nicht
eingebaut.

**Referenzset, Live-Pfad (`messung_live_pfad.py`, Baseline = Worktree auf
0cb2825):** Eventzahl, Timing (med |dt| ±2 ms Jitter), Beats und
Nur-Bass-Treffer auf allen drei annotierten Titeln unverändert
(Let It Be 144 Events / 65 ms / 0 % von 9; Eight Days 84 / 37 ms; Something
113 / 42–43 ms / 42 % von 12). Der Slash-Vergleich über alle fünf Titel
(mit Tracker, Events mit Bass ≠ Grundton) zeigt, dass dieselbe Kette auch
dort lief – alle entfallenen Slashes sind in den .lab-Dateien NICHT
annotiert, der einzige neue ist annotiert:

| Titel | Bass gesetzt vorher → nachher | Slashes vorher → nachher | entfallen | neu |
|---|---|---|---|---|
| Let It Be | 116 → 124 | 7 → 6 | C/G 236,6 s (.lab: C) | – |
| Eight Days a Week | 24 → 25 | 0 → 0 | – | – |
| Something | 72 → 77 | 13 → 14 | – | **G/D 3,5 s (.lab: G/5)** |
| Crazy Little Thing | 45 → 39 | 10 → 3 | C/E ×2, G/B ×5 (.lab: keine Slashes im Titel) | – |
| It's Too Late | 82 → 95 | 15 → 1 | **D/A ×6, D6/A ×2, Fmaj7/E ×4, Fmaj7/C ×2** (.lab: nur drei F/2) | – |

It's Too Late ist der Beleg, dass das kein Sailing-Sonderfall war: Die
README der Referenz beschreibt die X-Y-X-Blips an genau diesem Titel
(11,6 s, verfeinerte D-Grenze committet, Modell sagt an der Commit-Grenze
noch Am7) und führte „D/A über jedem D6" seit Monaten als bekannten
Live-Fehlgriff, den die Quinten-Regel zu Recht stehen ließ („dort spielt
ein Bass"). Der Bass, der dort spielt, ist der des Am7 im 0,25-s-Stummel
vor dem D6-Downbeat – derselbe Vorhalt-Mechanismus. Ohne Blip ist das
Fenster 2 s, der Bass D, und 13 D6-Events mehr tragen überhaupt einen Bass.

**Proberaum-Test (13.10.):** Sailing to Philadelphia ohne Fehler, Telegraph
Road deutlich besser.

## 5. Nebenbefund

Die Verfeinerung setzt die Formanfänge hier 0,3–0,35 s vor den Downbeat,
auf den Bass-Vorhalt (Schritt 1). Für die Anzeige, die voraus läuft, ist das
unkritisch, aber es ist der Anlass der Kette. Ob die Anschlags-Gewichtung
in `refine_boundary` bei Vorhalten generell zu früh zieht, wäre eine eigene
Messung gegen die Isophonics-Grenzen.

Skripte: Session-Scratchpad (`lowband.py`, `spots.py`, `fft.py`,
`live_sim.py`, `hoplog2.py`, `mergelog.py`, `slashes.py`); alle nutzen nur
`jampilot.btc`, `jampilot.bass`, `jampilot.cli` und
`tests/reference/messung_live_pfad.py`.

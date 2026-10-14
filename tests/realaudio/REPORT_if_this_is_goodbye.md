# Praxis-Report: If This Is Goodbye – A statt D (Quinte der Gitarre als Bass)

**Stück:** Mark Knopfler & Emmylou Harris – *If This Is Goodbye* (All The Roadrunning, 2006), 4:45, ~86 bpm, D-Dur
**Datei:** `tests/realaudio/if_this_is_goodbye.mp3` (aus ../YoutubeDownload kopiert, nach WAV 22,05 kHz mono)
**Stand:** main 8bc1a5d (v1.4.1)
**Datum:** 2026-10-09
**Beobachtung (Proberaum, Bass):** JamPilot zeigt regelmäßig ein A, wo ein D sein müsste. Systematisch.

---

## 1. Was klingt (Chart und Audio)

Chart (Chordu, acordesweb, Ultimate Guitar – alle einig, UG mit Capo 2):
Intro **D A G D**; Strophe **D A D G** ×3, **D A G D**; Solo über dieselbe Folge.
Nur drei Akkorde, kein Slash notiert.

Was unter dem D-Akkord im Tiefband liegt, wechselt aber mit dem Arrangement:

| Stelle | tiefste Töne (FFT, 30–400 Hz, relativ) | Instrument |
|---|---|---|
| Strophe 1, 8,7–14,4 s (D) | A2 110 Hz 1,00 · A3 0,87 · D4 0,88 · E4 0,62 · F#3 0,39 – **kein D2/D3, nichts unter 100 Hz** | nur Gitarre, offener D-Griff mit A-Saite |
| Strophe 1, A- und G-Takte | A2 bzw. G2 als Tiefstes | Gitarre |
| Strophe 2, 61,8 s (D) | **D2 73 Hz 1,00** · A2 0,36 · D4 0,60 | Bass auf D, Gitarre darüber |
| 206,9 s (D) | A2 1,00 · A3 0,43 · D4 0,40 · D2 0,12 | Bass fast weg, Gitarre |
| 240,5 s (D) | **A1 55 Hz 1,00** · A2 0,50 · D4 0,57 · D3 0,20 | Bass spielt wirklich A (Pedal vor dem A-Akkord) |

Tiefband-Chroma (BTC-CQT, Notenbins, je Segment gepoolt), Verhältnis A/D in
den D-Segmenten: Strophe 1 **12–38**, Strophe 2–3 0,3–0,7, 206,9 s 3,5,
240,5 s 7,1.

## 2. Was JamPilot daraus macht

**Offline (`jampilot analyze`):** Labels stimmen mit dem Chart über das ganze
Stück überein (D, A, G; vereinzelt A7/D7 an Übergängen). Abweichung nur im
Bass: **alle acht D-Segmente der ersten Strophe (0–50 s) kommen als D/A**,
dazu 192,5 s (Kurzsegment), 206,9 s, 234,8 s und 240,5 s.

**Live-Pfad (messung_live_pfad.lauf, Delay 5 s, mit Beat-Tracker):** 98
Events. Jedes D der ersten Strophe (neun Events 0,5–45,8 s) wird mit
Bass A committet; ab 53,5 s Bass D; 207,0 s und 240,4 s wieder Bass A.
Anzeige: im Akkord-Modus steht „D/A" im Chip, im Bass-Modus groß **A**
mit „over D" darunter, der Hals markiert A. Das ist das beobachtete „A statt D".

## 3. Ursache

`bass.slash_note` hat drei Hürden (Mehrheit, Akkordton, Grundton-Ratio 3,0).
Die Ratio-Hürde zielt auf „Grundton-Bass plus laute Quinte" – hier fehlt der
Grundton im Tiefband aber ganz: Die Gitarre spielt das D erst bei D4 (294 Hz),
über der Bandgrenze 260 Hz, und ein Bassinstrument gibt es in der ersten
Strophe nicht. Der tiefste klingende Ton **ist** die A-Saite. Die Messung ist
physikalisch richtig; falsch ist die Deutung „der Bassist spielt A", weil
kein Bassist spielt. Dieselbe Klasse wie die bekannten Live-Fehlgriffe
(README der Referenz: „D/A über jedem D" in Eight Days bei Ratio 2,0, „D/A
über jedem D6" in It's Too Late) – nur dass die Ratio hier nicht greifen
kann.

Das D/A bei 240,5 s ist dagegen echt: A1 bei 55 Hz, der Bass hält das A
vor dem A-Akkord. Ein Bassist will das wissen. Das Ziel ist also nicht
„Quinte verbieten", sondern „Gitarrentiefton nicht als Bass ausgeben".

## 4. Gemessene Gegenmaßnahme: Bassregister-Gate (Prototyp, nicht eingebaut)

Idee: Ein Slash wird nur behauptet, wenn der Slash-Ton auch **unter E2
(82 Hz)** klingt – unter der tiefsten Gitarrensaite, wo nur ein Bass
(oder Klavier/Synth) sein kann. Umsetzung im Prototyp: zweite Faltung aus
den Bins C1..D#2 (32,7–77,8 Hz), Anteil `sub[ton] / tiefband[ton]`
muss eine Schwelle erreichen; sonst Grundton.

Anteil des Slash-Tons im Subband: Goodbye Strophe 1 **1–2 %** (0,010–0,019),
Goodbye 240,5 s 57 %; Isophonics-Umkehrungen (27, fünf Referenztitel)
4–69 %, ein Ausreißer bei 1 % (Let It Be 40,6 s).

`messung_bass_gt.py`-Metrik (Segmente ≥ 1 s, 2-s-Pooling wie live):

| Variante | falsche Slashes (385 Grundton-Seg.) | Umkehrung gefunden (27) | Goodbye Strophe 1 D/A | Goodbye 240,5 s D/A |
|---|---|---|---|---|
| **basis** (aktiv) | 1 (0,3 %) | 11 (41 %) | 8 von 8 falsch | bleibt |
| Subband-Anteil ≥ 50 % | 0 | 1 (4 %) | 0 | bleibt |
| ≥ 25 % | 0 | 1 (4 %) | 0 | bleibt |
| ≥ 10 % | 1 | 6 (22 %) | 0 | bleibt |
| ≥ 5 % | 1 | 9 (33 %) | 0 | bleibt |
| ≥ 3 % | 1 | 10 (37 %) | 0 | bleibt |

Lesart: Auf den 60er/70er-Referenzaufnahmen trägt das Subband wenig
(Bass-Fundamentale schwach, oft D/D# vom Schlagzeug obenauf), die echten
Umkehrungen liegen dort bei 4–15 %. Ein Gate bei 25–50 % wäre physikalisch
sauber, kostet aber 10 der 11 gefundenen Umkehrungen. Nur eine sehr tiefe
Schwelle (3 %) trennt Goodbye (≤ 2 %) von den Referenz-Umkehrungen (≥ 4 %,
bis auf eine) – das ist eine Messerschneide, an einem Titel kalibriert, und
bedeutet eigentlich „gar kein Subbass vorhanden", nicht „Bass klingt tief".

Offen: Ob die 17 falschen Live-Slashes der Referenz (It's Too Late D/A,
Fmaj7/E) dasselbe Muster haben (Subband leer), wurde nicht gemessen; die
Offline-Metrik zählt dort nur einen Fehlgriff. Wenn ja, wäre „Subband leer
→ kein Slash" ein Hebel mit zwei Belegen statt einem.

## 5. Eingebaut: die Quinte braucht eine Bassstimme (Branch feature/quinte-bassregister)

Das Gate aus §4 als allgemeine Hürde war zu teuer (Let It Be verliert bei
25 % alle sieben Em/G). Die Regel, die ein Mensch anwendet, ist enger: **Nur
die Quinte** unter dem Grundton ist verdächtig, weil nur sie ein Griff von
selbst unter den Grundton legt; Terz und Septime im Bass sind Absicht. Also
verlangt `bass.slash_note` den Register-Nachweis nur für die Quinte
(`FIFTH_REGISTER_SHARE` 5 %, `btc.fold_bass_register`, von `BassTrack`
parallel mitgeführt); fällt er aus, gilt Grundton-Lage, die Anzeige zeigt den
Grundton.

Offline (`messung_bass_gt.py`-Metrik, 2-s-Pooling), Quinten-Regel mit
Schwelle:

| Variante | Let It Be (7 Umk.) | Something (17 Umk.) | falsche Slashes (385) | Goodbye Str. 1 | Goodbye 240 s |
|---|---|---|---|---|---|
| ohne (main) | 7 | 4 | 1 | 8 falsch | bleibt |
| Quinte nie | 7 | 1 | 1 | 0 | verloren |
| **Quinte nur mit Register ≥ 5 %** | **7** | **4** | **1** | **0** | **bleibt** |
| Quinte nur mit Register ≥ 10 % | 7 | 2 | 1 | 0 | bleibt |

Live-Pfad (messung_live_pfad.lauf, mit Beat-Tracker), Slash-Events mit
Quinte als Bass, ohne → mit Regel:

| Titel | Quinten-Slashes ohne | mit | verloren |
|---|---|---|---|
| Goodbye | 11 (9 in Strophe 1) | 2 (207 s, 240 s) | die 9 falschen der Strophe 1 |
| Let It Be | 7 (alle C/G, annotiert Em/G) | 5 | 40,5 s, 182,0 s |
| Something | 8 (C/G, G/D) | 7 | 127,7 s |
| It's Too Late | 10 (D/A, D6/A, Fmaj7/C) | 10 | keiner: dort spielt ein Bass, die Quinte klingt im Register |

Eventzahl, Timing und Nur-Bass-Treffer sind in allen Titeln unverändert.
Die verlorenen Stellen in Let It Be sind der Preis: Das Modell labelt dort C
statt Em, der gemessene Bass G war richtig; mit der Regel steht C ohne Slash.
Register-Anteil dort 1 % bzw. knapp unter 5 % - McCartneys G liegt auf
diesen Aufnahmen kaum unter E2. Die zehn D/A und Fmaj7/C in It's Too Late
(README der Referenz, "Quinte als Oberwelle, oder der Bassist spielt es
wirklich") bleiben alle stehen: Dort spielt ein Bass, und seine Quinte
klingt unter E2. Die Regel trennt "Gitarre ohne Bass" von "Bass", nicht
"Bass auf der Quinte" von "Oberwelle" - das bleibt dem Ohr.

Skripte: Session-Scratchpad (`tiefband.py`, `spektrum.py`, `live.py`,
`varianten.py`, `goodbye_varianten.py`, `ref_varianten.py`); alle nutzen nur
`jampilot.btc`, `jampilot.bass`, `jampilot.cli` und
`tests/reference/messung_live_pfad.py`.

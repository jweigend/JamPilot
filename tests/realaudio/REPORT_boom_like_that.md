# Praxis-Report: Boom, Like That – landen die Akkorde auf der Eins?

**Stück:** Mark Knopfler – *Boom, Like That* (Remastered 2021), 5:49
**Datei:** `tests/realaudio/boom_like_that.mp3` (aus ../YoutubeDownload, gitignored)
**Stand:** main 224f18b, Branch feature/bass-vorlauf
**Datum:** 2026-11-17
**Beobachtung (Proberaum):** Die Akkorde stimmen immer, aber manchmal kommt
die Anzeige zu spät. Die Wechsel liegen im Stück immer auf der Eins.

---

## 1. Referenz ohne Annotation

Das Beat-Modell zählt 89,6 bpm (Schlag 670 ms, 506 Beats, 127 Einsen).
Johannes zählt den Takt halb so schnell (Doubletime): seine Eins ist jeder
zweite Modellschlag, also die Schläge 1 **und** 3 des Modellrasters. Die
Akkordfolge ist unstrittig – Strophe G, Bb, C, Eb; Refrain G, Eb, F – und
das Modell trifft sie offline (es schreibt Gm, A#, C, D#, F). Referenz
sind deshalb die Grundton-Wechsel der Offline-Labels, auf die nächste
starke Zählzeit gelegt: 216 Wechsel; nur 5 Offline-Grenzen liegen mehr als
400 ms von ihrer Zählzeit entfernt.

Skript: `tests/reference/messung_boom_like_that.py [variante ...] [--detail]`
(Live-Pfad über `messung_live_pfad.lauf`, mit Beat-Tracker, Delay 5 s).

## 2. Stand vor der Änderung

| | |
|---|---|
| auf der Eins (±70 ms) | **94 %** |
| früh | 1 % |
| leicht spät (< halber Schlag) | 1 % |
| ≥ halber Schlag spät | **4 %** (8 Wechsel, alle genau einen Schlag) |
| fehlt | 1 % (2) |
| Median / p90 | -1 ms / +11 ms |

Die Timing-Kette tut, was sie soll: Wer landet, landet exakt auf dem
Schlag. Die 8 Nachzügler sind ein Typ: **Eb nach C**. Frame-Labels dort:

    13.56 C … 14.12 | 14.21 Cm … 15.42 | 15.51 D#       (Eins bei 14.93)

Das Modell labelt den Takt vor dem Eb als Cm – C-Eb-G gegen Eb-G-Bb, zwei
geteilte Töne, der Bass entscheidet – und das Cm reicht bis 1,7 s über die
Eins hinaus. Die Audio-Verfeinerung sucht ±0,4 s um die Modellgrenze und
kommt nicht hin; der Snap nimmt den nächsten Schlag, einen zu spät. Von
27 C→Eb-Übergängen laufen 15 über ein Cm, 8 davon landen spät.

**Der Bass weiß es:** Tiefband-Chroma je Schlag (`bass.dominant`) ab dem
C-Onset: in allen 27 Fällen `C C D# D#` – die Bassnote springt genau auf
der starken Zählzeit nach Eb, auch wo das Label noch Cm sagt.

## 3. Varianten (Live-Simulation)

| Variante | auf der Eins | ≥ ½ Schlag spät | fehlt |
|---|---|---|---|
| Stand (nächster Beat) | 94 % | 4 % | 1 % |
| früherer Beat bevorzugt | 84 % | 2 % | 6 % |
| starker Beat (1/3) bevorzugt | 94 % | 2 % | 1 % |
| zwei Frames Vorlauf statt einem | 88 % | 11 % | 1 % |
| roh statt verfeinert, wenn snapbar | 93 % | 2 % | 1 % |
| **Bass-Vorlauf**, jeder Grundtonwechsel | **95 %** | **1 %** | 1 % |
| **Bass-Vorlauf, nur Paralleltonart** | **95 %** | **1 %** | 1 % |

Die reinen Timing-Stellschrauben helfen nicht: zwei Frames Vorlauf machen
es klar schlechter, der frühere Beat verschluckt Events, der starke Beat
holt zwei Fälle. Der Bass-Vorlauf zieht eine Grundton-Grenze auf den
frühesten Schlag zurück, auf dem das Tiefband schon den neuen Grundton
trägt (höchstens zwei Schläge, und nur wenn auch der eigene Schlag ihn
trägt): 20 Grenzen vorgezogen, 7 der 8 Nachzügler weg.

Regression auf den Isophonics-Titeln (`messung_live_pfad.timing`):

| | Let It Be | Eight Days a Week | Something |
|---|---|---|---|
| Stand: auf dem Schlag | 90 % | 80 % | 93 % |
| Bass-Vorlauf, jeder Grundtonwechsel | **87 %** (25 vorgezogen) | 80 % (0) | 93 % (2) |
| Bass-Vorlauf, nur Paralleltonart | 90 % | 80 % | 93 % |

Die breite Fassung kostet Let It Be drei Punkte: dort sind es echte
Vorhalte des Bassisten (der Bass spielt den neuen Grundton einen Schlag
vor dem Wechsel), kein Fehl-Label. Eingeschränkt auf die Paralleltonart-
Verwechslung (`bass.is_relative_change`: Moll-Label → Grundton + 3, Dur-
Label → Grundton + 9) greift sie auf den drei Titeln nicht ein einziges
Mal und bleibt auf Boom gleich gut.

## 4. Eingebaut (Branch feature/bass-vorlauf)

`cli._bass_anticipation`, nach der Audio-Verfeinerung einer frischen
Grenze (`_refine_fresh_bounds`), mit dem Live-Raster
(`BeatGrid.known_beats`, um höchstens drei Schläge fortgeschrieben – eine
frische Grenze liegt am Horizont, das Raster reicht dorthin erst mit dem
nächsten Beat-Lauf) und `BassTrack.frames_between`.
`BASS_ANTICIPATION_BEATS = 2`. Mit dem echten Code: **95 % auf der Eins,
1 % Nachzügler**, Median/p90 unverändert.

## 5. Was bleibt

Acht Wechsel außerhalb ±70 ms, alle mit Grund außerhalb der Timing-Kette:

- **29,6 s, 72,3 s – Bb→Eb einen Schlag spät.** Label pünktlich, aber der
  Bass hält auf der Eins noch Bb und spielt Eb erst auf 2; die Verfeinerung
  zieht die Grenze auf diesen Bassanschlag. "Roh statt verfeinert" würde
  es heilen, kostet aber anderswo (Tabelle).
- **88,3 s, 298,9 s – einen Schlag früh.** Das Modell wechselt schon auf
  der 4 (Labels D# ab 87,8 s, Gm ab 298,7 s); der Bass hält bis zur Eins
  den alten Ton. Das Spiegelbild des Vorlaufs ("Bass-Nachlauf") wäre
  denkbar, ist aber bei Pedalbässen riskant – nicht gemessen.
- **136,3 s – F einen Schlag spät.** Modell sagt bis 136,8 s A#.
- **174,9 s, 177,6 s, 228,3 s – +250 ms.** Das Cm-Label sitzt selbst auf
  der Eins, das vorgezogene Eb muss um `MIN_EVENT_GAP` nachrücken. Den
  leeren Vorgänger zu schlucken hält nicht: der Merge setzt ihn im
  nächsten Hop wieder ein (gemessen, Variante `relativ2`).
- **134,9 s C, 201,6 s D – fehlen** (kein Event gleichen Grundtons im
  Fenster; 201,6 s ist ein Offline-Label D, das live nie entsteht).

# Code-Review November 2026: Fehlersuche über das ganze Programm

Stand: 2026-11-10, Branch `fix/review-2026-11`. Anlass war keine konkrete
Störung, sondern die Frage „gibt es Fehler, und lässt sich etwas verbessern".
Dieses Dokument hält fest, was gefunden wurde, wie jeder Befund belegt ist,
was davon auf dem Branch behoben ist und was offen bleibt.

## Kurzfazit

Die Erkennungskette (Modell → Merge → Verfeinerung → Ledger) hat der Durchsicht
standgehalten. Die Fehler liegen an den Rändern:

- **Im Abbau der Umleitung.** Drei Wege, auf denen der Rechner stumm
  zurückbleiben konnte – die schlimmste Fehlerklasse dieses Programms.
- **In der Webanzeige.** Zustandsfehler der Seitenuhr und ein falsches
  Griffbild im Gitarrenmodus.
- **Auf dem Windows-Mute-Weg.** Die Analyse rechnete mit der falschen
  Abtastrate, sobald das Mixformat nicht 48 kHz war.
- **Im Selbsttest.** Er lud das Akkordmodell nie.

Acht Befunde sind behoben und mit Tests belegt (Abschnitt 2). Der Rest ist
dokumentiert und offen (Abschnitt 3). Die Testsuite stand vor dem Review bei
686 bestandenen Tests, danach bei 706.

## 1. Vorgehen und Grenzen

- Kern, Engine, Audio-Pfad, Tonart, Bass und Beats wurden vollständig gelesen;
  die Webanzeige sowie Routing, Windows-Audio und Packaging in zwei
  getrennten Durchgängen.
- Jeder Befund wurde am Code nachvollzogen und, wo es ging, nachgestellt:
  mit den Attrappen der Testsuite (`FakeCoreAudio`, `FakeAudioSystem`),
  mit Qt auf der Offscreen-Plattform und für die Seite mit dem kompletten
  Skript in einer Node-vm.
- **Windows-Code wurde nicht ausgeführt.** Alles dort ist gelesen und gegen
  die Attrappen gerechnet; ein Lauf auf einem echten Windows-Rechner steht
  aus. Das betrifft die Befunde 1, 4 und 5.
- **Die Seite wurde nicht in einem echten Browser nachgeprüft.** Die Fixes
  laufen in der Node-vm mit DOM-Attrappe; Darstellung („Stopped"-Text, das
  hohe Griffbild) ist ungesehen.
- Nichts davon ist im Proberaum gespielt.

## 2. Behoben

| Nr. | Befund | Beleg vorher | Test |
|---|---|---|---|
| 1 | Windows: Waise des Mute-Wegs wird nicht geräumt | mit Attrappen nachgestellt | `TestWaiseAufZweiEndpunkten` |
| 2 | Fenster: Signal während `engine.start()` verklemmt | reproduziert, Stack per faulthandler | `TestSignale` |
| 3 | Ohne Fenster: zweites Signal bricht den Abbau ab | 5 von 5 Läufen unsauber | `TestStartOhneFenster` |
| 5 | Analyse rechnet mit `--samplerate` statt der Stream-Rate | C/G wird zu C♯/G♯ | `TestAbtastrateDesStreams` |
| 6 | Seite: Zustand ohne `t` macht die Uhr zu NaN | Node-vm | `TestSeiteAlsGanzes` |
| 7 | Seite: Stop/Start hält die alte Uhr fest; `running: false` ungelesen | Node-vm | `TestSeiteAlsGanzes`, `TestSitzungswechselFuerDieAnzeige` |
| 8 | Gitarre: falsches Griffbild bei dim, sus2, m7b5 | Node-vm | `TestSeiteAlsGanzes` |
| 10 | Selbsttest lädt das Akkordmodell nie | `jampilot.btc` nach dem Lauf nicht importiert | `TestSelbsttestLaedtDasModell` |

### 1 – Windows: die Waise eines abgestürzten Laufs

`routing.backend()` wird aus dem heutigen Zustand des Rechners berechnet. Nach
einem Absturz auf dem Mute-Weg ist der stumme Umweg der Standard-Ausgang. Auf
einem Rechner mit genau zwei Ausgängen (Lautsprecher und HDMI) bleibt dann
kein Kandidat für den Umweg: der eine ist der Standard, der andere das
Telefoniegerät. `backend()` sagt `None`, und daran hingen beide Auswege:

- `jampilot cleanup --force` meldete „nothing to clean up" und kehrte um.
- Ein Neustart fiel in den Direktmodus; das `cleanup()` im Aufbau der
  Umleitung wurde nie erreicht.

Geändert:

- `cmd_cleanup` fragt unter Windows nicht mehr nach `available()`.
  `routing.cleanup()` räumt dort ohnehin nach dem Vermerk.
- Neu `routing.waisen_aufraeumen()`: `cmd_run` nimmt die Waise zurück, bevor
  irgendetwas `backend()` fragt, und verwirft danach die gemerkten Antworten.
  Angefasst wird nur, wozu es einen Vermerk gibt und dessen Besitzer tot ist.
- `current_output()` und die Instanzprüfung in `cmd_run` hängen unter Windows
  nicht mehr an `backend()`.

### 2 – Fenster: Signal während `engine.start()`

Der Signalhandler in `gui.beenden_bei_signal` rief `app.quit()` direkt. Qt 6
schließt dabei synchron das Fenster, `closeEvent` ruft `engine.stop()`. Python
führt den Handler zwischen zwei beliebigen Bytecodes des Hauptthreads aus,
also auch mitten in `engine.start()`, das das Engine-Lock hält. `stop()`
wartete dann auf das Lock des eigenen Threads. Der Prozess hing mit dem
Null-Sink als Standardausgang und ließ sich nur mit `kill -9` beenden.

Geändert: Der Handler reiht das Beenden ein (`QTimer.singleShot(0, app.quit)`).
Es läuft aus der Ereignisschlange, wenn `start()` zurück ist. Nachgestellt mit
einem SIGTERM an sechs Stellen des Aufbaus: jedes Mal sauberer Abbau.

### 3 – Ohne Fenster: das zweite Signal

Der Handler für SIGTERM und SIGHUP in `cmd_run` warf bei jedem Signal
`KeyboardInterrupt`, auch mitten in `finally: engine.stop()`. Wer das Terminal
schließt, bekommt SIGHUP doppelt (Shell und Kernel, im Nachbau mit einem pty
0,3 ms auseinander). Mit auf 15 ms verlangsamtem Fake-pactl blieb der
Null-Sink in 5 von 5 Läufen Standardausgang.

Geändert: Der erste Treffer stellt SIGINT, SIGTERM und SIGHUP auf
„ignorieren", bevor er wirft. SIGINT hängt am selben Handler, weil Pythons
eigener bei jedem Strg+C neu wirft. Derselbe Nachbau danach: 5 von 5 sauber.

Der Preis: Ein hängender Abbau lässt sich nicht mehr mit Strg+C abbrechen. Er
ist durch Zeitlimits begrenzt (Analysethread 3 s, pactl 5 s je Aufruf).

### 5 – Abtastrate auf dem Windows-Mute-Weg

Auf dem Mute-Weg gibt das Mixformat des Umwegs die Rate des Streams vor
(`engine.start` nimmt `route.samplerate`). `_display_loop` rechnete trotzdem
mit `args.samplerate`, also 48000. Nachgemessen mit 44,1-kHz-Audio, als 48 kHz
analysiert: das Modell meldet C♯/G♯ statt C/G, und aus 108 Frames werden 99 –
die Zeitachse der Analyse läuft der des Streams um 9 % davon.

Geändert: Die Schleife nimmt `loop.samplerate`.

Offen bleibt die verwandte Vermutung, dass der Ausgabestream gar nicht
aufgeht, wenn Umweg und Ausgabegerät verschiedene Raten haben (siehe 3.2).

### 6 und 7 – die Uhr der Webseite

Drei Fehler an derselben Stelle (`apply`/`syncClock` in `index.html`):

- **Zustand ohne `t`.** Vor dem ersten Analyse-Takt hat der Server keinen
  Zustand, in den `republish` mischen könnte, und schickt nur das geänderte
  Feld (`{muted: true}`). `syncClock(undefined)` machte `offset` zu NaN, und
  NaN heilt nicht. Die Chips stapelten sich am linken Rand bis zum Reload.
- **Sitzungswechsel.** Nach Ab- und Wiedereinschalten (oder einem Neustart
  bei offener Seite) zählt der Stream wieder ab null, der Epoch steht wieder
  auf 0. Der Minimum-Filter über 40 Messwerte hielt die alte Zeitrechnung
  10–20 s lang fest.
- **`running: false`.** `Engine.stop()` mischt das Feld in den letzten
  Zustand, die Seite las es nie. Der letzte Akkord stand unbegrenzt als
  laufend da.

Geändert:

- `syncClock` und `apply` ignorieren Positionen, die keine Zahl sind.
- Läuft die Position rückwärts, ohne dass ein Epoch es ansagt, verwirft die
  Seite ihre Uhr. Im laufenden Betrieb kommt das nicht vor: Jeder Sprung im
  Mitschnitt zählt den Epoch hoch, eine Pause hält `t` fest.
- Bei `running: false` leert die Seite Laufband und Record-Zustand und zeigt
  „Stopped".
- `Engine.start()` veröffentlicht `{running: true}` als frischen Zustand. Die
  Seite zeigt dann „Starting up", bis der erste Analyse-Takt kommt.
- `timeline_poc.html` überspringt Zustände ohne Position.

Nebenwirkung der Rückwärts-Regel: Sie fängt auch den Fall aus 3.1 (Epoch und
`t` zu verschiedenen Zeitpunkten gelesen) für Rückwärtssprünge.

Neu ist `tests/seite_harness.js`: die Seite als Ganzes in Node, mit
stellbarer Uhr und einzeln zugestellten Zuständen. Die bisherigen Seitentests
schneiden einzelne Funktionsblöcke aus; Zustandsfehler sehen sie nicht.

### 8 – Gitarrenmodus: dim, sus2, m7b5

Diese drei Qualitäten gibt es nur in `SHAPES_A`. `decideVoicing` fragte nur
`SHAPES_E`, der laufende Akkord fiel aus dem Planer-Fenster, und unter seinem
Namen stand das Griffbild des nächsten Akkords (unter „Bdim" das offene C).

Geändert: Der Planer fragt beide Kataloge, das Fenster muss mit dem laufenden
Akkord beginnen, und `planVoicing` antwortet nicht mehr mit der Lage des
Nachfolgers, wenn der laufende Akkord selbst keine hat.

Eine Entscheidung steckt darin: G und G♯ haben in diesen drei Qualitäten nur
die A-Form am 10. und 11. Bund, oberhalb der Barré-Grenze von Bund 9. Sie
wird jetzt gezeigt statt eines leeren Feldes. Wo es eine E-Form gibt, bleibt
die Grenze, wie sie war.

### 10 – Selbsttest

`jampilot selftest` ist der einzige Test, den der Build gegen das fertige
Bundle fährt. Er prüfte den Template-Pfad (`chords.py`, `chroma.py`), der seit
1.1.0 keinen Akkord mehr anzeigt; `jampilot.btc` wurde nicht einmal
importiert. Ein Bundle ohne `btc_large_voca.npz` bestand also.

Geändert: Die acht Grundstellungen laufen zusätzlich durch Log-CQT und Modell.
Verlangt sind Grundton und Geschlecht, nicht die Vierklang-Erweiterung: Den
obertonreinen Sinus-C7 ohne Schlagzeug nennt das Modell C.

### Nachtrag nach der Bewertung des Branches

Drei Kleinigkeiten, die beim zweiten Lesen des Diffs auffielen und im selben
Branch nachgezogen sind: Der Klaviatur-Planer hat dieselbe Sicherung wie der
Gitarren-Planer bekommen (er hätte sonst, wie der vor Befund 8, die Lage des
Nachfolgers liefern können – mit dem vollen Katalog tritt der Fall nicht ein,
aber die Symmetrie fehlte). Der Vertrag der Rückwärts-Regel aus Befund 7
steht jetzt bei `record_epoch` in `delay_stream.py`, damit ihn der nächste
Pfad nicht unwissentlich bricht. Und `seite_harness.js` sagt im Kopf, dass
ein `ReferenceError` aus Node meist die Attrappe meint, nicht die Seite.
Bewusst nicht angefasst: `timeline_poc.html` kennt `running: false` weiter
nicht (Debug-Seite), und die Lagen-Anker werden beim Abschalten gelöscht
(der Mitschnitt, auf den sie zeigen, ist dann weg).

## 3. Offen

Nichts in diesem Abschnitt ist behoben. Die Reihenfolge ist die der
Dringlichkeit.

### 3.1 Aus derselben Fehlerklasse wie Abschnitt 2

- **4a – Windows: Vermerk wird vor dem Zurückstellen gelöscht.**
  `_cleanup_windows` löscht `STATE_FILE`, bevor es etwas versucht, und
  `_stummschaltung_zurueck` schluckt alle Fehler. Scheitert Core Audio
  einmal, weiß kein späteres `cleanup` mehr von der Stummschaltung. Mit den
  Attrappen nachgestellt. Idee: erst nach geprüftem Erfolg löschen.
- **4b – Windows: `--output` kann der stumme Umweg werden.** Die Kandidaten
  schließen nur Standard- und Telefoniegerät aus, nicht das per `--output`
  gewählte. Mit den Attrappen nachgestellt.
- **4c – Windows: toter Loopback-Thread bleibt unbemerkt.** `Loopback._fehler`
  wird nur im Konstruktor gelesen. Wird der Umweg mitten im Lauf ungültig
  (Monitor schläft ein), liefert `read_into` Stille, und der Wachhund sieht
  weiter Frames, weil er die Ausgabe zählt. Am Code gelesen.
- **9a – R, P und Leertaste ignorieren `ev.repeat`.** Gedrückt gehalten
  schaltet R an/aus/an; jedes „aus" verwirft den Mitschnitt.
- **9b – Fortsetzen nach Pause blitzt eine falsche Position.** Der sofortige
  `republish` trägt `paused: false` mit altem Epoch und altem `t`; bis zum
  nächsten Takt springt die Anzeige um die Pausendauer vor.
- **9c – Epoch und `t` werden an verschiedenen Stellen des Takts gelesen**
  (`heard_pos` früh, `record_epoch` beim Veröffentlichen). Für
  Rückwärtssprünge fängt das jetzt die Regel aus Befund 7; für
  Vorwärtssprünge zieht die Uhr etwa eine Sekunde nach. Nicht reproduziert.
- **11 – Der Build-Stempel ignoriert `jampilot/data/`.**
  `packaging/build.sh` hasht nur `jampilot/*.py`, Spec und Lock. Nach einer
  reinen Änderung an `index.html` oder den Gewichten behält `run.sh --bundle`
  das alte Bundle. Betrifft den lokalen Nachbau, nicht die CI. Seit diesem
  Branch ist das akut: Befund 6–8 ändern nur `index.html`.

### 3.2 Kleineres und Ungeprüftes

- **Linux-Rückbau:** Beim Beenden wird der alte Sink bedingungslos
  zurückgesetzt, auch wenn während des Laufs umgestellt wurde. Nach einem
  Absturz nimmt `cleanup` den ersten Hardware-Sink.
- **Windows, Ausgabestream:** Der PortAudio-Stream wird mit der Rate des
  Umwegs geöffnet, ohne `auto_convert`. Vermutlich scheitert das, wenn Umweg
  und Ausgabegerät verschiedene Raten haben. Ungeprüft.
- **Sperrdatei:** Der Besitz ist eine nackte PID. Unter Windows überlebt
  `%TEMP%` einen Neustart; eine fremde PID kann den Start blockieren.
- **Klassisches PulseAudio:** Der eigene Stream wird nur über
  `application.name` gesucht, das nur pipewire-alsa setzt. Ungeprüft.
- **CI:** Der `devices`-Schritt endet mit `|| true`; ein Bundle ohne
  ladbares PortAudio geht durch.
- **`web.py`:** Ein Token mit Nicht-ASCII-Zeichen endet im Traceback statt in
  einem 403 (verifiziert). `ConnectionAbortedError` wird im SSE-Pfad nicht
  gefangen.
- **Seite, Optik:** Chips sacken kurz vor NOW etwa 9 px ab (die
  Countdown-Zeile hat keine reservierte Höhe). Nach Stille poppt derselbe
  Akkord nicht neu auf. Reine Bass- oder Lagen-Events erzeugen zwei gleich
  beschriftete Chips hintereinander – ob gewollt, ist eine Produktfrage.
- **`analyze`:** 24-Bit-WAV endet im Traceback.
- **Tonart:** Der Kommentar in `_detect_modulation` verspricht, dass die
  Paralleltonart (C-Dur/a-Moll) das Amt mitverteidigt; der Code nimmt die
  Varianttonart (C-Dur/c-Moll). In synthetischen Fällen ohne Wirkung: Dort
  kippt das lange Histogramm zuerst.
- **Altlast:** `chords.py` und der größte Teil von `chroma.py` werden nur
  noch vom Selbsttest benutzt.

## 4. Geprüft, ohne Befund

- **Merge → Verfeinerung → Ledger.** 1200 Fuzz-Läufe mit verrauschten
  Grenzen, Geister-Segmenten und zufälliger Verfeinerung: kein Verstoß auf
  Event-Ebene (Reihenfolge, Mindestabstand, Doppelaussage). Ein einziger Lauf
  zeigte zwei Zeitleisten-Einträge am selben Onset; auf Event-Ebene blieb
  das ohne Folge.
- **Tonart aus Randframes.** Der Estimator wird nur mit den jüngsten zwei
  Frames jedes Fensters gefüttert, deren Labels in 15–35 % der Fälle von dem
  abweichen, was dieselbe Stelle drei Sekunden später bekommt. Die
  naheliegende Verbesserung bringt nichts, gemessen auf zehn Tracks:

  | Fütterung | Tonika richtig | Tonika und Geschlecht | Tonika-Wechsel |
  |---|---|---|---|
  | Randframes (heute) | 92,2 % | 78,7 % | 5 |
  | 1 s hinter dem Rand | 90,9 % | 77,6 % | 9 |
  | 2 s hinter dem Rand | 91,0 % | 78,0 % | 7 |

  Crazy Little Thing fällt dabei von 100 auf etwa 75 %. Nicht weiterverfolgen.
- **Sonst unauffällig:** Mitschnitt-Puffer, Verzögerungsstufe, Beat-Raster,
  die COM-Schicht (Vtable-Indizes, Structs, Freigaben), der Capture-Ring,
  Griffbilder und Klaviatur für alle 12 × 14 Akkorde, Nashville-Stufen.

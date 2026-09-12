# Analyse: Woher koennen die Ton-Aussetzer auf dem Proberaum-PC kommen?

Stand: 2026-09-09. Analyse und Messung; was daraus schon umgesetzt ist, steht
bei den Punkten unter "Was das fuer den Code heisst".

## Ausgangsfrage

Auf dem Proberaum-PC (HP Z820, alter Dual-Xeon, moderne Grafikkarte) ruckelt
der Ton ab und zu. Zwei Fragen: Laesst sich noch einfach parallelisieren, und
gibt es offensichtliche Timing-Probleme?

Vorweg zur Grafikkarte: JamPilot benutzt sie nicht. Das Modell rechnet in
NumPy, die CQT in librosa/numba - alles CPU. Die Karte kann hoechstens
URSACHE sein (Ton ueber HDMI/DisplayPort, Treiber mit Latenzspitzen), nie
Abhilfe.

## Kurzfazit

Das Ruckeln kommt nach allem, was sich hier messen laesst, **nicht aus der
Rechenlast**, sondern aus zwei Dingen, die zusammenwirken:

1. **Der Audio-Callback hat unter Linux nur einen Block Reserve.**
   `delay_stream` oeffnet den Stream mit `latency="high"` und verlaesst sich
   darauf, dass das "grosszuegige Puffer" ergibt. Ueber PipeWire/ALSA
   `default` sind es gemessen **43 ms - genau ein Block** (2048 Frames bei
   48 kHz). Jede Pause im Prozess, die laenger ist, ist ein Xrun.

2. **Die Python-Garbage-Collection macht genau solche Pausen.**
   Der geladene Prozess traegt ~195 000 Objekte (librosa, numba, scipy, Qt).
   Eine volle Sammlung (Generation 2) haelt ALLE Threads an, auch den
   Audio-Callback (der laeuft in Python und braucht den GIL). Gemessen:
   36-74 ms je Sammlung, drei Sammlungen in 150 s Betrieb, eine davon traf
   den simulierten Callback mit 73 ms Verspaetung. Auf dem Z820 (aeltere,
   langsamere Kerne) entsprechend laenger.

Alles andere ist unauffaellig: Die GIL-Wartezeit des Callbacks liegt sonst
bei maximal 8 ms, auch mit gesaettigtem Analysethread und auf nur zwei
Kernen. BLAS-/numba-Threadzahl hat keinen messbaren Einfluss. Der Callback
selbst allokiert praktisch nichts.

Parallelisieren lohnt genau an einer Stelle (Grenzverfeinerung in einen
eigenen Thread), und das ist ein Hop-Budget-Thema, kein Aussetzer-Thema.

## Was gemessen wurde

Messskript: [tests/reference/messung_audio_aussetzer.py](../../tests/reference/messung_audio_aussetzer.py).
Alle Zahlen vom Entwicklungsrechner (2x Xeon E5-2690 v3, 48 Threads, Linux,
PipeWire). Die Z820-Zahlen fehlen noch - siehe "Naechste Schritte".

### Puffertiefe (`latenz`)

`sd.Stream(blocksize=2048, samplerate=48000, latency=...)`, Geraet `default`:

| latency          | stream.latency (out) |
|------------------|----------------------|
| `"high"` (heute) | **0.043 s**          |
| `0.15`           | 0.171 s              |
| `0.3`            | 0.256 s              |

Ein numerischer Wert gibt also echte Reserve. Der Preis: Die
Gesamtverzoegerung waechst um denselben Betrag (5.0 s -> ~5.2 s). Die
Anzeige bleibt exakt, weil `audible_position` ueber den DAC-Zeitstempel von
PortAudio rechnet und `output_latency` aus `stream.latency` liest - beides
zieht automatisch mit.

Unter Windows ist der MME-Standardpuffer ohnehin groesser; dort waere eher
der 200-ms-Puffer des WASAPI-Loopbacks (`wincapture._client`) die kritische
Grenze: Bekommt der Mitschnitt-Thread laenger als 200 ms keinen GIL, gehen
Pakete verloren (`ueberlaeufe`).

### Echte Anzeigeschleife mit Taktthread (`schleife`)

`_display_loop` laeuft gegen einen WAV-Fake-Stream in Echtzeit; daneben
tickt ein Thread im Blocktakt und misst, wie spaet er drankommt. Alle
GC-Sammlungen werden protokolliert. 150 s auf `tests/realaudio/peg.wav`:

| Generation | Anzahl | median  | max     |
|------------|--------|---------|---------|
| gen0       | 358    | 0.1 ms  | 0.4 ms  |
| gen1       | 33     | 0.9 ms  | 3.1 ms  |
| **gen2**   | **3**  | 36.1 ms | 74.0 ms |

Callback-Verspaetung: median 0.1 ms, p99 5.2 ms, **max 73.4 ms** - und die
faellt exakt auf die 74-ms-gen2-Sammlung. Alle anderen Spitzen liegen unter
9 ms.

Wiederholung ueber 120 s mit Zeitpunkten: gen2 bei t=2.4 s (12 ms), 3.6 s
(32 ms), 5.5 s (60 ms) - alle waehrend Modell-Laden und erstem Fenster,
danach keine mehr. Der Mechanismus ist damit belegt (eine volle Sammlung ist
laenger als der Puffer), seine Haeufigkeit im Betrieb nicht: Die
Messschleife hat kein Qt-Fenster, keine SSE-Clients und keinen Mitschnitt,
die alle Objekte anlegen. Das muss der Z820-Lauf zeigen.

### Gesaettigter Analysethread (`schleife` mit SATURATE=1)

Der Analysethread schlaeft nie zwischen den Hops (simuliert eine CPU, die das
250-ms-Raster nicht schafft), zusaetzlich mit `taskset -c 0,1` auf zwei
Kerne beschraenkt: Callback-Verspaetung weiter max 8 ms. Der GIL wird von
librosa/NumPy in den langen Rechenteilen freigegeben; die Wartezeit ist durch
das Switch-Intervall (5 ms) plus den laengsten nicht freigebenden C-Aufruf
begrenzt.

### Hop-Anteile und Ueberlappung (`ueberlappung`)

| Teil                 | median   | p90      |
|----------------------|----------|----------|
| features_from_audio  | 21 ms    | 22 ms    |
| model.predict        | 30 ms    | 30 ms    |
| live_segments        | 2.5 ms   | 3 ms     |
| **refine_boundary**  | **117 ms** | **210 ms** |
| Hop gesamt           | 170 ms   | 265 ms   |

Der Hop reisst das 250-ms-Raster schon hier gelegentlich; auf dem Z820
(Sandy/Ivy Bridge ohne AVX2, grob 1.5-2x langsamer) vermutlich dauerhaft.
Das kostet keinen Ton - die Schleife laesst dann Rasterpunkte aus -, aber der
Analysethread schlaeft nie mehr.

Zwei Threads: cqt+btc 50 ms, refine 116 ms, seriell 166 ms, parallel
**126 ms**. Zweimal refine parallel 138 ms statt 232 ms: Rund 60 % der
Verfeinerung laufen GIL-frei. Mehr Threads bringen nichts mehr, die uebrigen
Teile sind klein.

BLAS-Threads: OPENBLAS_NUM_THREADS=1 gegen 48 aendert keine der Zahlen. Die
Matrizen des Modells (108 x 128) liegen unter der Threading-Schwelle von
OpenBLAS.

## Was das fuer den Code heisst

In der Reihenfolge des erwarteten Hebels:

1. **Numerische PortAudio-Latenz statt `"high"`** (`delay_stream.py`,
   Stream-Aufbau, beide Varianten). Etwa 0.2 s. Einzige Nebenwirkung: 0.2 s
   mehr Gesamtverzoegerung. Der Kommentar dort ("grosszuegige Puffer") ist
   auf Linux schlicht falsch und gehoert mit korrigiert.
   **Umgesetzt (2026-09-09):** `OUTPUT_LATENCY_SECONDS = 0.2`.
2. **`gc.freeze()` nach dem Warmup** (nach `vorheizen` bzw. dem ersten
   Modelllauf). Die 195 000 Startobjekte wandern in die permanente
   Generation; spaetere volle Sammlungen sehen nur noch, was seither
   entstand, und werden von ~70 ms auf wenige ms kurz. Alternativ hoehere
   Schwellen (`gc.set_threshold`), aber freeze ist das gezieltere Werkzeug.
   Lohnt nur, wenn der Z820-Lauf volle Sammlungen NACH dem Start zeigt;
   sonst ist Punkt 1 allein die Antwort.
   **Umgesetzt (2026-09-09):** Der Z820-Lauf zeigte sie (77-84 ms bei
   t=3.8 s und 8.0 s). `vorheizen` laedt jetzt auch das Modell und friert
   danach den Heap ein.
3. **refine_boundary in einen Worker-Thread** (`_display_loop`): Die
   Verfeinerung gilt dann einen Hop spaeter, was der Ledger schon heute
   vertraegt (sie klemmt an der Commit-Grenze, s. 1.3.1). Hop-Budget 166 ->
   126 ms; auf dem Z820 entsprechend mehr Luft.
4. **Xruns sichtbar machen.** `loop.xruns` und `capture_dropouts` standen nur
   beim Beenden im Terminal (`cli._display_loop`, ganz unten). Im
   Kontrollfenster sah man sie nie. **Umgesetzt (2026-09-09):**
   `Engine.dropouts` reicht Xruns plus Mitschnitt-Aussetzer durch, das Fenster
   haengt sie ab dem ersten an die Info-Zeile ("Delay 5.0 s · Lead 4.0 s ·
   3 dropouts"). Ohne Aussetzer steht da nichts.

5. **OpenBLAS auf einen Thread** (`jampilot/__init__.py`, vor dem ersten
   numpy-Import). Auf dem Entwicklungsrechner ohne messbaren Effekt, auf dem
   Z820 der groesste Einzelposten - siehe unten. **Umgesetzt (2026-09-09).**

NICHT empfohlen ohne neue Messung: ein eigener Analyseprozess (Analyse ohne
geteilten GIL). Das waere der strukturelle Schritt, wenn GIL-Wartezeiten das
Problem waeren - sie sind es nach diesen Zahlen nicht.

## Befund auf dem Z820 (2026-09-09)

Die Maschine: 2x Xeon E5-2680 v2 (Ivy Bridge, 2x10 Kerne, 40 Threads, kein
AVX2), Ubuntu mit PipeWire 1.0.5, Ausgabe ueber ein Mackie ProFX per USB.
JamPilot lief 15 Minuten aus dem Terminal, mit Fenster und Firefox-Anzeige.
Das Fenster zeigte danach **4 dropouts**, einer davon hoerbar; im Journal
steht zur passenden Zeit `pipewire: spa.audioconvert: out of buffers`.

**Nichts im Audio-Pfad hat Echtzeit-Prioritaet.** PipeWires eigene
Datenschleifen laufen als SCHED_OTHER/0, ebenso alle Audio-Threads im
JamPilot-Prozess (`chrt -p`). Zwei Gruende: rtkit hat seit dem 6.9. mehrfach
"canary thread is apparently starving" gemeldet und danach "not allowing
further RT threads"; und die Portal-Anfrage beim JamPilot-Start scheitert
mit "Could not get pidns: pidns required but no pidfd provided"
(xdg-desktop-portal 1.20). Der Nutzer ist nicht in der Gruppe `pipewire`, die
in limits.conf rtprio 95 haette. Folge: Der ganze Graph haengt am normalen
Scheduler, und jeder CPU-lastige Prozess erzeugt Xruns - waehrend der
`ueberlappung`-Messung mit 40 BLAS-Threads stiegen PipeWires Fehlerzaehler
fuer den JamPilot-Ausgabestream von 4 auf 12, fuer die Soundkarte von 0 auf
5 (`pw-top`, Spalte ERR).

**OpenBLAS drehte sechs Kerne leer.** 40 Threads angelegt, zwoelf davon mit
je 57 % CPU (Spin-Wait nach jeder Matrixmultiplikation), der Prozess bei
609 % CPU, Load 11.6. Und langsamer als mit einem Thread:

| Hop-Anteil (`ueberlappung`, 62-s-Aufnahme) | 1 Thread | 40 Threads |
|--------------------------------------------|----------|------------|
| cqt+btc                                    | 72 ms    | 65 ms      |
| refine                                     | 110 ms   | 143 ms     |
| beides seriell                             | 179 ms   | 210 ms     |
| beides 2 Threads                           | 105 ms   | 169 ms     |

Der Hop passt mit einem Thread ins 250-ms-Raster, mit 40 nur knapp.

**Nebenbefund:** PortAudio haengt beim Start zusaetzlich einen JACK-Client
("PortAudio", `client.api=jack`, `node.always-process`) an PipeWire, der
nichts tut, aber mit `node.latency 256/48000` den ganzen Graph auf ein
256-Sample-Raster zwingt (eingestellt: 1024). Achtmal so viele Wakeups fuer
alle Knoten. Noch nicht behandelt.

**Ausserhalb von JamPilot zu tun:** Neustart stellt rtkits Echtzeit her, bis
zum naechsten "canary"-Vorfall; dauerhaft hilft `usermod -aG pipewire
johannes` (limits.conf gibt der Gruppe rtprio 95). Erledigt am 9.9.; danach
liefen PipeWires Datenschleifen und die im JamPilot-Prozess mit FIFO 83, und
`pw-top` zaehlte in der naechsten Session keinen einzigen Fehler mehr.

### Zweite Runde: zwei Aussetzer beim Start (Bundle, 2026-09-09)

Mit Echtzeit, einem BLAS-Thread und 0.2 s Puffer blieb ein Muster: Das
Bundle (`dist/jampilot`) meldete zwei Aussetzer in den ersten Sekunden,
danach nichts mehr. PipeWire zaehlte dabei auf keinem JamPilot-Knoten einen
Fehler, ein frisch geoeffneter Stream lieferte in 12 s keinen Statusflag -
die Ursache lag im Prozess. Zwei Messungen (`schleife` 40 s auf dem Z820,
und ein Takt-Thread neben den einzelnen Startschritten):

| Startschritt                         | Cache kalt | Cache warm | Callback max spaet |
|--------------------------------------|------------|------------|--------------------|
| vorheizen (features_from_audio)      | 24.4 s     | 2.0 s      | 81 ms / 8 ms       |
| BTCModel()                           | 61 ms      | 51 ms      | 0 ms               |
| erstes Fenster                       | 63 ms      | 54 ms      | 0 ms               |
| **erste refine_boundary**            | **4.4 s**  | **465 ms** | **55 ms / 35 ms**  |
| jede weitere refine_boundary         | 130 ms     | 127 ms     | 0 ms               |

Dazu die vollen GC-Sammlungen: gen2 bei t=2.3 s (12 ms), 3.8 s (77 ms),
8.0 s (84 ms); der Callback kam dabei 61 und 69 ms zu spaet - zwei Ereignisse
ueber einem Block in 40 s, beide in der Startphase, danach keine.

Zwei Dinge kamen zusammen: **Das Bundle entpackt sich je Start in ein neues
Verzeichnis, numbas Cache ist nach Quellpfad verschluesselt und damit jedes
Mal kalt** (`~/.cache/numba` traegt je Start neue Eintraege - einen Satz aus
dem Warmup, einen weiteren eine Minute spaeter aus der ersten Verfeinerung).
Und `vorheizen` uebersetzte nur den Merkmalspfad; die Kerne der
Grenzverfeinerung (HPSS, Chroma-CQT, Onset) kamen beim ersten Akkordwechsel
dran, mit laufendem Stream. Das allein (55 ms) passt in den Puffer; mit einer
vollen Sammlung (80 ms) obendrauf nicht mehr.

**Umgesetzt:** `vorheizen` ruft `refine_boundary` einmal mit synthetischem
Audio, laedt das Modell (`engine.modell`, die Anzeigeschleife nimmt es
entgegen) und friert danach den Heap ein (`gc.freeze`). Der Stream merkt
sich die ersten 16 Aussetzer mit Stream-Sekunde und Grund (`xrun_log`), die
Anzeigeschleife meldet sie ins Startprotokoll, das Fenster zeigt sie als
Tooltip am Zaehler - die naechste Session sagt dann selbst, ob es der Start
war.

**Offen:** numbas Cache fuer das Bundle an einen festen Ort legen
(`NUMBA_CACHE_DIR`), damit nicht jeder Start 25 s uebersetzt - Startzeit,
kein Aussetzer-Thema.

## Naechste Schritte auf dem Z820

Das Betriebssystem des Z820 ist in diesem Repo nicht festgehalten; die
Puffermessung oben gilt fuer Linux. Auf der Maschine:

1. **Zaehler ablesen.** JamPilot starten, eine Session mit Ruckeln
   durchspielen. Im Kontrollfenster steht ab dem ersten Aussetzer
   "· N dropouts" in der Info-Zeile; wer aus dem Terminal startet
   (`./run.sh` bzw. `run.cmd`) und mit Strg+C beendet, bekommt zusaetzlich
   `Stream warnings: N (last: ...)` (PortAudio-Xruns) und ggf.
   `Capture dropouts: U under, O over` (nur Windows-Loopback). Stehen dort
   Zahlen, liegt es im Prozess - Punkte 1 und 2 oben greifen. Steht dort
   nichts, obwohl es ruckelt, liegt das Ruckeln VOR oder HINTER JamPilot
   (PipeWire selbst, Treiber, Quelle).
2. **Puffer messen:** `python tests/reference/messung_audio_aussetzer.py latenz`
3. **GC und Callback-Verspaetung messen:**
   `python tests/reference/messung_audio_aussetzer.py schleife tests/realaudio/peg.wav 150`
   - einmal normal, einmal mit `SATURATE=1`, einmal mit `OPENBLAS_NUM_THREADS=1`.
   Interessant ist die Zeile "Callback-Verspaetung": ">43ms (1 Block)" ist
   die Zahl der Aussetzer, die der heutige Puffer nicht abfaengt.
4. **Hop-Budget messen:**
   `python tests/reference/messung_audio_aussetzer.py ueberlappung tests/realaudio/peg.wav`
5. **Ausserhalb von JamPilot:** Linux `pw-top` (Xruns pro Knoten, Quantum),
   CPU-Governor (`powersave` auf alten Xeons: Kerne takten langsam hoch);
   Windows LatencyMon (DPC-Latenz des Grafiktreibers). Und: Haengt der
   Lautsprecher am HDMI/DP-Ausgang der Grafikkarte?

Erst mit diesen Zahlen lohnt eine Aenderung - Profiling vor Optimierung.

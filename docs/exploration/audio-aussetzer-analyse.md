# Analyse: Woher koennen die Ton-Aussetzer auf dem Proberaum-PC kommen?

Stand: 2026-09-09. Nur Analyse und Messung, kein Code geaendert.

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

## Was das fuer den Code heisst (noch nichts geaendert)

In der Reihenfolge des erwarteten Hebels:

1. **Numerische PortAudio-Latenz statt `"high"`** (`delay_stream.py`,
   Stream-Aufbau, beide Varianten). Etwa 0.2 s. Einzige Nebenwirkung: 0.2 s
   mehr Gesamtverzoegerung. Der Kommentar dort ("grosszuegige Puffer") ist
   auf Linux schlicht falsch und gehoert mit korrigiert.
2. **`gc.freeze()` nach dem Warmup** (nach `vorheizen` bzw. dem ersten
   Modelllauf). Die 195 000 Startobjekte wandern in die permanente
   Generation; spaetere volle Sammlungen sehen nur noch, was seither
   entstand, und werden von ~70 ms auf wenige ms kurz. Alternativ hoehere
   Schwellen (`gc.set_threshold`), aber freeze ist das gezieltere Werkzeug.
   Lohnt nur, wenn der Z820-Lauf volle Sammlungen NACH dem Start zeigt;
   sonst ist Punkt 1 allein die Antwort.
3. **refine_boundary in einen Worker-Thread** (`_display_loop`): Die
   Verfeinerung gilt dann einen Hop spaeter, was der Ledger schon heute
   vertraegt (sie klemmt an der Commit-Grenze, s. 1.3.1). Hop-Budget 166 ->
   126 ms; auf dem Z820 entsprechend mehr Luft.
4. **Xruns sichtbar machen.** `loop.xruns` und `capture_dropouts` stehen nur
   beim Beenden im Terminal (`cli._display_loop`, ganz unten). Im
   Kontrollfenster sieht man sie nie. Ein Zaehler in der Statuszeile oder
   zumindest im Startprotokoll wuerde die naechste Diagnose um einen
   Proberaum-Abend verkuerzen.

NICHT empfohlen ohne neue Messung: ein eigener Analyseprozess (Analyse ohne
geteilten GIL). Das waere der strukturelle Schritt, wenn GIL-Wartezeiten das
Problem waeren - sie sind es nach diesen Zahlen nicht. Ebenso wenig
BLAS-Thread-Begrenzung als "Fix": kostet nichts, bringt aber gemessen auch
nichts.

## Naechste Schritte auf dem Z820

Das Betriebssystem des Z820 ist in diesem Repo nicht festgehalten; die
Puffermessung oben gilt fuer Linux. Auf der Maschine:

1. **Zaehler ablesen.** JamPilot aus dem Terminal starten (`./run.sh` bzw.
   `run.cmd`), eine Session mit Ruckeln durchspielen, mit Strg+C beenden.
   Am Ende stehen `Stream warnings: N (last: ...)` (PortAudio-Xruns) und ggf.
   `Capture dropouts: U under, O over` (nur Windows-Loopback). Stehen dort
   Zahlen, liegt es im Prozess - Punkte 1 und 2 oben greifen. Steht dort
   nichts, liegt das Ruckeln VOR oder HINTER JamPilot (PipeWire selbst,
   Treiber, Quelle).
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

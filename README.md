# chordelay — Realtime Chord Analyzer mit Vorlauf

Ein Werkzeug für Musiker: Systemaudio (YouTube, Spotify, eigene Dateien, …)
wird ein paar Sekunden gepuffert und dann **unverändert verzögert**
wiedergegeben. Analysiert wird das *frische* Signal — dadurch zeigt das Tool
den Akkord an, **bevor** man ihn hört. Man kann mitspielen, ohne hinterherzulaufen.

```
Systemaudio ──► Ringpuffer (N s) ──► Lautsprecher (verzögert, unverändert)
      │
      └──► Chroma-Analyse ──► Akkord-Anzeige (N s Vorlauf)
```

## Funktionsweise

1. **Capture**: Das Systemaudio wird abgegriffen — unter Linux über den
   Monitor eines PipeWire/PulseAudio-Null-Sinks, unter macOS über einen
   Loopback-Treiber (BlackHole).
2. **Delay**: Ein Ringpuffer exakt in Delay-Länge; an der Schreibposition wird
   der alte Wert ausgegeben und der neue geschrieben. Das Signal wird nicht
   verändert, nur verschoben.
3. **Analyse** (Pipeline aus `docs/exploration/first-draft.md`): Ein
   1,5-s-Fenster des frischen Signals durchläuft **harmonische Trennung**
   (HPSS — entfernt Drums/Percussion) und eine **Constant-Q-Chroma**-Analyse
   (librosa, 36 Bins/Oktave — logarithmische Auflösung trifft auch tiefe
   Grundtöne). Ein separates **Bass-Chroma** (32–260 Hz) gibt Akkorden einen
   Bonus, deren Grundton wirklich im Bass klingt (unterscheidet C von Am7).
   Verglichen wird gegen Akkord-Templates (Dur, Moll, 7, maj7, m7 × 12
   Grundtöne); Vierklänge müssen die Triade um eine kalibrierte Marge
   schlagen, weil Obertöne scheinbare Septimen erzeugen. Ein
   Mehrheitsentscheid über die letzten drei Erkennungen unterdrückt Flackern.
   Der Selbsttest misst beide Pipelines auf synthetischem Material mit
   Drums + Melodie: FFT-Fallback 1/8, HPSS+CQT 8/8.
4. **Timing**: Eine Erkennung sagt, *was* klingt — nicht, *seit wann*. Den
   Einsatzzeitpunkt aus der Erkennungslatenz zurückzurechnen scheitert daran,
   dass die je nach Signal schwankt. Der Wechsel wird deshalb im Fenster
   *gesucht*: das CQT-Frame-Chroma (23-ms-Raster, fällt ohnehin an) wird an der
   Stelle geschnitten, die es am besten in „davor = alter Akkord" / „ab hier =
   neuer" teilt. Damit liegt der Onset auf ±30 ms statt auf dem Analysetakt
   (~500 ms). Wie weit die Ausgabe hinterherhinkt, kommt aus PortAudios
   **DAC-Zeitstempeln**, nicht aus der gemeldeten Latenz — die lag im Test um
   60 ms daneben. Analysefenster enden immer auf einem festen Stream-Raster;
   dauert eine Analyse zu lang, fällt ein Rasterpunkt aus, das Raster bleibt.
   Ein Segment unter **250 ms** ist kein Akkord, sondern ein Fehlgriff der
   Erkennung. Weil der Vorlauf ihn Sekunden vor dem Hörbarwerden zeigt, wird er
   *zurückgenommen* statt als Blitz durchgereicht; der nachrückende Akkord erbt
   den früheren Onset (*wann* gewechselt wurde, stand fest — nur *was* gespielt
   wird, korrigiert sich). Eine Kette von Fehlgriffen konvergiert dadurch auf
   einen einzigen Wechsel, ohne den Zeitpunkt zu verschieben.
5. **Anzeige**: `Kommt in 2.9s: G | Jetzt hörbar: C`. Der Browser bekommt die
   Akkorde mit ihrer Onset-Position in Stream-Sekunden plus die gerade hörbare
   Position, gleicht seine Uhr per Minimum-Filter dagegen ab (NTP-Prinzip: die
   Zustellzeit ist immer positiv) und leitet **großen Akkord und Laufband aus
   derselben Uhr** ab. Sie können deshalb nicht auseinanderlaufen: der Akkord
   springt exakt in dem Frame um, in dem sein Chip die JETZT-Linie berührt.

### Audio-Routing unter Linux (automatisch)

Würde man den Monitor des normalen Ausgangs abgreifen und verzögert auf
denselben Ausgang ausgeben, hörte man Original + Verzögerung + Echo-Kaskade.
`chordelay run` richtet deshalb temporär einen **Null-Sink** als
Standard-Ausgang ein: Player spielen unhörbar dorthin, chordelay liest dessen
Monitor und gibt nur das verzögerte Signal auf die echte Hardware aus. Beim
Beenden (auch per `kill`) wird alles zurückgesetzt.

Das Einrichten läuft **transaktional**: jeder Schritt wird registriert, bevor
der nächste läuft; scheitert einer, wird rückwärts aufgeräumt. Sonst bliebe der
stumme Null-Sink als Standard-Ausgang stehen — `with` ruft `__exit__` nämlich
nicht auf, wenn `__enter__` fliegt. Ein `SIGKILL` lässt sich prinzipbedingt
nicht abfangen; dafür gibt es **`chordelay cleanup`**, das verwaiste Sinks
entfernt und den Standard-Ausgang zurückholt. `run` räumt beim Start selbst
auf, bevor es sich den bisherigen Ausgang merkt — sonst würde es die
Stummschaltung eines abgestürzten Vorlaufs als "vorherigen Zustand" sichern
und beim Beenden wiederherstellen.

Verwaist ist ein Sink allerdings nur, wenn sein **Besitzerprozess nicht mehr
lebt**. Wer ihn angelegt hat, steht in `/tmp/chordelay-<uid>.pid`; ohne diese
Prüfung würde eine zweite Instanz den Sink einer noch laufenden ersten
entladen, und beide rissen sich gegenseitig das Routing weg. Ein zweiter Start
bricht deshalb verständlich ab, statt Schaden anzurichten
(`cleanup --force` überstimmt das, falls nötig).

### macOS

[BlackHole (2ch)](https://existential.audio/blackhole/) installieren, dann:

- Systemausgabe auf „BlackHole 2ch“ stellen (übernimmt die Rolle des Null-Sinks),
- `chordelay run --no-route --input "BlackHole 2ch" --output "MacBook Pro Speakers"`.

Gerätenamen zeigt `chordelay devices`.

## Installation & Benutzung

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python -m chordelay selftest          # Erkennung ohne Audio testen
.venv/bin/python -m chordelay devices           # Geräte anzeigen
.venv/bin/python -m chordelay analyze lied.wav  # WAV offline analysieren
.venv/bin/python -m chordelay run --delay 4     # Live mit 4 s Vorlauf
.venv/bin/python -m chordelay cleanup           # Null-Sink nach Absturz entfernen
```

`run`-Optionen: `--delay` (Sekunden), `--output` (Ziel-Sink/Gerät),
`--input` + `--no-route` (Direktmodus ohne automatisches Routing),
`--samplerate` (Standard 48000), `--port` (Web-Anzeige, Standard 8765),
`--no-web`.

## Web-Anzeige

`run` startet automatisch eine Vollbild-Webanzeige (`http://<rechner>:8765/`,
URL steht beim Start im Terminal): schwarzer Hintergrund, der gerade
**hörbare** Akkord groß in der Mitte, die **kommenden** Akkorde laufen unten
als Band auf die JETZT-Linie zu. Rechts oben ein QR-Code — Smartphone im
gleichen WLAN scannt ihn und zeigt dieselbe Anzeige (Architektur aus dem
Explorationsdokument: der Rechner analysiert, alle Geräte sind reine
Fernanzeigen). Klick/Tipp = Vollbild. Technik: eingebetteter HTTP-Server mit
Server-Sent-Events, komplett offlinefähig (kein CDN); `?demo=1` zeigt die
Seite mit Beispielakkorden ohne laufende Analyse.

## Projektstruktur

```
chordelay/
  chroma.py        FFT → Chroma-Vektor (12 Tonklassen), CQT-Frame-Chroma
  chords.py        Akkord-Templates, Matching, Glättung, Onset-Suche
  delay_stream.py  Duplex-Stream mit Delay-Ringpuffer (sounddevice/PortAudio)
  routing.py       Null-Sink-Routing für Linux (pactl), transaktional
  web.py           SSE-Server + Vollbildanzeige mit Zeitleiste
  selftest.py      Synthetische Akkorde als Pipeline-Test
  cli.py           Kommandozeilen-Frontend, Zeitleisten-Logik
tests/             pytest-Suite (97 Tests)
```

## Tests

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

Abgedeckt sind vor allem die Stellen, an denen sich Fehler *leise* einschleichen:

- **Onset-Genauigkeit** (`test_onset_accuracy.py`) — hält fest, dass ein
  Akkordwechsel auf < 100 ms genau und mit < 50 ms Streuung gefunden wird.
  Schlägt an, sobald jemand am Fenster, am Pooling oder an der Onset-Suche dreht.
- **Zeitleiste** (`test_timeline.py`) — kein Segment unter 250 ms; Fehlgriffe
  werden zurückgenommen, echte 0,5-s-Wechsel überleben.
- **Glätter** (`test_chords.py`) — bei Gleichstand `"?"` statt raten (früher
  entschied der `PYTHONHASHSEED`).
- **Ringpuffer & DAC-Uhr** (`test_delay_stream.py`) — Wraparound, Grenzen,
  Rückfall auf die Latenzschätzung bei unbrauchbaren Zeitstempeln.
- **Routing** (`test_routing.py`) — Rollback bei Fehlern in *jedem* Schritt,
  Waisen-Erkennung, Schutz gegen eine zweite Instanz.
- **SSE-Rückstau** (`test_web.py`) — ein langsamer Client bekommt den
  *neuesten* Zustand, nicht die ältesten.

## Roadmap

- Bedienelemente in der Web-Anzeige: Vorlauf-Regler, Ein/Aus, Geräteauswahl
  (bisher nur Anzeige; Steuerung läuft über die CLI).
- Bessere Erkennung: sus/dim/aug-Templates, Umkehrungen (Slash-Akkorde),
  Beat-synchrone Segmentierung; später Essentia (fertige HPCP/Akkord-/
  Tonarterkennung, siehe Explorationsdokument) oder ein gelerntes Modell.
- macOS-Komfort: automatische Geräteerkennung von BlackHole.

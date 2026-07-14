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
4. **Anzeige**: `Kommt in 2.9s: G | Jetzt hörbar: C`. Angezeigt wird der
   **effektive** Vorlauf: `--delay` plus Soundkarten-Ausgabepuffer minus
   Erkennungslatenz (~1,2 s: ein Wechsel muss erst die gepoolte
   Fensterhälfte dominieren und den Glätter passieren). Die Zeitrechnung
   läuft auf Stream-Positionen statt Wanduhr; per Loopback-Aufnahme
   verifiziert stimmt "Jetzt hörbar" auf ±0,15 s.

### Audio-Routing unter Linux (automatisch)

Würde man den Monitor des normalen Ausgangs abgreifen und verzögert auf
denselben Ausgang ausgeben, hörte man Original + Verzögerung + Echo-Kaskade.
`chordelay run` richtet deshalb temporär einen **Null-Sink** als
Standard-Ausgang ein: Player spielen unhörbar dorthin, chordelay liest dessen
Monitor und gibt nur das verzögerte Signal auf die echte Hardware aus. Beim
Beenden (auch per `kill`) wird alles zurückgesetzt.

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
  chroma.py        FFT → Chroma-Vektor (12 Tonklassen)
  chords.py        Akkord-Templates, Matching, Glättung
  delay_stream.py  Duplex-Stream mit Delay-Ringpuffer (sounddevice/PortAudio)
  routing.py       Null-Sink-Routing für Linux (pactl)
  selftest.py      Synthetische Akkorde als Pipeline-Test
  cli.py           Kommandozeilen-Frontend
```

## Roadmap

- Bedienelemente in der Web-Anzeige: Vorlauf-Regler, Ein/Aus, Geräteauswahl
  (bisher nur Anzeige; Steuerung läuft über die CLI).
- Bessere Erkennung: sus/dim/aug-Templates, Umkehrungen (Slash-Akkorde),
  Beat-synchrone Segmentierung; später Essentia (fertige HPCP/Akkord-/
  Tonarterkennung, siehe Explorationsdokument) oder ein gelerntes Modell.
- macOS-Komfort: automatische Geräteerkennung von BlackHole.

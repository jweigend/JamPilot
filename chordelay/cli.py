"""Kommandozeilen-Frontend fuer den ersten Durchstich.

Befehle:
    devices                Audio-Geraete und Systemaudio-Quellen anzeigen
    selftest               Erkennungspipeline ohne Audiohardware testen
    analyze DATEI.wav      Akkorde einer WAV-Datei offline anzeigen
    run                    Live: Systemaudio verzoegert ausgeben + Akkorde anzeigen
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
import wave

import numpy as np

# Analysefenster: die harmonische Trennung (HPSS) braucht Kontext, und die
# CQT-Bassaufloesung profitiert von Laenge. Gepoolt wird nur die juengere
# Haelfte des Fensters, Akkordwechsel kommen also nach ~0.75s an - bei
# mehreren Sekunden Vorlauf unkritisch. 1.5s ist der Kompromiss aus
# Erkennungsrate (Selbsttest 16/16) und Rechenzeit (~230ms pro Analyse).
ANALYSIS_WINDOW = 1.5
ANALYSIS_HOP = 0.25


def cmd_devices(_args):
    import sounddevice as sd

    print("PortAudio-Geraete (--input/--output im Direktmodus):\n")
    print(sd.query_devices())
    if shutil.which("pactl"):
        out = subprocess.run(
            ["pactl", "list", "short", "sinks"], capture_output=True, text=True
        ).stdout
        print("\nPulseAudio/PipeWire-Ausgaenge (--output im Routing-Modus):")
        for line in out.strip().splitlines():
            print("  " + line.split("\t")[1])


def cmd_selftest(_args):
    from . import selftest

    sys.exit(0 if selftest.run() else 1)


def _load_wav_mono(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as wav:
        samplerate = wav.getframerate()
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        raw = wav.readframes(wav.getnframes())
    if width == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Nicht unterstuetzte Sample-Breite: {width * 8} Bit")
    return data.reshape(-1, channels).mean(axis=1), samplerate


def cmd_analyze(args):
    from .chroma import analyze_window, rms
    from .chords import SILENCE_RMS, match_chord

    samples, samplerate = _load_wav_mono(args.file)
    window = int(ANALYSIS_WINDOW * samplerate)
    hop = int(0.5 * samplerate)

    print(f"{args.file}: {len(samples) / samplerate:.1f}s @ {samplerate} Hz\n")
    last = None
    for start in range(0, len(samples) - window, hop):
        chunk = samples[start : start + window]
        if rms(chunk) < SILENCE_RMS:
            name = "-"
        else:
            chroma, bass = analyze_window(chunk, samplerate)
            name = match_chord(chroma, bass).name
        # Gepoolt wird die juengere Fensterhaelfte -> Zeitstempel mittig.
        if name != last:
            print(f"  {(start + 0.75 * window) / samplerate:6.1f}s  {name}")
            last = name


def cmd_run(args):
    import signal

    from . import routing
    from .delay_stream import DelayedLoopback

    # Auch bei SIGTERM (kill) Routing und Stream sauber zurueckbauen.
    def _raise_interrupt(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _raise_interrupt)

    web_display = None
    if not args.no_web:
        from . import web

        try:
            web_display = web.start(args.port)
            print(f"Anzeige: {web_display.url}  "
                  f"(QR-Code auf der Seite; Smartphone ins gleiche WLAN)")
        except OSError as exc:
            print(f"Web-Anzeige nicht verfuegbar ({exc}) - weiter ohne.")

    from .chroma import warmup

    print("Initialisiere Analyse...", end="", flush=True)
    warmup(args.samplerate, ANALYSIS_WINDOW)
    print(" ok")

    broadcaster = web_display.broadcaster if web_display else None
    try:
        use_routing = routing.available() and not args.no_route and args.input is None
        if use_routing:
            # Linux: Null-Sink wird Standard-Ausgang, wir capturen seinen
            # Monitor und geben verzoegert auf die bisherige Hardware aus.
            with routing.LinuxRouting() as route:
                loop = DelayedLoopback("default", "default", args.delay,
                                       samplerate=args.samplerate)
                loop.start()
                try:
                    route.move_own_playback_to(args.output)
                    print(f"Systemaudio wird abgegriffen (Null-Sink "
                          f"'{routing.SINK_NAME}'), Ausgabe auf: "
                          f"{args.output or route.previous_sink}")
                    _display_loop(loop, args, broadcaster)
                finally:
                    loop.stop()
        else:
            if args.input is None:
                print("Direktmodus: Standard-Eingang wird verwendet.")
                print("(macOS: BlackHole installieren und mit --input waehlen.)")
            loop = DelayedLoopback(args.input or "default", args.output,
                                   args.delay, samplerate=args.samplerate)
            loop.start()
            try:
                _display_loop(loop, args, broadcaster)
            finally:
                loop.stop()
    finally:
        if web_display:
            web_display.stop()


def _display_loop(loop, args, broadcaster=None):
    from .chroma import analyze_window, rms
    from .chords import SILENCE_RMS, ChordSmoother, match_chord

    # Ein erkannter Akkordwechsel hinkt dem Signal hinterher: er muss erst
    # die gepoolte juengere Fensterhaelfte dominieren (~0.35 * Fenster,
    # empirisch via Selbsttest-Signal gemessen) und den Mehrheits-Glaetter
    # passieren (window // 2 Analysetakte). Ohne Korrektur stimmt weder der
    # angezeigte Vorlauf noch der "Jetzt hoerbar"-Zeitpunkt.
    smoother = ChordSmoother(window=3)
    # 0.4 * Fenster: per Loopback-Messung kalibriert (rohe Erkennung folgt
    # einem Wechsel nach ~0.6s, geglaettet ~1.15s bei Tick ~0.5s).
    pooling_lag = 0.4 * ANALYSIS_WINDOW
    smoother_ticks = smoother.window // 2
    tick = ANALYSIS_HOP + 0.25  # Startschaetzung, unten laufend gemessen
    audible_delay = args.delay + loop.output_latency

    lead = audible_delay - (pooling_lag + smoother_ticks * tick)
    print(f"Laeuft: Ausgabe um {args.delay:.1f}s verzoegert, "
          f"effektiver Vorlauf ~{lead:.1f}s. Strg+C beendet.")
    if lead < 1.0:
        print("Hinweis: --delay ist knapp; fuer nutzbaren Vorlauf >= 3s waehlen.")
    print()

    debug_path = os.environ.get("CHORDELAY_DEBUG")
    debug = open(debug_path, "w") if debug_path else None
    if debug:
        debug.write(f"# latency in={loop._stream.latency[0]:.3f} "
                    f"out={loop._stream.latency[1]:.3f}\n")

    # Zeitbasis ist die Stream-Position (captured_seconds), nicht die
    # Wanduhr: sie bezeichnet exakt das Fensterende im Signal, unabhaengig
    # davon, wie lange Analyse und Ausgabe dieses Ticks dauern.
    history: list[tuple[float, str]] = []  # (Stream-Position, Akkord)
    last_tick_time = None
    try:
        while True:
            time.sleep(ANALYSIS_HOP)
            if loop.captured_seconds < ANALYSIS_WINDOW:
                continue  # Analysepuffer fuellt sich noch
            audio = loop.latest_audio(ANALYSIS_WINDOW)
            window_end = loop.captured_seconds
            now = time.monotonic()
            if last_tick_time is not None:
                tick = 0.7 * tick + 0.3 * (now - last_tick_time)
            last_tick_time = now
            detection_lag = pooling_lag + smoother_ticks * tick

            # Gepoolt wird die juengere Fensterhaelfte - Stille-Gate ebenso,
            # sonst liefern ausklingende Toene am Songende Phantomakkorde.
            raw = "-"
            if rms(audio[len(audio) // 2 :]) < SILENCE_RMS:
                smoother.reset()
                upcoming = "-"
            else:
                chroma, bass = analyze_window(audio, args.samplerate)
                result = match_chord(chroma, bass)
                raw = result.name
                upcoming = smoother.update(result)
                if upcoming == "N":
                    upcoming = "?"
            # Der Erkennung die Stream-Position zuordnen, die sie im Signal
            # beschreibt - nicht den Zeitpunkt, zu dem sie fertig wurde.
            history.append((window_end - detection_lag, upcoming))

            # Hoerbar ist gerade die Stream-Position, die den Ringpuffer und
            # den Ausgabepuffer bereits durchlaufen hat.
            audible = " "
            audible_pos = loop.captured_seconds - audible_delay
            while len(history) > 1 and history[1][0] <= audible_pos:
                history.pop(0)
            if history[0][0] <= audible_pos:
                audible = history[0][1]

            if debug:
                debug.write(f"{time.time():.3f}\t{window_end:.3f}\t{raw}\t"
                            f"{upcoming}\t{audible}\n")
                debug.flush()

            lead = audible_delay - detection_lag
            if broadcaster:
                # Kommende Akkordwechsel: Beginn jeder neuen Akkordregion in
                # der noch nicht hoerbaren History, mit Restzeit in Sekunden.
                future = []
                prev = history[0][1]
                for pos, name in history[1:]:
                    if name != prev and name not in ("?", "-"):
                        future.append({"chord": name,
                                       "in": round(pos - audible_pos, 2)})
                    prev = name
                broadcaster.publish({
                    "audible": audible.strip() or "-",
                    "upcoming": future,
                    "lead": round(lead, 1),
                })
            sys.stdout.write(
                f"\r  Kommt in {lead:3.1f}s: {upcoming:<6s} | Jetzt hoerbar: {audible:<6s}"
            )
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("\nBeendet.")
    if loop.status_messages:
        print(f"Stream-Warnungen: {len(loop.status_messages)} "
              f"(zuletzt: {loop.status_messages[-1]})")


def main():
    parser = argparse.ArgumentParser(
        prog="chordelay",
        description="Verzoegertes Systemaudio-Loopback mit Akkordanzeige (Vorlauf).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="Audio-Geraete anzeigen").set_defaults(func=cmd_devices)
    sub.add_parser("selftest", help="Erkennung ohne Audiohardware testen").set_defaults(
        func=cmd_selftest
    )

    p_analyze = sub.add_parser("analyze", help="WAV-Datei offline analysieren")
    p_analyze.add_argument("file")
    p_analyze.set_defaults(func=cmd_analyze)

    p_run = sub.add_parser("run", help="Live-Loopback mit Akkordanzeige")
    p_run.add_argument("--delay", type=float, default=4.0, help="Verzoegerung in Sekunden")
    p_run.add_argument("--input", default=None,
                       help="Eingabegeraet (Index/Name); schaltet in den Direktmodus")
    p_run.add_argument("--output", default=None,
                       help="Ausgabe: Sink-Name (Routing-Modus) bzw. Geraet (Direktmodus)")
    p_run.add_argument("--no-route", action="store_true",
                       help="Kein automatisches Null-Sink-Routing (Linux)")
    p_run.add_argument("--no-web", action="store_true",
                       help="Ohne Web-Anzeige starten")
    p_run.add_argument("--port", type=int, default=8765,
                       help="Port der Web-Anzeige (Standard 8765)")
    p_run.add_argument("--samplerate", type=int, default=48000)
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    # Geraete duerfen Index oder Name sein.
    for attr in ("input", "output"):
        value = getattr(args, attr, None)
        if isinstance(value, str) and value.isdigit():
            setattr(args, attr, int(value))
    args.func(args)


if __name__ == "__main__":
    main()

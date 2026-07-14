"""Kommandozeilen-Frontend fuer den ersten Durchstich.

Befehle:
    devices                Audio-Geraete und Systemaudio-Quellen anzeigen
    selftest               Erkennungspipeline ohne Audiohardware testen
    cleanup                Verwaiste Null-Sinks nach einem Absturz entfernen
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

# Kuerzer als das spielt niemand einen Akkord. Ein Segment darunter ist kein
# Wechsel, sondern ein Fehlgriff der Erkennung - und wird zurueckgenommen.
MIN_CHORD_SECONDS = 0.25

# Wie weit die Onset-Suche zurueckreichen darf. Muss deutlich ueber der
# Erkennungslatenz liegen (median ~0.8s, bei mehrdeutigen Wechseln aber auch
# ueber 1.5s): reicht die Suche nicht bis zum Einsatz zurueck, wird er auf den
# Suchanfang geklemmt - und das ist immer ZU SPAET, nie zu frueh.
MAX_ONSET_SEARCH = 4.0


def _bounded(kind, low, high, unit=""):
    """argparse-Typ mit fachlichen Grenzen - meldet Unsinn sofort, nicht erst
    als PortAudio-Traceback nach dem 3-Sekunden-Warmup."""
    def parse(text):
        try:
            value = kind(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"'{text}' ist keine Zahl")
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(
                f"{value}{unit} liegt ausserhalb von {low}{unit}..{high}{unit}")
        return value
    return parse


def _check_devices(input_device, output_device):
    """Geraete pruefen, BEVOR der teure Warmup laeuft."""
    import sounddevice as sd

    for device, kind in ((input_device, "input"), (output_device, "output")):
        if device is None:
            continue
        try:
            sd.query_devices(device, kind)
        except (ValueError, sd.PortAudioError) as exc:
            raise SystemExit(
                f"Geraet {device!r} nicht nutzbar ({kind}): {exc}\n"
                f"'chordify devices' zeigt die verfuegbaren Geraete."
            )


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


def cmd_cleanup(args):
    from . import routing

    if not routing.available():
        print("pactl nicht gefunden - hier gibt es nichts aufzuraeumen.")
        return
    # Ein SIGKILL laesst sich nicht abfangen; danach bleibt der Null-Sink als
    # Standard-Ausgang stehen und der Rechner ist stumm. Das raeumt das weg -
    # aber nur, wenn der Besitzer wirklich tot ist.
    try:
        removed = routing.cleanup(force=args.force)
    except routing.InstanceRunning as exc:
        raise SystemExit(f"{exc}\n'chordify cleanup --force' raeumt trotzdem auf.")
    print(f"{removed} verwaiste chordify-Sink(s) entfernt." if removed
          else "Keine verwaisten chordify-Sinks gefunden.")
    print(f"Standard-Ausgang: {routing._pactl('get-default-sink')}")


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
    if len(samples) < window:
        print(f"  Datei ist kuerzer als das Analysefenster ({ANALYSIS_WINDOW}s).")
        return

    last = None
    # +1, sonst faellt das letzte vollstaendige Fenster raus - und eine Datei
    # von genau Fensterlaenge wuerde ueberhaupt nicht analysiert.
    for start in range(0, len(samples) - window + 1, hop):
        chunk = samples[start : start + window]
        if rms(chunk) < SILENCE_RMS:
            name = "-"
        else:
            analysis = analyze_window(chunk, samplerate)
            name = match_chord(analysis.chroma, analysis.bass).name
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

    # Erst pruefen, dann teuer werden: Geraete- und Instanzfehler sollen sofort
    # kommen, nicht als Traceback nach drei Sekunden numba-Warmup.
    _check_devices(args.input, args.output)
    if routing.available():
        pid = routing.owner_pid()
        if pid is not None and pid != os.getpid():
            raise SystemExit(str(routing.InstanceRunning(pid)))

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
    print(" ok", flush=True)   # ohne flush landet das "ok" hinter einem Traceback

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
    from .chroma import FrameHistory, analyze_window, rms
    from .chords import SILENCE_RMS, ChordSmoother, match_chord

    sr = args.samplerate
    window_frames = int(round(ANALYSIS_WINDOW * sr))
    hop_frames = int(round(ANALYSIS_HOP * sr))
    smoother = ChordSmoother(window=3)
    # Frame-Chroma laenger aufheben als ein Fenster - siehe _locate_onset.
    history = FrameHistory(MAX_ONSET_SEARCH + ANALYSIS_WINDOW + 1.0)

    # Die Zeitleiste: (Onset-Position im Stream, Akkord). Die Onsets werden im
    # Frame-Chroma gemessen, nicht aus dem Erkennungszeitpunkt zurueckgerechnet
    # - eine Erkennung sagt WAS klingt, das Fenster sagt SEIT WANN.
    timeline: list[tuple[float, str]] = []
    current: str | None = None
    lead = args.delay - 1.0  # Startschaetzung, unten aus echten Onsets gemessen

    print(f"Laeuft: Ausgabe um {loop.delay_seconds:.1f}s verzoegert. Strg+C beendet.")
    if lead < 1.0:
        print("Hinweis: --delay ist knapp; fuer nutzbaren Vorlauf >= 3s waehlen.")
    print()

    debug_path = os.environ.get("CHORDIFY_DEBUG")
    debug = open(debug_path, "w") if debug_path else None
    if debug:
        debug.write(f"# latency in={loop._stream.latency[0]:.3f} "
                    f"out={loop._stream.latency[1]:.3f}\n")
        debug.write("# wall\twindow_end\traw\tchord\tonset\taudible_pos\n")

    grid = None  # naechster Analysepunkt als Stream-Position (Frames)
    try:
        while True:
            captured = loop.captured_frames
            if captured < window_frames:
                time.sleep(ANALYSIS_HOP)
                continue
            if grid is None:
                grid = captured // hop_frames * hop_frames
            if captured < grid:
                time.sleep(min(0.02, (grid - captured) / sr))
                continue

            # Fenster enden immer auf dem Hop-Raster. Dauert eine Analyse
            # laenger als ein Hop, faellt ein Rasterpunkt aus - das Raster
            # selbst bleibt exakt, und genau daran haengt die Genauigkeit.
            window_end = captured // hop_frames * hop_frames
            grid = window_end + hop_frames
            audio = loop.audio_ending_at(window_end, window_frames)
            if audio is None:
                continue  # Analyse zu weit hinten - Rasterpunkt verwerfen
            window_start = (window_end - window_frames) / sr

            # Gepoolt wird die juengere Fensterhaelfte - Stille-Gate ebenso,
            # sonst liefern ausklingende Toene am Songende Phantomakkorde.
            raw = "-"
            if rms(audio[len(audio) // 2 :]) < SILENCE_RMS:
                smoother.reset()
                chord = "-"
            else:
                analysis = analyze_window(audio, sr)
                result = match_chord(analysis.chroma, analysis.bass)
                raw = result.name
                history.add(analysis.frames, window_start)
                chord = smoother.update(result)
                if chord == "N":
                    chord = "?"

            audible_pos = loop.audible_position()

            onset = None
            if chord != "?" and chord != current:
                found = _locate_onset(chord, current, history, window_end / sr,
                                      timeline[-1][0] if timeline else None)
                onset = _commit(timeline, found, chord, audible_pos)
                current = timeline[-1][1] if timeline else chord
                if onset is not None and chord != "-":
                    # Echter Vorlauf: so weit im Voraus wissen wir von einem
                    # Wechsel. Faellt aus den Messwerten, nicht aus Konstanten.
                    lead = 0.7 * lead + 0.3 * max(onset - audible_pos, 0.0)

            # Vergangenes behalten wir kurz - die Anzeige blendet Akkorde
            # hinter der JETZT-Linie noch aus.
            while len(timeline) > 1 and timeline[1][0] <= audible_pos - 2.0:
                timeline.pop(0)
            audible = "-"
            for pos, name in timeline:
                if pos > audible_pos:
                    break
                audible = name

            if debug:
                debug.write(f"{time.time():.3f}\t{window_end / sr:.3f}\t{raw}\t"
                            f"{chord}\t{'' if onset is None else f'{onset:.3f}'}\t"
                            f"{audible_pos:.3f}\n")
                debug.flush()

            if broadcaster:
                # Der Browser bekommt die Zeitleiste in Stream-Sekunden plus
                # die gerade hoerbare Position. Er leitet daraus Akkordanzeige
                # UND Laufband aus derselben Uhr ab - deshalb koennen sie nicht
                # auseinanderlaufen.
                broadcaster.publish({
                    "t": round(audible_pos, 3),
                    "chords": [{"c": name, "at": round(pos, 3)}
                               for pos, name in timeline],
                    "lead": round(lead, 2),
                })
            sys.stdout.write(
                f"\r  Kommt in {max(lead, 0.0):3.1f}s: {current or '-':<6s} "
                f"| Jetzt hoerbar: {audible:<6s}"
            )
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("\nBeendet.")
    finally:
        if debug:
            debug.close()
    if loop.xruns:
        print(f"Stream-Warnungen: {loop.xruns} (zuletzt: {loop.last_status})")


def _locate_onset(chord, previous, history, window_end, last_onset):
    """Stream-Position, an der `chord` einsetzt.

    Gesucht wird nicht im Analysefenster, sondern in der Frame-Historie ab dem
    letzten bekannten Wechsel. Sonst begrenzt die Fensterlaenge, wie weit die
    Suche zurueckreicht - und ein Wechsel, dessen Erkennung laenger gedauert
    hat, wird auf den Fensteranfang geklemmt und damit zu spaet gemeldet.
    """
    from .chroma import FRAME_SECONDS
    from .chords import find_onset_frame

    if chord == "-":
        # Stille schlaegt an, sobald die juengere Fensterhaelfte leise ist -
        # der Einsatz liegt also grob in deren Mitte.
        return window_end - 0.25 * ANALYSIS_WINDOW

    # Nicht weiter zurueck als bis zum letzten Wechsel: davor stand ein anderer
    # Akkord, dessen Frames die Suche nur verwaessern wuerden.
    start = window_end - MAX_ONSET_SEARCH
    if last_onset is not None:
        start = max(start, last_onset)

    fallback = window_end - 0.4 * ANALYSIS_WINDOW
    span = history.since(start)
    if span is None:
        return fallback                       # FFT-Fallback / noch zu wenig Material

    frames, span_start = span
    previous_chord = previous if previous not in (None, "-", "?") else None
    index = find_onset_frame(frames, previous_chord, chord)
    if index is None:
        return fallback

    # Frame k ist der erste des neuen Akkords, seine Mitte liegt bei
    # k * FRAME_SECONDS - die Grenze also ein halbes Frame davor.
    onset = span_start + max(index - 0.5, 0.0) * FRAME_SECONDS
    return min(onset, window_end)   # gefunden werden kann nur Vergangenes


def _commit(timeline, onset, chord, audible_pos):
    """Traegt `chord` in die Zeitleiste ein. Gibt den Onset zurueck, oder None,
    wenn kein neues Segment entstand.

    Ein Segment unter MIN_CHORD_SECONDS ist kein Akkord, sondern ein Fehlgriff
    der Erkennung. Dank des Vorlaufs sehen wir den Fehlgriff Sekunden bevor er
    hoerbar wird - also nehmen wir ihn einfach zurueck, statt ihn als 50-ms-Blitz
    durchzureichen. Der nachrueckende Akkord erbt den frueheren Onset: *wann*
    gewechselt wurde, stand bereits fest; nur *was* gespielt wird, korrigiert
    sich. Deshalb konvergiert das - jede weitere Erkennung raeumt die vorige
    Fehlentscheidung ab, ohne den Zeitpunkt zu verschieben.
    """
    while (timeline
           and timeline[-1][0] > audible_pos          # noch nicht gehoert
           and onset - timeline[-1][0] < MIN_CHORD_SECONDS):
        onset = min(onset, timeline[-1][0])
        timeline.pop()

    if timeline:
        if timeline[-1][1] == chord:
            return None            # der Akkord lief durch, der Blip war Rauschen
        # Nur erreichbar, wenn das Vorsegment schon hoerbar war: dann laesst es
        # sich nicht mehr zuruecknehmen, aber der Wechsel darf trotzdem nicht
        # kuerzer als MIN_CHORD danach liegen.
        onset = max(onset, timeline[-1][0] + MIN_CHORD_SECONDS)

    timeline.append((onset, chord))
    return onset


def main():
    parser = argparse.ArgumentParser(
        prog="chordify",
        description="Verzoegertes Systemaudio-Loopback mit Akkordanzeige (Vorlauf).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="Audio-Geraete anzeigen").set_defaults(func=cmd_devices)
    sub.add_parser("selftest", help="Erkennung ohne Audiohardware testen").set_defaults(
        func=cmd_selftest
    )
    p_cleanup = sub.add_parser(
        "cleanup", help="Verwaiste Null-Sinks nach einem Absturz entfernen")
    p_cleanup.add_argument("--force", action="store_true",
                           help="Auch aufraeumen, wenn kein Besitzer eingetragen ist")
    p_cleanup.set_defaults(func=cmd_cleanup)

    p_analyze = sub.add_parser("analyze", help="WAV-Datei offline analysieren")
    p_analyze.add_argument("file")
    p_analyze.set_defaults(func=cmd_analyze)

    p_run = sub.add_parser("run", help="Live-Loopback mit Akkordanzeige")
    # Grenzen fachlich, nicht technisch: unter ~1s Delay bleibt kein Vorlauf
    # uebrig, ueber 30s laeuft der Ringpuffer aus dem Ruder.
    p_run.add_argument("--delay", type=_bounded(float, 0.5, 30.0, "s"), default=4.0,
                       help="Verzoegerung in Sekunden (0.5..30, Standard 4)")
    p_run.add_argument("--input", default=None,
                       help="Eingabegeraet (Index/Name); schaltet in den Direktmodus")
    p_run.add_argument("--output", default=None,
                       help="Ausgabe: Sink-Name (Routing-Modus) bzw. Geraet (Direktmodus)")
    p_run.add_argument("--no-route", action="store_true",
                       help="Kein automatisches Null-Sink-Routing (Linux)")
    p_run.add_argument("--no-web", action="store_true",
                       help="Ohne Web-Anzeige starten")
    p_run.add_argument("--port", type=_bounded(int, 1024, 65535), default=8765,
                       help="Port der Web-Anzeige (1024..65535, Standard 8765)")
    p_run.add_argument("--samplerate", type=_bounded(int, 8000, 192000, " Hz"),
                       default=48000, help="Abtastrate (8000..192000, Standard 48000)")
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

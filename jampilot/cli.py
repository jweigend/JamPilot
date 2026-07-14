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
            raise argparse.ArgumentTypeError(f"'{text}' is not a number")
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(
                f"{value}{unit} is outside {low}{unit}..{high}{unit}")
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
                f"Device {device!r} not usable ({kind}): {exc}\n"
                f"'jampilot devices' lists the available devices."
            )


def cmd_devices(_args):
    import sounddevice as sd

    print("PortAudio devices (--input/--output in direct mode):\n")
    print(sd.query_devices())
    if shutil.which("pactl"):
        out = subprocess.run(
            ["pactl", "list", "short", "sinks"], capture_output=True, text=True
        ).stdout
        print("\nPulseAudio/PipeWire outputs (--output in routing mode):")
        for line in out.strip().splitlines():
            print("  " + line.split("\t")[1])


def cmd_selftest(_args):
    from . import selftest

    sys.exit(0 if selftest.run() else 1)


def cmd_cleanup(args):
    from . import routing

    if not routing.available():
        print("pactl not found - nothing to clean up here.")
        return
    # Ein SIGKILL laesst sich nicht abfangen; danach bleibt der Null-Sink als
    # Standard-Ausgang stehen und der Rechner ist stumm. Das raeumt das weg -
    # aber nur, wenn der Besitzer wirklich tot ist.
    try:
        removed = routing.cleanup(force=args.force)
    except routing.InstanceRunning as exc:
        raise SystemExit(f"{exc}\n'jampilot cleanup --force' cleans up anyway.")
    print(f"Removed {removed} orphaned jampilot sink(s)." if removed
          else "No orphaned jampilot sinks found.")
    print(f"Default output: {routing._pactl('get-default-sink')}")


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
        raise ValueError(f"Unsupported sample width: {width * 8} bit")
    return data.reshape(-1, channels).mean(axis=1), samplerate


def cmd_analyze(args):
    from . import bass as bassmodul
    from .chroma import analyze_window, rms
    from .chords import SILENCE_RMS, match_chord
    from .tonality import SHARP, KeyEstimator, spell

    samples, samplerate = _load_wav_mono(args.file)
    window = int(ANALYSIS_WINDOW * samplerate)
    hop = int(0.5 * samplerate)

    print(f"{args.file}: {len(samples) / samplerate:.1f}s @ {samplerate} Hz\n")
    if len(samples) < window:
        print(f"  File is shorter than the analysis window ({ANALYSIS_WINDOW}s).")
        return

    # Offline liegt die ganze Datei vor: die Tonart darf ueber das gesamte
    # Material bestimmt werden (kein Verfall), statt nur ueber ihr Ende. Deshalb
    # erst alles erkennen, dann die Tonart, dann ausgeben - die Schreibweise der
    # ersten Zeile haengt schliesslich von Akkorden ab, die spaeter kommen.
    keys = KeyEstimator(hop / samplerate, half_life=None)
    erkannt = []
    # +1, sonst faellt das letzte vollstaendige Fenster raus - und eine Datei
    # von genau Fensterlaenge wuerde ueberhaupt nicht analysiert.
    for start in range(0, len(samples) - window + 1, hop):
        chunk = samples[start : start + window]
        if rms(chunk) < SILENCE_RMS:
            name = "-"
        else:
            analysis = analyze_window(chunk, samplerate)
            # Zwei Fragen, zwei Signale: der Akkord aus der vollen Harmonie, die
            # Bassnote aus dem Tiefband. Zusammen ergeben sie C/E statt nur C.
            #
            # Beide muessen ueber DENSELBEN Zeitraum reden: Das Chroma wird nur
            # aus der juengeren Fensterhaelfte gepoolt (chroma._pool), also darf
            # auch der Bass nur von dort kommen. Sonst klebt an jedem Wechsel der
            # Bass des VORIGEN Akkords am neuen, und die Anzeige erfindet
            # Umkehrungen, die nie gespielt wurden ("Bb/F", "C/Bb").
            bass_frames = analysis.bass_frames
            juengere = (bass_frames[:, bass_frames.shape[1] // 2 :]
                        if bass_frames is not None else None)
            name = bassmodul.slash(
                match_chord(analysis.chroma, analysis.bass).name,
                bassmodul.name(bassmodul.dominant(juengere)))
            keys.add(analysis.chroma)
        # Gepoolt wird die juengere Fensterhaelfte -> Zeitstempel mittig.
        erkannt.append(((start + 0.75 * window) / samplerate, name))

    key = keys.key
    accidental = key.accidental if key else SHARP
    print(f"  Key: {key.label} ({'b' if accidental != SHARP else '#'})\n" if key
          else "  Key: undetermined (too little music) - chords spelled with sharps\n")

    last = None
    for zeit, name in erkannt:
        if name != last:
            print(f"  {zeit:6.1f}s  {spell(name, accidental)}")
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
            print(f"Display: {web_display.url}  "
                  f"(QR code on the page; put your phone on the same Wi-Fi)")
        except OSError as exc:
            print(f"Web display unavailable ({exc}) - continuing without it.")

    from .chroma import warmup

    print("Initialising analysis...", end="", flush=True)
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
                    print(f"Capturing system audio (null sink "
                          f"'{routing.SINK_NAME}'), output to: "
                          f"{args.output or route.previous_sink}")
                    _display_loop(loop, args, broadcaster)
                finally:
                    loop.stop()
        else:
            if args.input is None:
                print("Direct mode: using the default input.")
                print("(macOS: install BlackHole and select it with --input.)")
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
    from . import bass as bassmodul
    from .chroma import FrameHistory, analyze_window, rms
    from .chords import SILENCE_RMS, ChordSmoother, match_chord
    from .tonality import SHARP, KeyEstimator, spell

    sr = args.samplerate
    window_frames = int(round(ANALYSIS_WINDOW * sr))
    hop_frames = int(round(ANALYSIS_HOP * sr))
    smoother = ChordSmoother(window=3)
    # Frame-Chroma laenger aufheben als ein Fenster - siehe _locate_onset.
    history = FrameHistory(MAX_ONSET_SEARCH + ANALYSIS_WINDOW + 1.0)
    # Die Tonart entscheidet ueber die Schreibweise (# oder b). Sie braucht
    # laengeres Material als ein Akkord und meldet sich die ersten ~12s Musik
    # gar nicht - bis dahin gelten Kreuze.
    keys = KeyEstimator(ANALYSIS_HOP)
    # Die Bassnote wird gemessen, nicht aus dem Akkord abgeleitet - erst dadurch
    # werden Umkehrungen sichtbar (C/E). Die Spur muss die ganze Zeitleiste
    # abdecken: von 2s hinter der hoerbaren Position bis zur Analysefront.
    bass_track = bassmodul.BassTrack(args.delay + ANALYSIS_WINDOW + 4.0)

    # Die Zeitleiste: (Onset-Position im Stream, Akkord). Die Onsets werden im
    # Frame-Chroma gemessen, nicht aus dem Erkennungszeitpunkt zurueckgerechnet
    # - eine Erkennung sagt WAS klingt, das Fenster sagt SEIT WANN.
    timeline: list[tuple[float, str]] = []
    current: str | None = None
    lead = args.delay - 1.0  # Startschaetzung, unten aus echten Onsets gemessen

    print(f"Running: output delayed by {loop.delay_seconds:.1f}s. Ctrl+C quits.")
    if lead < 1.0:
        print("Note: --delay is tight; choose >= 3s for a useful lead.")
    print()

    debug_path = os.environ.get("JAMPILOT_DEBUG")
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
                keys.add(analysis.chroma)
                # Die Bassnote laeuft NEBEN der Akkorderkennung, nicht in ihr:
                # zwei Fragen, zwei Signale. Der Akkord braucht die volle
                # Harmonie, der Bass nur das Tiefband - und dessen Frames fallen
                # in derselben Analyse ohnehin an (siehe bass.py).
                bass_track.add(analysis.bass_frames, window_start)
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

            key = keys.key
            # Zu jedem Segment die Bassnote, die WAEHREND seiner Dauer gemessen
            # wurde - auch fuer Segmente, die noch niemand gehoert hat. Der
            # Vorlauf gilt fuer den Bass genauso wie fuer den Akkord.
            basslinie = _bass_per_segment(timeline, bass_track, window_end / sr)
            bass_jetzt = None
            for (pos, _), gemessen in zip(timeline, basslinie):
                if pos > audible_pos:
                    break
                bass_jetzt = gemessen      # der letzte, der schon erklungen ist

            if broadcaster:
                # Der Browser bekommt die Zeitleiste in Stream-Sekunden plus
                # die gerade hoerbare Position. Er leitet daraus Akkordanzeige
                # UND Laufband aus derselben Uhr ab - deshalb koennen sie nicht
                # auseinanderlaufen.
                #
                # Die Akkorde gehen kanonisch raus (immer mit Kreuz); wie sie
                # geschrieben werden, entscheidet der Browser aus `key` und der
                # dort eingestellten Vorliebe. So wirkt eine Umstellung sofort
                # und rueckwirkend, ohne Runde ueber den Server - und Laptop und
                # Handy duerfen verschieden eingestellt sein.
                # Die Bassnote faehrt pro Segment mit; ob sie gezeigt wird,
                # entscheidet der Browser (Modus "Bass") - wie bei der
                # Schreibweise ist das eine Anzeige-, keine Serverfrage.
                broadcaster.publish({
                    "t": round(audible_pos, 3),
                    "chords": [{"c": name, "at": round(pos, 3), "b": bassnote}
                               for (pos, name), bassnote in zip(timeline, basslinie)],
                    "lead": round(lead, 2),
                    "key": key.as_dict() if key else None,
                })

            # Im Terminal gibt es keinen Dialog - hier gilt immer die erkannte
            # Tonart, und solange keine feststeht, das Kreuz.
            accidental = key.accidental if key else SHARP
            # Der hoerbare Akkord mit gemessenem Bass: C/E statt C.
            jetzt = bassmodul.slash(audible, bass_jetzt)
            sys.stdout.write(
                f"\r  In {max(lead, 0.0):3.1f}s: "
                f"{spell(current or '-', accidental):<6s} "
                f"| Now playing: {spell(jetzt, accidental):<8s} "
                f"| Bass: {spell(bass_jetzt or '-', accidental):<3s} "
                f"| Key: {key.label if key else '...':<9s}"
            )
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if debug:
            debug.close()
    if loop.xruns:
        print(f"Stream warnings: {loop.xruns} (last: {loop.last_status})")


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


def _bass_per_segment(timeline, track, front: float) -> list[str | None]:
    """Zu jedem Zeitleisten-Segment die vorherrschende Bassnote (kanonisch).

    Ein Segment reicht von seinem Onset bis zum naechsten; das letzte bis zur
    Analysefront. Waehrend einer Stille gibt es keinen Bass - und wo die Messung
    keine Mehrheit findet, steht None: lieber nichts anzeigen als raten.
    """
    from . import bass as bassmodul

    noten = []
    for i, (onset, chord) in enumerate(timeline):
        ende = timeline[i + 1][0] if i + 1 < len(timeline) else front
        if chord == "-" or ende <= onset:
            noten.append(None)
            continue
        noten.append(bassmodul.name(track.note_between(onset, ende)))
    return noten


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
        prog="jampilot",
        description="Delayed system-audio loopback with a chord display that runs ahead.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("devices", help="List audio devices").set_defaults(func=cmd_devices)
    sub.add_parser("selftest", help="Test detection without audio hardware").set_defaults(
        func=cmd_selftest
    )
    p_cleanup = sub.add_parser(
        "cleanup", help="Remove orphaned null sinks after a crash")
    p_cleanup.add_argument("--force", action="store_true",
                           help="Clean up even if no owner is registered")
    p_cleanup.set_defaults(func=cmd_cleanup)

    p_analyze = sub.add_parser("analyze", help="Analyse a WAV file offline")
    p_analyze.add_argument("file")
    p_analyze.set_defaults(func=cmd_analyze)

    p_run = sub.add_parser("run", help="Live loopback with chord display")
    # Grenzen fachlich, nicht technisch: unter ~1s Delay bleibt kein Vorlauf
    # uebrig, ueber 30s laeuft der Ringpuffer aus dem Ruder.
    p_run.add_argument("--delay", type=_bounded(float, 0.5, 30.0, "s"), default=4.0,
                       help="Delay in seconds (0.5..30, default 4)")
    p_run.add_argument("--input", default=None,
                       help="Input device (index/name); switches to direct mode")
    p_run.add_argument("--output", default=None,
                       help="Output: sink name (routing mode) or device (direct mode)")
    p_run.add_argument("--no-route", action="store_true",
                       help="No automatic null-sink routing (Linux)")
    p_run.add_argument("--no-web", action="store_true",
                       help="Start without the web display")
    p_run.add_argument("--port", type=_bounded(int, 1024, 65535), default=8765,
                       help="Port of the web display (1024..65535, default 8765)")
    p_run.add_argument("--samplerate", type=_bounded(int, 8000, 192000, " Hz"),
                       default=48000, help="Sample rate (8000..192000, default 48000)")
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

"""Kommandozeilen-Frontend fuer den ersten Durchstich.

Befehle:
    devices                Audio-Geraete und Systemaudio-Quellen anzeigen
    selftest               Erkennungspipeline ohne Audiohardware testen
    install                Starter fuer den Doppelklick anlegen (Linux)
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

# [POC-BTC] BTC-Transformer fuehrend (siehe _display_loop). Das Modell sieht
# pro Lauf ein 10-s-Fenster (108 Frames); der juengste Rand hat keinen
# Zukunftskontext und flackert - Segmente dort warten bis zum naechsten Hop.
# Beides zehrt vom --delay-Puffer (Default 4s), nicht von der Anzeige.
BTC_LIVE_WINDOW = 10.0
BTC_EDGE_GUARD = 1.0

# Eine schon veroeffentlichte Akkordgrenze bleibt liegen, solange die frische
# Modellausgabe sie nur um so viel verschiebt: Das Frameraster wandert pro Hop
# (s. _merge_model_segments), und staendig springende Grenzen zerlegen die
# Chips der Vorlaufansicht. Gegen falsches Anschnappen schuetzen Namensgleichheit,
# Einmal-Verbrauch je alter Grenze und der Monotonie-Waechter - nicht die Weite.
ONSET_HYSTERESIS = 0.35

# Naeher als das an der hoerbaren Position wird NICHTS mehr umgebaut: Diese
# Chips liest der Musiker gerade, um den Griff vorzubereiten - eine Korrektur
# dort ist schlimmer als ein stehengelassener Fehler. Revisionen darf das
# Modell nur weiter draussen anbringen (bei --delay 4 bleiben dafuer ~1.5s
# zwischen Veroeffentlichung am Horizont und dem Einfrieren).
BTC_FREEZE_AHEAD = 1.5

# Eine NEUE Grenze kommt erst in die Zeitleiste, wenn schon der VORIGE
# Modelllauf sie gesehen hat (gleicher Name, Lage bis auf diese Toleranz).
# Das filtert Geister-Segmente, die nur einen einzigen Lauf lang existieren -
# und verzoegert echte Segmente nicht: Der vorige Lauf reicht ueber den
# Horizont hinaus, dort stand die Grenze bereits.
BTC_DEBOUNCE_MATCH = 0.3

# Verfeinerte Grenzen (btc.refine_boundary) liegen bis zu so viel FRUEHER als
# die rohe Modellgrenze des naechsten Laufs - die Hysterese-Fenster im Merge
# sind um diesen Betrag nach hinten verlaengert, sonst wuerde dieselbe Grenze
# jeden Hop neu verfeinert. Muss btc.REFINE_BACK entsprechen.
_REFINED_LOOKBACK = 0.40

# Kuerzer als das spielt niemand einen Akkord. Ein Segment darunter ist kein
# Wechsel, sondern ein Fehlgriff der Erkennung - und wird zurueckgenommen.
MIN_CHORD_SECONDS = 0.25

# Wie weit die Onset-Suche zurueckreichen darf. Muss deutlich ueber der
# Erkennungslatenz liegen (median ~0.8s, bei mehrdeutigen Wechseln aber auch
# ueber 1.5s): reicht die Suche nicht bis zum Einsatz zurueck, wird er auf den
# Suchanfang geklemmt - und das ist immer ZU SPAET, nie zu frueh.
MAX_ONSET_SEARCH = 4.0

# Wie lange der Ringpuffer stillstehen darf, bevor der Stream als tot gilt.
# Ein Callback kommt alle ~43ms (2048 Frames bei 48kHz); selbst ein schwer
# klemmender Rechner haelt keine 3s durch. Grosszuegig gewaehlt, weil ein
# Fehlalarm den laufenden Betrieb abbaeche - USB-Geraete brauchen nach dem
# Start durchaus eine Sekunde, bis die ersten Frames kommen.
STREAM_STALL_TIMEOUT = 3.0


class StreamStalled(RuntimeError):
    """Es kommen keine Frames mehr - das Audiogeraet ist weg."""


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


def _check_devices(args):
    """Geraete pruefen, BEVOR der teure Warmup laeuft.

    `--output` ist im Routing-Modus ein PulseAudio-SINK, sonst ein
    PortAudio-GERAET - zwei Namensraeume, die sich nicht ueberschneiden. Wer im
    Routing-Modus gegen PortAudio prueft, weist genau die Sink-Namen ab, die
    `jampilot devices` unter "routing mode" auflistet: `--output
    alsa_output.usb-...` starb dann mit "Device not usable", bevor ueberhaupt
    etwas lief. Deshalb entscheidet hier dieselbe Funktion wie beim Aufbau.
    """
    import sounddevice as sd

    from . import routing

    geroutet = routing.uses_routing(args)
    # Ein SINK-Name ist `--output` nur unter Linux. Die Windows-Umleitung
    # schickt die verzoegerte Ausgabe an ein PortAudio-GERAET wie im
    # Direktmodus - dort muss also weiter gegen PortAudio geprueft werden,
    # sonst laeuft `--output "Kopfhoerer..."` ungeprueft in den Aufbau.
    sink_modus = geroutet and routing.backend() == routing.PULSE
    geraete = [(args.input, "input")]
    if not sink_modus:
        geraete.append((args.output, "output"))

    for device, kind in geraete:
        if device is None:
            # Ohne Angabe darf hier NUR geprueft werden, was engine.start()
            # hinterher wirklich an PortAudio uebergibt - sonst prueft man ein
            # anderes Geraet als das, das gleich geoeffnet wird.
            #
            # Im Routing-Modus ist das der Null-Sink, den es jetzt noch gar
            # nicht gibt. Unter Linux ohne Routing ist es die ALSA-Quelle
            # "default" (engine._standardgeraet) - die traegt seit jeher, und
            # sie hier zusaetzlich zu pruefen waere eine Verhaltensaenderung auf
            # der Referenzplattform ohne Gegenwert. Beides bleibt also aussen
            # vor, genau wie bisher.
            #
            # Bleibt der Fall, in dem PortAudio sein Standardgeraet SELBST
            # waehlt: Windows und macOS. Und genau darauf faellt dort der erste
            # Versuch herein, denn das ist das Mikrofon, oft mono.
            if geroutet or sys.platform.startswith("linux"):
                continue
            try:
                info = sd.query_devices(kind=kind)
            except (ValueError, sd.PortAudioError):
                continue        # kein Standardgeraet - das faellt beim Aufbau auf
        else:
            try:
                info = sd.query_devices(device, kind)
            except (ValueError, sd.PortAudioError) as exc:
                raise SystemExit(
                    f"Device {device!r} not usable ({kind}): {exc}\n"
                    f"'jampilot devices' lists the available devices."
                )
        # Der Stream ist stereo (delay_stream.DelayedLoopback, channels=2). Ein
        # Geraet mit nur einem Kanal laesst ihn mit "Invalid number of channels
        # [PaErrorCode -9998]" scheitern - eine Meldung, die nicht sagt, WELCHES
        # der beiden Geraete gemeint ist und schon gar nicht, was zu tun waere.
        # Unter Windows ist das der haeufigste Fehlgriff: Die meisten Mikrofone
        # sind mono, das virtuelle Kabel dagegen ist stereo.
        kanaele = info[f"max_{kind}_channels"]
        if kanaele < 2:
            bezeichnung = (f"The default {kind} device {info['name']!r}"
                           if device is None else f"Device {device!r}")
            hinweis = (f"Pass --{kind} to pick another one; "
                       if device is None else "")
            raise SystemExit(
                f"{bezeichnung} has {kanaele} {kind} channel(s) - JamPilot "
                f"needs 2 (stereo).\n"
                f"This is usually a microphone. What you want as the input is a "
                f"loopback device that carries the system sound "
                f"(VB-CABLE on Windows, BlackHole on macOS).\n"
                f"{hinweis}'jampilot devices' lists the available devices."
            )

    if sink_modus and args.output is not None:
        try:
            sinks = routing.hardware_sinks()
        except (RuntimeError, OSError):
            return          # pactl streikt - das faellt beim Aufbau auf, hier nicht
        if str(args.output) not in {feld for sink in sinks for feld in sink}:
            raise SystemExit(
                f"Sink {args.output!r} unknown.\n"
                f"'jampilot devices' lists the available sinks."
            )


def cmd_devices(_args):
    import sounddevice as sd

    from . import routing

    print("PortAudio devices (--input/--output in direct mode):\n")
    print(sd.query_devices())

    # Unter Windows ist die interessanteste Frage nicht, WELCHE Geraete es gibt
    # - davon stehen oben dreissig -, sondern ob JamPilot sich selbst versorgen
    # kann. Diese zwei Zeilen beantworten sie.
    if sys.platform == "win32":
        print("\nAutomatic routing (no options needed):")
        stumm = routing._stummweg(neu_pruefen=True)
        kabel = routing._kabel(neu_pruefen=True)
        if kabel:
            ziel = routing.windows_playback_target()
            print(f"  routes    system output -> {kabel[0].name}")
            print(f"  captures  {kabel[1].name}")
            print(f"  playback  {ziel.name if ziel else '(no real output!)'}")
            if stumm:
                print(f"  (--route mute would use {stumm[0].name} as a muted "
                      f"detour instead - no driver)")
        elif stumm:
            umweg, ausgabe = stumm
            print(f"  routes    system output -> {umweg.name}  [muted]")
            print(f"  captures  the same endpoint (WASAPI loopback)")
            print(f"  playback  {ausgabe.name}")
            print("  no driver needed")
        else:
            print("  unavailable - JamPilot needs either a second output "
                  "endpoint to use as a silent detour, or VB-CABLE "
                  "(https://vb-audio.com/Cable/)")

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


def cmd_install(args):
    from . import desktop

    desktop.install(nach=args.to, entfernen=args.remove)


_konsolenwaechter = None       # Die Rueckruffunktion MUSS am Leben bleiben.


def _beim_schliessen_der_konsole(engine):
    """Das Fenster wegklicken darf den Ton nicht mitnehmen - Windows-Fassung.

    cmd_run faengt dafuer SIGTERM und SIGHUP ab. Unter Windows gibt es SIGHUP
    nicht, und SIGTERM schickt dort niemand: Wer sein Konsolenfenster
    zumacht, loest CTRL_CLOSE_EVENT aus, und das kennt nur
    SetConsoleCtrlHandler. Ohne diesen Haken bliebe das Kabel Standard-Ausgang
    und der Rechner stumm - bei einer Handlung, die JEDER macht und die vor
    dieser Umleitung voellig harmlos war.

    Windows raeumt danach selbst ab (etwa fuenf Sekunden Gnadenfrist, dann
    stirbt der Prozess). engine.stop() braucht davon hoechstens drei.

    NUR die Ereignisse, fuer die es keinen Python-Weg gibt. Strg+C laeuft
    weiter ueber KeyboardInterrupt und `finally` - dort ist die Meldung
    hoebscher, und zwei Wege fuer dasselbe waeren einer zu viel.
    """
    if sys.platform != "win32":
        return

    import ctypes

    CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT = 2, 5, 6
    HANDLER = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

    def behandeln(ereignis):
        if ereignis in (CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT):
            engine.stop()
        return False        # weiterreichen: danach beendet Windows uns regulaer

    # In einem Modulnamen festhalten. Wird die Rueckruffunktion eingesammelt,
    # ruft Windows spaeter in freigegebenen Speicher - der Prozess stuerbe genau
    # in dem Moment ab, in dem er aufraeumen sollte.
    global _konsolenwaechter
    _konsolenwaechter = HANDLER(behandeln)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_konsolenwaechter, True)


def _bericht_zur_quelle(args):
    """Eine Zeile darueber, WOHER der Ton kommt - und was fehlt, wenn er fehlt.

    Der teuerste Fehler dieses Programms ist der, bei dem es tadellos laeuft
    und das Falsche tut: Ohne Umleitung und ohne `--input` nimmt PortAudio sein
    Standard-Eingabegeraet, und das ist auf jedem Laptop das MIKROFON. JamPilot
    verzoegert dann den Raum statt der Musik und zeigt die Akkorde dazu an.
    Ein Absturz waere leichter zu durchschauen.
    """
    from . import routing

    if routing.uses_routing(args):
        if routing.backend() == routing.WINMUTE:
            weg = routing._stummweg()
            if weg:
                umweg, ausgabe = weg
                # Dieselbe Zeile wie beim Kabel, mit demselben Aufbau: wohin
                # der Systemton geht, und wo der Nutzer hoert. Das zweite ist
                # das, was er pruefen wird, wenn er nichts hoert.
                print(f"System audio -> {umweg.name!r} (a second output, "
                      f"muted so nothing comes out of it) -> JamPilot -> "
                      f"{ausgabe.name!r} (restored on exit). No driver needed. "
                      f"Voice chat is left alone.")
            return
        if routing.backend() == routing.WINCABLE:
            kabel = routing._kabel()
            ziel = routing.windows_playback_target()
            print(f"System audio -> {kabel[0].name!r} -> JamPilot -> "
                  f"{ziel.name if ziel else '?'} (restored on exit). "
                  f"Voice chat is left alone.")
        return

    if args.input is not None or sys.platform.startswith("linux"):
        # Unter Linux gibt engine.py hier die ALSA-Quelle "default" an, nicht
        # PortAudios Standardgeraet - ein Hinweis nennte also ein Geraet, das
        # gar nicht geoeffnet wird, und riete zu Treibern, die es auf der
        # Plattform nicht gibt. Wer dort `--no-route` tippt, weiss, was er tut.
        return

    if sys.platform == "win32" and not args.no_route:
        # Der einzige Fall, in dem unter Windows noch von Hand gearbeitet
        # werden muss - und der einzige, der sich mit einem Satz beheben laesst.
        # Danach ist Schluss: Der generische Hinweis unten wuerde denselben
        # Treiber ein zweites Mal empfehlen, und gleich darauf sagt
        # _check_devices ohnehin, welches Geraet nicht taugt.
        print("JamPilot cannot take over the system sound here and falls back "
              "to the default input device. It needs a silent detour for your "
              "players, and there are two ways to get one: a SECOND OUTPUT "
              "ENDPOINT it can mute and capture (an HDMI or S/PDIF output "
              "counts, nothing has to be plugged into it - no install at "
              "all), or VB-CABLE (https://vb-audio.com/Cable/, run "
              "VBCABLE_Setup_x64.exe as administrator, then reboot). "
              "'jampilot devices' shows what it found. Your speakers keep "
              "playing the delayed music either way.")
        return

    import sounddevice as sd

    try:
        name = sd.query_devices(kind="input")["name"]
    except Exception:                      # kein Eingang - faellt gleich auf
        name = "the system default input"
    print(f"No --input given: capturing from {name!r}. If that is a "
          f"microphone, JamPilot delays the room instead of your music - "
          f"point --input at a loopback device (VB-CABLE on Windows, "
          f"BlackHole on macOS). 'jampilot devices' lists them.")


def cmd_cleanup(args):
    from . import routing

    if not routing.available():
        print("No audio routing on this machine (Linux needs pactl, Windows "
              "needs a second playback device or VB-CABLE) - nothing to clean "
              "up here.")
        return
    # Ein SIGKILL laesst sich nicht abfangen; danach bleibt der stumme Umweg
    # Standard-Ausgang und der Rechner hat keinen Ton. Das raeumt das weg -
    # aber nur, wenn der Besitzer wirklich tot ist.
    try:
        aufgeraeumt = routing.cleanup(force=args.force)
    except routing.InstanceRunning as exc:
        raise SystemExit(f"{exc}\n'jampilot cleanup --force' cleans up anyway.")
    if sys.platform == "win32":
        # WAS zurueckgenommen wurde, steht im Vermerk des abgestuerzten Laufs
        # und nicht im heutigen backend() - deshalb hier eine Meldung fuer
        # beide Wege statt zwei, von denen eine luegen kann.
        print("Undid what a crashed run left behind (muted endpoint or "
              "redirected system output)." if aufgeraeumt
              else "Nothing left over - the audio setup is untouched.")
    else:
        print(f"Removed {aufgeraeumt} orphaned jampilot sink(s)." if aufgeraeumt
              else "No orphaned jampilot sinks found.")
    print(f"Default output: {routing.current_output()}")


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
    # [POC-BTC] BTC-Transformer fuehrend. Der bisherige Template-Matching-Pfad
    # liegt unveraendert in _cmd_analyze_template; Slash-Bass ist wieder aktiv
    # (Tiefband aus der BTC-CQT), Safe-Voicings/Key-Prior bleiben stillgelegt.
    from . import bass as bassmodul
    from .btc import (BTC_FRAME_SECONDS, BTCModel, features_from_audio,
                      fold_bass_chroma, fold_chroma, live_segments_from_labels,
                      refine_boundary)
    from .tonality import SHARP, KeyEstimator, spell

    samples, samplerate = _load_wav_mono(args.file)
    print(f"{args.file}: {len(samples) / samplerate:.1f}s @ {samplerate} Hz\n")
    # Unter Fensterlaenge ist auch fuer das Modell nichts zu holen - und die
    # Meldung soll dieselbe bleiben wie bisher.
    if len(samples) < ANALYSIS_WINDOW * samplerate:
        print(f"  File is shorter than the analysis window ({ANALYSIS_WINDOW}s).")
        return

    features = features_from_audio(samples, samplerate)
    labels = BTCModel().predict(features)

    # Tonart nur fuer die Schreibweise (# oder b) - wie bisher ueber die ganze
    # Datei, aber aus dem gefalteten BTC-CQT statt aus der Chroma-Pipeline.
    keys = KeyEstimator(BTC_FRAME_SECONDS, half_life=None)
    for frame in fold_chroma(features):
        keys.add(frame)
    key = keys.key
    accidental = key.accidental if key else SHARP
    print(f"  Key: {key.label} ({'b' if accidental != SHARP else '#'})\n" if key
          else "  Key: undetermined (too little music) - chords spelled with sharps\n")

    # Bassnote je Segment aus dem Tiefband der ohnehin berechneten CQT -
    # dieselbe Zwei-Signale-Idee wie im Template-Pfad (bass.py).
    bass_chroma = fold_bass_chroma(features)
    segmente = segments_from_labels(labels)
    # Grenzen aufs Audio-Ereignis verfeinern (93-ms-Raster -> 23-ms-Suche).
    fein = segmente[:1]
    for i in range(1, len(segmente)):
        pos, name = segmente[i]
        pos = refine_boundary(samples, samplerate, pos, segmente[i - 1][1], name)
        fein.append((max(pos, fein[-1][0] + 0.05), name))
    segmente = fein
    for i, (zeit, name) in enumerate(segmente):
        ende = (segmente[i + 1][0] if i + 1 < len(segmente)
                else len(labels) * BTC_FRAME_SECONDS)
        von, bis = int(zeit / BTC_FRAME_SECONDS), int(ende / BTC_FRAME_SECONDS)
        pooled = bass_chroma[:, von:bis].sum(axis=1) if bis > von else None
        note = bassmodul.name(bassmodul.slash_note(pooled, name))
        # N = nichts erklingt -> "-" wie bisher; "?" (X) geht durch.
        shown = bassmodul.slash("-" if name == "N" else name, note)
        print(f"  {zeit:6.1f}s  {spell(shown, accidental)}")


def _cmd_analyze_template(args):
    """[POC-BTC] stillgelegt: Offline-Analyse ueber Template-Matching.

    Vollstaendig funktionsfaehig, aber nicht mehr verdrahtet - cmd_analyze
    laeuft ueber das BTC-Modell. Hier liegen die Faehigkeiten, die BTC nicht
    hat (gemessener Slash-Bass), fuer die spaetere Reaktivierung.
    """
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
                match_chord(analysis.chroma, cqt=analysis.cqt).name,
                bassmodul.name(bassmodul.dominant(juengere)))
            keys.add(analysis.chroma)
        # Gepoolt wird die juengere Fensterhaelfte -> Zeitstempel mittig.
        erkannt.append(((start + 0.75 * window) / samplerate, name))

    key = keys.key
    # Offline gilt die Tonart der GANZEN Datei, und ausgegeben wird erst am
    # Ende: Hier gibt es nichts, was flackern koennte, also auch keinen Grund
    # fuer die traege Schreibweise des Live-Betriebs (KeyEstimator.accidental).
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

    # Auch bei `kill` (SIGTERM) und beim Schliessen des Terminals (SIGHUP) das
    # Routing sauber zurueckbauen. Unbehandelt beenden beide den Prozess SOFORT -
    # ohne finally, ohne Abbau, mit dem Null-Sink als Standardausgang. Wer sein
    # Terminalfenster zumacht, haette danach einen stummen Rechner und nichts,
    # was das erklaert.
    #
    # Unter Windows gibt es dafuer KEIN Signal - dieselbe Handlung heisst dort
    # CTRL_CLOSE_EVENT und geht ueber SetConsoleCtrlHandler, siehe
    # _beim_schliessen_der_konsole().
    #
    # Im Fenster reicht das NICHT: Dort entstuende die Ausnahme in einer
    # Qt-Verbindung, und PySide6 faengt sie ab und macht weiter. gui.py setzt die
    # Handler deshalb neu - siehe beenden_bei_signal().
    def _raise_interrupt(*_):
        raise KeyboardInterrupt

    for zeichen in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, zeichen):
            signal.signal(getattr(signal, zeichen), _raise_interrupt)

    # Die URSACHE vor der Absage. Unter Windows OHNE virtuelles Kabel bricht
    # _check_devices am Mikrofon ab ("hat 1 Kanal") - und das ist zwar wahr,
    # aber nicht das Problem: Das Problem ist der fehlende Treiber, und wer
    # zuerst die Absage liest, sucht den Fehler bei seinem Mikrofon. Beide
    # Pruefungen sind billig, die Reihenfolge kostet also nichts und erklaert
    # alles.
    _bericht_zur_quelle(args)

    # Erst pruefen, dann teuer werden: Geraete- und Instanzfehler sollen sofort
    # kommen, nicht als Traceback nach drei Sekunden numba-Warmup.
    _check_devices(args)
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

    broadcaster = web_display.broadcaster if web_display else None

    from .engine import Engine

    engine = Engine(args, broadcaster)
    _beim_schliessen_der_konsole(engine)

    # Der Stummschalter der Webseite und der im Fenster muessen DIESELBE Sache
    # umlegen - sonst zeigen die beiden Oberflaechen Verschiedenes an.
    if web_display:
        web_display.set_mute_toggle(engine.toggle_mute)
        web_display.set_control_guitar_toggle(engine.toggle_control_guitar)

    url = web_display.url if web_display else None

    # Fenster, wenn eines geht. Es ist die Notbremse fuer den Fall, dass jemand
    # die Webseite schliesst und sich fragt, wo sein Ton geblieben ist: Ohne
    # sichtbaren Schalter bleibt die Umleitung bestehen, und niemand findet den
    # Weg zurueck. Auf einem Server per SSH gibt es kein Fenster - dann laeuft es
    # wie bisher rein auf der Kommandozeile.
    from . import gui

    mit_fenster = not args.no_window and gui.verfuegbar()
    if not mit_fenster and not args.no_window:
        print("No display available - running headless (Ctrl+C quits).")

    def vorheizen():
        """numbas JIT uebersetzen lassen, bevor der erste Ton analysiert wird."""
        from .chroma import warmup

        warmup(args.samplerate, ANALYSIS_WINDOW)

    try:
        if mit_fenster:
            # Das Fenster geht ZUERST auf, das Audio startet erst darin. Anders
            # herum stuerbe ein Geraetefehler mit einem Traceback ins Terminal -
            # und ausgerechnet dann saehe der Nutzer kein Fenster, obwohl das der
            # Moment ist, in dem er eines braucht. So landet der Fehler dort, wo
            # er hingehoert: sichtbar, neben dem Schalter, der ihn behebt.
            #
            # Aus demselben Grund geht das Fenster auch vor dem WARMUP auf, und
            # der laeuft dahinter im Hintergrund (gui.run kuemmert sich darum).
            # numbas JIT braucht ~3s, das Entpacken der Binary noch einmal ~2.5s
            # - wer doppelklickt, hat kein Terminal, in dem "Initialising
            # analysis..." stuende, und saehe FUENF SEKUNDEN LANG NICHTS. Genau
            # so sieht ein Programm aus, das nicht startet: Man klickt noch
            # einmal, und dann laufen zwei.
            #
            # Qt MUSS im Hauptthread laufen (unter macOS zwingend), die Analyse
            # laeuft daher im Hintergrund - siehe engine.py.
            sys.exit(gui.run(engine, url, autostart=True, vorbereiten=vorheizen))
        print("Initialising analysis...", end="", flush=True)
        vorheizen()
        print(" ok", flush=True)   # ohne flush landet das "ok" hinter einem Traceback
        engine.start()
        try:
            engine._thread.join()      # bis Strg+C - oder bis der Stream stirbt
        except KeyboardInterrupt:
            print("\nStopped.")
        else:
            # Ohne Fenster gibt es niemanden, der `status` anzeigt. Der Thread
            # endet aber auch von selbst, wenn das Geraet verschwindet - dann
            # duerfte das Programm nicht wortlos und mit Erfolg zurueckkehren.
            if engine.status == "error":
                print()                # die Statuszeile steht ohne Zeilenumbruch
                raise SystemExit(engine.fehler or "Audio stream failed.")
    finally:
        engine.stop()
        if web_display:
            web_display.stop()


def _display_loop(loop, args, broadcaster=None, stop=None, engine=None):
    """Analyse und Anzeige, bis Strg+C kommt oder `stop` gesetzt wird.

    [POC-BTC] BTC-Transformer fuehrend: Jeder Hop laesst das Modell ueber die
    juengsten BTC_LIVE_WINDOW Sekunden laufen; der noch nicht hoerbare Teil der
    Zeitleiste wird komplett aus der frischen Modellausgabe neu aufgebaut.
    Gehoertes bleibt unantastbar, der juengste Fensterrand (BTC_EDGE_GUARD,
    dort fehlt der bidirektionalen Attention der Zukunftskontext) wartet bis
    zum naechsten Hop. Der Template-Pfad liegt in _display_loop_template.

    Wieder aktiv seit dem bestaetigten Musiktest: der gemessene Slash-Bass
    (bass.py, Tiefband jetzt aus der BTC-CQT gefaltet) und die Kontrollgitarre
    mit dem vollen BTC-Vokabular. Weiter bewusst stillgelegt:
      - Safe-Voicings / Powerchord-Rueckzug (harmony.safe_pitch_classes):
        es gibt keine Kandidatenliste mehr. Feld "v" sendet None.
      - Key-Prior (harmony.interpret_chord): Labels kommen fertig vom Modell.
        Die Tonart selbst laeuft weiter - fuer Schreibweise, Badge und
        Nashville-Stufen, seit dem Zwei-Skalen-Umbau (REPORT_key_window.md)
        mit 120-s-Histogramm plus Modulations- und Stille-Detektor.
      - ChordSmoother und Onset-Suche (find_onset_frame): Glaettung und
      	Grenzen kommen aus dem Modell (93-ms-Raster + Mindestdauer).

    `stop` (threading.Event) und `engine` wie im Template-Pfad.
    """
    from . import bass as bassmodul
    from .btc import (BTC_FRAME_SECONDS, BTCModel, features_from_audio,
                      fold_bass_chroma, fold_chroma, live_segments_from_labels,
                      refine_boundary)
    from .chords import SILENCE_RMS
    from .tonality import TwoScaleKeyEstimator, spell

    sr = args.samplerate
    window_frames = int(round(BTC_LIVE_WINDOW * sr))
    hop_frames = int(round(ANALYSIS_HOP * sr))
    model = BTCModel()
    # Zwei Zeitskalen: langes Histogramm fuer die Ruhe (an der Tonika haengen
    # Stufen und Schreibweise), kurzes als Modulations-/Songwechsel-Detektor.
    # Messwerte: tests/realaudio/REPORT_key_window.md.
    keys = TwoScaleKeyEstimator(ANALYSIS_HOP)
    # Die Bassspur muss die ganze Zeitleiste abdecken - vom Anzeige-Rueckblick
    # bis zur Analysefront (wie im Template-Pfad, nur im 93-ms-Raster; der
    # Randbeschnitt schrumpft mit, EDGE zaehlt Frames).
    bass_track = bassmodul.BassTrack(args.delay + BTC_LIVE_WINDOW + 4.0,
                                     frame_seconds=BTC_FRAME_SECONDS, edge=2)

    # Zeitleiste wie bisher: (Onset-Position im Stream, kanonischer Akkord).
    timeline: list[tuple[float, str]] = []
    previous_segments: list[tuple[float, str]] | None = None   # Debounce
    # Bereits verfeinerte Grenzen: jede neue Grenze wird genau EINMAL aufs
    # Audio-Ereignis gezogen (refine_boundary); danach haelt die Hysterese sie.
    refined_bounds: list[tuple[float, str]] = []
    lead = max(args.delay - BTC_EDGE_GUARD, 0.0)
    key_fed_until = 0.0

    print(f"Running: output delayed by {loop.delay_seconds:.1f}s. Ctrl+C quits.")
    if args.delay < BTC_EDGE_GUARD + 1.0:
        print("Note: --delay is tight; choose >= 3s for a useful lead.")
    print()

    debug_path = os.environ.get("JAMPILOT_DEBUG")
    debug = open(debug_path, "w") if debug_path else None
    if debug:
        debug.write(f"# latency in={loop._stream.latency[0]:.3f} "
                    f"out={loop._stream.latency[1]:.3f}\n")
        debug.write("# wall\twindow_end\tcurrent\taudible_pos\n")

    grid = None
    stillstand_bei, stillstand_seit = -1, time.monotonic()
    try:
        while not (stop is not None and stop.is_set()):
            captured = loop.captured_frames
            if captured != stillstand_bei:
                stillstand_bei, stillstand_seit = captured, time.monotonic()
            elif time.monotonic() - stillstand_seit > STREAM_STALL_TIMEOUT:
                raise StreamStalled(
                    f"No audio from the device for {STREAM_STALL_TIMEOUT:.0f}s "
                    f"- unplugged or switched off? JamPilot has stopped and "
                    f"restored your system sound; start it again once the "
                    f"device is back."
                )
            # Erst mit etwas Kontext lohnt ein Modelllauf.
            if captured < int(2.0 * sr):
                time.sleep(ANALYSIS_HOP)
                continue
            if grid is None:
                grid = captured // hop_frames * hop_frames
            if captured < grid:
                time.sleep(min(0.02, (grid - captured) / sr))
                continue

            window_end = captured // hop_frames * hop_frames
            grid = window_end + hop_frames
            audio = loop.audio_ending_at(window_end,
                                         min(window_frames, window_end))
            if audio is None:
                continue
            window_start = (window_end - len(audio)) / sr

            features = features_from_audio(audio, sr)
            labels = model.predict(features)
            bass_track.add(fold_bass_chroma(features), window_start)
            segments = live_segments_from_labels(labels, audio, sr,
                                                 offset=window_start,
                                                 silence_rms=SILENCE_RMS)

            audible_pos = loop.audible_position()
            horizon = window_end / sr - BTC_EDGE_GUARD
            _merge_model_segments(timeline, segments, audible_pos, horizon,
                                  previous_segments)
            previous_segments = segments

            # Frisch veroeffentlichte Grenzen einmalig aufs Audio-Ereignis
            # verfeinern (typisch 0-1 je Hop, ~100ms - dauert ein Hop mal
            # laenger, faellt nur ein Rasterpunkt aus, das Raster bleibt).
            freeze_edge = audible_pos + BTC_FREEZE_AHEAD
            for idx in range(1, len(timeline)):
                pos, name = timeline[idx]
                if pos <= freeze_edge:
                    continue
                if any(rn == name and abs(rp - pos) <= ONSET_HYSTERESIS
                       for rp, rn in refined_bounds):
                    continue
                pos = window_start + refine_boundary(
                    audio, sr, pos - window_start, timeline[idx - 1][1], name)
                pos = max(pos, timeline[idx - 1][0] + 0.05)
                if idx + 1 < len(timeline):
                    pos = min(pos, timeline[idx + 1][0] - 0.05)
                timeline[idx] = (pos, name)
                refined_bounds.append((pos, name))
            refined_bounds[:] = [(p, n) for p, n in refined_bounds
                                 if p > audible_pos - 2.0]
            lead = max(horizon - audible_pos, 0.0)
            if engine is not None:
                engine.lead = lead

            # Tonart (Schreibweise, Badge, Nashville-Stufen): gefaltetes
            # Chroma der NEU gesehenen Frames, damit kein Material doppelt in
            # die Statistik faellt. Auch Quasi-Stille geht hinein - sie ist
            # das Songwechsel-Signal des Zwei-Skalen-Estimators.
            folded = fold_chroma(features)
            first_new = max(0, int((key_fed_until - window_start) / BTC_FRAME_SECONDS) + 1)
            if first_new < len(folded):
                keys.add(folded[first_new:].mean(axis=0))
                key_fed_until = window_start + len(folded) * BTC_FRAME_SECONDS

            # Vergangenes behalten wir kurz - die Anzeige blendet Akkorde
            # hinter der JETZT-Linie noch aus.
            while len(timeline) > 1 and timeline[1][0] <= audible_pos - 2.0:
                timeline.pop(0)
            # Kontrollgitarre ohne Safe-Voicing-Filter (drittes Feld None):
            # sie schlaegt den VOLLEN Akkord an, auch dim7/sus/6 - die
            # Tonstrukturen kommen aus btc.BTC_CHORD_TONES.
            loop.set_control_timeline([
                (pos, name, None) for pos, name in timeline
            ])
            audible = "-"
            for pos, name in timeline:
                if pos > audible_pos:
                    break
                audible = name
            current = timeline[-1][1] if timeline else "-"

            # Bassnote je Segment aus dem Tiefband - der Vorlauf gilt fuer den
            # Bass genauso wie fuer den Akkord (wie im Template-Pfad).
            basslinie = _bass_per_segment(timeline, bass_track, window_end / sr)
            bass_jetzt = None
            for (pos, _), gemessen in zip(timeline, basslinie):
                if pos > audible_pos:
                    break
                bass_jetzt = gemessen

            if debug:
                debug.write(f"{time.time():.3f}\t{window_end / sr:.3f}\t"
                            f"{current}\t{audible_pos:.3f}\n")
                debug.flush()

            key = keys.key
            if broadcaster:
                # Protokoll unveraendert; [POC-BTC]: nur "v" (Safe-Voicings)
                # sendet noch None, siehe Docstring. "b" ist wieder gemessen.
                broadcaster.publish({
                    "t": round(audible_pos, 3),
                    "chords": [{"c": name, "at": round(pos, 3), "b": bassnote,
                                "v": None}
                               for (pos, name), bassnote in zip(timeline, basslinie)],
                    "lead": round(lead, 2),
                    "key": key.as_dict(keys.accidental) if key else None,
                    "muted": loop.muted,
                    "control_guitar": loop.control_guitar,
                })

            accidental = keys.accidental
            jetzt = bassmodul.slash(audible, bass_jetzt)
            sys.stdout.write(
                f"\r  In {max(lead, 0.0):3.1f}s: "
                f"{spell(current, accidental):<6s} "
                f"| Now playing: {spell(jetzt, accidental):<8s} "
                f"| Bass: {spell(bass_jetzt or '-', accidental):<3s} "
                f"| Key: {key.label_in(accidental) if key else '...':<9s}"
            )
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if debug:
            debug.close()
    if loop.xruns:
        print(f"Stream warnings: {loop.xruns} (last: {loop.last_status})")
    aussetzer = loop.capture_dropouts
    if aussetzer and any(aussetzer):
        print(f"Capture dropouts: {aussetzer[0]} under, {aussetzer[1]} over "
              f"(the two device clocks drifting apart)")


def _label_at(segments, t):
    """Das Etikett, das eine Segmentliste zum Zeitpunkt t behauptet."""
    name = None
    for pos, seg_name in segments:
        if pos > t:
            break
        name = seg_name
    return name


def _merge_model_segments(timeline, segments, audible_pos, horizon, previous=None):
    """BTC ist fuehrend: der unerhoerte Teil der Zeitleiste wird jedem Hop aus
    der frischen Modellausgabe neu aufgebaut.

    Regeln:
      - Gehoertes (Onset <= audible_pos) ist unantastbar - wie bisher.
      - Segmente jenseits `horizon` warten: am Fensterrand fehlt der
        bidirektionalen Attention der Zukunftskontext, dort flackern Labels.
      - Ein Segment, das an der Hoergrenze bereits laeuft, aendert das Etikett
        des Gehoerten nicht mehr; erst sein Nachfolger schreibt wieder.
        AUSNAHME: Sagt das Modell zwei Laeufe in Folge, dass an der Hoergrenze
        laengst ein ANDERER Akkord laeuft als der veroeffentlichte, bekommt die
        Zeitleiste eine Grenze an der Einfrierzone. Ohne diese Ausnahme bleibt
        eine in die Einfrierzone revidierte Grenze fuer immer verschluckt:
        spielt das Stueck danach lange denselben Akkord (D - A - D, und das
        zweite D kommt zu spaet oder uebermalt das A rueckwirkend), liefert
        kein spaeterer Lauf je wieder eine neue Grenze - die Anzeige zeigte
        das alte Etikett, bis das Stueck real wechselt.
      - Onset-Hysterese: Das CQT-Frameraster wandert pro Hop um eine NICHT
        ganze Framezahl (0.25s sind ~2.7 Frames), dieselbe Akkordgrenze landet
        also jedes Mal ein paar Millisekunden woanders. Ein bereits
        veroeffentlichtes Segment gleichen Namens in aehnlicher Lage behaelt
        deshalb seinen Onset - sonst springen die Chips der Vorlaufansicht
        viermal pro Sekunde (der Browser schluesselt sie nach Position+Name).
      - Einfrierzone: Auch noch nicht Gehoertes naeher als BTC_FREEZE_AHEAD an
        der hoerbaren Position bleibt stehen - diese Chips liest der Musiker
        gerade. Revisionen passieren nur weiter draussen.
      - Debounce, symmetrisch: Eine NEUE Grenze, die im vorigen Modelllauf
        (`previous`, ungeschnitten) nicht vorkam, wartet einen Hop. Und ein
        veroeffentlichter Chip VERSCHWINDET erst, wenn ihn auch der vorige
        Lauf nicht mehr sah - sonst blinkte er bei jeder Ein-Hop-Laune des
        Modells einen Viertelsekundenschlag weg und wieder her.
        Gemessen (Live-Simulation sting/peg, Chip-Schluessel wie im Browser):
        zusammen druecken die Regeln die Unruhe von 1.1 Chip-Wechseln je Hop
        auf 0.04-0.08, in der Nahzone (<2s vor der JETZT-Linie) von 49-64
        Ereignissen je 90s auf 6-7.
    """
    base = audible_pos + BTC_FREEZE_AHEAD
    published = []                      # bisher veroeffentlicht, noch formbar
    while timeline and timeline[-1][0] > base:
        published.append(timeline.pop())
    published.reverse()
    last = timeline[-1][1] if timeline else None

    for i, (pos, name) in enumerate(segments):
        if pos > horizon:
            break
        end = segments[i + 1][0] if i + 1 < len(segments) else float("inf")
        if end <= base:
            continue                    # vollstaendig hinter der Einfrierzone
        if pos <= base:
            if not timeline:            # Anlauf: noch nichts veroeffentlicht
                timeline.append((pos, name))
                last = name
            elif (name != last and previous is not None
                    and _label_at(previous, base) == name):
                # Revision in die Einfrierzone (siehe Docstring): Gehoertes
                # bleibt stehen, aber ab der Einfrierzone gilt das neue
                # Etikett - sonst kaeme es nie mehr auf die Anzeige.
                timeline.append((base, name))
                last = name
            continue
        if name == last:
            continue
        matched = False
        for j, (alt_pos, alt_name) in enumerate(published):
            # Asymmetrisch: eine veroeffentlichte Grenze wurde ggf. verfeinert
            # und liegt dann bis REFINE_BACK FRUEHER als die rohe Modellgrenze.
            if (alt_name == name
                    and -ONSET_HYSTERESIS <= pos - alt_pos
                    <= ONSET_HYSTERESIS + _REFINED_LOOKBACK):
                if not timeline or alt_pos > timeline[-1][0]:
                    pos = alt_pos       # bekannte Grenze: liegen lassen
                published.pop(j)        # jede alte Grenze zieht nur einmal
                matched = True
                break
        if not matched and previous is not None:
            if not any(prev_name == name and abs(prev_pos - pos) <= BTC_DEBOUNCE_MATCH
                       for prev_pos, prev_name in previous):
                continue                # Geist: erst wiedersehen, dann glauben
        timeline.append((pos, name))
        last = name

    # Entfernungs-Debounce: uebrige veroeffentlichte Chips, die der neue Lauf
    # nicht bestaetigt hat. Sah der VORIGE Lauf sie noch, bleiben sie einen
    # Hop stehen - erst zwei einige Laeufe duerfen einen Chip abraeumen.
    if previous is not None:
        for alt_pos, alt_name in published:
            # `>=`: auch die Korrektur-Grenze AN der Einfrierzone besetzt den
            # Platz - sonst blitzte der gerade revidierte Chip einen Hop auf.
            if any(-ONSET_HYSTERESIS <= pos - alt_pos
                   <= ONSET_HYSTERESIS + _REFINED_LOOKBACK
                   for pos, _ in timeline if pos >= base):
                continue                # Platz neu besetzt: das WAR die Revision
            if any(prev_name == alt_name and abs(prev_pos - alt_pos) <= BTC_DEBOUNCE_MATCH
                   for prev_pos, prev_name in previous):
                timeline.append((alt_pos, alt_name))
        timeline.sort()
        # Nach dem Einsortieren koennen Nachbarn gleichen Namens entstehen -
        # der fruehere gewinnt, der spaetere ist nur noch dieselbe Aussage.
        i = 1
        while i < len(timeline):
            if timeline[i][1] == timeline[i - 1][1]:
                timeline.pop(i)
            else:
                i += 1


def _display_loop_template(loop, args, broadcaster=None, stop=None, engine=None):
    """[POC-BTC] stillgelegt: Analyse ueber Template-Matching + Onset-Suche.

    Vollstaendig funktionsfaehig, aber nicht mehr verdrahtet - engine.py ruft
    _display_loop (BTC). Hier liegen die stillgelegten Faehigkeiten fuer die
    spaetere Reaktivierung: gemessener Slash-Bass, Safe-Voicings, Key-Prior,
    ChordSmoother, 23-ms-Onset-Suche.

    `stop` (threading.Event) und `engine` gibt es, seit der Betrieb abschaltbar
    ist: Laeuft die Schleife im Hintergrundthread des Kontrollfensters, kann sie
    nicht auf KeyboardInterrupt warten - der landet im Hauptthread bei Qt. Ohne
    `stop` verhaelt sich alles wie vorher (reiner CLI-Betrieb).
    """
    from . import bass as bassmodul
    from .chroma import FrameHistory, analyze_window, rms
    from .chords import SILENCE_RMS, ChordSmoother, match_chord
    from .harmony import interpret_chord, safe_pitch_classes
    from .tonality import KeyEstimator, spell

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
    # Juengste konservative Tonmenge je stabiler Akkord-ID. Die Timeline darf
    # String-basiert bleiben; Anzeige und Kontrollgitarre bekommen parallel die
    # Töne, die alle nahen Audio-Lesarten gemeinsam tragen.
    safe_by_chord: dict[str, tuple[int, ...]] = {}
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
    # Wachhund fuer ein Geraet, das verschwindet: USB-Kabel raus, Mischpult aus,
    # Karte im Suspend. PortAudio ruft den Callback dann einfach nicht mehr -
    # ohne Fehler, ohne Ende des Streams. Von aussen sieht das aus wie "laeuft":
    # Der Schalter steht auf An, die Umleitung steht, die Anzeige friert ein.
    # Genau das ist der Zustand, in dem der Nutzer den Rechner fuer kaputt haelt.
    # Also messen wir mit, ob ueberhaupt noch Frames eingehen.
    stillstand_bei, stillstand_seit = -1, time.monotonic()
    try:
        while not (stop is not None and stop.is_set()):
            captured = loop.captured_frames
            if captured != stillstand_bei:
                stillstand_bei, stillstand_seit = captured, time.monotonic()
            elif time.monotonic() - stillstand_seit > STREAM_STALL_TIMEOUT:
                raise StreamStalled(
                    f"No audio from the device for {STREAM_STALL_TIMEOUT:.0f}s "
                    f"- unplugged or switched off? JamPilot has stopped and "
                    f"restored your system sound; start it again once the "
                    f"device is back."
                )
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
                result = match_chord(analysis.chroma, cqt=analysis.cqt)
                raw = result.name
                history.add(analysis.frames, window_start)
                # Die bis hierhin stabile Tonart darf knappe Audio-Hypothesen
                # ordnen. Erst danach fliesst das aktuelle Fenster in die
                # Tonartschaetzung ein, damit kein Zirkelschluss entsteht.
                result = interpret_chord(result, keys.key)
                if result.is_chord:
                    safe_by_chord[result.name] = safe_pitch_classes(result)
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
                    if engine is not None:
                        engine.lead = lead      # das Fenster zeigt ihn an

            # Vergangenes behalten wir kurz - die Anzeige blendet Akkorde
            # hinter der JETZT-Linie noch aus.
            while len(timeline) > 1 and timeline[1][0] <= audible_pos - 2.0:
                timeline.pop(0)
            # Vollstaendiger Snapshot statt einzelner Trigger: Wird ein noch
            # nicht gehoertes Segment zurueckgenommen, verschwindet damit auch
            # sein Kontrollanschlag vor der Ausgabe.
            loop.set_control_timeline([
                (pos, name, safe_by_chord.get(name)) for pos, name in timeline
            ])
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
                    "chords": [{"c": name, "at": round(pos, 3), "b": bassnote,
                                "v": list(safe_by_chord.get(name, ())) or None}
                               for (pos, name), bassnote in zip(timeline, basslinie)],
                    "lead": round(lead, 2),
                    # Die Schreibweise kommt aus dem Schaetzer, nicht aus `key`:
                    # sie zieht traeger nach (siehe KeyEstimator.accidental).
                    "key": key.as_dict(keys.accidental) if key else None,
                    # Faehrt in jedem Zustand mit, nicht nur beim Umschalten: Ein
                    # Browser, der sich spaeter verbindet, muss die Stummschaltung
                    # sehen - sonst zeigt er munter Akkorde an, waehrend nichts zu
                    # hoeren ist, und der Fehler sitzt scheinbar im Audio.
                    "muted": loop.muted,
                    "control_guitar": loop.control_guitar,
                })

            # Im Terminal gibt es keinen Dialog - hier gilt immer die erkannte
            # Tonart, und solange keine feststeht, das Kreuz.
            accidental = keys.accidental
            # Der hoerbare Akkord mit gemessenem Bass: C/E statt C.
            jetzt = bassmodul.slash(audible, bass_jetzt)
            sys.stdout.write(
                f"\r  In {max(lead, 0.0):3.1f}s: "
                f"{spell(current or '-', accidental):<6s} "
                f"| Now playing: {spell(jetzt, accidental):<8s} "
                f"| Bass: {spell(bass_jetzt or '-', accidental):<3s} "
                f"| Key: {key.label_in(accidental) if key else '...':<9s}"
            )
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if debug:
            debug.close()
    if loop.xruns:
        print(f"Stream warnings: {loop.xruns} (last: {loop.last_status})")
    aussetzer = loop.capture_dropouts
    if aussetzer and any(aussetzer):
        print(f"Capture dropouts: {aussetzer[0]} under, {aussetzer[1]} over "
              f"(the two device clocks drifting apart)")


def _locate_onset(chord, previous, history, window_end, last_onset):
    """[POC-BTC] stillgelegt - nur noch vom Template-Pfad benutzt.

    Stream-Position, an der `chord` einsetzt.

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
        pooled = track.pooled_between(onset, ende)
        noten.append(bassmodul.name(bassmodul.slash_note(pooled, chord)))
    return noten


def _commit(timeline, onset, chord, audible_pos):
    """[POC-BTC] stillgelegt - nur noch vom Template-Pfad benutzt.

    Traegt `chord` in die Zeitleiste ein. Gibt den Onset zurueck, oder None,
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
    # NICHT required: Ohne Befehl laeuft `run`. Sonst ist die App per Doppelklick
    # unbenutzbar - ein Doppelklick uebergibt kein Argument, argparse bricht mit
    # "the following arguments are required: command" ab, und das Fenster, das
    # dem Nutzer alles erklaeren wuerde, geht nie auf. Fuer ein Programm, das als
    # fertige Binary ausgeliefert wird, ist "kein Argument" der HAEUFIGSTE Fall,
    # nicht ein Fehler.
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("devices", help="List audio devices").set_defaults(func=cmd_devices)
    sub.add_parser("selftest", help="Test detection without audio hardware").set_defaults(
        func=cmd_selftest
    )
    p_install = sub.add_parser(
        "install", help="Create a desktop launcher for double-clicking (Linux)")
    p_install.add_argument("--to", metavar="DIR", default=None,
                           help="Write JamPilot.desktop into DIR instead of the "
                                "application menu")
    p_install.add_argument("--remove", action="store_true",
                           help="Remove the launcher again")
    p_install.set_defaults(func=cmd_install)

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
                       help="Do not touch the system output; capture the "
                            "default input device instead")
    # Windows kann den stummen Umweg auf zwei Arten herstellen, und "auto"
    # entscheidet das per Messung. Die feste Wahl gibt es fuer den Fall, dass
    # die Messung auf einem Rechner das Falsche sagt - und fuer die Entwicklung,
    # in der man beide Wege durchspielen will, ohne einen Treiber zu
    # deinstallieren.
    p_run.add_argument("--route", choices=("auto", "mute", "cable"),
                       default="auto",
                       help="Windows only: how to silence the source - 'mute' "
                            "(no install needed), 'cable' (VB-CABLE), or "
                            "'auto' (default: measure and pick)")
    p_run.add_argument("--no-web", action="store_true",
                       help="Start without the web display")
    p_run.add_argument("--no-window", action="store_true",
                       help="No control window - terminal only (Ctrl+C quits)")
    p_run.add_argument("--port", type=_bounded(int, 1024, 65535), default=8765,
                       help="Port of the web display (1024..65535, default 8765)")
    p_run.add_argument("--samplerate", type=_bounded(int, 8000, 192000, " Hz"),
                       default=48000, help="Sample rate (8000..192000, default 48000)")
    p_run.set_defaults(func=cmd_run)

    # `run` ist der Standardbefehl - kein Argument bedeutet "starte das Programm".
    # Ein Doppelklick auf die Binary uebergibt naemlich gar nichts, und mit einem
    # erzwungenen Unterbefehl braeche argparse dort mit "the following arguments
    # are required: command" ab: Das Fenster, das dem Nutzer alles erklaeren
    # wuerde, ginge nie auf.
    #
    # Dasselbe gilt fuer Optionen OHNE Befehl. `jampilot --delay 6` ist der
    # Aufruf, den jeder tippt, und er scheiterte vorher an einer Meldung, die den
    # Grund nicht nennt ("invalid choice: '6'"). Steht vorn kein bekannter
    # Befehl, ist `run` gemeint.
    befehle = set(sub.choices)
    argumente = sys.argv[1:]
    if not argumente or (argumente[0] not in befehle
                         and argumente[0] not in ("-h", "--help")):
        argumente = ["run", *argumente]
    args = parser.parse_args(argumente)
    # Geraete duerfen Index oder Name sein.
    for attr in ("input", "output"):
        value = getattr(args, attr, None)
        if isinstance(value, str) and value.isdigit():
            setattr(args, attr, int(value))
    # BEVOR irgendjemand routing.backend() fragt: Die Antwort wird gemerkt, und
    # eine Wahl, die erst danach ankaeme, kaeme zu spaet.
    if getattr(args, "route", None):
        from . import routing

        routing.bevorzugen(args.route)
    args.func(args)


if __name__ == "__main__":
    main()

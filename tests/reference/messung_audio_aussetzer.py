"""Messung: Woher koennen Ton-Aussetzer kommen - Puffertiefe, GC, GIL, Hop?

Drei Messungen, alle ohne Audiogeraet lauffaehig (bis auf `latenz`), gedacht
fuer die ZIELMASCHINE (siehe docs/exploration/audio-aussetzer-analyse.md):

  python tests/reference/messung_audio_aussetzer.py latenz
      Oeffnet den Stream wie delay_stream (blocksize 2048, 48 kHz) mit
      latency="high" und mit numerischen Werten und druckt, wie viel Puffer
      PortAudio auf DIESEM Rechner daraus wirklich macht.

  python tests/reference/messung_audio_aussetzer.py schleife <wav> [sekunden]
      Laesst die ECHTE _display_loop gegen einen WAV-Fake-Stream in Echtzeit
      laufen. Daneben tickt ein Thread im Blocktakt (42.7 ms) wie der
      Audio-Callback und misst, wie spaet er drankommt (Scheduling + GIL +
      GC-Pausen). Alle GC-Sammlungen werden mit Dauer protokolliert.
      SATURATE=1 in der Umgebung: der Analysethread schlaeft nie zwischen den
      Hops (simuliert eine CPU, die das 250-ms-Raster nicht schafft).

  python tests/reference/messung_audio_aussetzer.py ueberlappung <wav>
      Hop-Anteile einzeln, seriell und in zwei Threads: wie viel der
      Verfeinerung (refine_boundary) laeuft GIL-frei parallel zu CQT+Modell?

Umgebungsvariablen wie OPENBLAS_NUM_THREADS=1 wirken wie ueblich vor dem
Import - so laesst sich der Einfluss der BLAS-Threads direkt vergleichen.
"""
import argparse
import gc
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SR = 48000
BLOCK = 2048 / SR


def _ms(x: float) -> str:
    return f"{1000 * x:6.1f}"


def _wav(pfad: str) -> np.ndarray:
    import librosa

    from jampilot.cli import _load_wav_mono

    samples, sr = _load_wav_mono(pfad)
    samples = samples.astype(np.float32)
    if sr != SR:
        samples = librosa.resample(samples, orig_sr=sr, target_sr=SR)
    return samples


class _CallbackTakt:
    """Ein Thread im Blocktakt: misst, wie spaet er jeweils drankommt."""

    def __init__(self):
        self.waits: list[tuple[float, float]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._laufen, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()

    def _laufen(self):
        nxt = time.perf_counter() + BLOCK
        while not self._stop.is_set():
            time.sleep(max(nxt - time.perf_counter(), 0))
            now = time.perf_counter()
            self.waits.append((now - nxt, now))
            nxt += BLOCK
            if now - nxt > 0.5:            # hoffnungslos hinterher: neu ankern
                nxt = now + BLOCK

    def bericht(self, t0: float, gcs=()):
        w = sorted(x[0] for x in self.waits)
        if not w:
            return
        print(f"Callback-Verspaetung n={len(w)}: median {_ms(w[len(w) // 2])} ms  "
              f"p99 {_ms(w[int(len(w) * .99)])} ms  max {_ms(w[-1])} ms  "
              f">20ms: {sum(1 for x in w if x > 0.02)}  "
              f">43ms (1 Block): {sum(1 for x in w if x > 0.043)}")
        for d, at in sorted(self.waits, reverse=True)[:5]:
            nahe = [(g, _ms(dd).strip()) for g, dd, t in gcs
                    if abs(t - at) < 0.1 and g >= 1]
            print(f"  +{_ms(d).strip()} ms bei t={at - t0:5.1f}s"
                  + (f"  GC(gen1/2) in +-100ms: {nahe}" if nahe else ""))


def cmd_latenz(_args):
    import sounddevice as sd

    for lat in ("high", 0.1, 0.15, 0.2, 0.3):
        try:
            s = sd.Stream(device=("default", "default") if sys.platform.startswith("linux")
                          else None, samplerate=SR, blocksize=2048, channels=2,
                          dtype="float32", latency=lat,
                          callback=lambda i, o, f, t, st: o.fill(0))
            s.start()
            time.sleep(0.3)
            print(f"latency={lat!r:7}: stream.latency (in, out) = "
                  f"{tuple(round(x, 3) for x in s.latency)}")
            s.stop()
            s.close()
        except Exception as exc:
            print(f"latency={lat!r}: FEHLER {exc}")


def cmd_schleife(args):
    from jampilot import cli, web

    samples = _wav(args.wav)

    class WavStream:
        delay_seconds, xruns, last_status = 5.0, 0, None
        capture_dropouts = None
        recording, record_paused, record_epoch = False, False, 0
        record_offset_seconds, record_capacity_seconds = 0.0, 0.0
        muted = control_guitar = False

        def __init__(self):
            self.t0 = time.perf_counter()

        @property
        def captured_frames(self):
            return min(int((time.perf_counter() - self.t0) * SR) // 2048 * 2048,
                       len(samples))

        def audible_position(self):
            return self.captured_frames / SR - self.delay_seconds

        heard_position = audible_position

        def audio_ending_at(self, ende, laenge):
            if ende > len(samples) or ende - laenge < 0:
                return None
            return samples[ende - laenge:ende].copy()

        def set_control_timeline(self, timeline):
            pass

    gcs: list[tuple[int, float, float]] = []
    beginn: dict[int, float] = {}

    def gc_protokoll(phase, info):
        gen = info["generation"]
        if phase == "start":
            beginn[gen] = time.perf_counter()
        else:
            jetzt = time.perf_counter()
            gcs.append((gen, jetzt - beginn[gen], jetzt))

    gc.callbacks.append(gc_protokoll)

    if os.environ.get("SATURATE"):
        echt_sleep = time.sleep
        # Nur die Hop-Pause der Schleife (<= 0.25 s) entfaellt; der Taktthread
        # wartet weiter.
        cli.time.sleep = lambda s: echt_sleep(0) if threading.current_thread().name == "analyse" else echt_sleep(s)

    takt = _CallbackTakt()
    takt.start()
    ns = argparse.Namespace(samplerate=SR, delay=5.0, record_buffer=0)
    halt = threading.Event()
    threading.Timer(args.sekunden, halt.set).start()
    t0 = time.perf_counter()
    stdout, sys.stdout = sys.stdout, open(os.devnull, "w")
    fehler = None

    def analyse():
        nonlocal fehler
        try:
            cli._display_loop(WavStream(), ns, web.ChordBroadcaster(), stop=halt)
        except Exception as exc:
            fehler = exc
            halt.set()

    thread = threading.Thread(target=analyse, name="analyse")
    thread.start()
    thread.join()
    sys.stdout = stdout
    takt.stop()
    if fehler:
        raise fehler

    print(f"Laufzeit {time.perf_counter() - t0:.0f} s, GC-Sammlungen: {len(gcs)}"
          f"  (SATURATE={'ja' if os.environ.get('SATURATE') else 'nein'}, "
          f"OPENBLAS_NUM_THREADS={os.environ.get('OPENBLAS_NUM_THREADS', '-')})")
    for gen in (0, 1, 2):
        d = sorted(x[1] for x in gcs if x[0] == gen)
        if d:
            print(f"  gen{gen}: n={len(d)} median {_ms(d[len(d) // 2])} ms"
                  f"  max {_ms(d[-1])} ms")
    # WANN die vollen Sammlungen fielen: nur beim Laden (erste Sekunden) oder
    # auch im laufenden Betrieb? Das entscheidet, ob sie eine Session treffen.
    volle = [f"t={t - t0:.1f}s ({_ms(d).strip()} ms)" for g, d, t in gcs if g == 2]
    if volle:
        print("  gen2-Zeitpunkte: " + ", ".join(volle))
    takt.bericht(t0, gcs)


def cmd_ueberlappung(args):
    from jampilot.btc import BTCModel, features_from_audio, refine_boundary

    samples = _wav(args.wav)
    audio = samples[20 * SR:30 * SR] if len(samples) >= 30 * SR else samples[:10 * SR]
    model = BTCModel()
    features_from_audio(audio, SR)
    refine_boundary(audio, SR, 6.0, "C", "G")

    def cqt_btc():
        model.predict(features_from_audio(audio, SR))

    def refine():
        refine_boundary(audio, SR, 6.0, "C", "G")

    def seriell():
        cqt_btc()
        refine()

    def parallel():
        t = threading.Thread(target=refine)
        t.start()
        cqt_btc()
        t.join()

    def zweimal_refine():
        t = threading.Thread(target=refine)
        t.start()
        refine()
        t.join()

    def dauer(fn, n=20):
        t = time.perf_counter()
        for _ in range(n):
            fn()
        return (time.perf_counter() - t) / n

    print(f"OPENBLAS_NUM_THREADS={os.environ.get('OPENBLAS_NUM_THREADS', '-')}")
    print(f"  cqt+btc            {_ms(dauer(cqt_btc))} ms")
    print(f"  refine             {_ms(dauer(refine))} ms")
    print(f"  beides seriell     {_ms(dauer(seriell))} ms")
    print(f"  beides 2 Threads   {_ms(dauer(parallel))} ms")
    print(f"  2x refine seriell  {_ms(2 * dauer(refine))} ms")
    print(f"  2x refine 2 Thr.   {_ms(dauer(zweimal_refine))} ms")


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("latenz")
    s = sub.add_parser("schleife")
    s.add_argument("wav")
    s.add_argument("sekunden", nargs="?", type=float, default=150.0)
    u = sub.add_parser("ueberlappung")
    u.add_argument("wav")
    args = p.parse_args()
    {"latenz": cmd_latenz, "schleife": cmd_schleife, "ueberlappung": cmd_ueberlappung}[args.cmd](args)


if __name__ == "__main__":
    main()

"""Bass-Stem fuer die Huellkurve: Open-Unmix (UMX-HQ, Target "bass") als
ONNX-Modell, hopweise im eigenen Thread.

Warum: Die Tiefband-Huellkurve (envelope.py, 30..250 Hz) zeigte jeden
Bassdrum-Schlag als Anschlag - die Kick liegt mit 50..100 Hz mitten im Bass,
im Frequenzbereich ist da nichts zu trennen. Ein Quellentrenner trennt im
ZEITVERHALTEN (gehaltener Ton mit Obertoenen gegen kurzen, breitbandigen
Knall) und nimmt die Kick heraus. Gemessen gegen echte Stems
(docs/exploration/bass-stem-huellkurve.md, tests/reference/messung_bass_stem.py):

  Korrelation der Huellkurve mit dem echten Bass-Stem, Mono-Eingang wie live
    Sailing to Philadelphia   Bandpass 0,30  ->  UMX-HQ 0,74
    Echoes                    Bandpass 0,81  ->  UMX-HQ 0,93
  Kick-Uebersprechen (Korrelation des Rests mit dem Drum-Stem, Echoes)
                              Bandpass 0,59  ->  UMX-HQ 0,13

Das Modell (Stoeter et al., JOSS 2019; https://github.com/sigsep/open-unmix-pytorch)
ist ein 3-Lagen-BLSTM ueber dem Betragsspektrogramm (STFT 4096/1024 bei
44,1 kHz, stereo). Exportiert mit dynamischer Framezahl und auf int8
quantisiert (9 MB statt 36, gleiche Messwerte): tests/reference/export_umx_bass.py.

Betrieb: ein Lauf je Analyse-Hop (0,25 s) auf dem juengsten Hop des Fensters,
mit CONTEXT_BACK Sekunden Kontext davor und CONTEXT_FRONT danach - das BLSTM
sieht in beide Richtungen, ohne Kontext franst der Rand aus. Gemessen ist
hopweise (1,0 s / 0,5 s Kontext) so gut wie am Stueck, ~90 ms je Hop auf einem
Kern eines Xeon E5 v2 von 2013; das Akkordmodell braucht im selben Hop ~60 ms.
Deshalb wie das Beat-Modell (beats.py) in einem EIGENEN Thread mit einem
ORT-Thread. Kommt der Worker nicht nach, fasst er alle wartenden Hops zu
EINEM Lauf zusammen (der Kontext zaehlt dann nur einmal) - so holt er auf,
statt Loecher zu lassen.

Der Stem reicht damit bis CONTEXT_FRONT plus eine Hop-Laufzeit hinter die
Analysefront; bei --delay 5 ist das gut 4 s vor JETZT, die Spur zeigt 2,8 s.
Die Huellkurve (envelope.py) fuehrt die Bass-Kurve getrennt vom Mix, sie darf
hinter ihm zurueckliegen.
"""

from __future__ import annotations

import os
import queue
import threading

import numpy as np

MODEL_PATH = os.path.join(os.path.dirname(__file__), "data", "umxhq_bass_int8.onnx")
MODEL_SR = 44100
N_FFT = 4096
HOP = 1024
CONTEXT_BACK = 1.0        # s Kontext vor dem Kern
CONTEXT_FRONT = 0.5       # s Kontext hinter dem Kern
MAX_BACKLOG = 4.0         # s wartender Kern, dann faellt das Aelteste weg


def onnxruntime_available() -> bool:
    import importlib.util
    return importlib.util.find_spec("onnxruntime") is not None


class BassStemModel:
    """Das ONNX-Modell: Eingabe `mag` (1, 2, 2049, T) float32 Betragsspektrum,
    Ausgabe `bass_mag` dieselbe Form, T dynamisch. STFT und Rueckweg in scipy,
    Maske = Schaetzung / Mix auf das komplexe Spektrum des Mixes."""

    def __init__(self, path: str = MODEL_PATH, threads: int = 1):
        import onnxruntime as ort
        from .beats import _providers
        providers = _providers(ort)
        if len(providers) > 1 and hasattr(ort, "preload_dlls"):
            try:
                ort.preload_dlls()
            except Exception:
                pass
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.log_severity_level = 3
        self._session = ort.InferenceSession(path, options, providers=providers)
        self._input = self._session.get_inputs()[0].name
        self.provider = self._session.get_providers()[0]

    def separate(self, audio: np.ndarray, samplerate: int) -> np.ndarray:
        """Mono-Audio -> Bass-Stem, mono, gleiche Rate und Laenge."""
        from scipy.signal import istft, stft
        y = np.asarray(audio, dtype=np.float32)
        if y.ndim > 1:
            y = y.mean(axis=1)
        n = len(y)
        if samplerate != MODEL_SR:
            import librosa
            y = librosa.resample(y, orig_sr=samplerate, target_sr=MODEL_SR)
        # Das Modell ist stereo trainiert; Mono geht als zwei gleiche Kanaele
        # hinein (so macht es auch openunmix.predict).
        y2 = np.stack([y, y])
        _, _, Z = stft(y2, fs=MODEL_SR, nperseg=N_FFT, noverlap=N_FFT - HOP,
                       window="hann", boundary="zeros", padded=True)
        # scipy teilt durch die Fenstersumme (N_FFT/2 beim Hann); das Modell
        # kennt die unskalierte torch-STFT.
        mag = (np.abs(Z) * (N_FFT / 2)).astype(np.float32)[None]
        est = self._session.run(None, {self._input: mag})[0][0]
        mask = est / (mag[0] + 1e-8)
        _, out = istft(Z * mask, fs=MODEL_SR, nperseg=N_FFT, noverlap=N_FFT - HOP,
                       window="hann", input_onesided=True, boundary=True)
        bass = out.mean(axis=0)
        if samplerate != MODEL_SR:
            bass = librosa.resample(bass.astype(np.float32), orig_sr=MODEL_SR,
                                    target_sr=samplerate)
        if len(bass) < n:
            bass = np.pad(bass, (0, n - len(bass)))
        return bass[:n].astype(np.float32)


def assemble(pieces: list[tuple[int, np.ndarray]]) -> tuple[int, np.ndarray]:
    """Ueberlappende Stuecke (Start-Frame, Samples) zu EINEM zusammenhaengenden
    Puffer; Luecken dazwischen bleiben Nullen. Spaetere Stuecke ueberschreiben
    fruehere an gleicher Stelle (dieselben Samples aus demselben Stream)."""
    start = min(s for s, _ in pieces)
    end = max(s + len(a) for s, a in pieces)
    out = np.zeros(end - start, dtype=np.float32)
    for s, a in pieces:
        out[s - start: s - start + len(a)] = a
    return start, out


class BassStemWorker:
    """Trennt im eigenen Thread. Der Analyse-Thread ruft je Hop `submit()`
    mit dem Audiostueck um den Kern (Kontext davor und dahinter) und `poll()`;
    beides kehrt sofort zurueck. Ergebnisse sind (Bass-Samples des Kerns,
    End-Frame des Kerns) - fertig fuer Envelope.add_bass()."""

    def __init__(self, model_factory=BassStemModel):
        self.ready = False
        self.error: str | None = None
        self.provider: str | None = None
        self.runs = 0
        self.dropped = 0
        self._factory = model_factory
        self._pending: list[tuple] = []           # (audio, sr, start, core_start, core_end)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._results: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._work, name="bass-stem", daemon=True)
        self._thread.start()

    @classmethod
    def create(cls) -> "BassStemWorker | None":
        """Der Worker, wenn onnxruntime und das Modell da sind - sonst None,
        und die Huellkurve nimmt den Bandpass wie zuvor."""
        if not onnxruntime_available() or not os.path.exists(MODEL_PATH):
            return None
        return cls()

    def submit(self, audio: np.ndarray, samplerate: int, start_frame: int,
               core_start: int, core_end: int) -> bool:
        """`audio` beginnt bei Stream-Frame `start_frame`; getrennt und
        zurueckgegeben wird nur der Kern [core_start, core_end)."""
        if self.error is not None:
            return False
        with self._lock:
            self._pending.append((np.asarray(audio, dtype=np.float32), samplerate,
                                  start_frame, core_start, core_end))
            # Rueckstau begrenzen: aeltesten Kern opfern (wird in der Kurve
            # zu Nullen), damit der Worker den Anschluss nicht verliert.
            while (self._pending[-1][4] - self._pending[0][3]
                   > MAX_BACKLOG * samplerate and len(self._pending) > 1):
                self._pending.pop(0)
                self.dropped += 1
        self._wake.set()
        return True

    def pending(self) -> int:
        with self._lock:
            return len(self._pending)

    def poll(self) -> list[tuple[np.ndarray, int]]:
        """Fertige Kerne (Bass-Samples, End-Frame), aelteste zuerst."""
        out = []
        while True:
            try:
                out.append(self._results.get_nowait())
            except queue.Empty:
                return out

    def stop(self) -> None:
        """Worker anhalten und auf ihn warten (s. BeatTracker.stop: eine
        ORT-Session, die beim Prozessende noch rechnet, stirbt laut)."""
        self._stop.set()
        self._wake.set()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=3.0)

    def _work(self) -> None:
        try:
            model = self._factory()
            self.provider = getattr(model, "provider", None)
            self.ready = True
        except Exception as exc:
            self.error = str(exc) or type(exc).__name__
            return
        while not self._stop.is_set():
            self._wake.wait()
            self._wake.clear()
            while not self._stop.is_set():
                with self._lock:
                    jobs, self._pending = self._pending, []
                if not jobs:
                    break
                # Alle wartenden Hops in EINEM Lauf: Audio zusammensetzen,
                # trennen, den gemeinsamen Kern zurueckgeben.
                sr = jobs[0][1]
                start, audio = assemble([(j[2], j[0]) for j in jobs])
                core_start = min(j[3] for j in jobs)
                core_end = max(j[4] for j in jobs)
                try:
                    bass = model.separate(audio, sr)
                except Exception as exc:
                    self.error = str(exc) or type(exc).__name__
                    return
                self.runs += 1
                lo, hi = core_start - start, core_end - start
                self._results.put((bass[max(lo, 0):hi], core_end))
        del model

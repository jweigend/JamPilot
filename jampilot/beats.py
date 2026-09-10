"""Beat und Takt: Beat This! (small0) als ONNX-Modell, Raster ueber Fenster,
Takt-Phase mit Hysterese - und der Viertel-Snap fuer die Akkordgrenzen.

Herkunft und Zahlen: docs/exploration/beat-tracking-ergebnisse.md (Uebergabe
aus JamPilotML, 2026-09-10). Kurz: Beat This! (Foscarin et al., ISMIR 2024),
Checkpoint small0, liefert auf 169 Beatles-Titeln Beat-F 0,99 bei 8 ms
Phasenfehler und ohne Oktavfehler - librosas Tracker traf 23-54 %. Das
Raster traegt damit, was tempo-und-takt.md §4.4 als groessten Timing-Hebel
gemessen hat: Akkordgrenzen auf das naechste Viertel geschnappt halbieren
den Grenzfehler (median 103 -> 52 ms, Anteil <= 93 ms 46 -> 76 %).

Der Preis ist die CPU: ~400 ms je 10-s-Fenster auf einem Kern (Haswell),
und daran aendern int8/Fusion nichts (Frontend-Attention). Deshalb laeuft
das Modell in einem EIGENEN Thread mit einem ORT-Thread, einmal je Sekunde
(BEAT_INTERVAL), nicht im 250-ms-Hop des Akkordmodells.

Drei Teile:

  1. Vor- und Nachverarbeitung des Modells (log_mel, pad_chunk, pick_peaks) -
     exakt wie beat_this in Torch, gegen das Original verifiziert
     (tests/test_beats.py, Golden-Fixture tests/data/beat_golden_window.npz).
  2. BeatGrid: das Raster ueber Fenster hinweg. Aus jedem 10-s-Fenster
     werden nur Beats aus der Commit-Zone [Ende-3 s, Ende-1 s) uebernommen
     (Randframes sind unsicher), Beats zweier Fenster < 60 ms auseinander
     gemittelt; was die Commit-Grenze passiert, wird genau einmal als Beat
     ausgeliefert (publish-once, wie die Akkord-Events). Die Eins kommt aus
     dem Modell, die Takt-Phase wird ueber Fenster gehalten (Hysterese).
  3. BeatTracker: der Thread drumherum. Bekommt Audiofenster, liefert
     Beats; das Raster selbst wird nur vom Analyse-Thread angefasst.

Vorverarbeitung exakt wie beat_this.preprocessing.LogMelSpect:
  torchaudio.MelSpectrogram(sr 22050, n_fft 1024, hop 441, f_min 30,
  f_max 11000, n_mels 128, mel_scale "slaney", normalized "frame_length",
  power 1) -> log1p(1000 * mel)
"frame_length" heisst: Betragsspektrum durch sqrt(n_fft) geteilt (nicht durch
die Fensternorm). Hann-Fenster, center=True mit Reflect-Padding, Mel-Filterbank
Slaney-Skala ohne Flaechennormierung (norm=None).

Nachverarbeitung wie beat_this.model.postprocessor.Postprocessor("minimal"):
lokale Maxima im Fenster +-3 Frames (70 ms), Logit > 0, benachbarte Peaks
(Abstand <= 1 Frame) zum Mittelwert zusammengezogen, Downbeats die Beats,
die auch Downbeat-Peak sind - sonst der naechste Beat-Peak.
"""

from __future__ import annotations

import bisect
import importlib.util
import os
import queue
import statistics
import threading
from collections import Counter

import numpy as np

SR = 22050
N_FFT = 1024
HOP = 441                      # 20 ms -> 50 Frames/s
FPS = SR / HOP
N_MELS = 128
F_MIN, F_MAX = 30.0, 11000.0
LOG_MULTIPLIER = 1000.0
BORDER = 6                     # Randframes je Seite, die das Modell verwirft
PEAK_HALF_WIDTH = 3            # +-3 Frames = +-70 ms wie im Original

MODEL_PATH = os.path.join(os.path.dirname(__file__), "data", "beat_this_small0.onnx")

# Betrieb (beat-tracking-ergebnisse.md §4, alles gemessen):
BEAT_WINDOW = 10.0       # 5 s halten die Beats, verlieren aber die Eins (-0,145)
BEAT_INTERVAL = 1.0      # ein Lauf je Sekunde; jede Stelle sehen zwei Fenster
ZONE_BACK = 3.0          # Commit-Zone [Ende-3, Ende-1): Randframes sind unsicher,
ZONE_FRONT = 1.0         # 1 s Vorlauf reicht fuer den Commit ~2 s hinter der Front
MERGE_TOLERANCE = 0.06   # zwei Fenster einigen sich in 93 % auf den Frame genau
MIN_BEAT_GAP = 0.15      # 400 bpm - darueber ist es kein Beat mehr

# Konfidenz-Gates (tempo-und-takt.md §6, Regel 1: kein Strich ist besser als
# ein falscher). Ein Beat, dessen Abstand zum letzten ANGENOMMENEN Beat mehr
# als so viel vom lokalen Median abweicht, bekommt keinen Strich - Rubato und
# Modell-Launen fallen so durch, und ein Geisterbeat reisst den naechsten
# echten nicht mit. Ein doppelter Abstand ist ein vom Modell verpasster
# Schlag (Beat-F 0,99, kommt vor): angenommen, der Takt zaehlt einen weiter.
# Nach einer echten Pause (Abstand > BREAK_FACTOR Median) beginnt die
# Taktzaehlung neu.
TEMPO_TOLERANCE = 0.30
MISSED_BEAT_TOLERANCE = 0.30
BREAK_FACTOR = 2.5
# Die Eins: Ein Modell-Votum wird angenommen, wenn es (bis auf einen Schlag)
# dort liegt, wo der gehaltene Takt sie erwartet - sonst erst, wenn ein zweites
# Votum einen Takt spaeter dieselbe andere Phase sagt (Hysterese gegen die
# Halbtakt-Ambiguitaet). Fehlt das Votum, wird die Eins hoechstens so viele
# Takte fortgeschrieben, dann ist der Takt "verloren" und es gibt nur noch
# Beat-Striche, bis das Modell neu ankert.
MAX_EXTRAPOLATED_BARS = 2
BAR_MEMORY = 4           # Taktlaengen, aus denen das Metrum gemittelt wird


# ---------------------------------------------------------------------------
# 1. Rund um das Modell: Log-Mel, Padding, Peak-Picking


_mel_fb = None


def mel_filterbank() -> np.ndarray:
    """(N_MELS, N_FFT//2+1) - Slaney-Skala, keine Flaechennormierung."""
    global _mel_fb
    if _mel_fb is None:
        import librosa
        _mel_fb = librosa.filters.mel(sr=SR, n_fft=N_FFT, n_mels=N_MELS,
                                      fmin=F_MIN, fmax=F_MAX, htk=False,
                                      norm=None).astype(np.float32)
    return _mel_fb


def log_mel(samples: np.ndarray) -> np.ndarray:
    """Mono-Samples (22050 Hz) -> Log-Mel-Frames (T, 128), T = len//441 + 1."""
    import librosa
    y = np.asarray(samples, dtype=np.float32)
    window = np.hanning(N_FFT + 1)[:-1].astype(np.float32)   # torch.hann_window
    spec = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP, window=window,
                               center=True, pad_mode="reflect"))
    spec = spec.astype(np.float32) / np.float32(np.sqrt(N_FFT))  # "frame_length"
    mel = mel_filterbank() @ spec                              # (128, T)
    return np.log1p(LOG_MULTIPLIER * mel).T.astype(np.float32)


def pad_chunk(spect: np.ndarray, border: int = BORDER) -> np.ndarray:
    """Nullen an beiden Enden, wie beat_this.inference.split_piece."""
    return np.pad(spect, ((border, border), (0, 0)))


def strip_border(logits: np.ndarray, border: int = BORDER) -> np.ndarray:
    return logits[border:-border] if border else logits


def _local_maxima(x: np.ndarray, half: int = PEAK_HALF_WIDTH) -> np.ndarray:
    """Frames, an denen x das Maximum seiner +-half-Umgebung ist und x > 0.
    Ersetzt F.max_pool1d(x, 2*half+1, 1, half) != x (Rand mit -inf)."""
    padded = np.concatenate([np.full(half, -np.inf), x, np.full(half, -np.inf)])
    windows = np.lib.stride_tricks.sliding_window_view(padded, 2 * half + 1)
    return np.flatnonzero((x == windows.max(axis=1)) & (x > 0))


def _deduplicate(peaks: np.ndarray, width: int = 1) -> np.ndarray:
    """Gruppen benachbarter Peaks (Abstand <= width) -> Mittelwert der
    Indizes, wie beat_this.model.postprocessor.deduplicate_peaks."""
    out, prev, count = [], None, 0
    for p in map(int, peaks):
        if prev is not None and p - prev <= width:
            count += 1
            prev += (p - prev) / count
        else:
            if prev is not None:
                out.append(prev)
            prev, count = p, 1
    if prev is not None:
        out.append(prev)
    return np.asarray(out, dtype=np.float64)


def pick_peaks(beat_logits: np.ndarray, downbeat_logits: np.ndarray,
               fps: float = FPS) -> tuple[np.ndarray, np.ndarray]:
    """Logits (T,) -> (Beat-Zeiten s, Downbeat-Zeiten s) wie Postprocessor
    "minimal": Downbeat-Peaks werden auf den naechsten Beat-Peak gelegt,
    Beats ohne Downbeat-Peak bleiben Beats."""
    beat_frames = _deduplicate(_local_maxima(np.asarray(beat_logits)))
    down_frames = _deduplicate(_local_maxima(np.asarray(downbeat_logits)))
    if len(beat_frames) == 0:
        return np.zeros(0), np.zeros(0)
    if len(down_frames):
        # Downbeats auf den naechsten Beat ziehen (Original: jeder Downbeat-
        # Peak wird dem naechstgelegenen Beat-Peak zugeordnet, Duplikate raus)
        idx = np.abs(beat_frames[None, :] - down_frames[:, None]).argmin(axis=1)
        down_frames = np.unique(beat_frames[idx])
    return beat_frames / fps, down_frames / fps


def onnxruntime_available() -> bool:
    return importlib.util.find_spec("onnxruntime") is not None


def _providers(ort) -> list[str]:
    """Ausfuehrungs-Provider in Vorzugsreihenfolge: was die Plattform an
    Beschleunigung hat (CUDA, ROCm, DirectML, CoreML, OpenVINO), CPU immer
    als Rueckfall. Gemessen: CPU 415 ms je Fenster, CUDA 10 ms (RTX 2080
    SUPER, onnxruntime-gpu 1.30) - beat-tracking-ergebnisse.md §3/§8.
    TensorRT steht bewusst nicht dabei: Das GPU-Paket MELDET ihn als
    verfuegbar, die TensorRT-Bibliotheken fehlen aber ohne eigene
    Installation, und ORT bricht dann laut ab und probiert erst danach
    CUDA - das bringt bei 10 ms nichts mehr ein."""
    preferred = ["CUDAExecutionProvider", "ROCMExecutionProvider",
                 "DmlExecutionProvider", "CoreMLExecutionProvider",
                 "OpenVINOExecutionProvider"]
    available = set(ort.get_available_providers())
    return [p for p in preferred if p in available] + ["CPUExecutionProvider"]


class BeatModel:
    """Das ONNX-Modell: Eingabe `spect` (1, T, 128) float32, Ausgaben `beat`
    und `downbeat` (1, T) Logits, T dynamisch. Ein ORT-Thread - im eigenen
    Thread reicht das, und mehr griffe nach allen Kernen und stoerte den
    Audio-Callback."""

    def __init__(self, path: str = MODEL_PATH, threads: int = 1):
        import onnxruntime as ort
        providers = _providers(ort)
        if len(providers) > 1 and hasattr(ort, "preload_dlls"):
            # GPU-Paket: Die CUDA/cuDNN-Bibliotheken kommen als pip-Pakete
            # (onnxruntime-gpu[cuda,cudnn]) und liegen NICHT auf dem
            # Bibliothekspfad - ohne dieses Vorladen faellt ORT unter Linux
            # mit "libcublasLt.so: cannot open" auf die CPU zurueck.
            # Gemessen (RTX 2080 SUPER): 10 ms je Fenster statt 415 auf CPU.
            try:
                ort.preload_dlls()
            except Exception:
                pass                      # dann eben CPU - ORT meldet es unten
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        # Nur Fehler ins Terminal: ORT warnt sonst je Sitzung ueber Memcpy-
        # Knoten und ScatterND - beides bekannt, beides ohne Folgen.
        options.log_severity_level = 3
        self._session = ort.InferenceSession(path, options, providers=providers)
        self._input = self._session.get_inputs()[0].name
        self.provider = self._session.get_providers()[0]

    def run(self, samples: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Ein Fenster (22050 Hz mono) -> (Beats s, Downbeats s) relativ zum
        Fensteranfang."""
        chunk = pad_chunk(log_mel(samples))[None].astype(np.float32)
        beat, down = self._session.run(None, {self._input: chunk})
        return pick_peaks(strip_border(beat[0]), strip_border(down[0]))


# ---------------------------------------------------------------------------
# 2. Das Raster ueber Fenster hinweg


class BeatGrid:
    """Beats in Stream-Sekunden, ueber Fenster gesammelt und publish-once
    ausgeliefert.

    `absorb()` nimmt die Beats eines Fensters aus der Commit-Zone auf und
    mittelt sie mit schon bekannten (< MERGE_TOLERANCE); die Eins-Voten
    werden gezaehlt. `commit(frontier)` liefert alles unter der Commit-Grenze
    genau einmal als Beat {"at", "n"} in `events` aus - n ist die Schlag-
    nummer im Takt (1 = Eins), 0 = Takt unbekannt. Ein Beat, der einmal in
    `events` steht, wird nie mehr angefasst - dieselbe Zusage wie beim
    EventLedger, und aus demselben Grund: ein wandernder Strich waere
    Flackern durch die Hintertuer.

    `snap(pos)` ist der Viertel-Snap fuer die Akkordgrenzen: der naechste
    Beat, wenn einer in Reichweite (gut ein halber Schlag) liegt.
    """

    def __init__(self):
        self.events: list[dict] = []
        self._open: list[list] = []         # [at, eins_voten, voten], sortiert
        # Tempo-Gate: Abstaende der zuletzt gesehenen Rasterbeats (auch der
        # verworfenen - sonst kaeme das Raster nach einem Tempowechsel nie
        # wieder auf die Fuesse).
        self._last_seen: float | None = None
        self._intervals: list[float] = []
        self._dropped = 0                   # verworfene Beats seit dem letzten Strich
        # Takt: gehaltenes Metrum (Schlaege je Takt), Zaehler seit der letzten
        # angenommenen Eins, Fortschreibungen in Folge, Index des zuletzt
        # verworfenen Eins-Votums (fuer die Hysterese).
        self._meter: int | None = None
        self._bar_lengths: list[int] = []
        self._since_down: int | None = None
        self._extrapolated = 0
        self._index = 0
        self._last_rejected: int | None = None

    # -- Aufnahme ----------------------------------------------------------

    def absorb(self, beats: np.ndarray, downbeats: np.ndarray,
               window_start: float, window_end: float) -> None:
        """Beats eines Fensters (relativ zum Fensteranfang) aufnehmen - nur
        aus der Commit-Zone [Ende-ZONE_BACK, Ende-ZONE_FRONT)."""
        lo, hi = window_end - ZONE_BACK, window_end - ZONE_FRONT
        downs = np.asarray(downbeats, dtype=np.float64)
        # Hinter dem letzten COMMITTETEN Beat ist alles willkommen - auch
        # hinter der Commit-Grenze: Der Worker liefert ein Fenster ~0,5 s
        # nach dem Abgeben, auf langsamen Rechnern spaeter, und die Grenze
        # rueckt derweil vor. Ein spaeter Beat wird beim naechsten Commit
        # nachgeliefert (ein Strich, der etwas naeher an der JETZT-Linie
        # einsteigt) statt verworfen.
        floor = self.events[-1]["at"] if self.events else float("-inf")
        for b in np.asarray(beats, dtype=np.float64):
            at = window_start + float(b)
            if not (lo <= at < hi) or at <= floor:
                continue
            is_down = bool(len(downs)) and bool(np.min(np.abs(downs - b)) < 1e-6)
            i = bisect.bisect_left([o[0] for o in self._open], at - MERGE_TOLERANCE)
            if i < len(self._open) and abs(self._open[i][0] - at) <= MERGE_TOLERANCE:
                entry = self._open[i]
                entry[0] = (entry[0] * entry[2] + at) / (entry[2] + 1)
                entry[1] += int(is_down)
                entry[2] += 1
            else:
                self._open.insert(i, [at, int(is_down), 1])

    # -- Commit ------------------------------------------------------------

    def commit(self, frontier: float) -> list[dict]:
        """Alles unter der Commit-Grenze genau einmal ausliefern; liefert die
        in diesem Aufruf neuen Beats."""
        fresh = []
        while self._open and self._open[0][0] <= frontier:
            at, down_votes, votes = self._open.pop(0)
            beat = self._commit_one(at, down_votes / votes)
            if beat is not None:
                fresh.append(beat)
        return fresh

    def _commit_one(self, at: float, downbeat_share: float) -> dict | None:
        # Der lokale Beat-Abstand kommt aus ALLEN gesehenen Beats (auch den
        # verworfenen - sonst kaeme das Raster nach einem Tempowechsel nie
        # wieder auf die Fuesse); der Median ueber sechs vertraegt zwei
        # Ausreisser.
        reference = self.interval()
        if self._last_seen is not None:
            self._intervals.append(at - self._last_seen)
            del self._intervals[:-6]
        self._last_seen = at
        if self.events and at - self.events[-1]["at"] < MIN_BEAT_GAP:
            return None
        skipped = 0
        if reference is not None and self.events:
            ratio = (at - self.events[-1]["at"]) / reference
            if ratio > BREAK_FACTOR:
                self._since_down = None            # Pause: Takt neu zaehlen
                self._extrapolated = 0
                self._last_rejected = None
            elif abs(ratio - 2.0) <= MISSED_BEAT_TOLERANCE and not self._dropped:
                skipped = 1                        # das Modell hat einen verpasst
            elif abs(ratio - 1.0) > TEMPO_TOLERANCE:
                self._dropped += 1                 # kein Strich - und der
                return None                        # doppelte Abstand danach ist
                                                   # kein verpasster Schlag
        self._dropped = 0
        beat = {"at": round(at, 3),
                "n": self._bar_position(downbeat_share >= 0.5, skipped)}
        self.events.append(beat)
        return beat

    def _bar_position(self, candidate: bool, skipped: int = 0) -> int:
        """Schlagnummer im Takt fuer den naechsten Beat - Takt-Phase halten.
        `skipped`: Schlaege, die das Modell davor verpasst hat (zaehlen mit)."""
        self._index += 1 + skipped
        meter = self._meter
        if self._since_down is None:
            if candidate:
                self._since_down = 0
                self._last_rejected = None
                return 1
            return 0
        count = self._since_down + 1 + skipped     # Schlaege seit der Eins
        if candidate and count >= 2:
            expected = meter is None or count >= meter - 1
            if not expected and self._last_rejected is not None \
                    and abs((self._index - self._last_rejected) - meter) <= 1:
                expected = True                    # zweites Votum, gleiche Phase
                self._bar_lengths.clear()          # neue Phase, altes Metrum
            if expected:
                if meter is None or count >= meter - 1:
                    self._bar_lengths.append(count)
                    del self._bar_lengths[:-BAR_MEMORY]
                    self._update_meter()
                self._since_down = 0
                self._extrapolated = 0
                self._last_rejected = None
                return 1
            self._last_rejected = self._index
        self._since_down = count
        if meter is None:
            return count + 1
        if count == meter and self._extrapolated < MAX_EXTRAPOLATED_BARS:
            self._extrapolated += 1                # Eins fortschreiben
            self._since_down = 0
            return 1
        return count + 1 if count < meter else 0   # 0: Takt verloren

    def _update_meter(self) -> None:
        if len(self._bar_lengths) < 2:
            return
        (length, n), *rest = Counter(self._bar_lengths).most_common()
        if n >= 2 and 2 <= length <= 12 and not (rest and rest[0][1] == n):
            self._meter = length

    # -- Auskunft ----------------------------------------------------------

    def interval(self) -> float | None:
        """Lokaler Beat-Abstand (Median der letzten Abstaende) - None, solange
        das Raster zu kurz ist."""
        recent = self._intervals[-4:]
        return statistics.median(recent) if len(recent) >= 3 else None

    def tempo(self) -> float | None:
        interval = self.interval()
        return 60.0 / interval if interval else None

    def snap(self, pos: float) -> float | None:
        """Viertel-Snap: der naechste bekannte Beat, wenn er in Reichweite
        liegt (gut ein halber Schlag - ohne Schwelle innerhalb des Rasters,
        aber nicht ueber Loecher hinweg). None, wenn kein Raster da ist."""
        candidates = [e["at"] for e in self.events[-16:]] + [o[0] for o in self._open]
        if not candidates:
            return None
        nearest = min(candidates, key=lambda at: abs(at - pos))
        interval = self.interval()
        reach = 0.6 * interval if interval else 0.5
        return nearest if abs(nearest - pos) <= reach else None

    def window(self, lo: float, hi: float) -> list[dict]:
        return [e for e in self.events if lo <= e["at"] <= hi]

    def prune(self, heard_pos: float, rueckhalt: float = 2.0) -> None:
        """Vergangenes vergessen - gemessen an der HOERBAREN Position, nicht
        weiter zurueck als der Mitschnitt reicht (wie EventLedger.prune)."""
        grenze = heard_pos - max(rueckhalt, 2.0)
        i = bisect.bisect_right([e["at"] for e in self.events], grenze)
        if i:
            del self.events[:i]


# ---------------------------------------------------------------------------
# 3. Der Thread drumherum


class BeatTracker:
    """Laesst das Modell im eigenen Thread laufen und fuehrt das Raster.

    Der Analyse-Thread ruft `submit()` mit dem Audiofenster (im Takt
    BEAT_INTERVAL) und `poll()` je Hop; beides kehrt sofort zurueck. Das
    Raster (`grid`) wird NUR im Analyse-Thread veraendert - der Worker
    liefert rohe Fensterergebnisse ueber eine Queue. Ist der Worker noch
    beschaeftigt, faellt ein Fenster aus: die Commit-Zone ist 2 s breit, ein
    Aussetzer kostet also nichts, solange der naechste Lauf unter 2 s bleibt.
    """

    def __init__(self, model_factory=BeatModel):
        self.grid = BeatGrid()
        self.ready = False
        self.error: str | None = None
        self.provider: str | None = None
        self.runs = 0
        self._factory = model_factory
        self._slot: tuple | None = None
        self._slot_lock = threading.Lock()
        self._wake = threading.Event()
        self._results: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._work, name="beats", daemon=True)
        self._thread.start()

    @classmethod
    def create(cls) -> "BeatTracker | None":
        """Der Tracker, wenn onnxruntime da ist - sonst None (JamPilot laeuft
        dann ohne Taktstriche und ohne Snap, mit der Verfeinerung wie zuvor)."""
        return cls() if onnxruntime_available() else None

    def submit(self, audio: np.ndarray, samplerate: int,
               window_start: float, window_end: float) -> bool:
        """Ein Fenster zum Rechnen geben. False, wenn der Worker noch am
        vorigen sitzt (das Fenster faellt dann aus)."""
        if self.error is not None:
            return False
        with self._slot_lock:
            if self._slot is not None:
                return False
            self._slot = (audio, samplerate, window_start, window_end)
        self._wake.set()
        return True

    def busy(self) -> bool:
        with self._slot_lock:
            return self._slot is not None

    def poll(self) -> int:
        """Fertige Fenster ins Raster uebernehmen; Anzahl der neuen Fenster."""
        n = 0
        while True:
            try:
                beats, downs, start, end = self._results.get_nowait()
            except queue.Empty:
                return n
            self.grid.absorb(beats, downs, start, end)
            n += 1

    def stop(self) -> None:
        """Worker anhalten und auf ihn WARTEN (hoechstens ein Fenster lang).

        Ohne das Warten stirbt der Prozess womoeglich, waehrend der Thread
        noch in ORT rechnet - dann raeumt der Interpreter die Session unter
        ihm weg, und ORT antwortet mit "terminate called without an active
        exception" und einem Core-Dump beim Strg+C. Ein Schoenheitsfehler,
        aber einer, der wie ein Absturz aussieht.
        """
        self._stop.set()
        self._wake.set()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=3.0)

    def _work(self) -> None:
        try:
            model = self._factory()
            self.provider = getattr(model, "provider", None)
            self.ready = True
        except Exception as exc:       # fehlende Datei, kaputtes Wheel, ...
            self.error = str(exc) or type(exc).__name__
            return
        while not self._stop.is_set():
            self._wake.wait()
            self._wake.clear()
            while True:
                with self._slot_lock:
                    job, self._slot = self._slot, None
                if job is None or self._stop.is_set():
                    break
                audio, samplerate, start, end = job
                try:
                    beats, downs = model.run(_to_model_rate(audio, samplerate))
                except Exception as exc:
                    self.error = str(exc) or type(exc).__name__
                    return
                self.runs += 1
                self._results.put((beats, downs, start, end))
        del model                      # Session im eigenen Thread freigeben


def _to_model_rate(audio: np.ndarray, samplerate: int) -> np.ndarray:
    y = np.asarray(audio, dtype=np.float32)
    if samplerate == SR:
        return y
    import librosa
    return librosa.resample(y, orig_sr=samplerate, target_sr=SR)

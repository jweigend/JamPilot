"""Beat This! (small0) ohne Torch: Referenz fuer Vor- und Nachverarbeitung.

Uebergabe aus JamPilotML (docs/exploration/beat-tracking-ergebnisse.md).
Das Modell selbst liegt als ONNX-Datei vor (jampilot/data/beat_this_small0.onnx,
Eingabe "spect" (1, T, 128) float32, Ausgaben "beat"/"downbeat" (1, T) Logits).
Dieses Modul liefert die beiden Stuecke drumherum, die beat_this in Torch
rechnet, in NumPy/librosa - gegen das Original verifiziert
(tests/test_beat_this_referenz.py, Golden-Fixture tests/data/beat_golden_window.npz):

  log_mel(samples)            -> (T, 128)  Log-Mel-Spektrogramm, 50 Frames/s
  pad_chunk(spect)            -> (T+12, 128)  6 Randframes je Seite, wie das
                                 Modell sie beim Training sah
  pick_peaks(beat, downbeat)  -> (Beat-Sekunden, Downbeat-Sekunden)
  run_window(session, samples)-> alles zusammen fuer ein Fenster

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

_mel_fb = None


def mel_filterbank() -> np.ndarray:
    """(N_MELS, N_FFT//2+1) — Slaney-Skala, keine Flaechennormierung."""
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


def run_window(session, samples: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Ein Fenster (z. B. 10 s) durch ONNX Runtime: (Beats s, Downbeats s),
    relativ zum Fensteranfang. `session` = onnxruntime.InferenceSession."""
    chunk = pad_chunk(log_mel(samples))[None].astype(np.float32)
    beat, down = session.run(None, {session.get_inputs()[0].name: chunk})
    return pick_peaks(strip_border(beat[0]), strip_border(down[0]))

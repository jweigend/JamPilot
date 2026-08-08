"""NumPy-Inferenz fuer das BTC-Akkorderkennungsmodell (Park et al., ISMIR 2019).

Port des Torch-Modells aus https://github.com/jayg996/BTC-ISMIR19 (MIT-Lizenz),
Checkpoint btc_model_large_voca.pt, exportiert nach data/btc_large_voca.npz
(ohne das LSTM im OutputLayer, das bei Inferenz nie aufgerufen wird).

Der Port muss zwei Eigenheiten des Originals exakt nachbilden, sonst weichen
die Vorhersagen von der Torch-Referenz ab:
 - Der Custom-LayerNorm teilt durch die UNVERZERRTE Standardabweichung
   (Torch-Default, ddof=1) und addiert eps auf die Std, nicht auf die Varianz.
 - Im Positionwise-FeedForward laeuft ReLU auch nach der LETZTEN Conv
   (die Schleifenbedingung `i < len(layers)` ist immer wahr).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .chroma import NOTE_NAMES

# Feature-Parameter des Trainings (run_config.yaml des BTC-Repos).
BTC_SR = 22050
BTC_HOP = 2048
BTC_N_BINS = 144
BTC_BINS_PER_OCTAVE = 24
BTC_TIMESTEP = 108
BTC_FRAME_SECONDS = BTC_HOP / BTC_SR          # ~92.9 ms
BTC_WINDOW_SECONDS = 10.0                     # ein Modell-Fenster (108 Frames)

# 1-2-Frame-Flackern der Rohausgabe; Segmente darunter werden vom Vorgaenger
# geschluckt (Benchmark REPORT_btc_benchmark.md, Abschnitt 3).
MIN_SEGMENT_SECONDS = 0.25

_WEIGHTS_PATH = Path(__file__).with_name("data") / "btc_large_voca.npz"

# BTC-Qualitaeten -> kanonische JamPilot-Suffixe (Kreuz-Schreibweise, Umschrift
# in b-Form macht wie bisher tonality.spell).
_QUALITY_SUFFIX = {
    "min": "m", "maj": "", "dim": "dim", "aug": "aug",
    "min6": "m6", "maj6": "6", "min7": "m7", "minmaj7": "mMaj7",
    "maj7": "maj7", "7": "7", "dim7": "dim7", "hdim7": "m7b5",
    "sus2": "sus2", "sus4": "sus4",
}
_QUALITY_ORDER = ["min", "maj", "dim", "aug", "min6", "maj6", "min7",
                  "minmaj7", "maj7", "7", "dim7", "hdim7", "sus2", "sus4"]

# Intervallstrukturen der BTC-Qualitaeten - fuer Griffbrett/Kontrollgitarre,
# analog zu chords.CHORD_TYPES.
BTC_CHORD_TONES = {
    "": (0, 4, 7), "m": (0, 3, 7), "dim": (0, 3, 6), "aug": (0, 4, 8),
    "m6": (0, 3, 7, 9), "6": (0, 4, 7, 9), "m7": (0, 3, 7, 10),
    "mMaj7": (0, 3, 7, 11), "maj7": (0, 4, 7, 11), "7": (0, 4, 7, 10),
    "dim7": (0, 3, 6, 9), "m7b5": (0, 3, 6, 10),
    "sus2": (0, 2, 7), "sus4": (0, 5, 7),
}


def _label_names() -> list[str]:
    """Index 0..169 -> kanonischer Akkordname ("C", "Cm7b5", ... , "?", "N")."""
    names = [""] * 170
    for i in range(168):
        root = NOTE_NAMES[i // 14]
        names[i] = root + _QUALITY_SUFFIX[_QUALITY_ORDER[i % 14]]
    names[168] = "?"    # X: Akkord, den das Modell nicht einordnen kann
    names[169] = "N"
    return names


LABEL_NAMES = _label_names()


def _layer_norm(x: np.ndarray, gamma: np.ndarray, beta: np.ndarray) -> np.ndarray:
    mean = x.mean(axis=-1, keepdims=True)
    std = x.std(axis=-1, keepdims=True, ddof=1)
    return gamma * (x - mean) / (std + 1e-6) + beta


def _softmax(x: np.ndarray) -> np.ndarray:
    x = x - x.max(axis=-1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=-1, keepdims=True)


def _conv3(x: np.ndarray, weight: np.ndarray, bias: np.ndarray) -> np.ndarray:
    """Conv1d, Kernel 3, beidseitig 1 Frame Zero-Padding. x: (T, C_in)."""
    pad = np.zeros((1, x.shape[1]), dtype=x.dtype)
    xp = np.concatenate([pad, x, pad], axis=0)
    # weight: (C_out, C_in, 3)
    return (xp[:-2] @ weight[:, :, 0].T
            + xp[1:-1] @ weight[:, :, 1].T
            + xp[2:] @ weight[:, :, 2].T
            + bias)


def _timing_signal(length: int, channels: int) -> np.ndarray:
    position = np.arange(length)
    num_timescales = channels // 2
    log_inc = np.log(1.0e4) / (num_timescales - 1)
    inv = np.exp(np.arange(num_timescales, dtype=np.float64) * -log_inc)
    scaled = position[:, None] * inv[None, :]
    return np.concatenate([np.sin(scaled), np.cos(scaled)], axis=1).astype(np.float32)


@dataclass
class _AttnBlock:
    ln_mha_g: np.ndarray
    ln_mha_b: np.ndarray
    w_q: np.ndarray
    w_k: np.ndarray
    w_v: np.ndarray
    w_o: np.ndarray
    ln_ffn_g: np.ndarray
    ln_ffn_b: np.ndarray
    conv0_w: np.ndarray
    conv0_b: np.ndarray
    conv1_w: np.ndarray
    conv1_b: np.ndarray

    def forward(self, x: np.ndarray, mask: np.ndarray, num_heads: int) -> np.ndarray:
        t, hidden = x.shape
        head = hidden // num_heads
        xn = _layer_norm(x, self.ln_mha_g, self.ln_mha_b)
        q = (xn @ self.w_q.T).reshape(t, num_heads, head).transpose(1, 0, 2)
        k = (xn @ self.w_k.T).reshape(t, num_heads, head).transpose(1, 0, 2)
        v = (xn @ self.w_v.T).reshape(t, num_heads, head).transpose(1, 0, 2)
        q = q * np.float32(head ** -0.5)
        logits = q @ k.transpose(0, 2, 1) + mask[:t, :t]
        ctx = _softmax(logits) @ v
        ctx = ctx.transpose(1, 0, 2).reshape(t, hidden)
        x = x + ctx @ self.w_o.T
        xn = _layer_norm(x, self.ln_ffn_g, self.ln_ffn_b)
        y = np.maximum(_conv3(xn, self.conv0_w, self.conv0_b), 0.0)
        y = np.maximum(_conv3(y, self.conv1_w, self.conv1_b), 0.0)  # ReLU auch hier, s.o.
        return x + y


class BTCModel:
    """Bi-direktionaler Transformer, reine NumPy-Vorwaertsrechnung."""

    def __init__(self, weights_path: Path = _WEIGHTS_PATH, num_heads: int = 4):
        z = np.load(weights_path)
        w = {k: z[k].astype(np.float32) for k in z.files}
        self.mean = float(w["norm/mean"])
        self.std = float(w["norm/std"])
        self.num_heads = num_heads
        self.embed = w["self_attn_layers.embedding_proj.weight"]
        self.final_ln_g = w["self_attn_layers.layer_norm.gamma"]
        self.final_ln_b = w["self_attn_layers.layer_norm.beta"]
        self.out_w = w["output_layer.output_projection.weight"]
        self.out_b = w["output_layer.output_projection.bias"]
        self.timing = _timing_signal(BTC_TIMESTEP, self.embed.shape[0])

        def block(prefix: str) -> _AttnBlock:
            return _AttnBlock(
                ln_mha_g=w[prefix + "layer_norm_mha.gamma"],
                ln_mha_b=w[prefix + "layer_norm_mha.beta"],
                w_q=w[prefix + "multi_head_attention.query_linear.weight"],
                w_k=w[prefix + "multi_head_attention.key_linear.weight"],
                w_v=w[prefix + "multi_head_attention.value_linear.weight"],
                w_o=w[prefix + "multi_head_attention.output_linear.weight"],
                ln_ffn_g=w[prefix + "layer_norm_ffn.gamma"],
                ln_ffn_b=w[prefix + "layer_norm_ffn.beta"],
                conv0_w=w[prefix + "positionwise_convolution.layers.0.conv.weight"],
                conv0_b=w[prefix + "positionwise_convolution.layers.0.conv.bias"],
                conv1_w=w[prefix + "positionwise_convolution.layers.1.conv.weight"],
                conv1_b=w[prefix + "positionwise_convolution.layers.1.conv.bias"],
            )

        self.layers = []
        i = 0
        while f"self_attn_layers.self_attn_layers.{i}.linear.weight" in w:
            base = f"self_attn_layers.self_attn_layers.{i}."
            self.layers.append((
                block(base + "attn_block."),
                block(base + "backward_attn_block."),
                w[base + "linear.weight"],
                w[base + "linear.bias"],
            ))
            i += 1

        neg = np.float32(-np.inf)
        self.mask_fwd = np.triu(np.full((BTC_TIMESTEP, BTC_TIMESTEP), neg, dtype=np.float32), 1)
        self.mask_bwd = self.mask_fwd.T.copy()

    def _instance(self, features: np.ndarray) -> np.ndarray:
        """Ein 108-Frame-Fenster -> Label-Indizes (108,). features: (108, 144), normalisiert."""
        x = features @ self.embed.T
        x = x + self.timing[: x.shape[0]]
        for fwd, bwd, w_lin, b_lin in self.layers:
            f = fwd.forward(x, self.mask_fwd, self.num_heads)
            b = bwd.forward(x, self.mask_bwd, self.num_heads)
            x = np.concatenate([f, b], axis=1) @ w_lin.T + b_lin
        x = _layer_norm(x, self.final_ln_g, self.final_ln_b)
        logits = x @ self.out_w.T + self.out_b
        return np.argmax(logits, axis=-1)

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Log-CQT-Frames (T, 144) -> Label-Indizes (T,).

        Wie test.py des Originals: normalisieren, auf Vielfache von 108 Frames
        mit Nullen auffuellen, instanzweise rechnen, Padding wieder abschneiden.
        """
        t = features.shape[0]
        x = (features.astype(np.float32) - np.float32(self.mean)) / np.float32(self.std)
        pad = (-t) % BTC_TIMESTEP
        if pad:
            x = np.pad(x, ((0, pad), (0, 0)))
        labels = np.concatenate([
            self._instance(x[s : s + BTC_TIMESTEP])
            for s in range(0, x.shape[0], BTC_TIMESTEP)
        ])
        return labels[:t]


def features_from_audio(samples: np.ndarray, samplerate: int) -> np.ndarray:
    """Audio -> Log-CQT-Frames (T, 144), wie audio_dataset.py des Originals.

    Die CQT laeuft in 10-s-Stuecken, nicht am Stueck - das repliziert die
    Referenz (und haelt die Latenz im Live-Pfad konstant).
    """
    import librosa

    y = np.asarray(samples, dtype=np.float32)
    if samplerate != BTC_SR:
        y = librosa.resample(y, orig_sr=samplerate, target_sr=BTC_SR)
    chunk = int(BTC_SR * BTC_WINDOW_SECONDS)
    parts = []
    for start in range(0, max(len(y) - chunk, 0) + 1, chunk):
        parts.append(librosa.cqt(
            y[start : start + chunk], sr=BTC_SR, n_bins=BTC_N_BINS,
            bins_per_octave=BTC_BINS_PER_OCTAVE, hop_length=BTC_HOP))
    rest = len(parts) * chunk
    if rest < len(y) or not parts:
        parts.append(librosa.cqt(
            y[rest:], sr=BTC_SR, n_bins=BTC_N_BINS,
            bins_per_octave=BTC_BINS_PER_OCTAVE, hop_length=BTC_HOP))
    feature = np.concatenate(parts, axis=1)
    return np.log(np.abs(feature) + 1e-6).T.astype(np.float32)


# Tiefband fuer die Bassmessung: C1 + 3 Oktaven (32.7..260 Hz) - dasselbe
# Band, das chroma.analyze_window fuer bass.py zog (2 Bins je Halbton).
BTC_BASS_BINS = 72

# Grenz-Verfeinerung: Die Modellgrenze liegt auf dem 93-ms-Raster und im
# Schnitt ~140 ms HINTER dem annotierten Wechsel. Im kleinen Fenster darum
# such ein Akkordton-Schnitt im HPSS-Chroma (23-ms-Raster) den echten
# Umschlagpunkt, Onset-Staerke gewichtet mit - Wechsel fallen auf Anschlaege.
# Gegen die Isophonics-Referenz gemessen (tests/reference/README.md):
# median |dt| 187 -> 121 ms, Anteil <=1 Frame verdoppelt (25% -> 42%).
REFINE_RADIUS = 0.3        # Suchweite um die Modellgrenze
REFINE_CONTEXT = 0.75      # Audio-Slice je Seite (HPSS braucht Kontext)
REFINE_ONSET_WEIGHT = 1.0
_FINE_HOP = 512            # 23-ms-Raster der Feinsuche (bei 22050 Hz)


def _tone_template(name: str) -> np.ndarray | None:
    """Normierter 12-Ton-Vektor der kanonischen Akkord-ID - None fuer N/?/-."""
    if not name or name[0] not in "ABCDEFG":
        return None
    root_name = name[:2] if len(name) > 1 and name[1] == "#" else name[:1]
    quality = name[len(root_name):]
    if quality not in BTC_CHORD_TONES:
        return None
    template = np.zeros(12, dtype=np.float32)
    for interval in BTC_CHORD_TONES[quality]:
        template[(NOTE_NAMES.index(root_name) + interval) % 12] = 1.0
    return template / np.linalg.norm(template)


def refine_boundary(samples: np.ndarray, samplerate: int, boundary: float,
                    prev_name: str, new_name: str) -> float:
    """Verfeinerte Position einer Segmentgrenze (Sekunden relativ zu samples).

    Prinzip: Im +-REFINE_RADIUS-Fenster wird der Schnittpunkt k gesucht, hinter
    dem das HPSS-Chroma den NEUEN Akkordtoenen aehnelt und davor den ALTEN -
    Onset-Staerke des Rohsignals zieht den Schnitt auf den Anschlag. Kann die
    Grenze nicht verfeinert werden (Stille/Unbekannt/Randlage), kommt sie
    unveraendert zurueck.
    """
    import librosa

    prev_template = _tone_template(prev_name)
    new_template = _tone_template(new_name)
    if prev_template is None or new_template is None:
        return boundary

    start = boundary - REFINE_CONTEXT
    stop = boundary + REFINE_CONTEXT
    i0, i1 = int(start * samplerate), int(stop * samplerate)
    if i0 < 0 or i1 > len(samples):
        return boundary
    y = np.asarray(samples[i0:i1], dtype=np.float32)
    if samplerate != BTC_SR:
        y = librosa.resample(y, orig_sr=samplerate, target_sr=BTC_SR)
    fine = _FINE_HOP / BTC_SR

    harmonic = librosa.effects.harmonic(y, margin=4.0)
    chroma = librosa.feature.chroma_cqt(y=harmonic, sr=BTC_SR,
                                        hop_length=_FINE_HOP, bins_per_octave=36)
    onset = librosa.onset.onset_strength(y=y, sr=BTC_SR, hop_length=_FINE_HOP)

    mitte = REFINE_CONTEXT / fine
    lo = max(0, int(mitte - REFINE_RADIUS / fine))
    hi = min(chroma.shape[1], int(mitte + REFINE_RADIUS / fine) + 1)
    if hi - lo < 4:
        return boundary
    seg = chroma[:, lo:hi]
    norm = np.linalg.norm(seg, axis=0) + 1e-9
    diff = (new_template @ seg) / norm - (prev_template @ seg) / norm
    scores = np.array([diff[k:].sum() - diff[:k].sum()
                       for k in range(1, len(diff))])
    env = onset[lo + 1 : lo + len(scores) + 1]
    if len(env) == len(scores) and env.max() > 0:
        scores = scores + REFINE_ONSET_WEIGHT * scores.std() * (env / env.max())
    return start + (lo + 1 + int(np.argmax(scores))) * fine


def fold_bass_chroma(features: np.ndarray) -> np.ndarray:
    """Log-CQT-Frames (T, 144) -> Tiefband-Chroma (12, T) fuer bass.dominant.

    Orientierung wie chroma.analyze_window.bass_frames: Tonklassen x Frames.
    """
    mag = np.exp(features[:, :BTC_BASS_BINS])
    pcs = (np.arange(BTC_BASS_BINS) // 2) % 12
    out = np.zeros((12, features.shape[0]), dtype=np.float32)
    for pc in range(12):
        out[pc] = mag[:, pcs == pc].sum(axis=1)
    return out


def fold_chroma(features: np.ndarray) -> np.ndarray:
    """Log-CQT-Frames (T, 144) -> 12-Ton-Chroma je Frame.

    Fuer die Tonartschaetzung (Schreibweise # oder b): Die CQT beginnt bei C1
    mit 2 Bins je Halbton, also gehoert Bin b zur Tonklasse (b//2) % 12.
    Gefaltet werden die Magnituden, nicht die Log-Werte.
    """
    mag = np.exp(features)
    pcs = (np.arange(features.shape[1]) // 2) % 12
    out = np.zeros((features.shape[0], 12), dtype=np.float32)
    for pc in range(12):
        out[:, pc] = mag[:, pcs == pc].sum(axis=1)
    return out


def segments_from_labels(labels: np.ndarray, offset: float = 0.0,
                         min_seconds: float = MIN_SEGMENT_SECONDS) -> list[tuple[float, str]]:
    """Frame-Labels -> Zeitleiste [(Startsekunde, Name)], Kurzsegmente verschmolzen.

    Ein Segment unter min_seconds ist 1-2-Frame-Flackern; es faellt an seinen
    Vorgaenger (das erste Segment an seinen Nachfolger).
    """
    if len(labels) == 0:
        return []
    runs: list[tuple[int, int, int]] = []      # (startframe, endframe, label)
    start = 0
    for i in range(1, len(labels) + 1):
        if i == len(labels) or labels[i] != labels[start]:
            runs.append((start, i, int(labels[start])))
            start = i
    min_frames = max(1, int(round(min_seconds / BTC_FRAME_SECONDS)))
    merged: list[tuple[int, int, int]] = []
    for s, e, lab in runs:
        if merged and (e - s) < min_frames:
            ps, _, plab = merged[-1]
            merged[-1] = (ps, e, plab)
        elif merged and merged[-1][2] == lab:
            merged[-1] = (merged[-1][0], e, lab)
        else:
            merged.append((s, e, lab))
    # Falls das allererste Segment zu kurz war, gehoert es zum Nachfolger.
    if len(merged) > 1 and (merged[0][1] - merged[0][0]) < min_frames:
        merged[1] = (merged[0][0], merged[1][1], merged[1][2])
        merged.pop(0)
    out = []
    for s, _, lab in merged:
        name = LABEL_NAMES[lab]
        if not out or out[-1][1] != name:
            out.append((offset + s * BTC_FRAME_SECONDS, name))
    return out

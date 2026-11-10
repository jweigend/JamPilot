"""Huellkurven-Vergleich gegen echte Stems: Bandpass 30..250 Hz (bisher)
gegen Open-Unmix umxhq/umxl, blockweise wie live. Zahlen in
docs/exploration/bass-stem-huellkurve.md.

    UMX_DIR=<ordner mit umx_*_bass.onnx> python tests/reference/messung_bass_stem.py

Braucht: onnxruntime, librosa, scipy (Projekt-venv reicht); die Modelle aus
export_umx_bass.py; den Sailing-Bass-Stem in tests/realaudio/ (gitignored) und
die Echoes-Stems unter ~/Documentos (s. Fundorte in der Projekt-Memory).
"""
import sys, glob, os, time, warnings
warnings.filterwarnings("ignore")
import numpy as np, librosa, onnxruntime as ort
from scipy.signal import butter, sosfilt, stft, istft

SR = 44100; NFFT = 4096; HOP = 1024
BLOCK = int(round(0.0125 * SR))           # 12,5 ms wie envelope.py
SOS = butter(2, [30, 250], btype="bandpass", fs=SR, output="sos")

def load(path, offset, dur):
    y, _ = librosa.load(path, sr=SR, mono=False, offset=offset, duration=dur)
    return y if y.ndim == 2 else np.stack([y, y])

def env(y):                                 # y: (2, n) oder (n,)
    m = y.mean(axis=0) if y.ndim == 2 else y
    n = len(m) // BLOCK
    return np.sqrt((m[: n * BLOCK].reshape(n, BLOCK) ** 2).mean(axis=1))

UMX_DIR = os.environ.get("UMX_DIR", ".")

class Umx:
    def __init__(self, path, threads=4):
        path = os.path.join(UMX_DIR, path)
        so = ort.SessionOptions(); so.intra_op_num_threads = threads
        self.s = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
    def separate(self, y):                  # y: (2, n) -> (2, n)
        f, t, Z = stft(y, fs=SR, nperseg=NFFT, noverlap=NFFT - HOP, window="hann",
                       boundary="zeros", padded=True)
        Z = Z * NFFT / 2                    # scipy skaliert (1/sum(win)); umx erwartet torch-STFT-Skala
        mag = np.abs(Z).astype(np.float32)[None]          # (1, 2, bins, frames)
        est = self.s.run(None, {"mag": mag})[0][0]
        mask = est / (mag[0] + 1e-8)
        _, out = istft(Z * mask, fs=SR, nperseg=NFFT, noverlap=NFFT - HOP, window="hann",
                       input_onesided=True, boundary=True)
        return (out * 2 / NFFT)[:, : y.shape[1]]
    def separate_blockwise(self, y, core=6.0, margin=1.0):
        n = y.shape[1]; out = np.zeros_like(y); c = int(core * SR); m = int(margin * SR)
        t0 = time.perf_counter(); k = 0
        for start in range(0, n, c):
            a = max(0, start - m); b = min(n, start + c + m)
            sep = self.separate(y[:, a:b])
            out[:, start:min(n, start + c)] = sep[:, start - a: start - a + min(c, n - start)]
            k += 1
        return out, (time.perf_counter() - t0) / k

def metrics(est_env, true_env, drum_env=None):
    n = min(len(est_env), len(true_env)); e, tr = est_env[:n], true_env[:n]
    corr = np.corrcoef(e, tr)[0, 1]
    # dB-Korrelation: wie die Hoehe auf dem Bildschirm wirkt (Spitzenwert-normiert)
    db = lambda v: 20 * np.log10(np.maximum(v / (v.max() + 1e-12), 1e-3))
    corr_db = np.corrcoef(db(e), db(tr))[0, 1]
    quiet = tr < 0.05 * tr.max(); loud = tr > 0.3 * tr.max()
    leak = e[quiet].mean() / e[loud].mean() if quiet.any() and loud.any() else np.nan
    r = dict(corr=corr, corr_db=corr_db, leak=leak)
    if drum_env is not None:
        d = drum_env[:n]
        # Kick-Uebersprechen: Korrelation der Residuen (nach bestem linearem Fit auf den Bass) mit den Drums
        a = np.dot(e, tr) / np.dot(tr, tr); res = e - a * tr
        r["drum_corr"] = np.corrcoef(res, d)[0, 1]
    return r

def align(est, ref, max_shift=20):          # Verschiebung in Bloecken, die die Korrelation maximiert
    best = (-2, 0)
    for s in range(-max_shift, max_shift + 1):
        a = est[max(0, s):len(est) + min(0, s)]; b = ref[max(0, -s):len(ref) + min(0, -s)]
        n = min(len(a), len(b)); c = np.corrcoef(a[:n], b[:n])[0, 1]
        if c > best[0]: best = (c, s)
    return best[1]

def run(name, mix, bass, drums=None):
    true_env = env(bass); drum_env = env(drums) if drums is not None else None
    results = {}
    bp = sosfilt(SOS, mix, axis=1)
    results["bandpass 30-250 Hz (heute)"] = (env(bp), 0.0)
    for tag in ["umxhq", "umxl"]:
        u = Umx(f"umx_{tag}_bass.onnx")
        sep, dt = u.separate_blockwise(mix)
        results[f"{tag} blockweise"] = (env(sep), dt)
        results[f"{tag} + bandpass"] = (env(sosfilt(SOS, sep, axis=1)), dt)
    print(f"\n== {name} ({mix.shape[1]/SR:.0f} s)")
    print(f"{'Methode':30s} {'corr':>6s} {'corrdB':>7s} {'leak':>6s} {'drum':>6s} {'ms/6s':>6s}")
    for k, (e, dt) in results.items():
        s = align(e, true_env); e2 = e[max(0, s):]; t2 = true_env[max(0, -s):]
        d2 = drum_env[max(0, -s):] if drum_env is not None else None
        r = metrics(e2, t2, d2)
        print(f"{k:30s} {r['corr']:6.3f} {r['corr_db']:7.3f} {r['leak']:6.3f} {r.get('drum_corr', float('nan')):6.3f} {dt*1000:6.0f}")

R = "/home/johannes/Programieren/JamPilot/tests/realaudio/"
E = glob.glob(os.path.expanduser("~/Documentos/Pink Floyd - Echoes*"))[0] + "/"
def stem(kind): return glob.glob(E + f"*-{kind}-*.mp3")[0]

# Sailing: 90 s, Ausschnitt mit dem meisten Bass
full_bass, _ = librosa.load(R + "Mark Knopfler - Sailing to Philadelphia-bass-A major-99bpm-442hz.mp3", sr=SR, mono=True)
win = 90 * SR; e = np.array([np.sum(full_bass[i:i+win]**2) for i in range(0, len(full_bass) - win, 10 * SR)])
off = int(np.argmax(e)) * 10
print(f"Sailing: Ausschnitt ab {off} s")
run("Sailing to Philadelphia", load(R + "sailing_to_philadelphia.mp3", off, 90),
    load(R + "Mark Knopfler - Sailing to Philadelphia-bass-A major-99bpm-442hz.mp3", off, 90))

# Echoes: Mix = Summe der Stems ausser Metronom; Ausschnitt mit viel Bass UND Drums
fb, _ = librosa.load(stem("bass"), sr=SR, mono=True); fd, _ = librosa.load(stem("drums"), sr=SR, mono=True)
n = min(len(fb), len(fd)); e = np.array([np.sum(fb[i:i+win]**2) * np.sum(fd[i:i+win]**2) for i in range(0, n - win, 10 * SR)])
off = int(np.argmax(e)) * 10
print(f"Echoes: Ausschnitt ab {off} s")
stems = {k: load(stem(k), off, 90) for k in ["bass", "drums", "guitars", "keys", "other", "piano", "vocals"]}
L = min(v.shape[1] for v in stems.values())
mix = sum(v[:, :L] for v in stems.values())
run("Echoes", mix, stems["bass"][:, :L], stems["drums"][:, :L])

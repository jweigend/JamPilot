"""Hopweise Trennung: Kern 0,25 s mit Kontext links/rechts, Mono-Eingang wie
live - Qualitaet und ms je Hop (1 Thread). Nutzt Funktionen aus
messung_bass_stem.py (gleicher UMX_DIR). Zahlen in
docs/exploration/bass-stem-huellkurve.md.
"""
import warnings; warnings.filterwarnings("ignore")
import sys, time, glob, os, numpy as np
sys.argv = ["x"]
HIER = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HIER, "messung_bass_stem.py")).read().split("\nR = ")[0])   # Funktionen/Klassen uebernehmen

def blockwise(u, y, core, ml, mr):
    n = y.shape[1]; out = np.zeros_like(y); c = int(core*SR); l = int(ml*SR); r = int(mr*SR)
    t0 = time.perf_counter(); k = 0
    for start in range(0, n, c):
        a = max(0, start - l); b = min(n, start + c + r)
        sep = u.separate(y[:, a:b])
        out[:, start:min(n, start+c)] = sep[:, start-a: start-a+min(c, n-start)]; k += 1
    return out, (time.perf_counter()-t0)/k

R = "/home/johannes/Programieren/JamPilot/tests/realaudio/"
E = glob.glob(os.path.expanduser("~/Documentos/Pink Floyd - Echoes*"))[0] + "/"
def stem(kind): return glob.glob(E + f"*-{kind}-*.mp3")[0]
songs = {}
mono = lambda y: np.repeat(y.mean(axis=0, keepdims=True), 2, axis=0)
songs["Sailing"] = (mono(load(R + "sailing_to_philadelphia.mp3", 210, 60)),
                    load(R + "Mark Knopfler - Sailing to Philadelphia-bass-A major-99bpm-442hz.mp3", 210, 60), None)
st = {k: load(stem(k), 380, 60) for k in ["bass","drums","guitars","keys","other","piano","vocals"]}
L = min(v.shape[1] for v in st.values()); mix = sum(v[:, :L] for v in st.values())
songs["Echoes"] = (mono(mix), st["bass"][:, :L], st["drums"][:, :L])

configs = [("umxhq", 6.0, 1.0, 1.0), ("umxhq", 0.25, 1.0, 1.0), ("umxhq", 0.25, 1.0, 0.5), ("umxhq", 0.25, 0.5, 0.5),
           ("umxhq", 0.25, 2.0, 1.0), ("umxhq", 0.5, 1.0, 0.5), ("umxhq_int8", 0.25, 1.0, 0.5)]
print(f"{'Modell':11s} {'core':>5s} {'links':>5s} {'rechts':>6s} | {'Sail corr':>9s} {'leak':>5s} | {'Echo corr':>9s} {'leak':>5s} {'drum':>6s} | ms/Hop(1Thr)")
for tag, core, ml, mr in configs:
    u = Umx(f"umx_{tag}_bass.onnx", threads=1)
    row = []
    for name, (mix, bass, drums) in songs.items():
        sep, dt = blockwise(u, mix, core, ml, mr)
        e = env(sep); te = env(bass); s = align(e, te)
        r = metrics(e[max(0,s):], te[max(0,-s):], env(drums)[max(0,-s):] if drums is not None else None)
        row.append((r, dt))
    (rs, dts), (re_, dte) = row
    print(f"{tag:11s} {core:5.2f} {ml:5.2f} {mr:6.2f} | {rs['corr']:9.3f} {rs['leak']:5.3f} | {re_['corr']:9.3f} {re_['leak']:5.3f} {re_['drum_corr']:6.3f} | {dts*1000:4.0f}", flush=True)

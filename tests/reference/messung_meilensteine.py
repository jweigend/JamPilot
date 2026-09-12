"""Meilenstein-Vergleich, Lauf: <repo> <weights.npz> <track|telegraph> <out.pkl>

Faehrt _display_loop der angegebenen Pipeline-Version (Repo-Checkout, z. B.
ein git worktree) hop fuer hop ueber die Datei - FakeLoop wie in
messung_live_pfad.py, Beat-Tracker synchron, falls die Version einen hat -
mit den angegebenen BTC-Gewichten als Drop-in, und sichert ALLE
Broadcast-Zustaende (t, committed/chords, beats, key). Auswertung:
messung_meilensteine_auswertung.py. Ergebnisse und Lesart:
docs/exploration/meilenstein-vergleich-2026-09.md.

Gewichte aus der Historie: git show <commit>:jampilot/data/btc_large_voca.npz
(7d8cb69 Original-BTC, e7ad6f1 iso-only, b9cf896 v7). Pipelines: git
worktree add <dir> <commit> (02cdb26 vor Publish-once, main, HEAD).
"""
import sys, threading, argparse, time, io, contextlib, pickle
from pathlib import Path
import numpy as np, librosa
repo, weights, track, out = sys.argv[1:5]
sys.path.insert(0, repo)
from jampilot import cli, btc
HERE = Path(__file__).resolve().parents[2]
SR = 22050

class Modell(btc.BTCModel):
    def __init__(self, weights_path=None, num_heads=4):
        super().__init__(Path(weights), num_heads)
btc.BTCModel = Modell
try:
    from jampilot import beats
    class SyncTracker:
        ready, error = True, None
        def __init__(self):
            self.grid = beats.BeatGrid(); self.model = beats.BeatModel(); self.provider = self.model.provider
        def submit(self, audio, sr, start, end):
            b, d = self.model.run(beats._to_model_rate(audio, sr)); self.grid.absorb(b, d, start, end); return True
        def poll(self): return 0
        def stop(self): pass
    beats.BeatTracker.create = classmethod(lambda cls: SyncTracker())
    mit_beats = True
except ImportError:
    mit_beats = False

class FakeLoop:
    xruns, last_status, capture_dropouts = 0, None, None
    recording = record_paused = muted = control_guitar = False
    record_epoch, record_offset_seconds, record_capacity_seconds = 0, 0.0, 0.0
    def __init__(self, y, delay, stop):
        self.y, self.delay_seconds, self._stop = y, delay, stop
        self._pos, self.hop = 0, int(0.25 * SR); self.control = []
    @property
    def captured_frames(self):
        self._pos = min(self._pos + self.hop, len(self.y))
        if self._pos >= len(self.y): self._stop.set()
        return self._pos
    def audio_ending_at(self, end, length):
        if end - length < 0 or end > len(self.y): return None
        return self.y[end - length:end].copy()
    def audible_position(self): return self._pos / SR - self.delay_seconds
    heard_position = audible_position
    def set_control_timeline(self, tl): self.control = list(tl)

class Sammler:
    def __init__(self): self.states = []
    def publish(self, s):
        self.states.append({k: s.get(k) for k in ("t", "frontier", "committed", "chords", "beats", "key", "lead")})

if track == "telegraph":
    y, _ = librosa.load(HERE / "tests/realaudio/telegraph_road.mp3", sr=SR, mono=True, offset=645.0, duration=165.0)
else:
    y, _ = librosa.load(HERE / "tests/reference" / f"{track}.mp3", sr=SR, mono=True)
y = y.astype(np.float32)
stop = threading.Event(); loop = FakeLoop(y, 5.0, stop); bc = Sammler()
args = argparse.Namespace(samplerate=SR, delay=5.0, record_buffer=0)
t0 = time.perf_counter()
with contextlib.redirect_stdout(io.StringIO()):
    cli._display_loop(loop, args, bc, stop=stop)
pickle.dump({"repo": repo, "weights": weights, "track": track, "mit_beats": mit_beats,
             "states": bc.states, "dauer": len(y) / SR}, open(out, "wb"))
print(f"fertig {track} {Path(repo).name} {Path(weights).name} {len(bc.states)} Zustaende {time.perf_counter() - t0:.0f} s", flush=True)

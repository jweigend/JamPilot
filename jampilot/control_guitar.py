"""Leise Kontrollgitarre zum akustischen Pruefen erkannter Akkorde.

Kein Begleitautomat: ein trockener, kurzer Anschlag pro Akkordwechsel. Die
Saiten werden mit einem Karplus-Strong-Modell erzeugt; dadurch bleibt JamPilot
offline und braucht keine fremden oder lizenzpflichtigen Sampledateien.
"""

from functools import lru_cache

import numpy as np

from .chords import CHORD_TYPES
from .chroma import NOTE_NAMES

CONTROL_GAIN = 0.16
PLUCK_SECONDS = 1.35


def _parse(chord: str) -> tuple[int, str] | None:
    if not chord or chord[0] not in "ABCDEFG":
        return None
    root_name = chord[:2] if len(chord) > 1 and chord[1] == "#" else chord[:1]
    quality = chord[len(root_name):].split("/")[0]
    if quality not in CHORD_TYPES:
        return None
    return NOTE_NAMES.index(root_name), quality


def _midi_voicing(root: int, quality: str) -> list[int]:
    """Vier aufsteigende Akkordtoene im echten Gitarrenregister."""
    pcs = [(root + interval) % 12 for interval in CHORD_TYPES[quality]]
    if len(pcs) == 3:                       # Grundton oben verdoppeln
        pcs.append(root)
    notes = []
    previous = 39
    for pc in pcs:
        midi = 40 + ((pc - 4) % 12)         # ab tiefer E-Saite
        while midi <= previous:
            midi += 12
        notes.append(midi)
        previous = midi
    # Nicht jenseits des praxisnahen Registers wachsen lassen.
    while notes[-1] > 76:
        notes = [note - 12 for note in notes]
    return notes


def _pluck(midi: int, samplerate: int, seed: int) -> np.ndarray:
    frequency = 440.0 * 2.0 ** ((midi - 69) / 12.0)
    period = max(2, int(round(samplerate / frequency)))
    length = int(round(PLUCK_SECONDS * samplerate))
    rng = np.random.default_rng(seed)
    ring = rng.uniform(-1.0, 1.0, period).astype(np.float32)
    out = np.empty(length, dtype=np.float32)
    index = 0
    for i in range(length):
        current = ring[index]
        nxt = ring[(index + 1) % period]
        out[i] = current
        ring[index] = .996 * .5 * (current + nxt)
        index = (index + 1) % period
    # Kurzer Finger-/Plektrum-Attack, danach natuerliches Ausschwingen.
    out *= np.linspace(1.0, .72, length, dtype=np.float32)
    return out


@lru_cache(maxsize=128)
def render(chord: str, samplerate: int) -> np.ndarray | None:
    """Stereo-Anschlag fuer eine kanonische Akkord-ID, oder ``None``."""
    parsed = _parse(chord)
    if parsed is None:
        return None
    root, quality = parsed
    stagger = max(1, int(round(.018 * samplerate)))
    notes = _midi_voicing(root, quality)
    length = int(round(PLUCK_SECONDS * samplerate)) + stagger * (len(notes) - 1)
    mixed = np.zeros((length, 2), dtype=np.float32)
    for i, midi in enumerate(notes):
        string = _pluck(midi, samplerate, seed=midi * 97 + root * 13 + i)
        start = i * stagger
        pan = .25 + .5 * i / max(len(notes) - 1, 1)
        mixed[start:start + len(string), 0] += string * np.sqrt(1.0 - pan)
        mixed[start:start + len(string), 1] += string * np.sqrt(pan)
    peak = float(np.max(np.abs(mixed)))
    if peak:
        mixed *= CONTROL_GAIN / peak
    return mixed

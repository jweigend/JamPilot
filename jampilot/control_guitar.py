"""Leise Kontrollgitarre zum akustischen Pruefen erkannter Akkorde.

Kein Begleitautomat: ein trockener, kurzer Anschlag pro Akkordwechsel. Die
Saiten werden mit einem Karplus-Strong-Modell erzeugt; dadurch bleibt JamPilot
offline und braucht keine fremden oder lizenzpflichtigen Sampledateien.
"""

from functools import lru_cache

import numpy as np

from .btc import BTC_CHORD_TONES
from .chroma import NOTE_NAMES

# Volles BTC-Vokabular (14 Qualitaeten): Obermenge der fuenf alten
# chords.CHORD_TYPES mit identischen Intervallen - beide Erkenner-Pfade
# koennen damit angeschlagen werden, inklusive dim7/sus/6/m7b5.
CHORD_TYPES = BTC_CHORD_TONES

# Diagnose-Mix: Die Terz muss auch gegen ein dichtes Original sofort auffallen.
# Der Originalton wird parallel in delay_stream abgesenkt.
CONTROL_GAIN = 0.34
PLAYBACK_GAIN = 0.58
PLUCK_SECONDS = 1.35

# Klangcharakter: cleane E-Gitarre statt perkussiver Akustik. Der Anschlag
# wird doppelt entschaerft - das Anregungsrauschen laeuft durch einen Tiefpass
# (weicherer "Pick", weniger Drahtklirren) und die ersten Millisekunden
# blenden ein, statt hart einzusetzen. Dazu etwas laengeres Sustain (cleane
# E-Gitarre steht laenger als eine gedaempfte Akustische) und ein expliziter
# Ausklang, damit das laengere Sustain am Puffer-Ende nicht abreisst.
EXCITE_SMOOTHING = 3        # Glaettungsdurchlaeufe ueber den Rauschimpuls
ATTACK_SECONDS = 0.012
SUSTAIN = 0.998             # Verlustfaktor je Sample (vorher 0.996)
RELEASE_SECONDS = 0.15


def _parse(chord: str) -> tuple[int, str] | None:
    if not chord or chord[0] not in "ABCDEFG":
        return None
    root_name = chord[:2] if len(chord) > 1 and chord[1] == "#" else chord[:1]
    quality = chord[len(root_name):].split("/")[0]
    if quality not in CHORD_TYPES:
        return None
    return NOTE_NAMES.index(root_name), quality


def _midi_voicing(root: int, quality: str,
                  safe_pcs: tuple[int, ...] | None = None) -> list[int]:
    """Vier aufsteigende Akkordtoene im echten Gitarrenregister."""
    pcs = [(root + interval) % 12 for interval in CHORD_TYPES[quality]]
    if safe_pcs is not None:
        pcs = [pc for pc in pcs if pc in safe_pcs]
    if not pcs:
        return []
    if len(pcs) == 3:                       # Grundton oben verdoppeln
        pcs.append(root)
    elif len(pcs) == 2:                     # Powerchord: Grundton verdoppeln
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
    # Weicher Anschlag, Teil 1: den Rauschimpuls tiefpassfiltern (zirkular,
    # der Ring ist eine Schleife). Das nimmt dem ersten Umlauf das Klirren -
    # klassischer Karplus-Strong-Griff fuer "weiches Plektrum".
    for _ in range(EXCITE_SMOOTHING):
        ring = (np.roll(ring, 1) + ring + np.roll(ring, -1)) / 3.0
    ring *= 3.0 / (EXCITE_SMOOTHING + 1)     # Lautstaerkeverlust grob ausgleichen
    out = np.empty(length, dtype=np.float32)
    index = 0
    for i in range(length):
        current = ring[index]
        nxt = ring[(index + 1) % period]
        out[i] = current
        ring[index] = SUSTAIN * .5 * (current + nxt)
        index = (index + 1) % period
    # Weicher Anschlag, Teil 2: einblenden statt hart einsetzen.
    n_att = min(int(ATTACK_SECONDS * samplerate), length)
    if n_att > 1:
        out[:n_att] *= 0.5 - 0.5 * np.cos(
            np.pi * np.arange(n_att, dtype=np.float32) / n_att)
    # Natuerliches Ausschwingen plus expliziter Ausklang am Ende.
    out *= np.linspace(1.0, .72, length, dtype=np.float32)
    n_rel = min(int(RELEASE_SECONDS * samplerate), length)
    if n_rel > 1:
        out[-n_rel:] *= 0.5 + 0.5 * np.cos(
            np.pi * np.arange(n_rel, dtype=np.float32) / n_rel)
    return out


@lru_cache(maxsize=256)
def render(chord: str, samplerate: int,
           safe_pcs: tuple[int, ...] | None = None) -> np.ndarray | None:
    """Stereo-Anschlag fuer eine kanonische Akkord-ID, oder ``None``."""
    parsed = _parse(chord)
    if parsed is None:
        return None
    root, quality = parsed
    stagger = max(1, int(round(.018 * samplerate)))
    notes = _midi_voicing(root, quality, safe_pcs)
    if not notes:
        return None
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

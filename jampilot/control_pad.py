"""Leiser Keyboard-Flaechensound zum akustischen Pruefen erkannter Akkorde.

Nachfolger der Kontrollgitarre (control_guitar.py, bis 1.4.0): Ein kurzer,
trockener Anschlag je Wechsel liess sich harmonisch schlecht beurteilen -
er war nach einer Sekunde weg, und das Original lief weiter. Eine FLAECHE
steht, solange der Akkord steht: Terz und Septime reiben hoerbar gegen das
Original, wenn sie falsch sind, und sitzen darin, wenn sie stimmen.

Kein Begleitautomat: keine Rhythmik, kein Arpeggio, nur der gehaltene
Akkord auf exakt der Stream-Zeitachse des verzoegerten Originals. Der Klang
wird lokal per Wavetable-Synthese erzeugt (drei leicht verstimmte, weich
tiefpassgefilterte Saegezaehne je Ton, langsamer Ein- und Ausschwinger),
JamPilot bleibt damit offline und braucht keine Sampledateien.
"""

from functools import lru_cache

import numpy as np

from .btc import BTC_CHORD_TONES
from .chroma import NOTE_NAMES

# Volles BTC-Vokabular (14 Qualitaeten), wie bei der Kontrollgitarre.
CHORD_TYPES = BTC_CHORD_TONES

# Diagnose-Mix: Der Originalton wird parallel in delay_stream abgesenkt
# (PLAYBACK_GAIN), die Flaeche sitzt mit CONTROL_GAIN Spitzenpegel darunter.
# Eine Flaeche traegt bei gleichem Spitzenpegel deutlich mehr Energie als ein
# Anschlag - deshalb leiser als die Gitarre (0,34), das Original etwas hoeher.
CONTROL_GAIN = 0.22
PLAYBACK_GAIN = 0.62

# Die Flaeche wird EINMAL je Akkord in voller Laenge gerendert und gecacht;
# delay_stream spielt davon so viel, wie das Segment lang ist, und legt den
# Ausklang beim Mischen darueber. Laengere Segmente enden nach PAD_SECONDS
# mit dem Ausklang - der Akkord ist dann laengst beurteilt. (10 s waeren
# schoener, kosten aber ein Viertel mehr Renderzeit je Akkord, s. _voice.)
PAD_SECONDS = 8.0
ATTACK_SECONDS = 0.10
RELEASE_SECONDS = 0.25

# Klang: je Ton drei Oszillatoren, um DETUNE_CENTS gegeneinander verstimmt
# (das langsame Schweben einer Flaeche), links und rechts leicht verschieden
# (Breite). Harmonische fallen mit 1/k^ROLLOFF ab und enden an CUTOFF_HZ -
# ein weicher, "sauberer" Saegezahn ohne Klirren.
DETUNE_CENTS = ((-8.0, 0.0, 6.0), (-6.0, 0.0, 8.0))     # links, rechts
ROLLOFF = 1.6
CUTOFF_HZ = 2600.0
TABLE_SIZE = 4096


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
    """Enge Lage in der Keyboard-Mitte (C4..B5) plus Grundton eine Oktave
    tiefer - so, wie eine linke Hand den Akkord haelt."""
    pcs = [(root + interval) % 12 for interval in CHORD_TYPES[quality]]
    if safe_pcs is not None:
        pcs = [pc for pc in pcs if pc in safe_pcs]
    if not pcs:
        return []
    notes = []
    previous = 59
    for pc in pcs:
        midi = 60 + pc
        while midi <= previous:
            midi += 12
        notes.append(midi)
        previous = midi
    while notes[-1] > 83:
        notes = [note - 12 for note in notes]
    return [notes[0] - 12] + notes            # Grundton (bzw. tiefster Ton) unten


@lru_cache(maxsize=64)
def _table(frequency: float, samplerate: int) -> np.ndarray:
    """Eine Periode des bandbegrenzten, weich gefilterten Saegezahns."""
    k = np.arange(1, int(min(CUTOFF_HZ, samplerate / 2 - 1) / frequency) + 1)
    if len(k) == 0:
        k = np.array([1])
    phase = np.arange(TABLE_SIZE) / TABLE_SIZE
    amp = 1.0 / k.astype(np.float64) ** ROLLOFF
    # sanfte Kante am Cutoff statt hartem Abschnitt
    amp *= 0.5 + 0.5 * np.cos(np.pi * (k * frequency) / max(CUTOFF_HZ, frequency))
    table = (amp[:, None] * np.sin(2 * np.pi * k[:, None] * phase[None, :])).sum(axis=0)
    return (table / (np.max(np.abs(table)) + 1e-9)).astype(np.float32)


def _voice(midi: int, samplerate: int, length: int, cents: tuple[float, ...]) -> np.ndarray:
    """Ein Ton: die verstimmten Oszillatoren aus der Wavetable, linear
    interpoliert. Bewusst float32 und in place - die Flaeche wird im
    Analyse-Thread gerendert, und PAD_SECONDS mal Abtastrate mal Oszillatoren
    ist viel: 48 kHz, vier Toene, zwei Kanaele in float64 mit Zwischenfeldern
    kosteten 600 ms je Akkord, so sind es ~140 ms (einmal je Akkord, danach
    aus dem Cache)."""
    base = 440.0 * 2.0 ** ((midi - 69) / 12.0)
    table = _table(round(base, 3), samplerate)
    ext = np.concatenate([table, table[:1]])       # i0 + 1 ohne Modulo
    out = np.zeros(length, dtype=np.float32)
    n = np.arange(length, dtype=np.float32)
    for i, c in enumerate(cents):
        f = base * 2.0 ** (c / 1200.0)
        phase = n * np.float32(f / samplerate)
        # Startphase je Oszillator versetzt, damit sich die Verstimmung nicht
        # bei Sekunde null zu einer Spitze addiert.
        phase += np.float32(i / len(cents))
        phase -= np.floor(phase)
        phase *= TABLE_SIZE
        i0 = phase.astype(np.int32)
        phase -= i0                                 # Interpolationsanteil
        out += ext[i0] * (1.0 - phase)
        out += ext[i0 + 1] * phase
    out /= len(cents)
    return out


@lru_cache(maxsize=32)
def render(chord: str, samplerate: int,
           safe_pcs: tuple[int, ...] | None = None) -> np.ndarray | None:
    """Stereo-Flaeche (PAD_SECONDS lang, eingeschwungen, OHNE Ausklang) fuer
    eine kanonische Akkord-ID, oder ``None`` fuer Stille/Unbekanntes.

    Den Ausklang legt delay_stream beim Mischen ans Segmentende
    (release_envelope) - so kann dieselbe gecachte Flaeche jede Segmentlaenge
    bedienen, ohne je Hop neu gerendert zu werden.
    """
    parsed = _parse(chord)
    if parsed is None:
        return None
    root, quality = parsed
    notes = _midi_voicing(root, quality, safe_pcs)
    if not notes:
        return None
    length = int(round(PAD_SECONDS * samplerate))
    mixed = np.zeros((length, 2), dtype=np.float32)
    for i, midi in enumerate(notes):
        gain = 0.7 if i == 0 else 1.0          # der tiefe Grundton etwas zurueck
        for channel, cents in enumerate(DETUNE_CENTS):
            mixed[:, channel] += gain * _voice(midi, samplerate, length, cents)
    n_att = min(int(ATTACK_SECONDS * samplerate), length)
    if n_att > 1:
        ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(n_att, dtype=np.float32) / n_att)
        mixed[:n_att] *= ramp[:, None]
    peak = float(np.max(np.abs(mixed)))
    if peak:
        mixed *= CONTROL_GAIN / peak
    return mixed


def release_envelope(length: int, samplerate: int, start: int, count: int) -> np.ndarray | None:
    """Huellkurve fuer die Frames [start, start+count) eines Segments von
    `length` Frames: 1 bis auf die letzten RELEASE_SECONDS, dort ein
    Kosinus-Ausklang. None, wenn der Abschnitt vor dem Ausklang liegt."""
    n_rel = min(int(RELEASE_SECONDS * samplerate), length)
    tail = length - n_rel
    if n_rel < 2 or start + count <= tail:
        return None
    idx = np.arange(start, start + count, dtype=np.float32)
    env = np.ones(count, dtype=np.float32)
    im_tail = idx >= tail
    env[im_tail] = 0.5 + 0.5 * np.cos(np.pi * (idx[im_tail] - tail) / n_rel)
    return env

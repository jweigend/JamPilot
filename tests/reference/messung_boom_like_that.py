"""Boom, Like That (Mark Knopfler): Landen die Akkorde auf der Eins?

Referenz ohne Annotation: Die Wechsel liegen im Titel immer auf einer
STARKEN Zaehlzeit (Beat-Raster des Beat-Modells, 90 bpm, Schlag 1 und 3 -
der Bassist zaehlt den Takt halb so schnell, fuer ihn ist jeder dieser
Schlaege eine Eins). Die Akkordfolge (G, Bb, C, Eb; G, Eb, F) ist
unstrittig, das Modell trifft sie offline. Also: Grundton-Wechsel der
Offline-Labels auf die naechste starke Zaehlzeit gelegt = Referenz; dann
der LIVE-Pfad (messung_live_pfad.lauf, mit Beat-Tracker) und je Wechsel
der Abstand des committeten Events zur Referenz.

Aufruf: python tests/reference/messung_boom_like_that.py [--variante NAME ...]
Varianten (Quick-Win-Kandidaten, s. unten): nearest (Stand), earlier,
strong, shift2.
"""
import sys
from pathlib import Path

import numpy as np
import librosa

PROJEKT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "tests" / "reference"))
from jampilot import beats, cli  # noqa: E402
from jampilot.btc import BTCModel, features_from_audio, segments_from_labels  # noqa: E402
import messung_live_pfad as lp  # noqa: E402

SR = 22050
AUDIO = PROJEKT / "tests" / "realaudio" / "boom_like_that.mp3"
STARK = (1, 3)          # starke Zaehlzeiten im Raster des Modells


def root_of(name):
    return None if name in ("N", "-", "?") else (name[:2] if len(name) > 1 and name[1] == "#" else name[:1])


def offline_grid(y):
    m = beats.BeatModel(); grid = beats.BeatGrid()
    for end in np.arange(10.0, len(y) / SR, 1.0):
        b, d = m.run(y[int((end - 10) * SR):int(end * SR)])
        grid.absorb(b, d, end - 10, end); grid.commit(end - 3)
    grid.commit(len(y) / SR)
    return np.array([e["at"] for e in grid.events]), np.array([e["n"] for e in grid.events])


def referenz(y, bt, n):
    """(Zeit der starken Zaehlzeit, Grundton) je Grundtonwechsel der Offline-Labels."""
    labels = BTCModel().predict(features_from_audio(y, SR))
    segs = segments_from_labels(labels)
    stark = bt[np.isin(n, STARK)]
    out, prev = [], None
    for s0, name in segs:
        r = root_of(name)
        if r is None or r == prev:
            continue
        prev = r
        if s0 < 8.0:
            continue                       # Intro ohne Raster
        k = int(np.argmin(np.abs(stark - s0)))
        out.append((stark[k], r, s0 - stark[k]))
    # Zwei Wechsel auf derselben Zaehlzeit: der spaetere Grundton gilt
    dedup = {}
    for t, r, d in out:
        dedup[round(t, 3)] = (t, r, d)
    return sorted(dedup.values())


def messen(ref, events, beat):
    """Je Referenzwechsel das erste Event gleichen Grundtons im Fenster
    [-1 Schlag, +2 Schlaege]: dt in Sekunden; None = fehlt."""
    ev = sorted(events.items())
    rows = []
    for t, r, _ in ref:
        hit = None
        for at, e in ev:
            if at < t - beat or at > t + 2 * beat:
                continue
            if root_of(e["c"]) == r:
                hit = at; break
        rows.append((t, r, None if hit is None else hit - t))
    return rows


def bericht(name, rows, beat):
    dts = np.array([d for *_, d in rows if d is not None])
    n = len(rows)
    auf = np.sum(np.abs(dts) <= 0.07); frueh = np.sum(dts < -0.07)
    spaet_klein = np.sum((dts > 0.07) & (dts < 0.5 * beat)); schlag = np.sum(dts >= 0.5 * beat)
    print(f"  {name:10s} Events {len(dts)}/{n}: auf der Eins (+-70 ms) {auf/n:4.0%}, "
          f"frueh {frueh/n:3.0%}, leicht spaet {spaet_klein/n:3.0%}, >= halber Schlag spaet {schlag/n:3.0%}, "
          f"fehlt {(n-len(dts))/n:3.0%}; median {np.median(dts)*1000:+.0f} ms, p90 {np.percentile(dts, 90)*1000:+.0f} ms",
          flush=True)
    return dts


# ------------------------------------------------------------------ Varianten
def snap_earlier(self, pos):
    """Wie snap, aber bei zwei erreichbaren Beats der FRUEHERE."""
    candidates = sorted([e["at"] for e in self.events[-16:]] + [o[0] for o in self._open])
    if not candidates:
        return None
    interval = self.interval(); reach = 0.6 * interval if interval else 0.5
    inreach = [c for c in candidates if abs(c - pos) <= reach]
    return min(inreach) if inreach else None


def snap_strong(self, pos):
    """Wie snap, aber eine STARKE Zaehlzeit (n 1 oder 3) in Reichweite gewinnt."""
    ev = self.events[-16:]
    candidates = [(e["at"], e["n"]) for e in ev] + [(o[0], 0) for o in self._open]
    if not candidates:
        return None
    interval = self.interval(); reach = 0.6 * interval if interval else 0.5
    inreach = [(at, nn) for at, nn in candidates if abs(at - pos) <= reach]
    if not inreach:
        return None
    strong = [at for at, nn in inreach if nn in STARK]
    if strong:
        return min(strong, key=lambda at: abs(at - pos))
    return min((at for at, _ in inreach), key=lambda at: abs(at - pos))


# Bass-Vorlauf (Orakel-Fassung): Nach der Audio-Verfeinerung einer
# GRUNDTON-Grenze pruefen, ob das Tiefband-Chroma den NEUEN Grundton schon
# auf den Schlaegen davor als dominante Bassnote fuehrt (und nicht den
# alten) - dann die Grenze auf den fruehesten solchen Schlag ziehen, max.
# BASSVOR_MAX_BEATS zurueck. Orakel: Chroma und Raster offline ueber den
# ganzen Titel; live staenden BassTrack.frames_between und das Raster bereit.
BASSVOR_MAX_BEATS = 2
_bassvor = {}


def ist_relativ(prev_name, new_root, bassmod):
    """Der neue Grundton ist die Terz des vorigen Akkords, und zwar so, dass
    beide Akkorde zwei Toene teilen: Moll-Label -> Grundton + 3 (Cm -> Eb,
    die Paralleltonart) oder Dur-Label -> Grundton + 9 (Eb -> Cm). Genau die
    Verwechslung, in der das Modell den Bass braucht, um sich zu entscheiden."""
    prev_root = bassmod.chord_root(prev_name)
    tones = bassmod.chord_tone_classes(prev_name)
    if prev_root is None or tones is None:
        return False
    moll = (prev_root + 3) % 12 in tones and (prev_root + 4) % 12 not in tones
    dur = (prev_root + 4) % 12 in tones and (prev_root + 3) % 12 not in tones
    return (moll and (new_root - prev_root) % 12 == 3) or (dur and (new_root - prev_root) % 12 == 9)


def make_bassvor(y, bt, bassvor=True, rawsnap=False, relativ=False, schlucken=False):
    """bassvor: Bass-Vorlauf (s.o.). rawsnap: Liegt die ROHE Grenze in
    Snap-Reichweite eines Schlags, bleibt sie roh - die Audio-Verfeinerung
    darf sie dann nicht auf einen anderen Schlag ziehen (gemessen war
    roh+Snap = verfeinert+Snap; die Verfeinerung ist fuer den Fall ohne
    Raster da). Orakel mit dem Offline-Raster."""
    from jampilot.btc import fold_bass_chroma
    from jampilot import bass as bassmod
    chroma = fold_bass_chroma(features_from_audio(y, SR))
    F = 2048 / 22050
    beat = float(np.median(np.diff(bt)))

    def dominant_between(a, b):
        fr = chroma[:, int(round(a / F)): int(round(b / F))]
        return bassmod.dominant(fr) if fr.shape[1] >= 2 else None

    def korrigiere(p, prev_name, name):
        new_root, prev_root = bassmod.chord_root(name), bassmod.chord_root(prev_name)
        if new_root is None or prev_root is None or new_root == prev_root:
            return p
        if relativ and not ist_relativ(prev_name, new_root, bassmod):
            return p
        k = int(np.argmin(np.abs(bt - p)))               # Schlag, auf den p faellt
        if k + 1 >= len(bt) or dominant_between(bt[k], bt[k + 1]) != new_root:
            return p                                      # der eigene Schlag muss den Grundton tragen
        ziel = p
        for j in range(k - 1, max(k - 1 - BASSVOR_MAX_BEATS, -1), -1):
            if dominant_between(bt[j], bt[j + 1]) != new_root:
                break
            ziel = bt[j]
        if ziel != p:
            _bassvor["n"] = _bassvor.get("n", 0) + 1
        return ziel

    orig = cli._refine_fresh_bounds

    def patched(timeline, refined_bounds, frontier, refine):
        if not schlucken:
            return orig(timeline, refined_bounds, frontier, verfeinere_mit(refine))
        # Wie cli._refine_fresh_bounds, plus: Zieht der Bass-Vorlauf eine
        # Grenze bis an den Onset des Vorgaengers (oder davor) zurueck, und
        # ist der Vorgaenger noch nicht committet, wird er GESCHLUCKT - er
        # war das Fehl-Label (Cm) auf dem Schlag, auf dem der neue Akkord
        # beginnt; sonst bliebe ein leerer Chip und der neue rueckt um
        # MIN_EVENT_GAP nach.
        f = verfeinere_mit(refine)
        idx = 1
        while idx < len(timeline):
            pos, name = timeline[idx]
            if pos <= frontier:
                idx += 1; continue
            if any(rn == name and abs(rp - pos) <= cli.ONSET_HYSTERESIS for rp, rn in refined_bounds):
                idx += 1; continue
            pos = f(pos, timeline[idx - 1][1], name)
            if (idx >= 2 and pos <= timeline[idx - 1][0] + cli.MIN_EVENT_GAP
                    and timeline[idx - 1][0] > frontier):
                _bassvor["geschluckt"] = _bassvor.get("geschluckt", 0) + 1
                del timeline[idx - 1]
                idx -= 1
            pos = max(pos, timeline[idx - 1][0] + cli.MIN_EVENT_GAP)
            if idx + 1 < len(timeline):
                pos = min(pos, timeline[idx + 1][0] - 0.05)
            pos = max(pos, frontier)
            timeline[idx] = (pos, name)
            refined_bounds.append((pos, name))
            idx += 1

    def verfeinere_mit(refine):
        def f(pos, prev_name, name):
            if rawsnap and np.min(np.abs(bt - pos)) <= 0.6 * beat:
                p = pos
            else:
                p = refine(pos, prev_name, name)
            return korrigiere(p, prev_name, name) if bassvor else p
        return f
    return patched


VARIANTEN = {
    "nearest": {},
    "bassvor": {"bassvor": True},
    "rawsnap": {"rawsnap": True},
    "kombi": {"bassvor": True, "rawsnap": True},
    "relativ": {"bassvor": True, "relativ": True},
    "relativ2": {"bassvor": True, "relativ": True, "schlucken": True},
    "earlier": {"snap": snap_earlier},
    "strong": {"snap": snap_strong},
    "shift2": {"shift": 2 * 2048 / 22050},
}


def main():
    args = sys.argv[1:]
    namen = [a for a in args if a != "--variante" and not a.startswith("--")] or ["nearest"]
    y, _ = librosa.load(AUDIO, sr=SR, mono=True); y = y.astype(np.float32)
    bt, n = offline_grid(y)
    beat = float(np.median(np.diff(bt)))
    ref = referenz(y, bt, n)
    print(f"{AUDIO.name}: {len(y)/SR:.0f} s, {len(bt)} Beats, Schlag {beat*1000:.0f} ms, "
          f"{len(ref)} Referenzwechsel auf starken Zaehlzeiten")
    weit = [(t, r, d) for t, r, d in ref if abs(d) > 0.4]
    print(f"  Offline-Grenze > 400 ms von der Zaehlzeit entfernt: {len(weit)} "
          + " ".join(f"{t:.1f}s({r}{d*1000:+.0f})" for t, r, d in weit[:12]))
    ergebnisse = {}
    for name in namen:
        v = VARIANTEN[name]
        orig_snap, orig_shift, orig_refine = beats.BeatGrid.snap, cli.BTC_ONSET_SHIFT, cli._refine_fresh_bounds
        if "snap" in v:
            beats.BeatGrid.snap = v["snap"]
        if "shift" in v:
            cli.BTC_ONSET_SHIFT = v["shift"]
        if v.get("bassvor") or v.get("rawsnap"):
            _bassvor.clear()
            cli._refine_fresh_bounds = make_bassvor(y, bt, bassvor=bool(v.get("bassvor")),
                                                    rawsnap=bool(v.get("rawsnap")),
                                                    relativ=bool(v.get("relativ")),
                                                    schlucken=bool(v.get("schlucken")))
        try:
            bc, dauer = lp.lauf(y, True)
        finally:
            beats.BeatGrid.snap, cli.BTC_ONSET_SHIFT = orig_snap, orig_shift
            cli._refine_fresh_bounds = orig_refine
        if v.get("bassvor"):
            print(f"  (Bass-Vorlauf hat {_bassvor.get('n', 0)} Grenzen vorgezogen, "
                  f"{_bassvor.get('geschluckt', 0)} Vorgaenger geschluckt)")
        rows = messen(ref, bc.events, beat)
        ergebnisse[name] = (rows, bc)
        bericht(name, rows, beat)
    if "--detail" in args:
        name = namen[0]; rows, bc = ergebnisse[name]
        live_beats = sorted(bc.beats.items())
        print(f"\n  Details {name}: Referenz | Grundton | dt | Zaehlzeit des Events im Live-Raster")
        for t, r, d in rows:
            if d is None:
                print(f"    {t:7.2f} {r:3s}  fehlt"); continue
            at = t + d
            k = min(range(len(live_beats)), key=lambda i: abs(live_beats[i][0] - at)) if live_beats else None
            nn = live_beats[k][1]["n"] if k is not None else "?"
            print(f"    {t:7.2f} {r:3s} {d*1000:+6.0f} ms  Beat n={nn} ({(at-live_beats[k][0])*1000:+.0f} ms vom Beat)" if k is not None else f"    {t:7.2f} {r:3s} {d*1000:+6.0f} ms")


if __name__ == "__main__":
    main()

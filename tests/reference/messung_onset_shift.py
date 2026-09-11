"""Messung: Vorwaertskorrektur der BTC-Grenze (cli.BTC_ONSET_SHIFT) und
Vorwaerts-Verfeinerung (btc.REFINE_FORWARD) im LIVE-Pfad, je Variante ein
Lauf. Hintergrund: BTC setzt seine Grenzen systematisch VOR den echten Wechsel
(synthetisch -263 ms, lagenunabhaengig; live median -184 ms gegen die
Beat-This-Taktlinie), die nur rueckwaerts suchende Verfeinerung zog sie dann
auf den vorigen Schlag - der Viertel-Snap landete "auf der 4". Ergebnisse
(2026-09-11) in README.md hier, Abschnitt "Vorwaertskorrektur".

Aufruf:
  python tests/reference/messung_onset_shift.py <track|telegraph> <shift_s> <refine_forward_s> <out.pkl>

  track     Referenztrack (let_it_be, eight_days_a_week, something,
            its_too_late, crazy_little_thing) oder "telegraph" fuer den
            Outro-Ausschnitt 645-810 s von tests/realaudio/telegraph_road.mp3
            (nicht im Repo; Dire Straits, Telegraph Road, Albumversion)
  shift_s   BTC_ONSET_SHIFT in Sekunden (0 = aus, 0.186 = zwei Frames)
  fwd_s     REFINE_FORWARD in Sekunden (0.05 = alt, 0.40 = symmetrisch)

Telegraph: Anteil der Events auf einer Taktlinie (Schlag n=1 des Beat-Grids)
bzw. auf dem Schlag davor; "Hauptwechsel" = Events mit >= 1,5 s Dauer.
Referenztrack: Timing der Events gegen die .lab-Wechsel (driftkorrigiert wie
in messung_live_pfad.py), Beat-F, und ob Event und annotierter Wechsel auf
demselben GT-Beat liegen. Beispiel fuer alle Varianten:

  for v in "0 0.05" "0.186 0.05" "0 0.40" "0.186 0.40"; do
      python tests/reference/messung_onset_shift.py eight_days_a_week $v /tmp/x.pkl; done
"""
import sys, pickle
from pathlib import Path
import numpy as np, librosa
PROJEKT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJEKT)); sys.path.insert(0, str(PROJEKT / "tests" / "reference"))
from jampilot import cli, btc
import messung_live_pfad as m
track, shift, fwd, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), Path(sys.argv[4])
cli.BTC_ONSET_SHIFT = shift
btc.REFINE_FORWARD = fwd
cli._REFINED_LOOKFORWARD = max(0.0, fwd - 0.05)
if track == "telegraph":
    START, STOP = 645.0, 810.0
    y, _ = librosa.load(PROJEKT / "tests/realaudio/telegraph_road.mp3", sr=m.SR, mono=True, offset=START, duration=STOP - START)
else:
    y, _ = librosa.load(m.REF / f"{track}.mp3", sr=m.SR, mono=True)
y = y.astype(np.float32)
bc, dauer = m.lauf(y, True)
pickle.dump({"events": bc.events, "beats": bc.beats, "track": track, "shift": shift, "fwd": fwd}, open(out, "wb"))
ev = sorted(bc.events.values(), key=lambda e: e["at"])
bts = sorted(bc.beats.values(), key=lambda b: b["at"])
b_at = np.array([b["at"] for b in bts]); b_n = np.array([b["n"] for b in bts])
tag = f"{track:18s} shift {shift:+.3f} fwd {fwd:.2f}"
if track == "telegraph":
    cls = {1: 0, 2: 0, 0: 0}; haupt = {1: 0, 2: 0, 0: 0}
    for i, e in enumerate(ev):
        if e["at"] < 20 or e["c"] == "-": continue
        j = np.argmin(np.abs(b_at - e["at"]))
        n = int(b_n[j]) if abs(b_at[j] - e["at"]) < 0.02 else 0
        n = n if n in (1, 2) else 0
        cls[n] += 1
        dauer_e = (ev[i + 1]["at"] - e["at"]) if i + 1 < len(ev) else 9
        if dauer_e >= 1.5: haupt[n] += 1
    tot = sum(cls.values()); th = sum(haupt.values())
    print(f"{tag} | Events {tot}: auf Linie {cls[1] / tot:4.0%}, Schlag davor {cls[2] / tot:4.0%}, kein Snap {cls[0] / tot:4.0%}"
          f" | Hauptwechsel {th}: auf Linie {haupt[1] / th:4.0%}, davor {haupt[2] / th:4.0%} | {dauer:.0f} s", flush=True)
else:
    scale, sh = m.ALIGNMENT.get(track, (1.0, m.OFF.get(track, 0.0)))
    korr = lambda t: t * scale + sh
    roh = np.array([float(l.split()[0]) for l in open(m.REF / f"{track}.lab") if l.split()[2] != "N"])
    gt_changes = korr(roh)
    evt = np.array([e["at"] for e in ev if e["c"] != "-"])
    line = f"{tag} | {len(evt)} Events | vs .lab: {m.timing(evt, gt_changes)}"
    beats_file = m.REF / f"{track}.beats"
    if beats_file.exists():
        gt = np.loadtxt(beats_file); gt_beats = korr(gt[:, 0])
        same = before = after = n = 0
        for g in gt_changes:
            i = np.argmin(np.abs(evt - g))
            if abs(evt[i] - g) > 0.6: continue
            n += 1
            bg = np.argmin(np.abs(gt_beats - g)); be = np.argmin(np.abs(gt_beats - evt[i]))
            if be == bg: same += 1
            elif be < bg: before += 1
            else: after += 1
        line += (f" | gleicher GT-Beat {same / n:4.0%}, Schlag davor {before / n:4.0%}, danach {after / n:4.0%} (n={n})"
                 f" | Beat-F {m.f_measure(b_at, gt_beats):.2f}")
    print(line + f" | {dauer:.0f} s", flush=True)

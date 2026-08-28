# Changelog

## 1.1.1 — 2026-08-28

The theme of this release: **a timeline that holds still under fire.**
1.1.0 made committed chords immutable; 1.1.1 makes sure they also keep
their distance. Validated in the rehearsal room the same day.

### Timeline: events keep a minimum spacing

The publish-once channel could commit chords a few hundredths of a second
apart — five chips in one second, cutting each other off into unreadable
fragments. The model itself never produces segments shorter than 0.25 s;
the density arose afterwards in the live path (boundary refinement with a
0.05 s floor, and the late-boundary correction landing 0.02 s behind an
event that had just been committed). Now the `EventLedger` guarantees a
minimum gap of 0.25 s: within one hop the later entry wins (it is the
model's more recent judgement), against an already published event the
newcomer moves up to the minimum gap instead of colliding — and an entry
that merely repeats its predecessor (same chord, same bass) is no event.
Refinement and correction hold the gap at the source as well.

| Track (reference set, `--delay 5`) | Events closer than 0.25 s | Root accuracy vs. ground truth |
|---|---|---|
| Let It Be | 44 of 184 → **0 of 165** | 84.2 % → 83.4 % |
| Something | 44 of 151 → **0 of 139** | 74.8 % → 75.0 % |

Measured with `tests/reference/messung_event_abstand.py`; confirmed in a
rehearsal-room session — the display stays stable through fast changes.

### Feature extraction: librosa filterbank memoised

librosa rebuilt the CQT filterbank on every call — ~50 ms of fixed cost per
hop, independent of signal length. It is now built once per process:
feature extraction per hop 70 → 21 ms (48 kHz, 10 s window), output
bit-identical, covered by tests. An incremental CQT that caches frames
across hops (`feature/incremental-cqt`, a further 21 → 12 ms) was measured
end-to-end and deliberately left out: identical features, but the
hop-stable frame grid yields ~7 % more committed events on the reference
set — the wandering grid of the full recomputation acts as a dither the
debounce relies on.

### Display: the big chord no longer turns grey on every change

The change animation faded the chord name in from 40 % opacity — on black
that read as a grey chord for almost half a second, right when you want to
read it, and on fast changes for nearly half its lifetime. It also fired
whenever anything in the header changed (the scale degree arriving, the
spelling flipping, the bass moving up). Now the pop is a size-only nudge,
and only on an actual change of the chord (or, in bass mode, the bass note).

## 1.1.0 — 2026-08-27

The theme of this release: **a timeline you can trust.** Every number below
is measured — the methodology and raw results live in
`docs/exploration/zeitleiste-redesign.md`, `tests/reference/README.md` and
`tests/realaudio/REPORT_key_labels.md`.

### Timeline: publish-once instead of silent revisions

The display no longer shows a continuously revised hypothesis. The server
commits every chord **exactly once** at a commit boundary ahead of the
audible position; a committed event can never move, get renamed, or vanish —
structurally, not by damping.

| What | Before | Now |
|---|---|---|
| Shown chords later contradicted by the analysis (live run, full song) | 19 % of events | **5 %** — and none of it reaches the screen anymore |
| Chips deleted/recreated or shifted on screen | regular (revision churn) | **zero** — chips have event identity |
| Contract violations (a sent event changing afterwards) | — (no contract existed) | **0** across all live runs |
| Truth cost of freezing at 2 s (root accuracy vs. endless revision, reference set) | — | **~1 point** (83.3 % vs. 84.5 %) — deliberately paid |

Also new: rapid changes occlude cleanly (the later chip cuts off the
earlier one instead of overlapping it), the lane animates on the compositor
(no more layout jank), and clock jitter is absorbed as an imperceptible
tempo change instead of visible jumps.

### Chord recognition: retrained model weights

The BTC recogniser now runs with weights fine-tuned on offset-corrected
Isophonics ground truth (`docs/exploration/nachtraining-kampagnen-2026-08.md`):

| Reference set (5 annotated tracks) | 0.1.0 weights | 1.1.0 weights |
|---|---|---|
| Labels exactly right | 69.8 % | **73.1 %** |
| Root right | 75.6 % | **79.1 %** |

No off-the-shelf teacher beat this finetune (ChordMini 68.1 %,
ChordNet 63.1 %, MERT head 48.0 %).

### Bass: a slash that never flickers

The measured bass follows a **monotone rule**: it is committed only after
the same note was stable for ~1 s, may appear **once** later if it was
still empty — and never disappears or changes afterwards. The root cause of
bass flicker was found by measurement: the verdict itself is stable, the
moving segment end was not. Bass is now pooled over a **fixed 2 s window**
after the onset — against the Isophonics bass annotations this window
matches the full-segment verdict exactly (1 % false slashes, 5/412 verdicts
differ at all), so nothing is lost.

Live effect on a full song: 24 retracted basses per run before → structurally
0 visible; expected slashes (e.g. G/B) stay on screen.

### Key detection: major/minor from the chords, tonic from the chroma

The key's tonic keeps coming from the chroma (measured best), but its
**gender** (major/minor) is now voted by the recognised chords — third-less
voicings no longer flip a minor song to major:

| Correct major/minor (10-track set, hop-weighted) | before | now |
|---|---|---|
| | 66.9 % | **98.4 %** |

Two songs were wrong for their entire duration and are now correct
(a G-minor track shown as G major with sharp spelling: 0 % → 98 %; an
A-dorian track shown as A major: 0 % → 100 %). No major song flipped.
Also since 0.1.0: the two-scale estimator (calm, but modulation-capable)
and a **key pin** in the settings for when you simply know the key.

### Nashville scale degrees (new)

Degrees above the timeline chords and the big chord — plain, inverted
(degree large, name small), or off. Spelling and degrees hang on the key,
which is why the key work above matters twice.

### The delay is now a real control

`--delay` defaults to **5 s** and splits — after the 1 s analysis guard —
**half and half** into visible lookahead and model settle time:

| `--delay` | lookahead on the lane | settle time per chord |
|---|---|---|
| 3 s | 1.0 s | 1.0 s |
| **5 s (default)** | **2.0 s** | **2.0 s** |
| 6 s | 2.5 s | 2.5 s |

More buffer now means seeing further ahead *and* better-settled chords.

### Under the hood

- `/timeline-poc`: internal debug view showing committed events, the still
  revisable hypothesis as ghost chips, and live counters for discarded
  revisions and contract violations.
- Measurement scripts checked in (`tests/reference/messung_*.py`) —
  every number above is reproducible.
- 468 tests (0.1.0: 419).

## 0.1.0 — 2026-08-13

First public release. See the GitHub release notes for the full feature list.

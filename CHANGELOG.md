# Changelog

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

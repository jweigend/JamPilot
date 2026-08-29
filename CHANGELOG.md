# Changelog

## Unreleased

### The control window says what the start is doing

The very first start of a binary takes up to a minute — numba compiles the
analysis kernels and writes its cache (measured: 23 s cold, 2 s warm). A window
that says "Starting" for that long and nothing else looks like a program that
hangs. It now carries one line that changes with the current stage — *Compiling
the analysis (first start: up to a minute) …*, *Routing the system audio …*,
*Opening the audio devices …*, *Loading the chord model*, *First window
analysed - chords are live* — with the duration once a stage is done. The
terminal gets the same stages as lines with timestamps, replacing the old
`Initialising analysis... ok`; a stage that fails keeps its error in the line.

Once the analysis runs, the same line turns into the terminal's status —
*Now playing C/E · in 3.0 s: G · Key C major*. Small and grey on purpose: the
window is the emergency brake, not the stage. What the line is for is proof
that sound arrives — a route that stands but carries no audio (wrong endpoint,
cable, exclusive-mode app) now reads *Now playing – · no sound arriving?*
instead of showing nothing until you open the browser.

## 1.2.0 — 2026-08-28

The theme of this release: **Windows gets a download.** No new analysis, no
change to what you see on stage — this is about the last platform that could
only be installed from source, and about one thing that looked wrong there.

### A standalone build for Windows

`run.cmd --bundle` now produces `dist\JamPilot\` and a release ZIP next to it,
the same way `./run.sh --bundle` has always produced a binary on Linux and
macOS. It skips when nothing changed, `--force` builds anyway, `--check` builds
twice and proves the result is reproducible, `--venv` builds from a fresh
environment out of the lock file. `packaging/venv.ps1` carries the environment
logic that `run.ps1` had inline, so there is one copy of it and not two.

**It is a folder in a ZIP, not a single file** — the one place where Windows
gets a different answer than the other platforms, and the reason the build was
held back until now. A single unsigned executable of this size that unpacks
itself into `%TEMP%` on every launch *is* a packer, technically, and heuristics
treat it as one. The folder does not trip that, and it starts in ~0.45 s
instead of ~2.5 s. It does **not** remove the SmartScreen warning: unsigned is
unsigned until someone buys a certificate. What it removes is the part that
also upsets virus scanners.

| | Linux / macOS | Windows |
|---|---|---|
| Shape | one file | a folder in a ZIP |
| Size | ~183 MB | 150 MB zipped, 363 MB unpacked |
| Start | ~2.5 s | ~0.45 s |
| Reproducible | yes (SHA-256 of the file) | yes (all ~1700 files compared) |

The ZIP carries a `JamPilot.cmd` — **double-click that, not the `.exe`**. A
console program takes its window down the instant it exits, so a JamPilot that
stops with a message ("no second output endpoint") would show that message for
a few milliseconds and then look like a program that did nothing. The `.cmd`
keeps the window open when the exit code is not zero, and only then. A
`README.txt` next to it covers the two dialogs Windows shows on a first start,
including the firewall one that silently breaks the QR code if it is dismissed.

Windows is now in `.github/workflows/build.yml` and builds on tag push together
with Linux and macOS.

**Reproducibility holds on Windows too** — that was an open question, not an
assumption: the PE format carries a timestamp in its header, and whether
PyInstaller normalises it was unknown. Measured over two full builds: identical
across all ~1700 files. What is compared there is the contents of the folder,
file by file; a ZIP stores modification times and therefore cannot be
bit-stable, which is a property of the format rather than a hole in the claim.

### An icon

JamPilot has a symbol now — a pick with a note and a spectrum — and it shows up
everywhere the program does: in the control window and its taskbar entry, as
the favicon of the web display (and as the home-screen icon when you add the
page on your phone), on the Linux launcher that `jampilot install` writes, and
embedded in the Windows executable and the macOS app bundle. The Linux launcher
used to borrow a generic audio icon from the theme; it now installs its own
into `~/.local/share/icons` and removes it again with `--remove`.

### The big chord was too heavy on Windows

`#current` asked for `font-weight: 750`. Only fonts with a continuous weight
axis can give you that — SF Pro Display on macOS can, Segoe UI on Windows
cannot. CSS then searches upwards, finds no 800, and lands on **Segoe UI
Black**: at 52 vh the chord came out blocky and far too fat. It was the only
element on the page asking for more than 700, which is why it was the only one
that looked wrong. Now 700, a real face everywhere, and Windows 11's
`Segoe UI Variable Display` is preferred where it exists.

### The version number had three homes, and one of them was wrong

`jampilot/__init__.py` and `pyproject.toml` both said 1.1.1 and agreed — but
the third copy did not: `packaging/jampilot.spec` wrote a hardcoded **0.1.0**
into the macOS bundle's `Info.plist`, and had done since 0.1.0 was current. Two
releases of `JamPilot.app` reported a version two minors behind the program
inside them, and nothing could have caught it, because nothing compared them.

The number now lives in `__init__.py` alone. `pyproject.toml` reads it from
there (`tool.setuptools.dynamic`), the spec parses it out for the `Info.plist`,
and `build.ps1` uses it for the name of the ZIP. A value that is written once
cannot drift.

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

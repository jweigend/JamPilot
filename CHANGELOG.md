# Changelog

## 1.4.2 — 2026-10-14

The theme of this release: **the root.** Two fixes for the same symptom
seen from two sides: a slash chord on the chip and a big "A over D" in the
bass view where the band plays plain D. One comes from a guitar voicing,
the other from the bass player's own pickup note — and neither should
reach the screen. Every number below is measured, the tables live in
`tests/reference/README.md` and `tests/realaudio/`.

### The fifth in the bass needs a bass player

In the first verse of *If This Is Goodbye* (Knopfler/Harris) nobody plays
bass. The lowest string under the D shape is the open A (110 Hz); the
guitar's D sits an octave above the low band. The low band therefore reads
A, and every D of the verse came up as `D/A` — eight bars out of eight, in
bass mode as a big **A over D**. The ratio hurdle from 1.4.0 cannot help
here: there is no root below to compare against. Same class as `D/A` over
every D in *Eight Days a Week* and `D6/A` in *It's Too Late*.

The fifth is the only chord tone a guitar shape puts under the root by
itself; a third or a seventh in the bass is always deliberate. So only the
fifth now needs proof a guitar cannot give: at least 5 % of its low-band
energy in the **bass register** C1–D♯2 (32–78 Hz, below the low E string).
Without that proof the chord stays in root position. The real A pedal the
bass holds under D later in the same song (A1, 55 Hz) passes.

Offline on the reference set nothing moves (1 false slash in 385 chords,
11 of 27 inversions, unchanged). Live, fifth slashes before → after:
*If This Is Goodbye* 11 → 2, *Let It Be* 7 → 5, *Something* 8 → 7,
*It's Too Late* 10 → 10 (a bass plays there, the fifth does sound in the
register). A general register gate for every slash tone was measured and
rejected: it takes ten of the eleven inversions, because the bass
fundamentals of sixties recordings rarely reach below E2
(`tests/realaudio/REPORT_if_this_is_goodbye.md`).

### The pickup note no longer sticks to the chord

*Sailing to Philadelphia* in bass mode showed **E over F#m7** at the start
of every form, although the bass plays a clear F# from the downbeat on.
The chain: the bass plays an E pickup before the downbeat. The boundary
refinement pulls the F#m7 onset 0.3 s early onto that pickup (E is a chord
tone). The model sets F#m7 only on the downbeat and still says A at the
commit line, so the late-boundary rule from 1.1.0 enters A as a 50 ms blip
and F#m7 a second time. The blip rule from 1.4.1 keeps both out of the
events — but the blip has already cut the committed chord's bass window
from two seconds to a quarter second: exactly the pickup. There E is the
majority, E is a chord tone, and it lands on the event for good.

The late-boundary rule now recognises this as the same chord change, set
later by the model than by the refinement, and enters nothing: when the
re-reported chord is the one before the last committed event, the model
immediately leads the committed chord again, and its onset lies at most
0.75 s behind. No onset moves; a genuine `D – A – D` with a longer A is
still added as before.

Measured on the live path: *Sailing* loses all three `F#m7/E` and six
other wrong slashes (`A/C#`, `D/F#`, `E/B`) and gains nine bass roots. On
the reference set event count, timing, beats and bass-only hits are
unchanged, and the unannotated slashes go away: *It's Too Late* 15 → 1
(the `D/A` over every D6 known since August was the Am7 bass in the stub
before the downbeat), *Crazy Little Thing* 10 → 3, *Let It Be* 7 → 6;
*Something* gains the annotated `G/D` at 3.5 s. A minimum bass-window
length as a second hurdle was measured and rejected: no gain, costs the
roots of one-beat chords (`tests/realaudio/REPORT_sailing_to_philadelphia.md`).
The pickup fix was judged in the rehearsal room (Sailing to Philadelphia,
Telegraph Road); the fifth rule is measured on recordings so far.

### Smaller things

- Comfortably Numb (PULSE live version): the passing bass from 1.4.1 hits
  4 of 13 solo transitions; the rest are a too-short F# run or an `F#m`
  label from the model. Left as it is — Moises shows plain G → Em there
  too (`tests/realaudio/REPORT_comfortably_numb.md`).
- 648 tests (1.4.1: 633).

## 1.4.1 — 2026-09-15

The theme of this release: **calm.** A bugfix release for the flicker that
survived 1.4.0: the old chord popping back for exactly one beat right after
the new one was shown (`D – A – D – A`). Around it, two things the
rehearsal room asked for: the passing bass a chord model can never label,
and a control sound you can actually judge a chord by. Judged in the
rehearsal room before it was tagged; every number below is measured, the
tables live in `tests/reference/README.md`.

### The one-beat blip is gone

Since 1.4.0 chord boundaries snap to the beat, and that turned a small
artefact into a visible one: the refined boundary of the new chord is
published while the model's own boundary still lies a few frames later. At
the commit line the model still hears the old chord, the late-boundary rule
from 1.1.0 dutifully re-inserts it, and the new chord arrives a second time
— one beat later. What you saw: `A` for one beat between two `D`s, and the
`D` you needed landing a beat late.

Comparing 1.1.1, 1.4.0 and today's code on the reference set showed the
count of such short events had not risen since 1.1.1 — the retrained chord
model just draws more boundaries, and on the beat grid every blip is
exactly one beat long, which makes it look like a chord. So the publish
channel now knows the blip's signature: a chord that returns to the one
before the last event within about a beat, *while the timeline behind it
already shows the new chord again*, is dropped, and so is the repeat. The
first event stays where it was; nothing moves. Without that second look
the rule would also eat the return after a genuine short misfire
(`A – D – A – G`) — it did, in the first cut, in Comfortably Numb.

Live simulation, root accuracy of the displayed chord / events shorter
than 0.6 s per minute, 1.4.0 → 1.4.1:

| Track | Root | short events / min |
|---|---|---|
| Crazy Little Thing | 85 % → 86 % | 16.5 → 9.8 |
| Eight Days a Week | 96 % → 97 % | 2.7 → 1.2 |
| It's Too Late | 86 % → 88 % | 14.0 → 4.6 |
| Let It Be | 86 % → 87 % | 4.6 → 2.3 |
| Something | 80 % → 81 % | 12.2 → 4.2 |

Timing is unchanged. The remaining short events (about one per minute)
are real changes or single misfires that should stay.

### The passing bass: `G/F#` before `Em`

In the closing solo of Comfortably Numb the whole band holds an F# for half
a beat between `G` and `Em`. The chord model — trained on annotations that
write `G/F#` as plain `G` — keeps saying `G`, and no weights will change
that. The measured bass can: when the low band shows a note stepping
chromatically *between* the current root and the next one, stable for at
least three frames and ending with the segment, the segment gets a second
event with the same chord and that bass. The bass view shows a big
**F# over G** at the right moment; the chip reads `G/F#`. Six of the seven
solo passages get it (the seventh is torn into splinters by the model
itself). On the five reference tracks this adds five events in fourteen
minutes, three of them annotated, and changes nothing else
(`tests/realaudio/REPORT_comfortably_numb.md`).

### A pad instead of a pluck

The control sound in the gear menu is no longer a dry one-second guitar
pluck but a quiet keyboard pad that holds every recognised chord until the
next change, on exactly the stream clock of the delayed original. A pluck
is gone before the ear has judged it; a sustained third or seventh rubs
audibly against the original when it is wrong and sits inside it when it is
right. Full chord vocabulary, close voicing around C4 with the root an
octave below, synthesised locally (no sample files, JamPilot stays
offline), off by default and free when off. Details in
`docs/gitarrenmodus.md`.

## 1.4.0 — 2026-09-12

The theme of this release: **time.** JamPilot has always told you *what*
comes next; now it also tells you *where in the bar* — and the same pulse
pulls every chord change onto the beat it belongs to. Around it: a
retrained chord model, an audio path that no longer stutters on a
twenty-core rehearsal-room PC, and the bass that had gone quiet since
August speaks again. Judged in the rehearsal room before it was tagged.
Every number below is measured; methodology and raw results live in
`docs/exploration/tempo-und-takt.md`,
`docs/exploration/beat-tracking-ergebnisse.md`,
`docs/exploration/audio-aussetzer-analyse.md` and `tests/reference/README.md`.

### Bar lines: a beat tracker under the timeline

A learned beat tracker (Beat This!, ISMIR 2024, shipped as a 10 MB ONNX
model and run by ONNX Runtime in its own thread) listens alongside the
chord model. Under the lane you now get a faint tick per beat, the downbeat
a little taller, in a hint of the page's blue — the chip says *what* comes,
the ticks say *where in the bar*: is that `G` the start of the next bar, or
a change on the three? Three layouts were tried in the rehearsal room (a
line over the whole lane, an edge on the chip, ticks at the floor); the
ticks won, because everything else made the picture restless.

The ticks appear only while the pulse is steady and the downbeat has
settled — no tick is better than a wrong one, and a rubato ballad gets
none. Beats travel as a second publish-once channel next to the chords, so
a bar line, once drawn, never moves. Off in the gear menu (per device) if
you hear the one yourself.

The first thing you will notice with the ticks in place: **chords often
change on the four**, not on the one. That is not a bug. Vocals and lead
steer for the target chord a beat early, and JamPilot hears the whole mix.
A chord sheet writes the change on the bar line; the band plays it where
JamPilot shows it.

### The same grid halves the timing error

Every chord boundary now snaps to its nearest quarter note before it is
committed. Measured hop by hop against drift-corrected Isophonics
annotations, committed events only (median |Δt| / share within 93 ms):

| Track | 1.3.1 | 1.4.0 |
|---|---|---|
| Let It Be | 127 ms / 35 % | **70 ms / 71 %** |
| Eight Days a Week | 196 ms / 17 % | **61 ms / 59 %** |
| Something | 121 ms / 41 % | **48 ms / 80 %** |

Beat-F on the three tracks: 0.96 / 0.99 / 0.85. On the way there, two
things the measurement turned up were fixed: the chord model places its
boundaries systematically *before* the real change (a synthetic change at
exactly 5.000 s came out at 4.737 s, in every key), so boundaries are
shifted forward by one model frame before they enter the timeline, and
boundary refinement now searches forward as well as backward — it used to
pull a clean change on the one onto the previous beat's attack. Main
changes landing on the bar line in Telegraph Road: 45 % → 69 %.

The feasibility study that preceded all this is checked in
(`docs/exploration/tempo-und-takt.md`): librosa's beat grid hit only
23–54 % of the beats and was 100–200 ms off in phase, and estimating the
phase from JamPilot's own chord onsets did not rescue it — the phase has to
come from the audio. Hence the model.

### Chord recognition: model v7_2b

The weights are a distillation from a multi-view teacher (an iso-only
model over five Demucs stem views plus Viterbi), then retrained on a CQT
computed in one piece rather than 10-second chunks. That second step
removed a drift the old weights had learnt as a lead: 108 frames were
10.031 s, not 10 s, and the offline time axis drifted +31 ms per chunk.
`jampilot analyze` is now time-true; the live path (one window, one chunk)
was never affected.

| | 1.3.1 | 1.4.0 |
|---|---|---|
| Verdict share vs. ChordNet, 6285-song library radar | 48.1 % | **52.1 %** |
| Reference set, labels exactly right | 0.776 | 0.767 |
| maj7 / m7 | — | **0.81 / 0.95** (better) |
| Sixth chords | 0.47 | 0.16 (worse — teacher bias, the library has few standards) |

The reference set is a hair worse, the library a clear step better; the
trade was taken with eyes open. The retraining campaign, with the runs that
lost, is documented in `docs/exploration/nachtraining-kampagnen-2026-08.md`.

### Bass: it speaks again

Since the bass source moved to the chord model's low band on 8 August, the
measured bass had been empty for 60–90 % of live events — the bass view
showed the chord name, the fretboard the root. The fold that turns the
model's chroma into a bass note summed *both* bins per semitone, including
the one at +50 cents that carries the neighbouring note's leak, and the
majority threshold kept failing. The old CQT path had one bin per semitone
and never had this problem.

Only the on-note bins are folded now, and the root/slash ratio is 3.0
instead of 2.0 — with more signal, 2.0 let the fifth through as a slash (32
wrong on five tracks). Offline: empty segments 63 % → 33 %, false slashes
0.3 %, inversions unchanged at 44 %. Live on five tracks: 143 → **287**
correctly set basses, 12 → 17 wrong ones. Confirmed by ear in the rehearsal
room.

### Audio: no more stutter on the rehearsal-room PC

The rehearsal-room machine (a Z820, 2×10 cores) stuttered. Measured on the
machine itself, three causes, all fixed:

- **OpenBLAS spawned 40 threads**, twelve of which kept spinning at 57 %
  CPU after every matrix multiply: 609 % CPU for the process, load 11.6 —
  and the hop got *slower* (refinement 143 ms instead of 110). One BLAS
  thread is now set before NumPy is ever imported. After: 51 % CPU, load 2.
- **The output buffer was one block.** `latency="high"` gave 43 ms under
  PipeWire/ALSA, and a full garbage collection (36–74 ms) was longer than
  that. The stream now opens with a 0.2 s output buffer; the display stays
  exact because it computes from the DAC timestamp. Price: 0.2 s more total
  delay.
- **The first seconds dropped out twice, then never again.** The bundle
  unpacks into a fresh directory on every start, so numba's cache is always
  cold, and the refinement kernels compiled on the first chord change *with
  the stream running*: 4.4 s, the callback 55 ms late. Everything heavy now
  happens before the stream opens — refinement is warmed with a synthetic
  tone, the model is loaded, and the heap is frozen (`gc.freeze()` over
  181 000 objects: a full collection takes 0.1 ms afterwards instead of 59).

And the next diagnosis needs no guessing: the stream records the first 16
dropouts with stream second and PortAudio status, the start log names each
one ("Audio dropout 1 at 3.8 s: output underflow"), and the control window
shows a dropout counter in its info line — nothing at all if there were
none. Outside the code, the second cause on that machine was that nothing
in the audio path ran with realtime priority; the analysis document says
how to check.

### Record mode: choose the position

Pause in record mode (`P`) and small arrows under the fretboard step
through the alternatives for that spot: chord shapes on guitar (open,
barre), inversions on keyboard, string positions on bass. The choice is an
anchor on the event — the spot looks the same on every pass, and every
chord from there on is planned from the anchor, so the chorus can sit low
and the verse high. `↑`/`↓` do the same on the keyboard. Anchors go with
the recording when you leave the mode. Client-side, per device.

### Smaller things

- **The page on the music stand survives a restart.** The display
  reconnected by itself, but every control (record, mute, transport) still
  carried the old session token and ran silently into a 403. The token now
  lives in the config directory and is reused on every start; old URLs, QR
  scans and home-screen entries stay valid.
- **Clean exit.** `Ctrl+C` occasionally ended in a core dump because the
  process died while the beat worker was still inside ONNX Runtime. The
  worker is now joined on shutdown.
- **Measurement rules in the live-path harness.** "No event" for 13 % of
  annotated changes turned out to be almost entirely measurement error
  (repeated labels, bass-only changes, events one beat off beyond a rigid
  0.5 s window). The harness now counts a change as a chord change without
  the bass, matches to half a beat, and lets the delay drain at the end of
  the file. Real misses: 0–8 % per track.
- New dependency: `onnxruntime` (locked at 1.30.0). The bundle grows by the
  runtime and the 10 MB beat model.
- 597 tests (1.3.1: 468).

## 1.3.1 — 2026-08-30

The theme of this release: **trust.** A bugfix release for a rare but
corrosive failure: a passage clearly sits on one chord, yet JamPilot keeps
showing the previous one — for the whole passage. Nothing undermines
confidence in a chord display like a wrong chord that *stays*.

### Timeline: a late boundary can no longer fall behind the ledger

The chain that swallowed it, found by replaying the live loop hop by hop in
simulation: a boundary the model recognizes late enters the timeline just
beyond the commit line. Boundary refinement then pulls it backwards onto the
audible onset — by up to 0.40 s, while the ledger's waterline advances only
~0.25 s per hop. The refined boundary lands *behind* the waterline, and the
publish-once ledger, which only ever commits forward, never turns it into an
event. The internal timeline was right all along; only the display never
heard about it. The late-boundary correction from 1.1.0 could not rescue it
either — it checks the timeline, which *had* the boundary, not the events,
which did not.

The fix is one clamp: refinement may not move a boundary backwards across
the commit line. In the narrow band where this used to strike (~0.15 s per
hop), the event now lands *on* the commit line — up to 0.4 s later than the
audio says, the honest price for the event arriving at all. Everywhere else
the output is unchanged: the simulation scenarios around the band produce
identical events before and after. The refinement loop moved out of the live
loop into its own function on the way, so the new regression tests exercise
the real interplay of merge, refinement and ledger.

## 1.3.0 — 2026-08-30

The theme of this release: **record mode.** JamPilot has always shown you the
change — now it lets you *replay* it. Judged in the rehearsal room before it
was merged: for a beginner the fretboard diagrams move too fast live; with `R`
you learn the shape at your own pace, then the chord name is enough to play
along.

### Record mode: `R`, and a player for the change you did not catch

The one thing missing when you use JamPilot to actually *learn* a song: a
change goes by, you did not catch it, and there is no way to hear it again
without reaching for Spotify. `R` starts record mode. From then on what you hear
is kept in a buffer inside the app, and you get a player: `←`/`→` jump to the
**previous and next chord** — `←` going first to the start of the *current*
chord like a CD player, and again to the one before, which is how you hear a
change coming — `P` pauses, `Home`/`End` go to the start of the recording and
back to live. The same five buttons sit as a half-transparent bar at the bottom of the
display, so a phone on the music stand can drive it too (it cannot *enter* the
mode: `R` is a key, deliberately). The only other sign of the mode is a small
red dot by the logo — no seconds, no bar; where you are in the recording, the
music tells you. `R` again leaves: back to live, buffer discarded.

The buffer holds **30 minutes** (one side of a traditional album), lives only in
RAM, and is reserved **on the first `R`** rather than at startup — in a
background thread, because a page fault over 660 MB inside the audio callback
would be a dropout, and because paying that in every session for a mode most
sessions never enter would be exactly the bloat this feature is being judged
for. Too little memory leaves `R` inert with a note in the log.
`--record-buffer <minutes>` resizes it, `0` turns it off.

Architecturally it is a **separate stage behind the delay buffer**, not a change
to it: the delay is the time base the analysis computes its commit boundary on,
and letting it grow would force the chord timeline to hold minutes of future
through a merge that is quadratic in its length. With `R` off the stage returns
before touching a byte, the output is bit-identical, and the display clock is
the same function as before — the mode costs a session that never uses it
nothing but a key nobody else had claimed.

**Mute became a real mute.** It used to freeze the big chord and dim the lane —
a stand-in for "let me look at this chord" when there was nothing better. Now
there is, so `Space` (or `M`) means sound off and nothing else; every view keeps
running. The button lost its play/pause icons with it (a speaker now), which
also fixes a stale selector that had been drawing both icons on top of each
other while muted.

Also part of this work: the audio callback survives blocks that are larger or
smaller than the one announced at stream creation (the mute fade and the
crossfades clamp to what is actually there); a chord held longer than eight
seconds no longer drops out of the published window and shows "No music"; and
the display clock hard-resets on every jump instead of easing into it — the
easing exists to absorb network jitter and would have shown the wrong position
for about ten seconds after every rewind.

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
*Now playing C/E · next G in 1.3 s · Key C major*. Small and grey on purpose: the
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

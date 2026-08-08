# JamPilot — jam along with anything, in real time

**Ever wanted to just grab your instrument and play along with whatever is coming
out of your computer?** Spotify, YouTube, the MP3s on your disk — the live take
nobody ever wrote a chord sheet for, the B-side that no tutorial will ever cover.
Not "look it up, learn it, come back next week". *Now.*

That is the whole idea. Whatever plays on your machine, JamPilot listens to it
and **shows you the chords while it runs** — and it shows them **before you hear
them**, so you are never a beat behind. Practise, learn a tune, or just play
along for the fun of it.

**No more googling for chords.** No transcription, no tutorial, no waiting a
week. Press play, and play.

Two things worth knowing before you start, because you would find them out anyway:

- **You hear the song a few seconds late.** That is not a glitch, it is the deal:
  those seconds are what the analysis spends on the part you have not heard yet,
  and they are what gets the chord onto your screen *before* your ears get the
  music. The price is that JamPilot is for playing along with your machine — not
  for jamming with someone else in the room, and not for staying in sync with a
  video you are also watching.
- **Chords, not tabs.** JamPilot names the harmony — `Bm`, `C`, `D`, and the bass
  note under it if you want (`C/E`). It does not give you riffs, fingerings or
  solos. It hears a full working vocabulary — triads, sevenths, `sus`, `dim`,
  `aug`, `6` — with pop, rock, blues, folk as its home turf. Extensions beyond
  the seventh (`9`, `13`, altered notes) are folded into their core chord, so on
  a Real Book standard it will simplify what it hears. Why recognition works the
  way it does — and why it can never be 100 % — is the story of
  [HOW-IT-WORKS.md](HOW-IT-WORKS.md).

Written entirely in Python and platform-independent — fully tested on Linux, also
running on macOS, with Windows explored ([see the table](#platforms)). It all
happens on your own machine — no account, no cloud, nothing uploaded anywhere.

---

**How, in one paragraph:** JamPilot taps your system audio, holds it back for a
few seconds, and plays it to your speakers **delayed but otherwise untouched**.
What it *analyses*, though, is the fresh signal — the part you have not heard
yet. So the chord is on your screen **seconds before it reaches your ears**.

You stop chasing the song. You see what is coming and play it.

![The web display: the audible chord large in the centre, the coming chords running towards the NOW line](docs/bilder/web-anzeige.png)

*The chord you hear right now is the big one — `Bm`. `C` arrives in 1.3 seconds,
`D` in 3.2 — enough time to get your hand there. Top left, the key JamPilot has
worked out (G major); top right, a QR code to put the same display on your phone.*

```
System audio ──► ring buffer (N s) ──► speakers (delayed, unchanged)
      │
      └──► chord analysis ──► chord display (N s of lead)
```

The delay is not a defect to be minimised. **It is the feature**: it buys the
analysis a few seconds of the future, and it buys the player time to react. Four
seconds is a good default — long enough to see a change coming, short enough that
you still feel like you are playing *with* the record.

## What you see

**The display in the browser** is where you play. It opens by itself at
`http://<your-machine>:8765/` and is built to be read from across the room, in a
glance, while both your hands are busy:

- **The big chord in the centre** is what is sounding **right now**, in sync with
  what your speakers are putting out — not what the analysis is chewing on.
- **The lane at the bottom** is the future, moving right to left towards the
  `NOW` line. Each chord carries its countdown (`in 1.3s`). A chord flips to the
  centre in exactly the frame in which its chip touches the line — big chord and
  lane run off the same clock, so they cannot drift apart.
- **The key badge**, top left, once there is enough music to be sure of it.
- **The QR code** — scan it with a phone on the same Wi-Fi and you get the same
  display on your music stand. The computer does the listening; every other
  device is just a screen.
- Click or tap for fullscreen, `Space` to mute. The **gear** switches spelling
  (♯/♭) and the instrument mode (chords, bass or guitar) — both are per-device,
  so your phone and your laptop may disagree.

**The control window** opens next to it — a small native window, and it is not
the main interface. It is the **way back**:

![The control window: state, the routing switch, the mute switch, delay and measured lead](docs/bilder/kontrollfenster.png)

JamPilot reroutes your system sound while it runs. Close the browser tab and,
without this window, there would be no UI left at all: your sound is delayed, or
silent, and nothing on screen tells you why. So the big switch at the top,
**Audio through JamPilot**, is the panic button — off, and your system sound is
normal again, immediately. Below it, **Sound** mutes only the delayed output (the
music and the chords keep running; you just hear nothing). Underneath: the state,
the delay, and the **lead actually being measured** — 3.9 seconds in the shot
above, which is how far ahead of your ears the display is running.

Closing the window quits JamPilot, and that restores your audio. Leaving it
running invisibly in the background is precisely the trap the window exists to
prevent.

Muting is *not* pausing, and the difference matters: the ring buffer keeps
running. Pausing it would silently mean "increase the delay" — you would drift
further behind the song with every muted second, and the lead, the whole point of
the program, would be gone.

`--no-window` runs without it (terminal only). Over SSH or in CI, where there is
no display, that happens by itself.

## Get it running

One script, straight from a fresh clone — Linux and macOS:

```bash
git clone https://github.com/jweigend/JamPilot.git && cd JamPilot
./run.sh                     # sets everything up on the first call, then starts
```

**The first call takes about a minute** — it creates `.venv` and installs the
locked dependencies. **Every call after that starts in well under a second.** A
stamp inside `.venv` records which lock file and which Python it was built
against; if that still matches and every package is present, there is nothing to
do and the script gets out of the way.

If it *doesn't* match, the script repairs it instead of failing at you — and that
is the whole point of it. A lock file that changed, a Python that was upgraded out
from under the venv, an install someone interrupted with Ctrl+C, a `site-packages`
that lost a package: each of these used to end in a message that named the symptom
(`No module named librosa`) and not the cause, days later. The stamp is written
*only after* a successful install, so a half-built environment is never mistaken
for a finished one.

```bash
./run.sh --delay 6           # any option of `jampilot run`
./run.sh selftest            # any other command: devices, analyze, cleanup ...
./run.sh --bundle            # standalone binary + double-click launcher -> dist/
./run.sh --neu               # throw the environment away and start over
```

`run` options: `--delay` (seconds), `--output` (target sink/device), `--input` +
`--no-route` (direct mode without automatic routing), `--samplerate` (default
48000), `--port` (web display, default 8765), `--no-web`, `--no-window`.

Then just play something — a YouTube video, Spotify, anything that makes sound —
and watch the chords arrive before it does.

### Platforms

JamPilot is written **entirely in Python and is platform-independent**: the
capture, the delay buffer, the chord analysis, the control window and the web
display are the *same* code everywhere. The only part that differs per operating
system is how the system sound is tapped silently — and even that already has a
portable path (`--no-route` with an explicit loopback device).

| Platform | Status | Notes |
|---|---|---|
| **Linux** | ✅ Fully tested | The reference platform. Automatic null-sink routing via PipeWire/PulseAudio (`pactl`). |
| **macOS** | 🟡 Developed, incompletely tested | Runs via [BlackHole](https://existential.audio/blackhole/) as the loopback driver (`--no-route`). Built, but not exhaustively verified on hardware. |
| **Windows** | 🧭 Explored, not yet implemented | The core already runs unchanged; only silent capture is missing (VB-CABLE + `--no-route`). See [`docs/exploration/windows-portierung.md`](docs/exploration/windows-portierung.md). |

The one thing the script cannot install for you is **PortAudio**, because it is a
system library and not a Python package (`sudo apt install libportaudio2`,
`brew install portaudio`). It checks for it and says so, rather than letting
`sounddevice` fail with "PortAudio library not found". On macOS you also need
[BlackHole](https://existential.audio/blackhole/) — see below.

## How it works

1. **Capture**: System audio is tapped — on Linux through the monitor of a
   PipeWire/PulseAudio null sink, on macOS through a loopback driver
   (BlackHole).
2. **Delay**: A ring buffer exactly one delay long; at the write position the
   old value is played out and the new one written. The signal is not altered,
   only shifted. When a source starts playing after a longer silence — press
   play in Spotify, and for the length of the delay the speakers are
   necessarily still silent, which looks like failure — a short **count-in**
   is played into that gap: one beep per remaining second (3 – 2 – 1, the last
   one accented), then the music arrives. A break inside a song does not
   trigger it: the count-in only fires when the silence was at least one full
   delay long, so the output really is quiet until the new material lands.
3. **Analysis**: The chord labels come from a **learned model** — BTC, a small
   bidirectional transformer for chord recognition (Park et al., ISMIR 2019),
   ported to pure NumPy (`btc.py`, 12 MB of weights, no PyTorch). Every 250 ms
   it labels the most recent 10 seconds of the fresh signal: **14 chord
   qualities × 12 roots**, from plain triads to `m7b5` and `dim7`. The model
   replaced the original chroma-template matcher after measurements on
   hand-annotated recordings — the error rate on chord labels was cut in half,
   and the old maj7 bias (overtones faking sevenths) disappeared. The full
   story, numbers included, is in [HOW-IT-WORKS.md](HOW-IT-WORKS.md).
   **Which** of those notes lies at the bottom is a separate question, answered
   by a separate signal: a **bass chroma** over 32–260 Hz, folded out of the
   same CQT the model consumes (`bass.py`). Only that measurement makes
   inversions visible — `C/E` is not in any chord label, and deriving the bass
   from the chord instead of measuring it wrecked every inversion when it was
   tried.
4. **Timing**: The model says *what* is sounding on a ~93 ms grid — and it
   tends to place a boundary *behind* the audible change. So every fresh
   boundary is refined once: within an asymmetric search window (far back,
   barely forward), a chord-tone cut through a 23 ms HPSS chroma — weighted by
   onset strength, so the cut lands on an attack — pulls the boundary onto the
   audio event (`refine_boundary`). Measured against hand-annotated changes,
   that takes the median error from 187 ms to 117 ms without ever pushing a
   boundary late into the bar.
   A segment shorter than **250 ms** is not a chord, it is flicker of the
   recogniser, and it is merged away. Because the lead shows every chord
   seconds before it becomes audible, a corrected reading is *withdrawn* rather
   than flashed on screen — what has already been heard stays untouched.
   How far the output lags is taken from PortAudio's **DAC timestamps**, not
   from the reported latency — which was off by 60 ms in testing. Analysis
   windows always end on a fixed stream grid; if an analysis takes too long, a
   grid point is dropped and the grid stays exact.
5. **Display**: `In 2.9s: G | Now playing: C`. The browser receives the chords
   with their onset in stream seconds plus the currently audible position, syncs
   its clock against it with a minimum filter (NTP principle: delivery time is
   always positive) and derives **the big chord and the running lane from the
   same clock**. They cannot drift apart: the chord flips in exactly the frame
   in which its chip touches the NOW line.

### Audio routing on Linux (automatic)

Tapping the monitor of the normal output and playing the delayed signal back to
that same output would give you the original plus the delay plus an echo
cascade. So `jampilot run` temporarily installs a **null sink** as the default
output: players play into it inaudibly, JamPilot reads its monitor and sends
only the delayed signal to the real hardware. On exit (including `kill`)
everything is restored.

Setup is **transactional**: every step is registered before the next one runs;
if one fails, everything unwinds backwards. Otherwise the silent null sink would
be left behind as the default output — `with` does not call `__exit__` if
`__enter__` throws. A `SIGKILL` cannot be caught by design; that is what
**`jampilot cleanup`** is for: it removes orphaned sinks and restores the
default output. `run` cleans up at startup, *before* it remembers the current
output — otherwise it would save the muted state left by a crashed predecessor
as the "previous state" and restore that on exit.

A sink counts as orphaned only if its **owner process is dead**. Who created it
is recorded in `/tmp/jampilot-<uid>.pid`; without that check a second instance
would unload the sink of a running first one, and the two would tear each
other's routing apart. A second start therefore fails with a clear message
instead of doing damage (`cleanup --force` overrides it if needed).

### macOS

Install [BlackHole (2ch)](https://existential.audio/blackhole/), then:

- set the system output to "BlackHole 2ch" (it takes the role of the null sink),
- `jampilot run --no-route --input "BlackHole 2ch" --output "MacBook Pro Speakers"`.

`jampilot devices` lists the device names.

## Standalone binary

A single executable, no Python and no venv on the target machine:

```bash
./run.sh --bundle          # -> dist/jampilot + dist/JamPilot.desktop
./dist/jampilot selftest   # verifies the bundle (the build already ran this)
```

**It only builds when it has to.** A stamp in `dist/` holds the fingerprint of
the sources the binary was made from (`jampilot/*.py`, the spec, the entry point,
the lock file). Unchanged, `--bundle` returns in under a second instead of three
minutes — and it would have produced the identical bytes anyway, which is exactly
what `--check` below proves. `--force` builds regardless.

### Double-clicking it (Linux)

**Double-click `dist/JamPilot.desktop`, not `dist/jampilot`.** Double-clicking the
binary itself does nothing at all — no window, no message, no error — and that is
not a bug in JamPilot: a Linux file manager will not run a binary. `dist/jampilot`
has the MIME type `application/x-executable`, no application is registered for it,
and the "run this file?" prompt (`executable-text-activation`) exists only for
executable *text* files. Nemo and Nautilus simply do nothing.

The launcher is the mechanism Linux provides for this. `packaging/build.sh` writes
it next to the binary; to get JamPilot into the application menu instead:

```bash
./dist/jampilot install            # -> ~/.local/share/applications/jampilot.desktop
./dist/jampilot install --remove   # takes it back out
```

Started this way there is no terminal, so the **window has to be the feedback** —
which is why it now opens *before* the ~3 s numba warmup rather than after it.
Between the `--onefile` unpacking and the warmup, the old order left a
double-clicker staring at an empty screen for five seconds, which looks exactly
like a program that failed to start (and invites a second double-click).

**~183 MB, ~2.5 s to start.** The size is librosa's doing — it drags in numba and
llvmlite (206 MB of JIT compiler) plus scipy and scikit-learn, and none of it can
be excluded: librosa imports all of it on our code path even though we call none
of its functions. Qt adds ~46 MB on top, after throwing out every module the
control window does not touch. The startup cost is `--onefile` unpacking itself
into a temp directory on every launch. For a tool you start once per session and
leave running, that is the right trade; if you want a 0.45 s start, build
`--onedir` instead and ship a folder.

The build is **reproducible**: same commit, same lock file, same platform → the
same bytes. `packaging/build.sh --check` proves it by building twice and
comparing the SHA-256.

`dist/jampilot selftest` is the test that matters here: it drives librosa, numba
and both CQTs without needing a sound card, so it trips over any module
PyInstaller failed to collect. Run it after every change to the spec.

**Builds do not cross-compile.** PyInstaller bundles the native libraries of the
machine it runs on, so a Linux binary needs Linux, and macOS needs a Mac —
separately for Intel and Apple Silicon. `.github/workflows/build.yml` does all
three on tag push.

What the binary still cannot bring with it, because these are system components:

- **macOS** — [BlackHole](https://existential.audio/blackhole/) must be installed
  separately (it is an audio driver, not a library). Also: an unsigned binary
  downloaded from the internet is quarantined by Gatekeeper. Either
  `xattr -d com.apple.quarantine jampilot` on first use, or sign and notarise it
  with an Apple Developer account. Started from a terminal, JamPilot inherits the
  terminal's microphone permission; a double-clickable `.app` would need its own
  `NSMicrophoneUsageDescription`.
- **Linux** — `pactl` (PipeWire/PulseAudio) is called as an external program for
  the null-sink routing. Without it, use `--no-route --input <device>`. The glibc
  of the build machine is the *minimum* on the target, so build on the oldest
  distribution you want to support.

## Web display, under the hood

What the page *shows* is described above. What it *is*: an embedded HTTP server
with server-sent events, no framework, no CDN, fully offline-capable — it has to
work on a stage with no internet. The browser is a pure display: it receives the
chords with their onset in stream seconds plus the currently audible position,
syncs its clock against that with a minimum filter (the NTP principle: delivery
time is always positive), and derives **both** the big chord and the lane from
that one clock. `?demo=1` renders the page with example chords and no running
analysis — handy for working on the layout.

## Chord spelling: ♯ or ♭ (key detection)

The same key on the piano is called **A♯ or B♭** depending on the song — the
pitch class alone does not decide that, the **key** does: in D major it is an
A♯, in F major a B♭. And once the key is known, there is exactly *one* good
spelling for every chord; it does not have to be reinvented per chord.

So detection and naming are **two separate steps**:

1. **Signal** (`chords.py`) → pitch class as a number 0..11 plus chord quality.
   The name carried by `ChordResult` is a canonical **ID** (always spelled with
   sharps), not a display string — it keeps the timeline comparable.
2. **Music** (`tonality.py`) → the most likely key from a pitch-class histogram
   (Krumhansl-Schmuckler, 24 major/minor profiles), and from it **one** spelling
   decision for the whole display.

For the first ~12 seconds of music, detection deliberately reports **no key at
all**: a histogram built from two chords fits half a dozen keys, and a guessed
key would be worse than none — it would spell the chords wrong and then switch
spelling mid-song. Until then, sharps apply. After that, detection also follows
a **modulation** (the histogram decays with a ~30 s half-life), but stays
sluggish enough not to flicker between relative keys (C major / A minor).

The browser receives the chords canonically plus the detected key and does the
spelling itself — **via the gear icon in the top right**:

| Setting | Effect |
|---|---|
| **Automatic** (default) | follows the detected key; the key is shown top left |
| **Always sharps** | C♯ · D♯ · F♯ · G♯ · A♯ |
| **Always flats** | D♭ · E♭ · G♭ · A♭ · B♭ |

The choice takes effect immediately and retroactively on everything already on
the lane, survives a reload (`localStorage`) and applies **per device** — laptop
and phone may be set differently. Terminal and `analyze` always follow the
detected key.

## Your instrument: chords or bass

The chord says what the **band** plays. It does not say what a **bass player**
plays: in C/E the chord is C, and the bass sits on E. That difference is not in
the chord name — and it is the one thing human annotators disagree about most.

So JamPilot **measures** the bass rather than deriving it from the chord. The
gear menu switches the display:

| Mode | Large on screen | Lane |
|---|---|---|
| **Chords** (default) | the audible chord | `C` |
| **Bass** | the **measured bass note**, chord as context | `C/E` |
| **Guitar** | the audible chord, with a **fretboard diagram** top-left | `C` |

In **Guitar** mode the display adds the one thing a chord name leaves out: *where*
to put your hand. A fingering diagram appears top-left, and — because the same
harmony lives in several positions on the neck — the voicing is not picked in
isolation but with the lead: a short Viterbi search over the coming chords chooses
the path with the least hand travel, so you keep playing in one position instead
of jumping across the neck between chords (see
[`docs/exploration/gitarrenmodus-lagen.md`](docs/exploration/gitarrenmodus-lagen.md)).
The complete design and current behaviour of the safe guitar mode are documented in
[`docs/gitarrenmodus.md`](docs/gitarrenmodus.md).

The diagram is deliberately conservative when the audio cannot reliably decide
between nearby readings. If A major and A minor are almost equally plausible,
JamPilot shows a playable A5 shape (A and E) and mutes the uncertain third instead
of asking the guitarist to guess C or C#. An uncertain seventh is omitted in the
same way. The optional **control guitar** in Settings plays exactly this safe set
of pitch classes over the quieter delayed original, making a bad recommendation
immediately audible without pretending to reconstruct the recorded fingering.

![The guitar display: the fretboard diagram for the current chord top-left, the big chord in the centre, the coming chords in the lane below](docs/bilder/gitarrenmodus.png)

*Guitar mode: `F` is sounding — its barre-chord shape at the 1st fret is drawn
top-left — while `Gm` and `C7` approach in the lane.*

The measurement is free: the analysis already computes a low-band chroma
(32–260 Hz) and used to throw it away. Keeping it costs memory, not CPU —
**0.03 ms** per analysis tick.

*On the method:* the bass-transcription literature recommends pYIN on a
band-passed mix. That was tried and rejected, with numbers: on dense voicings —
chord tones sitting right above the bass, i.e. the normal case in real music —
YIN drops to 4/12, because it estimates the period of the *mixture*. The low-band
CQT chroma gets 60/60 on the same material and costs nothing, because a
constant-Q transform uses long windows at low frequencies by construction. See
`bass.py`.

## Project layout

```
run.sh             the one entry point: sets up, starts, builds (--bundle)
jampilot/
  btc.py           the chord recogniser: BTC transformer (NumPy port) + boundary refinement
  data/            model weights (btc_large_voca.npz) and the web page (index.html)
  chroma.py        FFT → chroma vector (12 pitch classes), CQT frame chroma
  chords.py        chord templates, matching, smoothing, onset search (legacy path)
  bass.py          the measured bass note → inversions / slash chords
  tonality.py      key detection → spelling (♯ or ♭)
  delay_stream.py  duplex stream with the delay ring buffer (sounddevice/PortAudio)
  routing.py       null-sink routing for Linux (pactl), transactional
  engine.py        routing + stream + analysis as one switchable thing
  gui.py           the control window (Qt) - the way back when the page is closed
  desktop.py       the .desktop launcher - the way in, for a double-click
  web.py           SSE server; the page it serves lives in data/index.html
  selftest.py      synthetic chords as a pipeline test
  cli.py           command-line frontend, timeline logic
packaging/
  venv.sh          the environment, stamped: expensive once, free afterwards
  build.sh         the reproducible build (and it skips when nothing changed)
  jampilot.spec    PyInstaller: one file on Linux, a real .app on macOS
tests/             pytest suite (353 tests)
docs/exploration/  design documents (in German)
```

Code comments, tests and the design documents are written in **German**;
everything a user sees is English.

## Tests

```bash
./run.sh selftest                 # the pipeline, no sound card needed
.venv/bin/python -m pytest        # the suite (353 tests)
```

The suite covers the places where bugs creep in *quietly*:

- **The recogniser port** (`test_btc.py`) — the NumPy port reproduces the
  original Torch model bit-exactly on a golden window; segment merging and
  boundary refinement behave.
- **Onset accuracy** (`test_onset_accuracy.py`, `test_frame_history.py`) — pins
  down that a chord change is found to within < 100 ms and with < 50 ms spread.
  Fires as soon as anyone touches the window, the pooling or the onset search.
- **Timeline** (`test_timeline.py`) — no segment under 250 ms; misfires are
  withdrawn, genuine 0.5 s changes survive.
- **Smoother** (`test_chords.py`) — a tie yields `"?"` instead of a guess
  (this used to be decided by `PYTHONHASHSEED`).
- **Key detection** (`test_tonality.py`) — F major spells B♭, not A♯; no key is
  reported before there is enough music; a modulation is followed, but relative
  keys do not flicker.
- **Ring buffer & DAC clock** (`test_delay_stream.py`) — wraparound, bounds,
  fallback to the latency estimate when timestamps are unusable.
- **Routing** (`test_routing.py`) — rollback on failure in *every* step, orphan
  detection, protection against a second instance.
- **SSE backpressure** (`test_web.py`) — a slow client gets the *newest* state,
  not the oldest.
- **The way back** (`test_gui.py`, `test_engine.py`) — closing the window tears
  the routing down; `kill`, Ctrl+C and a closed terminal (SIGHUP) leave the Qt
  loop; and an **interrupt during startup** unwinds what was already built. Both
  were real bugs, both left the machine **silent**: the signal handler raised
  `KeyboardInterrupt`, which PySide6 swallowed inside a slot (JamPilot survived
  SIGTERM — only `kill -9` ended it, and that skips every cleanup); and the
  rollback in `engine.py` caught `Exception`, which a `KeyboardInterrupt` is not
  — so Ctrl+C during the seconds it takes to open the audio device left the null
  sink installed as your default output.
- **The launcher** (`test_desktop.py`) — a `.desktop` file with the right
  absolute path, quoted, executable, and `Terminal=false`.

## Roadmap

- More controls in the web display: lead slider, on/off, device selection (right
  now only the spelling lives there; the rest of the control is in the CLI).
- An incremental CQT in the live path — the 10 s analysis window is currently
  recomputed from scratch every 250 ms, and that is the biggest lever for old
  hardware.
- An honest look at music outside the model's training terrain (see
  [HOW-IT-WORKS.md](HOW-IT-WORKS.md) on why a learned recogniser has a home
  style).
- Turn the last stage from a chord *detector* into a **harmonic interpreter** —
  one that decides from key, bass, chord history, metre and genre which chord is
  most *useful to the player*, and that uses the lead to revise its own display
  before anyone has seen it. See
  [`docs/exploration/harmonischer-interpreter.md`](docs/exploration/harmonischer-interpreter.md).
- macOS convenience: automatic BlackHole device detection.

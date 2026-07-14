# JamPilot — jam along with anything, in real time

A tool for musicians: system audio (YouTube, Spotify, your own files, …) is
buffered for a few seconds and then played back **delayed but unchanged**. The
*fresh* signal is what gets analysed — so the chord is on screen **before you
hear it**. You can play along instead of chasing the song.

```
System audio ──► ring buffer (N s) ──► speakers (delayed, unchanged)
      │
      └──► chroma analysis ──► chord display (N s of lead)
```

The delay is not a defect to be minimised. It is the feature: it buys the
analysis a few seconds of the future, and it buys the player time to react.

## How it works

1. **Capture**: System audio is tapped — on Linux through the monitor of a
   PipeWire/PulseAudio null sink, on macOS through a loopback driver
   (BlackHole).
2. **Delay**: A ring buffer exactly one delay long; at the write position the
   old value is played out and the new one written. The signal is not altered,
   only shifted.
3. **Analysis**: A 1.5 s window of the fresh signal goes through **harmonic
   separation** (HPSS — removes drums/percussion) and a **constant-Q chroma**
   analysis (librosa, 36 bins/octave — logarithmic resolution also catches low
   roots). The chord is decided by the pitch-class *set* alone; **which** of
   those notes lies at the bottom is a separate question, answered by a separate
   signal — a **bass chroma** over 32–260 Hz (`bass.py`). Letting the bass vote
   on the chord used to be a `BASS_BONUS`, and it wrecked every inversion: it
   dragged the root onto the bass note, turning C/E into Em and F/A into Am —
   chords promising notes (the B in Em, the E in Am) that are not being played.
   Measured, it prevented not one wrong note and caused three. The
   result is matched against chord templates (major, minor, 7, maj7, m7 × 12
   roots); four-note chords must beat the triad by a calibrated margin, because
   overtones fake sevenths. A majority vote over the last three detections
   suppresses flicker. The selftest measures both pipelines on synthetic
   material with drums and a melody: FFT fallback 1/8, HPSS+CQT 8/8.
4. **Timing**: A detection says *what* is sounding — not *since when*.
   Back-computing the onset from the detection latency fails, because that
   latency varies with the material. So the change is *searched for*: the CQT
   frame chroma (23 ms grid, computed anyway) is cut at the point that best
   splits it into "before = old chord" / "from here = new chord". That puts the
   onset within ±30 ms instead of on the analysis tick (~500 ms).
   The search runs over a **frame history**, not just the current 1.5 s window:
   how long detection takes depends on the material — for ambiguous changes
   (C/Am, G/Em) it exceeds 1.5 s. If the search cannot reach back to the onset,
   it clamps to the start of the window, and that error is **one-sided**: the
   display is late, never early. Measured: at 2 s of detection latency, the
   window-only search reported the change up to 600 ms late; with the history
   the error stays at −30 ms, regardless of latency. The frames are merely kept
   — no extra CQT (9 µs and 13 KB per tick).
   How far the output lags is taken from PortAudio's **DAC timestamps**, not
   from the reported latency — which was off by 60 ms in testing. Analysis
   windows always end on a fixed stream grid; if an analysis takes too long, a
   grid point is dropped and the grid stays exact.
   A segment shorter than **250 ms** is not a chord, it is a misfire of the
   detector. Because the lead shows it seconds before it becomes audible, it is
   *withdrawn* rather than flashed on screen; the chord that takes its place
   inherits the earlier onset (*when* the change happened was already settled —
   only *what* is played gets corrected). A chain of misfires therefore
   converges on a single change without moving its time.
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

## Install & use

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python -m jampilot selftest         # test detection without audio
.venv/bin/python -m jampilot devices          # list devices
.venv/bin/python -m jampilot analyze song.wav # analyse a WAV offline
.venv/bin/python -m jampilot run --delay 4    # live, with 4 s of lead
.venv/bin/python -m jampilot cleanup          # remove a null sink after a crash
```

`run` options: `--delay` (seconds), `--output` (target sink/device), `--input` +
`--no-route` (direct mode without automatic routing), `--samplerate` (default
48000), `--port` (web display, default 8765), `--no-web`.

## The control window

`run` opens a small native window (Qt). It is not the main interface — you play
by the web display — it is the **way back**.

JamPilot reroutes your system sound: everything goes into a null sink that only
JamPilot listens to. Close the web page, and there is no UI left: your sound is
delayed, or silent, and nothing on screen explains why. The window is the switch
that undoes it.

- **Audio through JamPilot** — off tears the routing down and your system sound
  is normal again, immediately. This is the panic switch.
- **Sound** — mutes the delayed output. The music keeps playing and the chords
  keep running; you just hear nothing. Same thing as `Space` on the web page.
- Status (Running / Muted / Stopped), delay, measured lead, and a link to the
  web display.

Closing the window quits JamPilot — and so restores your audio. Leaving it
running invisibly in the background is exactly the trap the window exists to
prevent.

Muting is *not* pausing, and the difference matters: the ring buffer keeps
running. Pausing it would silently mean "increase the delay" — you would drift
further behind the source with every muted second, and the lead, the whole point
of the program, would be gone.

`--no-window` runs without it (terminal only). Over SSH or in CI, where no
display exists, that happens automatically.

## Standalone binary

A single executable, no Python and no venv on the target machine:

```bash
pip install pyinstaller
pyinstaller packaging/jampilot.spec --noconfirm   # -> dist/jampilot
./dist/jampilot selftest                          # verifies the bundle
```

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

## Web display

`run` automatically starts a fullscreen web display (`http://<machine>:8765/`,
the URL is printed at startup): black background, the currently **audible**
chord large in the centre, the **upcoming** chords running along the bottom lane
towards the NOW line. Top right a QR code — a phone on the same Wi-Fi scans it
and shows the same display (the computer analyses, every device is a pure remote
display). Click/tap = fullscreen. Under the hood: an embedded HTTP server with
server-sent events, fully offline-capable (no CDN); `?demo=1` shows the page with
example chords and no running analysis.

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
jampilot/
  chroma.py        FFT → chroma vector (12 pitch classes), CQT frame chroma
  chords.py        chord templates, matching, smoothing, onset search
  bass.py          the measured bass note → inversions / slash chords
  tonality.py      key detection → spelling (♯ or ♭)
  delay_stream.py  duplex stream with the delay ring buffer (sounddevice/PortAudio)
  routing.py       null-sink routing for Linux (pactl), transactional
  engine.py        routing + stream + analysis as one switchable thing
  gui.py           the control window (Qt) - the way back when the page is closed
  web.py           SSE server + fullscreen display with the timeline
  selftest.py      synthetic chords as a pipeline test
  cli.py           command-line frontend, timeline logic
tests/             pytest suite (220 tests)
docs/exploration/  design documents (in German)
```

Code comments, tests and the design documents are written in **German**;
everything a user sees is English.

## Tests

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

The suite covers the places where bugs creep in *quietly*:

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

## Roadmap

- More controls in the web display: lead slider, on/off, device selection (right
  now only the spelling lives there; the rest of the control is in the CLI).
- Better detection: sus/dim/aug templates, inversions (slash chords),
  beat-synchronous segmentation.
- Turn the last stage from a chord *detector* into a **harmonic interpreter** —
  one that decides from key, bass, chord history, metre and genre which chord is
  most *useful to the player*, and that uses the lead to revise its own display
  before anyone has seen it. See
  [`docs/exploration/harmonischer-interpreter.md`](docs/exploration/harmonischer-interpreter.md).
- macOS convenience: automatic BlackHole device detection.

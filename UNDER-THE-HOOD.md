# JamPilot, under the hood

This is the engineering companion to the [README](README.md). The README tells
you what JamPilot does and how to run it; [HOW-IT-WORKS.md](HOW-IT-WORKS.md)
tells the story of the chord recognition itself. This document is about how the
machine around it is built: the audio routing, the timing, the launcher
scripts, the packaging — and the reasons things are the way they are, including
the failed attempts.

Code comments, tests and the design documents in
[`docs/exploration/`](docs/exploration/) are written in **German**; everything
a user sees is English.

## The pipeline, in detail

1. **Capture**: System audio is tapped — on Linux through the monitor of a
   PipeWire/PulseAudio null sink, on Windows through a WASAPI loopback tap on
   the muted detour endpoint, on macOS through a loopback driver (BlackHole).
2. **Delay**: A ring buffer exactly one delay long; at the write position the
   old value is played out and the new one written. The signal is not altered,
   only shifted. When a source starts playing after a longer silence — press
   play in Spotify, and for the length of the delay the speakers are
   necessarily still silent, which looks like failure — a short **count-in**
   is played into that gap: one beep per remaining second (3 – 2 – 1, the last
   one accented), then the music arrives. A break inside a song does not
   trigger it: the count-in only fires when the silence was at least one full
   delay long, so the output really is quiet until the new material lands.
   This buffer is *exactly* one delay long and stays that way for the life of
   the run — the record mode (`R`) is a **separate stage behind it**,
   described under *Control window*, precisely so that the delay here never
   has to change.
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

## Audio routing, transactional

Tapping the monitor of the normal output and playing the delayed signal back to
that same output would give you the original plus the delay plus an echo
cascade. So `jampilot run` temporarily puts a **silent detour** in front of the
default output: players play into it inaudibly, JamPilot reads the other end and
sends only the delayed signal to the real hardware. On exit (including `kill`)
everything is restored.

The detour differs per platform, the choreography does not:

| | Linux | Windows, VB-CABLE | Windows, no driver |
|---|---|---|---|
| the detour | a **null sink**, created via `pactl` | the **VB-CABLE** loop | a **second output endpoint**, muted |
| made silent | silent by construction | nothing comes out of a cable | `IAudioEndpointVolume::SetMute` |
| made default | `pactl set-default-sink` | `IPolicyConfig::SetDefaultEndpoint` | the same |
| captured from | the null sink's monitor | CABLE Output, the recording side | the same endpoint, WASAPI loopback |
| played back to | the previous default sink | the previous default endpoint | the same |
| left alone | — | the *Communications* device | the same, and it is never the detour |

The last two rows are the point: **you keep hearing on the device you were
already using.** The endpoint that gets muted is the *detour* — the thing your
players spill into — never the one you listen on.

The driver-free variant works because of one measurable fact: **the mute of an
endpoint sits behind the loopback tap.** The endpoint goes quiet, the capture
keeps the full signal. That is what turns *any* second output into a null sink,
even an HDMI port with a TV on the other end. It is driver behaviour, not
something the documentation promises, so JamPilot does not believe it — at
startup it mutes a candidate, sends an inaudible probe tone into it, measures at
the tap and unmutes again (~350 ms per candidate). Only an endpoint that passes
becomes the detour.

If VB-CABLE is installed it wins: it is the proven path, and someone who
installed it chose it. `--route mute|cable` forces either. Endpoints are ranked
by their Core Audio **form factor**, not by name — HDMI and S/PDIF first (nobody
listens there), headphones last. The name is useless for this: the HDMI output
on the test machine is called "LEN LT2452pwC (NVIDIA High Definition Audio)".

macOS is the one platform where this is still manual: BlackHole can take the
role of the cable, but switching the default device there is a different API
again (`AudioObjectSetPropertyData`) and is not implemented.

Setup is **transactional**: every step is registered before the next one runs;
if one fails, everything unwinds backwards. Otherwise the silent null sink would
be left behind as the default output — `with` does not call `__exit__` if
`__enter__` throws. A `SIGKILL` cannot be caught by design; that is what
**`jampilot cleanup`** is for: it removes orphaned sinks and restores the
default output. `run` cleans up at startup, *before* it remembers the current
output — otherwise it would save the muted state left by a crashed predecessor
as the "previous state" and restore that on exit.

All of that holds on Windows too, with one addition. There the change outlives
the process — a killed run would leave the endpoint muted, or the cable as the
default output, across a reboot — so what has to be undone is written to a file
*before* the change is made. `cleanup` reads that file rather than asking what
the machine can do today: between the crash and the cleanup the headphones may
be gone or the cable uninstalled, and a decision made now would undo the wrong
thing. It also only acts if the state is in fact still there — if you have
already unmuted your speakers yourself, JamPilot keeps its hands off, and an
endpoint you had muted *before* starting stays muted.

Of the two Windows failure modes, the muted endpoint is the friendlier one: it
shows up as a crossed-out speaker icon that every user can find and click. A
default output silently pointing at a virtual cable is invisible.

A sink counts as orphaned only if its **owner process is dead**. Who created it
is recorded in `/tmp/jampilot-<uid>.pid`; without that check a second instance
would unload the sink of a running first one, and the two would tear each
other's routing apart. A second start therefore fails with a clear message
instead of doing damage (`cleanup --force` overrides it if needed).

## Windows, in depth

You set nothing in *Settings → System → Sound*, and you pass no `--input`.
`run.cmd devices` prints what the automatic mode will pick:

```
Automatic routing (no options needed):
  routes    system output -> LEN LT2452pwC (NVIDIA High Definition Audio)  [muted]
  captures  the same endpoint (WASAPI loopback)
  playback  Lautsprecher (Realtek High Definition Audio)
  no driver needed
```

Read it as: your players are sent to the monitor's audio output, which is muted
so nothing comes out of it anywhere; JamPilot taps that endpoint and plays the
delayed music on your speakers. On exit both are put back. `--output` overrides
where the delayed sound goes; `--no-route` turns the whole mechanism off and
captures the default input device instead.

If the machine has no second endpoint, the fallback is
[VB-CABLE](https://vb-audio.com/Cable/) (unpack it, run `VBCABLE_Setup_x64.exe`
**as administrator**, reboot). It adds **CABLE Input**, an output nothing
audible comes out of, and **CABLE Output**, the recording side of the same pipe
— together exactly the null sink Linux builds with `pactl`.

One deliberate non-feature: **unmute the detour mid-session and you will hear
both** the original and the delayed signal. That is not a bug you need to
report; JamPilot deliberately does not fight you over a setting you just
changed by hand. Stop it, or mute again. And the detour is never your headset —
Windows' *Communications* device is excluded from the candidates, because a
headset going silent in the middle of a video call is not a bug anyone would
look for in a chord display.

All of the Windows routing runs on `ctypes` in the process itself — no extra
dependency, no administrator rights, nothing installed:
[`jampilot/winaudio.py`](jampilot/winaudio.py) enumerates endpoints (with their
form factor) and reads and sets the default device and the mute state,
[`jampilot/wincapture.py`](jampilot/wincapture.py) carries the loopback tap and
the startup probe. The bundled PortAudio (19.7.0) does not offer loopback at
all, so it is not a matter of a flag — the code is not in the DLL.

Switching the default output device is the one thing Windows has no documented
API for; JamPilot uses `IPolicyConfig`, the undocumented COM interface behind
the Sound control panel that nircmd and SoundVolumeView also use. It needs no
administrator rights. Should a future Windows version drop it, both Windows
routes lose the switch and JamPilot falls back to the manual path with a message
rather than failing. Muting and the endpoint enumeration go through documented
interfaces (`IAudioEndpointVolume`, `IMMDeviceEnumerator`).

**Prefer routing just one app?** Since Windows 10 the volume mixer (*Settings →
System → Sound → Volume mixer*) can give a single application its own output
device. Point *only* your browser or Spotify at **CABLE Input**, start JamPilot
with `--no-route --input "CABLE Output (VB-Audio Virtual Cable), Windows
WASAPI"`, and everything else — system sounds, messenger, video calls — stays on
the speakers. More fiddly, but nothing but that one app gets delayed.

What has been verified on Windows 10: setup and start via `run.cmd`, the
automatic routing including restore on exit, recovery after a hard kill, the
second-instance guard, closing the console window, device enumeration,
`selftest`, the test suite (399 tests at the time), a live run with the delay
buffer and the measured lead, the web display, and the control window. A single
full-duplex stream across two *different* WASAPI devices — the one thing that
could have broken the design — carries.

For the driver-free route specifically: the mute sits behind the loopback tap on
all four driver families available on the test machine (Realtek HD Audio, NVIDIA
HDMI, VB-Audio, Oculus), the captured peak is bit-identical to what was sent,
audio from a *different* process is captured just the same, and output on the
listening device does not bleed back into the tap. A full run with the HDMI
output as the muted detour and the speakers as playback carries the signal
end-to-end with no dropouts, and puts both back afterwards. Whether the mute
behaves this way on every driver is exactly what the startup probe exists for.
What has *not* been done is a long musical session, hence 🟡 in the README's
platform table.

Since 1.2.0 `run.cmd --bundle` builds a standalone version here too — as a
folder in a ZIP rather than a single file. That is the answer to the
SmartScreen question that had held the Windows build up; see
[Size, startup, reproducibility](#size-startup-reproducibility).

## The launcher scripts

`run.sh` (and `run.cmd`/`run.ps1` on Windows) look like convenience wrappers;
their real job is repair. **The first call takes about a minute** — it creates
`.venv` and installs the locked dependencies. **Every call after that starts in
well under a second.** A stamp inside `.venv` records which lock file and which
Python it was built against; if that still matches and every package is
present, there is nothing to do and the script gets out of the way.

If it *doesn't* match, the script repairs it instead of failing at you — and
that is the whole point of it. A lock file that changed, a Python that was
upgraded out from under the venv, an install someone interrupted with Ctrl+C, a
`site-packages` that lost a package: each of these used to end in a message
that named the symptom (`No module named librosa`) and not the cause, days
later. The stamp is written *only after* a successful install, so a half-built
environment is never mistaken for a finished one.

`run.cmd` exists because a freshly installed Windows has its PowerShell
execution policy on `Restricted`, and `.\run.ps1` fails there with a message
that reads like a broken script rather than like a setting. `run.cmd` passes
`-ExecutionPolicy Bypass` for that one call and changes nothing about your
system.

The one thing the scripts cannot install is **PortAudio**, because it is a
system library and not a Python package (`sudo apt install libportaudio2`,
`brew install portaudio`). They check for it and say so, rather than letting
`sounddevice` fail with "PortAudio library not found". On Windows PortAudio
comes inside the `sounddevice` wheel.

## The control window: why it exists at all

The control window is not the main interface. It is the **way back**: JamPilot
reroutes your system sound while it runs. Close the browser tab and, without
this window, there would be no UI left at all — your sound is delayed, or
silent, and nothing on screen tells you why. So the big switch at the top,
**Audio through JamPilot**, is the panic button: off, and your system sound is
normal again, immediately. Closing the window quits JamPilot, and that restores
your audio. Leaving it running invisibly in the background is precisely the
trap the window exists to prevent.

**Muting is not pausing**, and the difference matters: the **Sound** switch
(`Space`) mutes only the delayed output — the music and the chords keep
running, and *every view keeps moving*; you just hear nothing. The delay ring
buffer keeps running too. (Mute used to freeze the big chord and dim the lane,
an attempt to get "let me look at this chord" out of the mute switch because
there was nothing better. Now there is, so mute means exactly what it says.)

Pausing and going back is **record mode** (`R`), a **separate stage**
(`record_buffer.py`) behind the delay stage — and it has to be separate, because
pausing *that* ring buffer would silently mean "increase the delay". The delay
is the time base the analysis computes its commit boundary on: let it grow, and
the chord timeline has to hold minutes of future — through a merge that is
quadratic in its length. So `R` does not touch the delay stage. A second buffer
sits behind it, records the **finished mix** (music, count-in, control guitar —
everything except the mute fade, so rewinding past a muted stretch gives you
the music back), and has its own read pointer. `P` holds that pointer still
while the write edge runs away; `←`/`→` move it to the previous or next chord
onset — landing a hair *after* it, so the target is unambiguously the sounding
chord: big in the middle, its chip on the NOW line (an earlier design landed
0.7 s early "to hear the change coming" and failed in the rehearsal room for
exactly that reason — the target sat visibly beside NOW, not on it; you get
the run-up the way every player gives it, with `←` twice); `Home`/`End` go to
the start of the recording and back to the live edge. Every jump is crossfaded
over 15 ms, because a hard cut in the signal is a click.

The mode is a mode, not a background state, and that is the property that
makes it safe to carry: **with `R` off, `record_buffer.process()` returns
before touching a byte**, the output is bit-identical to a run without it, and
the display clock is *the same function* as before — no second time axis, no
event window, no epoch counter. The delay stage learns exactly one thing about
all this: nothing. It exposes `heard_position()`, which falls through to
`audible_position()` unless a recording is running.

The cost is memory — 30 minutes of stereo float32 is about 660 MB — and it is
paid **on the first `R`, not at startup**: the buffer is reserved and touched
in a background thread (a page fault over that much memory inside the audio
callback would be a dropout), the red dot shows hollow for the ~0.2 s it
takes, then recording begins. Too little free memory just leaves `R` inert
with a note in the startup log. `--record-buffer 0` turns it off,
`--record-buffer <minutes>` resizes it.

`--no-window` runs without the control window (terminal only). Over SSH or in
CI, where there is no display, that happens by itself.

## Web display, under the hood

What the page *shows* is described in the README. What it *is*: an embedded
HTTP server with server-sent events, no framework, no CDN, fully
offline-capable — it has to work on a stage with no internet. The browser is a
pure display: it receives the chords with their onset in stream seconds plus
the currently audible position, syncs its clock against that with a minimum
filter (the NTP principle: delivery time is always positive), and derives
**both** the big chord and the lane from that one clock. `?demo=1` renders the
page with example chords and no running analysis — handy for working on the
layout.

## Key detection: two steps, one spelling

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
the lane, survives a reload (`localStorage`) and applies **per device** —
laptop and phone may be set differently. Terminal and `analyze` always follow
the detected key.

## The measured bass

The chord says what the band plays; which note is on the bottom is measured,
not derived. The measurement is free: the analysis already computes a low-band
chroma (32–260 Hz) and used to throw it away. Keeping it costs memory, not CPU
— **0.03 ms** per analysis tick.

*On the method:* the bass-transcription literature recommends pYIN on a
band-passed mix. That was tried and rejected, with numbers: on dense voicings —
chord tones sitting right above the bass, i.e. the normal case in real music —
YIN drops to 4/12, because it estimates the period of the *mixture*. The
low-band CQT chroma gets 60/60 on the same material and costs nothing, because
a constant-Q transform uses long windows at low frequencies by construction.
See `bass.py`.

## Guitar and keyboard voicings

In guitar mode the voicing is not picked in isolation but with the lead: a
short **Viterbi search** over the coming chords chooses the path with the least
hand travel, so you keep playing in one position instead of jumping across the
neck between chords (see
[`docs/exploration/gitarrenmodus-lagen.md`](docs/exploration/gitarrenmodus-lagen.md)).
The complete design and current behaviour of the safe guitar mode are
documented in [`docs/gitarrenmodus.md`](docs/gitarrenmodus.md).

Keyboard mode runs the same look-ahead over piano *inversions*: the search
picks the inversion with the least finger travel, so the right hand stays in
place instead of jumping back to root position on every change. The measured
bass is marked in orange as the left hand: in C/E you see the C-major keys
with the E marked below them.

When the audio cannot reliably decide between nearby readings, the diagram is
deliberately conservative: if A major and A minor are almost equally plausible,
JamPilot shows a playable A5 shape (A and E) and mutes the uncertain third
instead of asking the guitarist to guess. An uncertain seventh is omitted the
same way. The optional **control guitar** in Settings plays exactly this safe
set of pitch classes over the quieter delayed original, making a bad
recommendation immediately audible without pretending to reconstruct the
recorded fingering.

## Standalone binary

```bash
./run.sh --bundle          # -> dist/jampilot + dist/JamPilot.desktop
./dist/jampilot selftest   # verifies the bundle (the build already ran this)
```

**It only builds when it has to.** A stamp in `dist/` holds the fingerprint of
the sources the binary was made from (`jampilot/*.py`, the spec, the entry
point, the lock file). Unchanged, `--bundle` returns in under a second instead
of three minutes — and it would have produced the identical bytes anyway, which
is exactly what `--check` below proves. `--force` builds regardless.

### Double-clicking it (Linux)

**Double-click `dist/JamPilot.desktop`, not `dist/jampilot`.** Double-clicking
the binary itself does nothing at all — no window, no message, no error — and
that is not a bug in JamPilot: a Linux file manager will not run a binary.
`dist/jampilot` has the MIME type `application/x-executable`, no application is
registered for it, and the "run this file?" prompt
(`executable-text-activation`) exists only for executable *text* files. Nemo
and Nautilus simply do nothing.

The launcher is the mechanism Linux provides for this. `packaging/build.sh`
writes it next to the binary; to get JamPilot into the application menu
instead:

```bash
./dist/jampilot install            # -> ~/.local/share/applications/jampilot.desktop
./dist/jampilot install --remove   # takes it back out
```

Started this way there is no terminal, so the **window has to be the feedback**
— which is why it opens *before* the ~3 s numba warmup rather than after it.
Between the `--onefile` unpacking and the warmup, the old order left a
double-clicker staring at an empty screen for five seconds, which looks exactly
like a program that failed to start (and invites a second double-click).

### Double-clicking it (Windows)

```bat
run.cmd --bundle    :: -> dist\JamPilot\ + dist\JamPilot-1.3.0-windows-x86_64.zip
```

**Double-click `JamPilot.cmd`, not `jampilot.exe`.** Here the raw executable
*does* start — the problem is the opposite one of Linux's. `jampilot.exe` is a
console program, so Windows takes its console window down in the same instant
the process ends. When JamPilot exits with a message (no second output
endpoint, a device with one channel), that message is on screen for a few
milliseconds and then gone, and what the user sees is a program that did
nothing. `JamPilot.cmd` keeps the window open when the exit code is not zero,
and only then. It passes every argument through, so `JamPilot.cmd devices`
works as well.

The ZIP also carries a `README.txt`: whoever downloads a ZIP is not reading
GitHub, and the two things Windows will ask them on the first start —
SmartScreen and the firewall dialog — are worth one paragraph each where they
will actually be seen.

### Size, startup, reproducibility

**~183 MB, ~2.5 s to start.** The size is librosa's doing — it drags in numba
and llvmlite (206 MB of JIT compiler) plus scipy and scikit-learn, and none of
it can be excluded: librosa imports all of it on our code path even though we
call none of its functions. Qt adds ~46 MB on top, after throwing out every
module the control window does not touch. The startup cost is `--onefile`
unpacking itself into a temp directory on every launch. For a tool you start
once per session and leave running, that is the right trade; if you want a
0.45 s start, build `--onedir` instead and ship a folder.

**Windows ships a folder instead: 150 MB zipped, 363 MB unpacked, ~0.45 s to
start.** Same spec, same collected parts — they hang off a `COLLECT` instead of
the `EXE`. The reason is not speed but delivery: a single unsigned executable of
this size that unpacks itself into `%TEMP%` on every launch *is* a packer,
technically, and every heuristic treats it as one. The folder does not trip
that. It does **not** make the warning go away — unsigned is unsigned, and the
first start still says *"Windows protected your PC"* until someone pays for a
code signing certificate — but it removes the part that also upsets virus
scanners. What is lost is the promise "one file"; inside a ZIP, a folder is the
same single download either way.

The build is **reproducible**: same commit, same lock file, same platform → the
same bytes. `packaging/build.sh --check` proves it by building twice and
comparing the SHA-256; `run.cmd --bundle --check` does the same on Windows.

That last one was an open question rather than an assumption — the PE format
carries a timestamp in its header, and whether PyInstaller normalises it was
unknown. Measured: it does. Two full builds are identical across all ~1700
files of the folder, with `PYTHONHASHSEED=0` doing the same work it does
elsewhere. What `--check` compares there is the *contents of the folder*, file
by file, not the ZIP: a ZIP stores each file's modification time in its header,
so two ZIPs made from bit-identical folders still differ. That is a property of
the format, not a hole in the claim — the checksum in a release note is the one
of the uploaded file, not of a rebuild.

`dist/jampilot selftest` is the test that matters here: it drives librosa,
numba and both CQTs without needing a sound card, so it trips over any module
PyInstaller failed to collect. Run it after every change to the spec.

**Builds do not cross-compile.** PyInstaller bundles the native libraries of
the machine it runs on, so a Linux binary needs Linux, and macOS needs a Mac —
separately per architecture. `.github/workflows/build.yml` builds Linux x86_64,
macOS Apple Silicon and Windows x86_64 on tag push. **Intel macOS is not built
any more**: `macos-13` was GitHub's last free Intel runner, it is being
retired, and its queue no longer moves — Intel Macs install from source, which
`run.sh` makes cheap.

What the binary still cannot bring with it, because these are system
components:

- **macOS** — [BlackHole](https://existential.audio/blackhole/) must be
  installed separately (it is an audio driver, not a library). Also: an
  unsigned binary downloaded from the internet is quarantined by Gatekeeper.
  Either `xattr -d com.apple.quarantine jampilot` on first use, or sign and
  notarise it with an Apple Developer account. Started from a terminal,
  JamPilot inherits the terminal's microphone permission; a double-clickable
  `.app` would need its own `NSMicrophoneUsageDescription`.
- **Linux** — `pactl` (PipeWire/PulseAudio) is called as an external program
  for the null-sink routing. Without it, use `--no-route --input <device>`. The
  glibc of the build machine is the *minimum* on the target, so build on the
  oldest distribution you want to support.
- **Windows** — nothing, which is the point of the driver-free route. What it
  cannot suppress is the environment: SmartScreen on the first start, and the
  firewall dialog the first time the display server binds. Both are in the
  ZIP's `README.txt`, because the second one silently breaks the QR code if it
  is clicked away.

## Project layout

```
run.sh             the one entry point: sets up, starts, builds (--bundle)
run.ps1            the same for Windows - same three jobs, same options
run.cmd            the shell around run.ps1 - gets past the execution policy
jampilot/
  btc.py           the chord recogniser: BTC transformer (NumPy port) + boundary refinement
  data/            model weights (btc_large_voca.npz) and the web page (index.html)
  chroma.py        FFT → chroma vector (12 pitch classes), CQT frame chroma
  chords.py        chord templates + matching (kept for the self-test)
  bass.py          the measured bass note → inversions / slash chords
  tonality.py      key detection → spelling (♯ or ♭)
  delay_stream.py  duplex stream with the delay ring buffer (sounddevice/PortAudio)
  routing.py       automatic routing, transactional: null sink via pactl
                   (Linux), VB-CABLE via Core Audio (Windows), none on macOS
  winaudio.py      Windows Core Audio via ctypes - list endpoints, read and
                   set the default output device (no extra dependency)
  engine.py        routing + stream + analysis as one switchable thing
  gui.py           the control window (Qt) - the way back when the page is closed
  desktop.py       the .desktop launcher - the way in, for a double-click
  web.py           SSE server; the page it serves lives in data/index.html
  selftest.py      synthetic chords as a pipeline test
  cli.py           command-line frontend, timeline logic
packaging/
  venv.sh          the environment, stamped: expensive once, free afterwards
  build.sh         the reproducible build (and it skips when nothing changed)
  venv.ps1         the same environment logic for Windows (run.ps1 uses it too)
  build.ps1        the same build for Windows, plus the release ZIP
  jampilot.spec    PyInstaller: one file on Linux, a real .app on macOS,
                   a folder on Windows (SmartScreen - see the file's header)
tests/             pytest suite (419 tests)
docs/exploration/  design documents (in German)
```

## Tests

```bash
./run.sh selftest                 # the pipeline, no sound card needed
.venv/bin/python -m pytest        # the suite (419 tests)
```

On Windows: `run.cmd selftest` and `.venv\Scripts\python -m pytest`.

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

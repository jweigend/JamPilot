# Contributing to JamPilot

Thanks for wanting to help. JamPilot is young, and the most valuable
contribution right now is honest feedback from people who actually play:
open a [Discussion](https://github.com/jweigend/JamPilot/discussions) or an
[Issue](https://github.com/jweigend/JamPilot/issues) and tell us what happened
in your practice room.

## Before you write code

- **Talk first for anything non-trivial.** Open an issue or discussion before
  building a feature — the design has strong opinions (see
  [UNDER-THE-HOOD.md](UNDER-THE-HOOD.md) and
  [`docs/exploration/`](docs/exploration/)), and it is cheaper to align before
  the work than after.
- **Read the two companion documents.** [HOW-IT-WORKS.md](HOW-IT-WORKS.md)
  explains the recognition and its limits; [UNDER-THE-HOOD.md](UNDER-THE-HOOD.md)
  explains the machinery around it and why several obvious alternatives were
  tried and rejected. Many "why don't you just…" questions are answered there,
  with measurements.

## Working on the code

```bash
./run.sh selftest                 # the pipeline, no sound card needed
.venv/bin/python -m pytest        # the full suite must stay green
```

- **Language convention:** code comments, tests and design documents are
  written in **German**; everything a user sees (CLI output, web display,
  README) is **English**.
- **Claims need numbers.** Changes to recognition, timing or routing behaviour
  should come with a measurement — the reference recordings under
  `tests/reference/` and the accuracy tests show how existing claims are pinned
  down.
- **The tests encode hard-won bugs.** If a test is in your way, read its
  comment before weakening it; most of them exist because something real broke
  once (see the test list in [UNDER-THE-HOOD.md](UNDER-THE-HOOD.md)).

## Pull requests

- Keep them focused — one topic per PR.
- `pytest` green, `./run.sh selftest` green.
- If behaviour changes, update README / HOW-IT-WORKS / UNDER-THE-HOOD to match.

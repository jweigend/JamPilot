# JamPilot — Technisches Design (Template-Pfad, entfernt)

Dieses Dokument beschrieb den urspruenglichen Template-Matching-Pfad
(Chroma → 5 Akkord-Schablonen → Prior/Glaettung/Onset-Suche). Der Pfad wurde
am 2026-08-08 vom BTC-Transformer abgeloest, lag danach stillgelegt im Code
und wurde nach dem 1.1.0-Release vollstaendig entfernt.

- **Code und Doku im Zustand vor der Entfernung:** Git-Verlauf, z. B.
  `git show v1.1.0:docs/technical-design.md` bzw.
  `git show v1.1.0:jampilot/harmony.py`.
- **Aktueller Stand der Erkennung:** [../HOW-IT-WORKS.de.md](../HOW-IT-WORKS.de.md)
  (englisch: [../HOW-IT-WORKS.md](../HOW-IT-WORKS.md)) und
  [../UNDER-THE-HOOD.md](../UNDER-THE-HOOD.md).
- **Zeitleisten-Architektur (publish-once):**
  [exploration/zeitleiste-redesign.md](exploration/zeitleiste-redesign.md).

Weiterhin aktiv aus dieser Aera: `chords.match_chord` (nur noch vom
Selbsttest genutzt), die Chroma-/CQT-Helfer in `chroma.py` und die
Bassmessung (`bass.py`) — Letztere lebt im BTC-Pfad weiter.

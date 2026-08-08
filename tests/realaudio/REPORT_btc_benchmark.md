# Experiment-Report: BTC-Transformer als Alternativ-Erkenner (Offline-Benchmark)

**Kandidat:** BTC — „A Bi-directional Transformer for Musical Chord Recognition" (Park et al., ISMIR 2019), Repo `jayg996/BTC-ISMIR19`, MIT-Lizenz, fertiger Checkpoint `btc_model_large_voca.pt` (170 Klassen: 12 Roots × {maj, min, dim, aug, min6, maj6, min7, minmaj7, maj7, 7, dim7, hdim7, sus2, sus4} + N + X).
**Frage:** Taugt das Modell als Label-Quelle für JamPilot — gemessen an unseren vier Realaudio-Tracks gegen die bestehende Ground-Truth (REPORT_peg / REPORT_sting_faith / REPORT_misty / REPORT_misty2_clean) und gegen `jampilot analyze`?
**Datum:** 2026-08-08
**Setup:** Scratchpad-venv, CPU-only PyTorch; drei Alterungs-Patches nötig (`yaml.load`-Loader, `torch.load(..., weights_only=False)`, `np.float`→`np.float64`). Inferenz `test.py --voca True` über die vier WAVs.

---

## 1. Rechenlast (Nebenbefund, aber wichtig)

Reine Modell-Inferenz: **< 1 s pro kompletten Song auf CPU** (8 Layer, Hidden 128, Checkpoint 12 MB). Die restliche Laufzeit ist librosa-Laden + CQT. Für den Live-Pfad (250-ms-Hop-Budget) ist das Modell rechnerisch völlig unkritisch; das 4-s-Delay liefert genug „Zukunft" für die bidirektionale Attention an der hörbaren Position.

## 2. Labelqualität gegen Ground-Truth

**Misty2 (Adair, Eb, clean) — der stärkste Lauf.** Der A-Teil kommt nahezu Real-Book-getreu (BTC notiert enharmonisch in Kreuzen): `D#:maj7 | A#:min7 D#:7 | G#:maj7 | G#:min7 C#:7 | … C:min7 F:min7 A#:7` = `Ebmaj7 | Bbm7 Eb7 | Abmaj7 | Abm7 Db7 | … Cm7 Fm7 Bb7`. Beide Backdoor-Akkorde mit **korrekter Dominant-Qualität**.

**Der maj7-Bias-Befund (unsere dokumentierte Top-Schwäche):** An den Db7-Stellen, wo JamPilot `Dbmaj7` zeigt (REPORT_misty2: 16.6, 45.1, 55.6, 102.1, 119.6 s), labelt BTC `C#:7` — echte Dominante. Dauergewichtete Qualitätsverteilung Misty2: BTC `7` 26 % / `maj7` 20 %, JamPilot `7` 11 % / `maj7` 17 % — bei dominantlastiger Jazz-Ground-Truth ist das die richtige Richtung. Der Bias ist beim gelernten Modell praktisch weg.

**Peg (Stresstest) — Intro-Abstieg:** 7/8 Roots (ein Ausrutscher: `D:min7` statt Fmaj9-Fortsetzung im Slot 3), dabei `F#:7` **mit korrekter Terz**, wo unser Matcher `F#m7` griff (echter Falschton laut REPORT_peg), `E:7`, `D:7`, `D#`, `C:maj7` exakt.

**Sting — Strophe:** lehrbuchhaft stabiles `A | G | D` ×3 in sauberen Blöcken, wo unsere Anzeige zwischen `Amaj7/A7/C#m/E/Gm` flackert. Im grundtonlosen Intro trifft BTC sogar das `Cmin6` der Ground-Truth.

## 3. Stabilität

| Track | Segmente JamPilot | Segmente BTC | davon < 0.2 s |
|---|---|---|---|
| Peg | 385 | 254 | 40 |
| Misty (Garner) | 221 | 98 | 7 |
| Misty2 (Adair) | 296 | 169 | 25 |
| Sting | 259 | 135 | 10 |

Dazu der härteste Einzelbefund: **tonartfremde Roots in Peg (C#, G#, A# in G-Dur): JamPilot 24 Segmente, BTC 0** — über die vollen 236 s. Das `C#maj7`/`A#maj7`-Streuen aus REPORT_peg existiert beim Transformer nicht. Restflackern hat BTC auch (1–2-Frame-Segmente, s. Tabelle), wäre aber mit trivialem Min-Dauer-Filter behebbar.

## 4. Was BTC *nicht* kann (bestätigt die Hybrid-These)

- **Keine Slash-Bässe/Umkehrungen im Vokabular:** Das signaturhafte `G/B` in Peg ist bei BTC unsichtbar (nur `G`). Unser separater Bass-Messpfad (`bass.py`) bleibt unverzichtbar.
- **Timing nicht beweisbar besser:** BTC arbeitet auf ~93-ms-Frames (Hop 2048 @ 22 050 Hz). Gegen `jampilot analyze` liegen BTC-Wechsel systematisch **100–230 ms früher** (Median über 60–144 gematchte Root-Wechsel pro Track) — aber `analyze` stempelt selbst nur aufs 0,5-s-Raster ohne Onset-Suche, also ist keiner der beiden eine Referenz. Der Befund aus den Onset-Experimenten gilt unverändert: **Timing-Aussagen brauchen handannotierte Ground-Truth.** (Die Isophonics-Annotationen aus dem BTC-Umfeld wären genau das — sofern passendes Audio beschaffbar.)
- **Triaden-Tendenz bei mu-/add9-Voicings:** In Peg zeigt BTC oft `C`/`C:sus2` statt `Cmaj7`-Farbe (maj7-Anteil nur 4 %) — die von REPORT_peg dokumentierte add9/sus2-Ambiguität, nur in die andere Richtung reduziert.

## 5. Urteil

Als **Ersatz** für die Pipeline: nein (Slash-Bass fehlt, Onset-Auflösung gröber, PyTorch-Dependency). Als **Label-Quelle im Hybrid** klar positiv getestet: sauberere und funktional richtigere Qualitäten (Dominanten!), keine tonartfremden Ausreißer, 35–55 % weniger Segmentflackern — bei vernachlässigbarer Rechenlast. Die Form, die zur Architektur passt (vgl. `docs/exploration/lernbasiertes-chroma.md`): BTC liefert Qualität/Label bzw. re-rankt die Top-5-Kandidaten aus `match_chord`, eigene Onset-Suche liefert weiter das Timing, `bass.py` weiter den Slash-Bass.

**Nächste Schritte, falls weiterverfolgt:**
1. ONNX-Export des Checkpoints (Modell winzig; erspart die ~200-MB-Torch-Dependency im PyInstaller-Binary).
2. Prototyp-Integration als Kandidaten-Re-Ranker auf `match_chord`-Ebene, Fenster [t−6 s, t+4 s] im Live-Pfad.
3. Playtest am Mitspiel-Fluss (Jam-Tool-Maßstab, nicht Transkriptions-Maßstab).

**Artefakte:** BTC-Ausgaben (`.lab`) und `analyze`-Referenzläufe im Session-Scratchpad `scratchpad/labs/`; gepatchtes Repo unter `scratchpad/BTC-ISMIR19/`; Vergleichsskript `scratchpad/compare.py`.

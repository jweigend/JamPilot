# Beat-Tracking: Ergebnisse der Evaluierung und Einbau-Rezept

*Uebergabe aus JamPilotML, 2026-09-10. Die Messung selbst steht in
[`../../../JamPilotML/docs/beat-tracking-evaluierung.md`](../../../JamPilotML/docs/beat-tracking-evaluierung.md)
§6 (Skripte, Parquet-Ergebnisse, Caches); dieses Dokument enthaelt, was
JamPilot zum Einbau braucht, und schliesst Stufe 3 aus
[`tempo-und-takt.md`](tempo-und-takt.md) §5 ab.*

---

## 1. Antwort auf die vier Fragen

Beat This! (Foscarin et al., ISMIR 2024), Checkpoint `small0` (2,1 M
Parameter), gemessen auf 169 Beatles-Titeln mit Isophonics-Beat-Annotation
(nach Korrektur der Annotations-Offsets, siehe §5), Peak-Picking ohne DBN:

| Frage | Ergebnis `small0` | Schwelle | |
|---|---|---|---|
| Q1 Beat-F / Downbeat-F / Phase, ganzer Titel | 0,991 / 0,974 / 7,5 ms | > 0,9 / > 0,8 / < 40 ms | erfuellt |
| Q2 Verlust im 10-s-Fenster ohne Gedaechtnis | Beats −0,008, Eins −0,060 | Δ > −0,05 | Beats ja, Eins knapp nicht |
| Q3 CPU je 10-s-Fenster, 1 Thread / 4 Threads | 380 ms / 168 ms (ONNX Runtime) | < 50 ms | **verfehlt** |
| Q4 Viertel-Snap der BTC-Grenzen, median \|dt\| / Anteil ≤ 93 ms | 103 → 52 ms, 46 → 76 % | < 80 ms, > 60 % | erfuellt, gleich Oracle |

Oktavfehler gibt es nicht mehr (176 von 178 Titeln ×1; librosa kippte jede
Ballade). Die Phase liegt unter dem 20-ms-Frameraster des Modells.
`final0` (20 M Parameter) ist auf Beats gleich, bei der Eins einen Hauch
besser (0,981) und doppelt so teuer — keine Option.

**Entscheidung:** Das Modell liefert das Raster, das die Quantisierung
braucht. Was den Einbau bestimmt, ist allein die CPU: gut ein Drittel
eines Kerns bei einem Lauf je Sekunde, und daran aendern int8, ONNX oder
torch.compile nichts (§3). Auf einer GPU kostet dasselbe Fenster 27 ms.

## 2. Was uebergeben ist

| Datei | Inhalt |
|---|---|
| `jampilot/data/beat_this_small0.onnx` (10,6 MB) | das Modell; Eingabe `spect` (1, T, 128) float32, Ausgaben `beat`, `downbeat` (1, T) Logits; T dynamisch |
| `tests/reference/beat_this_referenz.py` | NumPy/librosa-Referenz fuer alles um das Modell herum: Log-Mel-Spektrogramm (exakt wie `beat_this.preprocessing.LogMelSpect`), Rand-Padding, Peak-Picking (exakt wie `Postprocessor("minimal")`), `run_window()` fuer ein Fenster. Fertig zum Heben nach `jampilot/` |
| `tests/data/beat_golden_window.npz` (1 MB) | Golden-Fixture: 10 s aus `eight_days_a_week.mp3` (30–40 s), Spektrogramm, Logits und Peak-Ausgabe des Original-Torch-Modells, SHA-256 der ONNX-Datei |
| `tests/test_beat_this_referenz.py` | Golden-Test wie `test_btc.py`: Spektrogramm (< 1e-3), Peak-Picking (identisch), ONNX-Logits (< 1e-3, nur mit `onnxruntime`), Ende-zu-Ende |

Verifiziert gegen das Original: Spektrogramm max 3e-5, ONNX-Logits max
6e-5, Peak-Picking identisch. Kein Torch, kein `beat_this` noetig.

Neue Abhaengigkeit: **`onnxruntime`** (CPU-Paket ~15 MB; GPU-Varianten §3).
`pyproject.toml`: `package-data` um `data/*.onnx` erweitern.

## 3. Kosten und Laufzeitform

CPU-Messung (Xeon E5-2690 v3, Haswell, AVX2 ohne VNNI), `small0`, 10-s-Fenster,
Modell allein:

| Form | 1 Thread | 4 Threads |
|---|---|---|
| Torch fp32 | 458 ms | 158 ms |
| Torch int8 (dynamisch) | 497 ms | 203 ms |
| **ONNX Runtime fp32** | **380 ms** | 168 ms |
| ONNX Runtime int8 | 429 ms | 165 ms |
| torch.compile | 351 ms | 159 ms |
| GPU RTX 2080 Super (Torch, inkl. Transfer) | 27 ms | |

Quantisierung hilft nicht, Fusion wenig: 382 der 460 ms stecken im
Frontend, das Attention ueber Frequenz *und* Zeit in voller Aufloesung
rechnet (512 Frames × 32 Baender × 32 Kanaele) — viele kleine,
speichergebundene Operationen. Das ist die Architektur, nicht die
Laufzeit. Die Kosten sind linear in der Fensterlaenge (≈ 38 ms je Sekunde
Audio, ONNX, ein Thread); 5-s-Fenster halbieren sie, kosten aber die Eins
(§4). Der Proberaum-Z820 (Sandy Bridge, kein AVX2) liegt eher bei der
Haelfte eines Kerns.

**Laufzeitform:** ONNX Runtime mit derselben Datei ueberall.
`CPUExecutionProvider` als Rueckfall, davor je Plattform: CUDA/TensorRT
(NVIDIA), ROCm (AMD, Linux), DirectML (NVIDIA/AMD/Intel unter Windows),
OpenVINO (Intel), CoreML (Apple). Gemessen ist nur CPU (ORT) und CUDA
(Torch); die 27 ms sind startlatenz-, nicht rechenbegrenzt, eine schwache
oder integrierte GPU duerfte aehnlich liegen — zu pruefen, wenn es soweit
ist. `SessionOptions.intra_op_num_threads` setzen (1 im eigenen Thread,
sonst greift ORT nach allen Kernen und stoert den Audio-Thread).

## 4. Einbau-Rezept: die Parameter, die die Messung festlegt

```
Audio (22050 Hz mono, wie fuer BTC)
  └─ alle 1 s: letzte 10 s ─▶ log_mel ─▶ pad_chunk ─▶ ONNX ─▶ strip_border ─▶ pick_peaks
                                └─ Beats/Einsen nur aus [Ende − 3 s, Ende − 1 s) uebernehmen
                                └─ Beats, die < 60 ms neben einem schon bekannten liegen: mitteln
  └─ Takt-Phase ueber Fenster halten (Mehrheit der Eins-Position, Hysterese)
  └─ BTC-Grenze an der Commit-Grenze auf den naechsten Beat schnappen (Viertel)
```

| Parameter | Wert | Grund |
|---|---|---|
| Checkpoint | `small0` | Beats gleich `final0`, ein Zehntel der Parameter |
| Fenster | **10 s** | 5 s: Beat-F haelt (−0,015), Downbeat-F faellt auf 0,84 (−0,145) — zwei bis drei Takte reichen fuer die Eins nicht |
| Lauf-Intervall | **1 s** (alle 4 Hops), eigener Thread | Beats aendern sich langsam; im 250-ms-Hop-Budget ist kein Platz |
| Commit-Zone | [Ende − 3 s, Ende − 1 s) | Randframes sind unsicher; 1 s Vorlauf reicht fuer den Commit ~2 s hinter der Analysefront |
| Naht | zwei Fenster einigen sich in 93 % der Beats, dort auf den Frame genau; Merge-Toleranz 60 ms | gemessen mit Hop 1 s, jede Stelle von zwei Fenstern gesehen |
| Eins | **aus dem Modell**, Takt-Phase ueber Fenster halten | Fenster ohne Gedaechtnis verlieren 0,06 Downbeat-F; eine simple Mehrheit ueber ±8 Takte holt im Median 0,03 zurueck, kippt aber bei Metrumwechseln und 2/4-Zaehlung (P10 faellt) — Hysterese und Konfidenz je Fenster gehoeren in den Entwurf |
| Eins-Abstimmung aus Akkord-Onsets (§4.2 in tempo-und-takt) | nur Plausibilitaetswaechter, und nur bei Konzentration > 0,6 | bricht bei jedem zehnten Titel ein (Wechsel gleich oft auf 1 und 3), das Modell nicht; beide sind sich sonst zu 97 % einig |
| Quantisierung | **Viertel**, rohe BTC-Grenzen, kein Achtel, keine Schwelle | Achtel: 82 ms statt 50 (der Grenz-Nachlauf zieht zum falschen Achtel); Schwelle 100/150/200 ms: 89/75/61 ms; Vorziehen vor dem Snap: kein Gewinn |
| `refine_boundary` | **kann entfallen** | roh + Viertel-Snap (50 ms, 77 %) = verfeinert + Snap; spart ~200 ms CPU je Grenze — dieses Budget geht ans Beat-Modell |
| Anzeige | Grenze auf den Beat legen | nach dem Snap liegt die Grenze im Median 35 ms *hinter* dem annotierten Wechsel, auch auf dem Oracle-Raster — Annotationskonvention, nicht Fehler |
| DBN | nein | madmom bleibt draussen; Peak-Picking reicht (Beat-F 0,99) |

Was der Quantisierung bleibt: 23 % der Wechsel liegen auch nach dem Snap
jenseits 93 ms — das sind Wechsel, die BTC nicht oder einen Schlag daneben
erkennt. Ein Akkord-, kein Rasterproblem.

## 5. Zwei Befunde nebenbei, die JamPilot betreffen

**Die Isophonics-Offsets waren das Problem, nicht das Modell.** Der erste
Lauf ergab Beat-F 0,77. Die Chroma-Offsets (23-ms-Raster) liegen bei 111
von 178 Titeln > 50 ms daneben, bei 59 > 100 ms, und 48 Titel *driften*,
weil der Rip minimal schneller oder langsamer laeuft als die annotierte
Version (bis 0,37 %, ueber einen Titel bis 460 ms). Neun Titel sind
Versionsfehler im Matching (*Please Please Me* mono/stereo, *Strawberry
Fields* 263 statt 244 s). Fuer die drei Referenztitel hier: *Eight Days*
Offset gut, *Something* 50 ms daneben, *Let It Be* driftet 0,16 %
(384 ms ueber den Titel). Die beat-gestuetzte Korrektur je Titel liegt in
JamPilotML `data/beat_alignment.parquet`; das Akkordmodell `run_iso_only`
wurde mit den unkorrigierten Labels trainiert und evaluiert — ein Frame
Unschaerfe an jeder Grenze.

**Zehn Titel, bei denen die Modell-Eins konsistent einen Schlag neben der
annotierten liegt** (*It Won't Be Long*, *Taxman*, *Maxwell's Silver
Hammer*, *Mr. Moonlight* …). Ohne Anhoeren nicht entscheidbar, ob Modell
oder Annotation. Wer die Eins-Anzeige testet, sollte einen davon nehmen.

## 6. Was nicht gemacht werden sollte

- **Kein NumPy-Port.** Der waere langsamer als jede gemessene Form; das
  Port-Rezept vom BTC passt hier nicht, weil nicht die Linear-Layer die
  Zeit kosten.
- **Keine 5-s-Fenster** als Kostensenkung, solange die Eins aus dem Modell
  kommen soll.
- **Keine Achtel, keine Snap-Schwelle, kein Vorziehen** — alles gemessen,
  alles schlechter als der nackte Viertel-Snap.
- **Kein Finetuning** hier: Beatles sind im Trainingsset von Beat This!;
  die Zahlen sind fuer In-Domain-Pop optimistisch und sagen nichts ueber
  Jazz, Prog, Latin — dort bleibt der Hoertest (*Misty*, *Peg* in
  `tests/realaudio`).

## 7. Offen

1. GPU-Provider je Plattform paketieren und messen (nur CUDA/Torch gemessen).
2. Takt-Phasen-Haltung ueber Fenster entwerfen (Hysterese, Konfidenz) und
   gegen die Isophonics-Beats messen — die Skripte in JamPilotML lesen den
   Fenster-Cache und liefern die Zahl in Minuten.
3. Wenn ein Drittel Kern zu teuer ist: 7–8-s-Fenster messen (Q2-Skript,
   `--window 8`), oder ein destilliertes kleineres Modell — Trainingsaufwand.

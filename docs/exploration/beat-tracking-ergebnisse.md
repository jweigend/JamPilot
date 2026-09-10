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
| `jampilot/beats.py` (Teil 1; bis zum Einbau `tests/reference/beat_this_referenz.py`) | NumPy/librosa-Referenz fuer alles um das Modell herum: Log-Mel-Spektrogramm (exakt wie `beat_this.preprocessing.LogMelSpect`), Rand-Padding, Peak-Picking (exakt wie `Postprocessor("minimal")`), `BeatModel.run()` fuer ein Fenster |
| `tests/data/beat_golden_window.npz` (1 MB) | Golden-Fixture: 10 s aus `eight_days_a_week.mp3` (30–40 s), Spektrogramm, Logits und Peak-Ausgabe des Original-Torch-Modells, SHA-256 der ONNX-Datei |
| `tests/test_beats.py` (bis zum Einbau `tests/test_beat_this_referenz.py`) | Golden-Test wie `test_btc.py`: Spektrogramm (< 1e-3), Peak-Picking (identisch), ONNX-Logits (< 1e-3, nur mit `onnxruntime`), Ende-zu-Ende |

Verifiziert gegen das Original: Spektrogramm max 3e-5, ONNX-Logits max
6e-5, Peak-Picking identisch. Kein Torch, kein `beat_this` noetig.

Neue Abhaengigkeit: **`onnxruntime`** (CPU-Paket ~15 MB; GPU-Varianten §3).
`pyproject.toml`: `package-data` um `data/*.onnx` erweitern. *(Beides seit
dem Einbau erledigt, §8.)*

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
   Der Code waehlt den Provider nach Verfuegbarkeit (§8), gebuendelt ist nur
   das CPU-Paket.
2. ~~Takt-Phasen-Haltung ueber Fenster entwerfen~~ — entworfen und eingebaut
   (§8), gegen die drei Beatles-Referenztitel im Live-Pfad gemessen (§8.3);
   die Messung ueber alle 169 Titel mit den JamPilotML-Skripten steht aus.
3. Wenn ein Drittel Kern zu teuer ist: 7–8-s-Fenster messen (Q2-Skript,
   `--window 8`), oder ein destilliertes kleineres Modell — Trainingsaufwand.
4. Der Proberaum: Taktstriche und Snap sind gemergt, nicht erprobt. Zu
   pruefen mit einem der zehn Titel aus §5 (Modell-Eins konsistent einen
   Schlag neben der Annotation) und mit Jazz/Prog (*Misty*, *Peg*).

## 8. Einbau (2026-09-10, Branch `analysis/tempo-und-takt`)

Was aus dem Rezept in §4 geworden ist, und wo der Einbau davon abweicht.

### 8.1 Bausteine

| Stueck | Wo | Was |
|---|---|---|
| Modell | `beats.BeatModel` | ONNX Runtime, ein Intra-Op-Thread, Provider nach Verfuegbarkeit (TensorRT/CUDA/ROCm/DirectML/CoreML/OpenVINO, CPU als Rueckfall) |
| Thread | `beats.BeatTracker` | eigener Thread; `submit()` je vierten Hop (1 s), `poll()` je Hop; ist der Worker beschaeftigt, faellt das Fenster aus (Zone 2 s breit, ein Aussetzer kostet nichts) |
| Raster | `beats.BeatGrid` | Commit-Zone [Ende−3, Ende−1), Mitteln < 60 ms, publish-once ueber `commit(frontier)`; `prune` mit Record-Rueckhalt wie der EventLedger |
| Snap | `cli.EventLedger.advance(snap=)` | beim Commit: Event-Onset = naechster Beat, wenn einer in Reichweite (0,6 Schlag, Loecher werden nicht ueberbrueckt); die Zeitleiste behaelt die rohe Grenze, die Kontrollgitarre spielt auf dem Event-Onset |
| Kanal | `"beats": [{at, n}]` | zweiter Publish-once-Kanal, geschnitten wie `committed`; `n` Schlag im Takt, 1 = Eins, 0 = unbekannt |
| Anzeige | `index.html` `.beat` / `.beat.bar` | Ticks am Boden (Eins doppelt so hoch) hinter den Chips, und der Chip, dessen Wechsel auf der Eins liegt, bekommt eine helle linke Kante (`.chip.eins`); Linien ueber die ganze Spur - hinter wie vor den Chips - waren im Playtest zu unruhig (10.09.); Schalter im Zahnrad (`jampilot.beats`, pro Geraet, Standard an); dieselbe Formel und Uhr wie die Chips, kein Client-Raster |
| Selbsttest | `selftest._beats_pruefen` | laedt das Modell aus dem Paket und prueft auf einem 120-bpm-Loop den Viertelabstand — fehlt die ONNX-Datei im Bundle, faellt der Bau, nicht der Nutzer |
| Paket | `pyproject.toml`, `requirements.lock`, `jampilot.spec` | `onnxruntime>=1.17` (gesperrt 1.30.0, dazu flatbuffers/protobuf), `data/*.onnx`, `collect_all("onnxruntime")` |

### 8.2 Abweichungen vom Rezept

- **Die Verfeinerung bleibt.** §4 sagt „kann entfallen“ — richtig, sobald
  der Snap kommt. Aber eine frische Grenze steht am Horizont (Ende−1 s), das
  Raster reicht in dem Moment bis Ende−2 s und trifft erst einen Lauf spaeter
  ein. Faellt der Lauf aus oder macht das Gate zu, gaebe es ohne
  Verfeinerung die nackte 93-ms-Grenze. Der Versuch, sie nur zu
  ueberspringen, „wenn das Raster bis kurz davor reicht“, war in der
  Simulation genau der Fall, in dem der Snap dann doch fehlte. Ein Pfad statt
  zweier; die ~100 ms je Grenze bleiben.
- **Spaete Fenster werden nachgeliefert, nicht verworfen.** Ein
  Fensterergebnis trifft ~0,5 s nach dem Abgeben ein (Z820: spaeter), die
  Commit-Grenze rueckt derweil vor. Beats hinter der Grenze, aber hinter
  dem letzten committeten Beat, kommen beim naechsten Commit nach — ein
  Strich, der etwas naeher an der JETZT-Linie einsteigt. Die erste Fassung
  verwarf sie und verlor in der (zeitgerafften) Simulation 90 % der Beats.
- **Tempo-Gate** (Regel 1 aus tempo-und-takt.md §6): Ein Beat, dessen
  Abstand zum letzten *angenommenen* Beat mehr als 30 % vom Median der
  letzten sechs gesehenen Abstaende abweicht, bekommt keinen Strich. Ein
  doppelter Abstand ohne verworfenen Beat dazwischen ist ein vom Modell
  verpasster Schlag (angenommen, Takt zaehlt einen weiter); mehr als das
  2,5-fache ist eine Pause (Takt zaehlt neu). Rubato faellt so durch, ein
  Geisterbeat reisst den naechsten echten nicht mit.
- **Takt-Phase mit Hysterese** (§7.2 war offen): Ein Eins-Votum (Mehrheit
  der Fenster, die den Beat sahen) wird angenommen, wenn es liegt, wo der
  gehaltene Takt sie erwartet (Taktlaenge ±1 Schlag) — oder ein Votum an
  anderer Stelle einen Takt spaeter von einem zweiten bestaetigt wird
  (Halbtakt-Ambiguitaet: das Modell muss es zweimal sagen). Fehlt das
  Votum, wird die Eins hoechstens zwei Takte fortgeschrieben, dann ist der
  Takt „verloren“ (n = 0, nur Beat-Striche), bis das Modell neu ankert. Das
  Metrum ist der haeufigste Wert der letzten vier angenommenen Taktlaengen
  (2..12) — 3/4 und 6/8 fallen so heraus, ohne dass jemand die Taktart
  kennt. Konfidenz je Fenster (§4) ist NICHT eingebaut; die Mehrheit ueber
  zwei Fenster und die Hysterese sind der Entwurf erster Fassung.
- **Kein Tempo im Kontrollfenster**, kein Countdown, keine Zahl im Laufband
  (Regel 3). `BeatGrid.tempo()` gibt es, es wird nicht angezeigt.
- **GPU gemessen, mit ORT statt Torch** (§7.1 teilweise erledigt): Mit
  `onnxruntime-gpu[cuda,cudnn]==1.30.0` im venv (RTX 2080 SUPER, Treiber
  580, CUDA 13 per pip) kostet das Fenster **10 ms** statt 415 auf der CPU,
  Laden 1,4 s, erster Lauf 400 ms (Warmup). Zwei Stolpersteine, beide im
  Code abgefangen: ORT findet die pip-CUDA-Bibliotheken unter Linux nur
  nach `ort.preload_dlls()` (sonst „libcublasLt.so.13: cannot open“ und
  stiller Rueckfall auf CPU), und das GPU-Paket meldet TensorRT als
  verfuegbar, ohne dass die Bibliotheken da sind — TensorRT steht deshalb
  nicht in der Vorzugsliste. Gebuendelt bleibt das CPU-Paket; die
  Sperrdatei ebenso.

### 8.3 Live-Pfad-Simulation gegen die Referenz

`_display_loop` hop fuer hop ueber die drei Beatles-Referenztitel (Fake-
Loop statt Soundkarte, `--delay 5`, Tracker synchron im Analyse-Thread, damit
die Zeitraffung keine Thread-Latenz vortaeuscht), einmal ohne Tracker (wie
1.3.1) und einmal mit. Gemessen werden die *committeten Events* — das, was
die Anzeige zeigt — gegen die annotierten Wechsel, und die committeten
Beats gegen die `.beats`.

**Die Referenz musste erst geradegerueckt werden.** Die Isophonics-Beats
driften gegen unsere Rips (§5 sagt es fuer die ML-Bibliothek, es gilt auch
hier: Eight Days ~0,3 s ueber den Titel, segmentweise Beat-F 0,95, ueber den
Titel mit festem Offset 0,36). Die ML-Korrektur gilt fuer andere Rips, also
je Titel ein eigener linearer Fit (Skalierung + Versatz) aus den Modell-
Beats — zwei Parameter gegen 200–360 Beats, ein schlechter Tracker kann sich
damit nicht gesundrechnen. Beats sind periodisch, die Familie der Loesung
(Versatz modulo Viertel) legt der Chroma-Offset der Akkorde fest (Titelmitte
±0,2 s). Ergebnis: Let It Be Skalierung 1,00135, Eight Days 1,0021,
Something 1,0004; Versaetze in Titelmitte 0,07 / −0,04 / −0,06 s gegen die
Chroma-Offsets 0,08 / −0,15 / −0,06 — bei Eight Days liegen die beiden
Referenzen 0,1 s auseinander, und die Zahlen gegen den alten Chroma-Offset
sind fuer diesen Titel entsprechend nicht belastbar (in der Tabelle in
Klammern).

| Titel | Referenz | ohne Tracker: med \|dt\| / ≤ 93 ms | mit Snap: med \|dt\| / ≤ 93 ms | Beat-F | Downbeat-F |
|---|---|---|---|---|---|
| Let It Be | driftkorrigiert | 127 ms / 35 % | **70 ms / 71 %** | 0,96 | 0,65 (Modell zaehlt Halbtakte: 138 Einsen gegen 70) |
| | Chroma-Offset | 165 ms / 29 % | 124 ms / 42 % | | |
| Eight Days a Week | driftkorrigiert | 196 ms / 17 % | **61 ms / 59 %** | 0,99 | **0,995** (92 gegen 91) |
| | Chroma-Offset | (135 ms / 39 %) | (186 ms / 24 %) | | |
| Something | driftkorrigiert | 121 ms / 41 % | **48 ms / 80 %** | 0,85 (234 gegen 194: Intro/Outro unannotiert) | 0,66 |
| | Chroma-Offset | 124 ms / 40 % | 53 ms / 73 % | | |

Lesart:

- **Der Live-Pfad liefert, was die Offline-Messung versprach.** Median
  48–70 ms und 59–80 % innerhalb eines Frames gegen 121–196 ms und 17–41 %
  ohne Raster; die Q4-Zahl (52 ms / 76 %) liegt mitten drin. Der Snap
  verschiebt die Events im Median nach *hinten* (med dt +29 bis +65 ms bei
  Let It Be und Something) — die Annotationskonvention aus §4.
- **Beats im Live-Pfad wie offline** (0,96–0,99 nach Korrektur; Something
  0,85 nur, weil das Modell im unannotierten Intro/Outro weiterzaehlt).
  Tempo 70,2 / 136,4 / 68,2 bpm gegen 69,8 / 139,2 / 66,3 — bei Eight Days
  ist die Differenz die Drift der Annotation, nicht des Modells.
- **Die Eins ist titelabhaengig.** Eight Days: 0,995, Takt-Phase haelt
  ueber den ganzen Titel (kein einziges n = 0). Let It Be: das Modell hoert
  konsequent jeden zweiten Schlag als Eins (2/4-Zaehlung, ein Fall aus §5) —
  die Striche sind doppelt so dicht, aber nie an der falschen Stelle;
  Something aehnlich (64 gegen 49). Die Phasen-Haltung macht daraus keine
  falschen Einsen, sie kann aber auch nicht wissen, dass der Takt vier
  Schlaege hat. Das ist der Preis dafuer, keine Eins-Abstimmung aus
  Akkordwechseln (§4.2 in tempo-und-takt) zu fuehren; ob sie als
  Halbtakt-Waechter lohnt, ist ein Punkt fuer den Playtest.
- **Mit den v7-Gewichten** (Drop-in am selben Tag, nachtraining-kampagnen-
  2026-08.md) dasselbe Bild: 120 → 70 ms / 39 → 71 % (Let It Be), 226 → 79 ms /
  14 → 51 % (Eight Days), 137 → 54 ms / 30 → 74 % (Something); Tabelle in
  tests/reference/README.md. Something liefert mit v7 109 statt 145 Events —
  weniger Flackern, dieselbe Trefferquote.
- **Verfeinerung + Snap statt roh + Snap** (§8.2) kostet nichts: Die
  Events liegen auf dem Beat, wo einer ist, und dort ist es egal, was die
  Verfeinerung davor tat.

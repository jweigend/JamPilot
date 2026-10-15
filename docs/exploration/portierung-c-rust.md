# Den Kern nach C oder Rust: Was es bringt, was es kostet

*Explorationsdokument, 2026-10-15. Status: Bestandsaufnahme am Quelltext und
am Bundle, kein Implementierungsplan. Zahlen sind auf dem Entwicklungsrechner
gemessen (2× Xeon E5-2690 v3, Linux, Python 3.12, Stand main 7ac561c), wo
nichts anderes dabeisteht. Wo ich schätze, steht, dass ich schätze.*

*Entscheidung 2026-10-15: Kein Port nach C oder Rust. Die Entfernung von
librosa und Qt (Abschnitt 8) bleibt als Option offen, wird aber vorerst nicht
angegangen.*

---

## Ergebnis vorweg

**Geht es?** Ja. Nichts im Kern ist an Python gebunden. Die beiden Modelle
sind Matrixrechnung, der Rest ist Signalverarbeitung und Buchführung. Jeder
einzelne Baustein hat ein natives Gegenstück, und für die zwei heikelsten
(BTC-Transformer, Beat This!) liegen Golden-Fixtures im Repo, gegen die man
einen Port abnehmen kann.

**Aber die 236 MB sind nicht Pythons Schuld.** Das Bundle besteht
ausgepackt aus 607 MB, und davon entfallen rund 345 MB auf librosa und das,
was librosa mitzieht (numba, llvmlite, scipy, scikit-learn), weitere rund
130 MB auf Qt samt GTK/X11-Stack. Python selbst, NumPy, ONNX Runtime und die
Modellgewichte zusammen sind etwa 130 MB. Wer den Footprint will, muss
zuerst librosa und Qt loswerden, und beides geht ohne Sprachwechsel.

**Was wird schneller?** Fast nichts, was der Spieler merkt. Der Hop braucht
170 bis 300 ms von 250 ms Budget, und davon ist alles Schwere schon C: die CQT
läuft in FFT-Code, der Transformer in BLAS, das Beat-Modell in ONNX Runtime.
Ein Port gewinnt an der Verfeinerung (HPSS) vielleicht Faktor 2 bis 3, am
Beat-Modell gar nichts (Architektur, nicht Laufzeit). Der Vorlauf wird davon
keine Millisekunde länger, den bestimmt die Verzögerung, nicht die Rechenzeit.

**Was wirklich besser würde:** Startzeit (heute 2,5 s Auspacken plus 2 bis
23 s numba-Warmup, nativ unter einer Sekunde), Arbeitsspeicher (570 MB nach
dem Warmlaufen, nativ geschätzt 60 bis 120 MB), und die Immunität des
Audio-Callbacks gegen GIL und Garbage Collector, die auf dem Z820 als
Aussetzer-Ursache im Verdacht stehen. Dazu die Größe: 236 MB gegen geschätzt
30 bis 50 MB. Die Startzeit ist der einzige dieser Punkte, der das Produkt
("Null Anlauf") direkt trifft.

**Leidet die Wartbarkeit?** Ja, und zwar an der Stelle, wo das Projekt lebt.
JamPilot entsteht im Rhythmus "Referenzset messen, Regel ändern, neu messen".
Dieses Labor (565 Tests, 13 Messskripte, die Realaudio-Reports, das ML-Repo)
ist Python und ruft die Pipeline-Module direkt. Ein Rust-Kern spaltet die
Welt: Entweder jede Regel (Ledger, Blip-Sperre, Durchgangsbass,
Quinten-Regel) existiert zweimal, oder das Labor spricht nur noch über eine
Schnittstelle mit dem Kern. Beides ist machbar, beides kostet jeden
Experimentierzyklus Zeit, und davon macht dieses Projekt viele.

**Empfehlung:** In Stufen, und nach jeder messen. Stufe 1: librosa durch
eigene NumPy-Routinen ersetzen (CQT, HPSS, Onset-Stärke, Mel), Resampling über
soxr direkt. Das halbiert das Bundle, streicht den numba-Warmup und ändert
keine Sprache. Stufe 2: das Kontrollfenster von Qt lösen. Danach liegt das
Bundle geschätzt bei 60 bis 80 MB und startet in gut einer Sekunde. Erst wenn
das nicht reicht, lohnt die Rust-Frage, und dann als eigenständiges Binary
mit JSON-Schnittstelle, das das Python-Labor als Messinstrument behält.
C ist für dieses Projekt keine sinnvolle Option (Abschnitt 7).

---

## 1. Die Frage und die Messlatte

Die Frage war: Kern nach C oder Rust, geht das, was wird schneller, leidet
die Wartbarkeit, und was müsste sich ändern, wenn Geschwindigkeit und
Footprint das Ziel sind. Der vermutete Hauptgewinn war die Größe.

Zwei Dinge muss man dafür auseinanderhalten, weil sie im Bundle vermischt
sind:

- **Was Python kostet**: Interpreter, NumPy, Bytecode. Das ist der Teil, den
  nur ein Sprachwechsel entfernt.
- **Was unsere Bibliothekswahl kostet**: librosa, Qt. Das ist der Teil, der
  in jeder Sprache verschwindet, sobald man ihn ersetzt, auch in Python.

Der Abschnitt 3 zeigt, dass der zweite Posten fünfmal so groß ist wie der
erste. Das verschiebt die Frage: nicht "Python oder Rust", sondern "welche
Abhängigkeiten tragen ihr Gewicht".

## 2. Was der Kern ist

Der Live-Pfad, in Lesereihenfolge des Signals. Zeilen sind grobe
Richtwerte aus `wc -l`.

| Baustein | Modul | Zeilen | Fremdcode, den er braucht |
|---|---|---|---|
| Audio-Umleitung | routing.py, winaudio.py, wincapture.py | ~1990 | pactl (Prozess), Windows COM über ctypes |
| Verzögerungspuffer, Einzähler, Mute | delay_stream.py | 560 | PortAudio (sounddevice) |
| Mitschnitt (Record-Modus) | record_buffer.py | 550 | nur NumPy |
| Kontrollfläche (Pad-Synthese) | control_pad.py | 170 | nur NumPy |
| CQT, Resampling | btc.features_from_audio | 30 | librosa.cqt, librosa.resample (soxr) |
| BTC-Transformer | btc.BTCModel | 130 | nur NumPy (reiner Vorwärtspass) |
| Grenzverfeinerung | btc.refine_boundary | 50 | librosa HPSS, chroma_cqt, onset_strength |
| Bass-Messung, Durchgangsbass | bass.py, btc.fold_* | 400 | nur NumPy |
| Beat-Tracker | beats.py | 540 | ONNX Runtime, Mel-Filterbank (librosa, einmalig) |
| Tonart, Schreibweise, Stufen | tonality.py | 470 | nur NumPy |
| Merge, Ledger, Blip-Sperre, Snap | cli._merge_model_segments, EventLedger | ~450 | reines Python |
| Anzeigeschleife | cli._display_loop | ~370 | reines Python |
| Web-Anzeige (SSE, QR) | web.py, data/index.html | 300 + HTML | Standardbibliothek, qrcode |
| Kontrollfenster | gui.py, engine.py | 1250 | PySide6 (Qt) |

Drei Beobachtungen daraus:

1. **librosa wird an genau drei Stellen gerufen** (CQT für das Modell,
   HPSS/Chroma/Onset in der Verfeinerung, Mel-Filterbank beim Start), und
   keine davon ist exotisch. Dafür kostet es 345 MB und den numba-Warmup.
2. **Die eigentliche Erkennung ist schon "portiert"**: BTC läuft als reiner
   NumPy-Vorwärtspass, bit-exakt gegen Torch abgenommen (test_btc.py). Das
   ist die Blaupause dafür, wie ein weiterer Port aussieht: Golden-Fenster,
   Vergleich, fertig.
3. **Das Wissen steckt in den 800 Zeilen Buchführung** (Merge, Ledger,
   Regeln) und in tonality/bass. Das ist der Teil, der sich im Git-Verlauf am
   häufigsten ändert: Acht der letzten neun Code-Commits auf main (ohne
   Release-Bumps) fassen cli.py, bass.py oder btc.py an. Dort entscheidet
   sich die Wartbarkeitsfrage.

## 3. Wo die 236 MB herkommen

Gemessen am Inhaltsverzeichnis des PyInstaller-Builds
(`build/jampilot/PKG-00.toc`, 2071 Einträge). Das onefile-Binary ist 236 MB
groß, ausgepackt sind es 607 MB; Windows liefert dieselben Teile als Ordner
(363 MB laut UNDER-THE-HOOD, andere Plattformbibliotheken).

| Posten | ausgepackt | Warum es drin ist |
|---|---:|---|
| llvmlite (eine .so) | 180 MB | numbas JIT-Compiler; librosa importiert numba auf unserem Pfad |
| PySide6 + shiboken | 102 MB | Kontrollfenster (QtCore, QtGui, QtWidgets nach allen Ausschlüssen) |
| scipy | 74 MB | von librosa importiert; wir rufen nichts direkt |
| onnxruntime | 64 MB | Beat-Modell (die .so selbst ~29 MB, dazu das Python-Binding ~31 MB) |
| System-.so-Kopien | 54 MB | davon ~25 MB GTK/X11/Cairo/HarfBuzz (zieht Qt), libpython 9 MB, libcrypto 5 MB |
| numpy | 43 MB | Rechenkern, davon 28 MB OpenBLAS |
| Python-Bytecode (PYZ) | 23 MB | alle .pyc, Großteil scipy/sklearn/librosa |
| jampilot/data | 23 MB | BTC-Gewichte 11,8 MB, Beat-Modell 10,6 MB, Icons, HTML |
| scikit-learn | 16 MB | von librosa importiert; wir rufen nichts |
| numba | 16 MB | dito |
| Rest (soundfile, soxr, msgpack, cffi, certifi, ...) | ~12 MB | |

Zusammengefasst:

| Gruppe | ausgepackt | Anteil |
|---|---:|---:|
| librosa-Welt (llvmlite, numba, scipy, sklearn, librosa, msgpack) | ~345 MB | 57 % |
| Qt-Welt (PySide6 + GTK/X11-Stack) | ~130 MB | 21 % |
| Python + NumPy + Bytecode-Rest | ~60 MB | 10 % |
| ONNX Runtime | ~64 MB | 11 % |
| Modellgewichte, HTML, Icons | ~23 MB | 4 % |

Der Sprachwechsel allein, also Python und NumPy raus, spart die dritte Zeile.
Die ersten beiden Zeilen sind Bibliothekswahl und fallen in jeder Sprache,
sobald man sie ersetzt. ONNX Runtime und die Gewichte bleiben in jeder
Sprache, solange die Modelle bleiben.

## 4. Wo die Zeit hingeht

Gemessen heute mit Zufallsrauschen (10-s-Fenster, 48 kHz), nach Warmlaufen,
jeweils Minimum über mehrere Läufe. Deckt sich mit den Zahlen aus
audio-aussetzer-analyse.md vom 9. September.

| Schritt im Hop (alle 250 ms) | Zeit | Läuft eigentlich in |
|---|---:|---|
| CQT 10 s inkl. Resampling (Filterbank memoisiert) | 22 ms | FFT (scipy/numpy, C), soxr (C) |
| BTC-Transformer, 108 Frames | 27 ms | OpenBLAS (C/Assembler) |
| Grenzverfeinerung, je frischer Grenze (0–1 pro Hop) | 121 ms (p90 ~210) | HPSS: STFT + Medianfilter (scipy.ndimage, C); chroma_cqt; Onset |
| Merge, Ledger, Tonart, Bass, SSE | einstellige ms | reines Python |

Außerhalb des Hops:

| | Zeit | |
|---|---:|---|
| Beat This!, 10-s-Fenster, einmal je Sekunde, eigener Thread | 460 ms | ONNX Runtime, ein Thread; "int8 und Fusion helfen nicht" (beats.py) |

Start und Speicher:

| | gemessen |
|---|---:|
| onefile auspacken (Linux) | ~2,5 s |
| erster librosa/numba-Aufruf (Cache warm) | 2,6 s |
| dito ohne Cache (erster Start eines Bundles) | bis 23 s, laut engine.py bis zu einer Minute |
| Beat-Modell laden | 1,0 s |
| RSS nach Import von numpy, librosa, ORT, Qt | 68 MB |
| RSS nach dem ersten CQT-Aufruf (numba übersetzt) | 333 MB |
| RSS nach Warmlaufen aller Pfade inkl. Beat-Modell | 571 MB |

Lesart: Das Budget von 250 ms ist in der Regel eingehalten, die Verfeinerung
reißt es im p90, und das ist bekannt und absichtlich (ein Rasterpunkt fällt
aus, das Raster bleibt). Der Python-Anteil an der Hop-Zeit ist unter 5 %.
Was ein Port an Rechenzeit holen kann, holt er in der Verfeinerung
(Medianfilter und drei Transformationen über denselben Ausschnitt, die man
nativ in einem Durchgang fusioniert), nicht im Modell. Was er an Start und
Speicher holt, ist groß, weil dort fast alles librosa/numba ist.

## 5. Geht es? Baustein für Baustein

Für jeden Baustein: das native Gegenstück, der Aufwand als Größenordnung,
und das Risiko, das nicht im Code steht.

**Audio-Ein-/Ausgabe.** PortAudio ist eine C-Bibliothek; sounddevice ist nur
der Wrapper. C ruft es direkt, Rust hat `cpal` (nativ ALSA/WASAPI/CoreAudio)
oder ebenfalls PortAudio-Bindings. Der Ringpuffer, der Einzähler, Mute, die
DAC-Zeitstempel (`audible_position`) sind 300 Zeilen Arithmetik. Risiko:
WASAPI-**Loopback** auf dem stummen Umweg (wincapture.py) ist kein
Standardfall; cpal kann das meines Wissens nicht von Haus aus, man schreibt
es wie heute gegen `IAudioClient` direkt, in Rust über das `windows`-Crate.
Das ist dieselbe Arbeit wie die heutigen 900 Zeilen ctypes, nur mit Typen.
Eher einfacher als heute.

**Routing.** Linux ruft `pactl` als Prozess, das bleibt. Windows ist
COM-Code, siehe oben. macOS fasst JamPilot nicht an (BlackHole). Keine
Schwierigkeit, aber viel Fläche und drei Plattformen zum Testen.

**Resampling.** Heute librosa.resample mit soxr darunter. Nativ: libsoxr
direkt (C, beide Sprachen) oder `rubato` (Rust). Ergebnisse weichen in den
letzten Bits ab, nicht hörbar, aber jede Abweichung an der Modelleingabe
muss gegen das Referenzset gemessen werden (siehe Vorbehalt unten).

**CQT.** librosas `cqt` ist eine Filterbank im Frequenzbereich mit
oktavweisem Downsampling. Eine eigene Implementierung ist 150 bis 250
Zeilen, `rustfft`/`realfft` oder FFTW/pocketfft darunter. **Das ist der
Baustein mit dem versteckten Risiko:** Die Features müssen nicht bit-exakt
sein, aber das Live-Verhalten hängt an Details, die nicht in der
Feature-Genauigkeit sichtbar sind. Präzedenzfall ist die inkrementelle CQT
vom August: Features identisch, trotzdem 7 % mehr Events, weil das je Hop
wandernde Frameraster als Dither wirkt, den der Debounce nutzt. Ein Port muss
also dieselbe Fensterung, dasselbe Padding und dieselbe Rasterlage
reproduzieren und wird danach am Referenzset abgenommen, nicht am
Golden-Fenster allein.

**BTC-Transformer.** Schon heute reiner Vorwärtspass: LayerNorm, vier
Matmuls je Attention-Block, zwei 1-D-Convs, Softmax, über 108 Frames. In
Rust mit `ndarray` + `matrixmultiply` oder `faer` sind das 300 Zeilen; in C
mit OpenBLAS oder handgeschriebenen Kerneln ähnlich. Alternative, die den
Code noch kleiner macht: das Torch-Original im ML-Repo nach ONNX
exportieren und über dieselbe ONNX Runtime laufen lassen wie das
Beat-Modell. Dann gibt es eine Modell-Laufzeit statt zwei Codepfaden.
Golden-Fixture ist vorhanden.

**Grenzverfeinerung (HPSS, Chroma, Onset).** HPSS ist STFT, zwei
Medianfilter (Zeit- und Frequenzrichtung), Soft-Mask, iSTFT; Onset-Stärke
ist Mel-Spektrogramm plus spektraler Fluss; die Mel-Filterbank steht schon
in beats.py. Zusammen 300 bis 400 Zeilen. Nativ kann man die drei
Transformationen über denselben 1,5-s-Ausschnitt fusionieren; das ist die
eine Stelle, an der ein Port messbar Rechenzeit gewinnt (121 ms → geschätzt
40 bis 60 ms).

**Beat This!** Bleibt ONNX. In C die ORT-C-API, in Rust das `ort`-Crate;
beides zieht die ~29 MB große Laufzeitbibliothek mit. Reine Rust-Laufzeiten
(`tract`, `candle`) würden das sparen, aber ob sie das Frontend des Modells
(partielle Attention) vollständig und mit vergleichbarer Geschwindigkeit
abdecken, müsste man ausprobieren; ich würde es nicht versprechen. Die 460 ms
je Fenster bleiben in jeder Sprache, das ist das Modell.

**Timeline-Logik: Merge, Ledger, Blip-Sperre, Snap, Durchgangsbass,
Quinten-Regel, Tonart mit Hysterese, Takt-Phase.** Reines Python ohne
Abhängigkeiten, portiert sich 1:1. Aufwand: 1500 Zeilen abschreiben und
die zugehörigen Tests (test_cli.py, test_tonality.py, test_bass.py,
test_beats.py Teil 2) nachziehen. Technisch der einfachste Teil. Fachlich
der heikelste, siehe Abschnitt 7.

**Web-Anzeige.** HTTP-Server mit SSE und ein QR-Code. In Rust `tiny_http`
oder `axum` plus `qrcode`; in C ein kleiner eingebetteter Server
(civetweb/mongoose) oder handgeschrieben. index.html bleibt wie sie ist.
Trivial.

**Kontrollfenster.** Heute Qt, 624 Zeilen mit Animationen. Nativ: `egui`
oder `iced` (Rust, 5 bis 10 MB, eigene Zeichnung, überall gleich),
`slint`, oder ein Tray-Icon ohne Fenster. In C: GTK (unter Linux
Systembibliothek, unter Windows ein Problem) oder Win32 pur. Die
Produktanforderung dahinter ist klein: ein sichtbarer Schalter, der die
Umleitung zurückdreht, und eine Statuszeile. Das erfüllt auch ein Tray-Icon
mit Menü, und der Browser zeigt den Rest ohnehin.

**Mitschnitt, Pad-Synthese, Einzähler.** Array-Arithmetik. Trivial.

**Plattformen und Bauen.** Hier ist Rust dem heutigen Stand klar
überlegen: PyInstaller kann nicht cross-kompilieren, Rust kann es (Linux
x86_64 und aarch64, Windows, macOS beide Architekturen aus einer CI). Ein
statisch gelinktes Linux-Binary löst nebenbei die glibc-Frage aus
UNDER-THE-HOOD. Die ONNX-Laufzeit bleibt eine dynamische Bibliothek je
Plattform.

**Was ein Port NICHT verändert:** die Erkennungsqualität. Dieselben
Gewichte, dieselben Regeln, dieselben Fehler. Wer sich davon besseres Timing
oder weniger Flackern verspricht, bekommt es nicht.

## 6. Was schneller wird und was nicht

| | heute | nativ (Schätzung) | für den Spieler |
|---|---|---|---|
| Startzeit bis erste Anzeige | ~5 s warm, bis 30 s kalt (onefile + numba) | < 1 s | **spürbar**, trifft "Null Anlauf" |
| Hop-Rechenzeit | 170–300 ms | 100–200 ms (Verfeinerung fusioniert) | nicht spürbar, Vorlauf bleibt gleich |
| Beat-Modell | 460 ms / 10 s | 460 ms / 10 s | gleich |
| Arbeitsspeicher | 570 MB | 60–120 MB (ORT + Gewichte + Puffer) | nur auf kleinen Rechnern |
| Audio-Callback | teilt den GIL mit der Analyse, GC-Pausen 36–74 ms | eigener Thread, keine Pausen | **vielleicht**: Z820-Aussetzer, falls GC/GIL die Ursache sind, was offen ist |
| Download | 236 MB | 30–50 MB | spürbar beim ersten Mal |
| Erkennung, Timing, Flackern | | | **unverändert** |

Der Vorlauf ist eine Verzögerung minus Randschutz, keine Rechenzeit. Mehr
Tempo im Hop kauft keinen längeren Vorlauf. Was Tempo kaufen würde, ist
Luft für mehr Rechnung je Hop (ein größeres Modell, ein zweiter Durchgang),
und das ist heute nicht der Plan.

## 7. Leidet die Wartbarkeit?

Ja, an drei konkreten Stellen, und ein Teil davon ist unabhängig von der
Sprache.

**1. Das Labor ist Python und ruft die Module direkt.** tests/reference
hat 13 Messskripte, die `_merge_model_segments`, `EventLedger`,
`refine_boundary`, `BeatGrid` importieren und am Referenzset auswerten. Die
Realaudio-Reports entstehen genauso. Das ML-Repo trainiert in Torch und
exportiert nach NumPy/ONNX. Jede Regeländerung der letzten zwei Monate
(Blip-Sperre, Durchgangsbass, Quinten-Regel, Onset-Shift) lief als
"Variante bauen, Referenzset messen, verwerfen oder behalten", oft mehrere
Varianten am Tag. Ein nativer Kern hat zwei Möglichkeiten: Entweder das
Labor misst weiter am Python-Code und der Kern wird nachgezogen (zwei
Implementierungen jeder Regel, die auseinanderlaufen werden), oder der Kern
bietet eine Schnittstelle (`analyze` → JSON-Events) und das Labor misst
daran. Die zweite ist richtig, kostet aber jeden Experimentierzyklus den
Umweg über Compiler und Schnittstelle. Für ein Projekt, dessen Fortschritt
fast ausschließlich aus solchen Zyklen besteht, ist das der eigentliche
Preis.

**2. Die numerische Abnahme ist nicht "Tests grün".** Drei Vorfälle im
Projekt zeigen, dass gleiche Features nicht gleiches Verhalten bedeuten:
inkrementelle CQT (+7 % Events bei identischen Features), gestückelte CQT
(+31 ms Drift je 10 s), Bass-Notenbins (Bass wochenlang leer statt falsch).
Jeder portierte DSP-Baustein ändert die letzten Bits, und nach jedem muss
das Referenzset laufen (Root-Accuracy, Events, Timing-Median), nicht nur
das Golden-Fenster. Das ist Arbeit, die kein Compiler abnimmt, und sie
fällt in jeder Zielsprache an, auch beim Python-Weg aus Abschnitt 8.

**3. Ein Entwickler, der in NumPy denkt.** Der Code ist durchgängig als
Begründungsprosa geschrieben; das überträgt sich in jede Sprache. Nicht
überträgt sich die Geschwindigkeit, mit der man heute eine Idee
ausprobiert: eine Zeile NumPy, ein Messskript, eine Stunde. In Rust steht
dazwischen der Borrow-Checker um Ringpuffer, Callback und drei Threads
herum, und das ist zu Beginn langsam. In C steht dazwischen nichts, und
genau das ist das Problem: ein Prozess, der stundenlang Audio durch einen
Ringpuffer schiebt, mit Index-Arithmetik ohne Netz.

**Was besser würde:** Typen an den Grenzen (Stream-Frames gegen Sekunden
gegen Feature-Frames, heute drei Floats, die man verwechseln kann), ein
Compiler, der die Thread-Geschichte prüft, kein GIL, kein PyInstaller-Spec
mit "jeder weitere Ausschluss endete im Absturz".

**C oder Rust?** Rust. Die Gründe sind nicht ideologisch: cargo gegen
Makefiles und Vendoring, Cross-Compilation ab Werk, `cpal`/`rustfft`/
`rubato`/`ort`/`tiny_http` als gepflegte Crates, Thread-Sicherheit im
Typsystem an der Stelle, wo JamPilot sie braucht (Callback gegen Analyse
gegen Beat-Thread). C hätte als einzigen Vorteil, dass es als Bibliothek in
alles einbettbar ist, und das ist kein Ziel dieses Projekts.

## 8. Der kleinere Weg: Footprint ohne Sprachwechsel

Weil 78 % des Bundles Bibliothekswahl sind, gibt es einen Weg, der die
Größe angeht und das Labor unberührt lässt.

**Stufe 1: librosa ersetzen.** Vier Routinen in NumPy, ohne scipy:

- `cqt` (Filterbank, oktavweises Downsampling, dieselbe Rasterlage), ~200
  Zeilen; Abnahme gegen das vorhandene Golden-Fenster und das Referenzset.
- `hpss`/`harmonic` (STFT, zwei Medianfilter, Soft-Mask, iSTFT); der
  Medianfilter über Stride-Tricks und `np.median`, auf einem 1,5-s-Ausschnitt
  mit 23-ms-Hop sind das kleine Matrizen.
- `onset_strength` (Mel + spektraler Fluss); die Mel-Filterbank aus beats.py
  wird zur gemeinsamen Funktion.
- Resampling über das `soxr`-Python-Paket direkt (0,5 MB, schon im Bundle).

Weg sind damit llvmlite, numba, scipy, scikit-learn, librosa, msgpack,
audioread, lazy_loader: rund 345 MB ausgepackt. Weg ist der numba-Warmup
(2,6 s warm, bis 23 s kalt) und der Grund, weshalb der erste Start eines
Bundles eine Minute dauern kann. Weg ist die Hälfte der Spec-Sonderfälle.
Was bleibt: NumPy mit seiner eigenen FFT (`np.fft`, pocketfft, schnell
genug für 10 s bei 22 kHz) und OpenBLAS.

Erwartung, grob über die heutige Kompressionsrate (236/607): Bundle
ausgepackt ~260 MB, onefile **~100 MB**. Startzeit ohne numba: Auspacken
2,5 s plus Modell laden 1 s. Als onedir-Ordner, wie Windows ihn schon
bekommt: gut eine Sekunde.

Aufwand: eine bis zwei Wochen inklusive der Messrunde am Referenzset, die
hier nicht entfallen darf (Abschnitt 7, Punkt 2).

**Stufe 2: Qt ersetzen.** Das Kontrollfenster braucht einen Schalter, eine
Statuszeile, einen Record-Knopf. Optionen in Python: tkinter (in CPython
enthalten, PyInstaller bündelt Tcl/Tk mit ~10 MB; nüchterner als das
heutige Fenster, keine Animationen), oder gar kein Fenster und stattdessen
ein Tray-Icon plus Browser-Steuerung (die Bibliotheken dafür ziehen unter
Linux wieder GTK, also nur unter Windows/macOS ein Gewinn). Erwartung mit
tkinter: ausgepackt ~160 MB, onefile **~60–70 MB**. Das ist die Grenze
dessen, was Python erreicht: Interpreter, NumPy, ONNX Runtime, Gewichte.

**Was nach beiden Stufen übrig bleibt, und was Rust davon noch holt:**

| | nach Stufe 1+2 (Python) | Rust |
|---|---:|---:|
| Download | ~60–70 MB | ~30–50 MB |
| Start (onedir) | ~1–1,5 s | < 0,5 s |
| RSS | ~250 MB (geschätzt, ohne numba) | 60–120 MB |
| Audio-Callback | weiter unter GIL/GC | frei |
| Labor | unverändert | Schnittstelle nötig |

Der Rest-Gewinn von Rust ist real, aber er liegt bei Faktor 1,5 bis 2 statt
bei Faktor 5 bis 8, und er kostet das Labor. Ob er das wert ist, kann man
erst nach Stufe 1 beurteilen, wenn man ein 100-MB-Bundle in der Hand hat
und weiß, ob es sich "dick" anfühlt.

**Unabhängig von allem:** Die Gewichte sind float32. BTC in float16 wären
6 statt 12 MB, das ONNX-Modell 5 statt 11 MB; ob die Erkennung das
verträgt, ist eine Nachmittagsmessung. Das spart 11 MB in jeder Sprache.

## 9. Wenn Rust, dann so

Falls die Entscheidung irgendwann für Rust fällt, drei Regeln, die vor dem
ersten Crate feststehen sollten:

1. **Ein Kern-Binary, das Python-Labor bleibt Messinstrument.** Der Kern
   bietet `jampilot-core analyze <wav>` mit JSON-Events (dasselbe Format,
   das heute über SSE geht) und `jampilot-core run` als Live-Betrieb. Die
   Messskripte in tests/reference rufen `analyze` statt die Module. Das
   zwingt die Schnittstelle sauber zu halten und erlaubt, Python-Kern und
   Rust-Kern am selben Referenzset gegeneinander zu messen, solange beide
   existieren.
2. **Bausteinweise, Fixture zuerst.** Reihenfolge nach Risiko und
   Abnehmbarkeit: BTC (Golden-Fenster vorhanden) → Beat This! über `ort`
   (Golden-Fenster vorhanden) → CQT (Referenzset-Abnahme, Dither-Vorbehalt)
   → HPSS/Verfeinerung → Timeline-Logik (Tests portieren) → Audio/Routing
   je Plattform → Web → Fenster. Jeder Schritt endet mit einer Messung am
   Referenzset, nicht mit grünen Unit-Tests.
3. **Nichts "bei der Gelegenheit" verbessern.** Jede Regel wird so
   portiert, wie sie ist, inklusive der Stellen, die man anders machen
   würde. Verbesserungen kommen danach, einzeln, gemessen. Sonst weiß man
   bei der ersten Abweichung am Referenzset nicht, ob es der Port war oder
   die Idee.

Größenordnung für eine Person, alle drei Plattformen, mit Parität am
Referenzset: zwei bis vier Monate, in denen am Produkt sonst wenig
passiert. Plus danach dauerhaft der Umweg in jedem Experiment. Das ist
keine Zahl, die ich belegen kann; sie ist aus dem Umfang der Tabelle in
Abschnitt 2 geschätzt, und bei der Windows-Portierung lag der unterschätzte
Teil nicht im Code, sondern in der Auslieferung (windows-portierung.md).

## 10. Was ich nicht empfehlen würde

- **PyO3-Hybrid** (Rust-Erweiterung in Python): Für die Größe bringt es
  nichts, Python und NumPy bleiben im Bundle, und der Rechenzeit-Gewinn
  ist nach Abschnitt 4 nicht das Problem. Es wäre der Aufwand eines Ports
  ohne seinen Nutzen.
- **C**: siehe Abschnitt 7.
- **Mit Rust anfangen, bevor Stufe 1 gemessen ist.** Die Hälfte des
  Gewinns liegt in librosa, und der ist in Python billiger zu haben. Wer
  danach noch Rust will, hat dann schon die eigene CQT und HPSS als
  abgenommene Referenz, die man portiert, statt librosa nachzubauen.

## 11. Nächste Schritte, falls es weitergeht

1. Stufe 1 als Branch: `cqt`, `hpss`, `onset_strength` in NumPy, soxr
   direkt. Abnahme: test_btc-Golden-Fenster, dann
   `messung_meilensteine.py` am Referenzset gegen main.
2. Bundle neu bauen, `dist/jampilot selftest`, Größe und Startzeit messen
   und in dieses Dokument nachtragen.
3. float16-Gewichte messen (Nachmittag).
4. Erst dann die Qt-Frage, erst danach die Rust-Frage, jeweils mit den
   gemessenen Zahlen aus Schritt 2 statt mit den Schätzungen hier.

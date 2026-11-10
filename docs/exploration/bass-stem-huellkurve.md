# Bass-Stem fuer die Huellkurve (2026-11-09)

Branch `feature/wellenform-laufband`. Frage: Wie aufwaendig ist ein echter
Bass-Stem fuer die Huellkurve unter dem Laufband - denn das Tiefband
(30..250 Hz) zeigte jede Bassdrum als Anschlag.

## Optionen

| | Aufwand | Qualitaet | Preis |
|---|---|---|---|
| HPSS (librosa, Median-Filter) | halber Tag | Kick-Ausklang bleibt tonal drin | keiner |
| **Open-Unmix UMX-HQ als ONNX** | 2-4 Tage | mittel, Kick weitgehend weg | 9 MB int8, ~90 ms/Hop auf einem Kern |
| Demucs (htdemucs) | 1-2 Wochen | sehr gut | torch, 80 MB Gewichte, CPU grenzwertig |

Gewaehlt: Open-Unmix. onnxruntime ist wegen des Beat-Modells ohnehin im
Bundle; die UMX-HQ-Gewichte stehen auf Zenodo (3370489) unter MIT. UMX-L
(CC BY-NC-SA 4.0) ist nur zur Einordnung mitgemessen und bleibt draussen.

## Export

`tests/reference/export_umx_bass.py` (braucht torch und openunmix, nur zum
Export). Die Vorwaertsfunktion ist neu geschrieben, weil `OpenUnmix.forward`
die Framezahl ueber `x.data.shape` einbrennt - mit `x.shape` und `reshape(-1)`
bleibt die Frame-Achse dynamisch. ORT gegen torch: relative Abweichung < 1e-6.

| Modell | Datei | 6-s-Block, 4 Threads | 1 Thread |
|---|---|---|---|
| umxhq fp32 | 35,6 MB | 65 ms | 213 ms |
| umxhq int8 (dynamisch) | 9,0 MB | - | 277 ms |
| umxl fp32 | 113 MB | 182 ms | 671 ms |

(Xeon E5-2680 v2, 2013, kein AVX2 - int8 ist hier langsamer als fp32; auf
CPUs mit VNNI ist es schneller. Die Messwerte unten sind fuer int8 gleich.)

## Messung

`tests/reference/messung_bass_stem.py`. Referenz: echte Stems - Sailing to
Philadelphia (Bass-Stem, `tests/realaudio/`), Echoes (alle Stems, Mix =
Summe). Je 60-90 s mit viel Bass (Echoes: Bass UND Drums). Huellkurven wie
in envelope.py (RMS je 12,5 ms), Verschiebung bis +-20 Bloecke ausgeglichen.

- corr: Korrelation der berechneten Huellkurve mit der des echten Bass-Stems
- leak: mittlere Hoehe, wo der echte Bass still ist (< 5 % max), relativ zu laut
- drum: Korrelation des Rests (nach linearem Fit auf den Bass) mit der Drum-Huellkurve

Stereo-Eingang, 6-s-Bloecke mit 1 s Rand:

| Methode | Sailing corr | leak | Echoes corr | leak | drum |
|---|---|---|---|---|---|
| Bandpass 30-250 Hz (bisher) | 0,30 | 0,73 | 0,81 | 0,29 | 0,59 |
| umxhq | 0,79 | 0,36 | 0,96 | 0,06 | -0,06 |
| umxl | 0,86 | 0,28 | 0,97 | 0,06 | -0,11 |

Mono-Eingang (so ist das Analysefenster live), hopweise, umxhq:

| core | Kontext links | rechts | Sailing corr | Echoes corr | drum | ms/Hop (1 Thread) |
|---|---|---|---|---|---|---|
| 6,00 | 1,0 | 1,0 | 0,74 | 0,95 | 0,18 | 433 |
| 0,25 | 1,0 | 1,0 | 0,75 | 0,94 | 0,15 | 110 |
| **0,25** | **1,0** | **0,5** | **0,74** | **0,93** | **0,13** | **87** |
| 0,25 | 0,5 | 0,5 | 0,74 | 0,92 | 0,15 | 64 |
| 0,25 | 2,0 | 1,0 | 0,75 | 0,95 | 0,16 | 154 |
| 0,25 int8 | 1,0 | 0,5 | 0,74 | 0,93 | 0,13 | 108 |

Lesart: Hopweise mit kleinem Kontext ist so gut wie am Stueck; Mono kostet
gegenueber Stereo ein wenig (0,79 -> 0,74). Die Kick ist raus (drum 0,59 ->
0,13). Was bleibt (Sailing corr 0,74, nicht 1,0), ist die Trennqualitaet von
UMX-HQ selbst - Demucs laege hoeher, zu dem oben genannten Preis.

## Betrieb

stems.py: ein Lauf je Hop auf dem juengsten Hop des Analysefensters, 1,0 s
Kontext davor, 0,5 s dahinter, eigener Thread mit einem ORT-Thread
(BeatTracker-Muster). Rueckstau wird zu einem Lauf zusammengefasst, ueber
4 s Kern faellt das Aelteste weg (Nullen in der Kurve). Die Bass-Kurve der
Huellkurve hinkt der Analysefront damit um gut 0,75 s nach - bei --delay 5
reicht sie ~4 s vor JETZT, die Spur zeigt 2,8 s. Ohne onnxruntime oder
Modell: Bandpass wie zuvor.

Offen: Proberaum-Test; ob der eigene Thread auf dem Proberaum-PC neben Beat-
und Akkordmodell ohne Aussetzer laeuft (Aussetzer-Messung wie in
audio-aussetzer-analyse.md).

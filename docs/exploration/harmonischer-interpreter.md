# Harmonischer Interpreter statt Akkorderkennung

*Explorationsdokument. Status: These mit Literaturlage und Code-Bestandsaufnahme.
Kein Implementierungsplan — eine Entscheidungsgrundlage.*

---

## Die These

Die meisten Programme behandeln Musik als **Signalverarbeitungsproblem**: Welche
zwölf Tonklassen liegen gerade im Spektrum? Das ist eine Frage über *Audio*.

Ein Mensch beantwortet eine andere Frage. Er hört einen Akkord nicht aus dem
aktuellen Spektrum, sondern aus Kontext: Tonart, Bass als harmonisches Fundament,
was vorher kam, was als Nächstes wahrscheinlich ist, welches Genre, welche
Taktposition. Und er entscheidet nicht, *was klingt*, sondern **was er
aufschreiben würde**.

Der letzte Schritt der Pipeline wäre demnach kein Detektor, sondern ein
**harmonischer Interpreter**: Er bekommt nicht nur ein Chromagramm, sondern
Tonart, Bassgrundton, die bisherige Akkordfolge, Tempo, Taktposition, Genre und
die Konfidenzen aller Einzelanalysen — und entscheidet daraus, **welcher Akkord
dem Musiker am sinnvollsten angezeigt wird.**

Dieses Dokument prüft die These gegen zwei Realitäten: die Forschungslage und den
eigenen Quelltext. Ergebnis vorweg:

- Die These ist **richtig und von der Forschung ausdrücklich formuliert** — als
  unerledigte Hausaufgabe des Feldes.
- Sie ist **nicht neu**. Genau dieser Ansatz ist seit 2012 kommerzialisiert — von
  einer Firma namens *Chordify*. Dieses Projekt hieß bis zur Recherche für dieses
  Dokument genauso; es heißt seitdem **JamPilot**.
- Der Teil, der **wirklich unbesetzt** ist, ist ein anderer als gedacht — und
  dieses Projekt hat dafür durch den Vorlauf einen strukturellen Vorteil, den die
  Konkurrenz nicht hat.

---

# Teil I — Was die Forschung weiß

## 1. Das Feld hat den Unterschied selbst benannt

Die Trennung, um die es hier geht, ist bereits publiziert — in der einflussreichsten
Kritik des Feldes:

> **Humphrey & Bello (2015), „Four Timely Insights on Automatic Chord Estimation",
> ISMIR** — [PDF](https://archives.ismir.net/ismir2015/paper/000294.pdf)

Die Autoren trennen wörtlich zwei Aufgaben, die die Community vermische
„to some undefined degree":

| | |
|---|---|
| **chord recognition** | „quite literal, and is closely related to polyphonic pitch detection" |
| **chord transcription** | „an abstract task related to functional analysis, taking into consideration high-level concepts such as long term musical structure, repetition, segmentation or key" |

Das ist exakt die These dieses Dokuments, zehn Jahre älter. Sie ist also nicht
spekulativ — sie ist **die offene Baustelle, die das meistzitierte Kritikpapier
des Feldes benannt und niemand geschlossen hat.**

## 2. Es gibt keine Wahrheit, die man detektieren könnte

Der stärkste Beleg gegen „Detection" ist nicht technisch, sondern empirisch:
**Menschen sind sich nicht einig, welcher Akkord da steht.**

> **Koops, de Haas, Burgoyne, Bransen, Kent-Muller, Volk (2019), „Annotator
> subjectivity in harmony annotations of popular music", Journal of New Music
> Research 48(3)** —
> [DOI](https://www.tandfonline.com/doi/full/10.1080/09298215.2019.1613436) ·
> [Datensatz CASD](https://github.com/chordify/CASD)

Vier Experten, 50 Songs:

- **73 %** Übereinstimmung im Dur/Moll-Vokabular — **54 %** bei den komplexesten Labels.
- **Unter 20 %** der Akkordlabels werden von allen vieren geteilt.
- Die Spitzensysteme von MIREX 2017 liegen **etwa 10 % über dieser
  „subjectivity ceiling"**. Die Maschinen sind also bereits „genauer", als
  Menschen untereinander einig sind.

Und der Befund, der für ein Musikerwerkzeug alles verändert:

> Die beiden **Gitarristen** unter den Annotatoren teilen deutlich mehr Labels
> miteinander als mit den beiden **Pianisten**.

**Das gewählte Label hängt vom Instrument des Spielers ab.** „Welcher Akkord ist
richtig?" hat keine eindeutige Antwort. „Welcher Akkord ist für *diesen* Spieler
nützlich?" hat eine — und das ist eine Frage, die man beantworten kann.

Bestätigt von der großen Übersichtsarbeit:

> **Pauwels, O'Hanlon, Gómez, Sandler (2019), „20 Years of Automatic Chord
> Recognition from Audio", ISMIR** —
> [PDF](https://archives.ismir.net/ismir2019/paper/000004.pdf)
>
> „what exactly contributes to a chord is ill-defined … the granularity of a chord
> sequence … **depends on the user or use-case**."

## 3. Das Plateau ist real — und mehr Signalmodellierung kauft nichts mehr

Zahlen aus dem Transformer-Papier (Park et al., ISMIR 2019, „A Bi-directional
Transformer for Musical Chord Recognition",
[PDF](https://archives.ismir.net/ismir2019/paper/000075.pdf)), WCSR in Prozent:

| Modell | Maj-min | MIREX | Triads | Sevenths | Tetrads |
|---|---|---|---|---|---|
| CNN | 81.8 | 79.8 | 75.5 | 71.5 | 65.2 |
| CRNN | 82.3 | 79.9 | 75.3 | 71.3 | 65.2 |
| **BTC (Transformer)** | **82.7** | 80.8 | 75.9 | 71.8 | 65.5 |

Ein bidirektionaler Transformer schlägt ein simples CNN um **0,9 Punkte** — innerhalb
der Standardabweichung. Von 2019 bis 2025 kommen ein bis zwei Punkte dazu
(ChordFormer, [arXiv:2502.11840](https://arxiv.org/html/2502.11840): 84,1 %).

Noch aussagekräftiger: ChordFormer erreicht über 301 Akkordklassen eine
*frame-wise* Genauigkeit von 0,788 — aber eine ***class-wise* Genauigkeit von
0,388**. Die häufigen Akkorde sind gelöst; die seltenen sind es nicht; die
häufigen dominieren die Metrik. Passend dazu Pauwels et al.: **fünf Akkordtypen
decken über 80 % der Popmusik-Datensätze ab.**

Auch das Sprachmodell-Argument ist schwächer, als man hofft. Korzeniowski &
Widmer zeigen, dass Sprachmodelle auf *Frame*-Ebene prinzipiell nutzlos sind
([arXiv:1702.00178](https://arxiv.org/abs/1702.00178) — Titel: „On the **Futility**
of Learning Complex Frame-Level Language Models for Chord Recognition"); auf
Akkordfolgen-Ebene helfen sie, aber „their effects are small compared to other
domains" ([arXiv:1808.05341](https://arxiv.org/abs/1808.05341)).

**Der Signalpfad ist ausgereizt. Wer hier noch Punkte sucht, sucht am falschen Ort.**

## 4. Die Metrik ist blind für genau das, was der Musiker sieht

Und hier wird es konkret — mit einem Beispiel aus diesem Repository.

`mir_eval.chord`, die Referenz-Evaluationsbibliothek des Feldes
([Quelle](https://github.com/mir-evaluation/mir_eval/blob/main/mir_eval/chord.py)),
rechnet Grundtöne über `pitch_class_to_semitone()` in Halbtonzahlen 0–11 um.
**C♯ und D♭ sind dort dasselbe.** Enharmonische Schreibweise ist in der gesamten
MIREX-Metrik unsichtbar.

Das heißt: Die Tonart-Erkennung, die dieses Projekt gerade gebaut hat — die
dafür sorgt, dass in F-Dur ein **B♭** steht und kein A♯ — bekäme in jeder
Standardevaluation **exakt null Punkte**. Sie ist metrisch nicht existent.

Für den Musiker vor dem Bildschirm ist sie das Erste, was er bemerkt.

> **Das ist die These in einem Satz: Was gemessen wird, ist nicht, was gesehen wird.**

Passend dazu der Befund von Koops et al.: Über **Pitch Spelling** sind sich die
menschlichen Annotatoren weitgehend **einig** (es ist also lösbar), während der
größte Streit bei den **Umkehrungen/Slash-Akkorden** herrscht.

---

# Teil II — Was der Code heute tut

## Die Entscheidungsstelle

Es gibt genau **eine** inhaltliche Akkordentscheidung im ganzen Programm, und sie
ist eine lineare Score-Summe über 60 Templates mit anschließendem Argmax —
[chords.py:129-141](../../jampilot/chords.py#L129-L141):

```python
score = float(np.dot(unit, template)) - penalty_rate * extra_notes
if bass is not None:
    score += BASS_BONUS * float(bass[root])
if score > best_score:
    best, best_score = (name, root, suffix), score
```

Drei Terme, drei Konstanten: Cosinus-Ähnlichkeit, eine Komplexitätsstrafe
(`0.08` bzw. `0.02`), ein Bassbonus (`0.12`), eine Schwelle (`0.55`).

Das ist bereits ein winziger Interpreter — der Bassbonus *ist* Kontextwissen
(„der Grundton sollte im Bass liegen"). Aber er ist der einzige, und er sieht
vom 12-dimensionalen Bassvektor genau **eine Zahl**: `bass[root]`.

## Wo die Evidenz vernichtet wird

Der eigentliche Befund der Code-Durchsicht ist nicht, dass Kontext fehlt. Er ist,
dass **die Evidenz zerstört wird, bevor irgendein Kontext sie sehen könnte:**

| Stelle | Was verloren geht |
|---|---|
| [chords.py:129-141](../../jampilot/chords.py#L129-L141) | 60 Scores → **ein** Gewinner. Keine Rangliste, kein Zweitplatzierter, kein Abstand zum Zweiten. |
| [cli.py:307](../../jampilot/cli.py#L307) | `raw = result.name` — `confidence`, `root`, `quality` fallen weg, **bevor** irgendetwas Zeitliches passiert. |
| [chords.py:158](../../jampilot/chords.py#L158) | Der Glätter bekommt ein `ChordResult` und liest davon **nur den String**. Mehrheitsentscheid über drei Namen, ungewichtet. |
| [cli.py:259](../../jampilot/cli.py#L259) | Die Zeitleiste ist `list[tuple[float, str]]` — **(Zeit, String)**. Kein Score, keine Alternativen, kein Rückbezug aufs Chroma. |
| [tonality.py:128](../../jampilot/tonality.py#L128) | `correlate()` liefert eine **Verteilung über 24 Tonarten** — `argmax` in [tonality.py:187](../../jampilot/tonality.py#L187) wirft sie weg. |
| [cli.py:309](../../jampilot/cli.py#L309) | Die Tonart wird gesammelt, aber **nie zurückgeführt**: `match_chord` kennt keine Tonart. Es gibt keinen diatonischen Prior. |

Der letzte Punkt ist der bezeichnendste. Das Programm **kennt die Tonart** und
benutzt sie ausschließlich für die *Schreibweise* — nie für die *Wahl* des
Akkords. In F-Dur ist ein H-Dur unwahrscheinlich; das Programm weiß das und
nutzt es nicht.

## Was es definitiv nicht gibt

Tempo, Beat, Taktposition, Genre, Stimmentrennung, Akkord-Übergangs­wahr­schein­lich­keiten,
Umkehrungen/Slash-Akkorde, sus/dim/aug. Der Akkordvorrat sind
**fünf Typen × 12 Grundtöne = 60 Templates**
([chords.py:10-16](../../jampilot/chords.py#L10-L16)). Und die Zeitleiste wird
zwei Sekunden hinter der hörbaren Position gelöscht
([cli.py:329](../../jampilot/cli.py#L329)) — es gibt **kein Gedächtnis der
Progression**, die man als Evidenz benutzen könnte.

---

# Teil III — Der Hebel, den nur dieses Projekt hat

Hier kommt der Punkt, an dem die Literatur ihr stärkstes Gegenargument verliert.

Pauwels et al. und die gesamte Echtzeit-Literatur argumentieren: Die wirksamsten
Kontexthebel — **bidirektionale** Aufmerksamkeit, Wiederholungsstruktur,
Song-Level-Tonart, nachträgliche Korrektur — sind **kausal nicht verfügbar**,
wenn man in Echtzeit mit niedriger Latenz anzeigen will. Man kann die Zukunft
nicht in die Gegenwart einrechnen.

**Dieses Projekt kauft sich die Zukunft.** Es verzögert die Wiedergabe um
Sekunden (Vorgabe: vier). Damit gibt es zwei getrennte Uhren:

- `loop.captured_frames` — was **schon analysiert** ist
- `loop.audible_position()` — was der Mensch **schon gehört** hat

Alles dazwischen ist **Zukunft für den Musiker und Vergangenheit für den
Interpreter.** In diesem Fenster darf der Interpreter beliebig lange nachdenken,
beliebig weit zurückschauen — und **beliebig oft seine Meinung ändern.**

Und dieses Widerrufsrecht ist **bereits gebaut und getestet**.
[`_commit()`](../../jampilot/cli.py#L433-L437) nimmt Segmente zurück, solange sie
noch niemand gehört hat:

```python
while (timeline
       and timeline[-1][0] > audible_pos          # noch nicht gehoert
       and onset - timeline[-1][0] < MIN_CHORD_SECONDS):
    onset = min(onset, timeline[-1][0])
    timeline.pop()
```

Der Onset wird dabei **vererbt**: *wann* gewechselt wurde, steht fest; *was*
gespielt wird, korrigiert sich. Genau diese Trennung braucht ein Interpreter.

Dazu kommt das **Frame-Chroma-Archiv**
([`FrameHistory.since()`](../../jampilot/chroma.py#L168)): 6,5 Sekunden Chroma im
23-Millisekunden-Raster, in Stream-Koordinaten, **ohne eine einzige zusätzliche
CQT**. Ein Interpreter kann jedes noch nicht hörbare Segment mit beliebigen
Hypothesen neu bewerten, ohne das Audio erneut anzufassen.

Und der Broadcast überträgt **vollständige Snapshots** der Zeitleiste
([web.py:35](../../jampilot/web.py#L35)) — ein Interpreter, der Segmente
umschreibt, braucht **kein neues Protokoll**. Die Korrektur propagiert von selbst
bis ins Handy.

> **Die Verzögerung, die als Bequemlichkeit für den Musiker gedacht war, ist in
> Wahrheit die Architektur, die den Interpreter überhaupt erst möglich macht.**
> Ein Werkzeug mit 100 ms Latenz kann keinen bidirektionalen Kontext nutzen.
> Dieses hier kann es — und es ist das Einzige, das es kann, weil alle anderen
> ihre Latenz minimieren wollen.

Das ist die eine Hälfte der Forschungsfrage dieses Projekts. Nicht „Interpreter
statt Detektor" (das ist bekannt), sondern:

> **Was wird möglich, wenn ein Echtzeit-Interpreter vier Sekunden Zukunft hat und
> seine Anzeige rückwirkend widerrufen darf, bevor sie jemand gehört hat?**

Die andere Hälfte steht im nächsten Teil.

---

# Teil IV — Die Wende, die 2012 nicht möglich war: messen statt modellieren

## Warum es die Grammatik überhaupt gab

Chordifys Harmoniegrammatik (HarmTrace) war **keine Erkenntnis, sondern eine
Kompensation**. 2012 gab es genau *eine* Evidenzquelle: das Chroma des
Gesamtmixes. Ist die Evidenz dünn, muss das Modell dick werden — daher die
kontextfreie Grammatik, daher das Bayes-Netz über Tonart, Metrum und Bass. Man
hat mit **Priors** bezahlt, was man an **Messung** nicht bekommen konnte.

Und genau das ist der Grund für das Plateau aus Teil I: Zwanzig Jahre lang wurde
am *Modell* geschraubt, während die *Evidenz* konstant blieb. Deshalb bringt ein
Transformer gegenüber einem CNN 0,9 Punkte. Die ganze Disziplin optimiert auf
einer Achse, die ausgereizt ist.

Seit ein paar Jahren gibt es eine zweite Achse: **Quellentrennung.** Was man
früher aus dem Mix erschließen musste, kann man heute teilweise *herausziehen*.
Naheliegende Folgerung: Evidenz kaufen statt Priors bauen.

**Diese Folgerung ist zur Hälfte falsch.** Und das genau zu wissen, ist der
wertvollste Teil dieses Dokuments.

## Der Realitätscheck: Trennung verbessert die Akkorderkennung NICHT

Das ist gemessen, und zwar gegen die naheliegende Hoffnung:

> **Mitoma & Furuya, APSIPA ASC 2025** —
> [PDF](http://www.apsipa.org/proceedings/2025/papers/APSIPA2025_P307.pdf)
> HTDemucs-Trennung, einzelne Stems verstärkt, remixt, dann Akkorderkennung
> (BTC). 485 Songs. WCSR, großes Vokabular:

| Variante | triads | root | maj-min | tetrads |
|---|---|---|---|---|
| konventionell (keine Trennung) | 75.52 | 82.51 | 81.59 | 67.44 |
| **Bass** verstärkt | **75.06** | 82.21 | 81.09 | 66.83 |
| Vocals verstärkt | 74.75 | 81.81 | 80.82 | 66.48 |
| bestes Ergebnis (`other` verstärkt) | 75.67 | 82.66 | 81.78 | 67.45 |

**Den Bass zu verstärken machte die Akkorderkennung schlechter.** Der beste Fall
gewinnt **+0,20 Prozentpunkte**. Die einzige Arbeit, die einen isolierten
Bass-Stem gezielt für Umkehrungen nutzt ([arXiv:2509.18700](https://arxiv.org/html/2509.18700v1),
2025), holt +0,75 bis +1,21 pp — und warnt selbst, dass *ausgehaltene Bassnoten*
korrekt erkannte Akkordwechsel zerstören.

> **Wer von der Trennung eine bessere Akkorderkennung erwartet, läuft in dieselbe
> Sackgasse wie die Grammatik — nur teurer.** Es ist wieder dieselbe Achse.

## Und trotzdem ist „messen statt modellieren" richtig — nur für eine andere Frage

Der Denkfehler steckt im Ziel, nicht im Werkzeug. Der gemessene Bass soll den
**Akkord** gar nicht verbessern. Er beantwortet eine Frage, die der Akkordname
überhaupt nicht stellt:

> **„Was spiele *ich* unten?"**

Bei `C/E` steht im Akkord ein C, und der Bassist greift ein E. Der Akkordname
enthält diese Information nicht — und in *jeder* Standardmetrik ist sie
unsichtbar oder umstritten: Koops et al. haben gemessen, dass die
**Umkehrungen** der größte Streitpunkt unter menschlichen Annotatoren sind.

Das ist zum zweiten Mal dieselbe Erkenntnis wie bei der Enharmonik (Teil I.4):

> **Die Metrik misst nicht, was der Musiker sieht.** Erst die Schreibweise, jetzt
> der Bass. Zwei Features, die in jeder Standardevaluation **null Punkte** bringen
> — und die ein Spieler sofort bemerkt.

## Was die Trennung 2026 wirklich hergibt (und was nicht)

Bevor man ein Instrumentenmenü baut, muss man wissen, welche Spuren es überhaupt
gibt. MoisesDB (**Pereira et al., ISMIR 2023**,
[PDF](https://archives.ismir.net/ismir2023/paper/000073.pdf), Tab. 3,
`htdemucs_6s`, globales SDR):

| Stem | SDR | ideale Maske (Oracle MWF) |
|---|---|---|
| **Bass** | **11.93** | 8.24 |
| Drums | 11.02 | 9.23 |
| Vocals | 9.55 | 9.81 |
| **Gitarre** | **3.07** | 5.41 |
| **Piano/Keyboard** | **1.60** | 4.97 |

**Zwei Dinge stehen da.**

**Erstens: Gitarre und Keyboard sind nicht lieferbar.** Sie liegen ~9 dB unter
Bass — und, entscheidend, **unter dem, was eine ideale Maske könnte**. Das Modell
schöpft dort nicht einmal das theoretisch Machbare aus. Das Demucs-README sagt es
selbst: *„a lot of bleeding and artifacts for the `piano` source… the `piano`
source is not working great at the moment"*
([README](https://github.com/facebookresearch/demucs)). Ein Menüpunkt „Keyboard",
der auf Trennung baut, verspricht etwas, das es nicht gibt.

**Zweitens — und das ist die Pointe: Dass der Bass so gut geht, ist der Grund,
warum man dort keine Trennung braucht.** HTDemucs schlägt beim Bass die *ideale
Maske* (11,93 gegen 8,24). Das ist kein Wunder, das ist ein Geständnis: **Bass ist
spektral ohnehin fast linear separierbar.** Er wohnt unten fast allein; der
einzige ernsthafte Mitbewohner ist die Bassdrum — breitbandig und transient,
also genau das, was die **HPSS-Stufe schon heute entfernt**
([chroma.py:125](../../jampilot/chroma.py#L125)).

## Das CPU-Budget entscheidet die Frage ohnehin

HTDemucs ist **nicht kausal** und braucht immer einen **7,8-Sekunden-Forward-Pass**
(so groß ist das Attention-Fenster).

| | Realtime-Faktor | Kosten pro Durchlauf (7,8 s Segment) |
|---|---|---|
| CPU (PyTorch / ONNX) | 0,35 – 0,43 | **~3 s** |
| GPU | ~0,03 | ~0,23 s |

Der Analysetakt dieses Programms ist **250 ms**
([cli.py:27](../../jampilot/cli.py#L27)). Auf der CPU liegt HTDemucs damit
**Faktor 12 über dem Budget**; auf der GPU träfe es das Limit exakt — mit null
Reserve für die Akkorderkennung selbst.

*Anmerkung zum Vorlauf:* Die 4 Sekunden Verzögerung lösen das **Kausalitäts**-,
nicht das **Kosten**problem. Ein nicht-kausales 7,8-s-Fenster über bereits
vergangenes Audio zu legen, ist hier erlaubt (siehe Teil III) — es ist nur zu
teuer. Explizite Echtzeit-Trenner gibt es (HS-TasNet, ICASSP 2024,
[arXiv:2402.17701](https://arxiv.org/abs/2402.17701); RT-STT, 2025,
[arXiv:2511.13146](https://arxiv.org/abs/2511.13146) — 383 K Parameter, ~1 ms
Inferenz), sie kosten aber **3–5 dB SDR**.

## Der billige Weg zum Bass: der klassische, und er ist Echtzeit seit 2004

> **Goto, PreFEst** (Speech Communication, 2004) —
> [Projektseite](https://staff.aist.go.jp/m.goto/PROJ/f0.html)
> Schätzt Melodie **und Basslinie** direkt aus CD-Aufnahmen, **in Echtzeit**,
> ohne jede Quellentrennung — über den vorherrschenden F0 in einem *bewusst
> eingeschränkten Frequenzband*.

Und die *aktuelle* Bass-Transkriptionsforschung (**Abeßer et al.**,
[AudioLabs](https://www.audiolabs-erlangen.de/resources/MIR/2017-AES-WalkingBassTranscription))
mappt ebenfalls **Mix-Spektrogramm → Bass-Salienz** — ohne generischen Separator.

Einen publizierten Beleg, dass „Trennung + Pitch-Tracking" den Weg „Bandpass +
Pitch-Tracking" schlägt, gibt es **nicht**. (Die eine Pipeline, die es so macht —
Araz, ISMIR 2021 LBD — evaluiert rein qualitativ, „by listening".)

**Zwei Umsetzungsdetails, die man sonst teuer lernt** (beide aus Araz):

- **pYIN, nicht CREPE.** CREPE hat zu wenig Sub-Bass im Trainingsset und schneidet
  dort messbar schlechter ab.
- **Waveform-/autokorrelationsbasiert, nicht spektrogrammbasiert.** Im Sub-Bass
  liegen benachbarte Halbtöne ~1,95 Hz auseinander — dafür reicht die
  FFT-Auflösung nicht.

## Die Konsequenz: der Instrumentenwähler wählt die ANZEIGE, nicht den Analysepfad

Damit fällt die ganze Idee auf die Füße — und wird dabei viel billiger, als sie
klang. Für **drei von vier** Instrumenten braucht es überhaupt keine Trennung:

| Instrument | Was der Spieler braucht | Woher | Trennung? |
|---|---|---|---|
| **Bass** | die *tatsächliche* Bassnote, Slash-Akkorde | Bandpass ~40–400 Hz + pYIN; die Bass-CQT läuft **heute schon** ([chroma.py:128](../../jampilot/chroma.py#L128)) | **nein** |
| **Gitarre** | Akkord + Griff/Capo | ist schon da — nur anders **gerendert** | **nein** |
| **Keyboard** | Akkord mit Optionstönen | ist schon da — nur anders **gerendert** | **nein** (ginge auch gar nicht, s. o.) |
| **Gesang** | Melodieton | Predominant-F0 (PreFEst-Weg) | nein |

Die **Tonart** wird weiterhin auf dem **Gesamtmix** bestimmt, und das ist keine
Bequemlichkeit: Eine Basslinie besteht überwiegend aus Grundtönen und Quinten.
Ein Tonart-Histogramm daraus wäre systematisch verzerrt — es verlöre gerade die
**Terzen**, die Dur von Moll unterscheiden. Die Tonart braucht die volle Harmonie,
die Bassnote braucht das Tiefband. Zwei Fragen, zwei Signale.

Eine echte Trennung lohnt sich erst für ein **anderes Feature**: das verzögerte
**Playback selbst** zu verändern (ein Instrument im Mix hervorheben oder
ausblenden, karaoke-artig). Dafür ist der 4-Sekunden-Puffer genau richtig — und
dafür braucht es eine GPU.

## Damit lautet die zweite Hälfte der Forschungsfrage

> **Wie viel nützlicher wird eine Akkordanzeige, wenn sie nicht mehr fragt „welcher
> Akkord ist wahr", sondern „was spielt *dieses* Instrument gerade" — und wie
> billig ist das wirklich, wenn man nur misst, was ohnehin schon berechnet wird?**

---

# Teil V — Was ein Interpreter konkret wäre

## Schritt 1: Evidenz statt Strings

Der Umbau, ohne den nichts anderes geht. Heute:

```
Chroma → match_chord → "Am" → Smoother("Am","Am","C") → timeline: (12.4, "Am")
```

Ab dem zweiten Pfeil ist alles ein String. Stattdessen:

```
Chroma ─┐
Bass   ─┼→ Kandidaten (Top-k mit Scores) ─┐
Tonart ─┘                                  ├→ Interpreter → Segment mit
Vorgeschichte ─────────────────────────────┘                Alternativen
```

Konkret: `match_chord` gibt eine **Rangliste** zurück statt eines Gewinners
(`ChordResult` trägt `root`, `quality`, `confidence` bereits — sie werden nur von
niemandem gelesen). Die Zeitleiste trägt Segmente mit **Alternativen und Scores**
statt `(float, str)`. Damit wird eine spätere Revision überhaupt erst
*informiert* möglich statt bloß möglich.

## Schritt 2: Die Kontextquellen — nach Kosten sortiert

| Quelle | Aufwand | Erwarteter Nutzen | Begründung |
|---|---|---|---|
| **Gemessene Bassnote** (Tiefband + pYIN) | gering — die Bass-CQT läuft schon, ihre Frames werden **weggeworfen** ([chroma.py:129](../../jampilot/chroma.py#L129)) | **hoch — aber für die ANZEIGE, nicht für die Trefferquote** | Slash-Akkorde und Umkehrungen: der größte Streitpunkt unter Annotatoren (Koops) und für einen Bassisten *die* Frage. Erwartet **keinen** Metrik-Gewinn (Teil IV). |
| **Tonart als diatonischer Prior** | sehr gering — [`correlate()`](../../jampilot/tonality.py#L128) liefert die Verteilung schon | mittel-hoch | Kostet einen Term in der Score-Summe. In F-Dur ist H-Dur unwahrscheinlich. Die Information liegt ungenutzt herum. |
| **Akkordfolge als Sprachmodell** | mittel (Zeitleiste muss Gedächtnis bekommen) | gering-mittel | Literatur: hilft, aber „effects are small". Nicht überschätzen. |
| **Beat / Taktposition** | hoch (neue Analyse) | mittel | Mauch & Dixon: Bass + Metrum helfen vor allem, die richtige **Granularität** zu treffen — das ist eine *Anzeige*-Eigenschaft. |
| **Genre** | hoch (Klassifikator) | offen | Billiger Zwischenschritt: **den Nutzer fragen.** Ein Schalter „Pop / Blues / Jazz" ist eine Zeile UI und ersetzt einen Klassifikator. |
| **Quellentrennung (Demucs o. ä.)** | **sehr hoch** — 12× über dem CPU-Budget (Teil IV) | **für Akkorde: nachweislich ~null** (+0,20 pp, APSIPA 2025) | Lohnt sich nur, wenn man das **Playback** verändern will, nicht die Anzeige. Braucht eine GPU. |

**Die Reihenfolge ist die Botschaft:** Die zwei billigsten Hebel (gemessene
Bassnote, Tonart-Prior) nutzen Informationen, die **bereits berechnet und dann
verworfen werden**. Sie kosten fast nichts und sind noch nicht angefasst. Der
teuerste Hebel (Trennung) steht unten, weil er für dieses Ziel **gemessen nichts
bringt** — nicht, weil er zu aufwendig wäre.

## Schritt 3: Der Entscheider

Erst dann stellt sich die Frage, *wie* entschieden wird — und die Antwort ist
vermutlich **nicht** „ein neuronales Netz", sondern eine gewichtete Kombination
mit **explizit benannten, einzeln abschaltbaren Termen**. Denn:

- Die Terme müssen einzeln messbar sein, sonst lernt man nichts (siehe Teil VI).
- Die Literatur zeigt, dass die großen Modelle hier **kaum etwas gewinnen**.
- Ein erklärbarer Interpreter kann dem Musiker *sagen*, warum er sich umentschieden
  hat („Bass wechselt nach A, Tonart F-Dur → Am statt C").

---

# Teil VI — Forschungsfragen, die sich beantworten lassen

Damit das ein Forschungsprojekt wird und keine Meinung, braucht es Fragen mit
falsifizierbaren Antworten. Vorschläge, nach Aussagekraft geordnet:

1. **Wie oft revidiert ein bidirektionaler Interpreter eine Entscheidung, bevor
   sie hörbar wird — und wie oft macht er sie dadurch besser statt schlechter?**
   Messbar mit dem vorhandenen Debug-Trace
   ([`JAMPILOT_DEBUG`](../../jampilot/cli.py#L268)): Jede Revision jenseits von
   `audible_pos` protokollieren, gegen eine Referenzannotation halten. **Das ist
   die Kernfrage dieses Projekts und meines Wissens unbeantwortet.**

2. **Schlägt der billige Weg zur Bassnote (Bandpass + pYIN) den teuren
   (Demucs-Bass-Stem + pYIN)?** Diesen A/B-Vergleich hat, soweit auffindbar,
   **niemand publiziert** — die eine Arbeit, die den teuren Weg geht (Araz, ISMIR
   2021 LBD), evaluiert rein qualitativ, „by listening". Die Gegenprobe ist
   billig: beide Wege auf denselben Ausschnitten, Notenraten vergleichen. Ein
   negatives Ergebnis („der Bandpass reicht") ist genauso wertvoll — und würde
   ein 40-Millionen-Parameter-Modell aus einem Echtzeitwerkzeug fernhalten.

3. **Wie groß ist der Gewinn eines Tonart-Priors — und verschwindet er wieder,
   wenn die Tonart falsch erkannt ist?** (Fehlerfortpflanzung, siehe Teil VII.)
   Direkt messbar: ein Term an-/abschalten, Selbsttest und Referenzkorpus laufen
   lassen.

4. **Wählen Gitarristen und Pianisten wirklich andere Labels — und kann eine
   Umschaltung „Anzeige für Bass / Gitarre / Klavier" die wahrgenommene Qualität
   heben, ohne dass sich eine einzige Standardmetrik bewegt?** Der Befund von
   Koops et al. legt es nahe; der CASD-Datensatz (vier Annotatoren, offen) erlaubt
   es zu testen. **Das ist die Frage, an der sich entscheidet, ob dieses Projekt
   ein Produkt oder eine Fußnote wird.**

5. **Ab welcher Verzögerung bringt Lookahead nichts mehr?** Es gibt eine
   Sättigung; wo sie liegt, sagt einem niemand. `--delay` ist bereits ein
   Parameter von 0,5 bis 30 Sekunden — das Experiment ist ein Sweep.

---

# Teil VII — Was dagegen spricht. Ehrlich.

## 1. Das ist alles schon gebaut. Und es hieß, wie wir hießen.

Die schmerzhafteste Erkenntnis der Recherche:

> **chordify.net** ist ein etabliertes kommerzielles Produkt, gegründet 2013 aus
> der MIR-Forschung der **Universität Utrecht** (u. a. W. Bas de Haas), mit
> Millionen Nutzern. Es hat 2015 bereits 250.000 registrierte Nutzer und 3 Mio.
> analysierte Songs gemeldet ([ISMIR 2015
> LBD](https://ismir2015.ismir.net/LBD/LBD42.pdf)).

Und seine Engine ist **exakt die These dieses Dokuments**: **HarmTrace** (de Haas
et al., ISMIR 2012, „Improving Audio Chord Transcription by Exploiting Harmonic and
Metric Knowledge") verwendet eine **kontextfreie Grammatik der tonalen Harmonie** —
bei unsicherer Audio-Evidenz entscheidet **das Harmoniemodell**, nicht das Signal.
Genau das, was hier „harmonischer Interpreter" heißt.

Dieselbe Gruppe (de Haas, Koops, Bransen, Volk) hat außerdem
**die Subjektivitätsforschung** *und* die **Label-Personalisierung** publiziert
([arXiv:1706.09552](https://arxiv.org/abs/1706.09552) — ein Modell, das pro
Annotator personalisierte Labels ableitet). Und Chordify hat eine
[Live-Akkorderkennung über Mikrofon](https://chordify.net/toolkit/live-chord-detection).

**Drei Konsequenzen:**

- **Der Name musste weg** — und ist weg. Er kollidierte nicht nur
  markenrechtlich, sondern ausgerechnet mit dem Marktführer für exakt diese Idee;
  das war kein Namensproblem, das war ein Positionierungsproblem. Das Projekt
  heißt seit dieser Recherche **JamPilot**: Der Lotse sitzt vorne und sagt an,
  was kommt — genau das tut der Vorlauf.
- **„Wir interpretieren statt zu detektieren" ist kein Alleinstellungsmerkmal.**
  Die Differenzierung muss konkreter sein. Die Kandidaten stehen in Teil III und
  IV: **der Vorlauf** und **die instrumentenspezifische Anzeige**. Chordify
  analysiert Dateien offline (da hat es alle Zeit der Welt) oder live mit
  minimaler Latenz (da hat es keine Zukunft). Der Mittelweg — **Echtzeit mit
  absichtlich gekaufter Zukunft und Widerrufsrecht** — ist der Punkt, an dem
  dieses Projekt allein steht.
- **Die Grammatik selbst muss man aber nicht nachbauen.** Sie war die Antwort auf
  eine Evidenzarmut, die 2012 unvermeidlich war (Teil IV). Wer sie heute
  nachbaut, erbt ihre Kosten, ohne ihren Grund zu erben. Der Ausweg ist **nicht**,
  sie durch Quellentrennung zu ersetzen — die bringt für Akkorde gemessen ~nichts
  —, sondern **die Frage zu wechseln**: nicht denselben Akkord genauer, sondern
  einen *anderen, spielerspezifischen* Inhalt anzeigen.

## 2. Die Literatur ist skeptisch, dass Kontext viel bringt

Das ist unbequem, aber es steht da:

- Höhere Markov-Ordnungen: „small overall improvement" (Pauwels et al.).
- Frame-Level-Sprachmodelle: **„futile"** (Korzeniowski & Widmer).
- Tonart-relative Akkord-Repräsentationen: „it has **not been proven** that [they]
  lead to improvements in actual chord recognition" (Pauwels et al.).
- Der bidirektionale Transformer schlägt das CNN **innerhalb der Standardabweichung**.

**Gegenmittel:** Nicht die Trefferquote als Ziel nehmen. Die Literatur sagt
nirgends, dass Kontext für *Granularität, Stabilität, Schreibweise und
Konsistenz der Anzeige* nichts bringt — sie hat es nur nie gemessen, weil die
Metrik es nicht sieht.

## 3. Fehlerfortpflanzung

Ein Interpreter, der auf Tonart und Beat aufsetzt, **erbt deren Fehler**. Eine
falsch erkannte Tonart, die als Prior in die Akkordwahl eingeht, macht die
Erkennung nicht robuster, sondern **selbstbestätigend falsch** — sie zieht die
Akkorde in die falsche Tonart und die Tonart bestätigt sich aus den falschen
Akkorden. Pauwels et al. warnen ausdrücklich davor.

**Gegenmittel:** Der Prior muss **schwach** sein und die Konfidenz der Tonart
berücksichtigen. Die Architektur hat dafür bereits die richtige Haltung: Die
Tonart meldet sich die ersten zwölf Sekunden **gar nicht**
([tonality.py:34](../../jampilot/tonality.py#L34)), statt zu raten. Diese
Vorsicht muss der Interpreter erben.

## 4. Man wird es mit Standardmetriken nicht beweisen können

Jede etablierte Metrik wird die Verbesserung entweder **ignorieren** (Enharmonik —
`mir_eval` sieht sie nicht) oder **bestrafen** (eine Glättung, die einen seltenen,
aber laut Annotation korrekten Akkord wegbügelt, kostet WCSR). Pauwels et al.
schreiben, die einzig saubere Bewertung — Experten fragen, ob eine Transkription
eine *gute Analyse* ist — sei „impossible to test [for] multiple
parameterisations", also nicht skalierbar.

**Das ist zugleich das Risiko und die Chance.** Wenn die Standardmetrik das Ziel
nicht messen kann, muss man die Bewertung selbst bauen — und *das* wäre ein
eigenständiger Forschungsbeitrag: **eine Evaluation, die misst, was der Musiker
sieht.** Ansatzpunkt: nicht „stimmt das Label", sondern „wie oft muss der Spieler
stolpern" — Zahl der Anzeigewechsel, die er *nicht* mitspielen konnte, Zahl der
Revisionen, die ihn erreicht haben statt vor der Hörschwelle abgefangen zu werden.

---

# Teil VIII — Wenn man es macht: die Reihenfolge

Ohne Zeitangaben, nach Erkenntnisgewinn pro Aufwand. Der Bass steht jetzt vorn,
weil er das **billigste sichtbare Ergebnis** ist — und weil er die These des
Dokuments am schnellsten testet.

1. **Die Bassnote messen, statt sie zu erraten.** Heute wird eine vollständige
   Bass-CQT berechnet ([chroma.py:128](../../jampilot/chroma.py#L128)) und auf
   *ein Skalar* eingedampft: `BASS_BONUS * bass[root]`
   ([chords.py:134](../../jampilot/chords.py#L134)). Die Frames werden gar nicht
   erst aufgehoben. Stattdessen: Tiefband + **pYIN** (nicht CREPE, Teil IV) →
   Bassnote pro Frame, zeitlich geglättet. Kostet Millisekunden, kein Modell,
   keine GPU.

2. **Instrumentenauswahl ins Zahnrad** — der Dialog steht schon
   ([web.py](../../jampilot/web.py)). Modus **Bass**: Bassnote groß, Akkord als
   Kontext, `C/E` sichtbar. Modi Gitarre/Keyboard: **derselbe** Analysepfad,
   andere Darstellung (Griffe, Optionstöne). **Kein Menüpunkt, der Quellentrennung
   bräuchte** — Gitarren- und Piano-Stems liefern heute nicht (Teil IV).

3. **Evidenz retten.** `match_chord` gibt eine Rangliste; die Zeitleiste trägt
   Alternativen und Scores. *Ohne diesen Schritt ist kein Interpreter möglich.*
   Klein und rein additiv.

4. **Tonart als schwachen Prior einspeisen.** Der billigste Kontexthebel — die
   Verteilung existiert bereits ([tonality.py:128](../../jampilot/tonality.py#L128))
   und wird weggeworfen. Sofort messbar: an/aus, Selbsttest.

5. **Revisionen messen.** Den Debug-Trace um Revisionsereignisse erweitern: Wie
   oft ändert der Vorlauf die Meinung, bevor es jemand hört — und wird es dadurch
   besser? **Das ist die Kernfrage aus Teil III, und sie ist mit dem vorhandenen
   Code fast beantwortbar.**

6. **Den Nutzer nach dem Genre fragen**, statt es zu erraten. Ein Schalter ist
   eine Zeile UI; ein Genre-Klassifikator ist ein Projekt.

7. Erst danach: Beat, Taktposition, gelerntes Modell.

**Nicht auf dieser Liste: Quellentrennung.** Nicht aus Bequemlichkeit, sondern
weil sie für dieses Ziel gemessen nichts bringt (+0,20 pp) und das CPU-Budget um
Faktor 12 sprengt. Sie kommt zurück auf die Liste, sobald das **Playback** selbst
verändert werden soll — das ist ein anderes Produkt, und es braucht eine GPU.

---

# Fazit

Die These stimmt, aber sie ist nicht der Beitrag — sie ist der Stand der
Forschung, den das Feld selbst formuliert (Humphrey & Bello) und eine Firma seit
2012 verkauft (Chordify/HarmTrace). Wer sie bloß wiederholt, kommt zehn Jahre zu
spät.

Und die naheliegende Modernisierung — „2012 brauchte man eine Grammatik, heute
trennt man einfach die Spuren" — ist **zur Hälfte falsch**. Quellentrennung
verbessert die Akkorderkennung **gemessen nicht** (+0,20 pp; den Bass zu
verstärken macht sie sogar schlechter), die Gitarren- und Piano-Stems existieren
praktisch nicht, und HTDemucs sprengt das Echtzeitbudget um Faktor 12. Wer
Trennung benutzt, um denselben Akkord genauer zu treffen, hat nur die Sackgasse
gewechselt.

**Beide Sackgassen haben dieselbe Ursache: Sie optimieren die Antwort auf eine
Frage, die der Musiker nie gestellt hat.**

Der Beitrag liegt woanders — und er liegt schon im Repository:

- Dieses Programm **sieht die Zukunft**, bevor der Mensch sie hört, und darf seine
  Anzeige **widerrufen**, solange sie noch niemand gesehen hat. Beides ist gebaut,
  getestet — und wird für nichts benutzt außer einem Laufband. Kein anderes
  Echtzeitwerkzeug hat diesen Spielraum, weil alle anderen ihre Latenz minimieren.
- Und es **rechnet den Bass bereits aus** — um ihn dann auf eine einzige Zahl
  einzudampfen. Dabei ist die Bassnote genau das, was der Akkordname nicht
  enthält, was unter Menschen am umstrittensten ist, und was ein Bassist als
  Erstes wissen will.

Beides ist in derselben Metrik **null Punkte wert**. Und beides sieht ein Spieler
sofort.

Die Frage ist also nicht mehr „Interpretation statt Detektion?" — die ist
beantwortet. Sie lautet:

> **Wie viel nützlicher wird eine Anzeige, die (a) vier Sekunden Zukunft hat und
> sich vor der Hörschwelle korrigieren darf und (b) nicht fragt „welcher Akkord ist
> wahr", sondern „was spielt *dieses* Instrument gerade"? Und was misst man, um das
> zu zeigen, wenn die etablierte Metrik beides per Konstruktion nicht sehen kann?**

Das ist ein Forschungsprojekt. Und es fängt mit zwei kleinen, additiven Änderungen
an: **hör auf, die Evidenz wegzuwerfen — und miss den Bass, statt ihn zu raten.**

---

## Quellen

**Kritik & Grundlagen**
- Humphrey & Bello (2015), *Four Timely Insights on Automatic Chord Estimation*, ISMIR — [PDF](https://archives.ismir.net/ismir2015/paper/000294.pdf)
- Pauwels, O'Hanlon, Gómez, Sandler (2019), *20 Years of Automatic Chord Recognition from Audio*, ISMIR — [PDF](https://archives.ismir.net/ismir2019/paper/000004.pdf)
- Koops et al. (2019), *Annotator subjectivity in harmony annotations of popular music*, JNMR 48(3) — [DOI](https://www.tandfonline.com/doi/full/10.1080/09298215.2019.1613436) · [CASD](https://github.com/chordify/CASD)
- Ni, McVicar, Santos-Rodríguez, De Bie (2013), *Understanding Effects of Subjectivity in Measuring Chord Estimation Accuracy*, IEEE/ACM TASLP 21(12) *(Metadaten verifiziert, DOI nicht abgerufen)*

**Kontextmodelle**
- Mauch & Dixon (2010), *Simultaneous Estimation of Chords and Musical Context from Audio*, IEEE TASLP 18(6)
- Papadopoulos & Peeters, *Joint Estimation of Chords and Downbeats from an Audio Signal* — [HAL](https://hal.science/hal-00525172v2)
- de Haas, Magalhães, Wiering (2012), *Improving Audio Chord Transcription by Exploiting Harmonic and Metric Knowledge* (HarmTrace), ISMIR
- McFee & Bello (2017), *Structured Training for Large-Vocabulary Chord Recognition*, ISMIR — [PDF](https://brianmcfee.net/papers/ismir2017_chord.pdf)
- Park et al. (2019), *A Bi-directional Transformer for Musical Chord Recognition*, ISMIR — [PDF](https://archives.ismir.net/ismir2019/paper/000075.pdf) · [Code](https://github.com/jayg996/BTC-ISMIR19)
- Korzeniowski & Widmer, *On the Futility of Learning Complex Frame-Level Language Models* — [arXiv:1702.00178](https://arxiv.org/abs/1702.00178); *Higher-Order Harmonic Language Modelling* — [arXiv:1808.05341](https://arxiv.org/abs/1808.05341)

**Anzeige, Personalisierung, Vokabular**
- Koops, de Haas, Bransen, Volk (2017), *Chord Label Personalization through Deep Learning* — [arXiv:1706.09552](https://arxiv.org/abs/1706.09552)
- Carsault, Nika, Esling (2018), *Using Musical Relationships Between Chord Labels in Automatic Chord Extraction Tasks*, ISMIR — [PDF](https://archives.ismir.net/ismir2018/paper/000231.pdf)
- Koops et al. (2023), *SERENADE: Human-in-the-loop Automatic Chord Estimation* — [arXiv:2310.11165](https://arxiv.org/abs/2310.11165)

**Schreibweise & Tonart**
- Meredith (2006), *The ps13 Pitch Spelling Algorithm*, JNMR 35(2) — [PDF](http://www.titanmusic.com/papers/public/ps13-escom-paper.pdf)
- Temperley (1999), *What's Key for Key? The Krumhansl-Schmuckler Key-Finding Algorithm Reconsidered*, Music Perception
- Temperley (2002), *A Bayesian Approach to Key-Finding*
- Bouquillard & Jacquemard (2024), *Engraving Oriented Joint Estimation of Pitch Spelling and Local and Global Keys* — [arXiv:2402.10247](https://arxiv.org/abs/2402.10247)
- `mir_eval.chord` — [Quelltext](https://github.com/mir-evaluation/mir_eval/blob/main/mir_eval/chord.py) (C♯ ≡ D♭)

**Quellentrennung & Bass (Teil IV)**
- Pereira et al. (2023), *MoisesDB: A Dataset for Source Separation Beyond 4-Stems*, ISMIR — [PDF](https://archives.ismir.net/ismir2023/paper/000073.pdf) *(Stem-SDR inkl. Gitarre/Piano)*
- Rouard, Massa, Défossez (2023), *Hybrid Transformers for Music Source Separation* (HTDemucs), ICASSP — [arXiv:2211.08553](https://arxiv.org/abs/2211.08553) · [Code/README](https://github.com/facebookresearch/demucs)
- Lu et al. (2023), *Music Source Separation with Band-Split RoPE Transformer* (BS-RoFormer) — [arXiv:2309.02612](https://arxiv.org/abs/2309.02612); Mel-Band RoFormer — [arXiv:2310.01809](https://arxiv.org/abs/2310.01809)
- **Mitoma & Furuya (2025)**, APSIPA ASC — [PDF](http://www.apsipa.org/proceedings/2025/papers/APSIPA2025_P307.pdf) *(Trennung als Vorstufe zur Akkorderkennung: +0,20 pp; Bass-Verstärkung verschlechtert)*
- *Enhancing Automatic Chord Recognition through LLM Chain-of-Thought Reasoning* (2025) — [arXiv:2509.18700](https://arxiv.org/html/2509.18700v1) *(Bass-Stem für Umkehrungen: +0,75…+1,21 pp)*
- Goto (2004), *A real-time music-scene-description system: predominant-F0 estimation for detecting melody and bass lines* (PreFEst), Speech Communication — [Projekt](https://staff.aist.go.jp/m.goto/PROJ/f0.html)
- Abeßer et al., *Walking Bass Transcription* — [AudioLabs](https://www.audiolabs-erlangen.de/resources/MIR/2017-AES-WalkingBassTranscription) · [Code](https://github.com/jakobabesser/walking_bass_transcription_dnn)
- Araz (2021), *Bass line transcription* (Demucs + pYIN; pYIN schlägt CREPE im Sub-Bass), ISMIR LBD — [PDF](https://archives.ismir.net/ismir2021/latebreaking/000016.pdf)
- Low-Latency-Trennung: HS-TasNet (ICASSP 2024) — [arXiv:2402.17701](https://arxiv.org/abs/2402.17701) · RT-STT (2025) — [arXiv:2511.13146](https://arxiv.org/abs/2511.13146)

**Korpora & Evaluation**
- Isophonics/Beatles — [isophonics.net](https://isophonics.net/content/reference-annotations-beatles)
- McGill Billboard (Burgoyne et al., ISMIR 2011) — [ddmal.ca](https://ddmal.ca/research/The_McGill_Billboard_Project_(Chord_Analysis_Dataset)/)
- JAAH (Eremenko et al., ISMIR 2018) — [PDF](https://archives.ismir.net/ismir2018/paper/000206.pdf) · [Zenodo](https://zenodo.org/records/1290737)
- MIREX Audio Chord Estimation — [Wiki](https://www.music-ir.org/mirex/wiki/2019:Audio_Chord_Estimation)
- ChordFormer (2025) — [arXiv:2502.11840](https://arxiv.org/html/2502.11840)

**Produkte**
- Chordify — [chordify.net](https://chordify.net/pages/about/) · [Live Chord Detection](https://chordify.net/toolkit/live-chord-detection) · Magalhães (2015), *Chordify: Three Years After the Launch*, ISMIR LBD — [PDF](https://ismir2015.ismir.net/LBD/LBD42.pdf)
- Chord ai — [chordai.net](https://chordai.net/)
- Moises — [moises.ai](https://moises.ai/features/chord-finder/)

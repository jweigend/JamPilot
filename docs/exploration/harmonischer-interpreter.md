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

Das ist die eigentliche Forschungsfrage dieses Projekts. Nicht „Interpreter statt
Detektor" (das ist bekannt), sondern:

> **Was wird möglich, wenn ein Echtzeit-Interpreter vier Sekunden Zukunft hat und
> seine Anzeige rückwirkend widerrufen darf, bevor sie jemand gehört hat?**

---

# Teil IV — Was ein Interpreter konkret wäre

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
| **Tonart als diatonischer Prior** | sehr gering — [`correlate()`](../../jampilot/tonality.py#L128) liefert die Verteilung schon | **hoch** | Kostet einen Term in der Score-Summe. In F-Dur ist H-Dur unwahrscheinlich. Die Information liegt ungenutzt herum. |
| **Bassverlauf statt `bass[root]`** | gering — die Bass-Frames werden heute berechnet und **weggeworfen** ([chroma.py:129](../../jampilot/chroma.py#L129)) | mittel-hoch | Grundlage für Umkehrungen/Slash-Akkorde — laut Koops der **größte Streitpunkt** unter Menschen, also der größte Interpretationsspielraum. |
| **Akkordfolge als Sprachmodell** | mittel (Zeitleiste muss Gedächtnis bekommen) | mittel | Literatur: hilft, aber „effects are small". Nicht überschätzen. |
| **Beat / Taktposition** | hoch (neue Analyse) | mittel | Mauch & Dixon: Bass + Metrum helfen vor allem, die richtige **Granularität** zu treffen — das ist eine *Anzeige*-Eigenschaft. |
| **Genre** | hoch (Klassifikator oder Nutzerangabe) | offen | Billiger Zwischenschritt: **den Nutzer fragen.** Ein Schalter „Pop / Blues / Jazz" ist eine Zeile UI und ersetzt einen Klassifikator. |
| **Stimmentrennung (Demucs o.ä.)** | sehr hoch, Echtzeit fraglich | hoch, aber teuer | Was Moises tut. Vermutlich außerhalb des Echtzeitbudgets. |

**Die Reihenfolge ist die Botschaft:** Die zwei billigsten Hebel (Tonart-Prior,
Bassverlauf) nutzen Informationen, die **bereits berechnet und dann verworfen
werden**. Sie kosten fast nichts und sind noch nicht angefasst.

## Schritt 3: Der Entscheider

Erst dann stellt sich die Frage, *wie* entschieden wird — und die Antwort ist
vermutlich **nicht** „ein neuronales Netz", sondern eine gewichtete Kombination
mit **explizit benannten, einzeln abschaltbaren Termen**. Denn:

- Die Terme müssen einzeln messbar sein, sonst lernt man nichts (siehe Teil V).
- Die Literatur zeigt, dass die großen Modelle hier **kaum etwas gewinnen**.
- Ein erklärbarer Interpreter kann dem Musiker *sagen*, warum er sich umentschieden
  hat („Bass wechselt nach A, Tonart F-Dur → Am statt C").

---

# Teil V — Forschungsfragen, die sich beantworten lassen

Damit das ein Forschungsprojekt wird und keine Meinung, braucht es Fragen mit
falsifizierbaren Antworten. Vorschläge, nach Aussagekraft geordnet:

1. **Wie oft revidiert ein bidirektionaler Interpreter eine Entscheidung, bevor
   sie hörbar wird — und wie oft macht er sie dadurch besser statt schlechter?**
   Messbar mit dem vorhandenen Debug-Trace
   ([`JAMPILOT_DEBUG`](../../jampilot/cli.py#L268)): Jede Revision jenseits von
   `audible_pos` protokollieren, gegen eine Referenzannotation halten. **Das ist
   die Kernfrage dieses Projekts und meines Wissens unbeantwortet.**

2. **Wie groß ist der Gewinn eines Tonart-Priors — und verschwindet er wieder,
   wenn die Tonart falsch erkannt ist?** (Fehlerfortpflanzung, siehe Teil VI.)
   Direkt messbar: ein Term an-/abschalten, Selbsttest und Referenzkorpus laufen
   lassen.

3. **Wählen Gitarristen und Pianisten wirklich andere Labels — und kann eine
   Umschaltung „Anzeige für Gitarre / Klavier" die wahrgenommene Qualität heben,
   ohne dass sich eine einzige Standardmetrik bewegt?** Der Befund von Koops et
   al. legt es nahe; der CASD-Datensatz (vier Annotatoren, offen) erlaubt es zu
   testen.

4. **Ab welcher Verzögerung bringt Lookahead nichts mehr?** Es gibt eine
   Sättigung; wo sie liegt, sagt einem niemand. `--delay` ist bereits ein
   Parameter von 0,5 bis 30 Sekunden — das Experiment ist ein Sweep.

---

# Teil VI — Was dagegen spricht. Ehrlich.

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

**Zwei Konsequenzen:**

- **Der Name musste weg** — und ist weg. Er kollidierte nicht nur
  markenrechtlich, sondern ausgerechnet mit dem Marktführer für exakt diese Idee;
  das war kein Namensproblem, das war ein Positionierungsproblem. Das Projekt
  heißt seit dieser Recherche **JamPilot**: Der Lotse sitzt vorne und sagt an,
  was kommt — genau das tut der Vorlauf.
- **„Wir interpretieren statt zu detektieren" ist kein Alleinstellungsmerkmal.**
  Die Differenzierung muss konkreter sein. Der Kandidat dafür steht in Teil III:
  **der Vorlauf.** Chordify analysiert Dateien offline (da hat es alle Zeit der
  Welt) oder live mit minimaler Latenz (da hat es keine Zukunft). Der Mittelweg —
  **Echtzeit mit absichtlich gekaufter Zukunft und Widerrufsrecht** — ist der
  Punkt, an dem dieses Projekt allein steht.

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

# Teil VII — Wenn man es macht: die Reihenfolge

Ohne Zeitangaben, nach Erkenntnisgewinn pro Aufwand:

1. **Evidenz retten.** `match_chord` gibt eine Rangliste; die Zeitleiste trägt
   Alternativen und Scores. *Ohne diesen Schritt ist alles andere unmöglich.*
   Änderung ist klein und rein additiv.

2. **Tonart als schwachen Prior einspeisen.** Der billigste Kontexthebel
   überhaupt — die Verteilung existiert bereits
   ([tonality.py:128](../../jampilot/tonality.py#L128)) und wird weggeworfen.
   Sofort messbar: an/aus, Selbsttest.

3. **Revisionen messen.** Den Debug-Trace um Revisionsereignisse erweitern und
   auswerten: Wie oft ändert der Vorlauf die Meinung, bevor es jemand hört, und
   wird es dadurch besser? **Das ist die Kernfrage — und sie ist mit dem
   vorhandenen Code fast beantwortbar.**

4. **Bassverlauf ins Archiv.** Die Bass-Frames werden berechnet und weggeworfen
   ([chroma.py:129](../../jampilot/chroma.py#L129)). Sie aufzuheben kostet
   Speicher, keine Rechenzeit — und ist die Voraussetzung für Slash-Akkorde.

5. **Den Nutzer nach dem Genre fragen**, statt es zu erraten. Ein Schalter ist
   eine Zeile UI; ein Genre-Klassifikator ist ein Projekt.

6. Erst danach: Beat, Taktposition, gelerntes Modell.

---

# Fazit

Die These stimmt, aber sie ist nicht der Beitrag — sie ist der Stand der
Forschung, den das Feld selbst formuliert (Humphrey & Bello) und eine Firma seit
2012 verkauft (Chordify/HarmTrace). Wer sie bloß wiederholt, kommt zehn Jahre zu
spät.

**Der Beitrag liegt woanders, und er liegt schon im Repository:**

Dieses Programm sieht die Zukunft, bevor der Mensch sie hört, und es darf seine
Anzeige widerrufen, solange sie noch niemand gesehen hat. Beides ist gebaut,
getestet, und wird **für nichts benutzt** — außer, um einen Balken über den
Bildschirm laufen zu lassen. Kein anderes Echtzeitwerkzeug hat diesen Spielraum,
weil alle anderen ihre Latenz minimieren.

Die Frage ist also nicht „Interpretation statt Detektion?". Die ist beantwortet.
Die Frage ist:

> **Wie viel besser wird eine Akkordanzeige, wenn der Interpreter vier Sekunden
> Zukunft hat — und was misst man, um das zu zeigen, wenn die etablierte Metrik
> es per Konstruktion nicht sehen kann?**

Das ist ein Forschungsprojekt. Und es fängt mit einer kleinen, additiven Änderung
an: **hör auf, die Evidenz wegzuwerfen.**

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

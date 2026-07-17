# Gitarrenmodus: sichere, spielbare Voicings

## Ziel

Der Gitarrenmodus versucht nicht, den exakten Fingersatz der Aufnahme zu
rekonstruieren. In einem vollständigen Mix lässt sich meist nicht zuverlässig
entscheiden, ob ein Akkord offen, als Barré oder in einer bestimmten Umkehrung
gespielt wurde.

Stattdessen verfolgt JamPilot ein praktischeres Versprechen:

> Was das Griffbild zum Mitspielen freigibt, soll keinen offensichtlich falschen
> Ton zum Song hinzufügen.

Ein Griff darf deshalb unvollständig oder klanglich neutral sein. Das ist besser
als ein vollständiger Akkord mit einer geratenen Terz oder Septime. Der Ansatz
entspricht dem Bassmodus: Die vorgeschlagene Stimme ist nicht immer die Stimme
der Aufnahme und nicht immer rhythmisch perfekt, ihre Töne sollen aber
harmonisch verwendbar bleiben.

## Erkanntes Akkordvokabular

Die Signalstufe kennt derzeit fünf Akkordqualitäten über allen zwölf
Grundtönen:

| Qualität | Intervalle |
|---|---|
| Dur | Grundton, große Terz, Quinte |
| Moll | Grundton, kleine Terz, Quinte |
| `7` | Dur-Dreiklang, kleine Septime |
| `maj7` | Dur-Dreiklang, große Septime |
| `m7` | Moll-Dreiklang, kleine Septime |

`sus`, `dim`, `aug`, `6`, `add9`, `9`, `11`, `13` und alterierte Akkorde
werden noch nicht als eigene Qualitäten erkannt. Der separat gemessene Bass kann
als Slash-Bass angezeigt werden, bestimmt aber nicht den Gitarrengriff.

## Vom Messwert zur Spielanweisung

Die Akkorderkennung behält neben ihrem Gewinner mehrere nahe Kandidaten mit
ihren Audioscores. Der harmonische Interpreter darf bei gleichem Grundton eine
knappe Qualitätsentscheidung anhand der erkannten Tonart korrigieren. Klare
Audioevidenz gewinnt weiterhin; die Tonart ist ein weicher Prior und kein
Verbot chromatischer Akkorde.

Für das Griffbild folgt danach eine bewusst strengere Entscheidung. JamPilot
bildet die Schnittmenge der Tonklassen, die alle ausreichend nahen Lesarten
desselben Grundtons gemeinsam haben. Nur diese Töne werden zum Mitspielen
freigegeben.

### Unsichere Dur-/Moll-Terz

Sind `A` und `Am` fast gleich plausibel, gilt:

```text
A-Dur: A C# E
A-Moll: A C  E
Sicher: A    E
```

Das Griffbild zeigt deshalb `A5`. Saiten mit C oder C# werden gedämpft. Die
Anzeige entscheidet sich nicht blind für eine Terz, die beim Mitspielen sofort
schief klingen könnte.

Das häufige Auftreten solcher X5-Griffe ist insbesondere bei Blues, Rock und
Gitarrenmusik kein Defekt. Dort sind terzlose Powerchords, offene Quinten und
zwischen Dur und Moll schwebende Terzen musikalisch üblich. Ein X5-Griff ist in
diesem Fall zugleich die konservative und oft die stilistisch passende Antwort.

### Unsichere Septime

Sind beispielsweise `A7` und `A` fast gleich plausibel, ist ihre gemeinsame
Tonmenge A–C#–E. JamPilot zeigt und spielt dann den sicheren A-Dur-Dreiklang. Die
kleine Septime G kommt erst hinzu, wenn die Audioevidenz deutlich genug ist.

Entsprechend fällt ein unsicheres `Am7` auf `Am` und ein unsicheres `Amaj7` auf
`A` zurück.

### Eindeutige Erkennung

Liegt keine fast gleich gute alternative Qualität vor, bleibt der vollständige
erkannte Dreiklang oder Septakkord erhalten. Detail wird also nicht pauschal
entfernt, sondern an die Sicherheit der Messung gekoppelt.

## Griffwahl auf dem Hals

Aus der sicheren Tonmenge erzeugt die Webanzeige spielbare Kandidaten:

- bewegliche E-Form,
- bewegliche A-Form,
- vorhandene offene Sonderformen,
- gedämpfte Saiten für nicht freigegebene Töne.

Ein kurzer Viterbi-Planer betrachtet den hörbaren Akkord und die kommenden
Akkorde im Vorlauf. Er bewertet Handweg, Formwechsel und hohe Lagen und wählt
einen Pfad mit möglichst wenig Bewegung. Das Voicing des hörbaren Akkords wird
einmal festgeschrieben, damit das Griffbild nicht nachträglich springt.

Die Position ist damit eine sinnvolle Spielanweisung, keine Behauptung über den
auf der Aufnahme verwendeten Griff.

## Griffbild und Akkordname

Der große Akkordname bleibt die wahrscheinlichste harmonische Analyse. Das
Griffbild benennt dagegen die tatsächlich sichere Spielvariante:

| Große Anzeige | Unsicherheit | Griffbild |
|---|---|---|
| `A` | A oder Am | `A5` |
| `A7` | Septime unsicher | `A` |
| `Am7` | Septime unsicher | `Am` |
| `A7` | eindeutig | `A7` |

Damit behauptet das Diagramm nicht, einen Ton zu enthalten, den es bewusst
abdämpft.

## Kontrollgitarre

In den Einstellungen lässt sich eine Kontrollgitarre aktivieren. Sie ist kein
Begleitautomat und besitzt keine Rhythmuserkennung. Bei jedem erkannten
Akkordwechsel erklingt ein kurzer, trockener Anschlag auf exakt derselben
Stream-Zeitachse wie das verzögerte Original.

Die Kontrollgitarre:

- spielt nur die freigegebenen sicheren Tonklassen,
- unterscheidet damit hörbar zwischen vollständigem Akkord und X5-Rückfall,
- senkt im Diagnosemodus das Original auf 58 Prozent ab,
- spielt den Kontrollanschlag mit 34 Prozent Spitzenpegel,
- ist vollständig abschaltbar,
- kostet ausgeschaltet keine Synthesezeit,
- übernimmt Rücknahmen noch nicht hörbarer Fehlsegmente.

Der Klang wird lokal mit einem Saitenmodell erzeugt. Es werden keine externen
oder lizenzpflichtigen Samples benötigt. Die Kontrollgitarre rekonstruiert nicht
die exakten Saiten der Aufnahme; verbindlich ist die sichere Tonklassenmenge.

## Was der Modus bewusst nicht verspricht

- keine Erkennung des tatsächlich aufgenommenen offenen oder Barré-Griffs,
- keine Rekonstruktion von Fingersatz, Anschlagsrichtung oder Dynamik,
- keine Rhythmus- oder Takterkennung,
- keine Garantie, dass die vorgeschlagene Stimme die schönste Begleitstimme ist,
- keine vollständige Benennung derzeit unbekannter Akkorderweiterungen.

Das Qualitätsziel ist konservativer: Ein vorgeschlagener Griff kann dünner,
einfacher oder anders als die Aufnahme klingen, soll aber keine nur erratene und
offensichtlich falsche Note hinzufügen.

## Technischer Datenfluss

```text
Audio
  -> CQT/Chroma
  -> mehrere Akkordkandidaten mit Scores
  -> weiche harmonische Interpretation über die Tonart
  -> Schnittmenge sicherer Tonklassen
       -> Gitarren-Griffkandidaten und lagenbewusste Auswahl
       -> Kontrollgitarren-Anschlag
  -> gemeinsame Timeline mit präzisem Onset
```

Relevante Implementierungsstellen:

- `jampilot/chords.py`: Templates und Kandidatenscores
- `jampilot/harmony.py`: Tonartprior und sichere Tonklassenmenge
- `jampilot/web.py`: Griffkandidaten, Saitenfilter und Lagenplanung
- `jampilot/control_guitar.py`: diagnostischer Gitarrenanschlag
- `jampilot/delay_stream.py`: samplegenaue Mischung in das Playback
- `jampilot/cli.py`: Timeline und Übertragung der sicheren Tonklassen

Die älteren Dokumente unter `docs/exploration/` beschreiben die Entwicklung der
ursprünglichen Griffanzeige und der lagenbewussten Voicing-Wahl. Dieses Dokument
beschreibt den aktuell implementierten Stand.

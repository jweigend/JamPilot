# Analyse: Warum die Zeitleiste flackert und Eintraege verschwinden

Stand: 2026-08-26

## Ausgangsfrage

Die aktuelle Frage ist **nicht**, warum ein Modell im Grenzfall schwankt. Das
ist normal. Die eigentliche Produktfrage lautet:

> **Warum darf in JamPilot ein bereits gezeigter Akkord oder eine bereits
> gezeigte Bassinformation in der UI wieder verschwinden?**

Die Antwort nach Code-Lektuere lautet: **weil die Zeitleiste heute nicht als
Archiv bereits gefundener Ereignisse modelliert ist, sondern als laufend
revidierbare Zukunftshypothese.**

Das ist eine bewusste Designentscheidung, keine technische Notwendigkeit.


## Kurzfazit

Die Instabilitaet kommt aus **drei getrennten Schichten**, die sich in der UI
ueberlagern:

1. **Serverseitige Zukunfts-Revisionen**
   Der unerhoerte Teil der Timeline wird bei jedem Modelllauf neu aufgebaut.
   Schon veroeffentlichte Zukunftsakkorde duerfen also wieder entfernt,
   verschoben oder umbenannt werden.

2. **Bass wird nicht am Ereignis, sondern am Segmentintervall gemessen**
   Sobald sich Segmentgrenzen aendern, aendert sich das Messfenster. Dadurch
   kann dieselbe Bassinfo einmal vorhanden und im naechsten Lauf wieder weg
   sein, ohne dass sich der sichtbare Akkordname geaendert hat.

3. **Die UI behandelt auch kleine Datenaenderungen als neue Identitaet**
   Ein Chip ist heute ueber `Zeit | Akkord | Bassnote` identifiziert. Schon ein
   reines Bass-Update loescht und erzeugt das DOM-Element neu, selbst wenn sich
   der sichtbare Text in der aktuellen Ansicht gar nicht aendert.

Wenn man die Zeitleiste stabiler haben will, muss man **nicht nur das Modell**
beruhigen, sondern vor allem diese Produktentscheidung hinterfragen:

> **Soll die Zeitleiste eine Wahrheit in Revision sein – oder eine stabile
> Spielhilfe?**

Nach der Ruecksprache ist die bevorzugte Richtung jetzt klarer:

> **Die Vorlaufansicht soll keine dauernd neu geschriebene Wahrheit sein,
> sondern eine einmal veroeffentlichte Lesefassung auf Zeit.**

Praktisch heisst das: Die Analyse darf kurz sammeln und verstehen; was danach
in die Vorlaufansicht gelangt, bleibt fuer diesen Abschnitt stehen. Neue
Erkenntnisse gelten erst fuer spaeter neu hinzugekommenes Material.


## Was die Zeitleiste heute fachlich ist

Die aktuelle BTC-Zeitleiste ist eine Mischung aus zwei Dingen:

- **nahe Zukunft**, die der Musiker gleich spielen soll,
- **vorlaeufige Modellhypothesen**, die noch durch spaetere Kontexteingaben
  geaendert werden koennen.

Beides liegt in derselben Leiste und wird in derselben visuellen Form gezeigt.
Damit sieht ein Benutzer nicht, ob ein Chip

- ein stabiler, praktisch schon feststehender Wechsel ist,
- oder nur die momentan beste Wette des letzten 10-s-Fensters.

Das ist der Kern des gefuehlten „Flackerns“: **nicht nur Rauschen im Modell,
sondern fehlende Trennung von stabil und spekulativ.**


## Warum Akkorde verschwinden

### 1. Ein Chip repraesentiert kein einzelnes Frame-Urteil

Die Intuition „wenn der Akkord in dem Frame eindeutig erkannt wurde, warum
verschwindet er dann?“ trifft das System nicht ganz.

Im BTC-Pfad wird **kein einzelnes Frame** veroeffentlicht. Verarbeitet wird:

1. ein 10-s-Fenster,
2. darauf die komplette Label-Sequenz,
3. daraus zusammengefasste Segmente,
4. danach ein Neuaufbau des **unerhoerten** Timeline-Teils.

Ein Chip bedeutet also nicht „Frame 73 war G“, sondern eher:

> „Nach dem aktuellen Gesamtkontext glaube ich, dass ab diesem Zeitpunkt ein
> Segment `G` beginnt.“

Wenn derselbe Bereich im naechsten Fenster anders segmentiert wird, verschwindet
der Chip wieder – obwohl innerhalb eines frueheren Laufs dort einmal ein klares
G-Frame vorkam.


### 2. Zukunft wird absichtlich revidiert

Der Merge-Code behandelt alles nach der Einfrierzone als **formbar**. Der
unerhoerte Teil der Timeline wird pro Hop neu aufgebaut. Daraus folgen vier
Mechanismen:

- **Hinter dem Horizont** wird noch gar nichts veroeffentlicht.
- **Neue Chips** brauchen eine Bestaetigung aus dem vorigen Lauf.
- **Alte Chips** bleiben nur stehen, wenn der vorige Lauf sie noch stuetzte.
- **Nicht bestaetigte Zukunft** darf verschwinden.

Das ist fachlich konsistent, aber eine klare Produktaussage:

> Ein bereits gezeigter Zukunftsakkord ist **nicht bindend**.

Die Leiste ist damit eher ein **Speculative Planner** als eine feste Timeline.


### 3. Kurze Segmente werden rueckwirkend wegfusioniert

Segmente unter 250 ms gelten als Modellflackern und werden mit dem Nachbarn
verschmolzen. Das ist als Modellschutz sinnvoll, hat aber eine Folge:

- ein kurz sichtbarer Wechsel kann bei mehr Kontext komplett wieder in seinem
  Nachbarsegment aufgehen.

Auch das fuehlt sich im Browser wie „Akkord war da und ist wieder weg“ an,
obwohl intern die Regel korrekt arbeitet.


### 4. Onset-Korrektur aendert die Identitaet eines Chips

Grenzen werden nach der Veroeffentlichung noch einmal aufs Audio-Ereignis
gezogen. Dadurch kann nicht nur der Akkordname, sondern auch die Startzeit
wechseln. Weil die UI Chips ueber die Startzeit schluesselt, wird aus Sicht des
Browsers oft nicht „derselbe Chip aktualisiert“, sondern „alter Chip weg, neuer
Chip da“.

Der Code versucht das ueber Hysterese zu beruhigen, aber konzeptionell bleibt es
eine **Delete/Recreate-Mechanik**.


### 5. Die UI ist kein Archiv, sondern nur ein Sichtfenster

Chips werden in der UI entfernt, sobald sie durchgelaufen sind. Das ist fuer ein
Vorlaufband sinnvoll. Wichtig ist aber: Es gibt **keine getrennte Ebene** aus

- „dies wurde schon einmal verbindlich gezeigt“ und
- „dies ist jetzt gerade noch sichtbar“.

Deshalb sehen Entfernung, Revision und normales Durchlaufen im DOM sehr aehnlich
aus.


## Warum die orangenen Bass-/Folgesymbole verschwinden

Hier gibt es **nicht eine**, sondern mindestens **drei** Ursachen.

### 1. Die Bassnote ist an ein Intervall gebunden, nicht an einen Zeitpunkt

Die Bassmessung wird pro Segment ueber dessen Dauer gepoolt. Veraendert sich

- der Onset,
- das Segmentende,
- oder der naechste Wechsel,

dann aendert sich sofort auch das Tiefbandfenster. Dieselbe musikalische Stelle
kann dadurch in einem Lauf eine dominante Bassnote ergeben und im naechsten
nicht mehr.

Das ist keine UI-Macke, sondern direkte Folge der fachlichen Definition:

> `b` ist heute **nicht „Bass an Position x“**, sondern **„Bass, der fuer
> dieses aktuell angenommene Segmentintervall stark genug war“**.


### 2. Die Bassentscheidung ist bewusst konservativ

`slash_note()` gibt nur dann etwas zurueck, wenn mehrere Huerden gleichzeitig
genommen werden:

- genug Energie,
- Mehrheit gegen die zweitstaerkste Note,
- passend zum Akkordtonmaterial,
- bei Umkehrungen deutlich staerker als der Grundton.

Sobald eine dieser Huerden im neu gepoolten Fenster nicht mehr gilt, faellt die
Bassinfo auf `None` zurueck. Dann verschwindet

- der Slash-Bass,
- der orange Punkt in der Keyboard-Ansicht,
- oder die orange Zielnote im Bassfenster.


### 3. Der orange Folgeton haengt am naechsten Segment

Im Bass-Griffbrett wird die kommende Linie aus den kommenden Segmenten gebaut.
Wenn der naechste Eintrag

- zurueckgezogen,
- umbenannt,
- dedupliziert,
- oder bassseitig auf den gleichen Pitch-Class-Wert reduziert wird,

dann verschwindet der orange Folgeton sofort. Nicht weil der aktuelle Ton weg
waere, sondern weil die **Prognose fuer den naechsten** Ton sich geaendert hat.


## Ein zusaetzlicher UI-Fehler: zu grobe Identitaet von Chips

Unabhaengig von der Grundsatzfrage gibt es in der aktuellen UI noch einen
eigenen Instabilitaetsverstaerker:

- Die Chip-Identitaet enthaelt immer die Bassnote.
- Die Bassnote wird aber nur in bestimmten Ansichten ueberhaupt sichtbar.

Folge:

- Im normalen Akkordmodus kann ein Chip geloescht und neu erzeugt werden, obwohl
  sich der sichtbare Text gar nicht geaendert hat.

Das ist **kein unvermeidbarer Trade-off**, sondern ein konkreter Kopplungsfehler
zwischen Datenmodell und UI-Identitaet.


## Welche Grundannahmen man in Frage stellen sollte

### Annahme A: „Vorlauf muss bis kurz vor NOW voll revidierbar bleiben“

Das ist technisch bequem, aber musikalisch fragwuerdig. Eine Spielhilfe hat
einen anderen Optimierungspunkt als ein Benchmark:

- **zu spaet korrigierte Wahrheit** ist schlecht,
- **kurz vor der Ausfuehrung verschwindende Wahrheit** oft aber auch.

Die aktuelle Architektur bevorzugt „moeglichst aktuelle Revision“ gegenueber
„moeglichst ruhiger Lesbarkeit“.


### Annahme B: „Bass darf nur gezeigt werden, wenn er gerade jetzt streng
beweisbar ist“

Das ist sehr sauber als Analyseaussage, aber vielleicht nicht optimal als UI.
Fuer den Benutzer ist ein kurz stabil bleibender Slash-Bass oft hilfreicher als
ein Punkt, der dauernd verschwindet, sobald das Intervall leicht umdefiniert
wird.


### Annahme C: „Ein Chip ist dann neu, wenn irgendein Attribut neu ist“

Aus UI-Sicht ist das zu stark gekoppelt. Sichtbar relevant sind je nach Modus
unterschiedliche Attribute:

- im Chord-Modus der Akkordname,
- im Bass-Modus der Slash-Bass,
- in Keyboard/Bass-Diagrammen die orange Zusatzinfo,
- bei Nashville zusaetzlich die Tonika.

Eine einzige starre Identitaet fuer alle Modi produziert unnötigen Churn.


## Produktbewertung

Die heutige Zeitleiste ist logisch stimmig, aber sie optimiert auf die falsche
Frage.

Sie beantwortet gut:

> „Was ist nach dem neuesten Modelllauf die beste Hypothese fuer die Zukunft?“

Ein Musiker braucht aber oft eher:

> „Was soll ich jetzt mit hoher visueller Ruhe als naechstes greifen?“

Diese beiden Ziele sind verwandt, aber nicht identisch.


## Zielbild: feste Anzeige-Slices statt rueckwirkender Neuschrift

Die einfachere und produktnaehere Zielidee ist kein feines Zonenmodell,
sondern dieses Prinzip:

1. Die Analyse bekommt eine feste Zeit zum Verstehen, z. B. rund **2 Sekunden**.
2. Danach wird fuer den entsprechenden Vorlaufabschnitt eine **feste Ansicht**
   veroeffentlicht.
3. Diese veroeffentlichte Ansicht wird **nicht rueckwirkend umgeschrieben**.
4. Neue Audioinformation erweitert nur den **rechten, neu hinzugekommenen Teil**.

Das ist kein „best effort latest truth“-Modell mehr, sondern ein
**publish-once display slice**.


### Was dabei ausdruecklich stabil bleibt

Fuer einen bereits veroeffentlichten Abschnitt bleiben fest:

- der Akkordname,
- die Schreibweise (`#` oder `b`),
- das Vorhandensein der Nashville-Zahl,
- die Bass-/Slash-Information,
- die orange Folgenote in den Instrument-Ansichten.

Wenn spaeter mehr Wissen da ist, gilt das **nur fuer neu veroeffentlichte
Abschnitte**.


### Beispiel Tonart

Wenn die Tonart bei der ersten Veroeffentlichung eines Abschnitts noch nicht
sicher ist, dann ist das fuer diesen Abschnitt ok:

- Akkorde erscheinen zunaechst ggf. in `#`-Schreibweise,
- Nashville-Zahlen fehlen dort noch,
- spaeter erkannte `b`-Schreibweise oder Stufen gelten erst rechts fuer neue
  Abschnitte.

Wichtig ist dabei nicht perfekte Rueckwirkung, sondern **visuelle Ruhe**.


### Beispiel Nashville

Die Zahlen sollen in diesem Modell nicht rueckwirkend ein- und ausgehen.
Stattdessen gilt pro veroeffentlichtem Abschnitt genau eines von zwei Dingen:

- entweder dieser Abschnitt hat **keine** Nashville-Info,
- oder er hat sie **vollstaendig**.

Aber: nie rueckwirkendes Einblenden oder Entfernen in bereits sichtbaren Chips.


### Warum dieses Modell besser zum Produkt passt

Die Vorlaufansicht ist keine Analysekonsole, sondern eine **temporäre
Spielansicht**. Ein Musiker liest keinen wissenschaftlichen Korrekturstrom,
sondern braucht eine kurze, ruhige Fassung dessen, was gleich kommt.

Das neue Prinzip lautet daher:

> **Erst verstehen, dann veroeffentlichen, danach nicht mehr umschreiben.**


## Auswirkungen auf die heutigen Flackerquellen

Mit diesem Modell verlieren mehrere aktuelle Ursachen ihre Schaerfe:

- **Segment-Revisionen** duerfen den bereits veroeffentlichten Teil nicht mehr
  loeschen.
- **Spaete Tonarterkenntnis** aendert nicht mehr rueckwirkend die Glyphen oder
  Nashville-Zahlen.
- **Bass-Neuberechnung** darf nicht mehr alte Chips optisch austauschen.
- **UI-Delete/Recreate** wird seltener, weil sichtbare Slices feste Identitaet
  haben koennen.

Die Analyse darf intern weiterhin alles revidieren. Neu ist nur: **Die Anzeige
bekommt davon nur veroeffentlichte Schnitte zu sehen, nicht den laufenden
Korrekturstrom.**


## Empfohlener naechster Schritt: redundante Mini-POC-UI

Bevor dieses Prinzip in die heutige UI eingebaut wird, ist ein **komplett
redundanter Mini-POC** sinnvoll.

Das Ziel des POC ist nicht gutes Styling, sondern das Produktverhalten isoliert
zu pruefen:

- Wie ruhig wirkt eine publish-once-Vorlaufansicht?
- Fuehlt sich fehlende Rueckwirkung bei Tonart/Nashville besser an als heutiges
  Flackern?
- Reicht eine einfache Slice-Logik, ohne die jetzige UI-Architektur mitzuziehen?


### Was der POC bewusst nicht koennen muss

Der POC muss anfangs **nicht** die volle Produktions-UI nachbauen. Er darf
bewusst schlicht sein:

- einfache horizontale Leiste,
- Akkordchips mit fixer Schreibweise,
- optional Nashville als Textzeile,
- einfache Orange/Bass-Markierung,
- keine komplexen Instrument-Diagramme noetig.

Wichtig ist nur, dass man das neue Anzeigeprinzip live erleben kann.


### Was der POC zeigen sollte

Minimum fuer einen aussagekraeftigen POC:

1. **Linke sichtbare Zone bleibt stehen**
   Bereits veroeffentlichte Chips veraendern sich nicht mehr.

2. **Rechter Rand wird periodisch ergaenzt**
   Mit jedem neuen Analyseschritt kommt nur neues Material hinzu.

3. **Tonart kommt spaeter, aber nur fuer neue Slices**
   Fruehe Chips koennen `#` behalten; spaetere duerfen in `b` erscheinen.

4. **Nashville ist pro Slice ganz da oder gar nicht da**
   Kein Rueckwaerts-Umschalten.

5. **Bassinfo ist pro Slice fest**
   Ein einmal gezeigter Slash-Bass oder orange Marker verschwindet nicht
   rueckwirkend wieder.


### Warum der POC redundant sein sollte

Die jetzige UI ist bereits komplex und traegt viele eigene Regeln. Baut man das
neue Prinzip sofort dort ein, ist am Ende unklar, ob ein beobachteter Effekt

- aus dem neuen Modell,
- aus der alten UI-Logik,
- oder aus deren Mischung stammt.

Ein redundanter POC trennt diese Fragen sauber. Erst wenn das Verhalten dort
ueberzeugt, lohnt sich die Integration in die Produktions-UI.


## Messplan vor einem Umbau

Bevor man etwas groesser umbaut, sollte man die Instabilitaet einmal messbar
machen. Sinnvolle Metriken:

1. **Chip-Ereignisse pro Minute**
   - erzeugt
   - geloescht
   - umbenannt
   - nur Bass geaendert

2. **Rueckzuege nach Sichtbarkeit**
   - wie oft verschwindet ein Chip, nachdem er schon X Sekunden sichtbar war?

3. **Bass-Volatilitaet**
   - wie oft wechselt `b` fuer denselben Akkord, dieselbe Lage, denselben Onset?

4. **Benutzungsnahe Zonenanalyse**
   - Churn in `> 2.0 s`
   - Churn in `1.0 .. 2.0 s`
   - Churn in `< 1.0 s` vor NOW

Gerade die letzte Metrik ist produktrelevant: Flackern weit rechts ist weniger
kritisch als Flackern kurz vor der Ausfuehrung.


## Vorlaeufige Empfehlung

Wenn das Ziel ausdruecklich **weniger Flackern und mehr Vertrauen** ist, dann
wuerde ich im naechsten Schritt **nicht zuerst am Modell** ansetzen, sondern an
der **Semantik der Veroeffentlichung**:

1. Anzeige als **feste Slices** denken,
2. redundanten Mini-POC bauen,
3. erst danach pruefen, welche Teile in die bestehende UI uebernommen werden.

Erst danach lohnt sich Tuning an Hysterese, Debounce oder Grenzwerten.


## Eine ehrliche Produktthese

Die aktuelle Zeitleiste ist fuer Analyse schoen, fuer Live-Spielhilfe aber
wahrscheinlich **zu wahrheitsgierig und zu wenig merkfaehig**.

Anders gesagt:

> Das System korrigiert lieber weiter, als dem Musiker etwas fuer kurze Zeit
> verlässlich stehen zu lassen.

Ob das richtig ist, ist keine Modellfrage, sondern eine Produktentscheidung.

Die nun bevorzugte Alternative ist einfacher:

> **Die Analyse darf nachdenken. Die Anzeige darf danach stehenbleiben.**

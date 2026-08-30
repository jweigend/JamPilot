# Record-Modus: der Mitschnitt wird ein Modus, kein Grundzustand

Stand: 2026-08-30 · Status: **Umgesetzt auf `feature/record-modus`** — ein
frischer Branch ab dem letzten Stand vor dem Mitschnitt-Experiment
(`7e964c7`), auf den nur die Teile übernommen wurden, die tragen: der
Speicherpuffer, die Callback-Härtung, die Uhr-Behandlung der Anzeige. Bewusst
**kein Merge** — erst Proberaum, dann Urteil (§ 12).

Zieht die Konsequenz aus den ersten Bass-Proben mit dem Vorläufer
(`feature/pause-buffer`, sechs Commits, bleibt als Referenz stehen): Die
Pausetaste war als Grundzustand gedacht und hat sich als Grundzustand nicht
bewährt. Sie ist jetzt ein **Modus**, den man betritt und wieder verlässt.

> **Entscheidung in einem Satz:** Die Leertaste gehört wieder dem Stummschalter;
> der Mitschnitt lebt in einem eigenen Modus hinter der `R`-Taste, der sich nur
> durch einen roten Punkt und eine halbtransparente Transportleiste bemerkbar
> macht — und beim Verlassen restlos verschwindet.

Zuständigkeiten danach:

| Zuständigkeit | Ort |
|---|---|
| Verzögern, Analysieren, Committen | **unverändert**, `delay_stream` + `cli` |
| Aufzeichnen, Leseposition halten | `pause_buffer` — **nur im R-Modus aktiv** |
| Wohin ein Sprung geht (Akkordgrenze) | `engine`, liest den EventLedger |
| Transportleiste zeichnen, Tasten annehmen | `index.html` |


## 1. Der Befund aus dem Proberaum

Die gebaute Fassung legt die Pause auf die Leertaste und zeigt unten dauerhaft
einen Streifen mit dem Rückstand in Sekunden. Nach den ersten Proben am Bass:

* **Die Leertaste ist am Stummschalter besser aufgehoben.** Stummschalten ist
  die häufige Geste (kurz mit jemandem reden, das Instrument allein hören); der
  Mitschnitt ist die seltene. Die naheliegendste Taste gehört der häufigsten
  Handlung, nicht der interessantesten.
* **Der Sekundenstreifen ist Lärm.** Wie weit man zurückliegt, ist keine
  Information, die man beim Spielen braucht — man hört ja, wo man ist. Was man
  braucht, ist: *bin ich im Aufnahmemodus oder nicht.*
* **Fünf Sekunden sind die falsche Sprungweite.** Man will nicht „fünf Sekunden
  zurück", man will „diesen Wechsel nochmal". Die Sprungeinheit ist der
  **Akkord**, nicht die Sekunde.
* **Der Modus muss restlos verschwindbar sein.** Solange nicht feststeht, ob er
  das Werkzeug bereichert oder überfrachtet, darf er im Normalbetrieb nicht
  spürbar sein — weder als Taste, noch als Pixel, noch als Speicher.


## 2. Zustandsmodell: zwei Schalter, nicht einer

Heute gibt es einen Zustand (`paused`) und einen abgeleiteten Versatz. Künftig
sind es **zwei unabhängige Schalter** plus den abgeleiteten Versatz:

| Zustand | Bedeutung | wo |
|---|---|---|
| `record` | Der Mitschnitt läuft mit. | `pause_buffer` |
| `transport_paused` | Die Wiedergabe steht. Nur *innerhalb* von `record` sinnvoll. | `pause_buffer` |
| `offset` | Rückstand zur Live-Kante, abgeleitet aus `_written − _play_end`. | `pause_buffer` |
| `muted` | Lautsprecher aus. **Orthogonal**, gilt in beiden Modi. | `delay_stream` |

Die Invarianten, die das Ganze tragen:

```
record == False   ⟹   offset == 0  ∧  transport_paused == False
                  ∧   die Ausgabe ist bitgleich zu einem Lauf ohne Mitschnitt
                  ∧   heard_position() == audible_position()
```

Die letzte Zeile ist die wichtigste des Dokuments. Ist `record` aus, läuft
**exakt der Code von vor diesem Branch** — keine zweite Uhr, kein Fenster auf
der Event-Liste, kein Epoch-Zähler. Alle drei Fehler, die dieser Branch bisher
produziert hat, saßen in genau dieser Zusatzmechanik; mit `record == False`
kann keiner davon auftreten. Das ist als Test formulierbar und soll auch so
festgeschrieben werden (§ 10.1).

Mute bleibt bewusst orthogonal und sitzt weiterhin **hinter** dem Mitschnitt:
Wer stumm schaltet und später zurückspringt, findet die Musik wieder, nicht die
selbst verordnete Stille.


## 3. Tastatur

| Taste | ohne R-Modus | im R-Modus |
|---|---|---|
| `Space` | **Mute an/aus** | **Mute an/aus** (unverändert) |
| `R` | R-Modus **an** | R-Modus **aus** → Sprung auf NOW |
| `P` | – | Wiedergabe **play/pause** |
| `←` | – | **voriger** Akkord |
| `→` | – | **nächster** Akkord |
| `Home` | – | Anfang des Mitschnitts |
| `End` | – | NOW (Live-Kante) |
| `M` | Mute an/aus (Alias) | Mute an/aus (Alias) |

Rückbau gegenüber dem gebauten Stand: `Space` war Pause, `M` war Mute, `L` war
„zurück zu live". `Space` geht an den Stummschalter zurück, `M` bleibt als
Alias bestehen (kostet nichts, und wer sich `M` angewöhnt hat, verliert nichts),
`L` entfällt zugunsten von `End`.

**Warum `P` und nicht `Space` für play/pause?** Eine kontextabhängige Leertaste
— außerhalb Mute, innerhalb play/pause — wäre die elegantere Tabelle und die
schlechtere Bedienung: Man schaltet im R-Modus genauso stumm wie außerhalb, und
eine Taste, die je nach unsichtbarem Zustand zweierlei tut, ist die Sorte
Überraschung, die man im Proberaum nicht gebrauchen kann. Verworfen.


## 4. Die Transportleiste

Erscheint **nur** im R-Modus, unten, halbtransparent, fünf Knöpfe:

```
        ┌───────────────────────────────────────────────┐
        │   |◀◀      ◀◀      ▶ / ❚❚      ▶▶      ▶▶|    │
        │  Anfang  Akkord   play/pause  Akkord   NOW    │
        └───────────────────────────────────────────────┘
```

* **Halbtransparent im Normalfall**, voll deckend bei Hover/Touch. Die Leiste
  ist Werkzeug, nicht Bühne — sie darf den großen Akkord nicht bedrängen.
* **Sie löst das Handy-Problem.** Bisher ist der Mitschnitt reine
  Tastaturfunktion, und die Anzeige steht laut eigenem Code-Kommentar meistens
  auf einem Handy. Mit der Leiste ist er dort bedienbar — bis auf das *Betreten*
  des Modus, siehe § 10.2.
* **Kein Fortschrittsbalken, keine Zeitangabe.** Ausdrücklich nicht: Wo im
  Mitschnitt man steht, sagt die Musik. Ein Balken wäre die Rückkehr des
  Sekundenstreifens in Grafikform.


## 5. Sprung auf Akkordgrenzen

Das ist die inhaltlich neue Idee und der Grund, warum der Modus sich lohnen
könnte. Bisher springt `seek()` um feste 5 s. Künftig springt er auf die
**Onsets der committeten Events**.

### 5.1 Woher die Grenzen kommen

Der Mitschnitt rechnet in Frames und weiß nichts von Akkorden; die Akkorde
liegen im `EventLedger` der Anzeigeschleife. Die Kopplung geht in **eine**
Richtung, wie bei `engine.lead` und `engine.jetzt`: Die Anzeigeschleife legt je
Hop die Onset-Liste auf der Engine ab, die Engine rechnet daraus das Sprungziel.

> **Wichtig:** Die Engine liest die **volle** Ledger-Liste, nicht das
> veröffentlichte Fenster (`_im_fenster`). Das Fenster ist auf die Anzeige
> zugeschnitten und reicht nur acht Sekunden zurück — ein Sprung über zehn
> Akkorde hinweg fände dort nichts. Der Ledger hält so weit zurück wie der
> Mitschnitt reicht (`ledger_rueckhalt`), und genau das ist hier gebraucht.

### 5.2 Der Algorithmus

```
jetzt = heard_position()

zurück:  ziel = Onset des LAUFENDEN Akkords
         wenn (jetzt − ziel) < NEUSTART_SCHWELLE:      # schon am Anfang
             ziel = Onset des VORIGEN Akkords
vor:     ziel = Onset des NÄCHSTEN Akkords (> jetzt)

ziel = ziel − VORLAUF
seek(ziel − jetzt)                                     # der Puffer klemmt selbst
```

Zwei Feinheiten, beide aus dem Üben begründet:

* **`NEUSTART_SCHWELLE` (Vorschlag 1,0 s).** „Zurück" heißt zuerst *an den
  Anfang des laufenden Akkords* — die CD-Player-Konvention. Man drückt zurück,
  weil man **diesen** Wechsel nochmal will, nicht den davor. Erst wer schon am
  Anfang steht, geht eine Grenze weiter zurück.
* **`VORLAUF` (Vorschlag 0,7 s).** Der Sprung landet ein Stück **vor** dem
  Onset. Wer einen Wechsel lernen will, muss den *Anlauf* hören; genau auf die
  Grenze zu springen liefert den Zielakkord ohne das, was zu ihm hinführt.

Beide Werte sind Playtest-Kandidaten, keine Messwerte. Sie stehen als
Konstanten mit Begründung im Code, damit man sie im Proberaum drehen kann.

### 5.3 Ränder

| Fall | Verhalten |
|---|---|
| kein nächster Onset (an der Live-Kante) | Sprung auf NOW |
| kein voriger Onset (Anfang des Mitschnitts) | Sprung auf den Anfang |
| Ledger noch leer (Anlauf) | Sprung tut nichts, kein Fehler |
| Ziel liegt jenseits der Pufferlänge | der Puffer klemmt (`_stellen`) |


## 6. Das rote Kreisicon

Ein kleiner roter Punkt, oben links neben dem Verbindungspunkt im `#brand` —
dort sitzt schon der Status, und dort sucht das Auge ihn. **Keine Schrift, keine
Sekundenangabe, kein Balken.**

* **Ruhig, nicht blinkend.** Ein pulsierender Punkt auf einem Notenständer ist
  eine Ablenkung. Aufnahmegeräte blinken, weil man vergessen könnte, dass sie
  laufen — hier verlässt man den Modus mit derselben Taste, mit der man ihn
  betreten hat.
* **Der Streifen `#behind` entfällt ersatzlos**, samt seiner Halbtransparenz-
  Logik von gestern. Damit fällt auch das Feld `behind` aus dem SSE-Zustand weg;
  `paused` und `epoch` bleiben (die Uhr braucht sie weiter).

Eine Lücke, die ich benennen muss: Der Punkt sagt *Modus an*, aber nicht *du
bist zurückgesprungen*. Wer im R-Modus zurückspringt und es vergisst, spielt zu
einer Aufnahme von vor zwei Minuten und merkt es nur daran, dass es nicht mehr
zur Quelle passt. Ein Vorschlag dazu steht in § 10.3 — bewusst als offene
Entscheidung und nicht als Teil der Spezifikation, weil du „nur ein kleines
rotes Kreisicon" gesagt hast.


## 7. Speicher: Reservierung wird faul

Bisher werden 659 MiB beim **Start** reserviert und angefasst. Die Begründung
war: Ein Seitenfehler dieser Größe im Audio-Callback wäre ein Aussetzer, und ein
Fehlschlag soll passieren, solange nichts auf dem Spiel steht.

Diese Begründung trägt weiter — aber die Voraussetzung hat sich geändert. Der
Mitschnitt war ein Grundzustand, jetzt ist er ein **bewusst betretener Modus**.
In jeder Sitzung 659 MiB für einen Modus zu reservieren, den die meisten
Sitzungen nie betreten, ist genau die Überfrachtung, um die es hier geht.

**Vorschlag:**

| Zeitpunkt | was passiert |
|---|---|
| Start | Speicher **prüfen** (`plan()`), nicht belegen. Reicht er nicht: `R` ist inaktiv, Hinweis im Startprotokoll. |
| erstes `R` | Reservieren **im Hintergrundthread**; roter Punkt sofort, Aufzeichnung startet, sobald die Seiten da sind (~0,2 s). |
| `R` aus | Speicher **behalten** — ein zweites `R` muss sofort greifen. |
| `stop()` | freigeben, wie heute. |

Die 0,2 s Verzug sind unkritisch: Man drückt `R`, weil man aufzeichnen will, was
*kommt*. Schlägt die Reservierung trotz Startprüfung fehl (jemand hat sich
zwischenzeitlich den Speicher genommen), bleibt `R` wirkungslos mit einer
Meldung — nie ein Absturz, nie ein Aussetzer.

`--pause-buffer 0` schaltet `R` weiterhin komplett ab.


## 8. Verlassen des Modus

`R` im R-Modus, in dieser Reihenfolge:

1. Wiedergabe auf **NOW** (`to_now()`), überblendet wie heute — kein Knacken.
2. `transport_paused` aufheben, falls gesetzt.
3. Aufzeichnung aus; `offset` ist damit 0 und der Durchlauf wieder bitgleich.
4. Roter Punkt und Transportleiste verschwinden.
5. Der Pufferinhalt gilt als verworfen; ein neues `R` beginnt eine neue
   Aufzeichnung. (Der *Speicher* bleibt, siehe § 7.)

`R` ist damit auch die Notbremse: Wer sich im Mitschnitt verirrt hat, kommt mit
einer Taste zurück in den Normalbetrieb.


## 9. Was unverändert bleibt

* **Die Verzögerungsstufe.** Ringpuffer weiter exakt `delay` lang, Zeitbasis der
  Analyse weiter konstant. Der Mitschnitt bleibt eine eigene Stufe dahinter.
* **Analyse, Merge, Commit-Grenze, EventLedger.** Kein Eingriff.
* **Die Härtung** der Callback-Ränder (variable Blockgrößen) bleibt — die ist
  unabhängig vom Modus richtig.
* **Der Fix für lang gehaltene Akkorde** (`_im_fenster` behält den klingenden
  Eintrag) bleibt — er greift nur bei aktivem Fenster, aber er ist die richtige
  Semantik.
* **`heard_position()`** bleibt samt Frame-Zähler-Zweig; mit `record == False`
  fällt sie auf `audible_position()` durch.


## 10. Offene Entscheidungen

**10.1 Die Bitgleichheits-Zusage als Test.** *Umgesetzt:*
`test_record_buffer.py::TestModus::test_aus_ist_bitgleich_und_ruehrt_den_ring_nicht_an`
und `test_delay_stream.py::TestMitschnittAngehaengt::test_eingehaengt_aber_aus_ist_die_uhr_dieselbe`
halten § 2 fest — Byte für Byte, und `heard_position()` ist ohne Aufnahme
dieselbe Funktion, nicht nur dieselbe Zahl.

**10.2 Wie betritt man `R` auf dem Handy?** *Entschieden: gar nicht.* Record
ist Laptop-Geste; das Handy am Notenständer **zeigt** den Modus (roter Punkt)
und **bedient** die Transportleiste — vor, zurück, play/pause, Anfang, Ende
gehen von überall. Betreten und verlassen wird er nur per Taste.

**10.3 Sagt der Punkt, dass man zurückliegt?** Vorschlag ohne Schrift: Der Punkt
ist **gefüllt**, solange live aufgezeichnet wird, und wird zum **Ring**, sobald
man hinter der Live-Kante steht. Gleiche Größe, gleiche Farbe, keine Bewegung.
*Offen — du hast „nur ein kleines rotes Kreisicon" gesagt, und das hier ist
genau ein Zeichen mehr, als du bestellt hast.*

**10.4 Was zeigt das Kontrollfenster?** Das Terminal und die Qt-Statuszeile sind
Diagnoseflächen, keine Bühne — dort wäre eine Sekundenangabe („12 s back")
weiterhin nützlich, während sie in der Webanzeige verschwindet. *Vorschlag:
Kontrollfenster behält sie, Webanzeige nicht.*

**10.5 Vorlauf und Neustart-Schwelle** (§ 5.2): 0,7 s / 1,0 s sind geraten.
*Im Proberaum zu drehen.*


## 11. Umsetzungsreihenfolge

Klein und einzeln testbar, damit jeder Schritt für sich zurückgenommen werden
kann:

1. **Rückbau.** `Space` → Mute, `#behind` raus, `L` raus, `behind` aus dem
   SSE-Zustand. Danach ist der Branch funktional wieder der alte Stand plus
   einem Mitschnitt ohne Bedienung.
2. **Modus-Schalter.** `record` in `pause_buffer`, Invarianten aus § 2 als
   Tests, `R` in Webanzeige und Qt-Fenster, roter Punkt.
3. **Faule Reservierung** (§ 7) samt Hintergrundthread und Fehlerpfad.
4. **Akkordsprünge** (§ 5): Onset-Liste auf der Engine, `seek_chord`,
   Pfeiltasten umstellen.
5. **Transportleiste** (§ 4) mit `Home`/`End`/`P`.
6. **Doku** nachziehen: README-Bulletliste, UNDER-THE-HOOD, CHANGELOG-Eintrag
   umschreiben (der beschreibt derzeit `Space` als Pause).


## 12. Die eigentliche Frage: überfrachtet das das Werkzeug?

Das Dokument wäre unehrlich, wenn es diese Frage nicht selbst stellte — sie ist
der Grund, warum der Branch nicht gemerged wird.

**Was dagegen spricht.** Dieser Branch hat bisher **drei** Fehler produziert,
und alle drei kamen aus derselben Ecke: dem Nebeneinander von Analysezeit und
Hörzeit (`behind` fehlte im Republish; lang gehaltene Akkorde fielen aus dem
Publish-Fenster; das Laufband zitterte, weil eine kontinuierliche gegen eine
blockweise Uhr rechnete). Das ist keine Pechsträhne, das ist der Preis einer
zweiten Zeitachse. Dazu kommen eine Taste, ein Modus und eine Leiste in einem
Werkzeug, dessen Alleinstellung „null Anlauf" heißt.

**Was dafür spricht.** Der Rückbau nimmt dem Preis die Schärfe: Mit `record ==
False` läuft keine der drei Fehlerquellen. Der Modus kostet im Normalbetrieb
eine Taste, die sonst niemand belegt, und (mit § 7) kein Byte. Und die
Akkordsprünge sind das erste Stück des Ganzen, das kein anderes Werkzeug so
bietet — „spiel mir diesen Wechsel nochmal, mit Anlauf" ist genau die Geste, die
beim Üben fehlt.

**Woran du es entscheidest.** Nicht am Gefühl nach einer Session, sondern an
drei Fragen nach etwa fünf Proben:

1. **Hast du `R` gedrückt?** Wie oft, in wievielen Sessions? Wer den Modus in
   fünf Proben zweimal betritt, braucht ihn nicht.
2. **Wenn ja: Pfeiltasten oder play/pause?** Wenn fast nur die Pfeile, ist das
   Feature in Wahrheit „Wechsel wiederholen" — dann kann alles Übrige weg
   (Transportleiste, Anfang/Ende, vielleicht sogar play/pause).
3. **Hat dich der Modus je gestört, wenn du ihn nicht wolltest?** Versehentlich
   betreten, vergessen zu verlassen, verwirrende Anzeige. Ein einziges „ich war
   im Aufnahmemodus und wusste es nicht" ist ein Befund gegen § 6.

**Der Ausstieg ist billig.** Weil der Mitschnitt eine eigene Stufe hinter dem
fertigen Mix ist und die Verzögerungsstufe nie angefasst wurde, ist das
Entfernen ein sauberer Rückbau: ein Modul, ein Einhängepunkt, eine Handvoll
Anzeigezweige. Falls die Antwort „überfrachtet" lautet, kostet sie einen
Nachmittag — und die Härtung aus § 9 bleibt als Gewinn zurück.

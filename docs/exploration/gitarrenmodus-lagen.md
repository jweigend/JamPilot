# Gitarrenmodus, Ausbaustufe: lagenbewusste Voicing-Wahl

*Explorationsdokument. Status: Entwurf mit Entscheidungen und Umsetzungsplan —
Grundlage für die Implementierung im selben Zweig. Baut auf
[gitarrenmodus.md](gitarrenmodus.md) auf.*

---

## Warum die erste Fassung zu kurz greift

Die erste Fassung wählt für jeden Akkord **isoliert** die tiefste von E-/A-Form.
Das ist ein Akkordkatalog: die Antwort auf „Wie greife ich X?" — kontextfrei, für
jeden Akkord einzeln. Das kann jede App, jedes Buch, jede Webseite.

Ein Gitarrist denkt aber nicht akkordweise, sondern in **Lagen**. Er bleibt mit
der Hand an einem Fleck und nimmt lieber ein Barré im 3. Bund, *wenn* die
folgenden Akkorde nah liegen (Bund 4–5, ähnliche Griffform), statt für jeden
Akkord an den Hals-Anfang zu springen. Genau dieses „nah bleiben" ist der
eigentliche Mehrwert — und die isolierte Wahl zerstört ihn. Einem Anfänger nur
den offenen E-Griff zu zeigen, ist nur die ersten paar Wochen interessant.

## Die eigentliche Frage

Nicht **„Wie greife ich X?"** (Katalog), sondern **„Wie spiele ich DIESE
FOLGE?"** Das Voicing eines Akkords hängt damit von seinen **Nachbarn** ab — das
ist kein Nachschlagen mehr, sondern **Spielanleitung**: nicht *was* zu greifen
ist, sondern *wie* man sich über den Hals bewegt.

Und der entscheidende Punkt: Das ist **JamPilots** Feature, nicht das einer
beliebigen Akkord-App. Es braucht den **Vorlauf** — die kommenden Akkorde. Die
Timeline liegt bereits im Browser vor (`chords = [{c, at, b}]`). Der
lagenbewusste Modus ist das einzige Stück Gitarrenmodus, das den Vorlauf
tatsächlich *nutzt*; ohne Lookahead ist er prinzipiell nicht möglich. Das ist der
Burggraben.

## Der Ansatz: Voicing-Pfad mit minimaler Handbewegung

### Kandidaten-Voicings je Akkord

Für einen Akkord (Grundton-Tonklasse `pc`, Qualität) gibt es mehrere spielbare
Lagen über den Hals:

- **E-Form** (Grundton auf Saite 6) bei Bund `R_E = (pc − 4) mod 12`
- **A-Form** (Grundton auf Saite 5) bei Bund `R_A = (pc − 9) mod 12`
- ggf. eine **offene Sonderform** (C, G, D-Familie), die sich nicht aus den
  beweglichen E-/A-Schablonen ergibt (offenes C = x32010, G = 320003, D = xx0232
  usw.)

E- und A-Form liegen 5 Bünde auseinander (`R_A = (R_E − 5) mod 12`), decken also
zwei Hals-Regionen ab. Zusammen mit den offenen Formen hat jeder Akkord 2–3
Kandidaten in unterschiedlichen Lagen. Der **Anker** eines Voicings ist der Bund,
an dem die Hand sitzt (Barré-Bund; bei offenen Formen ~0).

### Die Wahl als Pfad-Optimierung (DP / Viterbi)

Über das sichtbare Fenster (hörbarer Akkord + kommende) wird der Pfad durch die
Kandidaten gesucht, der die **Handbewegung minimiert**:

- **Übergangskosten** zwischen aufeinanderfolgenden Voicings:
  `|Anker_i − Anker_{i+1}|` (Handweg) + kleine **Formwechsel-Strafe** (E→E leichter
  als E→A) .
- **Knotenkosten** je Voicing: milder **Offen-/Tieflagen-Bonus** (damit, *wenn*
  Bewegung nichts kostet, der offene/tiefe Griff gewinnt) + leichte **Hochlagen-Strafe**
  (Spielbarkeit).

Das versöhnt beide Ziele: Anfänger bekommen offene Griffe, *wo sie gratis sind*;
Fortgeschrittene bekommen „Lage halten", *wo es hilft*. Der offene-Griff-Override
aus der Diskussion fällt so als Sonderfall des Offen-Bonus heraus — keine
Extraregel.

### Die harte Stelle: Stabilität im Streaming

Das Fenster schiebt sich, neue Akkorde tauchen am Horizont auf — und der optimale
Pfad kann sich *rückwirkend* ändern. Ein schon gezeigtes Griffbild dürfte niemals
umspringen.

Lösung — **Receding Horizon / einmal entscheiden, dann festnageln**:

1. Angezeigt wird nur das Griffbild des **hörbaren** Akkords.
2. Wird ein Akkord hörbar und hat noch kein Voicing, wird es **jetzt** entschieden
   — mit dem Voicing des Vorgängers als **festem** Startknoten und dem Lookahead
   der kommenden Akkorde, damit die Wahl nicht in eine Sackgasse führt.
3. Einmal entschieden, bleibt es **gesperrt**. Der Nachfolger wird später mit
   diesem als festem Start entschieden.

So ist jeder angezeigte Übergang (Vorgänger→aktuell) mutual optimiert, jede
Entscheidung fällt mit vollem Lookahead — und weil nur der gesperrte aktuelle
Akkord gezeigt wird, **flackert nichts**. Der Lookahead verbessert die aktuelle
Wahl (weg von Sackgassen), auch wenn nur der aktuelle Akkord festgeschrieben wird
— genau dafür braucht es die Timeline.

Bei Stille/„?" bleibt die letzte Lage stehen (die Hand wandert nicht); nach
langer Pause darf sie sich zurücksetzen.

## Verifikation

- **Node-Harness gegen ECHTE Akkordfolgen**: die aus `analyze` gewonnenen
  Progressionen unserer Testsongs (Sting, Peg, Misty) durch den Planer schicken
  und prüfen, dass die Handbewegung klein bleibt (Summe/Median der Anker-Sprünge)
  — im Vergleich zur isolierten Wahl. Das ist der eigentliche Wertnachweis.
- **Eigenschaftstests** an bekannten Progressionen: C–Am–F–G bleibt in einer
  Region statt zwischen Nut und Bund 8 zu springen; eine reine Offen-Griff-Folge
  (Em–C–G–D-Bereich) wählt weiter offen; Grifftöne jedes gewählten Voicings
  stimmen weiter exakt (Regression gegen die erste Fassung).
- **PAGE-/Suite-Tests** grün; `?demo` zeigt den lagenbewussten Wechsel live
  (manuelle QS durch den Autor).

## Nicht-Ziele (bewusst offen)

- Kein Vorschau-Griffbild des *nächsten* Akkords (das könnte bei Neuplanung
  flackern; erst mit Stickiness sinnvoll — spätere Stufe).
- Keine Fingersatz-Optimierung innerhalb eines Griffs.
- Kein globales Optimum über den ganzen Song — Receding Horizon (lokal, stabil)
  ist bewusst gewählt; ein globaler Plan wäre im Streaming ohnehin nicht haltbar.

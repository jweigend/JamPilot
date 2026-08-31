# Lagenwahl im Record-Modus: Anker setzen, Folgegriffe folgen

*Explorationsdokument. Status: Entwurf mit Entscheidungen und Umsetzungsplan —
Grundlage für die Implementierung im selben Zweig. Baut auf
[gitarrenmodus-lagen.md](gitarrenmodus-lagen.md) und
[record-modus.md](record-modus.md) auf.*

---

## Das Bedürfnis

Der Lagen-Planer wählt die Lage mit der geringsten Handbewegung — und liegt
damit meistens richtig, aber nicht immer im Sinn des Spielers. Wer den Refrain
bewusst **tief** und die Strophe **hoch** spielen will (Klangfarbe, Dynamik,
Übungsziel), hat bisher keinen Hebel: Der Planer entscheidet, der Spieler folgt.

Der Record-Modus liefert genau den Moment, in dem man eingreifen möchte: Man
hält an (P), sieht das Griffbild in Ruhe — und will jetzt sagen: „**Diese**
Stelle bitte anders." A-Dur offen? Als Barré im 5. Bund? Beim Keyboard: welche
Umkehrung? Beim Bass: welche Saite?

## Die Idee: ein Anker, kein Override-Katalog

Die Wahl an einer Stelle ist ein **Anker**: Genau dieses Event (dieser Onset)
wird ab jetzt immer in der gewählten Form gezeigt, und die **Folgegriffe werden
von dort aus neu gerechnet** — der Viterbi startet an der Stelle einfach mit dem
Anker als festem Startknoten, exakt wie er heute mit `lastVoicing` startet. Es
gibt keinen zweiten Mechanismus: Der Anker ersetzt nur die *eine* Entscheidung
des Planers; alles danach ist wieder der normale Planer.

Damit ergibt sich das Refrain/Strophe-Verhalten von selbst: ein Anker am
Refrain-Anfang (tief), ein Anker am Strophen-Anfang (hoch) — dazwischen bleibt
der Planer in der Nähe des jeweils letzten Ankers, weil Bewegung kostet.

## Warum das rein im Browser geht

Drei Bestandsentscheidungen tragen das Feature:

1. **Publish-once**: Ein committetes Event ändert sich nie und verschiebt sich
   nie. Sein Onset `at` ist eine stabile Identität — der Anker-Schlüssel ist
   `at|Akkord`, derselbe Schlüssel, den der Voicing-Cache schon benutzt.
2. **Record-Rückhalt**: Im Record-Modus behält der Ledger die Events so weit
   zurück wie der Mitschnitt reicht (`ledger.prune` mit Rückhalt). Wer
   zurückspult, bekommt **dieselben Events mit denselben `at`** wieder — der
   Anker greift bei jedem Durchlauf.
3. **Voicing-Wahl ist Anzeige-Logik**: Instrument, Schreibweise, Griffbrett —
   alles entscheidet der Browser pro Gerät. Die Lagenwahl gehört in dieselbe
   Schicht. Der Server kennt keine Lagen und soll keine kennen.

## Entscheidungen

**Nur im pausierten Record-Modus wählbar.** Die Pfeile erscheinen, wenn
`recording && paused` und ein Griffbrett sichtbar ist. Während der Fahrt wäre
Durchschalten ein Blindflug — und die Zusage „ein gezeigtes Griffbild springt
nie um" bliebe sonst nicht haltbar. Der Anker *wirkt* dagegen immer, auch nach
dem Fortsetzen und bei jedem erneuten Durchlauf.

**Was durchgeschaltet wird, ist der Kandidatenraum des Planers** — nichts
Neues, nichts Erfundenes:

- *Gitarre*: E-Form, A-Form, offene Sonderform (`candidates`), nach Lage
  sortiert. Umkehrungen gibt es hier bewusst nicht: Der Schablonen-Katalog
  kennt keine Slash-Griffe, und ein neuer Griffkatalog ist ein eigenes Feature.
- *Keyboard*: alle Umkehrungen in allen passenden Oktaven (`keyCandidates`) —
  hier **sind** die Alternativen die Umkehrungen; genau der gewünschte Fall.
- *Bass*: die vier Saitenlagen des aktuellen Tons (`bassPositions`).

**Persistenz: solange der Mitschnitt lebt.** Anker gehören zum Mitschnitt —
R aus verwirft den Mitschnitt, also fallen auch die Anker. Kein
`localStorage`: `at` ist Stream-Zeit; nach einem Neustart zeigte ein
gespeicherter Anker auf eine andere Stelle in einem anderen Stück.

**Invalidierung nach vorn, nicht nach hinten.** Ein neuer Anker bei `at = X`
verwirft alle schon entschiedenen Voicings mit `at >= X` — sie werden beim
nächsten Hörbarwerden neu geplant, jetzt vom Anker aus. Entscheidungen *vor* X
bleiben stehen: Der Anker ist eine Aussage über diese Stelle und ihre Zukunft,
nicht über die Vergangenheit.

**Pro Gerät, wie alle Anzeige-Einstellungen.** Laptop und Handy dürfen
verschiedene Instrumente zeigen — dann sind auch die Anker verschieden. Wer am
Handy auf dem Notenständer wählt, wählt für das Handy.

## Bedienung

Unter dem Griffbild (im `#fretboard`-Block) eine kleine Zeile: `‹ 2/3 ›`.
Sichtbar nur bei `body.recording.rec-paused` und wenn es mehr als eine
Alternative gibt. Die Ziffer färbt sich, sobald die Stelle geankert ist —
so unterscheidet sich „Planer-Wahl" von „meine Wahl" auf einen Blick.

Tasten: `↑`/`↓` schalten die Lage durch (nur wirksam im pausierten
Record-Modus). `←`/`→` bleiben der Akkord-Transport — zwei Achsen, zwei
Tastenpaare. Auf dem Handy: die beiden Knöpfe.

## Verworfen

- **Server-seitige Anker** (im Ledger): zöge Instrument-Wissen in den Server
  und bräuchte pro Gerät doch wieder Client-Zustand. Kein Gewinn.
- **Anker per localStorage über den Neustart retten**: falsche Identität
  (Stream-Zeit), siehe oben.
- **Durchschalten auch im Live-Betrieb**: bricht „publish once" der Anzeige
  und trifft nie die gemeinte Stelle — bis man gewählt hat, klingt der
  nächste Akkord.
- **Gitarren-Umkehrungen als zusätzliche Kandidaten**: eigener Griffkatalog
  mit eigener Spielbarkeits-Frage; falls gewünscht, eigener Zweig.

# Nashville-Stufen in der Zeitleiste

*Explorationsdokument. Status: Entwurf mit Entscheidungen und Umsetzungsplan —
Grundlage für die Implementierung im selben Zweig
(`feature/nashville-scale-system`). Die Idee steht seit dem ersten Entwurf auf
der Liste ([first-draft.md](first-draft.md), „Nashville Number System").*

---

## Die Idee

In der Zeitleiste unten steht über jedem Akkordnamen seine **Stufe** in der
erkannten Tonart: über `F` in B♭-Dur ein kleines `V`, über `Cm` ein `ii`. Wer
mitspielt, denkt damit in Funktionen statt in absoluten Tönen — die Folge
`I–vi–IV–V` erkennt man nach zwei Durchgängen wieder, egal in welcher Tonart
das nächste Stück steht. Zusammen mit der Tonart (die im Badge oben ohnehin
angezeigt wird) ergibt sich der richtige Ton automatisch.

Das zahlt direkt auf den Kern ein: Mitspielen ohne Leadsheet. Die Stufe ist
die Information, die ein Musiker beim Raushören ohnehin im Kopf bildet —
JamPilot nimmt ihm diesen Schritt ab, ohne etwas Neues zu erfinden: **Tonart
und Akkorde sind schon da, die Stufe ist reine Arithmetik im Browser.**

---

## Bestandsaufnahme: alles Nötige liegt im Client

Kein Server-Umbau nötig. Im gleichen JS-Scope, in dem die Chips gebaut werden,
liegt bereits alles:

- `tonart` (`index.html:488`) — `{tonic, minor, acc, label}` aus dem
  SSE-Strom, gespeist vom `KeyEstimator` ([tonality.py](../../jampilot/tonality.py)).
  `null`, bis nach ~12 s Musik eine Tonart steht.
- `chords[]` (`:468`) und `chipHtml(seg)` (`:1180`) — dort entsteht das
  Chip-HTML, dort kommt die Stufenzeile dazu.
- `fmtChord` (`:528`) trennt kanonischen Grundton und Qualität, `NOTE_PC`
  (`:626`) liefert die Tonklasse. Die Stufe ist dann
  `(NOTE_PC[root] − NOTE_PC[tonart.tonic] + 12) % 12`, nachgeschlagen in der
  Skala — dieselben Intervalltabellen wie `_MAJOR_SCALE`/`_MINOR_SCALE` in
  [harmony.py](../../jampilot/harmony.py) (`(0,2,4,5,7,9,11)` bzw.
  `(0,2,3,5,7,8,10)`).

---

## Darstellung

### Römische Ziffern, nicht Zahlen

Beide Notationen sind verbreitet: das Nashville Number System schreibt `1 4 5`,
die Funktionslehre `I IV V`. Entscheidung: **römische Ziffern.** Drei Gründe:

1. **Verwechslungsgefahr.** JamPilot zeigt in Bass- und Gitarrenmodus
   Bundzahlen. Eine nackte `4` über einem Akkord liest sich in diesem Umfeld
   als Bund oder Fingersatz. `IV` ist unmissverständlich eine Stufe.
2. **Groß-/Kleinschreibung trägt gratis Information.** `ii` und `V` zeigen
   Moll/Dur auf einen Blick — bei Zahlen bräuchte es ein Suffix (`2m`), das
   nur dupliziert, was im Akkordnamen darunter ohnehin steht.
3. Die Stufe ist **Zweitinformation** über dem Akkordnamen, kein Ersatz. Wer
   klassisches Nashville-Charting mit Zahlen gewohnt ist, liest `IV` genauso
   flüssig; umgekehrt gilt das nicht.

Eine Notations-Wahl im Dialog (römisch vs. Zahlen) gibt es bewusst **nicht** —
siehe unten „Einstellungsdialog klein halten".

### Keine Vorzeichen, keine Zusatzsymbole

Die Stufe ist **relativ zur Tonart**, nicht zu C: In B♭-Dur ist `IV` = E♭ —
ohne ♭ an der Stufe, denn die Tonart macht klar, welcher Ton gemeint ist.
Konsequent weitergedacht:

- **Leitereigene Grundtöne** bekommen die nackte Stufe — im diatonischen
  Normalfall also `I ii iii IV V vi vii` (Dur) bzw. `i ii III iv v VI VII`
  (natürlich Moll). Diese Reihen sind aber das *typische Bild*, keine feste
  Tabelle: Groß/klein folgt immer der erkannten Akkordqualität, nicht der
  Skala — `E7` in a-Moll steht als `V` da, obwohl
  sein Terzton leiterfremd ist: der *Grundton* E ist leitereigen, und mehr
  fragt die Stufenrechnung nicht. Kein `°` am verminderten Akkord, keine `7`
  an der Dominante — die Qualität steht im Akkordnamen direkt darunter.
- **Leiterfremde Grundtöne bekommen keine Stufe.** Ein E♭-Akkord in C-Dur
  stünde klassisch als `♭III` — das verlangt genau die ♭-Symbole, die wir
  nicht wollen, und suggeriert eine Sicherheit der Deutung, die die Erkennung
  nicht hat. Stattdessen bleibt die Zeile leer. Die Leere ist selbst
  Information: „dieser Akkord fällt aus der Tonart" — für den Improvisierenden
  ein nützliches Warnsignal, im Geist der bewussten Ambiguität-als-Feature.

*Verworfen:* `♭VII`/`♯IV` mit Vorzeichen-Präfix. Das ist in Rock/Pop häufig
(mixolydisches `♭VII`), aber es widerspricht der Grundentscheidung und füllt
die Zeile mit Symbolen, die beim Mitspielen nichts beschleunigen. Falls der
Playtest zeigt, dass die leeren Stufen bei modalen Stücken stören, ist das
Präfix ein kleiner, rückwärtskompatibler Nachrüstschritt.

### Layout im Chip

Über dem Grundton, **linksbündig auf derselben Kante** — die linke Textkante
markiert im Laufband den Zeitpunkt (Kommentar `index.html:236-238`), die Stufe
muss dieselbe Kante halten, sonst lügt sie über das Timing. Zwischen
Lane-Oberkante und Akkord-Glyphe sind ~4–5 vh frei; das reicht für eine Zeile
in ~2.2 vh, gedeckt gefärbt wie die `.eta`-Zeile darunter (`#4a5158`-Familie),
damit die Hierarchie stimmt: Akkordname laut, Stufe und Countdown leise.

```
  IV                V
  E♭maj7            F
  in 2.3s           in 6.1s
──────┼──────────────────────────  ← NOW-Linie
```

Solange `tonart == null` (erste ~12 s), erscheinen schlicht keine Stufen —
dasselbe ehrliche Verhalten wie beim Tonart-Badge und der automatischen
Schreibweise. Slash-Akkorde (`C/E`) beziehen die Stufe auf den Akkord-Grundton
C, nicht auf den Basston. `N`, `-`, `?` bekommen nie eine Stufe.

*Offen (Folgeausbau, nicht Teil dieses Zweigs):* dieselbe Stufe klein am
großen aktuellen Akkord (`#current`) und im Keyboard-/Gitarrenmodus. Erst der
Playtest in der Zeitleiste zeigt, ob das mehr hilft als unruhig macht.

---

## Einstellungsdialog klein halten

Der Dialog ist eine einzige Spalte aus Sektionen; jede neue Sektion kostet
Scrollweg. Entscheidung: **genau eine neue Sektion mit genau zwei Karten** —
An/Aus. Alles andere ist Designentscheidung statt Einstellung:

- keine Notations-Wahl (römisch ist gesetzt, s. o.),
- keine Tonart-Übersteuerung (die Tonart kommt aus der Erkennung; eine
  manuelle Tonartwahl wäre ein eigenes Feature mit eigenem Papier),
- keine Vorzeichen-Optionen (es gibt keine Vorzeichen).

Vorschlag für die Sektion (nutzersichtbar Englisch, wie alles im Dialog):

> **Scale degrees**
> *Every key has the same seven chords — the degree (I, IV, V…) names their
> role. Shown above each chord in the timeline once the key is settled, so a
> progression looks the same in every key.*
>
> **Shown** — Roman numerals above the timeline chords. `[an]`
> **Hidden** — Just the chord names. `[aus]`

**Default: an.** Das Feature ist unaufdringlich (kleine, gedeckte Zeile),
erklärt sich durch die Tonart im Badge von selbst und ist sonst unauffindbar.
Persistenz nach dem Muster des Griffbrett-Toggles (`setzeGriffbrett`,
`index.html:1325`): `localStorage`-Schlüssel `jampilot.degrees`,
Default-an-Idiom `localStorage.getItem(KEY) !== "off"`, Umschalten über den
bestehenden zentralen `.opt`-Click-Dispatcher (`:1449`).

---

## Stolpersteine

1. **Chip-Cache invalidiert bei Tonika-Wechsel nicht.** Chips sind über
   `at|chord|bass` gekeyt (`index.html:1197`); `neuSchreibenFallsNoetig`
   (`:1270`) baut bislang nur bei *Vorzeichen*-Wechsel neu. Eine Stufenanzeige
   hängt zusätzlich an der **Tonika** — wechselt der `KeyEstimator` die Tonart
   (oder kommt sie nach 12 s erstmals an), müssen die Chips neu geschrieben
   werden, sonst stehen veraltete Stufen im Laufband. Das ist der eine Ort, an
   dem man den Fehler lautlos einbaut.
2. **Tonart-Konfidenz.** Der `KeyEstimator` wechselt träge
   (`SWITCH_MARGIN`), das dämpft Stufen-Flackern von allein. Keine eigene
   Hysterese in der Anzeige einbauen, bevor ein Realaudio-Test zeigt, dass es
   nötig ist.
3. **Moll-Numerierung.** Stufen relativ zur Moll-Tonika (`i iv v/V …`), nicht
   relativ zur Dur-Parallele — das Badge zeigt „A minor", also muss `Am`
   darunter `i` heißen, alles andere verwirrt.

---

## Umsetzungsplan

1. `index.html`: `stufeVon(name)` → `"IV"` / `null`, in **zwei getrennten
   Schritten** — eine feste PC→Stufenname-Tabelle reicht semantisch nicht,
   sie könnte `E7` in a-Moll nur als `v` ausgeben:
   - **Skalengrad** aus Grundton + Tonart: PC-Differenz in der Dur-/Moll-
     Skala nachschlagen → Ordnungszahl 1–7, oder `null` bei leiterfremdem
     Grundton.
   - **Schreibweise** aus der kanonischen Qualität des Akkords: Suffix
     abtrennen wie in `fmtChord` (`:528`); klein bei Moll- oder verminderter
     Terz (`m`, `m6`, `m7`, `mMaj7`, `m7b5`, `dim`, `dim7`), sonst groß.

   Python-Vorbilder für genau diesen Split und die Qualitätslogik:
   `_parse` in [control_guitar.py](../../jampilot/control_guitar.py) (`:38`)
   und `_foreign_tones` in [harmony.py](../../jampilot/harmony.py) (`:30`) —
   dort ist der E7-in-Moll-Fall bereits als Kommentar dokumentiert.
   Aufruf in `chipHtml`, neue Zeile `<span class="degree">` mit CSS analog
   `.eta`.
2. Chip-Key bzw. Rebuild um die Tonika erweitern (Stolperstein 1);
   `apply(state)` löst bei Tonika-Wechsel `neuSchreibenFallsNoetig` aus.
3. Dialog-Sektion + `setzeStufen(an)` nach dem Muster von `setzeGriffbrett`,
   Schlüssel `jampilot.degrees`, Verkabelung im `.opt`-Dispatcher und im
   Startup-Block (`:1469`).
4. Tests: `tests/test_web.py::TestSeite` um String-Assertions für die neue
   Sektion und den Schlüssel erweitern (Muster: Fretboard-Toggle, `:116`).
5. Visuelle Iteration über `?demo` (`index.html:1474`) — die Demo spielt
   F-Dur, Tonart kommt nach 8 s: exakt der Fall „Stufen erscheinen später".

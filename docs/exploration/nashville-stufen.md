# Nashville-Stufen in der Zeitleiste

*Explorationsdokument. Status: Umgesetzt im selben Zweig
(`feature/nashville-scale-system`). Zweite Fassung: Die Notation ist nach
Diskussion von klassischer Stufentheorie auf ein echtes Nashville-System
umgestellt; die verworfenen Varianten sind unten dokumentiert. Die Idee steht
seit dem ersten Entwurf auf der Liste ([first-draft.md](first-draft.md),
„Nashville Number System").*

*Nachtrag (2026-08-24): Die Sektion hat inzwischen eine **dritte Karte
„Inverted"** (Stufe groß, Akkordname klein darüber — für Spieler, die in
Funktionen denken), und die Stufe steht auch an der **großen Akkordansicht**
(im Bass-Modus die des gemessenen Basstons). Ohne Tonart und bei `N`/`-`/`?`
bleibt der Name groß. Der Folgeausbau „Stufe am großen Akkord" aus dem
Abschnitt unten ist damit umgesetzt.*

---

## Die Idee

In der Zeitleiste unten steht über jedem Akkordnamen seine **Stufe** in der
erkannten Tonart: über `F` in B♭-Dur eine kleine `5`, über `Cm` eine `2`. Wer
mitspielt, denkt damit in Funktionen statt in absoluten Tönen — die Folge
`1–6–4–5` erkennt man nach zwei Durchgängen wieder, egal in welcher Tonart das
nächste Stück steht. Zusammen mit der Tonart (die im Badge oben ohnehin
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
  (`:626`) liefert die Tonklasse. Die Stufe ist dann die Halbton-Differenz
  `(NOTE_PC[root] − NOTE_PC[tonart.tonic] + 12) % 12`, nachgeschlagen in einer
  festen Tabelle (s. Umsetzungsplan).

---

## Darstellung

### Das System: eine Regel

**Arabische Ziffern, gezählt von der Dur-Skala der erkannten Tonika — auch in
Moll.** Eine nackte Ziffer heißt: Der Grundton liegt auf dieser Stufe der
Dur-Skala. Ein ♭ heißt: einen Halbton darunter. Mehr Regeln gibt es nicht.
Die zwölf möglichen Halbton-Abstände zur Tonika bilden ab auf:

```
0   1   2   3   4   5   6   7   8   9   10  11   Halbtöne über Tonika
1   ♭2  2   ♭3  3   4   ♭5  5   ♭6  6   ♭7  7    Stufe
```

- **Keine Qualitäts-Suffixe.** Kein Minus, kein `m`, kein `°`, keine `7` —
  ob der Akkord Dur, Moll oder vermindert ist, steht im Akkordnamen direkt
  darunter. `Am` in a-Moll zeigt schlicht `1`. Das echte Nashville-Charting
  braucht seine Minusse, weil das Chart den Akkordnamen *ersetzt*; bei uns
  ist die Stufe Zweitinformation *über* dem Namen.
- **Einheitlich ♭, nie ♯.** Kontextabhängige ♯-Schreibweisen (`♯4` lydisch,
  `♯1` als Durchgang) wären Deutungsentscheidungen; die feste ♭-Tabelle ist
  eine Regel ohne Urteil und deckt die häufigen Fälle (`♭3 ♭6 ♭7 ♭2`) in
  ihrer üblichen Schreibweise ab. Nachrüstbar, falls der Playtest widerspricht.
- **Jeder Grundton bekommt eine Stufe.** Es gibt keinen Blindfleck für
  tonartfremde Akkorde — das mixolydische `♭7` im Rock (G-Dur-Akkord in
  A-Dur) steht ganz regulär da, und genau das ♭ ist die nützliche Warnung
  „hier verlässt der Song die Tonart". Nur `N`, `-`, `?` bleiben ohne Stufe.
  Slash-Akkorde (`C/E`) beziehen die Stufe auf den Akkord-Grundton, nicht auf
  den Basston.

Ein Dur-Song zeigt damit im Normalfall gar keine Symbole — in B♭-Dur ist E♭
die nackte `4`, die Tonart macht klar, welcher Ton gemeint ist. Ein Moll-Song
sieht so aus (a-Moll):

| Akkord | Am | Bdim | C | Dm | E7 | F | G |
|---|---|---|---|---|---|---|---|
| Stufe | `1` | `2` | `♭3` | `4` | `5` | `♭6` | `♭7` |

Die Tonika ist auch in Moll die `1` — konsistent mit dem Badge („A minor" →
`Am` = `1`). Die verbreitete Session-Praxis, Moll-Songs in der Dur-Parallele
zu denken („ist in C, fängt auf der 6 an"), ist bewusst **nicht** übernommen:
Sie würde der eigenen Tonartanzeige widersprechen.

### Warum dieser Rahmen

Die Entscheidung fiel am Bass-Anwendungsfall. `♭3` trägt echte
Griffbrett-Information: ein fester Bund-Versatz zur Tonika, dieselbe
Geometrie in jeder Tonart — Moll als erniedrigte Dur-Skala ist genau der
Rahmen, in dem Griffbrett-Pädagogik und Jazz-Praxis denken („flat three",
„flat seven"). Eine skalenbezogene nackte `3` verlangt dagegen, dass der
Spieler die aktuelle Tonleiter (Dur *oder* Moll) präsent hat, um die Ziffer
in ein Intervall zu übersetzen. Dazu kommt: eine einzige Zählregel statt
zweier Rahmen, und kein Blindfleck bei entliehenen Akkorden.

### Verworfene Varianten

Beide Vorstufen dieses Entwurfs sind an derselben Frage gescheitert: *Was
muss die Stufenzeile leisten, wenn der volle Akkordname direkt darunter
steht?*

1. **Römische Ziffern mit Groß/Klein-Qualität** (`ii`, `V`, erste Fassung
   dieses Papiers). Hauptargument war, dass Groß/klein die Dur/Moll-Info
   „gratis" trägt — aber diese Info ist redundant, sie steht im Akkordnamen
   darunter. Übrig bleiben Kosten: bis zu drei Zeichen (`vii`), eine
   Lesekonvention, die man lernen muss, und Sonderfall-Logik (E7 in a-Moll
   als `V` statt `v` verlangt eine Qualitätsauswertung). Das zweite Argument
   — Verwechslungsgefahr nackter Ziffern mit Bundzahlen — war überbewertet:
   Bundzahlen erscheinen im Diagramm oben links, nicht im Laufband; eine
   kleine gedeckte Ziffer direkt über einem Akkordnamen hat genug Kontext.
2. **Nackte Ziffern relativ zur jeweiligen Skala** (in Moll von der
   Moll-Tonleiter gezählt: C in a-Moll = `3`). Vermeidet jedes Vorzeichen und
   lässt Schrittbewegung als Nachbar-Ziffern erscheinen (`1–7–6–5` statt
   `1–♭7–♭6–5`) — aber sie braucht zwei Zählrahmen, lässt tonartfremde
   Grundtöne zwangsläufig leer und entkoppelt die Ziffer vom
   Griffbrett-Intervall. Der ursprüngliche Wunsch „keine ♭-Symbole" hat sich
   in der Diskussion präzisiert: keine *redundanten* Symbole. Das ♭ der
   Nashville-Zählung ist nicht redundant — es trägt den Bund-Versatz.

### Layout im Chip

Über dem Grundton, **linksbündig auf derselben Kante** — die linke Textkante
markiert im Laufband den Zeitpunkt (Kommentar `index.html:236-238`), die Stufe
muss dieselbe Kante halten, sonst lügt sie über das Timing. Zwischen
Lane-Oberkante und Akkord-Glyphe sind ~4–5 vh frei; das reicht für eine Zeile
in ~2.2 vh, gedeckt gefärbt wie die `.eta`-Zeile darunter (`#4a5158`-Familie),
damit die Hierarchie stimmt: Akkordname laut, Stufe und Countdown leise.

```
  4                 5
  E♭maj7            F
  in 2.3s           in 6.1s
──────┼──────────────────────────  ← NOW-Linie
```

Solange `tonart == null` (erste ~12 s), erscheinen schlicht keine Stufen —
dasselbe ehrliche Verhalten wie beim Tonart-Badge und der automatischen
Schreibweise.

Ein Fall ist vorab im `?demo`-Modus zu prüfen: eine Stufen-`7` über einem
Akkord, der selbst eine `7` im Namen trägt (`G7`). Falls das irritiert, ist
es eine Styling-Frage (Größe, Farbe, Abstand), keine Notationsfrage.

*Offen (Folgeausbau, nicht Teil dieses Zweigs):* dieselbe Stufe klein am
großen aktuellen Akkord (`#current`) und im Keyboard-/Gitarrenmodus. Erst der
Playtest in der Zeitleiste zeigt, ob das mehr hilft als unruhig macht.

---

## Einstellungsdialog klein halten

Der Dialog ist eine einzige Spalte aus Sektionen; jede neue Sektion kostet
Scrollweg. Entscheidung: **genau eine neue Sektion mit genau zwei Karten** —
An/Aus. Alles andere ist Designentscheidung statt Einstellung:

- keine Notations-Wahl (Nashville-Ziffern sind gesetzt, s. o.),
- keine Tonart-Übersteuerung (die Tonart kommt aus der Erkennung; eine
  manuelle Tonartwahl wäre ein eigenes Feature mit eigenem Papier),
- keine Vorzeichen-Optionen (die ♭-Regel ist fest).

Vorschlag für die Sektion (nutzersichtbar Englisch, wie alles im Dialog):

> **Scale degrees**
> *Nashville-style numbers above each chord in the timeline: 1 is the key's
> root, 5 its fifth, a ♭ marks roots outside the key's major scale. A
> progression looks the same in every key — shown once the key is settled.*
>
> **Shown** — Numbers above the timeline chords. `[an]`
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
   dem man den Fehler lautlos einbaut. (Ein reiner Dur/Moll-Wechsel bei
   gleicher Tonika ist dagegen egal — die Zählung hängt nur an der Tonika.)
2. **Tonart-Konfidenz.** Der `KeyEstimator` wechselt träge
   (`SWITCH_MARGIN`), das dämpft Stufen-Flackern von allein. Keine eigene
   Hysterese in der Anzeige einbauen, bevor ein Realaudio-Test zeigt, dass es
   nötig ist.
3. **Moll-Songs sind der Playtest-Fall.** Dort tragen drei der sieben
   leitereigenen Akkorde dauerhaft ein ♭ (`♭3 ♭6 ♭7`) — ob das im Laufband
   ruhig genug bleibt, entscheidet eine echte Bass-Session mit einem
   Moll-Stück, nicht dieses Papier.

---

## Umsetzungsplan

1. `index.html`: `stufeVon(name)` → `"4"` / `"♭3"` / `null`. Die Stufe hängt
   **nur am Grundton** — die Qualitätsauswertung aus der ersten Fassung
   (Groß/klein nach Terz) ist ersatzlos entfallen. Damit reicht:
   Grundton abtrennen wie in `fmtChord` (`:528`), Slash-Bass abschneiden wie
   `_parse` in [control_guitar.py](../../jampilot/control_guitar.py) (`:38`,
   `.split("/")[0]`), Halbton-Differenz zur Tonika bilden und in der festen
   Zwölfer-Tabelle `["1","♭2","2","♭3","3","4","♭5","5","♭6","6","♭7","7"]`
   nachschlagen. Aufruf in `chipHtml`, neue Zeile `<span class="degree">` mit
   CSS analog `.eta`.
2. Chip-Key bzw. Rebuild um die Tonika erweitern (Stolperstein 1);
   `apply(state)` löst bei Tonika-Wechsel `neuSchreibenFallsNoetig` aus.
3. Dialog-Sektion + `setzeStufen(an)` nach dem Muster von `setzeGriffbrett`,
   Schlüssel `jampilot.degrees`, Verkabelung im `.opt`-Dispatcher und im
   Startup-Block (`:1469`).
4. Tests: `tests/test_web.py::TestSeite` um String-Assertions für die neue
   Sektion und den Schlüssel erweitern (Muster: Fretboard-Toggle, `:116`).
5. Visuelle Iteration über `?demo` (`index.html:1474`) — die Demo spielt
   F-Dur, Tonart kommt nach 8 s: exakt der Fall „Stufen erscheinen später".
   Für den ♭-Fall die Demo-Progression um einen entliehenen Akkord (`E♭` in
   F-Dur = `♭7`) ergänzen oder ein Moll-Stück laden.

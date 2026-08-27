# JamPilot — Technisches Design

Überblick über die Signalkette der Akkorderkennung: was JamPilot pro Zeitfenster
tut, welche Begriffe was bedeuten, und wo die bewussten Grenzen liegen. Gedacht
als Referenz beim Weiterentwickeln — jeder Abschnitt verweist auf den Code, der
die Aussage trägt.

Stand: 2026-07-17. Bei Änderungen an Fenstergrößen, Akkordtypen oder Prior bitte
hier mitziehen.

> **Veraltet (2026-08-08):** Dieses Dokument beschreibt den
> Template-Matching-Pfad, der seit dem Umbau auf das BTC-Modell stillgelegt
> ist (er liegt weiter in `_display_loop_template` / `_cmd_analyze_template`).
> Überblick über den aktuellen Stand und die Gründe des Umstiegs:
> [../HOW-IT-WORKS.de.md](../HOW-IT-WORKS.de.md) (englisch:
> [../HOW-IT-WORKS.md](../HOW-IT-WORKS.md)). Die Abschnitte zu Zeitrastern,
> Chroma und Bassmessung gelten sinngemäß weiter.

---

## 1. Die Signalkette in einem Satz

Live-Audio läuft mit **~5 s Verzögerung** durch. In diesem Puffer wird alle
**250 ms** ein **1,5-s-Fenster** analysiert: daraus entsteht ein **Chroma**
(12 Tonklassen-Energien), das gegen **5 Akkord-Schablonen** gematcht wird; ein
**Tonart-Prior** ordnet knappe Lesarten, und **sichere Tonmengen** entscheiden,
was dem Spieler zum Mitgreifen empfohlen wird.

## 2. Die drei Zeitraster (nicht verwechseln)

Das häufigste Missverständnis: „wir lösen in 250-ms-Fenstern auf". Falsch — es
gibt **drei** verschiedene Zeitskalen mit verschiedenen Aufgaben:

| Raster | Wert | Konstante | Aufgabe |
|---|---|---|---|
| **Ausgabeverzögerung** | 5,0 s (Default) | `--delay` ([cli.py:623](../jampilot/cli.py#L623)) | Vorlauf, damit der Akkord *vor* dem Ton angezeigt werden kann |
| **Analysefenster** | 1,5 s | `ANALYSIS_WINDOW` ([cli.py:27](../jampilot/cli.py#L27)) | **Wie viel Klang** jede Analyse sieht — bestimmt *welcher* Akkord |
| **Hop (Analysetakt)** | 250 ms | `ANALYSIS_HOP` ([cli.py:28](../jampilot/cli.py#L28)) | **Wie oft** wir neu hinschauen — die Fenster überlappen um 1,25 s |
| **CQT-Frame** | ~23 ms | `FRAME_SECONDS` ([chroma.py:34](../jampilot/chroma.py#L34)) | **Wann** ein Wechsel einsetzt (Onset), nicht *welcher* Akkord |

Kernpunkt: Ein Akkord braucht **~1,5 s Klang**, um sicher erkannt zu werden. Die
250 ms sagen nur, wie oft wir eine frische, stark überlappende 1,5-s-Sicht ziehen.
Das feinste Raster (~23 ms) dient allein der Onset-Lokalisierung, damit die
Anzeige nicht um einen halben Analysetakt springt.

## 3. Was ein Chroma ist

Ein **Chroma ist ein 12-Werte-Vektor — ein Eintrag je Tonklasse** (C, C#, D, …,
B). Er **faltet alle Oktaven zusammen**: ein C in jeder Lage landet im selben
„C"-Topf. Das Chroma beantwortet *„wie viel Energie steckt gerade in jeder der
12 Noten"* — die Oktave wird bewusst verworfen, weil für den Akkord**namen** egal
ist, in welcher Lage ein Ton klingt.

Berechnung in [chroma.py](../jampilot/chroma.py), Standardpfad `analyze_window`:

1. Resampling auf `ANALYSIS_SR = 22050 Hz` ([chroma.py:27](../jampilot/chroma.py#L27)).
2. **HPSS** (harmonisch/perkussiv): das perkussive Signal (Schlagzeug) wird
   entfernt, nur der tonale Anteil geht weiter ([chroma.py:137](../jampilot/chroma.py#L137)).
3. **Constant-Q-Chroma**: logarithmische Frequenzachse, trifft auch tiefe
   Grundtöne; 36 Bins/Oktave ([chroma.py:101](../jampilot/chroma.py#L101)).
4. **Pooling**: Median über die *jüngere* Fensterhälfte — robust gegen Ausreißer,
   reagiert trotzdem auf Wechsel im Fenster ([chroma.py:111](../jampilot/chroma.py#L111)).
5. Normierung auf Summe 1.

Bei C-Dur sind danach die Töpfe C, E, G groß und der Rest klein. Ohne librosa
greift ein leichter FFT-Fallback (`chroma_from_audio`) mit gröberem Ergebnis.

Nebenprodukte derselben Analyse ([chroma.py:42](../jampilot/chroma.py#L42)):
das **Bass-Chroma** (Tiefband C1..~260 Hz, für die Bassnote), die **Frame-Chromas**
(für Onset und Bassnote) — sie fallen ohnehin an und werden aufgehoben statt
weggemittelt.

## 4. Akkordtypen: es gibt genau fünf — und „5" ist keiner davon

Der Matcher `match_chord` kennt **fünf Schablonen** ([chords.py:10](../jampilot/chords.py#L10)):

| Suffix | Intervalle | Bedeutung |
|---|---|---|
| `` (leer) | 0, 4, 7 | Dur |
| `m` | 0, 3, 7 | Moll |
| `7` | 0, 4, 7, 10 | Dominantseptakkord |
| `maj7` | 0, 4, 7, 11 | großer Septakkord |
| `m7` | 0, 3, 7, 10 | Mollseptakkord |

Er vergleicht das Chroma per Cosinus-Ähnlichkeit mit jeder Schablone auf jedem
der 12 Grundtöne; unter `MATCH_THRESHOLD` gilt der Klang als „kein Akkord".
Vierklänge müssen die Triade um eine **Komplexitätsmarge** schlagen, weil
Obertöne scheinbare Septimen erzeugen ([chords.py:21](../jampilot/chords.py#L21)).

**Der Powerchord („5", ohne Terz) ist kein erkannter Akkordtyp.** Er entsteht
eine Stufe später in `safe_pitch_classes` ([harmony.py:76](../jampilot/harmony.py#L76)):
Sind sich zwei fast gleich gute Lesarten *desselben Grundtons* uneinig, ob die
Terz **groß oder klein** ist (A vs. Am), wird die Terz **weggelassen**. Das ist
keine Erkennung eines 5-Akkords, sondern eine **ehrliche Verweigerung** — „die
Terz ist unsicher, greif sie nicht mit". Gesteuert über `SAFE_AUDIO_DISTANCE`
([harmony.py:20](../jampilot/harmony.py#L20)).

## 5. Warum aus dem vollen Mix analysiert wird — und wo die Grenze liegt

Es wird **nicht quellengetrennt**, aber auch nicht roh: HPSS entfernt Perkussion,
das Band ist begrenzt (~55–2000 Hz). Alles **harmonische** Material — Gitarre,
Keyboard, **Gesang**, Bass — landet gemeinsam im Chroma.

### Bass: Trennung per Frequenzband (gratis)

Die Bassnote wird aus dem **Tiefband** gewonnen (C1..~260 Hz,
[chroma.py:140](../jampilot/chroma.py#L140)). Der Bass wohnt dort weitgehend
allein — das Frequenzband **isoliert ihn ohne Quellentrennung**. Deshalb ist der
volle Mix für den Bass kein Problem. (Der frühere `BASS_BONUS` im Matching wurde
verworfen, weil er bei Umkehrungen den Grundton fälschlich auf die Bassnote zog;
die Bassnote läuft jetzt **neben** der Akkorderkennung, siehe
[chords.py:28](../jampilot/chords.py#L28).)

### Gitarre/Keyboard: Gesang ist ein echtes Problem — der Bass-Trick greift nicht

Das Bass-Argument **überträgt sich nicht** auf die Akkorderkennung:

| | Bass | Gitarre / Keyboard |
|---|---|---|
| Wohnt in | eigenem Tiefband | **demselben Mittenband wie der Gesang** |
| Per Frequenz trennbar? | ✓ ja, gratis | ✗ nein — überlappt mit der Stimme |
| Gesang stört? | kaum | **ja, real** |

Der Akkord und die Singstimme teilen sich denselben Frequenzbereich. HPSS hilft
**nicht**, weil Gesang harmonisch ist (HPSS behält ihn). Eine gehaltene
Melodienote auf einem Nicht-Akkordton (Vorhalt, Blue Note) verzieht das Chroma
direkt. Was uns teilweise rettet: der Akkord hat 3–4 **gehaltene** Töne, der
Gesang nur **eine wandernde** — der Median über 1,5 s dämpft die Stimme etwas,
aber gehaltene Vokalnoten mogeln sich durch.

**Offener Hebel:** echte Gesangstrennung (Demucs/Spleeter) wäre sauberer, kostet
aber ML-Latenz/Rechenlast und beißt sich mit dem Echtzeitbudget. Noch nicht
gemessen, ob sich der Aufwand lohnt.

## 6. Tonart-Prior — kein Progressionsmodell

JamPilot **beschreibt keine Akkordfolgen.** Es macht etwas Bescheideneres:

- **Tonartschätzung** (`KeyEstimator`, [tonality.py](../jampilot/tonality.py)):
  rollendes Fenster mit 30-s-Halbwertszeit, Krumhansl-artige Tonprofile. Ergebnis:
  Grundton + Dur/Moll + Konfidenz.
- **Skalen-Prior** (`interpret_chord`, [harmony.py:41](../jampilot/harmony.py#L41)):
  Bei zwei fast gleich guten Lesarten *desselben Grundtons* bevorzugt der Prior
  die leitereigene (A↔Am, 7↔maj7). Er korrigiert **nur die Qualität, nie den
  Grundton**, und nur innerhalb `MAX_AUDIO_DISTANCE` — starke Audioevidenz
  überstimmt ihn immer. Bei unsicherer Tonart schrumpft der Prior automatisch.

Der Prior wirkt also praktisch als **Moll/Dur- bzw. 7/maj7-Entscheider** — aber
auf Basis der **Skalenzugehörigkeit**, nicht einer Akkordfolge. Es gibt kein
Modell von „auf X folgt gern Y".

### Bewusste Grenze: keine Auflösung, keine Zwischendominanten

Genau dieses fehlende Progressionsmodell ist eine harte Grenze. Eine
**Zwischendominante** (z. B. `E7` als V/ii in G-Dur, Peg) erkennt man erst an der
**Auflösung** (E7→Am) — also an der Folge, die der Prior nicht betrachtet. Ein
naheliegender statischer Fix (E7 straffrei, wenn das Quint-abwärts-Ziel
leitereigen ist) wurde gebaut, an Realaudio gemessen und **verworfen**: er kippt
im Gegenzug die diatonische vi (F#m in A-Dur, Sting) in einen Dominantseptakkord,
weil beide auf dem 6. Skalengrad sitzen und derselbe Prior sie nicht trennen
kann. Details: [tests/realaudio/REPORT_secondary_dominant_fix.md](../tests/realaudio/REPORT_secondary_dominant_fix.md).
Ein echter Fix gehört in eine Progressions-/Root-Motion-Schicht über zwei
Fenster, nicht in den fensterlokalen Skalen-Prior.

## 7. Onset: wann der Wechsel angezeigt wird

Steht ein neuer Akkord fest, sucht `_locate_onset` ([cli.py:496](../jampilot/cli.py#L496))
im aufbewahrten Frame-Chroma (`FrameHistory`, [chroma.py:147](../jampilot/chroma.py#L147))
rückwärts den tatsächlichen Einsatzpunkt — auf ~23 ms genau, statt ihn aus dem
Analysetakt zu schätzen. Der Fehler ist einseitig: die Anzeige kommt eher zu spät
als zu früh (siehe Kommentar in [chroma.py:147](../jampilot/chroma.py#L147)).

## 8. Signalfluss kompakt

```
Mikrofon
  │  (5 s Puffer, DelayedLoopback)
  ▼
alle 250 ms ein 1,5-s-Fenster
  ▼
analyze_window                      → Chroma (12), Bass-Chroma, Frame-Chromas
  ▼
match_chord (5 Schablonen)          → roher Akkordkandidat + Alternativen
  ▼
interpret_chord (Tonart-Prior)      → Qualität geschärft (A↔Am, 7↔maj7)
  │        ▲
  │        └── KeyEstimator (rollende Tonart, 30-s-Halbwertszeit)
  ▼
safe_pitch_classes                  → sichere Tonmenge (Terz/Septime ggf. raus → „X5")
  ▼
Onset-Suche (Frame-Chroma)          → genauer Einsatzzeitpunkt
  ▼
Anzeige / Kontrollgitarre / Bassnote
```

## 9. Offene Hebel (Stand 2026-07-17)

- **maj7-Bias** — dokumentierte Top-Schwäche über alle Realaudio-Tests: `7` wird
  oft als `maj7` gelabelt. Der Tonart-Prior hat ihn gedämpft, aber Matcher-Ebene
  ist ungeprüft.
- **Gesangstrennung** — §5: real messbarer Störer für Gitarre/Keyboard, Nutzen
  gegen Echtzeitkosten noch nicht gemessen.
- **Progressionsschicht** — §6: Voraussetzung für Zwischendominanten und andere
  folgenabhängige Korrekturen.
- **X5-Dosis** — Schwellwert `SAFE_AUDIO_DISTANCE` ist eine Spielgefühl-, keine
  Messfrage; am Instrument zu beurteilen.

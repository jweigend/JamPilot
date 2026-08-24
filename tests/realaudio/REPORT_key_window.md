# Experiment-Report: Größeres Fenster für die Tonarterkennung

**Frage:** Die Tonarterkennung produziert zu viele Sprünge und Fehler — sichtbar
geworden durch die Nashville-Stufen, die an der Tonika hängen. Hilft ein
größerer Analysehorizont, nur für die Tonart?
**Datum:** 2026-08-24
**Zweig:** `feature/nashville-scale-system`
**Status:** Umgesetzt im selben Zweig: `TwoScaleKeyEstimator` in tonality.py
(120-s-Histogramm + Modulationsdetektor + Stille-Reset), verkabelt im
BTC-Live-Pfad. Die Produktionsklasse reproduziert die Benchmark-Zahlen
exakt (4 Tonika-Sprünge, 77,9 %, Latenzen 47/55/53 s); einzige Abweichung:
die synthetische Doppelmodulation in Crazy Little Thing endet 2 s vor der
Schlussausblendung und fällt nun der Stille-Erkennung zum Opfer
(Randeffekt der Synthetik, kein realer Fall). Template-Pfad
(`_display_loop_template`) bewusst unverändert: dort speist die Tonart den
Akkord-Prior, dieses Zusammenspiel ist nicht mitgemessen.

**Vorab eine Klarstellung:** Die Tonart hängt nicht am 4-s-Delay oder am
10-s-BTC-Fenster. Der `KeyEstimator` (tonality.py) sammelt ein
Tonklassen-Histogramm über das ganze Stück mit exponentiellem Verfall —
`KEY_HALF_LIFE = 30 s` IST der Analysehorizont. „Größeres Fenster" heißt
hier also: längere Halbwertszeit. Genau das wurde variiert.

## Setup

Live-Fütterung repliziert (`_display_loop`: BTC-Log-CQT → `fold_chroma` →
Mittel der neuen Frames je 0,25-s-Hop → `KeyEstimator.add`), Halbwertszeit
∈ {30 s (Ist), 60, 120, 240, ∞}; `MIN_KEY_SECONDS` und `SWITCH_MARGIN`
unverändert. 9 Tracks: die vier Realaudio-WAVs plus die fünf
Referenz-Songs aus `tests/reference`. Gemessen wird, was die Stufen
umschreibt: **Tonika-Sprünge** nach der ersten Meldung (ein Dur/Moll-Flip
bei gleicher Tonika ändert keine Stufe) und der zeitgewichtete Anteil
akzeptierter Tonika. Skript: Session-Scratchpad
`key_window_experiment.py`.

## Ergebnis: Das größere Fenster wirkt stark

| Halbwertszeit | Tonika-Sprünge (Summe, 9 Tracks) | Tonika korrekt (Mittel) |
|---|---|---|
| 30 s (Ist) | **27** | 65,6 % |
| 60 s | 13 | 70,3 % |
| **120 s** | **4** | **77,9 %** |
| 240 s | 4 | 78,2 % |
| ∞ | 3 | 78,6 % |

Einzelbefunde bei 120 s gegen Ist:

- **Peg** (G-Dur): 6 Sprünge → 1 (nur der Einschwinger `D→G` bei 19 s bleibt), 79 → 97 % korrekt.
- **Sting Faith** (A-Dur): 5 → 1, 65 → 94 %. Das `E`/`C#m`-Gewander ab Minute 2 verschwindet.
- **Misty2** (E♭): 4 → 0, das `E♭↔Cm`-Pendeln (Parallel-Moll!) ist weg, 100 % korrekt.
- **Crazy Little Thing** (D): 4 → 0, statt `Em/Dm/A`-Irrfahrt durchgehend D, 48 → 100 %.
- **It's Too Late** (a-dorisch/F): der A↔Am-Flip verschwindet, durchgehend Tonika A.
- Kein Modulations-Schaden im Set: Die Bridge von *Something* (A-Dur) erkennt
  auch das 30-s-Fenster nie; verloren geht also nichts, was heute da wäre.

Ab 120 s ist der Gewinn ausgereizt — 240 s und ∞ bringen nichts mehr.

**Gegenprobe Hysterese:** Dieselbe Beruhigung über `SWITCH_MARGIN` statt
Fenster (0,10 / 0,15 bei 30 s) erreicht nur 17 bzw. 10 Sprünge und *senkt*
die Trefferquote (Fehl-Tonarten werden festgenagelt, Minimum fällt auf 0 %).
Das Fenster ist der richtige Hebel, nicht die Hysterese.

## Was das Fenster NICHT heilt

Zwei Tracks scheitern in **jeder** Konfiguration — selbst mit dem ganzen
Stück im Histogramm gewinnt die falsche Tonart:

- **Eight Days a Week** (D-Dur): Krumhansl kürt E-Dur (r=0,62) vor A, Bm,
  dann erst D (r=0,52). Das Roh-Chroma ist verschmiert (A#/G# prominent im
  Histogramm — `fold_chroma` faltet ohne HPSS/Tuning).
- **Misty/Garner** (E♭): c-Moll gewinnt klar (r=0,75 gegen 0,59) — die
  klassische Parallel-Moll-Ambiguität bei Jazz-Voicings.

Das ist ein **Signalproblem, kein Fensterproblem** — und die eine Kehrseite
des großen Fensters: Wo das Signal falsch liegt, wird der Fehler dauerhaft
(Misty/Garner fand mit 30 s bei Sekunde 158 noch zu E♭; mit 120 s nie).

**Ausblick Signalqualität:** Ein Histogramm aus den BTC-*Akkordlabels*
statt rohem Chroma (Akkordtöne je Frame, Grundton doppelt) trifft 7/9
Tonarten, repariert Eight Days (D r=0,87) und rückt Misty/Garner näher
(A♭ statt Cm) — verliert dafür Sting an die Ambiguität D/A (Strophe
`A|G|D`). Kein Dominator, aber als Zusatzsignal/Re-Ranker vielversprechend;
eigenes Experiment, falls die 120-s-Restfehler im Playtest stören.

## Kehrseite für den Live-Betrieb: Songwechsel

Der `KeyEstimator` lebt pro Session, nicht pro Song. Wer ein Album/eine
Playlist durchspielt, bekommt beim nächsten Song mit 120 s Halbwertszeit
minutenlang die alte Tonart angezeigt (heute: ~1 min). Der passende
Begleiter zum größeren Fenster ist deshalb ein **Histogramm-Reset nach
Stille** (Songlücke ≈ 1–2 s Quasi-Stille; `add` wird heute auch mit
Rauschteppich gefüttert, der `total < 1e-9`-Guard greift nie). Danach gilt
wieder `MIN_KEY_SECONDS` — ehrliches „noch keine Tonart" statt falscher
Alt-Tonart.

## Nachtrag: Modulationen mitten im Song (die Kehrseite, gemessen)

Einwand aus der Diskussion: Viele Pop-Songs modulieren bewusst — gern auch
zweimal einen Halbton nach oben. Sieht ein 120-s-Fenster das erst nach zwei
Minuten? **Gemessen: ja, oder nie.** Synthetische Modulation (Chroma ab
Sekunde 100 um +1 HT gerollt; Pop-Fall: +1 bei 90 s, nochmal +1 bei 120 s):

| Latenz +1 HT @100 s | 30 s (Ist) | 120 s | Zwei-Skalen (s. u.) |
|---|---|---|---|
| Let It Be | 42 s | 111 s | 47 s |
| Peg | **nie** | nie | 55 s |
| Crazy Little Thing | 40 s | nie | 53 s |
| Misty2 | nie | nie | nie |

Beim Doppel-Halbton (Latenz ab der zweiten Stufe) dasselbe Bild: Ist 17–36 s
bzw. nie, pures 120-s-Fenster 77 s bis nie, Zwei-Skalen 35–44 s. Bemerkenswert:
**Auch das heutige 30-s-Fenster verpasst zwei der vier Fälle komplett** — ein
einzelner Zeithorizont ist lose-lose (kurz = flackert und verpasst trotzdem,
lang = ruhig, aber modulationsblind).

**Ausweg: zwei Zeitskalen.** Langes Histogramm (120 s) bestimmt die Tonart;
ein kurzes (Halbwertszeit 25 s) dient nur als Modulationsdetektor: Liegt dort
dieselbe fremde Tonika 15 s lang mit deutlichem Korrelationsvorsprung
(> 0,20) vor der amtierenden (inkl. deren Parallel-Lesart), wird das lange
Histogramm durch das kurze ersetzt. Der große Gap ist der Diskriminator:
Nach echter Modulation korreliert die neue Tonart ~0,9 gegen ~0,3 der alten;
bloße Ambiguität (mixolydische Strophe in Sting, Parallel-Moll in Misty2,
verrauschte Strophe in Crazy Little Thing) kommt nie über ~0,15. Ein erster
Versuch mit einem 10-s-Detektor und kleinem Gap (0,08–0,12) ist genau daran
gescheitert: Fehl-Resets auf Something/Crazy/Sting fraßen den Stabilitätsgewinn
wieder auf.

Ergebnis der Kombination (short=25 s, gap=0,20, sustain=15 s): **identische
Stabilität wie pures 120 s** auf allen 9 echten Tracks (4 Tonika-Sprünge,
77,9 %, null Fehl-Resets) **und** Modulationslatenz 35–55 s — gleichauf bis
besser als das heutige 30-s-Fenster, das dabei 27-mal springt. Der
Misty2-Modulationsfall bleibt für alle Varianten unsichtbar
(Jazz-Chroma-Schmiere, siehe Signalproblem oben). Parameter sind auf diesem
Set getunt; das Plateau über drei Kombinationen (gap 0,20–0,30, sustain
15–20 s) spricht gegen scharfes Overfitting. Prototyp:
Session-Scratchpad `two_scale.py`.

Der Stille-Reset bleibt trotzdem sinnvoll: Der Detektor fängt einen
Songwechsel zwar auch (~40 s), die Stille-Heuristik ist aber schneller und
stellt ehrlich auf „noch keine Tonart" zurück statt hart umzuschalten.

## Empfehlung

1. **Zwei-Skalen-Estimator** statt nur `KEY_HALF_LIFE`-Erhöhung: langes
   Histogramm 120 s, Detektor 25 s / gap 0,20 / sustain 15 s (s. Nachtrag —
   die reine 120-s-Variante wäre modulationsblind). Wirkt nur auf den
   Live-Pfad und dort nur auf die Anzeige: Badge, Schreibweise, Stufen
   (`analyze` läuft schon ohne Verfall, der Akkord-Prior ist im BTC-Pfad
   stillgelegt).
2. Dazu im selben Schritt den Stille-Reset (sonst kauft man die Ruhe im
   Song mit Trägheit beim Songwechsel).
3. Danach der ohnehin offene Instrument-Playtest der Nashville-Stufen —
   die zwei verbleibenden Fehlerklassen (Chroma-Schmiere, Parallel-Moll)
   erst angehen, wenn sie dort wirklich stören.

**Grenzen der Messung:** Chroma aus einem Lauf über die ganze Datei statt
gleitender 10-s-Fenster (Randeffekte minimal anders); Referenzset
in-domain-lastig (vgl. REPORT über BTC-Genre-Sensitivität — für stilferne
Musik sind die Prozentzahlen optimistisch, die *Relation* zwischen den
Fenstern sollte halten).

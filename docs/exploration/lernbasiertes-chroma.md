# Lernbasiertes Chroma: bessere Vorderseite, in zwei Phasen

*Explorationsdokument. Status: These mit Bestandsaufnahme und Messplan. Kein
Implementierungsplan — eine Entscheidungsgrundlage.*

Vorwissen: [../technical-design.md](../technical-design.md) (was Chroma, Matcher
und Prior heute tun) und [harmonischer-interpreter.md](harmonischer-interpreter.md)
(warum die *Rückseite* — der Interpreter — der eigentlich unbesetzte Teil ist).
Dieses Dokument betrifft die **Vorderseite**: den Schritt Audio → 12-Tonklassen.

---

## Die These

Unser Chroma ([chroma.py](../../jampilot/chroma.py)) ist ein solider klassischer
Baseline — CQT + HPSS + Median-Pooling — aber nicht Stand der Technik. Zwei
Schwächen sind dokumentiert und beide sitzen **im Chroma, nicht im Matcher**:

- **Obertöne erzeugen scheinbare Septimen** → der maj7-Bias (Top-Schwäche über
  alle Realaudio-Tests). Wir bekämpfen das heute mit einem Hack
  (`COMPLEXITY_PENALTY`, [chords.py:21](../../jampilot/chords.py#L21)), nicht an
  der Wurzel.
- **Gesang liegt im selben Band wie der Akkord** und lässt sich — anders als der
  Bass — nicht per Frequenz heraustrennen ([technical-design.md §5](../technical-design.md)).

Die Vorderseite ist also verbesserbar, und zwar ohne die Rückseite anzufassen:
`match_chord`, `interpret_chord`, `safe_pitch_classes` und die Onset-Suche hängen
nur an einem *sauberen 12-d-Vektor*. Tauscht man den Erzeuger dieses Vektors aus,
bleibt der Rest gültig.

## Ergebnis vorweg

- **Phase 1 ist gemessen und abgeschlossen:** Extraktor tauschen, Rest lassen,
  gegen die Realaudio-Kette messen. Ergebnis (2026-07-17): CENS schlechter, ein
  selbst gebautes NNLS senkt den maj7-Bias auf 3/4 Files bei vernachlässigbarer
  Latenz — aber kein sauberer Gewinn. **Verdikt: weiter am Chroma frickeln lohnt
  nicht;** der eine Punkt, der half, war der *gelernte* Mechanismus, nicht das
  Tuning. Das zeigt auf Phase 2.
- **Phase 2 ist der eigentliche Weg — synthetisch angelernt, real geerdet:** ein
  Modell, das Audio direkt auf den **Griff inkl. Leersaiten** abbildet. Erst ein
  **synthetischer Korpus** (Bass/Drums-Kreuz, diverse Gitarrentypen) mit perfekter,
  gratis Wahrheit für den 90-%-Startstand; dann **Finetuning auf echten Aufnahmen**.
  Die zwei make-or-break-Stellen: der **Synth→Real-Graben** und die
  **Transkriptionsqualität** echter Labels (falsch/unvollständig/vereinfacht).
- **Eine Leitplanke bindet beides:** JamPilots Stärken (Onset auf ~23 ms,
  Unsicherheit → Powerchord, getrennte Bassnote) leben von den *Zwischenschichten*.
  Ein reines Label-Modell zerstört sie. Die Vorderseite darf gelernt werden — sie
  muss aber weiter **Voicing/Chroma + Konfidenzen** liefern, keine fertigen Labels.

---

# Phase 1 — Vorderseite tauschen und messen

## Das Vorgehen

Genau ein Baustein wird ersetzt: `analyze_window` liefert statt des CQT-Chromas
einen fremd erzeugten 12-d-Vektor. `match_chord` und alles danach bleibt Byte für
Byte gleich. Damit ist es ein sauberes A/B: jeder Unterschied im Ergebnis kommt
aus dem Chroma.

## Die Kandidaten (nach Aufwand/Ertrag)

| Extraktor | Angriff auf | Art | Aufwand |
|---|---|---|---|
| **NNLS-Chroma / Chordino** (Mauch) | Obertöne → maj7 | DSP-Dekonvolution gegen Ton+Oberton-Profile | mittel (Vamp-Port/Bindung) |
| **madmom `DeepChromaProcessor`** | Obertöne, Rauschen, z.T. Gesang | vortrainiertes CNN, CPU-tauglich | mittel (Dependency) |
| **CREMA** (McFee) | dito | vortrainiertes CNN | mittel |
| **Bass-Chroma ins Matching (→ 24-d)** | Umkehrungen/Slash | wir berechnen es längst ([chroma.py:140](../../jampilot/chroma.py#L140)) | niedrig |

Die ersten drei sind **vortrainiert** — kein eigenes Training nötig, um sie zu
probieren. NNLS ist der prinzipiellste Angriff auf den maj7-Bias (Obertöne per
Dekonvolution weg, statt per Strafmarge im Matcher). Der 24-d-Schritt ist fast
gratis, weil die Bass-Hälfte schon anfällt — nur nutzen wir sie heute separat für
die Bassnote statt fürs Matching.

## Wie gemessen wird

Die Messkette existiert bereits (Realaudio-Reports, `evaluate.py`-Muster):
Chromas einmal pro Datei cachen, dann Alt gegen Neu über dieselben vier
Aufnahmen. Erfolgskriterien — dieselben wie bei den bisherigen Fixes:

1. **Invariante:** Grundton darf sich nicht verschlechtern (0 unbegründete
   Root-Wechsel bleibt die Messlatte).
2. **maj7-Anteil** sinkt (der eigentliche Zielwert).
3. **Skalenfremde Fenster** relativ zur Ganzdatei-Tonart sinken.
4. **Dokumentierte Einzelfehler** (Dmaj7-Streuung in Peg, Amaj7-Tonika in Sting,
   Ebmaj7-statt-Eb7 in Misty) werden real getroffen.

## Die zwei Vorbehalte, die zuerst zu klären sind

- **Echtzeitbudget.** Alles muss im 250-ms-Takt bei 4 s Puffer durchlaufen. Vor
  jeder inhaltlichen Messung: läuft der Extraktor überhaupt schnell genug? madmom
  DeepChroma und CREMA gelten als CPU-tauglich; das ist *zu verifizieren*, nicht
  zu glauben.
- **Kalibrierung wandert mit.** Die Komplexitätsmargen ([chords.py:25](../../jampilot/chords.py#L25))
  und `SAFE_AUDIO_DISTANCE` sind auf das *jetzige* Chroma kalibriert. Ein
  saubereres Chroma verschiebt die Score-Abstände — die Margen müssen neu
  gesweept werden, sonst misst man den Extraktor mit falscher Brille.

## Phase-1-Ausgang

Entweder ein Extraktor schlägt den Baseline messbar auf den vier Kriterien (dann
Dependency-/Latenzkosten gegen den Gewinn abwägen), oder keiner tut es (dann ist
der Baseline bestätigt und Phase 2 wird die eigentliche Antwort). Beides ist ein
verwertbares Ergebnis.

## Phase-1-Befund (gemessen 2026-07-17)

Ein erster Durchlauf ist gelaufen — `base` (heute) vs. librosa **CENS** vs. ein
selbst gebautes **NNLS**-Chroma (Obertonbereinigung nach Mauchs Prinzip, per
`scipy.optimize.nnls`), gemessen auf allen vier Aufnahmen. Zielwert: `maj7`-Anteil.

| Datei | base | CENS | NNLS |
|---|---|---|---|
| sting (A) | 26,8 % | 51,9 % | **18,8 %** |
| peg (G) | 21,8 % | 31,4 % | 26,0 % |
| misty (Ab) | 16,3 % | 25,8 % | **12,2 %** |
| misty2 (Eb) | 19,0 % | 30,9 % | **15,6 %** |

- **CENS ist raus** — überall deutlich schlechter (Zeitglättung verschmiert Terz/Septime).
- **NNLS senkt den maj7-Bias auf 3 von 4 Aufnahmen** (peg regrediert), bei nur
  ~+12 ms/Fenster — **Latenz ist nicht der Blocker**. Und aus dem richtigen Grund:
  der 5. Oberton der großen Terz landet auf dem maj7-Ton (denselben Effekt
  kompensiert der Matcher-Hack `THIRD_OVERTONE`); NNLS entfernt ihn an der Quelle,
  weshalb gezielt `maj7` fällt und `7`/`m7` nicht mitfallen.
- **Aber kein sauberer Gewinn:** peg wird schlechter, skalenfremde Fenster steigen
  leicht, und die Matcher-Margen waren nicht neu gesweept.

**Entscheidung:** nicht weiterverfolgt. Der eine Punkt, der wirklich half, war der
*gelernte* Mechanismus, nicht das Handtuning — das ist genau das Argument, die
Energie in Phase 2 zu stecken statt weiter am Chroma zu frickeln. Skript:
`measure_chroma.py` im Session-Scratchpad.

---

# Phase 2 — Ein eigenes Modell, synthetisch angelernt, real geerdet

Die große Kiste — und der eigentliche zukunftsorientierte Weg. Ziel: ein Modell,
das die Audioquelle direkt mit dem **konkreten Griff** verbindet (Akkord *inkl.
Leersaiten*, nicht nur ein Label) und ein Vokabular lernt, das über die fünf
Schablonen hinauswächst — `sus`, `add9`, `9`, `6`, `m7b5`, … — **schrittweise**.

Der Ansatz zerfällt in zwei Stufen mit klarer Arbeitsteilung: **synthetisch
vortrainieren** (billig, perfekte Wahrheit) → **auf echten Aufnahmen finetunen und
validieren** (teuer, die eigentliche Bewährungsprobe). Beide haben je *ein*
zentrales Problem, das über Erfolg oder Misserfolg entscheidet.

## 2a. Der synthetische On-Ramp — warum er der bessere Einstieg ist

In der ersten Fassung dieses Dokuments war der teuerste Teil das **Alignment und
die strittigen Labels** echter Transkriptionen. Ein synthetischer Korpus
**eliminiert beide auf einen Schlag**: aus einer symbolischen Vorlage gerendert,
kennt man **sample-genaue Onsets** und **eindeutige Wahrheit** gratis. Das
„es gibt keine Ground Truth"-Problem aus
[harmonischer-interpreter.md §2](harmonischer-interpreter.md) verschwindet im
Trainingsraum — *wir* definieren die Wahrheit.

Die Raffinesse liegt in den **kontrollierten Confoundern**. Dieselbe Progression
wird mehrfach gerendert:

- **mit / ohne Bass, mit / ohne Drums** — lehrt Invarianz gegen das, was egal ist
  (Schlagzeug, ob ein Bass mitläuft), und Sensibilität für die Griffvoicing.
- **diverse sample-basierte Gitarrentypen**, Anschlagsarten (Strumming, Arpeggio,
  Fingerpicking), Stimmungen, Dynamik, Tempo — Vielfalt genau dort, wo das Modell
  robust werden muss.

Das ist präzise der Angriff auf die drei Kernprobleme, die wir sonst einzeln
hacken: Obertöne (gelernt unterdrückt statt per `THIRD_OVERTONE`-Marge), der
Bass-Confound und — mit einer synthetischen Melodieschicht, siehe unten — der
Gesang. Bereits generierte Daten können den **90-%-Startstand** liefern; das ist
der realistische Gewinn. Nicht die 90 % Real-World-Genauigkeit — die kommt erst
über 2c.

## 2b. Das Zielobjekt: Griff inkl. Leersaiten, nicht nur ein Label

„Exakter Akkord inklusive Leersaiten" ist ein *tieferes* Ziel als ein
Akkordname — es ist eine **Griffvoicing**. Das passt direkt auf ein bestehendes
Asset: der [Gitarrenmodus](gitarrenmodus.md) hat schon Schablonen mit Leersaiten
und CAGED-Lagen. Dieses Vokabular kann der **Ausgaberaum** des Modells sein — dann
liefert es Griff *und* Akkord in einem Schuss, und Leersaiten sind physikalisch
informativ (sie klingen mit, sie färben das Spektrum).

Wichtig ist der Zuschnitt des Ausgaberaums: nicht freier 6-Saiten-×-Bund-Raum
(kombinatorisch riesig), sondern ein **realistisches Voicing-Vokabular** (offene
Akkorde, gängige Formen, CAGED). Und die Leitplanke aus Phase 1 gilt weiter:

- **Kein reines Label-Modell.** Ein Audio→„Cmaj7"-Netz löst Gesang/Obertöne am
  besten, **zerstört aber** Onset (~23 ms), Unsicherheit → Powerchord und die
  getrennte Bassnote. Das ist kein Beiwerk, das ist das Produkt.
- **Zielrepräsentation mit Konfidenz:** das Modell gibt Voicing/Tonklassen *plus*
  eine Terz-/Septim-Konfidenz aus. Wo es unsicher ist, greift weiter
  `safe_pitch_classes` und lässt die Terz weg — „Erkennungs-Ambiguität ist ein
  Feature, kein Fehler".

## 2c. Der Synth→Real-Graben — die make-or-break-Stelle

Die bekannte Todesart dieses Ansatzes: **auf synthetischem Audio trainierte
Modelle brechen auf echten Aufnahmen ein.** Echte Räume, Mikrofon-Bleed,
Mix-Kompression, verstimmte Gitarren, menschliches Timing, Gesang, den der Synth
nie hatte. „90 % aus generierten Daten" gilt für eine *synthetische* Testmenge —
die reale letzte Meile ist der harte Teil. Drei Pflicht-Leitplanken:

1. **Aggressive Augmentation** — Hall, EQ, Codec/MP3, Rauschen, Stimmungsdrift.
   Ohne das lernt das Modell den Synth, nicht Musik.
2. **Eine synthetische Melodie-/Gesangsschicht** ins Training — sonst bleibt
   Gesang der blinde Fleck, der uns real schon plagt.
3. **Validierung *immer* auf echtem Audio** (unsere vier Realaudio-Files + was an
   gelabeltem Real dazukommt). Niemals der synth-eigenen Testmenge trauen — die
   lügt einen in Sicherheit.

## 2d. Das echte Erdungsproblem: Transkriptionsqualität

Damit das Modell wirklich fliegt, muss es auf **echten Aufnahmen mit bekannten
Akkordfolgen** nachjustiert und geprüft werden. Genau hier sitzt der wunde Nerv:
**die bekannten Transkriptionen können schlicht falsch oder unvollständig sein.**
Drei Fehlerachsen, jede mit eigenem Charakter:

- **Falsch:** verkehrte Tonart, Capo-Verwechslung, glatt daneben (v. a. in
  crowd-sourcten Charts).
- **Vereinfacht/unvollständig:** ein `maj7` als Dreiklang notiert, eine
  Durchgangsharmonie weggelassen, `sus`/`add9` zur Triade eingedampft.
- **Zeitlich grob:** taktweise statt beat-/framegenau — eine eigene Rauschquelle,
  bevor überhaupt die Harmonie stimmt.

Der **gefährlichste** Fall ist die *Vereinfachung*, weil sie **systematisch** ist:
Transkriptionen lassen Erweiterungen im Zweifel weg → naives Training darauf lehrt
das Modell, `7`/`9`/`sus` zu *unterrufen* — das Spiegelbild unseres maj7-Bias.
Folge fürs Design: **Erweiterungen lernt vor allem der Synth** (wo wir *wissen*,
dass die 9 klingt); echte Daten dienen dort der Robustheit und dem Presence-Check,
nicht als Primärlehrer.

Wie man mit schlechten Labels trotzdem arbeitet — sie als *verrauschte* statt
*perfekte* Aufsicht behandeln:

- **Konsens-Filter:** wo mehrere Transkriptionen desselben Songs existieren, nur
  die übereinstimmenden Segmente als hartes Label nehmen; Uneinigkeit wird zu
  „unsicher" (füttert genau die Konfidenz-Ausgabe aus 2b).
- **Modell-vs-Label-Abgleich (Self-Training):** das synth-vortrainierte Modell auf
  echtem Audio vorhersagen lassen und Segmente behalten, wo Modell und
  Transkription übereinstimmen. Die Widersprüche sind entweder Modell- *oder*
  Labelfehler — beide will man sehen, nicht blind mittrainieren.
- **Audio-Label-Konsistenz:** sagt die Transkription `Cmaj7`, das Chroma an der
  Stelle trägt aber kein H, ist das ein *detektierbarer* Widerspruch → Label
  herabgewichten. Billiger Filter gegen die groben Fehler.
- **Der saubere Brückenweg — selbst aufnehmen:** echte Gitarren in echten Räumen,
  die *bekannte* Progressionen spielen. Das umgeht das Transkriptionsproblem
  vollständig (die Wahrheit ist bekannt, weil wir sie gespielt haben), zum Preis
  manueller Aufnahmearbeit. Die ehrliche Mitte zwischen „billig, aber falsch"
  (Crowd-Charts) und „perfekt, aber knapp" (akademische Sets).

## Datenquellen (zu prüfen)

Grobe Landkarte, alles verifikationsbedürftig — Lizenz und Audio-Verfügbarkeit
sind der klassische Stolperstein:

- **Synthetisch, selbst gerendert** — der Primärkorpus fürs Vortraining (2a) und
  der einzige verlässliche Lehrer für Erweiterungen (2d). Sample-Bibliotheken +
  Bass/Drums-Kreuz + Augmentation.
- **Selbst aufgenommen, bekannte Progressionen** — der Brückenweg aus 2d: echtes
  Timbre/Raum bei bekannter Wahrheit.
- **Isophonics / Billboard / RWC-Popular** — expert-annotierte ACR-Sets mit
  zeitgenauen Labels; klein, Audio meist separat, aber die beste *gelabelte reale*
  Validierung.
- **Chordify/Ultimate-Guitar-artig** — groß, aber taktweise und strittig; nur mit
  Alignment und Konsens-Filter (2d) brauchbar.

## Die offenen Fragen von Phase 2 (bewusst noch nicht beantwortet)

1. **Synth-Diversität:** welche Gitarrentypen/Spielarten/Stimmungen braucht der
   Korpus, damit die 90-%-Basis auf reale Vielfalt trägt?
2. **Voicing-Vokabular:** welcher Ausschnitt (offene Akkorde, CAGED) ist als
   Ausgaberaum groß genug für die Praxis und klein genug zum Lernen?
3. **Domain-Gap messen:** um wie viel fällt die Genauigkeit synth→real *vor* dem
   Finetuning — die Zahl, die den ganzen Weg trägt oder kippt?
4. **Label-Rauschen:** welche der vier Filter (Konsens / Self-Training /
   Audio-Konsistenz / Selbstaufnahme) trägt am meisten pro Aufwand?
5. **Echtzeit:** passt die Architektur in den 250-ms-Takt, oder braucht es eine
   destillierte/kleine Variante fürs Live-Deployment?
6. **Evaluation:** die MIREX-Standardmetrik ist blind für das, was der Spieler
   sieht ([harmonischer-interpreter.md §4](harmonischer-interpreter.md)) — wir
   brauchen unsere Realaudio-Kriterien plus ein Playtest-Urteil.

---

## Reihenfolge, in der ich es täte

Phase 1 ist gemessen und abgeschlossen (siehe Befund oben): Chroma-Tuning bringt
zu wenig, der Fokus liegt auf Phase 2. Die Reihenfolge dort:

1. **Synth-Pipeline zuerst, klein:** eine Handvoll Progressionen mit dem
   Bass/Drums-Kreuz und ein paar Gitarrentypen rendern — genug, um den
   Datenfluss (Render → Label → Voicing-Ziel) zu bauen, nicht schon den Korpus.
2. **Domain-Gap messen, bevor investiert wird:** ein kleines Modell nur auf Synth
   trainieren und *ungetunt auf echtem Audio* (unsere vier Files) prüfen. Diese
   eine Zahl entscheidet, ob der Weg trägt — fällt sie katastrophal, ist die
   Augmentierung (2c), nicht der Korpus, der nächste Hebel.
3. **Real erden:** Finetuning auf gelabeltem Real + Selbstaufnahmen, mit den
   Label-Rausch-Filtern aus 2d. Erweiterungen (`sus`/`9`/…) klassenweise, jede muss
   sich am echten Audio beweisen.
4. **Erst dann Architektur/Echtzeit** festklopfen — eine destillierte Live-Variante
   ist ein Deployment-Problem, kein Forschungsproblem, und kommt zuletzt.

## Nicht-Ziele (bewusst offen)

- Kein End-to-End-Label-Modell, das Onset/Unsicherheit/Bass opfert.
- Kein Training auf systematisch vereinfachten Labels „weil Daten da sind" — der
  Weg in einen Triaden-Bias.
- Kein Vertrauen in synth-eigene Evaluation; Wahrheit ist die reale Aufnahme.
- Die Rückseite (harmonischer Interpreter, Progressionsschicht) ist ein *anderes*
  Projekt — dieses Dokument macht die Vorderseite besser, nicht die Deutung.

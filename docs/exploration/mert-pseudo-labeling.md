# Trainingsdaten statt Modellgröße: MERT-gestütztes Pseudo-Labeling

**Status:** Konzept, noch nicht begonnen. Umsetzung geplant in einem eigenen
Projektverzeichnis außerhalb von JamPilot; dieses Dokument ist die Übergabe.

**Stand:** 2026-08-25

## Ausgangslage

Die Erkennungsqualität von JamPilot (Akkorde und Tonart) ist an einem Punkt, an
dem lokale Verbesserungen ausgereizt sind:

- Der maj7-Bias — lange die Top-Schwäche — ist mit dem BTC-Transformer
  (ISMIR 2019) im Offline-Pfad behoben.
- Der Key-Pin deckt die praktischen Tonart-Problemfälle ab; der Label-Hybrid
  als Tonart-Signal wurde in 18 Varianten gemessen und verworfen.
- Die verbleibende Schwäche ist **Genre-Sensitivität**: BTC ist auf
  Isophonics/Billboard-artigem Pop-Repertoire trainiert. Real gemessen: Pop
  (Duran Duran) top, Prog (Porcupine Tree) falsch. Das ist Domain-Shift der
  Trainingsdaten, kein Kapazitätsproblem des Modells.

**These:** Ein substanzieller Sprung geht nur noch über breitere
Trainingsdaten, nicht über Architektur- oder Heuristik-Arbeit.

**Wichtige Abgrenzung:** *Nicht* über mehr Parameter. Ein größeres Modell auf
derselben Datenverteilung memoriert die In-Domain-Verteilung genauer, statt
besser zu generalisieren — und kollidiert mit der Zielhardware (MacBook 2013
ist mit dem BTC-Live-Pfad bereits an der CPU-Grenze). Modellgröße wird erst
Thema, wenn ein datenseitig gesättigtes Modell nachweislich am Limit ist, und
dann nur mit Distillation-Plan.

## Warum keine handgelabelten Komplettdaten

Vollständige Akkord-Annotation ist Expertenarbeit im Bereich Stunden pro
Album. Die klassischen Datensätze (Isophonics, McGill Billboard, RWC, JAAH)
sind zusammen nur wenige hundert Songs. Ein selbst annotiertes Trainingsset
über viele Stile wäre der teuerste denkbare Weg. Handarbeit lohnt nur für ein
**kleines, hartes Evaluationsset** — das braucht man ohnehin, um Fortschritt
messen zu können, und es fällt beim Workflow unten als Nebenprodukt ab.

## Was ist MERT

MERT („Music undERstanding model with large-scale self-supervised Training",
Li et al. 2023) ist ein selbstüberwacht vortrainiertes Audio-Foundation-Model
für Musik — BERT/HuBERT-Prinzip auf Musikaufnahmen. Masked Prediction mit zwei
Teachern: akustisch (EnCodec/RVQ-Tokens) und musikalisch (CQT-basierte
Harmonie-/Pitch-Information). Letzteres zwingt das Modell schon im
Pretraining, Harmoniestruktur zu repräsentieren.

- Offene Gewichte: `m-a-p/MERT-v1-95M` und `m-a-p/MERT-v1-330M` auf
  Hugging Face, nutzbar über Transformers. **Lizenz vor kommerzieller Nutzung
  prüfen** (variierte zwischen den Versionen). Dito die Lizenz des
  BTC-ISMIR19-Repos für Derivate — JamPilot hat seit der öffentlichen
  Ankündigung ein Publikum.
- Nutzungsmuster: Modell einfrieren, kleinen Head (Akkord-/Tonart-
  Klassifikator) auf den Embeddings trainieren. Die Stilbreite kommt aus dem
  Pretraining, nicht aus den Labels.
- Für den Live-Pfad ungeeignet (95M/330M Parameter, Transformer über
  Rohaudio): realistisch nur als Offline-Analysepfad oder als Teacher für
  Distillation in ein kleines Live-Modell.

### Ehrliche Benchmark-Einschätzung

Die publizierten Zahlen belegen **nicht**, dass MERT besser ist als ein
Spezialist wie BTC:

- Akkorderkennung wird im MARBLE-Benchmark auf **GuitarSet** gemessen
  (Solo-Akustikgitarre): MERT-330M ≈ 45 % majmin-WCSR per Probing. BTC liegt
  auf Isophonics (echte Band-Aufnahmen) bei > 80 % majmin. Nicht direkt
  vergleichbar (verschiedene Datensätze), aber kein Beleg für Überlegenheit
  auf Bandmusik.
- Tonart wird auf **GiantSteps** gemessen (nur EDM): MERT liegt dort *unter*
  den spezialisierten Systemen.
- MERT gibt von Haus aus keine Akkorde aus — der Erkenner, den man vergleichen
  will, muss erst gebaut werden (Head auf den existierenden Labels).

MERTs Versprechen ist Robustheit über Stile hinweg dank breitem Pretraining.
Plausibel, aber für unseren Anwendungsfall **unbewiesen** → erst messen
(Schritt 1), dann Pipeline bauen (Schritt 2).

## Der Datenkorpus

Eigene Audiobibliothek: **60 GB MP3**, von eigenen CDs gerippt (rechtlich
unkritisch für lokales Training; Streams mitschneiden — z. B. Spotify — ist
dagegen ToS-Verstoß und tabu). Grob 500–700 Stunden ≈ 8.000–10.000 Songs.

Warum dieser Korpus ideal ist:

1. **Menge:** Größenordnungen über den klassischen gelabelten Datensätzen;
   Engpass wird Rechenzeit, nicht Daten.
2. **Verteilung:** Per Definition die Musik, zu der tatsächlich gejammt wird —
   inklusive der stilfernen Fälle (Prog), an denen BTC scheitert. In-Domain
   für den realen Nutzungsfall statt für einen abstrakten Benchmark.
3. **Metadaten gratis:** ID3-Tags (Genre, Artist, Jahr) erlauben
   stratifizierte Samples und systematische Messung der Genre-Sensitivität.
4. **MP3-Artefakte sind kein Nachteil:** JamPilot analysiert im Einsatz
   ebenfalls komprimiertes Material — Training sieht dieselben Bedingungen
   wie der Ernstfall.

Ergänzend, falls mehr Breite nötig: frei lizenzierte Korpora (MTG-Jamendo,
Free Music Archive).

## Kernidee: Disagreement-Mining mit menschlichem Schiedsrichter

Zwei Modelle laufen parallel über den Korpus: das bestehende Modell
(BTC + eigene Onset/Bass-Pipeline) und ein MERT-basierter Erkenner.

Der naive Ansatz — „wo sie sich unterscheiden, ist Lernmaterial" — hat einen
Konstruktionsfehler: Eine Differenz sagt, *dass* sich die Modelle uneinig
sind, nicht *wer recht hat*. Ohne Schiedsrichter ist das keine gelabelte
Menge, sondern eine Streitliste. Bei Differenzen blind MERT zu glauben wäre
Distillation von MERT inklusive seiner Fehler.

Die funktionierende Variante (klassisches Active Learning):

- **Einigkeit beider Modelle** → hochkonfidente Pseudo-Labels, direkt als
  Trainingsmaterial. Das ist der Großteil der Stunden und fast gratis.
- **Uneinigkeit** → kleine Review-Queue, Entscheidung **nach Gehör** durch
  einen Musiker. JamPilot selbst ist das Review-Werkzeug: Stelle anspielen,
  mitspielen, hören, richtiges Label setzen. Aufwand: Minuten pro Stunde
  Musik statt Stunden pro Album.
- Nebenprodukt der Review-Queue: das handverifizierte, stratifizierte
  **Evaluationsset**, das für jede weitere Messung gebraucht wird.
- Nicht nur auf Differenzen trainieren (verzerrte Verteilung) — Einigkeit und
  geschlichtete Differenzen zusammen bilden das Trainingsset.

## Plan

### Schritt 0 — Korpus-Inventur

Skript über die Bibliothek: Stunden pro Genre aus den ID3-Tags,
stratifiziertes Sample von 50–100 Songs als Basis für das Eval-Set.

### Schritt 1 — Entscheidungsexperiment (billig, entscheidet alles Weitere)

1. MERT-v1 (erst 95M, bei Erfolg 330M) einfrieren, Akkord- und Tonart-Head
   auf den existierenden gelabelten Datensätzen trainieren.
2. Gegen BTC auf dem stratifizierten Sample aus der eigenen Bibliothek
   antreten lassen — insbesondere auf den bekannten BTC-Versagensfällen
   (Porcupine Tree u. ä.). Differenzen nach Gehör schlichten; dabei entsteht
   das Eval-Set.
3. **Messfrage:** Ist der MERT-Erkenner auf stilferner Musik signifikant
   robuster als BTC?

**Wenn nein:** Wochen Pipeline-Bau gespart. Alternativweg: BTC direkt auf
zusätzlichen Datensätzen fine-tunen (McGill Billboard, RWC, JAAH,
HookTheory-Alignments) — Wochenend-Experiment, kein neues Projekt.

### Schritt 2 — Pseudo-Label-Pipeline (nur bei positivem Schritt 1)

1. Volle Bibliothek durch beide Modelle (offline, Batch).
2. Einigkeit → Pseudo-Labels; Differenzen → Review-Queue → Schlichtung nach
   Gehör.
3. Das kleine Live-Modell (BTC-Größenklasse) auf dem kombinierten Set
   nachtrainieren.
4. Messen auf dem Eval-Set aus Schritt 1 — pro Genre, nicht nur aggregiert.

### Schritt 3 — Integration in JamPilot (separat zu entscheiden)

- Nachtrainiertes kleines Modell ersetzt/ergänzt BTC im bestehenden
  Hybrid-Weg (Re-Ranker + eigener Onset/Bass bleibt unberührt — Timing ist
  eine eigene Baustelle mit eigener Ground-Truth-Anforderung).
- Zielhardware-Validierung (MacBook 2013) vor jedem Merge; der
  inkrementelle-CQT-Fix (5.6x) ist dort weiterhin unvalidiert.

## Leitplanken

- **Profiling vor Optimierung:** Kein Pipeline-Bau vor dem
  Entscheidungsexperiment; jede Stufe erst messen, dann ausbauen.
- **Produktmaßstab:** JamPilot ist ein minimales Jam-Tool („null Anlauf").
  Erkennungs-Ambiguität in grundtonlosen Parts ist gewollt — das Nachtraining
  darf sie nicht wegoptimieren. Erfolgskriterium ist der Mitspiel-Fluss,
  nicht die Benchmark-Zahl.
- **Lizenz-Checks vor Code:** BTC-Repo (Derivate) und MERT-Gewichte
  (kommerzielle Nutzung).

## Quellen

- MERT-Paper: <https://arxiv.org/abs/2306.00107>
- MARBLE-Benchmark: <https://arxiv.org/abs/2306.10548>
- MERT-Gewichte: <https://huggingface.co/m-a-p/MERT-v1-95M>,
  <https://huggingface.co/m-a-p/MERT-v1-330M>
- BTC (ISMIR 2019, Park & Choi): <https://github.com/jayg996/BTC-ISMIR19>

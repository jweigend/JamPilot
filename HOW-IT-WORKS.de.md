# Wie JamPilot Akkorde erkennt — und warum das nie 100 % sein kann

*English version: [HOW-IT-WORKS.md](HOW-IT-WORKS.md)*

JamPilot hört das Systemaudio mit, hält es ein paar Sekunden zurück und zeigt
die Akkorde an, **bevor** man sie hört ([README](README.md)). Dieses Dokument
erzählt, *wie* die Erkennung dahinter funktioniert: den klassischen
Chroma-Ansatz, mit dem das Projekt gestartet ist, warum wir auf ein gelerntes
Modell umgestiegen sind — und warum auch der beste Erkenner an eine
prinzipielle Grenze stößt, die nichts mit Fleiß zu tun hat.

Stand: 2026-08-08 (nach dem Umbau auf das BTC-Modell). Alle Zahlen stammen aus
Messungen gegen handannotierte Referenzaufnahmen
([tests/reference/README.md](tests/reference/README.md)).

---

## 1. Der klassische Ansatz: Chroma + Schablonen

Die erste Fassung von JamPilot beantwortete die Frage „welcher Akkord klingt?"
rein mit Signalverarbeitung, in drei Schritten:

1. **Chroma berechnen.** Aus jedem 1,5-Sekunden-Fenster wird ein
   **12-Werte-Vektor** gewonnen — ein Eintrag je Tonklasse (C, C#, …, B), alle
   Oktaven zusammengefaltet. Vorher trennt eine harmonisch/perkussive
   Zerlegung (HPSS) das Schlagzeug heraus; eine Constant-Q-Transformation
   sorgt dafür, dass auch tiefe Grundtöne sauber getroffen werden
   ([chroma.py](jampilot/chroma.py)).
2. **Schablonen vergleichen.** Der Vektor wird per Cosinus-Ähnlichkeit gegen
   Akkord-Schablonen auf allen 12 Grundtönen gematcht — Dur, Moll, `7`,
   `maj7`, `m7` ([chords.py](jampilot/chords.py)). Der beste Treffer gewinnt;
   unter einer Mindestähnlichkeit gilt „kein Akkord".
3. **Absichern.** Ein Tonart-Prior ordnet knappe Lesarten, ein
   Mehrheitsentscheid über drei Analysen glättet Flackern, und eine separate
   **Onset-Suche** im 23-ms-Frameraster bestimmt, *wann* der Wechsel wirklich
   einsetzt — nicht wann die Erkennung ihn bemerkt hat.

Dazu kommt eine Idee, die JamPilot bis heute trägt: **zwei Fragen, zwei
Signale.** Welcher Akkord klingt, entscheidet die volle Harmonie; welche Note
*unten* liegt, wird separat im Tiefband gemessen ([bass.py](jampilot/bass.py)).
Nur so werden Umkehrungen sichtbar (`C/E`, `G/B`) — aus dem Akkordnamen allein
kann man sie nicht erraten.

**Die Stärken dieses Ansatzes** sind real und waren der Grund, so zu starten:
Er ist vollständig transparent (jede Entscheidung lässt sich nachrechnen),
braucht keinerlei Trainingsdaten, ist billig genug für alte Hardware — und er
ist **stilneutral**: Eine Schablone kennt kein Genre, ihr ist egal, ob Jazz
oder Metal anliegt.

**Die Schwächen** haben wir über Monate an echten Aufnahmen dokumentiert, und
sie sitzen tiefer, als es zunächst aussah:

- **Obertöne erzeugen Phantom-Töne.** Der fünfte Oberton einer großen Terz
  landet genau auf dem maj7-Ton. Ergebnis: ein hartnäckiger **maj7-Bias** —
  ein schlichtes `D7` wird gern als `Dmaj7` gelabelt, für Mitspielende der
  ärgerlichste Fehlertyp (die Septime ist *falsch*, nicht nur ungenau).
- **Gesang liegt im selben Frequenzband wie der Akkord** und lässt sich —
  anders als der Bass — nicht per Frequenz heraustrennen. Jede Melodielinie
  schüttet Nicht-Akkordtöne ins Chroma.
- **Fünf Schablonen sind ein kleines Vokabular.** `sus`, `dim`, `6`, `m7b5`
  existierten schlicht nicht; das Signal wurde in die nächstliegende der fünf
  Formen gepresst.
- **Flackern.** In dichten Passagen kippte die Anzeige zwischen Lesarten
  (`Amaj7`/`A7`/`C#m`…), und jede dieser Schwächen brauchte ihren eigenen
  Gegen-Hack: Komplexitätsmargen, Prior, Glättung.

Der entscheidende Befund kam aus einem systematischen Experiment
([docs/exploration/lernbasiertes-chroma.md](docs/exploration/lernbasiertes-chroma.md)):
Wir haben bessere Chroma-Extraktoren gemessen (CENS, ein selbst gebautes
NNLS-Chroma nach Mauch). Ergebnis: CENS klar schlechter, NNLS half nur
punktuell — **weiter am Chroma zu frickeln lohnt nicht.** Das Einzige, was
den maj7-Bias wirklich an der Wurzel packte, waren *gelernte* Mechanismen.
Dieses Messergebnis ist der eigentliche Wendepunkt des Projekts.

## 2. Der Umstieg: ein gelerntes Modell als Label-Quelle

Seit dem Umbau beantwortet die Frage „welcher Akkord?" ein neuronales Netz:
**BTC** („Bi-directional Transformer for Chord Recognition", Park et al.,
ISMIR 2019) — ein kleiner bidirektionaler Transformer, trainiert auf
expertenannotierten Aufnahmen, mit einem Vokabular von **14 Qualitäten × 12
Grundtöne** (170 Klassen). Der Checkpoint ist nur 12 MB groß; wir haben ihn
nach reinem NumPy portiert ([btc.py](jampilot/btc.py)), es gibt also keine
PyTorch-Abhängigkeit.

Wichtig: Es ist **kein Komplettersatz, sondern ein Hybrid.** Das Modell
liefert die Labels — alles, was es *nicht* kann, macht weiter unsere eigene
Signalverarbeitung:

- **Slash-Bässe** kennt das BTC-Vokabular nicht (`G/B` wäre für das Modell nur
  `G`). Die Bassnote wird weiter im Tiefband **gemessen**, jetzt aus derselben
  CQT, die ohnehin fürs Modell anfällt.
- **Grenzen verfeinern:** Das Modell arbeitet auf einem 93-ms-Raster und setzt
  Grenzen tendenziell *hinter* den hörbaren Wechsel. `refine_boundary` zieht
  jede Grenze im 23-ms-Raster auf das Audio-Ereignis — die Onset-Idee des
  alten Pfads, in neuer Form.
- **Tonart** wird weiter selbst geschätzt (sie entscheidet nur noch über die
  Schreibweise: `C#` oder `Db`).

### Was der Umstieg messbar gebracht hat

Gemessen gegen fünf sekundengenau handannotierte Referenzaufnahmen
(Isophonics-Annotationen: Beatles, Queen, Carole King — ~500 annotierte
Akkordwechsel), beide Pfade in ihrer echten Live-Konfiguration, dieselbe
Metrik ([tests/reference/README.md](tests/reference/README.md)):

| Dauergewichtete Trefferquote | Schablonen-Pfad | BTC-Pfad |
|---|---|---|
| Grundton richtig | 69,5 % | **82,8 %** |
| Grundton + Dur/Moll-Geschlecht | 62,8 % | **81,5 %** |
| volle Qualität (Septimen-Ebene) | 49,5 % | **76,8 %** |
| erkannte Segmente (Referenz: 508) | 764 | **588** |

Die Fehlerrate hat sich also je nach Ebene **halbiert bis mehr als halbiert**
— am deutlichsten genau dort, wo der alte Pfad strukturell schwach war: bei
den Qualitäten. Der maj7-Bias ist praktisch verschwunden (das Modell labelt
Dominanten als Dominanten), tonartfremde Ausreißer-Grundtöne ebenso, und die
Anzeige ist ruhiger geworden — der alte Pfad produzierte 50 % mehr Segmente
als die Referenz enthält, lauter kurzes Umspringen zwischen Lesarten.

**Beim Timing dagegen war der alte Pfad nie das Problem.** Beide Verfahren
treffen den annotierten Wechsel mit einem Medianfehler um ~130–150 ms; die
alte Onset-Suche war sogar etwas dichter dran, erkaufte das aber mit vielen
Phantom-Grenzen (nur 51 % ihrer Grenzen lagen an einem echten Wechsel, beim
BTC-Pfad 58 %). Der Gewinn des Umbaus liegt bei den **Labels**, nicht bei der
Zeit — für den Mitspiel-Fluss ist beides zusammen entscheidend: der richtige
Akkord, zur ungefähr richtigen Zeit, ohne Flackern.

### Der Preis

Ehrlichkeit gehört dazu: Der neue Pfad kostet spürbar mehr CPU (alle 250 ms
eine CQT über das 10-s-Fenster plus Transformer-Inferenz — auf einem alten
Laptop kann das an die Grenze gehen), und ein *gelerntes* Modell ist nicht
mehr stilneutral. Dazu gleich mehr.

## 3. Warum das nie 100 % sein kann

Wer die Tabelle oben liest, fragt zu Recht: Warum stehen da 83 % und nicht
99 %? Die Antwort ist nicht „das Modell ist noch nicht gut genug". Ein Teil
des Abstands ist prinzipiell — er verschwindet mit keinem noch so guten
Erkenner. Fünf Gründe, vom fundamentalsten zum praktischsten:

**1. Ein Akkord ist eine Deutung, kein Messwert.** `C6` und `Am7` bestehen
aus exakt denselben vier Tönen (C-E-G-A) — welcher von beiden „klingt",
entscheidet nicht das Signal, sondern der harmonische Kontext, und darüber
sind sich selbst zwei Musiker nicht immer einig. Dasselbe gilt für `add9`
gegen `sus2`, für Durchgangsharmonien, für die Frage, ob die Septime im
Klavier „zum Akkord gehört" oder nur eine Melodienote war. Auch unsere
Referenzannotationen sind eine *Interpretation* — die messbare Obergrenze
jedes Erkenners ist die Einigkeit menschlicher Experten, und die liegt nicht
bei 100 %.

**2. Die Physik legt Töne ins Signal, die niemand gegriffen hat.** Jede
gespielte Note bringt ihre Obertonreihe mit; der fünfte Oberton der Terz
*ist* der maj7-Ton. Umgekehrt fehlen Töne, die „zum Akkord gehören": Ein
verzerrter Powerchord enthält **keine Terz** — ob Dur oder Moll gemeint ist,
steht schlicht nicht im Signal. Jeder Erkenner muss dort raten; er kann nur
klug raten.

**3. Gesang und Melodie wohnen im selben Band.** Die Stimme lässt sich nicht
wie der Bass per Frequenz abtrennen. Jede Melodielinie streut Nicht-Akkordtöne
genau dorthin, wo die Harmonie gemessen wird — ein gelerntes Modell wird
darin robuster, aber die Überlagerung selbst bleibt.

**4. Ein Wechsel ist kein Zeitpunkt.** Der Bass kommt einen Tick vor der
Gitarre, der Anschlag verschmiert über Millisekunden, die Annotation selbst
trägt ±50 ms Unsicherheit. „Den" wahren Moment des Wechsels gibt es nur als
Konvention — deshalb messen wir Timing als Verteilung, nicht als
richtig/falsch.

**5. Ein gelerntes Modell kennt sein Trainingsterrain.** BTC ist auf Pop und
Rock der 60er bis 90er trainiert (Beatles, Queen, Carole King, UsPop-Korpus).
Auf produziertem Pop funktioniert es entsprechend stark — bei stilferner
Musik (Progressive Rock mit Drones, terzlosen Powerchords, quartigen
Voicings) kann es deutlich danebenliegen. Der alte Schablonen-Pfad war
stilblind; das Modell hat den Stil *gelernt*, mit allem, was dazugehört.
Und weil unsere Referenzaufnahmen aus demselben Korpus stammen, sind die
Zahlen oben **In-Domain-Zahlen**: Für Musik abseits dieses Stilraums liegt
die echte Genauigkeit darunter.

Ein letzter Punkt, der kein Mangel ist: **Ein Rest Unruhe ist gewollt.** Wo
die Harmonie objektiv mehrdeutig ist — grundtonlose Passagen, Vamps ohne
Terz — zeigt JamPilot lieber wechselnde plausible Lesarten als eine falsche
Gewissheit. Für Mitspielende ist das eine Improvisationshilfe: Alles, was da
angezeigt wird, *passt* zu dem, was klingt.

## 4. Wo es weitergeht

- **Rechenlast:** Der Fixkostenblock der Feature-Extraktion war librosas
  Filterbank, die bei jedem CQT-Aufruf neu gebaut wurde — memoisiert kostet
  die Extraktion je Hop 21 statt 70 ms, bitidentisch. Eine inkrementelle CQT
  (Frames über die Hops cachen) brächte weitere 21 → 12 ms, bleibt aber
  draußen: gleiche Features, aber ihr hop-stabiles Raster erzeugt im
  Live-Pfad ~7 % mehr Events — das wandernde Raster der Vollrechnung wirkt
  als Dither, den der Debounce nutzt.
- **Stilraum:** Für Musik außerhalb des Trainingsterrains ist zuerst ein
  ehrliches Hörprotokoll nötig (wo genau kippt es?), bevor an Lösungen zu
  denken ist.
- **Timing:** Beide Pfade streuen ~±150 ms um den Wechsel; enger geht es nur
  mit besserem Zeitraster, nicht mit besseren Labels.

Wer tiefer einsteigen will: Die Messmethodik steht in
[tests/reference/README.md](tests/reference/README.md), der ursprüngliche
Modell-Benchmark in
[tests/realaudio/REPORT_btc_benchmark.md](tests/realaudio/REPORT_btc_benchmark.md),
die Exploration, die zum Umstieg führte, in
[docs/exploration/lernbasiertes-chroma.md](docs/exploration/lernbasiertes-chroma.md).

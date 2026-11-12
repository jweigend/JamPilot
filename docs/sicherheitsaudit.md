# Sicherheitsprüfung je Release

Jedes Release bekommt vor der Veröffentlichung eine Sicherheitsprüfung und ein
Protokoll auf der Projektseite (`site/audit/<version>.html`, deutsch
`<version>.de.html`). Die Prüfung macht Claude (Claude Code) im Auftrag des
Entwicklers. Diese Datei ist die Checkliste dafür – die einzige Anweisung des
Projekts, nach der die Prüfung abläuft. Sie liegt offen im Repository, damit
jeder nachlesen kann, was geprüft wird und was nicht.

## Wofür

JamPilot ist ein Programm aus dem Internet, das auf dem eigenen Rechner den
Ton umleitet und einen Port im Netz öffnet. Wer es herunterlädt, fragt zu
Recht, was es dort tut. Das Protokoll beantwortet das für Musiker, nicht für
Administratoren.

## Regeln für das Protokoll

- **Geprüft wird das Release, nicht `main`.** Quelltext am Tag, und die
  Dateien, die wirklich zum Download stehen.
- **Kurz und ohne Fachsprache.** Das Ergebnis steht in einem Satz ganz oben.
  Dann die Fragen, die ein Musiker stellt (Internet, Zuhören, Aufnahmen,
  Veränderungen am Rechner, wer mitlesen kann, Echtheit des Downloads).
  Technik (Prüfsummen, Kennungen, Werkzeuge) gehört in den zugeklappten Teil
  am Ende.
- **Nur behaupten, was gemessen oder gelesen wurde.** Jede Aussage muss sich
  mit dem öffentlichen Code und den Prüfsummen nachprüfen lassen.
- **Sagen, was nicht geprüft wurde.** Der Abschnitt ist Pflicht.
- **Die Einordnung des Prüfers bleibt ehrlich.** Das Ergebnis wird nicht
  vorgegeben, kein Thema ausgeklammert. Aber: Die Prüfung ist beauftragt,
  Claude hat am Code mitgeschrieben und arbeitet unter allgemeinen Regeln von
  Anthropic. Das Protokoll nennt das und heißt deshalb nicht „unabhängiges
  Audit“ und nicht „Zertifikat“.
- **Befunde werden nicht geschönt und nicht weggelassen.** Ein Befund, der
  gegen die Veröffentlichung spricht, steht im Protokoll – und das Release
  wartet, bis er behoben ist. Das entscheidet der Entwickler; das Protokoll
  wird dafür nicht umgeschrieben.

## Ablauf

1. **Stand festhalten.** Tag, Commit, Build-Lauf. Quelltext des Tags getrennt
   auspacken (`git archive <tag>`), nicht den Arbeitsbaum lesen.
2. **Den Code lesen, wo das Programm nach außen greift:**
   - Netzwerk: jede ausgehende Verbindung, jeder lauschende Port
     (`web.py`, `updates.py`); was die Anzeige ohne Token preisgibt, was das
     Token schützt.
   - Dateien: alles, was geschrieben, gelöscht oder aus fremder Hand gelesen
     wird (`routing.py`, `desktop.py`, `cli.py`, `web.py`).
   - Ton: woher er kommt, wo er liegt, ob er den Arbeitsspeicher verlässt
     (`delay_stream.py`, `record_buffer.py`, `wincapture.py`, `envelope.py`).
   - Fremde Programme: jeder `subprocess`-Aufruf, Shell ja/nein, woher die
     Argumente stammen.
   - Laden von Daten: Modellgewichte, JSON, alles mit `pickle`-Risiko.
   - Die Seite im Browser: Fremdquellen, wohin sie sendet.
   - Dauerhaftes: Autostart, Dienste, Registry, Administratorrechte.
   - Start- und Build-Skripte, `packaging/`, die Workflows.
   - Der Diff zum vorigen Release wird vollständig gelesen.
3. **Bibliotheken.** `pipx run pip-audit -r requirements.lock --no-deps
   --disable-pip --desc on`. Jede Meldung einzeln bewerten: Ist die Stelle in
   diesem Release erreichbar?
4. **Download = Build.** Alle Release-Dateien herunterladen, SHA-256 messen,
   mit den Release-Notizen und dem Build-Protokoll vergleichen (Windows: das
   ZIP; Linux/macOS: das Programm im Archiv; `JamPilot.app`: identisch bis auf
   den Signaturblock). Heruntergeladenes in ein eigenes, leeres Verzeichnis.
5. **Beim Laufen beobachten.** `strace -f -e trace=network` um
   `jampilot selftest` des veröffentlichten Linux-Programms; vorher mit einem
   Gegenversuch zeigen, dass der Mitschnitt Verbindungen sieht. 1.5.1: kein
   einziger Netzwerkaufruf. Releases mit der Update-Schaltfläche fragen im
   Betrieb einmal pro Start bei `api.github.com` an (abschaltbar mit
   `--no-update-check`) – was davon im Mitschnitt steht, wird abgelesen, nicht
   angenommen.
6. **Protokoll schreiben**, englisch und deutsch, nach dem Muster des
   vorigen. Befunde nach Schwere: schwer (nicht benutzen), mittel (benutzen
   mit Einschränkung), klein (Hinweis).
7. **Verlinken.** Den Link im Download-Abschnitt von `site/index.html` auf
   das neue Protokoll stellen; im neuen Protokoll auf die früheren verweisen.
   Der Link gehört auch in die Release-Notizen.

## Grenzen, die jedes Protokoll nennt

- Die gebündelten Bibliotheken werden nicht gelesen, nur gegen die Liste
  bekannter Schwachstellen geprüft.
- Windows- und macOS-Dateien werden nicht gestartet (kein solcher Rechner in
  der Prüfung), nur per Prüfsumme verglichen.
- Kein Virenscanner.
- Fremde Tontreiber (BlackHole, VB-CABLE) sind nicht Teil der Prüfung.

## Bisherige Protokolle

| Release | Datum | Ergebnis | Protokoll |
|---|---|---|---|
| 1.5.1 | 12.11.2026 | nichts Schweres oder Mittleres, vier kleine Hinweise | [site/audit/1.5.1.html](../site/audit/1.5.1.html) |

# Explorationsdokument

## Projektidee: LiveChord – Echtzeit-Akkordanalyse für Musiker

### Vision

Musiker möchten beim Üben oder im Proberaum spontan zu beliebiger Musik spielen können. Heute ist dieser Workflow unnötig kompliziert:

* Song herunterladen
* Datei in Moises oder einen ähnlichen Dienst hochladen
* Verarbeitung abwarten
* Erst danach stehen Akkorde oder Stems zur Verfügung

Die Vision dieses Projekts ist eine Anwendung, die ohne diesen Umweg funktioniert.

Der Musiker startet einfach Spotify, YouTube oder einen beliebigen Audioplayer und erhält in Echtzeit eine große, gut lesbare Akkordanzeige.

**Der Workflow soll so einfach sein wie:**

1. Musik starten.
2. LiveChord starten.
3. Akkorde erscheinen.
4. Spielen.

---

# Zielgruppe

* Gitarristen
* Bassisten
* Keyboarder
* Schlagzeuger
* Bands im Proberaum
* Musikschulen

---

# Kernidee

Nicht das Bearbeiten von Musikdateien steht im Mittelpunkt, sondern die Live-Unterstützung beim Spielen.

Die Anwendung analysiert einen laufenden Audiostream und erkennt fortlaufend die harmonische Struktur.

Die Akkorde werden in Echtzeit oder mit einer bewusst eingeführten Verzögerung dargestellt.

---

# Problem auf Smartphones

Während der Exploration zeigte sich ein wesentliches technisches Hindernis.

## iPhone

iOS erlaubt keinen allgemeinen Zugriff auf den Audiostream beliebiger Apps.

Spotify oder YouTube können deshalb nicht einfach analysiert werden.

Eine Mikrofonlösung ist zwar möglich, eignet sich jedoch kaum für den praktischen Einsatz:

* Schlagzeug überdeckt die Musik
* Bassverstärker beeinflusst das Signal
* Raumakustik verschlechtert die Erkennung
* Kopfhörerbetrieb funktioniert praktisch nicht

Damit verliert die App ihren eigentlichen Nutzen.

---

## Android

Android besitzt zwar Möglichkeiten zur Audioaufnahme anderer Apps (Audio Playback Capture), jedoch können Anwendungen diese Funktion blockieren.

Für ein zuverlässiges kommerzielles oder plattformübergreifendes Produkt ist dies keine stabile Grundlage.

---

# Desktop als optimale Plattform

Während der Diskussion entstand eine deutlich bessere Architektur.

Der Audiostream wird nicht auf dem Smartphone, sondern auf einem Computer analysiert.

Insbesondere ein MacBook eignet sich hervorragend.

Im Proberaum ist bereits ein MacBook vorhanden.

Dieses wird ohnehin genutzt, um Musik über die Soundkarte auszugeben.

---

# Technische Architektur

```text
Spotify
YouTube
Browser
      │
      ▼
Virtuelles Audiogerät
      │
      ▼
Python Analyse
      │
      ├────────► Akkordanalyse
      │
      └────────► Verzögerte Wiedergabe
                      │
                      ▼
                 USB Soundkarte
```

Die eigentliche Audioverarbeitung findet vollständig auf dem MacBook statt.

---

# Warum eine Verzögerung sogar hilfreich ist

Eine interessante Erkenntnis war:

Eine kleine Verzögerung des Audios ist kein Nachteil.

Im Gegenteil.

Beispielsweise:

* Musik wird um 3 Sekunden verzögert ausgegeben.
* Die Analyse kennt dadurch bereits die nächsten Sekunden Musik.

Dadurch kann nicht nur der aktuelle Akkord dargestellt werden.

Sondern auch:

* nächster Akkord
* übernächster Akkord
* Akkordwechsel

Der Musiker erhält dadurch einen echten Blick nach vorne.

Beispiel:

```
JETZT

Am

ALS NÄCHSTES

F

DANACH

C
```

Das ist wesentlich hilfreicher als eine reine Echtzeiterkennung.

---

# Audioverarbeitung

Geplanter Signalfluss:

```
PCM Audio

↓

Mono

↓

Harmonische Trennung

↓

Chroma / Constant-Q

↓

Pitch Classes

↓

Akkorderkennung

↓

Zeitliche Glättung

↓

Anzeige
```

---

# Mögliche Bibliotheken

## sounddevice

Zum Lesen und Schreiben des Audiostreams.

Vorteile:

* PortAudio
* Echtzeitfähig
* Python
* NumPy-kompatibel

---

## librosa

Für einen ersten Prototyp.

Geeignet für:

* Chroma Features
* Constant-Q
* Harmonische Trennung

---

## Essentia

Später möglicherweise bessere Wahl.

Bietet bereits:

* HPCP
* Akkorderkennung
* Tonarterkennung
* Music Information Retrieval

---

# Version 0.1

Zunächst bewusst klein halten.

Funktionen:

* Audiostream lesen
* 2–4 Sekunden verzögert ausgeben
* Dur- und Mollakkorde erkennen
* Terminalausgabe

Beispiel:

```
Current : Am

Next : F

Confidence : 0.86
```

Noch keine grafische Oberfläche.

---

# Version 0.2

Grafische Oberfläche auf dem Mac.

Große Akkordanzeige.

Optional:

* Taktanzeige
* Akkordhistorie
* Konfidenz

---

# Smartphone-Anzeige

Hier entstand eine besonders elegante Idee.

Das Smartphone muss überhaupt keine Audioanalyse durchführen.

Es dient ausschließlich als Fernanzeige.

```
MacBook

↓

Audioanalyse

↓

WebSocket Server

↓

WLAN

↓

Smartphone
```

Dadurch ergeben sich mehrere Vorteile:

* keinerlei Zugriff auf Spotify notwendig
* keinerlei Zugriff auf YouTube notwendig
* keine Audioberechtigungen
* sehr geringe CPU-Last
* einfache Architektur

---

# Erste Version sogar ohne native App

Eine native App ist zunächst nicht notwendig.

Das Smartphone öffnet einfach:

```
http://macbook.local
```

Der Browser verbindet sich per WebSocket.

Der Bildschirm zeigt:

```
JETZT

Am

NÄCHSTER

F

DANACH

C
```

Dadurch funktioniert das System sofort auf:

* Android
* iPhone
* Tablet

ohne Installation.

---

# QR-Code-Verbindung

Um die Verbindung besonders einfach zu machen:

MacBook:

* startet lokalen Server
* erzeugt QR-Code

Smartphone:

* QR-Code scannen
* Browser öffnet automatisch
* Verbindung steht

Keinerlei Netzwerkkonfiguration notwendig.

---

# Mögliche spätere Funktionen

## Anzeige

* aktueller Akkord
* nächster Akkord
* Akkordhistorie
* Songposition
* Takt
* Tempo

---

## Musikerfunktionen

* Transponieren
* Capo-Modus
* vereinfachte Akkorde
* Nashville Number System
* deutsche Akkordschreibweise
* internationale Akkordschreibweise

---

## Erweiterungen

* Tonarterkennung
* Akkordwahrscheinlichkeit
* Rhythmuserkennung
* Formanalyse (Verse, Chorus, Bridge)
* automatische Songstruktur
* Live-Scrolling

---

# Mögliche spätere KI-Funktionen

* Erkennung von Modulationen
* automatische Lead-Sheets
* Harmonievorschläge
* Gitarrengriffe
* Basslinien
* Schlagzeug-Pattern
* Improvisationsskalen

---

# Projektphasen

## Phase 1

Machbarkeit

* Audiostream lesen
* Verzögerung
* Akkorderkennung

---

## Phase 2

Mac-Anwendung

* GUI
* große Akkordanzeige

---

## Phase 3

Remote-Anzeige

* Browser
* WebSocket
* QR-Code

---

## Phase 4

Optimierung

* bessere Akkorderkennung
* Glättung
* Tonarterkennung
* Vorhersage

---

# Fazit

Der ursprüngliche Ansatz, den Audiostream direkt auf Smartphones zu analysieren, stößt insbesondere auf iOS an systembedingte Grenzen.

Während der Exploration entstand deshalb eine deutlich elegantere Architektur.

Das MacBook übernimmt die komplette Audioverarbeitung, analysiert den Audiostream in Echtzeit und gibt ihn leicht verzögert wieder. Dadurch wird nicht nur der aktuelle Akkord erkannt, sondern es können bereits kommende Akkorde angezeigt werden.

Das Smartphone fungiert lediglich als drahtlose Fernanzeige und kommuniziert über das lokale WLAN mit dem MacBook.

Diese Architektur vermeidet sämtliche Einschränkungen der mobilen Betriebssysteme, ist technisch vergleichsweise einfach umzusetzen und bietet einen flüssigen Workflow ohne Dateiuploads oder Cloud-Verarbeitung.

Aus technischer Sicht erscheint dieser Ansatz als realistischer und vielversprechender erster Prototyp.

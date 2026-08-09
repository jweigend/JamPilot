# Eine Windows-Version — was wirklich fehlt

*Explorationsdokument. Status: Bestandsaufnahme am Quelltext, kein
Implementierungsplan. Geschrieben für den, der es irgendwann macht.*

*Nichts davon ist auf einer Windows-Maschine nachgemessen. Wo ich rate, steht,
dass ich rate — und wie man es in zehn Minuten nachprüft.*

---

## Nachtrag: gemessen, auf Windows 10 (Python 3.14, 64 bit)

*Der Text unten bleibt so stehen, wie er geschrieben wurde — er ist die
Vorhersage. Hier steht, was davon eingetroffen ist. Er hat gestimmt, bis auf
eine Ausnahme.*

- **Der Vollduplex-Test trägt.** Ein `sd.Stream` über zwei *verschiedene*
  WASAPI-Geräte öffnet ohne Murren; kein `paBadIODeviceCombination`. Der
  Umbau auf getrennte In-/Out-Streams entfällt also. (MME und DirectSound
  tragen ebenfalls. WDM-KS nicht — `Blocking API not supported yet`, was für
  uns egal ist.) Das war der einzige Punkt, der die Architektur hätte
  umwerfen können.
- **Die drei Stellen** sind behoben: `_nutzerkennung()` statt `os.getuid()` in
  [routing.py](../../jampilot/routing.py), die Lebendprüfung fasst `os.kill`
  außerhalb von POSIX nicht mehr an, und `engine._standardgeraet()` gibt
  außerhalb von Linux `None` statt `"default"`.
- **Was ohne eine einzige Änderung lief**, lief tatsächlich ohne eine einzige
  Änderung: numba/llvmlite haben cp314-Räder, das Kontrollfenster geht auf,
  die Weboberfläche liefert aus, der Verzögerungspuffer läuft, der gemessene
  Vorlauf steht. `selftest` ist voll grün, die Suite bis auf drei Tests, die
  an `Path("/opt/...")` hingen — ein Artefakt des Prüfers, kein Fehler
  (jetzt `PurePosixPath`).
- **Neu dazugekommen, weil es unter Linux nie auffiel:** Der Stream ist
  stereo, und das *Standard*-Eingabegerät ist unter Windows ein Mikrofon.
  Beides endete in Meldungen, die den Grund nicht nennen
  (`Invalid number of channels [PaErrorCode -9998]`) oder gar nicht erst
  auffallen (JamPilot verzögert klaglos den Raum statt der Musik). Beides
  fängt jetzt `_check_devices` bzw. ein Hinweis in `cmd_run` ab.
- **Bauskripte:** [run.ps1](../../run.ps1) + [run.cmd](../../run.cmd) statt
  eines Umschreibens nach Python — die Logik von `venv.sh` ist ein zweites Mal
  da, aber sie ist klein und steht damit in der Sprache, die auf der Plattform
  ohne Vorbedingung läuft. Zwei Windows-Eigenheiten, die im Text unten fehlen
  und beide Zeit gekostet haben: PowerShell 5.1 verliert eingebettete `"` beim
  Aufruf nativer Programme (`find_spec("numpy")` wird zu `find_spec(numpy)`),
  und ein Skript mit `param()`-Block versucht `--delay` als Parameternamen zu
  binden, statt es durchzureichen.
- **Offen geblieben:** `--bundle`. Nicht weil es nicht ginge, sondern weil die
  Frage am Ende dieses Dokuments (SmartScreen, Signatur) unbeantwortet ist.
  `run.cmd --bundle` sagt genau das und bricht ab.

---

## Ergebnis vorweg

Eine Windows-Version ist kein Umbau, sondern eine **Handvoll Stellen**. Der Kern
— Analyse, Kontrollfenster, Weboberfläche, Verzögerungspuffer — ist heute schon
plattformneutral und liefe unverändert. Was fehlt, ist genau ein Baustein: der
Weg, den Systemton **stumm** abzugreifen.

Und dieser Weg existiert im Code bereits. Es ist derselbe, den macOS geht:
JamPilot fasst das Audio-Routing nicht an, der Nutzer richtet einmalig ein
virtuelles Kabel ein. Unter macOS heißt es BlackHole, unter Windows VB-CABLE.
`--no-route` mit expliziten Geräten ist genau dieser Pfad, und er ist gebaut und
getestet — nur eben nie unter Windows gestartet.

Der Aufwand für den ehrlichen Weg liegt bei etwa **einem Tag**. Der unangenehme
Teil daran ist nicht der Code, sondern die Auslieferung (siehe ganz unten:
SmartScreen).

---

## Was ohne eine einzige Änderung liefe

| Baustein | Warum es trägt |
|---|---|
| Analyse (numpy, librosa, numba, scipy) | Windows-Wheels für alle, auch für llvmlite |
| Kontrollfenster ([gui.py](../../jampilot/gui.py)) | PySide6 hat ein Qt-Plattform-Plugin `windows`; die Ausschlussliste in der Spec lässt es stehen |
| Weboberfläche + QR ([web.py](../../jampilot/web.py)) | `ThreadingHTTPServer` aus der Standardbibliothek, `qrcode` über die SVG-Fabrik |
| Verzögerungspuffer ([delay_stream.py](../../jampilot/delay_stream.py)) | sounddevice bringt PortAudio unter Windows **im Wheel** mit — anders als unter Linux, wo es vom System kommt |
| Signalbehandlung | [cli.py:208](../../jampilot/cli.py#L208) und [gui.py:391](../../jampilot/gui.py#L391) fragen bereits `hasattr(signal, "SIGHUP")`, statt es vorauszusetzen |
| Doppelklick-Starter | [desktop.py:131](../../jampilot/desktop.py#L131) wirft für fremde Plattformen sauber `SystemExit`, statt Unsinn anzulegen |

Das ist mehr, als man erwartet, und es ist kein Zufall: Die plattformabhängigen
Teile sind von Anfang an in [routing.py](../../jampilot/routing.py) und
[desktop.py](../../jampilot/desktop.py) eingesperrt worden.

---

## Der eigentliche Punkt: das stumme Abgreifen

### Warum WASAPI-Loopback allein nicht reicht

Der erste Reflex ist falsch, und es lohnt sich, ihn ausdrücklich zu widerlegen —
sonst probiert ihn der Nächste wieder aus.

Windows kann Systemton **nativ** mitschneiden (WASAPI-Loopback), ohne
Fremdtreiber. Klingt nach der Lösung, ist aber keine: Loopback greift den Ton der
**echten Ausgabe** ab. Das Original bleibt hörbar. Man hörte also Original *und*
verzögerte Ausgabe gleichzeitig — genau die Kaskade, gegen die der Null-Sink
unter Linux überhaupt erst existiert (siehe den Kopf von
[routing.py](../../jampilot/routing.py#L1-L12)).

Für JamPilot ist Loopback also nur brauchbar, wenn man die echte Ausgabe stumm
schalten könnte, ohne dass der Mitschnitt mit verstummt. Das geht nicht: Sowohl
die Gerätestummschaltung als auch die App-Lautstärke im Mixer wirken **vor** dem
Punkt, an dem Loopback abgreift. Man schnitte Stille mit.

> **Nachtrag (nachgemessen): Der letzte Absatz ist zur Hälfte falsch.** Für die
> App-Lautstärke stimmt er — der Mitschnitt liefert dann Pakete, die als *silent*
> markiert sind und keinen Inhalt haben. Für die **Gerätestummschaltung stimmt er
> nicht**: Der Mute sitzt *hinter* dem Abgriff. Gemessen auf vier
> Treiberfamilien (Realtek HD Audio, NVIDIA HDMI, VB-Audio, Oculus), Peak am
> Abgriff jeweils exakt gleich der gesendeten Amplitude, stumm wie nicht stumm.
>
> Damit fällt die Begründung dieses ganzen Abschnitts: Der Null-Sink ist ein
> **zweiter, stummgeschalteter Ausgang** — ein ungenutzter HDMI- oder
> S/PDIF-Anschluss genügt. Der Mute ersetzt den **Treiber**, nicht das
> Umschalten des Standardgeräts: Umgebogen wird wie beim Kabel, gehört wird
> weiter auf den Lautsprechern. Gebaut in
> [`wincapture.py`](../../jampilot/wincapture.py) und
> `routing.WindowsMuteRouting`; VB-CABLE bleibt der Weg für Rechner, die
> wirklich nur einen einzigen Ausgang haben — und hat Vorrang, wo es installiert
> ist.
>
> *(Beim Bauen ist genau dieser Punkt einmal falsch herum gelandet: erst das
> Hörgerät stummgeschaltet und die Musik auf ein zweites Gerät geschoben. Das
> Programm lief dabei tadellos und tat das Gegenteil dessen, wofür es da ist —
> die teuerste Fehlersorte, die es hier gibt.)*
>
> Was der Absatz richtig gesehen hat: Ein *stummer Umweg* wird gebraucht,
> Loopback allein genügt nicht. Der Fehler lag nicht in der Frage, sondern in
> einer Annahme über den Treiber, die man hätte messen können — in zehn Minuten,
> genau wie den Vollduplex-Test weiter unten. Das ist die eigentliche Lehre
> dieses Dokuments, und sie hat hier ein zweites Mal zugeschlagen.

*(Nebenbei: sounddevice 0.5.5 gibt in `WasapiSettings` ohnehin nur `exclusive`,
`auto_convert` und `explicit_sample_format` nach außen — keinen
Loopback-Schalter. Neuere PortAudio-Bauten führen Loopback-Geräte stattdessen als
zusätzliche **Eingabegeräte** in der Geräteliste, erkennbar am Namenszusatz
`[Loopback]`. Ob das im Wheel-PortAudio von sounddevice drin ist, habe ich nicht
geprüft — für uns ist es aus dem Grund oben aber sowieso die falsche Fährte.)*

### Der richtige Weg: VB-CABLE ist das BlackHole von Windows

Das Muster ist identisch zu macOS:

1. Der Nutzer installiert VB-CABLE (oder VoiceMeeter) — ein virtuelles
   Ausgabegerät, dessen Ton nirgendwo hörbar herauskommt.
2. Er macht es zum Standardausgang. Die Player spielen unhörbar hinein.
3. JamPilot liest **„CABLE Output"** als ganz normales Aufnahmegerät — kein
   Loopback, keine Sonderbehandlung — und gibt verzögert auf die echten
   Lautsprecher aus.

Das ist im Code der `no_route`-Zweig in [engine.py:100](../../jampilot/engine.py#L100).
`routing.available()` prüft auf `pactl`, findet unter Windows keines, und die
Umleitung entfällt von selbst. Nichts daran muss neu erfunden werden.

### Ein Geschenk, das Linux nicht hat

Windows kann seit 10 im Lautstärkemixer **pro Anwendung** ein Ausgabegerät setzen
(*Einstellungen → System → Sound → Lautstärkemixer*).

Damit schickt man **nur den Browser** ins virtuelle Kabel; alles andere —
Systemtöne, Messenger, Videokonferenz — bleibt auf den Lautsprechern und normal
hörbar. Das ist strikt besser als der globale Null-Sink unter Linux, der den
gesamten Systemton umbiegt und deshalb überhaupt erst den Notausschalter in
[engine.py](../../jampilot/engine.py#L8-L13) nötig macht.

Wer die Windows-Version schreibt, sollte diesen Weg in die Anleitung nehmen, statt
den Linux-Ansatz nachzubauen.

---

## Die drei Stellen, die Windows sofort umbringen

Alle drei sind klein. Alle drei sind unvermeidbar.

**1. `os.getuid()` auf Modulebene** — [routing.py:29](../../jampilot/routing.py#L29)

```python
LOCK_FILE = Path(tempfile.gettempdir()) / f"jampilot-{os.getuid()}.pid"
```

`os.getuid` gibt es unter Windows nicht. Das ist keine Laufzeitfrage, sondern ein
`AttributeError` **beim Import** — und [engine.py:82](../../jampilot/engine.py#L82)
importiert `routing` bei jedem `start()`, auch wenn es hinterher gar nicht
gebraucht wird. JamPilot stürbe, bevor es irgendetwas tut.

Der Ausweg ist banal (`getpass.getuser()`, oder das ganze Modul unter Windows gar
nicht erst importieren) — aber es ist der harte Blocker, an dem der erste Versuch
scheitert, und er sieht nach nichts aus.

**2. `os.kill(pid, 0)` ist unter Windows kein Zustellversuch** — [routing.py:67](../../jampilot/routing.py#L67)

```python
os.kill(pid, 0)          # Signal 0 stellt nur zu, es passiert nichts
```

Der Kommentar stimmt unter POSIX. Unter Windows ruft `os.kill` für alles außer
`CTRL_C_EVENT`/`CTRL_BREAK_EVENT` schlicht `TerminateProcess` auf — es **beendet
den Prozess wirklich**, mit dem Signal als Exitcode. Eine Lebendprüfung, die ihr
Opfer umbringt.

Erreichbar wäre das nur, wenn jemand `routing` unter Windows doch benutzte (ohne
`pactl` passiert das nicht). Es ist trotzdem eine Falle, die man nicht stehen
lässt, weil sie beim Lesen wie das genaue Gegenteil dessen aussieht, was sie tut.

**3. Es gibt kein Gerät namens „default"** — [engine.py:100](../../jampilot/engine.py#L100)

```python
self._loop = DelayedLoopback(args.input or "default", args.output, ...)
```

sounddevice löst Gerätenamen per Teilstring-Suche auf. Unter Linux ist `default`
ein echter ALSA-/PulseAudio-Name; unter Windows existiert er nicht, und die Suche
endet mit einem `ValueError`. Für das Standardgerät ist die richtige Angabe
`None`, nicht der String.

*(Genau genommen ist das auch unter macOS schon eine Unsauberkeit — sie fällt dort
nur nicht auf, weil der BlackHole-Pfad ohnehin `--input` verlangt.)*

---

## Das eine Risiko, das man zuerst messen muss

[delay_stream.py:73](../../jampilot/delay_stream.py#L73) öffnet **einen einzigen
Vollduplex-Stream über zwei verschiedene Geräte**:

```python
self._stream = sd.Stream(device=(input_device, output_device), ...)
```

Unter Windows wären das das virtuelle Kabel (rein) und die Lautsprecher (raus) —
zwei physisch getrennte Geräte mit **unabhängigen Uhren**. CoreAudio kann das,
ALSA/Pulse kann das. Ob PortAudios WASAPI-Backend das mitmacht oder mit
`paBadIODeviceCombination` abwinkt, **weiß ich nicht**. Diesen Fehlercode gibt es
in PortAudio genau für diesen Fall, und er wäre der wahrscheinlichste erste
Absturz nach den drei Punkten oben.

Der Test dafür ist ein Zehnzeiler auf irgendeiner Windows-Kiste — und er muss
**vor** allem anderen laufen, weil er als Einziger die Architektur in Frage
stellen kann:

```python
import sounddevice as sd
print(sd.query_devices())               # welche Namen hat das Kabel wirklich?
with sd.Stream(device=("CABLE Output", "Lautsprecher"), samplerate=48000):
    pass                                # trägt oder wirft — mehr will man nicht wissen
```

**Falls es wirft:** kein Drama, aber Arbeit. Man trennt in `sd.InputStream` +
`sd.OutputStream` mit dem Ringpuffer dazwischen, den JamPilot ohnehin schon führt.
Bei mehreren *Sekunden* Verzögerung ist die Uhrdrift zweier Geräte (einige ppm)
vollkommen belanglos — der Puffer schluckt sie. Es ist also eine mechanische
Umschreibung, keine konzeptionelle. Aber sie trifft die zentrale Klasse, und
deshalb will man das Ergebnis **kennen, bevor** man einen Tag in Bauskripte steckt.

---

## Bauen

[run.sh](../../run.sh), [packaging/build.sh](../../packaging/build.sh) und
[packaging/venv.sh](../../packaging/venv.sh) sind Bash und kennen nur
`.venv/bin/python`; unter Windows heißt es `.venv/Scripts/python.exe`. Es braucht
also ein PowerShell-Pendant — oder, wahrscheinlich klüger, man schreibt die Logik
einmal in Python um, statt sie ein drittes Mal zu haben.

Die Spec selbst läuft durch: [packaging/jampilot.spec](../../packaging/jampilot.spec)
enthält nichts Unix-Eigenes, das `BUNDLE` ist schon hinter `sys.platform ==
"darwin"` weggesperrt. Das Ergebnis heißt dann `jampilot.exe`, worauf `build.sh`
an mehreren Stellen (`-x dist/jampilot`, `du -h dist/jampilot`) nicht vorbereitet
ist.

In [.github/workflows/build.yml](../../.github/workflows/build.yml) kommt
`windows-latest` in die Matrix. Der PortAudio-Schritt entfällt dort (das Wheel
bringt die DLL mit), der Info.plist-Schritt sowieso.

**Offen: hält die Bitgleichheit?** Der `--check` beweist heute unter Linux und
macOS, dass zwei Bauten aus denselben Quellen bitgenau dasselbe ergeben —
`PYTHONHASHSEED=0` war dafür der entscheidende Hebel. Unter Windows trägt das
PE-Format zusätzlich einen **Zeitstempel im Header**. Ob PyInstaller den
normalisiert, weiß ich nicht. Sollte er es nicht, ist der `--check` dort
schlicht nicht erfüllbar, und das muss man dann ehrlich hinschreiben, statt die
Prüfung stillschweigend zu überspringen.

---

## Der unangenehme Teil ist nicht der Code

**SmartScreen und Virenscanner.** Eine unsignierte PyInstaller-onefile-Exe von
gut 200 MB, die sich beim Start selbst nach `%TEMP%` entpackt, sieht für jede
Heuristik aus wie ein Packer — weil sie technisch einer ist. Zu erwarten sind:

- *„Der Computer wurde durch Windows geschützt"* bei jedem Nutzer, bei jedem
  Download. Wegklickbar, aber es kostet Vertrauen.
- Gelegentliche Fehlalarme einzelner Scanner.

Dagegen hilft nur ein Codesignatur-Zertifikat (laufende Kosten, Jahresgebühr) oder
die Auslieferung als **onedir im ZIP** statt als eine Datei. Letzteres wäre
ohnehin der schnellere Start (~0,45 s statt ~2,5 s, siehe die Notiz in der Spec) —
man verlöre nur das schöne Versprechen „eine Datei".

Das ist eine **Produktentscheidung, keine technische**, und sie sollte gefallen
sein, bevor jemand anfängt.

**Firewall.** Der Webserver lauscht auf `0.0.0.0` ([web.py:191](../../jampilot/web.py#L191)) —
beim ersten Start erscheint der Windows-Firewall-Dialog. Klickt der Nutzer ihn
weg, ist der QR-Code wertlos: Das Handy kommt nicht durch. Das gehört in die
Anleitung, sonst sucht jemand eine Stunde lang den Fehler bei sich.

---

## Was ich täte, in dieser Reihenfolge

1. **Den Vollduplex-Test** auf einer Windows-Kiste. Zehn Minuten, und er ist der
   einzige Punkt, der die Architektur umwerfen kann.
2. Die **drei Stellen** oben plattformfest machen. Eine Stunde.
3. VB-CABLE, Geräte von Hand über `--input`/`--output` gewählt, und einmal einen
   Song durchhören. Damit steht oder fällt die Behauptung „läuft unter Windows".
4. Erst **danach** Bauskript, CI-Job und README-Abschnitt.

Was ich **weglassen** würde: das automatische Umschalten des Standard-Ausgabe­geräts,
also das Windows-Gegenstück zum Null-Sink-Kunststück aus
[routing.py](../../jampilot/routing.py). Es ginge über die undokumentierte
COM-Schnittstelle `IPolicyConfig` oder ein Fremdwerkzeug wie `nircmd` — beides
Dinge, die man einem Musiker nicht auf den Rechner legt, und beides ein weiterer
Tag. Der Nutzer klickt das einmalig selbst; macOS verlangt seit jeher genau das,
und niemand hat sich beschwert.

Die Windows-Version ist damit ehrlicherweise die **macOS-Version mit anderem
Kabelnamen** — und das ist die gute Nachricht.

---

## Nachtrag: das Weggelassene ist doch gebaut worden

*Der Abschnitt oben bleibt stehen, wie er geschrieben wurde. Er ist die
Begründung, die zur ersten Windows-Fassung geführt hat, und die war richtig:
Erst musste feststehen, dass die Architektur trägt. Die Empfehlung selbst hat
sich danach aber nicht gehalten.*

**Was sie umgeworfen hat.** Der erste Start auf einer echten Windows-Kiste
scheiterte an der Meldung „Das Standard-Eingabegerät hat 1 Kanal". Danach lautete
die Anleitung: Systemton in den Lautstärkemixer umhängen, `jampilot devices`
lesen, `--input` und `--output` heraussuchen. Und das ging nicht einmal wie
dokumentiert — `--input "CABLE Output"` stirbt mit „Multiple input devices
found", weil derselbe Endpunkt unter MME, DirectSound, WASAPI und WDM-KS
zugleich geführt wird. Vier Namen, von denen nur einer die Kanalzahl ehrlich
meldet.

Das ist die eigentliche Erkenntnis, und sie stand oben noch nicht drin: Der
Handbetrieb ist unter Windows **nicht** so einfach wie unter macOS. Dort gibt es
ein „BlackHole 2ch", hier gibt es dasselbe Kabel viermal. Die Rechnung „der
Nutzer klickt das einmalig selbst" ging deshalb nicht auf — nicht, weil das
Klicken zu viel wäre, sondern weil danach noch die Geräteauswahl kommt.

**Was es tatsächlich gekostet hat.** Keinen Tag und kein Fremdwerkzeug: rund 200
Zeilen `ctypes` in [winaudio.py](../../jampilot/winaudio.py) —
`IMMDeviceEnumerator` zum Auflisten, `IPolicyConfig` zum Setzen. Keine neue
Abhängigkeit (comtypes und pycaw bauen genau diese vtables, mehr nicht), keine
Administratorrechte, nichts, was auf dem Rechner zurückbleibt. Der Einwand
„Dinge, die man einem Musiker nicht auf den Rechner legt" traf `nircmd`; auf
Code im eigenen Prozess trifft er nicht.

**Was dazugehörte und nicht offensichtlich war.**

- Die Umstellung **überlebt den Prozess**. Unter Linux verschwindet der
  Null-Sink mit dem Programm; unter Windows bliebe das Kabel Standardausgang
  über einen Neustart hinaus. Das Ziel muss also auf die Platte, *bevor*
  umgestellt wird, und `cleanup` darf nur zurückstellen, wenn der Standard
  wirklich noch am Kabel hängt.
- `os.kill(pid, 0)` ist unter Windows **keine Frage, sondern ein Todesurteil**
  (es ruft TerminateProcess). Die Lebendprüfung für die Sperrdatei braucht
  `OpenProcess` + `GetExitCodeProcess`.
- Das **Konsolenfenster zumachen** löst kein Signal aus, sondern
  `CTRL_CLOSE_EVENT`. Ohne `SetConsoleCtrlHandler` bliebe der Rechner nach einer
  Handlung stumm, die vor dieser Umleitung völlig harmlos war — siehe
  [cli.py](../../jampilot/cli.py), `_beim_schliessen_der_konsole`.
- Windows hat ein **eigenes Standardgerät für Telefonie**. Es unangetastet zu
  lassen kostet nichts und hält Teams, Discord und Zoom aus dem Vier-Sekunden-
  Puffer heraus. Das ist der eine Punkt, an dem die Windows-Fassung **besser**
  ist als die Linux-Referenz.

**Was von „Ein Geschenk, das Linux nicht hat" bleibt.** Das App-weise Routing im
Lautstärkemixer ist weiterhin der feinere Weg, wenn man *nur* den Browser
verzögern will — es steht als `--no-route`-Variante in der Anleitung. Als
Standardweg taugt es nicht: Es verlangt genau die Geräteauswahl von Hand, an der
der erste Versuch gescheitert ist.

Die Windows-Version ist damit **nicht** die macOS-Version mit anderem Kabelnamen,
sondern die Linux-Version mit anderem Null-Sink. macOS ist jetzt die einzige
Plattform, auf der noch von Hand gewählt wird — dort fehlt das Gegenstück
(`AudioObjectSetPropertyData` auf `kAudioHardwarePropertyDefaultOutputDevice`),
und das ist die nächste Baustelle, nicht mehr diese.

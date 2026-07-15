# Eine Windows-Version — was wirklich fehlt

*Explorationsdokument. Status: Bestandsaufnahme am Quelltext, kein
Implementierungsplan. Geschrieben für den, der es irgendwann macht.*

*Nichts davon ist auf einer Windows-Maschine nachgemessen. Wo ich rate, steht,
dass ich rate — und wie man es in zehn Minuten nachprüft.*

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

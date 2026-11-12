"""Erzeugt die Screenshots des README - aus der echten Seite, mit echter Analyse.

Nichts hier ist gemalt. Der Weg ist derselbe wie im Betrieb, nur ohne
Soundkarte:

1. Die LIVE-Analyse (cli._display_loop, Hop fuer Hop, mit Beat-Tracker)
   laeuft ueber die Referenzaufnahmen aus tests/reference/. Jeder Zustand,
   den sie an die Anzeige schicken wuerde, wird mitgeschrieben - Akkorde,
   Taktstriche, Huellkurve, Tonart.
2. Ein echter Webserver (web.start) spielt diese Zustaende in Echtzeit an
   eine echte Seite (data/index.html) aus.
3. Chrome zeigt sie ohne Fenster (headless) und wird im gewuenschten Moment
   fotografiert. Einstellungen kommen dorthin, wo der Nutzer sie auch
   hinlegt: in den localStorage der Seite.

Das Kontrollfenster ist Qt und wird ueber die Offscreen-Plattform
aufgenommen - deshalb ohne die Titelleiste des Desktops.

Was die Bilder NICHT verraten sollen: Der QR-Code traegt im Betrieb die
Adresse des Rechners samt Session-Token. Hier laeuft der Server mit einem
Wegwerf-Token (eigenes XDG_CONFIG_HOME) und der Code zeigt auf eine
Beispieladresse.

    .venv/bin/python docs/bilder/make-screenshots.py            # alle Bilder
    .venv/bin/python docs/bilder/make-screenshots.py hero.png   # nur dieses
    ... --out /tmp/probe      woandershin schreiben (zum Ansehen vor dem Ersetzen)
    ... --cache DIR           die Analyse-Mitschnitte wiederverwenden (~75 s je Titel)

Braucht google-chrome (oder chromium) im Pfad. Sonst nichts ausser dem, was
JamPilot ohnehin braucht: Das bisschen DevTools-Protokoll unten spricht die
Standardbibliothek.
"""

import argparse
import base64
import contextlib
import io
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

PROJEKT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "tests" / "reference"))

BREITE, HOEHE = 1920, 1200        # wie die bisherigen Bilder
HOP = 0.25                        # Abstand der Zustaende, wie live
VORLAUF = 12.0                    # so lange laeuft die Seite vor dem Foto
MITSCHNITT_SEKUNDEN = 100.0       # so viel vom Titel wird analysiert
BEISPIEL_ADRESSE = "http://192.168.1.42:8765/"

# Jede Szene: Titel, hoerbare Position des Fotos, Einstellungen der Seite.
# Die Positionen sind von Hand gewaehlt (Akkord steht, der naechste ist auf
# dem Laufband zu sehen) - aendert sich die Analyse, wandern die Wechsel, und
# die Zeiten hier muessen nachgezogen werden. `python ... --events let_it_be`
# listet, was wo liegt.
SZENEN = {
    # Let It Be: G klingt (die 5 in C-Dur), F und C kommen.
    "hero.png": dict(titel="let_it_be", t=34.75),
    # It's Too Late: Gm7 als Barre, C7 und Fmaj7 auf dem Band.
    "guitar.png": dict(titel="its_too_late", t=22.55,
                       speicher={"jampilot.instrument": "guitar"}),
    # It's Too Late: Fmaj7 auf den Tasten, Dm7 kommt.
    "keys.png": dict(titel="its_too_late", t=42.0,
                     speicher={"jampilot.instrument": "keys"}),
    # Something: F klingt, der Bass geht gleich aufs E (C/E).
    "bass.png": dict(titel="something", t=50.9,
                     speicher={"jampilot.instrument": "bass"}),
    # Record-Modus im Gitarrenmodus: Em7 klingt, Am7 kommt.
    "record-mode.png": dict(titel="its_too_late", t=46.4,
                            speicher={"jampilot.instrument": "guitar"},
                            zustand={"recording": True}),
}
# Ausschnitte: dieselbe Seite, nur ein Teil davon. `dialog` oeffnet das
# Zahnrad und schneidet den Abschnitt mit dieser Ueberschrift aus.
AUSSCHNITTE = {
    "connect-your-phone.png": dict(szene="hero.png", element="#qrbox", rand=20, zoom=1.5),
    "keypin.png": dict(szene="keys.png", dialog="Key"),
    "nashville.png": dict(szene="keys.png", dialog="Scale degrees"),
}


# --- 1. Die Analyse mitschneiden --------------------------------------------

def mitschnitt(titel: str, cache: Path) -> list[dict]:
    """Alle Anzeigezustaende der Live-Analyse ueber den Titelanfang."""
    datei = cache / f"{titel}.json"
    if datei.exists():
        return json.loads(datei.read_text())

    import librosa
    import numpy as np

    import messung_live_pfad as m           # FakeLoop + synchroner Beat-Tracker
    from jampilot import beats, cli

    print(f"  analysiere {titel} ({MITSCHNITT_SEKUNDEN:.0f} s) ...", flush=True)
    y, _ = librosa.load(str(PROJEKT / "tests" / "reference" / f"{titel}.mp3"),
                        sr=m.SR, mono=True, duration=MITSCHNITT_SEKUNDEN)
    zustaende = []

    class Rekorder:
        def publish(self, zustand):
            zustaende.append(json.loads(json.dumps(zustand)))

    stop = threading.Event()
    loop = m.FakeLoop(y.astype(np.float32), 5.0, stop)
    args = argparse.Namespace(samplerate=m.SR, delay=5.0, record_buffer=0)
    original = beats.BeatTracker.create
    beats.BeatTracker.create = classmethod(lambda cls: m.SyncTracker())
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            cli._display_loop(loop, args, Rekorder(), stop=stop)
    finally:
        beats.BeatTracker.create = original
    cache.mkdir(parents=True, exist_ok=True)
    datei.write_text(json.dumps(zustaende))
    return zustaende


def events_zeigen(titel: str, cache: Path):
    gesehen = {}
    for zustand in mitschnitt(titel, cache):
        for e in zustand.get("committed", []):
            gesehen[e["at"]] = e
    for at, e in sorted(gesehen.items()):
        print(f"  {at:6.1f} s   {e['c']:<8s} Bass {e.get('b') or '-'}")


# --- 2. Chrome fernsteuern (DevTools-Protokoll ueber einen WebSocket) --------

class Chrome:
    """Ein fensterloses Chrome und EINE Seite darin.

    Der WebSocket ist von Hand gesprochen: Handshake, maskierte Textframes
    hin, beliebig gestueckelte Frames zurueck. Das sind vierzig Zeilen - und
    eine Abhaengigkeit weniger, die nur dieses Skript braeuchte.
    """

    def __init__(self):
        programm = next((p for p in ("google-chrome", "chromium",
                                     "chromium-browser") if shutil.which(p)), None)
        if programm is None:
            raise SystemExit("google-chrome oder chromium wird gebraucht.")
        self._profil = tempfile.mkdtemp(prefix="jampilot-shots-")
        with socket.socket() as s:              # freien Port erfragen
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self._prozess = subprocess.Popen(
            [programm, "--headless=new", f"--remote-debugging-port={port}",
             f"--user-data-dir={self._profil}", "--no-first-run",
             "--hide-scrollbars", "--force-device-scale-factor=1",
             f"--window-size={BREITE},{HOEHE}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ziel = None
        for _ in range(100):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/json/list", timeout=1) as antwort:
                    seiten = [z for z in json.loads(antwort.read())
                              if z.get("type") == "page"]
                if seiten:
                    ziel = seiten[0]["webSocketDebuggerUrl"]
                    break
            except OSError:
                pass
            time.sleep(0.1)
        if ziel is None:
            self.schliessen()
            raise SystemExit("Chrome hat keine Seite geoeffnet.")
        pfad = ziel.split(f":{port}", 1)[1]
        self._sock = socket.create_connection(("127.0.0.1", port), timeout=30)
        self._sock.sendall((
            f"GET {pfad} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {base64.b64encode(os.urandom(16)).decode()}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n").encode())
        kopf = b""
        while b"\r\n\r\n" not in kopf:
            kopf += self._sock.recv(1)
        if b" 101 " not in kopf.split(b"\r\n", 1)[0]:
            raise SystemExit(f"Kein WebSocket: {kopf[:80]!r}")
        self._id = 0
        self.ruf("Emulation.setDeviceMetricsOverride", width=BREITE, height=HOEHE,
                 deviceScaleFactor=1, mobile=False)

    def _lies(self, n: int) -> bytes:
        daten = b""
        while len(daten) < n:
            stueck = self._sock.recv(n - len(daten))
            if not stueck:
                raise ConnectionError("Chrome hat die Verbindung geschlossen")
            daten += stueck
        return daten

    def _nachricht(self) -> dict:
        text = b""
        while True:
            b0, b1 = self._lies(2)
            laenge = b1 & 0x7F
            if laenge == 126:
                laenge = struct.unpack(">H", self._lies(2))[0]
            elif laenge == 127:
                laenge = struct.unpack(">Q", self._lies(8))[0]
            inhalt = self._lies(laenge)
            if b0 & 0x0F in (0x0, 0x1):           # Text oder Fortsetzung
                text += inhalt
                if b0 & 0x80:                     # letztes Stueck
                    return json.loads(text)

    def ruf(self, methode: str, **parameter) -> dict:
        self._id += 1
        inhalt = json.dumps({"id": self._id, "method": methode,
                             "params": parameter}).encode()
        maske = os.urandom(4)
        kopf = bytes([0x81])
        if len(inhalt) < 126:
            kopf += bytes([0x80 | len(inhalt)])
        elif len(inhalt) < 65536:
            kopf += bytes([0x80 | 126]) + struct.pack(">H", len(inhalt))
        else:
            kopf += bytes([0x80 | 127]) + struct.pack(">Q", len(inhalt))
        self._sock.sendall(kopf + maske + bytes(
            b ^ maske[i % 4] for i, b in enumerate(inhalt)))
        while True:                               # Ereignisse ueberlesen
            antwort = self._nachricht()
            if antwort.get("id") == self._id:
                if "error" in antwort:
                    raise RuntimeError(f"{methode}: {antwort['error']}")
                return antwort.get("result", {})

    def js(self, ausdruck: str):
        ergebnis = self.ruf("Runtime.evaluate", expression=ausdruck,
                            returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in ergebnis:
            raise RuntimeError(f"JS: {ergebnis['exceptionDetails'].get('text')} "
                               f"in {ausdruck[:80]}")
        return ergebnis.get("result", {}).get("value")

    def oeffnen(self, url: str, speicher: dict):
        """Seite laden - mit genau diesen Einstellungen und keinen anderen."""
        self.ruf("Page.navigate", url=url)
        self._warten()
        self.js("localStorage.clear();" + "".join(
            f"localStorage.setItem({json.dumps(k)}, {json.dumps(v)});"
            for k, v in speicher.items()))
        self.ruf("Page.reload")
        self._warten()

    def _warten(self):
        for _ in range(100):
            time.sleep(0.1)
            try:
                if self.js("document.readyState") == "complete":
                    return
            except RuntimeError:
                pass                              # mitten im Seitenwechsel
        raise SystemExit("Die Seite laedt nicht.")

    def foto(self, ziel: Path, ausschnitt: dict | None = None):
        parameter = {"format": "png"}
        if ausschnitt:
            parameter["clip"] = ausschnitt
        bild = self.ruf("Page.captureScreenshot", **parameter)["data"]
        ziel.write_bytes(base64.b64decode(bild))
        print(f"  {ziel.name}")

    def schliessen(self):
        with contextlib.suppress(Exception):
            self._sock.close()
        self._prozess.terminate()
        with contextlib.suppress(Exception):
            self._prozess.wait(timeout=5)
        shutil.rmtree(self._profil, ignore_errors=True)


# --- 3. Die Szene abspielen und fotografieren --------------------------------

def szene_stellen(chrome: Chrome, szene: dict, cache: Path):
    """Seite oeffnen, den Mitschnitt bis zur Fotoposition abspielen.

    Kehrt zurueck, sobald die Position erreicht ist; die Wiedergabe laeuft
    im Hintergrund weiter (die Seite soll nicht einfrieren, waehrend Chrome
    das Bild holt). Der Aufrufer ruft `beenden()`.
    """
    from jampilot import web

    zustaende = mitschnitt(szene["titel"], cache)
    anzeige = web.start(0)
    # Der QR-Code des Betriebs traegt die Adresse dieses Rechners. Ins README
    # gehoert eine, die niemandem gehoert.
    token = anzeige.url.split("?k=", 1)[1]
    anzeige._handler.qr_bytes = web._qr_svg(f"{BEISPIEL_ADRESSE}?k={token}")
    port = anzeige.url.split(":")[2].split("/")[0]
    chrome.oeffnen(f"http://127.0.0.1:{port}/?k={token}", szene.get("speicher", {}))

    erreicht, ende = threading.Event(), threading.Event()

    def abspielen():
        naechster = time.monotonic()
        for zustand in zustaende:
            if zustand["t"] < szene["t"] - VORLAUF:
                continue
            if ende.is_set():
                return
            anzeige.broadcaster.publish({**zustand, **szene.get("zustand", {})})
            if zustand["t"] >= szene["t"]:
                erreicht.set()
            naechster += HOP
            time.sleep(max(0.0, naechster - time.monotonic()))
        erreicht.set()

    threading.Thread(target=abspielen, daemon=True).start()
    if not erreicht.wait(VORLAUF + 30):
        raise SystemExit("Die Fotoposition wurde nicht erreicht.")

    def beenden():
        ende.set()
        anzeige.stop()
    return beenden


RECHTECK = """(() => {
  const r = document.querySelector(%s).getBoundingClientRect();
  return {x: r.left, y: r.top, width: r.width, height: r.height};
})()"""

# Der Abschnitt eines Dialogs: von seiner Ueberschrift bis vor die naechste.
ABSCHNITT = """(() => {
  const dialog = document.getElementById("dialog");
  const koepfe = [...dialog.querySelectorAll("h2")];
  const i = koepfe.findIndex(h => h.textContent.trim() === %s);
  koepfe[i].scrollIntoView({block: "start"});
  // Der Text der Ueberschrift, nicht ihr Kasten: Der traegt oben den
  // Trennstrich zum Abschnitt davor, und der gehoert nicht ins Bild.
  const bereich = document.createRange();
  bereich.selectNodeContents(koepfe[i]);
  const d = dialog.getBoundingClientRect(), oben = bereich.getBoundingClientRect();
  const unten = i + 1 < koepfe.length
      ? koepfe[i + 1].getBoundingClientRect().top - 14
      : dialog.lastElementChild.getBoundingClientRect().bottom + 12;
  const stil = getComputedStyle(dialog);
  const links = d.left + parseFloat(stil.paddingLeft) - 12;
  const rechts = d.right - parseFloat(stil.paddingRight) + 12;
  return {x: links, y: oben.top - 10, width: rechts - links,
          height: unten - oben.top + 10};
})()"""


def alle_bilder(ziel: Path, cache: Path, nur: set[str]):
    chrome = Chrome()
    try:
        for name, szene in SZENEN.items():
            abhaengige = {n: a for n, a in AUSSCHNITTE.items()
                          if a["szene"] == name and (not nur or n in nur)}
            if nur and name not in nur and not abhaengige:
                continue
            beenden = szene_stellen(chrome, szene, cache)
            try:
                if not nur or name in nur:
                    chrome.foto(ziel / name)
                for n, a in abhaengige.items():
                    if "element" in a:
                        r = chrome.js(RECHTECK % json.dumps(a["element"]))
                        rand = a.get("rand", 0)
                        chrome.foto(ziel / n, {
                            "x": r["x"] - rand, "y": r["y"] - rand,
                            "width": r["width"] + 2 * rand,
                            "height": r["height"] + 2 * rand,
                            "scale": a.get("zoom", 1)})
                    else:
                        chrome.js('document.getElementById("gear").click()')
                        time.sleep(0.4)
                        r = chrome.js(ABSCHNITT % json.dumps(a["dialog"]))
                        chrome.foto(ziel / n, {**r, "scale": 1})
                        chrome.js('document.dispatchEvent(new KeyboardEvent('
                                  '"keydown", {key: "Escape"}))')
            finally:
                beenden()
    finally:
        chrome.schliessen()


# --- Das Kontrollfenster ----------------------------------------------------

def kontrollfenster(ziel: Path):
    """Das Qt-Fenster im laufenden Betrieb, in doppelter Aufloesung.

    In einem eigenen Prozess: Die Offscreen-Plattform muss stehen, BEVOR Qt
    geladen wird. Die doppelte Aufloesung kommt vom Zeichnen in ein Bild mit
    doppelter Pixeldichte und NICHT ueber QT_SCALE_FACTOR: Der Offscreen-
    Bildschirm ist 800x800 gross, mit Faktor 2 also nur 400 Punkte hoch - das
    Fenster passte nicht mehr darauf und wurde zusammengedrueckt.
    """
    programm = r'''
import sys
from types import SimpleNamespace
from PySide6.QtCore import QPoint
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication
from jampilot import cli, gui

app = QApplication([])
engine = SimpleNamespace(
    running=True, muted=False, delay_seconds=5.0, lead=4.0, status="running",
    fehler=None, start=lambda: None, stop=lambda: None, toggle_mute=lambda: False,
    recording=False, record_paused=False, record_offset=0.0,
    jetzt=cli._live_zeile("G", "F", 0.7, "C major"))
fenster = gui.Fenster(engine, sys.argv[2])
# Wie gui.run(): Das Fenster oeffnet sich im Startzustand (der laengste
# Text bestimmt die Groesse) und laeuft dann an.
fenster.startet = True
fenster.nachziehen()
fenster.show()
app.processEvents()
fenster.startet = False
fenster.nachziehen()
app.processEvents()
bild = QPixmap(fenster.size() * 2)
bild.setDevicePixelRatio(2)
fenster.render(bild, QPoint(0, 0))
bild.save(sys.argv[1])
'''
    umgebung = {**os.environ, "QT_QPA_PLATFORM": "offscreen",
                "PYTHONPATH": str(PROJEKT)}
    subprocess.run([sys.executable, "-c", programm, str(ziel),
                    f"{BEISPIEL_ADRESSE}?k=3f9aXq7LmPw"],
                   check=True, env=umgebung, stderr=subprocess.DEVNULL)
    print(f"  {ziel.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("bilder", nargs="*", help="nur diese Dateien (Standard: alle)")
    parser.add_argument("--out", type=Path, default=Path(__file__).parent)
    parser.add_argument("--cache", type=Path,
                        default=Path(tempfile.gettempdir()) / "jampilot-screenshots")
    parser.add_argument("--events", metavar="TITEL",
                        help="die Akkordwechsel eines Titels auflisten und enden")
    args = parser.parse_args()

    if args.events:
        events_zeigen(args.events, args.cache)
        return
    bekannt = {*SZENEN, *AUSSCHNITTE, "controllwindow.png"}
    unbekannt = set(args.bilder) - bekannt
    if unbekannt:
        raise SystemExit(f"Unbekannt: {', '.join(sorted(unbekannt))}. "
                         f"Es gibt: {', '.join(sorted(bekannt))}")
    nur = set(args.bilder)
    args.out.mkdir(parents=True, exist_ok=True)

    # Wegwerf-Token statt des echten aus ~/.config/jampilot (web.py).
    with tempfile.TemporaryDirectory() as konfiguration:
        os.environ["XDG_CONFIG_HOME"] = konfiguration
        if not nur or nur - {"controllwindow.png"}:
            alle_bilder(args.out, args.cache, nur - {"controllwindow.png"})
    if not nur or "controllwindow.png" in nur:
        kontrollfenster(args.out / "controllwindow.png")


if __name__ == "__main__":
    main()

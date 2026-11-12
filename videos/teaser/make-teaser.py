"""Der 40-Sekunden-Teaser: aus der Play-along-Aufnahme, aber neu gebaut.

Was hier anders ist als ein Zusammenschnitt der Bildschirmaufnahme:

* Der Ton laeuft DURCH (ein Refrain am Stueck), und jedes Bild passt dazu.
  Die Anzeige wird nicht aus der Aufnahme geschnitten, sondern neu erzeugt:
  Die Live-Analyse (cli._display_loop) laeuft ueber die Tonspur der Aufnahme,
  und die echte Seite (data/index.html) zeigt das Ergebnis - in Full HD, mit
  dem heutigen Laufband, in allen vier Ansichten gleichzeitig und synchron.
* Aus der Aufnahme selbst kommt das Bild des Spielers (der Ausschnitt unten
  rechts) und der Ton.
* Gerendert wird Bild fuer Bild: Chrome laeuft mit angehaltener Uhr, die das
  Skript um genau 1/30 s je Bild weiterstellt. Nichts ruckelt, und zwei
  Laeufe ergeben denselben Film.

    .venv/bin/python videos/teaser/make-teaser.py              # der ganze Film
    .venv/bin/python videos/teaser/make-teaser.py --bild 12.5  # ein Standbild
    .venv/bin/python videos/teaser/make-teaser.py --von 9 --bis 16   # ein Stueck

Braucht ffmpeg und google-chrome. Die Aufnahme (QUELLE) und der Sprecher
(SPRECHER) liegen ausserhalb bzw. neben dem Skript; Zwischenstaende (Analyse,
Einzelbilder des Spielers) landen im Cache-Ordner.
"""

import argparse
import contextlib
import importlib.util
import io
import json
import os
import base64
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HIER = Path(__file__).resolve().parent
PROJEKT = HIER.parents[1]
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "tests" / "reference"))

QUELLE = Path.home() / "Downloads" / ("JamPilot Play Along - Ella Langley - "
                                      "Weren't for the wind..mp4")
SPRECHER = HIER.parent / "JamPilot-teaser-voiceover.mp3"
AUSGABE = HIER.parent / "JamPilot-teaser-40s.mp4"

FPS = 30
DAUER = 40.0
# Wo im Song der Film beginnt. 35,3 s ist die Eins des letzten Strophentakts
# (A); 3,2 s spaeter setzt der Refrain ein (E - D - F#m - A, zweimal). Alle
# Szenengrenzen unten liegen auf Akkordwechseln dieses Refrains.
SONG_AB = 35.30
VORLAUF = 14.0              # so lange laufen die Anzeigen vor dem ersten Bild

# Der Spieler in der Aufnahme (1280x720): Ausschnitt unten rechts.
PIP_AUSSCHNITT = "497:280:783:426"

SZENEN = {
    "live": 3.2,            # "You hear the song ..."      Bass + Spieler
    "was": 9.5,             # "Chords, key, timing ..."    Akkordansicht, Rahmen
    "raster": 15.8,         # "Connect your band ..."      vier Ansichten
    "spiel": 22.1,          # "Stop guessing ..."          Bass + Spieler
    "ende": 28.0,           # Endkarte
}

# Der Sprecher: (Einsatz im Film, Anfang und Ende in der Sprecherdatei). Die
# Schnittpunkte sind die gemessenen Pausen der Datei (ffmpeg silencedetect).
SPRECHER_SCHNITTE = [
    (0.90, 0.15, 1.80),     # Your next jam starts here.
    (3.95, 2.65, 3.80),     # You hear the song.
    (5.90, 4.60, 7.05),     # JamPilot shows you what to play - live.
    (11.70, 7.85, 11.15),   # Chords, key, timing, and what's coming next.
    (16.60, 11.95, 14.95),  # Connect your band on any screen and stay in the groove.
    (22.80, 15.75, 16.85),  # Stop guessing.
    (24.30, 17.68, 18.72),  # Start playing.
    (28.90, 19.52, 21.87),  # JamPilot - jam along with anything.
    (32.00, 22.68, 26.82),  # Available for your computer - Windows, Linux, and macOS.
    (36.80, 27.66, 29.45),  # Get it at jampilot.org.
]

ZEITPLAN = {
    "szenen": SZENEN,
    # Die Hinweisrahmen kommen mit dem Wort: Chords / key / timing / next.
    "rahmen": [11.75, 12.45, 13.00, 13.85],
    "pip": {"x": 1304, "y": 318, "breite": 600,
            "sichtbar": [[3.55, 9.45], [22.7, 27.95]], "ab": 3.2},
    "untertitel": [
        {"a": 3.90, "b": 5.75, "teile": [{"t": 3.90, "html": "You hear the song."}]},
        {"a": 5.85, "b": 9.25, "teile": [
            {"t": 5.85, "html": "JamPilot shows you what to play "},
            {"t": 7.40, "html": "&mdash; <b>live</b>."}]},
        {"a": 11.65, "b": 15.50, "teile": [
            {"t": 11.65, "html": "Chords, "}, {"t": 12.40, "html": "key, "},
            {"t": 12.95, "html": "timing "},
            {"t": 13.75, "html": "&mdash; and <b>what&rsquo;s coming next</b>."}]},
        {"a": 16.55, "b": 21.80, "teile": [
            {"t": 16.55, "html": "Connect your band on <b>any screen</b>. "},
            {"t": 18.35, "html": "Stay in the groove."}]},
        {"a": 22.75, "b": 27.75, "teile": [
            {"t": 22.75, "html": "Stop guessing. "},
            {"t": 24.25, "html": "<b>Start playing.</b>"}]},
    ],
    "ende": {"claim": 29.75, "os": [33.60, 34.25, 35.15], "url": 36.75},
    "token": "teaser",
}


def lauf(*befehl, **mehr):
    return subprocess.run([str(b) for b in befehl], check=True,
                          capture_output=True, text=True, **mehr)


# --- Vorarbeit: Tonspur, Analyse, Bilder des Spielers -----------------------

def zustaende(cache: Path) -> list[dict]:
    """Was die Live-Analyse zu diesem Song an die Anzeige schicken wuerde."""
    datei = cache / "zustaende.json"
    if datei.exists():
        return json.loads(datei.read_text())

    import librosa
    import numpy as np

    import messung_live_pfad as m           # FakeLoop + synchroner Beat-Tracker
    from jampilot import beats, cli

    bis = SONG_AB + SZENEN["ende"] + 6.0    # dahinter zeigt der Film keine Anzeige
    print(f"  analysiere die Tonspur (0 .. {bis:.0f} s, dauert ~1 min) ...", flush=True)
    y, _ = librosa.load(str(QUELLE), sr=m.SR, mono=True, duration=bis)
    gesammelt = []

    class Rekorder:
        def publish(self, zustand):
            gesammelt.append(json.loads(json.dumps(zustand)))

    import argparse as ap
    stop = threading.Event()
    loop = m.FakeLoop(y.astype(np.float32), 5.0, stop)
    args = ap.Namespace(samplerate=m.SR, delay=5.0, record_buffer=0)
    original = beats.BeatTracker.create
    beats.BeatTracker.create = classmethod(lambda cls: m.SyncTracker())
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            cli._display_loop(loop, args, Rekorder(), stop=stop)
    finally:
        beats.BeatTracker.create = original
    datei.write_text(json.dumps(gesammelt))
    return gesammelt


def pip_bilder(cache: Path) -> int:
    """Der Spieler als Einzelbilder, ab der ersten Szene bis zur Endkarte."""
    ordner = cache / "pip"
    ab, dauer = ZEITPLAN["pip"]["ab"], SZENEN["ende"] - ZEITPLAN["pip"]["ab"]
    stempel = ordner / f"stempel-{SONG_AB}-{ab}-{dauer}"
    if not stempel.exists():
        ordner.mkdir(parents=True, exist_ok=True)
        for alt in ordner.glob("*"):
            alt.unlink()
        lauf("ffmpeg", "-v", "error", "-y", "-ss", f"{SONG_AB + ab:.3f}",
             "-t", f"{dauer:.3f}", "-i", QUELLE, "-vf",
             f"fps={FPS},crop={PIP_AUSSCHNITT}", "-start_number", "0",
             "-q:v", "2", ordner / "%05d.jpg")
        stempel.touch()
    return len(list(ordner.glob("*.jpg")))


# --- Der Server: die echte Seite, die Komposition, die Bilder ----------------

def server(cache: Path, anzahl_pip: int):
    from http.server import ThreadingHTTPServer

    from jampilot import web

    seite = (HIER / "teaser.html").read_text(encoding="utf-8").replace(
        "__ZEITPLAN__", json.dumps({**ZEITPLAN, "pip": {**ZEITPLAN["pip"],
                                                         "anzahl": anzahl_pip}}))
    marke = (PROJEKT / "docs" / "bilder" / "icon-mark.png").read_bytes()

    class Handler(web._Handler):
        broadcaster = web.ChordBroadcaster()      # bleibt stumm: gefuettert
        token = ZEITPLAN["token"]                 # wird ueber feed(), nicht SSE
        # Wie in den README-Bildern: eine Adresse, die niemandem gehoert.
        qr_bytes = web._qr_svg("http://192.168.1.42:8765/?k=3f9aXq7LmPw")

        def do_GET(self):
            pfad = self.path.split("?")[0]
            if pfad == "/teaser.html":
                self._send(seite.encode(), "text/html; charset=utf-8")
            elif pfad == "/mark.png":
                self._send(marke, "image/png")
            elif re.fullmatch(r"/pip/\d{5}\.jpg", pfad):
                self._send((cache / pfad[1:]).read_bytes(), "image/jpeg")
            elif pfad == "/events":
                # Die Anzeigen oeffnen ihren Ereigniskanal wie im Betrieb -
                # er bleibt offen und STUMM. Gefuettert wird ueber feed().
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.flush()
                threading.Event().wait()
            else:
                super().do_GET()

    dienst = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    dienst.daemon_threads = True
    threading.Thread(target=dienst.serve_forever, daemon=True).start()
    return dienst


# --- Rendern -----------------------------------------------------------------

def chrome_klasse():
    """Die Chrome-Fernsteuerung der README-Screenshots, plus Ereignisse."""
    spec = importlib.util.spec_from_file_location(
        "shots", PROJEKT / "docs" / "bilder" / "make-screenshots.py")
    shots = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shots)
    shots.BREITE, shots.HOEHE = 1920, 1080

    class Chrome(shots.Chrome):
        def weiter(self, ms: float):
            """Die angehaltene Uhr der Seite um `ms` vorstellen."""
            self.ruf("Emulation.setVirtualTimePolicy", policy="advance", budget=ms)
            while self._nachricht().get("method") != "Emulation.virtualTimeBudgetExpired":
                pass

        def bild(self) -> bytes:
            """Ein PNG der Seite.

            Bleibt das Foto aus, haengt Chrome an etwas, das bei angehaltener
            Uhr nie fertig wird - bisher war das ein <img>, dessen dekodierte
            Fassung verworfen war (siehe teaser.html beim Logo). Dann lieber
            mit dieser Auskunft abbrechen als ewig warten.
            """
            try:
                return base64.b64decode(self.ruf(
                    "Page.captureScreenshot", format="png",
                    optimizeForSpeed=True)["data"])
            except TimeoutError:
                raise SystemExit(
                    "Chrome liefert kein Bild mehr. Steht ein <img> in der "
                    "Komposition? Bilder gehoeren dort in eine Zeichenflaeche.")

    return Chrome


def rendern(cache: Path, von: float, bis: float, ziel, standbild: Path | None = None):
    """Bilder von `von` bis `bis` als PNG nach `ziel` (eine Pipe zu ffmpeg)."""
    alle = zustaende(cache)
    dienst = server(cache, pip_bilder(cache))
    chrome = chrome_klasse()()
    try:
        port = dienst.server_address[1]
        chrome.ruf("Page.navigate", url=f"http://127.0.0.1:{port}/teaser.html")
        chrome._warten()
        if chrome.js("window.bereit") is not True:
            raise SystemExit("Die Komposition laedt nicht.")
        chrome.ruf("Emulation.setVirtualTimePolicy", policy="pause")

        # Die Anzeigen laufen ab VORLAUF Sekunden vor dem ersten Bild mit -
        # Laufband, Huellkurve und Tonart sollen stehen, wenn es losgeht.
        start = von - VORLAUF
        offen = [z for z in alle if z["t"] >= SONG_AB + start]
        uhr = start                       # Filmzeit, die die Seite schon hat

        def bis_zeit(t: float):
            nonlocal uhr
            while offen and offen[0]["t"] - SONG_AB <= t:
                zustand = offen.pop(0)
                jetzt = zustand["t"] - SONG_AB
                if jetzt > uhr:
                    chrome.weiter((jetzt - uhr) * 1000)
                    uhr = jetzt
                chrome.js(f"feed({json.dumps(zustand)})")
            if t > uhr:
                chrome.weiter((t - uhr) * 1000)
                uhr = t

        bilder = [von] if standbild else [
            von + i / FPS for i in range(round((bis - von) * FPS))]
        for nummer, t in enumerate(bilder):
            bis_zeit(t)
            chrome.js(f"seek({t:.5f})")
            bild = chrome.bild()
            if standbild:
                standbild.write_bytes(bild)
            else:
                ziel.write(bild)
                if nummer % 150 == 0:
                    print(f"  Bild {nummer}/{len(bilder)}", flush=True)
    finally:
        chrome.schliessen()
        dienst.shutdown()


# --- Ton ---------------------------------------------------------------------

def lautheit(datei: Path, *vorfilter: str) -> float:
    """Integrierte Lautheit (LUFS) nach EBU R128."""
    kette = ",".join([*vorfilter, "ebur128"])
    protokoll = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(datei), "-af", kette,
         "-f", "null", "-"], capture_output=True, text=True).stderr
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", protokoll)[-1])


def ton(ziel: Path, von: float, bis: float):
    """Musik am Stueck, unter dem Sprecher zurueckgenommen; Sprecher darueber."""
    musik_lufs = lautheit(QUELLE, f"atrim={SONG_AB}:{SONG_AB + DAUER}")
    sprecher_lufs = lautheit(SPRECHER)
    musik_db = -17.0 - musik_lufs          # Musik allein
    # Der Sprecher ist mono und geht auf beide Kanaele: Das zaehlt in der
    # Lautheit 3 dB mehr als die Messung der Mono-Datei. -18 hier sind -15 im
    # Film - klar ueber der zurueckgenommenen Musik (um -25).
    sprecher_db = -18.0 - sprecher_lufs

    # Die Musik weicht dem Sprecher: je Satz ein Trapez (0,3 s hinunter, 0,45 s
    # wieder hinauf), dazwischen steht sie voll da.
    def trapez(a, b):
        return (f"clip((t-{a - .30:.2f})/.30,0,1)*clip(({b + .45:.2f}-t)/.45,0,1)")
    weichen = "0"
    for einsatz, a, b in SPRECHER_SCHNITTE:
        weichen = f"max({weichen},{trapez(einsatz, einsatz + b - a)})"
    # Vor dem Refrain leiser (die Startkarte), auf der Endkarte halb zurueck.
    huelle = (f"(0.50+0.50*clip((t-{SZENEN['live'] - 0.9:.2f})/0.9,0,1))"
              f"*(1-0.30*clip((t-{SZENEN['ende'] - .2:.2f})/1.2,0,1))"
              f"*(1-0.62*({weichen}))")

    teile = [f"[0:a]atrim={SONG_AB}:{SONG_AB + DAUER},asetpts=PTS-STARTPTS,"
             f"aresample=48000,volume={musik_db:.2f}dB,"
             f"volume='{huelle}':eval=frame,"
             f"afade=t=in:st=0:d=0.5,afade=t=out:st={DAUER - 2.2}:d=2.2[m]"]
    namen = []
    for i, (einsatz, a, b) in enumerate(SPRECHER_SCHNITTE):
        ms = round(einsatz * 1000)
        teile.append(
            f"[1:a]atrim={a}:{b},asetpts=PTS-STARTPTS,aresample=48000,"
            f"highpass=f=75,volume={sprecher_db:.2f}dB,"
            f"afade=t=in:st=0:d=0.03,afade=t=out:st={b - a - .06:.2f}:d=0.06,"
            f"adelay={ms}|{ms},pan=stereo|c0=c0|c1=c0[s{i}]")
        namen.append(f"[s{i}]")
    teile.append(f"[m]{''.join(namen)}amix=inputs={len(namen) + 1}:normalize=0[a]")
    roh = ziel.with_name("ton-roh.wav")
    lauf("ffmpeg", "-v", "error", "-y", "-i", QUELLE, "-i", SPRECHER,
         "-filter_complex", ";".join(teile), "-map", "[a]",
         "-c:a", "pcm_s24le", roh)
    # Das Ganze auf -14 LUFS (der Pegel, auf den YouTube ohnehin regelt), mit
    # einem Begrenzer knapp unter Vollaussteuerung. Gemessen wird der ganze
    # Film, auch wenn nur ein Stueck gerendert wird.
    anheben = -14.0 - lautheit(roh)
    lauf("ffmpeg", "-v", "error", "-y", "-i", roh, "-af",
         f"volume={anheben:.2f}dB,alimiter=limit=0.89:level=false,"
         f"atrim={von}:{bis},asetpts=PTS-STARTPTS", "-c:a", "pcm_s16le", ziel)


# --- Zusammenbau --------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bild", type=float, metavar="T",
                        help="nur ein Standbild bei T Sekunden (PNG neben der Ausgabe)")
    parser.add_argument("--nur-ton", action="store_true",
                        help="das Bild des fertigen Films behalten, nur den Ton neu mischen")
    parser.add_argument("--von", type=float, default=0.0)
    parser.add_argument("--bis", type=float, default=DAUER)
    parser.add_argument("--out", type=Path, default=AUSGABE)
    parser.add_argument("--cache", type=Path,
                        default=Path(tempfile.gettempdir()) / "jampilot-teaser")
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    for noetig in (QUELLE, SPRECHER):
        if not noetig.exists():
            raise SystemExit(f"Fehlt: {noetig}")
    # Wegwerf-Konfiguration: Die Seite soll keine Einstellungen dieses
    # Rechners sehen und web.py kein echtes Token anfassen.
    os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="jampilot-teaser-cfg-")

    if args.bild is not None:
        ziel = args.out.with_name(f"{args.out.stem}-{args.bild:05.2f}s.png")
        rendern(args.cache, args.bild, args.bild, None, standbild=ziel)
        print(ziel)
        return

    spur = args.cache / "ton.wav"
    ton(spur, args.von, args.bis)
    if args.nur_ton:
        neu = args.out.with_name(args.out.stem + "-neu.mp4")
        lauf("ffmpeg", "-v", "error", "-y", "-i", args.out, "-i", spur,
             "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
             "-b:a", "224k", "-movflags", "+faststart", "-shortest", neu)
        neu.replace(args.out)
        print(args.out)
        return
    kodierer = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-c:v", "png",
         "-framerate", str(FPS), "-i", "-", "-i", str(spur),
         "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
         "-profile:v", "high", "-c:a", "aac", "-b:a", "224k",
         "-movflags", "+faststart", "-shortest", str(args.out)],
        stdin=subprocess.PIPE)
    try:
        rendern(args.cache, args.von, args.bis, kodierer.stdin)
    finally:
        kodierer.stdin.close()
        kodierer.wait()
    print(args.out)


if __name__ == "__main__":
    main()

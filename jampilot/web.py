"""Web-Anzeige: Vollbildseite mit grossem Akkord, Laufband und QR-Code.

Architektur wie im Explorationsdokument (Phase 2/3): der Rechner analysiert,
Browser und Smartphone sind reine Fernanzeigen im lokalen Netz. Statt
WebSocket kommen Server-Sent-Events zum Einsatz - einseitige Updates reichen,
und es braucht keine zusaetzliche Bibliothek. Die Seite ist komplett
self-contained (kein CDN), damit alles ohne Internet funktioniert.
"""

import json
import queue
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 8765


class ChordBroadcaster:
    """Verteilt Zustands-Updates an alle verbundenen SSE-Clients.

    Jeder Client haelt genau EINEN Platz. Jeder Zustand ist ein vollstaendiger
    Snapshot (Zeitleiste + hoerbare Position), Zwischenstaende wegzuwerfen ist
    also verlustfrei - den *neuesten* wegzuwerfen dagegen fatal: ein langsamer
    Client bekaeme eine Warteschlange alter Akkorde serviert und stellte seine
    Uhr auf veraltete Zeitpunkte. Bei Rueckstau gewinnt daher immer der neue
    Zustand, nicht der alte.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._clients: set[queue.Queue] = set()
        self._last: str | None = None
        self._last_state: dict | None = None

    def publish(self, state: dict):
        payload = json.dumps(state)
        with self._lock:
            self._last = payload
            self._last_state = state
            for q in self._clients:
                try:
                    q.get_nowait()      # veralteten Zustand verdraengen
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    pass  # Client liest gerade - er holt sich den naechsten

    def subscribe(self) -> tuple[queue.Queue, str | None]:
        q = queue.Queue(maxsize=1)
        with self._lock:
            self._clients.add(q)
            return q, self._last

    def unsubscribe(self, q: queue.Queue):
        with self._lock:
            self._clients.discard(q)

    def republish(self, **aenderungen):
        """Den letzten Zustand mit geaenderten Feldern SOFORT erneut senden.

        Der Stummschalter muss auf allen Geraeten sofort umschlagen. Warteten wir
        auf den naechsten Analysetakt, haetten Handy und Laptop bis zu 250 ms lang
        verschiedene Meinungen darueber, ob gerade Ton kommt - und wer tippt,
        saehe seine eigene Aktion verzoegert.
        """
        with self._lock:
            zustand = dict(self._last_state or {})
        zustand.update(aenderungen)
        self.publish(zustand)


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # sendet nichts, ermittelt nur die Route
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _qr_svg(url: str) -> bytes:
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=10)
    return img.to_string()


class _Handler(BaseHTTPRequestHandler):
    broadcaster: ChordBroadcaster = None  # von start() gesetzt
    qr_bytes: bytes = b""
    # Wird erst gesetzt, wenn der Audiostream steht - die Webseite laeuft schon
    # vorher (sie zeigt den QR-Code). Bis dahin: 503 statt Absturz.
    mute_toggle = None

    def log_message(self, *_):
        pass  # kein Request-Log im Terminal

    def _send(self, content: bytes, content_type: str):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self._send(PAGE.encode(), "text/html; charset=utf-8")
        elif path == "/qr.svg":
            self._send(self.qr_bytes, "image/svg+xml")
        elif path == "/events":
            self._serve_events()
        else:
            self.send_error(404)

    def do_POST(self):
        """Stumm umschalten. Die Antwort ist der neue Zustand.

        Warum POST und nicht GET? Das hier ist kein Abruf, sondern ein Eingriff -
        und ein GET wuerde jeder Link-Vorschau, jedem Prefetch des Browsers die
        Musik abstellen.
        """
        if self.path.split("?")[0] != "/mute":
            self.send_error(404)
            return
        if self.mute_toggle is None:
            self.send_error(503, "no audio stream")
            return
        stumm = bool(self.mute_toggle())
        self._send(json.dumps({"muted": stumm}).encode(), "application/json")

    def _serve_events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        q, last = self.broadcaster.subscribe()
        try:
            if last is not None:
                self.wfile.write(f"data: {last}\n\n".encode())
                self.wfile.flush()
            while True:
                try:
                    payload = q.get(timeout=15.0)
                    self.wfile.write(f"data: {payload}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.broadcaster.unsubscribe(q)


class WebDisplay:
    def __init__(self, server: ThreadingHTTPServer, url: str,
                 broadcaster: ChordBroadcaster, handler: type):
        self._server = server
        self._handler = handler
        self.url = url
        self.broadcaster = broadcaster

    def set_mute_toggle(self, fn):
        """Nachtraeglich verdrahten: Die Seite steht, bevor der Stream steht.

        `staticmethod`, sonst bekaeme die Funktion beim Zugriff ueber den
        Handler dessen `self` als erstes Argument untergeschoben.
        """
        self._handler.mute_toggle = staticmethod(fn)

    def stop(self):
        self._server.shutdown()
        self._server.server_close()


def start(port: int = DEFAULT_PORT) -> WebDisplay:
    broadcaster = ChordBroadcaster()
    url = f"http://{lan_ip()}:{port}/"

    handler = type("Handler", (_Handler,), {
        "broadcaster": broadcaster,
        "qr_bytes": _qr_svg(url),
    })
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return WebDisplay(server, url, broadcaster, handler)


PAGE = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>JamPilot</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; overflow: hidden; }
  body {
    background: #000; color: #fff; user-select: none; cursor: default;
    font-family: -apple-system, "SF Pro Display", "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
  }

  #topbar {
    position: fixed; top: 0; left: 0; right: 0; padding: 2.2vmin 2.6vmin;
    display: flex; justify-content: space-between; align-items: flex-start;
    z-index: 10;
  }
  #brandbox { display: flex; flex-direction: column; gap: .9vmin; }
  #brand { display: flex; align-items: center; gap: 1vmin;
           color: #666; font-size: 2.2vmin; letter-spacing: .35em;
           text-transform: uppercase; }
  #dot { width: 1.1vmin; height: 1.1vmin; border-radius: 50%;
         background: #e2483d; transition: background .3s; }
  #dot.on { background: #3ddc7f; }

  /* Die erkannte Tonart - der Grund, warum die Akkorde so geschrieben werden,
     wie sie geschrieben werden. Ohne diese Anzeige wirkt die Schreibweise
     willkuerlich; mit ihr ist sie nachvollziehbar. */
  #keybadge { color: #4a5158; font-size: max(1.9vmin, 13px);
              letter-spacing: .08em; padding-left: 2.1vmin; min-height: 2.4vmin; }
  #keybadge b { color: #6ea8ff; font-weight: 600;
                font-size: 1.35em; line-height: 1; }   /* ♭/♯ lesbar gross */

  #right { display: flex; align-items: flex-start; gap: 1.8vmin; }
  #gear {
    background: none; border: 0; padding: .6vmin; cursor: pointer;
    color: #555; transition: color .2s, transform .2s;
    -webkit-tap-highlight-color: transparent;
  }
  #gear:hover, #gear.open { color: #6ea8ff; transform: rotate(45deg); }
  #gear svg { width: 3.4vmin; height: 3.4vmin; display: block;
              min-width: 22px; min-height: 22px; }

  #mute {
    background: none; border: 0; padding: .6vmin; cursor: pointer;
    color: #555; transition: color .2s;
    -webkit-tap-highlight-color: transparent;
  }
  #mute:hover { color: #6ea8ff; }
  #mute svg { width: 3.4vmin; height: 3.4vmin; display: block;
               min-width: 22px; min-height: 22px; }
  /* Der Knopf zeigt, was ein Druck TUT, nicht was gerade ist: laeuft der Ton,
     steht da das Pausenzeichen; ist er stumm, das Play-Dreieck. */
  #mute .ic-play { display: none; }
  body.muted #mute { color: #f5a524; }
  body.muted #pause .ic-pause { display: none; }
  body.muted #mute .ic-play  { display: inline; }

  /* Stumm heisst: gedimmt und entfaerbt - aber NICHT verdeckt. Der Akkord laeuft
     weiter, weil die Quelle weiterlaeuft, und man will sehen, wo sie steht, um
     rechtzeitig wieder einzusteigen. Ein Overlay ueber dem Akkord waere genau
     die Information, die man in der Pause braucht. */
  #stage, #lane { transition: opacity .3s, filter .3s; }
  body.muted #stage, body.muted #lane { opacity: .3; filter: saturate(.15); }

  #mutebadge {
    position: fixed; top: 0; left: 50%; transform: translateX(-50%);
    z-index: 15; display: none; align-items: center; gap: 1.4vmin;
    padding: 1.3vmin 2.8vmin; border-radius: 0 0 1.4vmin 1.4vmin;
    background: #f5a52418; border: 1px solid #f5a52455; border-top: 0;
    color: #f5a524; font-size: max(2vmin, 13px);
    letter-spacing: .28em; text-transform: uppercase; font-weight: 600;
    animation: pulse 2.4s ease-in-out infinite;
  }
  body.muted #mutebadge { display: flex; }
  #mutebadge small { color: #8a7752; letter-spacing: .06em;
                      text-transform: none; font-weight: 400; }
  @keyframes pulse { 50% { opacity: .55; } }

  #backdrop {
    position: fixed; inset: 0; background: #000c; z-index: 20;
    display: flex; align-items: center; justify-content: center;
  }
  #backdrop[hidden] { display: none; }
  #dialog {
    background: #14161a; border: 1px solid #262a30; border-radius: 1.6vmin;
    padding: 3.4vmin; width: min(46rem, 88vw); cursor: default;
  }
  #dialog h2 { font-size: max(2.6vmin, 17px); font-weight: 650;
               letter-spacing: .02em; }
  #dialog h2.second { margin-top: 3.4vmin; padding-top: 2.8vmin;
                      border-top: 1px solid #262a30; }
  #dialog { max-height: 88vh; overflow-y: auto; }
  #dialog p.sub { color: #6b7280; font-size: max(1.9vmin, 13px);
                  margin-top: .8vmin; line-height: 1.5; }
  .opt {
    display: flex; align-items: center; gap: 1.6vmin; width: 100%;
    margin-top: 1.6vmin; padding: 1.8vmin 2vmin; cursor: pointer;
    background: #1b1e23; border: 1px solid #2a2f36; border-radius: 1vmin;
    color: #c8cdd4; text-align: left; font: inherit;
    transition: border-color .15s, background .15s;
  }
  .opt:hover { background: #202429; border-color: #3a414a; }
  .opt[aria-checked="true"] { border-color: #6ea8ff; background: #1a2130; }
  .opt .glyph { font-size: max(3.4vmin, 22px); width: 2.2em; flex: none;
                text-align: center; color: #6ea8ff; font-weight: 600;
                letter-spacing: .08em; }
  .opt .text { display: block; }   /* sonst laeuft die Beschreibung in die Zeile
                                      des Labels hinein statt darunter */
  .opt .label { display: block; font-size: max(2.1vmin, 15px);
                font-weight: 600; color: #e6e9ed; }
  .opt .desc { display: block; font-size: max(1.7vmin, 12px); color: #6b7280;
               margin-top: .5vmin; line-height: 1.45; }
  #autokey { color: #6ea8ff; }

  #qrbox { text-align: center; }
  #qrcard { background: #fff; border-radius: 1.2vmin; padding: .9vmin;
            width: 13vmin; height: 13vmin; }
  #qrcard svg, #qrcard img { width: 100%; height: 100%; display: block; }
  #qrlabel { color: #555; font-size: 1.6vmin; margin-top: .8vmin;
             letter-spacing: .06em; }
  @media (max-width: 640px) { #qrbox { display: none; } }

  #stage {
    position: absolute; inset: 0; bottom: 24vh;
    display: flex; align-items: center; justify-content: center;
  }
  #current {
    font-weight: 750; line-height: .9; white-space: nowrap;
    font-size: min(42vw, 52vh);
    transition: opacity .25s;
  }
  #current .suffix { font-size: 45%; font-weight: 550; color: #6ea8ff;
                     vertical-align: baseline; }
  #current.pop { animation: pop .45s ease-out; }

  /* Bass-Modus: der gemessene Basston gross, der Akkord als Kontext darunter.
     Der Bassist will wissen, was ER spielt - der Akkord sagt ihm das nicht. */
  #stage { flex-direction: column; }
  #context { display: none; margin-top: 1.2vh; text-align: center;
             font-size: min(6vw, 7vh); font-weight: 600; color: #565e66;
             line-height: 1; white-space: nowrap; }
  #context .suffix { font-size: 55%; font-weight: 500; }
  #context .over { font-size: 46%; font-weight: 400; color: #444b52;
                   letter-spacing: .12em; text-transform: uppercase;
                   margin-right: .5em; }
  body.bass #current { font-size: min(34vw, 44vh); }
  @keyframes pop {
    0% { transform: scale(.94); opacity: .4; }
    100% { transform: scale(1); opacity: 1; }
  }

  /* Ohne Akkord stand hier frueher ein Gedankenstrich in 52vh Groesse - das sah
     aus wie ein grauer Balken und bedeutete gleichzeitig "keine Musik", "nicht
     verbunden" und "startet noch". Diese Zustaende werden jetzt benannt. */
  #idle { display: none; text-align: center; padding: 0 6vmin; }
  #idleTitle { font-size: min(7vw, 9vh); font-weight: 700; color: #565e66;
               line-height: 1.15; }
  #idleHint { margin-top: 2.6vh; font-size: min(2.4vw, 3.2vh); line-height: 1.55;
              color: #4a5158; font-weight: 400; }
  #idleHint b { color: #6ea8ff; font-weight: 600; }
  /* Pulsierende Punkte, solange wir auf etwas warten. */
  #idle.waiting #idleTitle::after {
    content: "…"; animation: blink 1.3s ease-in-out infinite;
  }
  @keyframes blink { 0%, 100% { opacity: .2; } 50% { opacity: 1; } }

  #lane {
    position: absolute; left: 0; right: 0; bottom: 0; height: 22vh;
    border-top: 1px solid #1c1c1c;
  }
  #nowline {
    position: absolute; left: 14%; top: 0; bottom: 0; width: 2px;
    background: linear-gradient(#6ea8ff88, #6ea8ff22);
  }
  #nowline.hit { animation: hit .35s ease-out; }
  @keyframes hit {
    0% { box-shadow: 0 0 0 0 #6ea8ffcc; background: #fff; }
    100% { box-shadow: 0 0 2.5vmin 1vmin #6ea8ff00; }
  }
  #nowlabel { position: absolute; left: 14%; bottom: 1vh;
              transform: translateX(-50%);
              color: #444; font-size: 1.7vmin; letter-spacing: .25em; }
  .chip {
    /* Nur vertikal zentrieren: die LINKE Textkante markiert den Zeitpunkt,
       nicht die Label-Mitte. Sie trifft die JETZT-Linie in genau dem Frame,
       in dem der Akkord erklingt - sonst laege der Wechsel im Wortinneren. */
    position: absolute; top: 42%; transform: translateY(-50%);
    font-size: 7.5vh; font-weight: 650; color: #9aa3ad;
    white-space: nowrap; will-change: left, opacity;
  }
  .chip .suffix { font-size: 55%; color: #567da3; }
  .chip .bassnote { color: #6ea8ff; }   /* das /E in C/E - die eigentliche Info */
  .chip .eta { display: block; text-align: left; font-size: 2vmin;
               color: #4a5158; font-weight: 400; margin-top: .4vh; }

  #hint { position: fixed; bottom: 24.5vh; right: 2.6vmin; color: #333;
          font-size: 1.7vmin; z-index: 5; }

  /* Die Credits. Sie stehen in der RECHTEN unteren Ecke der Zeitleiste - links
     sitzt bei 14% das NOW-Label, dort stiessen sie dagegen. Die Chips ziehen
     weiter oben durch (42% der Spur), unter ihnen ist frei. Dunkler als jeder
     andere Text der Seite: wer auf die Akkorde schaut, soll sie nicht sehen;
     wer danach sucht, findet sie. Beim Ueberfahren hellen sie auf. */
  #credits {
    position: fixed; bottom: 1vh; right: 2.6vmin; z-index: 5;
    display: flex; align-items: center; gap: .9vmin;
    color: #2b2f34; font-size: max(1.5vmin, 10px); letter-spacing: .06em;
    transition: color .3s;
  }
  #credits:hover { color: #4a5158; }
  #credits .sep { opacity: .55; }
  #credits svg { width: 1.5em; height: 1.5em; display: block; }
</style>
</head>
<body>
  <div id="topbar">
    <div id="brandbox">
      <div id="brand"><div id="dot"></div>JamPilot</div>
      <div id="keybadge"></div>
    </div>
    <div id="right">
      <!-- Stummschalter. Die Leertaste tut dasselbe - aber ein Handy hat keine,
           und die Anzeige steht meistens auf einem Handy. Ein eigener Knopf muss
           sein: Tippen IRGENDWOHIN schaltet schon Vollbild, das ist vergeben. -->
      <button id="mute" aria-label="Mute" aria-pressed="false">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <g class="ic-pause">
            <line x1="9" y1="5" x2="9" y2="19"></line>
            <line x1="15" y1="5" x2="15" y2="19"></line>
          </g>
          <g class="ic-play">
            <path d="M7 4.5 19 12 7 19.5 Z" fill="currentColor"></path>
          </g>
        </svg>
      </button>
      <button id="gear" aria-label="Settings" aria-haspopup="dialog">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="3"></circle>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0
                   0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0
                   0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0
                   9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0
                   0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0
                   0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0
                   4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2
                   0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0
                   1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1
                   1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0
                   0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0
                   1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0
                   0-1.51 1z"></path>
        </svg>
      </button>
      <div id="qrbox">
        <div id="qrcard"><img src="/qr.svg" alt="QR"></div>
        <div id="qrlabel">Connect your phone</div>
      </div>
    </div>
  </div>

  <div id="backdrop" hidden>
    <div id="dialog" role="dialog" aria-modal="true" aria-label="Settings">
      <h2>Your instrument</h2>
      <p class="sub">The chord says what the <em>band</em> plays. It does not say
         what a <em>bass player</em> plays: in C/E the chord is C, and the bass is
         on E. JamPilot measures the bass separately &ndash; it is not guessed
         from the chord.</p>
      <button class="opt" data-inst="chords" role="radio">
        <span class="glyph">&#9835;</span>
        <span class="text">
          <span class="label">Chords</span>
          <span class="desc">The audible chord, large. The classic display.</span>
        </span>
      </button>
      <button class="opt" data-inst="bass" role="radio">
        <span class="glyph">&#9836;</span>
        <span class="text">
          <span class="label">Bass</span>
          <span class="desc">The <b>measured</b> bass note, large &ndash; with the
                             chord as context. Inversions become visible.</span>
        </span>
      </button>

      <h2 class="second">Chord spelling</h2>
      <p class="sub">The same key is called A&#9839; or B&#9837;, depending on
         the key of the song. JamPilot detects the key and spells accordingly
         &ndash; or you decide.</p>
      <button class="opt" data-mode="auto" role="radio">
        <span class="glyph">&#9839;&#9837;</span>
        <span class="text">
          <span class="label">Automatic <span id="autokey"></span></span>
          <span class="desc">Follows the detected key. Sharps apply for the
                             first few seconds, until the key is settled.</span>
        </span>
      </button>
      <button class="opt" data-mode="sharp" role="radio">
        <span class="glyph">&#9839;</span>
        <span class="text">
          <span class="label">Always sharps</span>
          <span class="desc">C&#9839; &middot; D&#9839; &middot; F&#9839;
                             &middot; G&#9839; &middot; A&#9839;</span>
        </span>
      </button>
      <button class="opt" data-mode="flat" role="radio">
        <span class="glyph">&#9837;</span>
        <span class="text">
          <span class="label">Always flats</span>
          <span class="desc">D&#9837; &middot; E&#9837; &middot; G&#9837;
                             &middot; A&#9837; &middot; B&#9837;</span>
        </span>
      </button>
    </div>
  </div>

  <div id="stage">
    <div id="current"></div>
    <div id="context"></div>
    <div id="idle"><div id="idleTitle"></div><div id="idleHint"></div></div>
  </div>

  <div id="lane"><div id="nowline"></div><div id="nowlabel">NOW</div></div>
  <div id="mutebadge">
    Muted <small>&mdash; the source keeps playing, you just hear nothing</small>
  </div>
  <div id="hint">Click = fullscreen &middot; Space = mute</div>
  <div id="credits">
    <span>Johannes Weigend</span>
    <span class="sep">&middot;</span>
    <svg viewBox="0 0 24 24" role="img" aria-label="Built with Claude">
      <title>Built with Claude</title>
      <g stroke="currentColor" stroke-width="2.1" stroke-linecap="round">
        <line x1="12" y1="4"   x2="12" y2="20"/>
        <line x1="4"  y1="12"  x2="20" y2="12"/>
        <line x1="6.3" y1="6.3" x2="17.7" y2="17.7"/>
        <line x1="17.7" y1="6.3" x2="6.3" y2="17.7"/>
      </g>
    </svg>
  </div>

<script>
"use strict";
const $ = id => document.getElementById(id);
const NOW_PCT = 14;          // Position der JETZT-Linie in %
const RIGHT_PCT = 97;        // Einstiegsposition rechts

// Der Server schickt die Akkorde mit ihrer Onset-Position in Stream-Sekunden
// (`at`) und dazu die gerade hoerbare Position (`t`). Der Browser rechnet
// beides in seine eigene Uhr um und leitet GROSSEN AKKORD UND LAUFBAND aus
// derselben Position ab. Deshalb kann der Akkordwechsel gar nicht anders, als
// exakt dann zu passieren, wenn der Chip die JETZT-Linie beruehrt.
let chords = [];             // [{c, at}] Onsets in Stream-Sekunden
let horizon = 4;             // Sekunden von rechts bis JETZT-Linie
let offset = null;           // browserZeit(s) - streamPosition(s)
let offsetSamples = [];
let chips = new Map();       // key -> {el, at, chord}
let link = "connecting";     // connecting | live | lost

// SCHREIBWEISE. Der Server schickt die Akkorde kanonisch, immer mit Kreuz
// ("A#m7") - das ist eine ID, keine Anzeige. Wie sie GESCHRIEBEN werden,
// entscheidet sich hier: aus der erkannten Tonart (`tonart`, vom Server) oder
// aus der festen Vorgabe des Benutzers (`modus`). Deshalb wirkt eine Umstellung
// sofort und rueckwirkend auf alles, was gerade auf dem Laufband steht - und
// Laptop und Handy duerfen verschieden eingestellt sein.
const MODUS_KEY = "jampilot.accidental";
const FLAT_OF  = { "C#": "D♭", "D#": "E♭", "F#": "G♭",
                   "G#": "A♭", "A#": "B♭" };
const SHARP_OF = { "C#": "C♯", "D#": "D♯", "F#": "F♯",
                   "G#": "G♯", "A#": "A♯" };

let modus = localStorage.getItem(MODUS_KEY) || "auto";   // auto | sharp | flat
let tonart = null;           // {tonic, minor, acc, label} - oder null
let schreibweise = "sharp";  // was daraus gerade folgt

// INSTRUMENT. Der Akkord sagt, was die BAND spielt - nicht, was DU spielst.
// Bei C/E steht im Akkord ein C, und der Bassist greift ein E. Der Server misst
// den Bass separat und schickt ihn pro Segment mit (`b`); ob er gezeigt wird,
// entscheidet - wie die Schreibweise - allein der Browser.
const INSTRUMENT_KEY = "jampilot.instrument";
let instrument = localStorage.getItem(INSTRUMENT_KEY) || "chords";  // chords | bass

// Ohne erkannte Tonart gilt das Kreuz: das ist die Schreibweise ohne Vorzeichen
// und die einzige ehrliche Vorgabe, solange wir die Tonart nicht kennen.
function gewaehlteSchreibweise() {
  if (modus === "sharp" || modus === "flat") return modus;
  return tonart ? tonart.acc : "sharp";
}

function schreibeGrundton(root, acc) {
  if (!root.includes("#")) return root;
  return (acc === "flat" ? FLAT_OF : SHARP_OF)[root] || root;
}

// Uhrabgleich nach NTP-Prinzip: die Zustellzeit eines SSE-Pakets ist immer
// positiv, also ist das MINIMUM der beobachteten Offsets der wahre Versatz.
// Ohne diesen Filter wandert die Zeitleiste mit dem Netz- und Tick-Jitter.
function syncClock(t) {
  offsetSamples.push(performance.now() / 1000 - t);
  if (offsetSamples.length > 40) offsetSamples.shift();
  const target = Math.min(...offsetSamples);
  if (offset === null) offset = target;
  else offset += (target - offset) * 0.2;   // sanft nachziehen, keine Spruenge
}

function streamNow() { return performance.now() / 1000 - offset; }

function fmtChord(name) {
  if (!name || name === "-" || name === " ") return null;
  if (name === "?") return { root: "…", suffix: "" };
  const m = name.match(/^([A-G]#?)(.*)$/);
  if (!m) return { root: name, suffix: "" };
  return { root: schreibeGrundton(m[1], schreibweise), suffix: m[2] };
}

function chordHtml(name) {
  const f = fmtChord(name);
  if (!f) return null;
  return f.root + (f.suffix ? '<span class="suffix">' + f.suffix + "</span>" : "");
}

// Kanonischer Grundton eines Akkords ("A#m7" -> "A#") - zum Vergleich mit der
// gemessenen Bassnote. Beide kommen kanonisch vom Server, also vergleichbar.
function wurzelVon(name) {
  const m = name ? name.match(/^([A-G]#?)/) : null;
  return m ? m[1] : null;
}

// Die Umkehrung: liegt unten etwas anderes als der Grundton? Nur dann ist der
// Bass eine eigene Information - sonst sagt der Akkordname schon alles.
function umkehrung(seg) {
  if (!seg || !seg.b) return null;
  return wurzelVon(seg.c) === seg.b ? null : seg.b;
}

// Was gerade los ist, wenn KEIN Akkord dasteht. Ohne diese Unterscheidung sieht
// "der Rechner spielt keine Musik" genauso aus wie "die Anzeige ist tot".
function idleText() {
  if (link === "connecting") return ["Connecting", "Looking for the JamPilot display."];
  if (link === "lost")
    return ["Connection lost",
            "JamPilot stopped responding. Is it still running in the terminal?"];
  if (offset === null) return ["Starting up", "The analysis is spinning up."];
  return ["No music",
          "Play something &ndash; the chord appears here "
          + "<b>before</b> you hear it."];
}

function showIdle() {
  const [titel, hinweis] = idleText();
  $("current").style.display = "none";
  $("current").dataset.shown = "";     // damit ein neuer Akkord wieder aufploppt
  $("context").style.display = "none";

  const idle = $("idle");
  idle.style.display = "block";
  idle.classList.toggle("waiting", link !== "live" || offset === null);
  if (idle.dataset.shown === titel) return;
  idle.dataset.shown = titel;
  $("idleTitle").textContent = titel;
  $("idleHint").innerHTML = hinweis;
}

// Im Bass-Modus steht der GEMESSENE Basston gross und der Akkord als Kontext
// darunter. Wurde kein Bass gemessen (Mehrheit fehlt, kein Bass im Stueck),
// faellt die Anzeige auf den Akkord zurueck - wir zeigen, was wir wissen, und
// erfinden nichts.
function setCurrent(seg) {
  const akkord = seg ? seg.c : null;
  if (chordHtml(akkord) === null) { showIdle(); return; }  // Stille/kein Akkord

  const bass = instrument === "bass" && seg.b ? seg.b : null;
  const html = bass ? schreibeGrundton(bass, schreibweise) : chordHtml(akkord);
  // Kontext nur, wenn der Akkord mehr sagt als der grosse Ton allein.
  const kontext = bass && akkord !== bass
    ? '<span class="over">over</span>' + chordHtml(akkord) : "";

  const el = $("current");
  $("idle").style.display = "none";
  $("idle").dataset.shown = "";
  el.style.display = "block";

  const ctx = $("context");
  ctx.style.display = kontext ? "block" : "none";
  if (ctx.dataset.shown !== kontext) {
    ctx.dataset.shown = kontext;
    ctx.innerHTML = kontext;
  }

  if (el.dataset.shown === html) return;
  el.dataset.shown = html;
  el.innerHTML = html;
  el.classList.remove("pop"); void el.offsetWidth; el.classList.add("pop");
  // Der Blitz auf der JETZT-Linie macht sichtbar, dass beide dieselbe Uhr
  // benutzen: er faellt mit dem Wechsel des grossen Akkords zusammen.
  const line = $("nowline");
  line.classList.remove("hit"); void line.offsetWidth; line.classList.add("hit");
}

// Auf dem Laufband steht im Bass-Modus der Slash-Akkord: C/E. Genau das ist die
// Information, die im Akkordnamen allein fehlt.
function chipHtml(seg) {
  const html = chordHtml(seg.c);
  if (html === null) return null;
  const bass = instrument === "bass" ? umkehrung(seg) : null;
  return bass
    ? html + '<span class="bassnote">/' + schreibeGrundton(bass, schreibweise)
             + "</span>"
    : html;
}

function syncChips(now) {
  const wanted = new Map();
  for (const c of chords) {
    if (c.c === "-" || c.c === "?") continue;
    if (c.at < now - 0.7) continue;        // schon durchgelaufen
    // Die Bassnote gehoert in den Schluessel: aendert sie sich, muss der Chip
    // neu gezeichnet werden - sonst bliebe ein "C" stehen, wo "C/E" hingehoert.
    wanted.set(c.at.toFixed(2) + "|" + c.c + "|" + (c.b || ""), c);
  }
  for (const [key, c] of wanted) {
    if (chips.has(key)) continue;
    const html = chipHtml(c);
    if (!html) continue;
    const el = document.createElement("div");
    el.className = "chip";
    el.innerHTML = html + '<span class="eta"></span>';
    $("lane").appendChild(el);
    chips.set(key, { el, at: c.at });
  }
  for (const [key, chip] of chips) {
    if (wanted.has(key)) continue;
    chip.el.remove(); chips.delete(key);
  }
}

function animate() {
  requestAnimationFrame(animate);

  // Ohne Verbindung oder ohne Uhr gibt es nichts anzuzeigen - dann sagen wir das,
  // statt eine eingefrorene Zeitleiste weiterlaufen zu lassen.
  if (link !== "live" || offset === null) {
    showIdle();
    for (const chip of chips.values()) chip.el.remove();
    chips.clear();
    return;
  }
  const now = streamNow();

  // Hoerbar ist das letzte Segment, dessen Onset erreicht ist. Es traegt den
  // Akkord UND die dort gemessene Bassnote.
  let audible = null;
  for (const c of chords) {
    if (c.at > now) break;
    audible = c;
  }
  setCurrent(audible);

  syncChips(now);
  for (const chip of chips.values()) {
    const remaining = chip.at - now;       // dieselbe Uhr wie oben
    const frac = Math.max(remaining, 0) / horizon;
    chip.el.style.left = (NOW_PCT + Math.min(frac, 1.15) * (RIGHT_PCT - NOW_PCT)) + "%";
    chip.el.style.opacity = remaining < 0 ? String(1 + remaining / 0.7)
                          : String(0.45 + 0.55 * (1 - Math.min(frac, 1)));
    chip.el.querySelector(".eta").textContent =
      remaining > 0.05 ? "in " + remaining.toFixed(1) + "s" : "";
  }
}

// Aendert sich die Schreibweise, muss ALLES neu geschrieben werden, was schon
// dasteht - der grosse Akkord und jeder Chip auf dem Laufband. Beide cachen
// ihr gerendertes HTML, also wird der Cache verworfen; die Chips baut
// syncChips() im naechsten Frame ohnehin neu auf.
function neuSchreibenFallsNoetig() {
  const acc = gewaehlteSchreibweise();
  const geaendert = acc !== schreibweise;
  schreibweise = acc;          // erst setzen, dann anzeigen: zeigeTonart liest es
  zeigeTonart();
  if (!geaendert) return;
  $("current").dataset.shown = "";
  for (const chip of chips.values()) chip.el.remove();
  chips.clear();
}

function zeigeTonart() {
  // Die Tonart steht auch dann da, wenn der Benutzer die Schreibweise fest
  // vorgegeben hat - sie ist eine Aussage ueber das Stueck, keine ueber die
  // Anzeige. Nur der Zusatz sagt, was gerade wirklich geschrieben wird.
  //
  // Das Label wird HIER gebaut, nicht vom Server uebernommen: der Grundton der
  // Tonart braucht dieselbe Glyphen-Schreibweise wie die Akkorde (B♭, nicht Bb),
  // und zwar in der Schreibweise der TONART selbst - Bb-Moll heisst nie A#-Moll,
  // auch wenn der Benutzer Kreuze erzwungen hat.
  const zeichen = schreibweise === "flat" ? "♭" : "♯";
  const label = tonart
    ? schreibeGrundton(tonart.tonic, tonart.acc)
      + (tonart.minor ? " minor" : " major")
    : null;
  $("keybadge").innerHTML = label ? label + " · <b>" + zeichen + "</b>" : "";
  $("autokey").textContent = tonart ? "· " + label : "";
}

function setzeModus(neu) {
  modus = neu;
  try { localStorage.setItem(MODUS_KEY, neu); } catch (e) {}  // Privatmodus
  for (const opt of document.querySelectorAll(".opt[data-mode]"))
    opt.setAttribute("aria-checked", String(opt.dataset.mode === neu));
  neuSchreibenFallsNoetig();
}

function setzeInstrument(neu) {
  instrument = neu;
  try { localStorage.setItem(INSTRUMENT_KEY, neu); } catch (e) {}
  for (const opt of document.querySelectorAll(".opt[data-inst]"))
    opt.setAttribute("aria-checked", String(opt.dataset.inst === neu));
  document.body.classList.toggle("bass", neu === "bass");
  // Alles neu zeichnen: der grosse Ton und jeder Chip sagen jetzt etwas anderes.
  $("current").dataset.shown = "";
  $("context").dataset.shown = "";
  for (const chip of chips.values()) chip.el.remove();
  chips.clear();
}

function dialog(offen) {
  $("backdrop").hidden = !offen;
  $("gear").classList.toggle("open", offen);
}

function apply(state) {
  chords = state.chords || [];
  horizon = Math.max(1.5, (state.lead || 3) + 0.8);
  tonart = state.key || null;
  if ("muted" in state) zeigeStumm(state.muted);
  neuSchreibenFallsNoetig();
  syncClock(state.t);
}

// STUMM. Nicht angehalten: Die Quelle laeuft weiter, der Ringpuffer laeuft
// weiter, die Analyse laeuft weiter - nur der Lautsprecher schweigt. Deshalb
// laeuft die Anzeige in der Pause WEITER (gedimmt), und beim Fortsetzen ist man
// sofort wieder synchron zur Quelle, statt immer weiter hinter sie zu rutschen.
let stumm = false;

function zeigeStumm(m) {
  stumm = !!m;
  document.body.classList.toggle("muted", stumm);
  const btn = $("mute");
  btn.setAttribute("aria-pressed", stumm ? "true" : "false");
  btn.setAttribute("aria-label", stumm ? "Unmute" : "Mute");
}

async function umschalten() {
  try {
    const antwort = await fetch("/mute", { method: "POST" });
    if (!antwort.ok) return;      // kein Stream (Demo-Modus) - dann eben nichts
    // Die Wahrheit kommt vom Server, nicht von unserer Vermutung: Sonst laufen
    // zwei Geraete auseinander, wenn beide gleichzeitig druecken.
    zeigeStumm((await antwort.json()).muted);
  } catch (e) {
    /* Verbindung weg - der naechste SSE-Zustand richtet die Anzeige wieder */
  }
}

$("mute").addEventListener("click", ev => {
  ev.stopPropagation();     // sonst schaltet der Body-Klick auch noch Vollbild
  umschalten();
  ev.currentTarget.blur();  // sonst wuerde die Leertaste danach den Knopf treffen
});

function connect() {
  const es = new EventSource("/events");   // EventSource verbindet selbst neu
  es.onopen = () => { link = "live"; $("dot").classList.add("on"); };
  es.onerror = () => { link = "lost"; $("dot").classList.remove("on"); };
  es.onmessage = e => { link = "live"; apply(JSON.parse(e.data)); };
}

// Ein Klick irgendwohin schaltet Vollbild. Das Zahnrad und der Dialog sind
// davon ausgenommen - sonst wuerde jede Einstellung nebenbei das Vollbild
// umschalten. Der Klick NEBEN den Dialog (auf den Hintergrund) schliesst ihn,
// ohne das Vollbild anzufassen.
document.body.addEventListener("click", ev => {
  if (ev.target.closest("#gear")) { dialog($("backdrop").hidden); return; }
  if (ev.target.closest("#dialog")) return;
  if (!$("backdrop").hidden) { dialog(false); return; }

  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen().catch(() => {});
});

for (const opt of document.querySelectorAll(".opt"))
  opt.addEventListener("click", () => {
    if (opt.dataset.mode) setzeModus(opt.dataset.mode);
    else if (opt.dataset.inst) setzeInstrument(opt.dataset.inst);
  });

document.addEventListener("keydown", ev => {
  if (ev.key === "Escape") { dialog(false); return; }
  if (ev.code === "Space" || ev.key === " ") {
    // Nicht im Einstellungsdialog: Dort waehlt die Leertaste eine Option aus,
    // und beides gleichzeitig zu tun waere eine Ueberraschung.
    if (!$("backdrop").hidden) return;
    ev.preventDefault();          // sonst scrollt die Seite
    umschalten();
  }
});

setzeInstrument(instrument);   // gespeicherte Wahl anwenden und markieren
setzeModus(modus);

if (new URLSearchParams(location.search).has("demo")) {
  // Demo in F-Dur: die Progression enthaelt A# (= Bb), damit man die
  // Schreibweise umschalten sieht - und zwei Umkehrungen (C/E, F/A), damit man
  // im Bass-Modus sieht, wofuer die gemessene Bassnote gut ist.
  const prog = [["F", "F"], ["A#", "A#"], ["C", "E"], ["Dm", "D"],
                ["F", "A"], ["Gm", "G"], ["C7", "A#"], ["A#", "A#"]];
  const start = performance.now() / 1000;
  link = "live";
  setInterval(() => {
    const t = performance.now() / 1000 - start;   // "hoerbare" Position
    const list = [];
    for (let i = Math.floor(t / 2) - 1; i < t / 2 + 3; i++)
      if (i >= 0) list.push({ c: prog[i % prog.length][0], at: i * 2,
                              b: prog[i % prog.length][1] });
    // Die Tonart faellt erst nach ein paar Sekunden - wie im echten Betrieb.
    const key = t < 8 ? null
      : { tonic: "F", minor: false, acc: "flat", label: "F-Dur" };
    apply({ t, chords: list, lead: 3, key });
  }, 250);
  $("dot").classList.add("on");
} else {
  connect();
}
animate();
</script>
</body>
</html>
"""

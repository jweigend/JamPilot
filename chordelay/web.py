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

    def publish(self, state: dict):
        payload = json.dumps(state)
        with self._lock:
            self._last = payload
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
                 broadcaster: ChordBroadcaster):
        self._server = server
        self.url = url
        self.broadcaster = broadcaster

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
    return WebDisplay(server, url, broadcaster)


PAGE = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
<title>chordelay</title>
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
  #brand { display: flex; align-items: center; gap: 1vmin;
           color: #666; font-size: 2.2vmin; letter-spacing: .35em;
           text-transform: uppercase; }
  #dot { width: 1.1vmin; height: 1.1vmin; border-radius: 50%;
         background: #e2483d; transition: background .3s; }
  #dot.on { background: #3ddc7f; }

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
  .chip .eta { display: block; text-align: left; font-size: 2vmin;
               color: #4a5158; font-weight: 400; margin-top: .4vh; }

  #hint { position: fixed; bottom: 24.5vh; right: 2.6vmin; color: #333;
          font-size: 1.7vmin; z-index: 5; }
</style>
</head>
<body>
  <div id="topbar">
    <div id="brand"><div id="dot"></div>chordelay</div>
    <div id="qrbox">
      <div id="qrcard"><img src="/qr.svg" alt="QR"></div>
      <div id="qrlabel">Smartphone verbinden</div>
    </div>
  </div>

  <div id="stage">
    <div id="current"></div>
    <div id="idle"><div id="idleTitle"></div><div id="idleHint"></div></div>
  </div>

  <div id="lane"><div id="nowline"></div><div id="nowlabel">JETZT</div></div>
  <div id="hint">Klick = Vollbild</div>

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
  const m = name.match(/^([A-G][#b]?)(.*)$/);
  return m ? { root: m[1], suffix: m[2] } : { root: name, suffix: "" };
}

function chordHtml(name) {
  const f = fmtChord(name);
  if (!f) return null;
  return f.root + (f.suffix ? '<span class="suffix">' + f.suffix + "</span>" : "");
}

// Was gerade los ist, wenn KEIN Akkord dasteht. Ohne diese Unterscheidung sieht
// "der Rechner spielt keine Musik" genauso aus wie "die Anzeige ist tot".
function idleText() {
  if (link === "connecting") return ["Verbinde", "Suche die chordelay-Anzeige."];
  if (link === "lost")
    return ["Verbindung verloren",
            "chordelay antwortet nicht mehr. Läuft es noch im Terminal?"];
  if (offset === null) return ["Startet", "Die Analyse läuft an."];
  return ["Keine Musik",
          "Spiel etwas ab &ndash; der Akkord steht hier, "
          + "<b>bevor</b> du ihn hörst."];
}

function showIdle() {
  const [titel, hinweis] = idleText();
  $("current").style.display = "none";
  $("current").dataset.shown = "";     // damit ein neuer Akkord wieder aufploppt

  const idle = $("idle");
  idle.style.display = "block";
  idle.classList.toggle("waiting", link !== "live" || offset === null);
  if (idle.dataset.shown === titel) return;
  idle.dataset.shown = titel;
  $("idleTitle").textContent = titel;
  $("idleHint").innerHTML = hinweis;
}

function setCurrent(name) {
  const html = chordHtml(name);
  if (html === null) { showIdle(); return; }   // Stille oder kein Akkord

  const el = $("current");
  $("idle").style.display = "none";
  $("idle").dataset.shown = "";
  el.style.display = "block";
  if (el.dataset.shown === html) return;
  el.dataset.shown = html;
  el.innerHTML = html;
  el.classList.remove("pop"); void el.offsetWidth; el.classList.add("pop");
  // Der Blitz auf der JETZT-Linie macht sichtbar, dass beide dieselbe Uhr
  // benutzen: er faellt mit dem Wechsel des grossen Akkords zusammen.
  const line = $("nowline");
  line.classList.remove("hit"); void line.offsetWidth; line.classList.add("hit");
}

function syncChips(now) {
  const wanted = new Map();
  for (const c of chords) {
    if (c.c === "-" || c.c === "?") continue;
    if (c.at < now - 0.7) continue;        // schon durchgelaufen
    wanted.set(c.at.toFixed(2) + "|" + c.c, c);
  }
  for (const [key, c] of wanted) {
    if (chips.has(key)) continue;
    const html = chordHtml(c.c);
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

  // Hoerbar ist der letzte Akkord, dessen Onset erreicht ist.
  let audible = null;
  for (const c of chords) {
    if (c.at > now) break;
    audible = c.c;
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

function apply(state) {
  chords = state.chords || [];
  horizon = Math.max(1.5, (state.lead || 3) + 0.8);
  syncClock(state.t);
}

function connect() {
  const es = new EventSource("/events");   // EventSource verbindet selbst neu
  es.onopen = () => { link = "live"; $("dot").classList.add("on"); };
  es.onerror = () => { link = "lost"; $("dot").classList.remove("on"); };
  es.onmessage = e => { link = "live"; apply(JSON.parse(e.data)); };
}

document.body.addEventListener("click", () => {
  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen().catch(() => {});
});

if (new URLSearchParams(location.search).has("demo")) {
  const prog = ["C", "G", "Am", "F", "C", "G7", "Am7", "F"];
  const start = performance.now() / 1000;
  link = "live";
  setInterval(() => {
    const t = performance.now() / 1000 - start;   // "hoerbare" Position
    const list = [];
    for (let i = Math.floor(t / 2) - 1; i < t / 2 + 3; i++)
      if (i >= 0) list.push({ c: prog[i % prog.length], at: i * 2 });
    apply({ t, chords: list, lead: 3 });
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

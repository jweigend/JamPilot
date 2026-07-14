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
    """Verteilt Zustands-Updates an alle verbundenen SSE-Clients."""

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
                    q.put_nowait(payload)
                except queue.Full:
                    pass  # langsamer Client: Update verfallen lassen

    def subscribe(self) -> tuple[queue.Queue, str | None]:
        q = queue.Queue(maxsize=8)
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
  #current.silent { color: #2a2a2a; }
  #current.pop { animation: pop .45s ease-out; }
  @keyframes pop {
    0% { transform: scale(.94); opacity: .4; }
    100% { transform: scale(1); opacity: 1; }
  }

  #lane {
    position: absolute; left: 0; right: 0; bottom: 0; height: 22vh;
    border-top: 1px solid #1c1c1c;
  }
  #nowline {
    position: absolute; left: 14%; top: 0; bottom: 0; width: 2px;
    background: linear-gradient(#6ea8ff88, #6ea8ff22);
  }
  #nowlabel { position: absolute; left: 14%; bottom: 1vh;
              transform: translateX(-50%);
              color: #444; font-size: 1.7vmin; letter-spacing: .25em; }
  .chip {
    position: absolute; top: 42%; transform: translate(-50%, -50%);
    font-size: 7.5vh; font-weight: 650; color: #9aa3ad;
    will-change: left, opacity;
  }
  .chip .suffix { font-size: 55%; color: #567da3; }
  .chip .eta { display: block; text-align: center; font-size: 2vmin;
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

  <div id="stage"><div id="current" class="silent">&ndash;</div></div>

  <div id="lane"><div id="nowline"></div><div id="nowlabel">JETZT</div></div>
  <div id="hint">Klick = Vollbild</div>

<script>
"use strict";
const $ = id => document.getElementById(id);
const NOW_PCT = 14;          // Position der JETZT-Linie in %
const RIGHT_PCT = 97;        // Einstiegsposition rechts
let state = null;            // letzter Serverzustand
let recvAt = 0;              // performance.now() beim Empfang
let horizon = 4;             // Sekunden von rechts bis JETZT-Linie
let chips = new Map();       // key -> {el, chord, audibleAt}

function fmtChord(name) {
  if (!name || name === "-" || name === " ") return null;
  if (name === "?") return { root: "…", suffix: "" };
  const m = name.match(/^([A-G][#b]?)(.*)$/);
  return m ? { root: m[1], suffix: m[2] } : { root: name, suffix: "" };
}

function setCurrent(name) {
  const el = $("current");
  const f = fmtChord(name);
  const html = f ? f.root + (f.suffix ? '<span class="suffix">' + f.suffix + "</span>" : "")
                 : "&ndash;";
  if (el.dataset.shown === html) return;
  el.dataset.shown = html;
  el.innerHTML = html;
  el.classList.toggle("silent", !f || name === "?");
  el.classList.remove("pop"); void el.offsetWidth; el.classList.add("pop");
}

function syncChips() {
  const seen = new Set();
  for (const u of (state.upcoming || [])) {
    const audibleAt = recvAt + u.in * 1000;
    let key = null;
    for (const [k, c] of chips)
      if (c.chord === u.chord && Math.abs(c.audibleAt - audibleAt) < 600) { key = k; break; }
    if (key === null) {
      key = u.chord + ":" + Math.round(audibleAt);
      const el = document.createElement("div");
      el.className = "chip";
      const f = fmtChord(u.chord);
      if (!f) continue;
      el.innerHTML = f.root + (f.suffix ? '<span class="suffix">' + f.suffix + "</span>" : "")
                   + '<span class="eta"></span>';
      $("lane").appendChild(el);
      chips.set(key, { el, chord: u.chord, audibleAt });
    } else {
      chips.get(key).audibleAt = audibleAt;  // Serverkorrektur uebernehmen
    }
    seen.add(key);
  }
  for (const [k, c] of chips)
    if (!seen.has(k) && c.audibleAt > performance.now() + 700) {
      c.el.remove(); chips.delete(k);       // vom Server zurueckgezogen
    }
}

function animate() {
  const now = performance.now();
  for (const [k, c] of chips) {
    const remaining = (c.audibleAt - now) / 1000;
    if (remaining < -0.7) { c.el.remove(); chips.delete(k); continue; }
    const frac = Math.max(remaining, 0) / horizon;
    const pct = NOW_PCT + Math.min(frac, 1.15) * (RIGHT_PCT - NOW_PCT);
    c.el.style.left = pct + "%";
    c.el.style.opacity = remaining < 0 ? String(1 + remaining / 0.7)
                        : String(0.45 + 0.55 * (1 - Math.min(frac, 1)));
    const eta = c.el.querySelector(".eta");
    if (eta) eta.textContent = remaining > 0 ? "in " + remaining.toFixed(1) + "s" : "";
  }
  requestAnimationFrame(animate);
}

function apply() {
  setCurrent(state.audible);
  horizon = Math.max(1.5, (state.lead || 3) + 0.8);
  syncChips();
}

function connect() {
  const es = new EventSource("/events");
  es.onopen = () => $("dot").classList.add("on");
  es.onerror = () => $("dot").classList.remove("on");
  es.onmessage = e => { state = JSON.parse(e.data); recvAt = performance.now(); apply(); };
}

document.body.addEventListener("click", () => {
  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen().catch(() => {});
});

if (new URLSearchParams(location.search).has("demo")) {
  const prog = ["C", "G", "Am", "F", "C", "G7", "Am7", "F"];
  let i = 0;
  setInterval(() => {
    state = { audible: prog[i % prog.length],
              upcoming: [{ chord: prog[(i + 1) % prog.length], in: 1.4 },
                         { chord: prog[(i + 2) % prog.length], in: 3.4 }],
              lead: 3 };
    recvAt = performance.now(); apply(); i++;
  }, 2000);
  $("dot").classList.add("on");
} else {
  connect();
}
animate();
</script>
</body>
</html>
"""

"""Web-Anzeige: Vollbildseite mit grossem Akkord, Laufband und QR-Code.

Architektur wie im Explorationsdokument (Phase 2/3): der Rechner analysiert,
Browser und Smartphone sind reine Fernanzeigen im lokalen Netz. Statt
WebSocket kommen Server-Sent-Events zum Einsatz - einseitige Updates reichen,
und es braucht keine zusaetzliche Bibliothek. Die Seite ist komplett
self-contained (kein CDN), damit alles ohne Internet funktioniert.
"""

import json
import queue
import secrets
import socket
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

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
    control_guitar_toggle = None
    # Session-Token: Die Seite ist bewusst im ganzen LAN erreichbar (Handy auf
    # dem Notenstaender), und ANZEIGEN ist harmlos. EINGREIFEN darf aber nur,
    # wer die URL wirklich hat - aus Terminal oder QR-Code, wo das Token schon
    # drinsteht. Das sperrt zugleich CSRF aus: eine fremde Webseite kann zwar
    # blind POSTen, kennt aber das Token nicht.
    token: str = ""

    def log_message(self, *_):
        pass  # kein Request-Log im Terminal

    def _authorized(self) -> bool:
        supplied = parse_qs(urlparse(self.path).query).get("k", [""])[0]
        return bool(self.token) and secrets.compare_digest(supplied, self.token)

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
        elif path == "/timeline-poc":
            self._send(TIMELINE_POC_PAGE.encode(), "text/html; charset=utf-8")
        elif path == "/qr.svg":
            # Der QR-Code traegt die URL SAMT Token. Offen ausgeliefert waere
            # er die Hintertuer, ueber die sich jeder im LAN das Token holt.
            if not self._authorized():
                self.send_error(403, "missing or wrong token")
                return
            self._send(self.qr_bytes, "image/svg+xml")
        elif path == "/events":
            self._serve_events()
        else:
            self.send_error(404)

    def do_POST(self):
        """Stumm umschalten. Die Antwort ist der neue Zustand.

        Warum POST und nicht GET? Das hier ist kein Abruf, sondern ein Eingriff -
        und ein GET wuerde jeder Link-Vorschau, jedem Prefetch des Browsers die
        Musik abstellen. Und weil es ein Eingriff ist, verlangt er das
        Session-Token (?k=..., siehe oben).
        """
        if not self._authorized():
            self.send_error(403, "missing or wrong token")
            return
        path = self.path.split("?")[0]
        if path == "/control-guitar":
            if self.control_guitar_toggle is None:
                self.send_error(503, "no audio stream")
                return
            enabled = bool(self.control_guitar_toggle())
            self._send(json.dumps({"control_guitar": enabled}).encode(),
                       "application/json")
            return
        if path != "/mute":
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

    def set_control_guitar_toggle(self, fn):
        self._handler.control_guitar_toggle = staticmethod(fn)

    def stop(self):
        self._server.shutdown()
        self._server.server_close()


def start(port: int = DEFAULT_PORT) -> WebDisplay:
    broadcaster = ChordBroadcaster()
    handler = type("Handler", (_Handler,), {
        "broadcaster": broadcaster,
        "token": secrets.token_urlsafe(8),
    })
    server = ThreadingHTTPServer(("0.0.0.0", port), handler)
    # URL und QR erst NACH dem Binden: bei port=0 (Tests) vergibt erst das
    # Betriebssystem den echten Port.
    url = f"http://{lan_ip()}:{server.server_address[1]}/?k={handler.token}"
    handler.qr_bytes = _qr_svg(url)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return WebDisplay(server, url, broadcaster, handler)


# Die Seite selbst liegt als echte HTML-Datei in den Paketdaten
# (data/index.html) - mit Editor-Unterstuetzung und Diff-Lesbarkeit, statt als
# 1300-Zeilen-String im Modul. Einmal beim Import gelesen: Der Server liefert
# sie aus dem Speicher, und ein defektes Bundle faellt sofort auf, nicht erst
# beim ersten Request.
PAGE = (Path(__file__).with_name("data") / "index.html").read_text(encoding="utf-8")
TIMELINE_POC_PAGE = (Path(__file__).with_name("data") / "timeline_poc.html").read_text(
    encoding="utf-8")

"""Kontrollfenster: der sichtbare Schalter fuer die Audioumleitung.

Es gibt dieses Fenster aus einem einzigen Grund, und der ist ein Fehler im
bisherigen Entwurf: JamPilot biegt den Systemton um. Wer die Webseite schliesst -
und irgendwann schliesst sie jeder -, hat danach KEINE Oberflaeche mehr, sieht
nur noch ein Terminal (oder gar nichts) und wundert sich, warum sein Ton
verzoegert, stumm oder "kaputt" ist. Ohne Fenster gibt es keinen Weg zurueck,
den man findet, ohne die Dokumentation zu lesen.

Deshalb ist der grosse Schalter ganz oben "Audio through JamPilot", und deshalb
steht darunter im Klartext, was AUS bedeutet: dein Ton ist sofort wieder normal.
Das Fenster ist die Notbremse, nicht die Hauptbedienung - gespielt wird nach der
Webanzeige.

Qt (PySide6) laeuft im HAUPTTHREAD, die Analyse in einem Hintergrundthread. Das
ist keine Stilfrage: Unter macOS darf die Oberflaeche ausschliesslich im
Hauptthread laufen, sonst stuerzt der Prozess ab. Die Oberflaeche fragt den
Zustand per Timer ab, statt sich aus dem Analysethread rufen zu lassen - ein
Widget aus einem fremden Thread anzufassen ist genau der Fehler, den man damit
gar nicht erst machen kann.
"""

import sys
import threading
import webbrowser
from pathlib import Path

from PySide6.QtCore import (Property, QEasingCurve, QPropertyAnimation, QSize, Qt,
                            QTimer, Signal)
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette
from PySide6.QtWidgets import (QAbstractButton, QApplication, QFrame, QHBoxLayout,
                               QLabel, QPushButton, QVBoxLayout, QWidget)

# Das Programmsymbol (Bildmarke: Plektrum mit Note und Balken) liegt bei den
# Paketdaten, neben der Webseite - dieselbe Datei liefert web.py als Favicon aus.
ICON_DATEI = Path(__file__).with_name("data") / "icon.png"

BG = "#111316"
KARTE = "#181b1f"
TEXT = "#e8eaed"
GRAU = "#8a9199"
BLAU = "#6ea8ff"
AMBER = "#f5a524"
ROT = "#e2483d"
GRUEN = "#3ddc7f"


class Schieber(QAbstractButton):
    """Ein Schalter, kein Haekchen.

    Ein Haekchen sagt "Option gewaehlt", ein Schieber sagt "das laeuft gerade" -
    und genau das ist hier die Frage. Die Animation ist nicht Zierde: Sie zeigt,
    DASS geschaltet wurde, auch wenn man gerade woanders hinsieht.
    """

    def __init__(self, farbe=BLAU, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self._farbe = QColor(farbe)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"schieberPos", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)
        self.toggled.connect(self._animieren)

    def sizeHint(self):
        return QSize(52, 30)

    def _animieren(self, an):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if an else 0.0)
        self._anim.start()

    def sofort(self, an: bool):
        """Zustand OHNE Animation setzen - fuer das Nachziehen aus der Engine.

        Beim Oeffnen des Fensters laeuft der Betrieb laengst. Wuerde der Schieber
        von "aus" losanimieren, zeigte das Fenster im ersten Moment genau die
        Luege, gegen die es gebaut wurde. Animiert wird nur, was der Nutzer
        selbst anfasst.
        """
        if self.isChecked() == an and self._pos == (1.0 if an else 0.0):
            return
        self._anim.stop()
        blockiert = self.blockSignals(True)
        self.setChecked(an)
        self.blockSignals(blockiert)
        self._pos = 1.0 if an else 0.0
        self.update()

    def _get_pos(self):
        return self._pos

    def _set_pos(self, wert):
        self._pos = wert
        self.update()

    schieberPos = Property(float, _get_pos, _set_pos)

    def paintEvent(self, _ereignis):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        r = h / 2.0
        aus = QColor("#33383e")
        bahn = QColor(aus)
        ziel = self._farbe if self.isEnabled() else QColor("#3a4048")
        # Farbe mitwandern lassen: Der Schieber faerbt sich, waehrend er laeuft.
        bahn.setRgbF(
            aus.redF() + (ziel.redF() - aus.redF()) * self._pos,
            aus.greenF() + (ziel.greenF() - aus.greenF()) * self._pos,
            aus.blueF() + (ziel.blueF() - aus.blueF()) * self._pos,
        )
        p.setPen(Qt.NoPen)
        p.setBrush(bahn)
        p.drawRoundedRect(0, 0, self.width(), h, r, r)

        knopf_r = r - 3
        x = 3 + self._pos * (self.width() - 2 * knopf_r - 6)
        p.setBrush(QColor("#ffffff" if self.isEnabled() else "#7a8189"))
        p.drawEllipse(int(x), 3, int(knopf_r * 2), int(knopf_r * 2))


class _Zeile(QWidget):
    """Ein Schalter mit Titel und Erklaerung darunter."""

    def __init__(self, titel, erklaerung, farbe=BLAU):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        texte = QVBoxLayout()
        texte.setSpacing(2)
        self.titel = QLabel(titel)
        self.titel.setStyleSheet(f"color:{TEXT}; font-size:14px; font-weight:600;")
        self.erklaerung = QLabel(erklaerung)
        self.erklaerung.setWordWrap(True)
        self.erklaerung.setStyleSheet(f"color:{GRAU}; font-size:11px;")
        texte.addWidget(self.titel)
        texte.addWidget(self.erklaerung)

        layout.addLayout(texte, 1)
        self.schieber = Schieber(farbe)
        layout.addWidget(self.schieber, 0, Qt.AlignVCenter)


class Fenster(QWidget):
    # Der Warmup laeuft in einem Hintergrundthread und muss melden, dass er durch
    # ist. Ein Signal ist der EINZIGE Weg, aus einem fremden Thread an die
    # Oberflaeche zu kommen: Qt stellt es in die Ereignisschlange des
    # Hauptthreads, statt das Widget von aussen anzufassen.
    vorbereitet = Signal()

    def __init__(self, engine, url: str | None):
        super().__init__()
        self.engine = engine
        self.url = url
        self._eigene_aenderung = False   # unterscheidet Klick von Nachziehen
        self.startet = False             # Warmup laeuft, der Betrieb noch nicht

        self.setWindowTitle("JamPilot")
        self.setWindowIcon(QIcon(str(ICON_DATEI)))
        self.setMinimumWidth(380)
        self.setStyleSheet(f"background:{BG};")

        wurzel = QVBoxLayout(self)
        wurzel.setContentsMargins(22, 20, 22, 18)
        wurzel.setSpacing(16)

        # --- Zustand, ganz oben und gross genug, um es zu glauben ------------
        kopf = QHBoxLayout()
        kopf.setSpacing(10)
        self.punkt = QLabel("●")
        self.punkt.setStyleSheet(f"color:{ROT}; font-size:15px;")
        self.zustand = QLabel("Stopped")
        self.zustand.setStyleSheet(
            f"color:{TEXT}; font-size:19px; font-weight:700; letter-spacing:.5px;")
        kopf.addWidget(self.punkt)
        kopf.addWidget(self.zustand)
        kopf.addStretch(1)
        wurzel.addLayout(kopf)

        # --- Der Hauptschalter: die Notbremse --------------------------------
        karte = QFrame()
        karte.setStyleSheet(f"background:{KARTE}; border-radius:10px;")
        karten_layout = QVBoxLayout(karte)
        karten_layout.setContentsMargins(16, 14, 16, 14)
        karten_layout.setSpacing(14)

        self.routing = _Zeile(
            "Audio through JamPilot",
            "Off puts your system sound back to normal, right away.",
            BLAU)
        self.routing.schieber.toggled.connect(self._routing_geschaltet)
        karten_layout.addWidget(self.routing)

        trenner = QFrame()
        trenner.setFixedHeight(1)
        trenner.setStyleSheet("background:#24282d; border:0;")
        karten_layout.addWidget(trenner)

        self.stumm = _Zeile(
            "Sound",
            "Mutes the delayed output. The music keeps playing and the chords "
            "keep running — you just hear nothing.",
            AMBER)
        self.stumm.schieber.toggled.connect(self._stumm_geschaltet)
        karten_layout.addWidget(self.stumm)
        wurzel.addWidget(karte)

        self.info = QLabel("")
        self.info.setStyleSheet(f"color:{GRAU}; font-size:11px;")
        wurzel.addWidget(self.info)

        # Die Adresse der Webanzeige - anklickbar, und vor allem LESBAR. Am Handy
        # tippt man sie ab oder scannt den QR-Code auf der Seite selbst; dafuer
        # muss sie hier stehen und nicht in einem Terminal, das laengst zu ist.
        # `setSelectable` ist Absicht: Man will sie kopieren koennen.
        self.link = QLabel()
        self.link.setOpenExternalLinks(True)
        self.link.setTextInteractionFlags(
            Qt.TextBrowserInteraction | Qt.TextSelectableByMouse)
        self.link.setStyleSheet(f"color:{GRAU}; font-size:12px;")
        self.link.setCursor(Qt.PointingHandCursor)
        if url:
            self.link.setText(
                f'<span style="color:{GRAU};">Display&nbsp;&nbsp;</span>'
                f'<a href="{url}" style="color:{BLAU}; text-decoration:none;">{url}</a>')
        else:
            self.link.setText(
                f'<span style="color:{GRAU};">Web display off '
                f'(started with --no-web)</span>')
        wurzel.addWidget(self.link)

        # --- Knoepfe ---------------------------------------------------------
        knoepfe = QHBoxLayout()
        knoepfe.setSpacing(8)
        self.anzeige_knopf = QPushButton("Open display")
        self.anzeige_knopf.setCursor(Qt.PointingHandCursor)
        self.anzeige_knopf.setStyleSheet(
            f"QPushButton {{ background:{KARTE}; color:{BLAU}; border:1px solid #2b3037;"
            f"  border-radius:7px; padding:8px 14px; font-size:12px; font-weight:600; }}"
            f"QPushButton:hover {{ border-color:{BLAU}; }}"
            f"QPushButton:disabled {{ color:#4a5058; border-color:#22262b; }}")
        self.anzeige_knopf.clicked.connect(self._anzeige_oeffnen)
        self.anzeige_knopf.setEnabled(bool(url))
        knoepfe.addWidget(self.anzeige_knopf)
        knoepfe.addStretch(1)

        beenden = QPushButton("Quit")
        beenden.setCursor(Qt.PointingHandCursor)
        beenden.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{GRAU}; border:1px solid #2b3037;"
            f"  border-radius:7px; padding:8px 14px; font-size:12px; }}"
            f"QPushButton:hover {{ color:{ROT}; border-color:{ROT}; }}")
        beenden.clicked.connect(self.close)
        knoepfe.addWidget(beenden)
        wurzel.addLayout(knoepfe)

        self.hinweis = QLabel("")
        self.hinweis.setWordWrap(True)
        self.hinweis.setStyleSheet(f"color:{AMBER}; font-size:11px;")
        self.hinweis.hide()
        wurzel.addWidget(self.hinweis)

        # Was der Start gerade tut - EINE Zeile, die wechselt, kein Log. Beim
        # allerersten Start eines Binaries steht das Fenster bis zu einer
        # Minute auf "Starting"; hier steht dann "Compiling the analysis
        # (first start: up to a minute) ...", und man sieht, dass es arbeitet
        # statt zu haengen. Gelesen wird per Timer aus engine.protokoll
        # (nachziehen); ein Zaehler spart das Neusetzen.
        #
        # Die Zeile ist IMMER da und reserviert zwei Zeilen Hoehe, auch leer.
        # Sonst wuerde das Fenster mit dem kleinen Stopped-Inhalt aufgehen und
        # der Inhalt danach wachsen - und ein Layout mit umbrechenden Labels
        # zieht ein geoeffnetes Fenster nicht nach: Die Karten oben werden
        # zusammengedrueckt, bis der Starthinweis bei "Running" verschwindet.
        # Genau so sah es aus. Was das Fenster spaeter zeigen soll, muss beim
        # show() schon Platz haben (siehe auch run()).
        self.etappe = QLabel("")
        self.etappe.setWordWrap(True)
        schrift = self.etappe.font()
        schrift.setPixelSize(11)
        self.etappe.setFont(schrift)
        self.etappe.setStyleSheet(f"color:{GRAU}; font-size:11px;")
        self.etappe.setMinimumHeight(2 * self.etappe.fontMetrics().lineSpacing())
        wurzel.addWidget(self.etappe)
        self._etappe_stand = -1

        # Der Analysethread darf keine Widgets anfassen. Also fragen WIR ihn.
        self._takt = QTimer(self)
        self._takt.timeout.connect(self.nachziehen)
        self._takt.start(200)
        self.nachziehen()

    # --- Bedienung ----------------------------------------------------------
    def _routing_geschaltet(self, an: bool):
        if self._eigene_aenderung:
            return
        try:
            self.engine.start() if an else self.engine.stop()
        except Exception as exc:
            self.hinweis.setText(f"Could not start: {exc}")
            self.hinweis.show()
        self.nachziehen()

    def _stumm_geschaltet(self, an: bool):
        # Der Schieber zeigt SOUND, nicht MUTE: oben = man hoert etwas.
        if self._eigene_aenderung:
            return
        if self.engine.running and self.engine.muted == an:
            self.engine.toggle_mute()
        self.nachziehen()

    def _anzeige_oeffnen(self):
        if self.url:
            webbrowser.open(self.url)

    def nachziehen(self):
        """Oberflaeche an den Zustand der Engine angleichen."""
        e = self.engine
        self._eigene_aenderung = True      # Schieber setzen, ohne sie auszuloesen
        try:
            self.routing.schieber.sofort(e.running)
            # Waehrend des Warmups laesst sich nichts schalten: Der Betrieb wird
            # gleich von selbst anlaufen, und ein Klick jetzt startete ihn ohne
            # uebersetzten JIT - der erste Akkord kaeme dann verstolpert.
            self.routing.schieber.setEnabled(not self.startet)
            self.stumm.schieber.sofort(e.running and not e.muted)
            self.stumm.schieber.setEnabled(e.running)
        finally:
            self._eigene_aenderung = False

        if e.status == "error":
            self.punkt.setStyleSheet(f"color:{ROT}; font-size:15px;")
            self.zustand.setText("Error")
            self.hinweis.setText(e.fehler or "unknown error")
            self.hinweis.setStyleSheet(f"color:{ROT}; font-size:11px;")
            self.hinweis.show()
        elif self.startet:
            # Der sichtbare Beweis, dass der Doppelklick angekommen ist. Ohne ihn
            # steht hier waehrend des Warmups "Stopped" - und das ist zwar wahr
            # (noch ist nichts umgeleitet), sieht aber aus wie ein Programm, das
            # nicht tut, was es soll. Welche Etappe gerade laeuft, steht in
            # der Zeile darunter (self.etappe).
            self.punkt.setStyleSheet(f"color:{AMBER}; font-size:15px;")
            self.zustand.setText("Starting")
            self.hinweis.setText("Preparing the analysis — a few seconds, on the "
                                 "very first start up to a minute. Then the "
                                 "sound starts running through JamPilot.")
            self.hinweis.setStyleSheet(f"color:{GRAU}; font-size:11px;")
            self.hinweis.show()
        elif not e.running:
            self.punkt.setStyleSheet(f"color:{GRAU}; font-size:15px;")
            self.zustand.setText("Stopped")
            self.hinweis.setText("Your system sound is normal. Nothing is routed "
                                 "through JamPilot.")
            self.hinweis.setStyleSheet(f"color:{GRAU}; font-size:11px;")
            self.hinweis.show()
        elif e.muted:
            self.punkt.setStyleSheet(f"color:{AMBER}; font-size:15px;")
            self.zustand.setText("Muted")
            self.hinweis.setText("Still routed — you hear nothing, but the "
                                 "chords keep running.")
            self.hinweis.setStyleSheet(f"color:{AMBER}; font-size:11px;")
            self.hinweis.show()
        else:
            self.punkt.setStyleSheet(f"color:{GRUEN}; font-size:15px;")
            self.zustand.setText("Running")
            self.hinweis.hide()

        if e.running:
            self.info.setText(f"Delay {e.delay_seconds:.1f} s   ·   "
                              f"Lead {max(e.lead, 0.0):.1f} s")
        else:
            self.info.setText("")

        # Dieselbe Zeile, zwei Leben: waehrend des Starts die Etappe, danach
        # die Live-Zeile der Analyse ("Now playing C · in 3.0 s: G · Key C
        # major"). getattr: Die Attrappe im Selbsttest hat weder das eine noch
        # das andere - und braucht es nicht.
        live = getattr(e, "jetzt", "") if e.running else ""
        if live:
            if self.etappe.text() != live:
                self.etappe.setText(live)
            self._etappe_stand = -1       # nach dem Stopp wieder die Etappen
            return
        protokoll = getattr(e, "protokoll", None)
        if protokoll is not None and protokoll.stand() != self._etappe_stand:
            self._etappe_stand = protokoll.stand()
            self.etappe.setText(protokoll.aktuell())

    def closeEvent(self, ereignis):
        """Fenster zu = Programm zu - und damit Ton zurueck.

        Das Fenster im Hintergrund weiterlaufen zu lassen waere genau die Falle,
        gegen die es gebaut wurde: eine unsichtbare Umleitung ohne Bedienung.
        Lieber ein Klick zu viel beendet, als ein Rechner, der grundlos stumm ist.
        """
        self.engine.stop()
        ereignis.accept()


def beenden_bei_signal(app) -> "QTimer":
    """Strg+C und `kill` muessen die Qt-Schleife verlassen - sauber.

    Das ist kein Feinschliff, sondern die Notbremse hinter der Notbremse. Ohne
    das hier ueberlebt JamPilot ein SIGTERM: Der Prozess laeuft weiter, der
    Null-Sink bleibt der Standardausgang - und der Rechner bleibt STUMM. Genau
    der Zustand, gegen den es dieses Fenster ueberhaupt gibt.

    Zwei Fallen stecken darin, und beide sind zugeschnappt:

    1. Ein Signalhandler, der KeyboardInterrupt WIRFT (so macht es die
       Kommandozeile in cli.py), hilft hier nichts: Die Ausnahme entsteht im
       Aufruf einer Qt-Verbindung, und PySide6 faengt sie dort ab, druckt einen
       Traceback und macht weiter. Nachgemessen - der Prozess liess sich nur
       noch mit `kill -9` beenden. Also nicht werfen, sondern app.quit() rufen.

    2. Python fuehrt Signalhandler nur zwischen Bytecodes aus. Waehrend
       app.exec() laeuft, steckt der Interpreter in C++ und kommt nie dazu. Ein
       Zeitgeber, der nichts tut, gibt ihm alle 200ms die Gelegenheit. (Das
       Fenster hat ohnehin einen - aber sich darauf zu verlassen, hiesse, dass
       ein Aufraeumen dort hier still den Notausgang zumauert.)
    """
    import signal

    # SIGHUP gehoert dazu, und zwar aus demselben Grund: Wer sein Terminal
    # schliesst oder dessen SSH-Sitzung abbricht, bekommt genau dieses Signal.
    # Unbehandelt beendet es den Prozess SOFORT - ohne finally, ohne Abbau, mit
    # dem Null-Sink als Standardausgang. Der Rechner bliebe stumm, und der
    # Nutzer haette nicht einmal mehr ein Fenster, in dem er das umlegen kann.
    # (Nachgemessen: genau so passiert.)
    zeichen = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGHUP"):
        zeichen.append(signal.SIGHUP)
    for eines in zeichen:
        signal.signal(eines, lambda *_: app.quit())

    wecker = QTimer()
    wecker.timeout.connect(lambda: None)
    wecker.start(200)
    return wecker            # der Aufrufer muss ihn halten, sonst raeumt Qt ihn ab


def run(engine, url: str | None, autostart: bool = False, vorbereiten=None) -> int:
    """Fenster oeffnen und die Qt-Schleife im Hauptthread fahren.

    `autostart` startet den Betrieb ERST, wenn das Fenster schon steht (per
    Timer, also aus der laufenden Qt-Schleife heraus). Der Unterschied zaehlt im
    Fehlerfall: Scheitert die Soundkarte, sieht der Nutzer die Meldung IM
    Fenster, neben dem Schalter - statt einen Traceback in einem Terminal, das er
    vielleicht gar nicht offen hat.

    `vorbereiten` ist die teure Vorarbeit (numbas JIT uebersetzen, ~3s). Sie
    laeuft in einem HINTERGRUNDTHREAD, waehrend das Fenster schon steht. Vorher
    lief sie davor - und wer die App doppelklickt, sah dadurch mehrere Sekunden
    lang ueberhaupt nichts, weil ein Doppelklick kein Terminal hat, in dem
    "Initialising analysis..." stuende. Ein Programm, das nach dem Klick nichts
    zeigt, ist fuer den Nutzer ein Programm, das nicht startet.

    Der Warmup laeuft VOR dem Audio, nicht daneben: Der Stream soll nicht schon
    Toene in den Puffer schieben, waehrend die halbe CPU im JIT-Compiler steckt.
    """
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("JamPilot")
    app.setWindowIcon(QIcon(str(ICON_DATEI)))
    # Unter Wayland nimmt die Fensterleiste das Symbol nicht vom Fenster, sondern
    # vom Starter: Der Name hier muss zur .desktop-Datei passen (desktop.py).
    app.setDesktopFileName("jampilot")
    palette = app.palette()
    palette.setColor(QPalette.Window, QColor(BG))
    app.setPalette(palette)

    _wecker = beenden_bei_signal(app)     # muss leben, solange die Schleife laeuft

    fenster = Fenster(engine, url)
    # "Starting" VOR dem show(): Das Fenster oeffnet sich in der Groesse seines
    # Inhalts, und nachwachsen tut es nicht (siehe Fenster.__init__ bei
    # self.etappe). Der Starthinweis ist der laengste Text, den es zeigt - er
    # muss also schon dastehen, wenn die Groesse bestimmt wird.
    if autostart and vorbereiten is not None:
        fenster.startet = True
        fenster.nachziehen()
    fenster.show()
    fenster.raise_()
    fenster.activateWindow()
    protokoll = getattr(engine, "protokoll", None)
    if protokoll is not None:
        protokoll.melden("Window open")

    if autostart:
        def anwerfen():
            fenster.startet = False
            try:
                engine.start()
            except Exception as exc:
                fenster.hinweis.setText(f"Could not start: {exc}")
                fenster.hinweis.setStyleSheet(f"color:{ROT}; font-size:11px;")
                fenster.hinweis.show()
            fenster.nachziehen()

        # Queued ueber die Ereignisschlange - `anwerfen` laeuft also im
        # Hauptthread, auch wenn das Signal aus dem Warmup-Thread kommt.
        fenster.vorbereitet.connect(anwerfen)

        if vorbereiten is None:
            QTimer.singleShot(0, anwerfen)
        else:
            def vorheizen():
                try:
                    vorbereiten()
                except Exception:
                    # Ein gescheiterter Warmup ist kein Grund, gar nicht zu
                    # starten: numba uebersetzt dann eben beim ersten Fenster.
                    # Was wirklich kaputt ist, meldet engine.start() - im Fenster.
                    pass
                fenster.vorbereitet.emit()

            threading.Thread(target=vorheizen, daemon=True).start()

    return app.exec()


def verfuegbar() -> bool:
    """Laesst sich hier ueberhaupt ein Fenster oeffnen?

    Auf einem Server per SSH, in der CI oder unter `nohup` gibt es keine Anzeige.
    Dann faellt der Betrieb auf die reine Kommandozeile zurueck, statt mit einem
    Qt-Fehler zu sterben.
    """
    try:
        import PySide6  # noqa: F401
    except ImportError:
        return False
    import os

    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True

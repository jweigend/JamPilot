"""Der laufende Betrieb als EIN schaltbares Ding: Umleitung + Stream + Analyse.

Warum es diese Schicht gibt: Bisher war der Betrieb an einen `with`-Block in
cmd_run gekettet - anfangen und aufhoeren konnte man nur, indem man das Programm
startete oder beendete. Das Kontrollfenster braucht aber genau das dazwischen:
mittendrin abschalten, ohne das Programm zu verlassen.

Und das ist keine Bequemlichkeit, sondern behebt eine Falle. JamPilot biegt den
Systemton um: Alles laeuft in einen Null-Sink, den nur wir abhoeren. Wer die
Webseite schliesst, sieht davon nichts mehr - aber sein Ton bleibt umgeleitet.
Er hoert nur noch die verzoegerte Ausgabe, findet kein Fenster, das das erklaert,
und haelt seinen Rechner fuer kaputt. Deshalb MUSS es einen sichtbaren Schalter
geben, der die Umleitung zurueckdreht.

AUS heisst dabei wirklich AUS - Umleitung UND Stream:

    Nur die Umleitung zurueckzudrehen und den Stream weiterlaufen zu lassen waere
    schlimmer als gar nichts. Der Stream liest die "default"-Quelle. Sobald die
    Umleitung faellt, ist das wieder die urspruengliche Quelle - typischerweise
    das MIKROFON. JamPilot wuerde dann das Mikrofon verzoegert ausgeben und
    dessen Akkorde anzeigen. Also: Stream anhalten, dann zurueckbauen.
"""

import sys
import threading
import time
from contextlib import contextmanager


def _standardgeraet():
    """Was "nimm das Standardgeraet" fuer PortAudio heisst.

    sounddevice loest Geraetenamen per Teilstring-Suche auf. Unter Linux ist
    `default` ein echter ALSA-/PulseAudio-Name und trifft; unter Windows und
    macOS existiert kein Geraet dieses Namens, und die Suche endet in einem
    ValueError, bevor irgendetwas laeuft. Die richtige Angabe ist dort None -
    dann nimmt PortAudio selbst sein Standardgeraet.
    """
    return "default" if sys.platform.startswith("linux") else None


class Startprotokoll:
    """Die Etappen des Starts - mitlesbar im Fenster und im Terminal.

    Warum es das gibt: Der allererste Start eines Binaries dauert bis zu einer
    Minute (numba uebersetzt seine Kerne und legt den Cache an; gemessen 23 s
    auf einem aktuellen Rechner, 2 s mit warmem Cache). Ein Fenster, das so
    lange "Starting" sagt und sonst nichts, sieht aus wie ein Programm, das
    haengt - und wird geschlossen, kurz bevor es fertig waere. Hier steht
    deshalb, WAS gerade passiert und wie lange die Etappen davor gebraucht
    haben.

    Threadsicher, ohne Qt: Warmup, Engine.start() und die Analyse laufen in
    verschiedenen Threads und schreiben alle hier hinein; das Fenster liest per
    Timer (`stand()` sagt ihm billig, ob sich etwas geaendert hat) und zeigt
    nur die juengste Zeile (`aktuell()`). `ausgabe` bekommt jede fertige Zeile
    zusaetzlich - im Terminal ist das print, und dort darf es ein Log sein.
    """

    def __init__(self, ausgabe=None, t0: float | None = None):
        self._t0 = time.monotonic() if t0 is None else t0
        self._lock = threading.Lock()
        self._eintraege: list[dict] = []
        self._stand = 0
        self.ausgabe = ausgabe

    # --- schreiben -----------------------------------------------------------
    def melden(self, text: str) -> None:
        """Ein Ereignis ohne Dauer ("Window open")."""
        self._anfuegen({"text": text, "beginn": self._jetzt(), "dauer": 0.0,
                        "fehler": None})

    @contextmanager
    def etappe(self, text: str):
        """Eine Etappe mit Dauer - die Zeile entsteht beim Eintritt (mit "...")
        und bekommt beim Verlassen ihre Dauer, oder den Fehler."""
        eintrag = {"text": text, "beginn": self._jetzt(), "dauer": None,
                   "fehler": None}
        self._anfuegen(eintrag)
        try:
            yield
        except BaseException as exc:
            self._abschliessen(eintrag, fehler=str(exc) or type(exc).__name__)
            raise
        else:
            self._abschliessen(eintrag)

    # --- lesen ---------------------------------------------------------------
    def stand(self) -> int:
        """Zaehler, der sich mit jeder Aenderung erhoeht - fuers Polling."""
        with self._lock:
            return self._stand

    def zeilen(self) -> list[str]:
        with self._lock:
            return [self._zeile(e) for e in self._eintraege]

    def aktuell(self) -> str:
        """Die juengste Etappe ohne Zeitstempel - die EINE Zeile fuers Fenster.

        Das Fenster ist kein Log: Es zeigt, was gerade passiert, und die Zeile
        wechselt, wenn die naechste Etappe beginnt. Was alles davor war, steht
        im Terminal.
        """
        with self._lock:
            if not self._eintraege:
                return ""
            return self._zeile(self._eintraege[-1], mit_zeit=False)

    # --- intern --------------------------------------------------------------
    def _jetzt(self) -> float:
        return time.monotonic() - self._t0

    def _anfuegen(self, eintrag: dict) -> None:
        with self._lock:
            self._eintraege.append(eintrag)
            self._stand += 1
        if eintrag["dauer"] is not None:
            self._ausgeben(eintrag)

    def _abschliessen(self, eintrag: dict, fehler: str | None = None) -> None:
        with self._lock:
            eintrag["dauer"] = self._jetzt() - eintrag["beginn"]
            eintrag["fehler"] = fehler
            self._stand += 1
        self._ausgeben(eintrag)

    def _ausgeben(self, eintrag: dict) -> None:
        if self.ausgabe is not None:
            self.ausgabe(self._zeile(eintrag))

    @staticmethod
    def _zeile(e: dict, mit_zeit: bool = True) -> str:
        kopf = f"{e['beginn']:5.1f} s  {e['text']}" if mit_zeit else e["text"]
        if e["fehler"]:
            return f"{kopf} - failed: {e['fehler']}"
        if e["dauer"] is None:
            return f"{kopf} ..."
        if e["dauer"] < 0.05:
            return kopf
        return f"{kopf} ({e['dauer']:.1f} s)"


# Akkordspruenge im Record-Modus (Engine.seek_chord). Beide Werte sind
# Playtest-Kandidaten, keine Messwerte - sie stehen hier, damit man sie im
# Proberaum drehen kann.
#
# VORLAUF: Der Sprung landet so viele Sekunden VOR dem Onset. Wer einen Wechsel
# lernen will, muss den Anlauf hoeren.
VORLAUF = 0.7
# NEUSTART_SCHWELLE: Steht man weniger als so lange im laufenden Akkord, geht
# "zurueck" an den vorigen; sonst an den Anfang des laufenden (CD-Player).
NEUSTART_SCHWELLE = 1.0


class Engine:
    """Umleitung, Audiostream und Analyse - startbar und stoppbar zur Laufzeit.

    Zustaende:
        running=False           aus. Der Systemton laeuft normal, JamPilot fasst
                                nichts an. (Auch der Zustand nach `stop()`.)
        running=True            laeuft. Ton wird umgeleitet, verzoegert, analysiert.
        running=True, muted     laeuft, aber der Lautsprecher schweigt. Puffer und
                                Analyse laufen weiter (siehe delay_stream).
    """

    def __init__(self, args, broadcaster=None, on_change=None, protokoll=None):
        self.args = args
        self.broadcaster = broadcaster
        # Die Etappen des Starts, fuer Fenster und Terminal. Wer keines
        # mitgibt, bekommt ein stilles - die Tests und `analyze` brauchen keins.
        self.protokoll = protokoll or Startprotokoll()
        # Wird bei jedem Zustandswechsel gerufen, damit die Oberflaeche sich
        # nachzieht - ohne dass diese Schicht die Oberflaeche kennen muss.
        self._on_change = on_change or (lambda: None)

        self._loop = None
        self._route = None
        # Der Mitschnitt (record_buffer). None, bis zum ersten R - der Speicher
        # (eine halbe Stunde Stereo sind 659 MiB) wird erst dann reserviert,
        # und zwar in einem Hintergrundthread, nicht im Audio-Callback.
        self._record = None
        self._record_lade: threading.Thread | None = None
        self.record_hinweis: str | None = None   # warum R nichts tut
        # Onsets der committeten Events in Stream-Sekunden, vom Anzeigepfad je
        # Hop abgelegt - die Sprungziele der Pfeiltasten im Record-Modus.
        self.onsets: tuple[float, ...] = ()
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.lead = 0.0
        # Die Live-Zeile der Analyse ("Now playing C · in 3.0 s: G · Key C
        # major"), geschrieben vom Analysethread, gelesen vom Fenster. Leer,
        # solange noch kein Modelllauf durch ist - und nach dem Stopp.
        self.jetzt = ""
        self.status = "stopped"     # stopped | starting | running | error
        self.fehler: str | None = None

    # --- Zustand ------------------------------------------------------------
    @property
    def running(self) -> bool:
        return self._loop is not None

    @property
    def muted(self) -> bool:
        return self._loop.muted if self._loop else False

    @property
    def delay_seconds(self) -> float:
        return self._loop.delay_seconds if self._loop else float(self.args.delay)

    def toggle_mute(self) -> bool:
        if not self._loop:
            return False
        stumm = self._loop.toggle_mute()
        if self.broadcaster:
            self.broadcaster.republish(muted=stumm)
        self._on_change()
        return stumm

    # --- Record-Modus (Taste R) ---------------------------------------------
    # Alles hier faellt auf gutmuetige Vorgaben zurueck, wenn es keinen
    # Mitschnitt gibt (Speicher reichte nicht, --record-buffer 0, oder R wurde
    # nie gedrueckt). Die Oberflaechen duerfen die Tasten immer anbieten - sie
    # tun dann nichts, und `record_hinweis` sagt warum.
    @property
    def recording(self) -> bool:
        return self._loop.recording if self._loop else False

    @property
    def record_pending(self) -> bool:
        """R ist gedrueckt, der Speicher wird gerade reserviert."""
        return self._record_lade is not None

    @property
    def record_paused(self) -> bool:
        return self._loop.record_paused if self._loop else False

    @property
    def record_offset(self) -> float:
        """Sekunden hinter der Live-Kante."""
        return self._loop.record_offset_seconds if self._loop else 0.0

    @property
    def record_epoch(self) -> int:
        """Zaehler der Zeitspruenge - die Anzeige stellt daran ihre Uhr neu."""
        return self._loop.record_epoch if self._loop else 0

    def toggle_record(self) -> bool:
        """R: Mitschnitt an oder aus. Gibt zurueck, ob er danach laeuft.

        AUS ist immer sofort: zurueck an die Live-Kante, Inhalt verworfen. AN
        braucht beim allerersten Mal den Speicher - der wird im Hintergrund
        geholt, und die Aufnahme beginnt, sobald er da ist (~0,2 s). Man drueckt
        R, weil man aufzeichnen will, was KOMMT; die zwei Zehntel fehlen
        niemandem. Waehrend des Ladens ist R wirkungslos: Ein zweiter Druck
        darf nicht abbrechen, was der erste angestossen hat.
        """
        if not self._loop:
            return False
        if self.recording:
            self._record.stop_record()
            self._record_gemeldet()
            return False
        if self._record_lade is not None:
            return False
        if self._record is None:
            if self.record_hinweis:
                return False                 # schon einmal gescheitert
            self._record_lade = threading.Thread(
                target=self._record_anlegen, name="record-buffer", daemon=True)
            self._record_lade.start()
            self._on_change()
            return True
        self._record.start_record()
        self._record_gemeldet()
        return True

    def _record_anlegen(self):
        """Im Hintergrundthread: reservieren, anfassen, einhaengen, starten."""
        from . import record_buffer

        loop = self._loop
        try:
            if loop is None:
                return
            gewuenscht = float(getattr(self.args, "record_buffer",
                                       record_buffer.DEFAULT_MINUTES))
            minuten, hinweis = record_buffer.plan(
                gewuenscht, loop.samplerate, loop.channels)
            if minuten <= 0:
                self.record_hinweis = hinweis or "record buffer is disabled"
                return
            try:
                puffer = record_buffer.RecordBuffer(
                    loop.samplerate, loop.channels, minuten)
            except MemoryError:
                # Der Voraus-Check hat sich geirrt (oder jemand hat sich in der
                # Zwischenzeit den Speicher genommen). Kein Absturz - nur ein
                # Grund, warum R nichts tut.
                self.record_hinweis = ("record buffer did not fit in memory - "
                                       "record mode (R) is off")
                return
            if hinweis:
                self.protokoll.melden(hinweis)
            with self._lock:
                if self._loop is not loop:       # inzwischen gestoppt
                    return
                self._record = puffer
                loop.attach_record(puffer)
                puffer.start_record()
        finally:
            self._record_lade = None
            if self.record_hinweis:
                self.protokoll.melden(self.record_hinweis)
            self._record_gemeldet()

    def toggle_record_pause(self) -> bool:
        if not self.recording:
            return False
        zustand = self._record.toggle_pause()
        self._record_gemeldet()
        return zustand

    def record_to_now(self) -> None:
        if not self.recording:
            return
        self._record.to_now()
        self._record_gemeldet()

    def record_to_start(self) -> None:
        if not self.recording:
            return
        self._record.to_start()
        self._record_gemeldet()

    def seek_chord(self, richtung: int) -> None:
        """Pfeiltasten im Record-Modus: zum vorigen/naechsten Akkord.

        Die Sprungeinheit ist der AKKORD, nicht die Sekunde - man will nicht
        "fuenf Sekunden zurueck", man will "diesen Wechsel nochmal". Zwei
        Feinheiten, beide aus dem Ueben begruendet:

        * "Zurueck" heisst zuerst: an den Anfang des LAUFENDEN Akkords - die
          CD-Player-Konvention. Man drueckt zurueck, weil man diesen Wechsel
          nochmal will, nicht den davor. Erst wer schon am Anfang steht
          (NEUSTART_SCHWELLE), geht eine Grenze weiter zurueck.
        * Der Sprung landet VORLAUF Sekunden VOR dem Onset. Wer einen Wechsel
          lernen will, muss den Anlauf hoeren; genau auf die Grenze zu springen
          liefert den Zielakkord ohne das, was zu ihm hinfuehrt.

        Gelesen wird die volle Onset-Liste des Ledgers (`self.onsets`), nicht
        das veroeffentlichte Anzeige-Fenster - das reicht nur acht Sekunden
        zurueck, und ein Sprung ueber zehn Akkorde faende dort nichts.
        """
        if not self.recording or not richtung:
            return
        jetzt = self._loop.heard_position()
        onsets = self.onsets
        if richtung < 0:
            vorige = [o for o in onsets if o <= jetzt]
            if not vorige:
                self._record.to_start()
                self._record_gemeldet()
                return
            ziel = vorige[-1]
            if jetzt - ziel < NEUSTART_SCHWELLE and len(vorige) >= 2:
                ziel = vorige[-2]
        else:
            # Der naechste Onset, der samt Vorlauf noch VOR uns liegt - sonst
            # spraenge "vor" um ein paar Zehntel zurueck.
            kommende = [o for o in onsets if o - VORLAUF > jetzt + 0.05]
            if not kommende:
                self._record.to_now()
                self._record_gemeldet()
                return
            ziel = kommende[0]
        self._record.seek(ziel - VORLAUF - jetzt)
        self._record_gemeldet()

    def _record_gemeldet(self):
        """Zustandswechsel sofort an alle Anzeigen - wie beim Stummschalter.

        Warten auf den naechsten Analysetakt hiesse: Der Musiker drueckt eine
        Taste, der Ton reagiert sofort, aber die Anzeige laeuft noch weiter.
        Genau die Diskrepanz, die den Eindruck macht, die Taste habe nicht
        gegriffen.

        Was mitkommt, ist der MODUS: an, wird gerade reserviert, angehalten.
        Das ist, was der rote Punkt und die Transportleiste sofort brauchen.

        Was NICHT mitkommt - und das ist keine Luecke, sondern die Lehre aus
        einem Fehler -, ist `epoch`. `republish` mischt nur das Uebergebene in
        den LETZTEN Zustand, und der traegt noch das alte `t`. Ginge der Epoch
        hier mit, stellte die Seite ihre Uhr auf die ALTE Position neu; kaeme
        dann eine Viertelsekunde spaeter der volle Zustand mit dem richtigen
        `t`, waere der Epoch schon verbraucht, und statt eines Resets griffe die
        sanfte Drift-Glaettung (syncClock: Minimum ueber 40 Messwerte). Bei
        einem Sprung ZURUECK gewinnt der alte Messwert bis zu zehn Sekunden
        lang, bei einem Sprung VOR gleitet die Uhr ueber Sekunden nach - der
        Ton springt sofort, das Laufband nicht. Der Epoch reist darum
        ausschliesslich mit dem frischen `t` aus der Anzeigeschleife.
        """
        if self.broadcaster:
            self.broadcaster.republish(recording=self.recording,
                                       record_pending=self.record_pending,
                                       paused=self.record_paused)
        self._on_change()

    @property
    def control_guitar(self) -> bool:
        return self._loop.control_guitar if self._loop else False

    def toggle_control_guitar(self) -> bool:
        if not self._loop:
            return False
        enabled = self._loop.toggle_control_guitar()
        if self.broadcaster:
            self.broadcaster.republish(control_guitar=enabled)
        self._on_change()
        return enabled

    # --- An und aus ---------------------------------------------------------
    def start(self):
        """Umleitung aufbauen, Stream starten, Analyse im Hintergrund laufen lassen."""
        with self._lock:
            if self._loop is not None:
                return
            from . import routing
            from .delay_stream import DelayedLoopback

            self.status = "starting"
            self.fehler = None
            self._on_change()
            try:
                args = self.args
                nutzt_routing = routing.uses_routing(args)
                if nutzt_routing:
                    # WELCHE Geraete zu oeffnen sind, weiss die Umleitung - und
                    # nur sie. Unter Linux ist es zweimal "default", weil das
                    # Umbiegen ueber die Standardgeraete laeuft; unter Windows
                    # sind es zwei feste PortAudio-Indizes, weil dort das Kabel
                    # der Umweg ist. Diese Schicht darf das nicht wissen
                    # muessen, sonst steht die Plattformfrage zweimal im
                    # Programm.
                    with self.protokoll.etappe("Routing the system audio"):
                        self._route = routing.create(args)
                        self._route.__enter__()
                    # Die Umleitung darf die Abtastrate VORGEBEN: Beim
                    # Windows-Mute-Weg kommt der Mitschnitt im Mixformat des
                    # Endpunkts, und das ist nicht verhandelbar - eine andere
                    # Rate ergaebe schlicht eine andere Tonhoehe.
                    rate = getattr(self._route, "samplerate", None) or args.samplerate
                    # [POC-BTC] Der Analysepuffer muss das 10-s-Modellfenster
                    # halten (Default waeren 3s).
                    with self.protokoll.etappe("Opening the audio devices"):
                        self._loop = DelayedLoopback(
                            self._route.capture_device,
                            self._route.playback_device,
                            args.delay,
                            samplerate=rate,
                            analysis_seconds=11.0,
                            capture=getattr(self._route, "capture_source", None))
                        self._loop.start()
                        self._route.after_start()
                else:
                    eingang = args.input if args.input is not None \
                        else _standardgeraet()
                    with self.protokoll.etappe("Opening the audio devices"):
                        self._loop = DelayedLoopback(
                            eingang, args.output, args.delay,
                            samplerate=args.samplerate,
                            analysis_seconds=11.0)  # [POC-BTC] s.o.
                        self._loop.start()
            except BaseException as exc:
                # Halb aufgebaut ist schlimmer als gar nicht: sonst bleibt der
                # Null-Sink als Standardausgang stehen und der Rechner ist stumm.
                #
                # BaseException, NICHT Exception - und das ist keine Pedanterie.
                # KeyboardInterrupt und SystemExit sind keine Exception, und
                # ausgerechnet sie treffen den Aufbau am wahrscheinlichsten: Er
                # dauert Sekunden (PortAudio oeffnen, Geraet einschwingen), und
                # genau dann drueckt der ungeduldige Nutzer Strg+C. Vorher rutschte
                # der Abbruch hier durch, der Null-Sink blieb Standardausgang, und
                # der Rechner war stumm. Nachgemessen, mit SIGHUP mitten im
                # DelayedLoopback.__init__.
                self._abbauen()
                if isinstance(exc, Exception):
                    self.status = "error"
                    self.fehler = str(exc)
                else:
                    self.status = "stopped"      # Strg+C ist kein Fehler
                self._on_change()
                raise

            self._stop.clear()
            self._thread = threading.Thread(target=self._analyse, daemon=True)
            self._thread.start()
            self.status = "running"
        self._on_change()

    def stop(self):
        """Alles zurueckbauen. Danach laeuft der Systemton wieder normal.

        Das ist der Notausschalter aus dem Fenster: Wer nicht mehr weiss, warum
        sein Ton komisch klingt, drueckt hier - und hat sofort sein gewohntes
        Audio zurueck.
        """
        with self._lock:
            # Auch dann abbauen, wenn NUR die Umleitung steht. Ein Abbruch
            # mitten im Aufbau (Strg+C, kill) laesst genau diesen Zustand
            # zurueck: Null-Sink da, Stream noch nicht. Wer hier auf `_loop`
            # prueft, geht darueber hinweg - und der Rechner bleibt stumm.
            if self._loop is None and self._route is None:
                return
            self._stop.set()
            thread, self._thread = self._thread, None
        if thread:
            thread.join(timeout=3.0)
        with self._lock:
            self._abbauen()
            # Nach einem Fehler bleibt "error" stehen, auch wenn der Abbau glatt
            # durchlief: Der Grund muss lesbar bleiben. Sonst meldete der
            # Wachhund einen toten Stream - und die Oberflaeche zeigte
            # anschliessend ein harmloses "Stopped", das niemandem sagt, warum.
            self.status = "error" if self.fehler else "stopped"
            self.lead = 0.0
            self.jetzt = ""
        if self.broadcaster:
            self.broadcaster.republish(muted=False, control_guitar=False,
                                       running=False)
        self._on_change()

    def _abbauen(self):
        """Stream zuerst, dann die Umleitung - in dieser Reihenfolge.

        Andersherum laege zwischen "Umleitung weg" und "Stream weg" ein Fenster,
        in dem der Stream die zurueckgesetzte Standardquelle liest. Das ist in der
        Regel das Mikrofon - und das dann verzoegert auf die Lautsprecher zu
        geben, ist die klassische Rueckkopplung.
        """
        if self._loop is not None:
            try:
                self._loop.stop()
            except Exception:
                pass
            self._loop = None
        # Erst NACH dem Stream loslassen: Solange der Callback laeuft, greift er
        # auf den Mitschnitt zu. Ein halbes Gigabyte im Stopp-Zustand liegen zu
        # lassen waere ausserdem genau das, was man einem Programm vorwirft,
        # das "im Hintergrund nichts tut".
        self._record = None
        self.record_hinweis = None
        self.onsets = ()
        if self._route is not None:
            try:
                self._route.__exit__(None, None, None)
            except Exception:
                pass
            self._route = None

    def _analyse(self):
        from .cli import _display_loop

        try:
            _display_loop(self._loop, self.args, self.broadcaster,
                          stop=self._stop, engine=self)
        except Exception as exc:      # der Thread darf nicht still sterben
            self.status = "error"
            self.fehler = str(exc)
            self._on_change()
            # Ein toter Stream mit STEHENDER Umleitung ist der schlimmste
            # Zustand ueberhaupt: Der Systemton laeuft weiter in den Null-Sink,
            # zu hoeren ist nichts mehr, und die Anzeige, die das erklaeren
            # koennte, steht still. Also abbauen - aus einem eigenen Thread,
            # denn stop() wartet auf GENAU DIESEN hier und wuerde sich sonst
            # selbst joinen.
            threading.Thread(target=self.stop, daemon=True).start()

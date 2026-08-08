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

import threading


class Engine:
    """Umleitung, Audiostream und Analyse - startbar und stoppbar zur Laufzeit.

    Zustaende:
        running=False           aus. Der Systemton laeuft normal, JamPilot fasst
                                nichts an. (Auch der Zustand nach `stop()`.)
        running=True            laeuft. Ton wird umgeleitet, verzoegert, analysiert.
        running=True, muted     laeuft, aber der Lautsprecher schweigt. Puffer und
                                Analyse laufen weiter (siehe delay_stream).
    """

    def __init__(self, args, broadcaster=None, on_change=None):
        self.args = args
        self.broadcaster = broadcaster
        # Wird bei jedem Zustandswechsel gerufen, damit die Oberflaeche sich
        # nachzieht - ohne dass diese Schicht die Oberflaeche kennen muss.
        self._on_change = on_change or (lambda: None)

        self._loop = None
        self._route = None
        self._thread = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.lead = 0.0
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
                    self._route = routing.LinuxRouting()
                    self._route.__enter__()
                    # [POC-BTC] Der Analysepuffer muss das 10-s-Modellfenster
                    # halten (Default waeren 3s).
                    self._loop = DelayedLoopback("default", "default", args.delay,
                                                 samplerate=args.samplerate,
                                                 analysis_seconds=11.0)
                    self._loop.start()
                    self._route.move_own_playback_to(args.output)
                else:
                    self._loop = DelayedLoopback(args.input or "default", args.output,
                                                 args.delay, samplerate=args.samplerate,
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

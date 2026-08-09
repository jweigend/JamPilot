"""Windows-Routing: Der Rechner darf nie stumm zurueckbleiben.

Dieselbe Frage wie in test_routing.py, andere Plattform - und deshalb dieselbe
Bauart: ein nachgebildetes Audiosystem samt Zustand, damit sich pruefen laesst,
was ein abgebrochener Lauf TATSAECHLICH hinterlaesst.

Core Audio wird komplett ersetzt, nicht bloss ueberlistet. Das muss so sein:
jampilot.winaudio laesst sich ausserhalb von Windows nicht einmal importieren
(ctypes.wintypes gibt es dort nicht), die Testlaeufer der CI sind aber Linux
und macOS. Weil routing.py das Modul ausschliesslich INNERHALB von Funktionen
importiert, genuegt ein Eintrag in sys.modules - und die Attrappe laeuft dann
auf jeder Plattform durch dieselben Pfade wie das Original unter Windows.
"""

import sys
import types

import pytest

from jampilot import routing

KABEL_EIN = "CABLE Input (VB-Audio Virtual Cable)"
KABEL_AUS = "CABLE Output (VB-Audio Virtual Cable)"
BOXEN = "Lautsprecher (Realtek High Definition Audio)"
HOERER = "Kopfhoerer (Oculus Virtual Audio Device)"


class FakeEndpunkt:
    def __init__(self, kennung, name):
        self.kennung = kennung
        self.name = name

    def __repr__(self):
        return f"FakeEndpunkt({self.name!r})"


class FakeCoreAudio(types.ModuleType):
    """Core Audio inklusive Systemzustand - als Modul, damit `from . import
    winaudio` es findet."""

    RENDER, CAPTURE = 0, 1
    CONSOLE, MULTIMEDIA, COMMUNICATIONS = 0, 1, 2
    UMZUSTELLENDE_ROLLEN = (0, 1)

    def __init__(self, fail_on_set=False):
        super().__init__("jampilot.winaudio")
        self.wiedergabe = [
            FakeEndpunkt("id-16ch", "CABLE In 16ch (VB-Audio Virtual Cable)"),
            FakeEndpunkt("id-kabel", KABEL_EIN),
            FakeEndpunkt("id-boxen", BOXEN),
            FakeEndpunkt("id-hoerer", HOERER),
        ]
        self.aufnahme = [
            FakeEndpunkt("id-kabel-aus", KABEL_AUS),
            FakeEndpunkt("id-mikro", "Headset Microphone"),
        ]
        # Die drei Rollen einzeln - nur so faellt auf, wenn jemand die
        # Telefonie mitumstellt, die er nicht anfassen soll.
        self.standardgeraet = {0: "id-boxen", 1: "id-boxen", 2: "id-hoerer"}
        self.fail_on_set = fail_on_set

    # --- die Schnittstelle, die routing.py benutzt --------------------------
    def endpunkte(self, flow=0):
        return list(self.wiedergabe if flow == self.RENDER else self.aufnahme)

    def standard(self, flow=0, rolle=0):
        if flow != self.RENDER:
            return None
        kennung = self.standardgeraet[rolle]
        return next((e for e in self.wiedergabe if e.kennung == kennung), None)

    def setze_standard(self, kennung, rollen=(0, 1)):
        if self.fail_on_set:
            raise RuntimeError("simulierter Core-Audio-Fehler")
        for rolle in rollen:
            self.standardgeraet[rolle] = kennung

    # --- was der Test wissen will -------------------------------------------
    @property
    def ausgang(self):
        return self.standard(self.RENDER, self.CONSOLE).name

    @property
    def telefonie(self):
        return self.standard(self.RENDER, self.COMMUNICATIONS).name

    @property
    def sauber(self):
        return self.ausgang == BOXEN and self.telefonie == HOERER


# PortAudio-Indizes, ohne PortAudio: Das Kabel ist 23, die Boxen sind 19.
_INDIZES = {(KABEL_AUS, "input"): 23, (BOXEN, "output"): 19,
            (HOERER, "output"): 22}


@pytest.fixture
def winaudio(monkeypatch, tmp_path):
    fake = FakeCoreAudio()
    # BEIDES, und das ist kein Guertel-und-Hosentraeger: `from . import
    # winaudio` nimmt das ATTRIBUT des Pakets, wenn es eines gibt, und sieht
    # sys.modules gar nicht erst an. Unter Windows hat irgendein frueherer Test
    # das echte Modul laengst importiert - dann liefe die Attrappe hier ins
    # Leere und die Tests haetten am echten Rechner herumgestellt.
    import jampilot

    monkeypatch.setitem(sys.modules, "jampilot.winaudio", fake)
    monkeypatch.setattr(jampilot, "winaudio", fake, raising=False)
    monkeypatch.setattr(routing, "backend", lambda: routing.WINCABLE)
    monkeypatch.setattr(routing, "LOCK_FILE", tmp_path / "jampilot.pid")
    monkeypatch.setattr(routing, "STATE_FILE", tmp_path / "jampilot.json")
    monkeypatch.setattr(routing, "_portaudio_index",
                        lambda name, kind: _INDIZES.get((name, kind)))
    monkeypatch.setattr(routing, "_kabel_cache", routing._UNSET, raising=False)
    return fake


def _args(**felder):
    import argparse

    return argparse.Namespace(**{"input": None, "output": None,
                                 "no_route": False, **felder})


class TestErkennung:
    def test_kabel_wird_gefunden(self, winaudio):
        ein, aus = routing._kabel(neu_pruefen=True)
        assert (ein.name, aus.name) == (KABEL_EIN, KABEL_AUS)

    def test_ohne_kabel_kein_routing(self, winaudio, monkeypatch):
        winaudio.wiedergabe = [e for e in winaudio.wiedergabe
                               if e.name != KABEL_EIN]
        monkeypatch.setattr(routing, "backend",
                            lambda: routing.WINCABLE
                            if routing._kabel_vorhanden() else None)
        assert routing._kabel(neu_pruefen=True) is None
        assert not routing.uses_routing(_args())

    def test_die_16_kanal_variante_ist_nicht_das_kabel(self, winaudio):
        """"CABLE In 16ch" liegt im selben Treiberpaket und faengt genauso an.

        Wer es fuer die Wiedergabeseite haelt, leitet den Systemton in ein Rohr
        um, dessen anderes Ende niemand abhoert - der Rechner waere stumm und
        JamPilot saehe nichts."""
        ein, _ = routing._kabel(neu_pruefen=True)
        assert ein.name == KABEL_EIN


class TestNormalfall:
    def test_durchlauf_hinterlaesst_nichts(self, winaudio):
        with routing.create(_args()) as route:
            assert winaudio.ausgang == KABEL_EIN      # waehrenddessen umgeleitet
            assert route.capture_device == 23
            assert route.playback_device == 19
        assert winaudio.sauber
        assert not routing.STATE_FILE.exists()
        assert not routing.LOCK_FILE.exists()

    def test_telefonie_bleibt_unangetastet(self, winaudio):
        """Ein Videogespraech durch einen Vier-Sekunden-Puffer ist unbenutzbar,
        und niemand sucht die Ursache bei einem Akkordanzeiger."""
        with routing.create(_args()):
            assert winaudio.telefonie == HOERER
        assert winaudio.telefonie == HOERER

    def test_wer_schon_von_hand_umgestellt_hatte_wird_geheilt(self, winaudio):
        """Die Falle, um die es hier ueberhaupt geht - und sie loest sich selbst.

        Wer JamPilot bisher von Hand benutzt hat, hat seinen Systemton selbst
        auf das Kabel gestellt. Dann waere der "vorherige" Ausgang das Kabel,
        und darauf auszugeben hiesse, in genau das Rohr zu spielen, das wir
        abhoeren - eine Rueckkopplung, die man als Stille erlebt.

        Dass das nicht passiert, kostet keine Sonderbehandlung: __enter__
        raeumt zuerst auf, und ein Standard-Ausgang am Kabel OHNE lebenden
        Besitzer ist per Definition eine Waise. Er wird also weggeraeumt, bevor
        `previous` gelesen wird - genau wie unter Linux. Der Nutzer bekommt
        seine Boxen zurueck, ohne je davon erfahren zu haben."""
        winaudio.standardgeraet[0] = "id-kabel"
        winaudio.standardgeraet[1] = "id-kabel"
        with routing.create(_args()) as route:
            assert route.playback_device == 19        # die Boxen, nicht 23
        assert winaudio.sauber

    def test_output_schlaegt_die_automatik(self, winaudio):
        with routing.create(_args(output=7)) as route:
            assert route.playback_device == 7
        assert winaudio.sauber


class TestRollback:
    def test_fehler_beim_umstellen_raeumt_vollstaendig_auf(self, winaudio):
        # `with` ruft __exit__ NICHT auf, wenn __enter__ fliegt - ohne eigene
        # Ruecknahme bliebe das Kabel der Standard-Ausgang.
        winaudio.fail_on_set = True
        with pytest.raises(RuntimeError):
            with routing.create(_args()):
                pytest.fail("darf nicht erreicht werden")
        assert winaudio.sauber
        assert not routing.STATE_FILE.exists()
        assert not routing.LOCK_FILE.exists()

    def test_fehlendes_geraet_faellt_auf_bevor_etwas_umgestellt_wird(
            self, winaudio, monkeypatch):
        """Ein Aufbau, der auf halbem Weg scheitert, soll an einem Rechner
        scheitern, der noch Ton hat."""
        monkeypatch.setattr(routing, "_portaudio_index", lambda name, kind: None)
        with pytest.raises(RuntimeError, match="PortAudio"):
            routing.create(_args()).__enter__()
        assert winaudio.sauber

    def test_ohne_echten_ausgang_wird_gar_nicht_erst_umgeleitet(self, winaudio):
        """Nur noch Kabel im Rechner: Dann gibt es kein Ziel fuer die Ausgabe,
        und umzuleiten hiesse, den Ton in einem Rohr verschwinden zu lassen."""
        winaudio.wiedergabe = [e for e in winaudio.wiedergabe
                               if "VB-Audio" in e.name]
        winaudio.standardgeraet = {0: "id-kabel", 1: "id-kabel", 2: "id-kabel"}
        with pytest.raises(RuntimeError, match="No real playback device"):
            routing.create(_args()).__enter__()
        assert winaudio.ausgang == KABEL_EIN          # unveraendert gelassen

    def test_mit_output_braucht_es_keinen_brauchbaren_standard(self, winaudio):
        """Wer sein Ziel selbst nennt, darf nicht daran scheitern, dass die
        Automatik keines gefunden HAETTE."""
        winaudio.wiedergabe = [e for e in winaudio.wiedergabe
                               if "VB-Audio" in e.name]
        winaudio.standardgeraet = {0: "id-kabel", 1: "id-kabel", 2: "id-kabel"}
        with routing.create(_args(output=7)) as route:
            assert route.playback_device == 7
            assert winaudio.ausgang == KABEL_EIN

    def test_fremde_umstellung_waehrend_des_laufs_wird_respektiert(self, winaudio):
        """Steckt der Nutzer mittendrin Kopfhoerer ein, schaltet Windows um.
        Seine Wahl ist die juengere - die ueberschreibt man beim Beenden nicht."""
        route = routing.create(_args())
        route.__enter__()
        winaudio.standardgeraet[0] = "id-hoerer"
        winaudio.standardgeraet[1] = "id-hoerer"
        route.__exit__()
        assert winaudio.ausgang == HOERER


class TestWaisen:
    def test_abgestuerzter_lauf_wird_beim_start_aufgeraeumt(self, winaudio):
        winaudio.standardgeraet[0] = "id-kabel"       # Rechner ist stumm
        winaudio.standardgeraet[1] = "id-kabel"
        routing.STATE_FILE.write_text('{"previous": "id-boxen"}')
        # Kein lebender Besitzer -> die Waise darf weg.
        with routing.create(_args()) as route:
            # Entscheidend: NICHT das Kabel als "vorherigen" Zustand merken,
            # sonst stellen wir beim Beenden die Stille wieder her.
            assert route.previous.name == BOXEN
        assert winaudio.sauber

    def test_cleanup_holt_den_ausgang_zurueck(self, winaudio):
        winaudio.standardgeraet[0] = "id-kabel"
        routing.STATE_FILE.write_text('{"previous": "id-hoerer"}')
        assert routing.cleanup() == 1
        assert winaudio.ausgang == HOERER

    def test_cleanup_ohne_vermerk_nimmt_irgendeinen_echten_ausgang(self, winaudio):
        """Nach einem Neustart ist die Vermerkdatei womoeglich weg. Irgendein
        echter Ausgang ist immer noch besser als ein stummer Rechner."""
        winaudio.standardgeraet[0] = "id-kabel"
        assert routing.cleanup() == 1
        assert winaudio.ausgang != KABEL_EIN

    def test_cleanup_ruehrt_nichts_an_was_nicht_am_kabel_haengt(self, winaudio):
        """Steht der Standard nicht auf dem Kabel, hat der Nutzer entweder nie
        umgeleitet oder es laengst selbst korrigiert. Ihm jetzt ein Geraet von
        vorgestern unterzuschieben waere uebergriffig."""
        routing.STATE_FILE.write_text('{"previous": "id-hoerer"}')
        assert routing.cleanup() == 0
        assert winaudio.ausgang == BOXEN

    def test_cleanup_ohne_alles(self, winaudio):
        assert routing.cleanup() == 0


class TestZweiteInstanz:
    def test_laufende_instanz_wird_nicht_abgeraeumt(self, winaudio, monkeypatch):
        routing.LOCK_FILE.write_text("4242")
        monkeypatch.setattr(routing, "_alive", lambda pid: True)
        winaudio.standardgeraet[0] = "id-kabel"

        with pytest.raises(routing.InstanceRunning):
            routing.cleanup()
        assert winaudio.ausgang == KABEL_EIN          # nicht weggezogen

    def test_die_sperrdatei_der_anderen_bleibt_liegen(self, winaudio, monkeypatch):
        """Der Aufbau scheitert hier in cleanup(). Wer dann bedingungslos
        aufraeumt, nimmt der LAUFENDEN Instanz ihren Besitzvermerk weg - und die
        beiden zerlegen sich gegenseitig das Routing."""
        routing.LOCK_FILE.write_text("4242")
        monkeypatch.setattr(routing, "_alive", lambda pid: True)

        with pytest.raises(routing.InstanceRunning):
            routing.create(_args()).__enter__()
        assert routing.LOCK_FILE.read_text() == "4242"

    def test_force_raeumt_trotzdem(self, winaudio, monkeypatch):
        routing.LOCK_FILE.write_text("4242")
        monkeypatch.setattr(routing, "_alive", lambda pid: True)
        winaudio.standardgeraet[0] = "id-kabel"
        assert routing.cleanup(force=True) == 1
        assert winaudio.ausgang == BOXEN


class TestWasDerNutzerLiest:
    """Der erste Start entscheidet sich an einer Zeile Text."""

    def test_mit_kabel_steht_der_ganze_weg_da(self, winaudio, capsys):
        from jampilot import cli

        cli._bericht_zur_quelle(_args())
        ausgabe = capsys.readouterr().out
        assert KABEL_EIN in ausgabe and BOXEN in ausgabe
        assert "restored on exit" in ausgabe

    def test_ohne_kabel_wird_der_treiber_genannt_und_sonst_nichts(
            self, winaudio, monkeypatch, capsys):
        """Ohne Kabel bricht die Geraetepruefung gleich darauf am Mikrofon ab
        ("hat 1 Kanal"). Das ist wahr, aber nicht die Ursache - wer nur das
        liest, sucht den Fehler bei seinem Mikrofon. Also zuerst der Treiber,
        und den generischen Hinweis dann NICHT auch noch."""
        from jampilot import cli

        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(routing, "backend", lambda: None)
        cli._bericht_zur_quelle(_args())
        ausgabe = capsys.readouterr().out
        assert "VB-CABLE is not installed" in ausgabe
        assert "No --input given" not in ausgabe

    def test_mit_no_route_kein_treiberwerbung(self, winaudio, monkeypatch, capsys):
        """Wer `--no-route` tippt, will die Umleitung nicht - dem muss man
        keinen Treiber andrehen."""
        from jampilot import cli
        import sounddevice as sd

        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(routing, "backend", lambda: None)
        monkeypatch.setattr(sd, "query_devices",
                            lambda device=None, kind=None: {"name": "Mikro"})
        cli._bericht_zur_quelle(_args(no_route=True))
        ausgabe = capsys.readouterr().out
        assert "VB-CABLE is not installed" not in ausgabe
        assert "No --input given" in ausgabe


class TestPortAudioAufloesung:
    """Zwei Namensraeume, ein Geraet - und vier Host-APIs, die alle denselben
    Namen tragen."""

    @pytest.fixture
    def sd(self, monkeypatch):
        import sounddevice

        apis = [{"name": "MME"}, {"name": "Windows DirectSound"},
                {"name": "Windows WASAPI"}, {"name": "Windows WDM-KS"}]
        geraete = [
            # MME kuerzt auf 31 Zeichen und meldet fuer das Kabel 16 Kanaele.
            {"name": "CABLE Output (VB-Audio Virtual ", "hostapi": 0,
             "max_input_channels": 16, "max_output_channels": 0},
            {"name": KABEL_AUS, "hostapi": 1,
             "max_input_channels": 16, "max_output_channels": 0},
            {"name": KABEL_AUS, "hostapi": 2,
             "max_input_channels": 2, "max_output_channels": 0},
            {"name": BOXEN, "hostapi": 2,
             "max_input_channels": 0, "max_output_channels": 2},
            {"name": "Headset Microphone", "hostapi": 2,
             "max_input_channels": 1, "max_output_channels": 0},
        ]
        monkeypatch.setattr(sounddevice, "query_hostapis", lambda: apis)
        monkeypatch.setattr(sounddevice, "query_devices", lambda: geraete)
        return geraete

    def test_wasapi_gewinnt(self, sd):
        """Nicht Geschmack: WASAPI ist der Weg, den Windows selbst geht, und
        der einzige, der die Kanalzahl ehrlich meldet."""
        assert routing._portaudio_index(KABEL_AUS, "input") == 2

    def test_exakter_name_statt_teilstring(self, sd):
        """sounddevice sucht per Teilstring und findet "CABLE Output" in vier
        Host-APIs - es lehnt dann mit "Multiple input devices found" ab. Genau
        deshalb wird hier exakt verglichen."""
        assert routing._portaudio_index("CABLE Output", "input") is None

    def test_mono_zaehlt_nicht(self, sd):
        assert routing._portaudio_index("Headset Microphone", "input") is None

    def test_unbekanntes_geraet(self, sd):
        assert routing._portaudio_index("gibtsnicht", "output") is None


@pytest.mark.skipif(sys.platform != "win32", reason="braucht echte Windows-PIDs")
class TestLebendpruefung:
    """os.kill(pid, 0) waere unter Windows kein Frage, sondern ein Todesurteil -
    es ruft in Wahrheit TerminateProcess auf."""

    def test_der_eigene_prozess_lebt(self):
        import os

        assert routing._alive(os.getpid())

    def test_eine_tote_pid_lebt_nicht(self):
        import subprocess

        kind = subprocess.Popen([sys.executable, "-c", "pass"])
        kind.wait()
        assert not routing._alive(kind.pid)

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
# Ein HDMI-Ausgang, benannt wie im echten Leben: Das Wort "HDMI" kommt darin
# NICHT vor. Wer den Umweg am Namen erkennen will, faellt hier herein.
MONITOR = "LEN LT2452pwC (NVIDIA High Definition Audio)"


class FakeEndpunkt:
    def __init__(self, kennung, name, formfaktor=10):
        self.kennung = kennung
        self.name = name
        self.formfaktor = formfaktor

    def __repr__(self):
        return f"FakeEndpunkt({self.name!r})"


class FakeCoreAudio(types.ModuleType):
    """Core Audio inklusive Systemzustand - als Modul, damit `from . import
    winaudio` es findet."""

    RENDER, CAPTURE = 0, 1
    CONSOLE, MULTIMEDIA, COMMUNICATIONS = 0, 1, 2
    UMZUSTELLENDE_ROLLEN = (0, 1)
    FF_UNBEKANNT, FF_LAUTSPRECHER, FF_KOPFHOERER = 10, 1, 3
    FF_HEADSET, FF_DIGITAL_DURCHREICHUNG, FF_SPDIF, FF_HDMI = 5, 7, 8, 9

    def __init__(self, fail_on_set=False):
        super().__init__("jampilot.winaudio")
        self.wiedergabe = [
            FakeEndpunkt("id-16ch", "CABLE In 16ch (VB-Audio Virtual Cable)"),
            FakeEndpunkt("id-kabel", KABEL_EIN),
            FakeEndpunkt("id-boxen", BOXEN, self.FF_LAUTSPRECHER),
            # Der Kopfhoerer steht VOR dem Monitor: Ohne Sortierung nach dem
            # Formfaktor wuerde er als Umweg gewaehlt.
            FakeEndpunkt("id-hoerer", HOERER, self.FF_KOPFHOERER),
            FakeEndpunkt("id-monitor", MONITOR, self.FF_HDMI),
        ]
        self.aufnahme = [
            FakeEndpunkt("id-kabel-aus", KABEL_AUS),
            FakeEndpunkt("id-mikro", "Headset Microphone"),
        ]
        # Die drei Rollen einzeln - nur so faellt auf, wenn jemand die
        # Telefonie mitumstellt, die er nicht anfassen soll.
        self.standardgeraet = {0: "id-boxen", 1: "id-boxen", 2: "id-hoerer"}
        self.fail_on_set = fail_on_set
        # Der Mute-Weg: welche Endpunkte gerade stummgeschaltet sind.
        self.stummgeschaltet = set()

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

    def stumm(self, kennung):
        if kennung not in {e.kennung for e in self.wiedergabe}:
            raise RuntimeError("Endpunkt gibt es nicht (mehr)")
        return kennung in self.stummgeschaltet

    def setze_stumm(self, kennung, an):
        if self.fail_on_set:
            raise RuntimeError("simulierter Core-Audio-Fehler")
        if an:
            self.stummgeschaltet.add(kennung)
        else:
            self.stummgeschaltet.discard(kennung)

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


class FakeWinCapture(types.ModuleType):
    """wincapture, so weit routing.py es benutzt: pruefen() und Loopback.

    Was hier NICHT nachgebildet wird, ist WASAPI - das ist Sache der Messung
    auf einem echten Rechner. Nachgebildet wird die Antwort, an der routing.py
    haengt: traegt der Mute-Weg auf diesem Geraet, ja oder nein."""

    def __init__(self, traegt=True):
        super().__init__("jampilot.wincapture")
        self.traegt = traegt
        self.geprueft = []
        self.offen = []          # Loopbacks, die noch nicht geschlossen sind

    def pruefen(self, kennung):
        self.geprueft.append(kennung)
        return self.traegt

    def Loopback(self, kennung, name=""):        # noqa: N802 - Klassenname
        return _FakeLoopback(self, kennung)


class _FakeLoopback:
    def __init__(self, modul, kennung):
        self.samplerate = 44100          # bewusst NICHT 48000: siehe engine
        self.kennung = kennung
        self._modul = modul
        modul.offen.append(self)

    def close(self):
        self._modul.offen.remove(self)


@pytest.fixture
def stummweg(winaudio, monkeypatch):
    """Derselbe Rechner wie oben, nur ohne Kabel und mit tragendem Mute-Weg."""
    import jampilot

    winaudio.wiedergabe = [e for e in winaudio.wiedergabe
                           if "VB-Audio" not in e.name]
    fake = FakeWinCapture()
    monkeypatch.setitem(sys.modules, "jampilot.wincapture", fake)
    monkeypatch.setattr(jampilot, "wincapture", fake, raising=False)
    monkeypatch.setattr(routing, "_stummweg_cache", routing._UNSET,
                        raising=False)
    monkeypatch.setattr(routing, "_wunsch", "auto", raising=False)
    monkeypatch.setattr(routing, "backend", lambda: routing.WINMUTE)
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


class TestStummerWeg:
    """Der Weg ohne Fremdtreiber - dieselben Rollen wie beim Kabel.

    DIE ROLLEN sind das, was hier gepruefen wird, und zwar zuerst: Der stumme
    Endpunkt ist der UMWEG, in den die Player spielen. Das Geraet, auf dem der
    Nutzer HOERT, bleibt hoerbar und bekommt das verzoegerte Signal. Wer das
    vertauscht, dreht dem Nutzer den Ton ab und spielt die Musik an ein Geraet,
    an dem niemand sitzt - und das Programm sieht dabei aus, als liefe es."""

    def test_der_umweg_wird_stumm_und_das_hoergeraet_nicht(self, stummweg,
                                                           winaudio):
        with routing.WindowsMuteRouting(_args()) as route:
            assert route.umweg.name == MONITOR
            assert route.ausgabe.name == BOXEN
            assert winaudio.stummgeschaltet == {"id-monitor"}
            assert "id-boxen" not in winaudio.stummgeschaltet

    def test_die_ausgabe_geht_auf_das_geraet_von_vorher(self, stummweg):
        """Der Nutzer hoert weiter da, wo er vorher gehoert hat - genau wie
        LinuxRouting mit `previous_sink` und der Kabelweg mit
        windows_playback_target()."""
        with routing.WindowsMuteRouting(_args()) as route:
            assert route.playback_device == _INDIZES[(BOXEN, "output")]

    def test_der_systemton_laeuft_auf_den_umweg(self, stummweg, winaudio):
        with routing.WindowsMuteRouting(_args()):
            assert winaudio.ausgang == MONITOR

    def test_die_telefonie_bleibt_unangetastet(self, stummweg, winaudio):
        with routing.WindowsMuteRouting(_args()):
            assert winaudio.telefonie == HOERER
            assert "id-hoerer" not in winaudio.stummgeschaltet

    def test_das_telefoniegeraet_wird_nie_zum_umweg(self, stummweg, winaudio):
        """Ein stummes Headset mitten in einer Videokonferenz waere ein Fehler,
        den niemand bei einem Akkordanzeiger suchte."""
        winaudio.wiedergabe = [e for e in winaudio.wiedergabe
                               if e.kennung in ("id-boxen", "id-hoerer")]
        assert routing._stummweg(neu_pruefen=True) is None

    def test_stille_endpunkte_werden_bevorzugt(self, stummweg, winaudio):
        """HDMI und S/PDIF zuerst: Der Mute macht zwar jeden Endpunkt still,
        aber einen Kopfhoerer zum Umweg zu machen hiesse, dass jemand, der ihn
        aufsetzt, Stille hoert."""
        winaudio.standardgeraet[2] = "id-boxen"      # kein eigenes Telefoniegeraet
        umweg, _ = routing._stummweg(neu_pruefen=True)
        assert umweg.name == MONITOR                 # nicht der Kopfhoerer

    def test_durchlauf_hinterlaesst_nichts(self, stummweg, winaudio):
        with routing.WindowsMuteRouting(_args()):
            pass
        assert winaudio.stummgeschaltet == set()
        assert winaudio.sauber
        assert stummweg.offen == []
        assert not routing.STATE_FILE.exists()
        assert not routing.LOCK_FILE.exists()

    def test_die_abtastrate_kommt_vom_umweg(self, stummweg):
        """Das Mixformat ist nicht verhandelbar - eine andere Rate ergaebe eine
        andere Tonhoehe."""
        with routing.WindowsMuteRouting(_args()) as route:
            assert route.samplerate == 44100

    def test_output_schlaegt_die_automatik(self, stummweg):
        with routing.WindowsMuteRouting(_args(output=7)) as route:
            assert route.playback_device == 7

    def test_ohne_zweiten_endpunkt_gibt_es_den_weg_nicht(self, stummweg,
                                                         winaudio):
        winaudio.wiedergabe = [e for e in winaudio.wiedergabe
                               if e.kennung == "id-boxen"]
        winaudio.standardgeraet[2] = "id-boxen"
        assert routing._stummweg(neu_pruefen=True) is None

    def test_traegt_der_treiber_nicht_gibt_es_den_weg_nicht(self, stummweg):
        """Sitzt der Mute VOR dem Loopback-Abgriff, schneidet man Stille mit.
        Das kann man nicht nachschlagen, nur messen - und wenn die Messung Nein
        sagt, gilt Nein. Gemessen wird JEDER Kandidat, nicht nur der erste -
        dass der Bildschirmausgang nicht mag, heisst nichts ueber den
        Kopfhoerer."""
        stummweg.traegt = False
        winaudio_modul = sys.modules["jampilot.winaudio"]
        winaudio_modul.standardgeraet[2] = "id-boxen"   # Telefonie freigeben
        assert routing._stummweg(neu_pruefen=True) is None
        assert stummweg.geprueft == ["id-monitor", "id-hoerer"]

    def test_fehlendes_ausgabegeraet_faellt_auf_bevor_etwas_passiert(
            self, stummweg, winaudio, monkeypatch):
        """ALLES wird aufgeloest, bevor etwas umgestellt wird - ein Fehlschlag
        soll an einem Rechner scheitern, der noch Ton hat."""
        monkeypatch.setattr(routing, "_portaudio_index", lambda name, kind: None)
        with pytest.raises(RuntimeError):
            with routing.WindowsMuteRouting(_args()):
                pass
        assert winaudio.stummgeschaltet == set()
        assert winaudio.sauber

    def test_abgestuerzter_lauf_wird_beim_start_aufgeraeumt(self, stummweg,
                                                            winaudio):
        """Sonst merkte sich der neue Lauf den stummen Umweg als "vorheriges"
        Hoergeraet - und gaebe die Musik auf ein Geraet aus, das stumm ist."""
        winaudio.stummgeschaltet.add("id-monitor")
        winaudio.standardgeraet[0] = winaudio.standardgeraet[1] = "id-monitor"
        routing.STATE_FILE.write_text(
            '{"previous": "id-boxen", "umweg": "id-monitor", '
            '"muted": "id-monitor", "war_stumm": false}')
        with routing.WindowsMuteRouting(_args()) as route:
            assert route.ausgabe.name == BOXEN
        assert winaudio.sauber
        assert winaudio.stummgeschaltet == set()

    def test_cleanup_holt_ausgang_und_stummschaltung_zurueck(self, stummweg,
                                                             winaudio):
        winaudio.stummgeschaltet.add("id-monitor")
        winaudio.standardgeraet[0] = winaudio.standardgeraet[1] = "id-monitor"
        routing.STATE_FILE.write_text(
            '{"previous": "id-boxen", "umweg": "id-monitor", '
            '"muted": "id-monitor", "war_stumm": false}')
        assert routing.cleanup() == 1
        assert winaudio.ausgang == BOXEN
        assert winaudio.stummgeschaltet == set()

    def test_cleanup_ruehrt_eine_eigene_stummschaltung_nicht_an(self, stummweg,
                                                                winaudio):
        """Wer den Endpunkt selbst stumm geschaltet hatte, bekommt ihn nicht
        von JamPilot wieder aufgedreht - der Ausgang kommt trotzdem zurueck."""
        winaudio.stummgeschaltet.add("id-monitor")
        winaudio.standardgeraet[0] = winaudio.standardgeraet[1] = "id-monitor"
        routing.STATE_FILE.write_text(
            '{"previous": "id-boxen", "umweg": "id-monitor", '
            '"muted": "id-monitor", "war_stumm": true}')
        assert routing.cleanup() == 1
        assert winaudio.ausgang == BOXEN
        assert winaudio.stummgeschaltet == {"id-monitor"}

    def test_cleanup_ruehrt_nichts_an_was_der_nutzer_schon_geheilt_hat(
            self, stummweg, winaudio):
        routing.STATE_FILE.write_text(
            '{"previous": "id-boxen", "umweg": "id-monitor", '
            '"muted": "id-monitor", "war_stumm": false}')
        assert routing.cleanup() == 0
        assert winaudio.sauber

    def test_cleanup_ohne_gemerktes_hoergeraet_nimmt_irgendeinen_ausgang(
            self, stummweg, winaudio):
        """Kopfhoerer abgezogen, Profil gewechselt - der Vermerk zeigt ins
        Leere. Irgendein Ausgang ist immer noch besser als der stumme Umweg."""
        winaudio.stummgeschaltet.add("id-monitor")
        winaudio.standardgeraet[0] = winaudio.standardgeraet[1] = "id-monitor"
        routing.STATE_FILE.write_text(
            '{"previous": "id-weg", "umweg": "id-monitor", '
            '"muted": "id-monitor", "war_stumm": false}')
        assert routing.cleanup() == 1
        assert winaudio.ausgang != MONITOR

    def test_fehler_beim_umstellen_raeumt_vollstaendig_auf(self, stummweg,
                                                           winaudio):
        winaudio.fail_on_set = True
        with pytest.raises(RuntimeError):
            with routing.WindowsMuteRouting(_args()):
                pass
        assert winaudio.stummgeschaltet == set()
        assert winaudio.sauber
        assert not routing.LOCK_FILE.exists()

    def test_das_kabel_gewinnt_wenn_es_da_ist(self, winaudio, monkeypatch):
        """Wer VB-CABLE installiert hat, hat sich dafuer entschieden - dem
        faehrt man nicht ueber Nacht in die Konfiguration. Und die Messung
        laeuft dann gar nicht erst: kein Endpunkt wird angefasst."""
        fake = _mit_wincapture(monkeypatch)
        assert routing.backend() == routing.WINCABLE
        assert fake.geprueft == []

    def test_route_mute_erzwingt_den_treiberlosen_weg(self, winaudio,
                                                      monkeypatch):
        """Sonst liesse sich der neue Weg auf einem Rechner mit Kabel gar nicht
        pruefen, ausser durch Deinstallieren."""
        _mit_wincapture(monkeypatch)
        monkeypatch.setattr(routing, "_wunsch", "mute", raising=False)
        assert routing.backend() == routing.WINMUTE

    def test_ohne_kabel_kommt_der_treiberlose_weg(self, winaudio, monkeypatch):
        winaudio.wiedergabe = [e for e in winaudio.wiedergabe
                               if "VB-Audio" not in e.name]
        _mit_wincapture(monkeypatch)
        assert routing.backend() == routing.WINMUTE

    def test_ohne_beides_bleibt_nichts(self, winaudio, monkeypatch):
        winaudio.wiedergabe = [e for e in winaudio.wiedergabe
                               if "VB-Audio" not in e.name]
        _mit_wincapture(monkeypatch, traegt=False)
        assert routing.backend() is None


def _mit_wincapture(monkeypatch, traegt=True):
    """Echtes backend() gegen die Attrappen laufen lassen."""
    import jampilot

    fake = FakeWinCapture(traegt=traegt)
    monkeypatch.setitem(sys.modules, "jampilot.wincapture", fake)
    monkeypatch.setattr(jampilot, "wincapture", fake, raising=False)
    monkeypatch.setattr(routing, "backend", _ECHTES_BACKEND)
    monkeypatch.setattr(routing, "_stummweg_cache", routing._UNSET,
                        raising=False)
    monkeypatch.setattr(routing, "_kabel_cache", routing._UNSET, raising=False)
    monkeypatch.setattr(routing, "_wunsch", "auto", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(routing.shutil, "which", lambda name: None)
    return fake


# backend() wird in den Fixtures ersetzt; die zwei Tests oben brauchen das
# Original und muessen es sich vorher gemerkt haben.
_ECHTES_BACKEND = routing.backend


class TestWasDerNutzerLiest:
    """Der erste Start entscheidet sich an einer Zeile Text."""

    def test_mit_kabel_steht_der_ganze_weg_da(self, winaudio, capsys):
        from jampilot import cli

        cli._bericht_zur_quelle(_args())
        ausgabe = capsys.readouterr().out
        assert KABEL_EIN in ausgabe and BOXEN in ausgabe
        assert "restored on exit" in ausgabe

    def test_ohne_weg_werden_beide_ausgaenge_genannt_und_sonst_nichts(
            self, winaudio, monkeypatch, capsys):
        """Ohne Umleitung bricht die Geraetepruefung gleich darauf am Mikrofon
        ab ("hat 1 Kanal"). Das ist wahr, aber nicht die Ursache - wer nur das
        liest, sucht den Fehler bei seinem Mikrofon. Also zuerst, was fehlt,
        und den generischen Hinweis dann NICHT auch noch.

        Was fehlt, sind seit dem Mute-Weg ZWEI Dinge, von denen eines genuegt:
        ein zweiter Ausgabe-Endpunkt als stummer Umweg, oder das Kabel. Nur den
        Treiber zu nennen schickte Nutzer zu einer Installation, die sie gar
        nicht brauchen."""
        from jampilot import cli

        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(routing, "backend", lambda: None)
        cli._bericht_zur_quelle(_args())
        ausgabe = capsys.readouterr().out
        assert "SECOND OUTPUT ENDPOINT" in ausgabe
        assert "VB-CABLE" in ausgabe
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

"""SSE-Verteilung: bei Rueckstau gewinnt der NEUE Zustand, nicht der alte.

Dazu der Vertrag der Seite: Akkorde gehen KANONISCH raus (immer mit Kreuz),
die Schreibweise entscheidet der Browser aus Tonart + Einstellung.
"""

import json
import queue
import urllib.error
import urllib.request

import pytest

from jampilot import web
from jampilot.web import PAGE, ChordBroadcaster


def _leeren(q):
    zustaende = []
    while True:
        try:
            zustaende.append(json.loads(q.get_nowait()))
        except queue.Empty:
            return zustaende


class TestChordBroadcaster:
    def test_stellt_zustand_zu(self):
        broadcaster = ChordBroadcaster()
        q, _ = broadcaster.subscribe()
        broadcaster.publish({"n": 1})
        assert _leeren(q) == [{"n": 1}]

    def test_langsamer_client_bekommt_den_NEUESTEN_zustand(self):
        # Frueher lief die Queue voll und neue Updates wurden verworfen: der
        # Client bekam die Zustaende 0..7 serviert und die aktuellen 8..11 nie.
        # Fuer eine Echtzeitanzeige ist das genau verkehrt herum - er wuerde
        # alte Akkorde abarbeiten und seine Uhr auf veraltete Zeiten stellen.
        broadcaster = ChordBroadcaster()
        q, _ = broadcaster.subscribe()
        for i in range(12):
            broadcaster.publish({"n": i})

        zustaende = _leeren(q)
        assert zustaende == [{"n": 11}], "nur der aktuellste Zustand darf warten"

    def test_jeder_zustand_ist_ein_vollstaendiger_snapshot(self):
        # Zwischenstaende zu verwerfen ist nur deshalb verlustfrei.
        broadcaster = ChordBroadcaster()
        q, _ = broadcaster.subscribe()
        broadcaster.publish({"t": 1.0, "chords": [{"c": "C", "at": 0.5}], "lead": 3})
        broadcaster.publish({"t": 2.0, "chords": [{"c": "C", "at": 0.5},
                                                  {"c": "G", "at": 4.0}], "lead": 3})
        (zustand,) = _leeren(q)
        assert zustand["t"] == 2.0
        assert len(zustand["chords"]) == 2      # Historie steckt im Snapshot

    def test_neuer_client_bekommt_sofort_den_letzten_zustand(self):
        broadcaster = ChordBroadcaster()
        broadcaster.publish({"n": 7})
        _, letzter = broadcaster.subscribe()
        assert json.loads(letzter) == {"n": 7}

    def test_mehrere_clients_bekommen_alle(self):
        broadcaster = ChordBroadcaster()
        a, _ = broadcaster.subscribe()
        b, _ = broadcaster.subscribe()
        broadcaster.publish({"n": 3})
        assert _leeren(a) == [{"n": 3}]
        assert _leeren(b) == [{"n": 3}]

    def test_abgemeldeter_client_bekommt_nichts_mehr(self):
        broadcaster = ChordBroadcaster()
        q, _ = broadcaster.subscribe()
        broadcaster.unsubscribe(q)
        broadcaster.publish({"n": 1})
        assert _leeren(q) == []

    def test_tonart_faehrt_im_snapshot_mit(self):
        # Der Browser braucht die Tonart im selben Snapshot wie die Akkorde:
        # sonst schriebe er einen Takt lang mit der Tonart von vorgestern.
        broadcaster = ChordBroadcaster()
        q, _ = broadcaster.subscribe()
        broadcaster.publish({
            "t": 12.0, "lead": 3.0, "chords": [{"c": "A#", "at": 10.0}],
            "key": {"tonic": "F", "minor": False, "acc": "flat", "label": "F-Dur"},
        })
        (zustand,) = _leeren(q)
        assert zustand["chords"][0]["c"] == "A#", "Akkorde gehen kanonisch raus"
        assert zustand["key"]["acc"] == "flat", "die Schreibweise faehrt mit"


class TestSeite:
    """Die Seite muss die Einstellung anbieten - sonst gibt es den Dialog nicht."""

    def test_zahnrad_und_dialog_sind_da(self):
        assert 'id="gear"' in PAGE
        assert 'id="dialog"' in PAGE

    def test_alle_drei_schreibweisen_stehen_zur_wahl(self):
        for modus in ("auto", "sharp", "flat"):
            assert f'data-mode="{modus}"' in PAGE, modus

    def test_wahl_wird_gemerkt(self):
        assert "localStorage" in PAGE and "jampilot.accidental" in PAGE

    def test_die_seite_kann_beide_schreibweisen(self):
        # Die Umschreibung passiert im Browser - beide Tabellen muessen da sein.
        assert "FLAT_OF" in PAGE and "SHARP_OF" in PAGE

    def test_alle_vier_instrumente_stehen_zur_wahl(self):
        # Chords, Bass, Guitar und Keyboard. Ohne die Optionen gibt es keinen Modus.
        for inst in ("chords", "bass", "guitar", "keys"):
            assert f'data-inst="{inst}"' in PAGE, inst

    def test_griffbrett_ist_abschaltbar(self):
        # Ein Schalter im Dialog blendet das Griffbrett aus - fuer Bass UND
        # Gitarre gleichermassen. Die Wahl wird wie die anderen gemerkt.
        for wahl in ("on", "off"):
            assert f'data-fret="{wahl}"' in PAGE, wahl
        assert "jampilot.fretboard" in PAGE
        assert "nofretboard" in PAGE          # eine Klasse schaltet beide Bretter

    def test_kontrollgitarre_ist_abschaltbar(self):
        for wahl in ("on", "off"):
            assert f'data-control="{wahl}"' in PAGE
        assert 'fetch("/control-guitar" + location.search, { method: "POST" })' in PAGE
        assert "control_guitar" in PAGE
        assert "kontrollgitarreSetzen" in PAGE

    def test_gitarrengriff_filtert_unsichere_toene(self):
        assert "keepSafe" in PAGE
        assert "secure.has(sounding)" in PAGE
        assert "safe: c.v || null" in PAGE
        assert "safeGuitarName" in PAGE

    def test_gitarrenmodus_hat_griffbild_und_grifflogik(self):
        # Das Griffbild-Element, die Grifflogik (E-/A-Form) und das SVG-Rendern
        # muessen in der Seite stehen - das Feature lebt komplett im Browser.
        assert 'id="fretboard"' in PAGE
        assert "candidates" in PAGE and "fretSvg" in PAGE
        assert "SHAPES_E" in PAGE and "SHAPES_A" in PAGE
        assert 'body.guitar' in PAGE          # eigene Sicht, per Klasse geschaltet

    def test_gitarrenmodus_ist_lagenbewusst(self):
        # Die Voicing-Wahl nutzt den Vorlauf: ein DP-Planer waehlt ueber die
        # KOMMENDEN Akkorde den bewegungsaermsten Pfad und schreibt jede Lage
        # einmal fest (Receding Horizon). Das ist der Unterschied zum Katalog.
        assert "planVoicing" in PAGE and "futureWindow" in PAGE
        assert "lastVoicing" in PAGE          # die gegriffene Lage traegt weiter
        assert "OPEN" in PAGE                 # offene Sonderformen als Tieflage

    def test_keyboardmodus_hat_klaviatur_und_griffe(self):
        # Klaviatur-SVG, Intervalltabelle (BTC-Vokabular) und der Renderer
        # muessen in der Seite stehen - das Feature lebt komplett im Browser,
        # per Klasse geschaltet wie Gitarre und Bass.
        assert "pianoSvg" in PAGE
        assert "KEY_INTERVALS" in PAGE
        assert "renderKeyboard" in PAGE
        assert "body.keys" in PAGE

    def test_keyboardmodus_ist_lagenbewusst(self):
        # Auch die Klaviatur waehlt nicht isoliert: derselbe DP wie beim
        # Gitarren-Griffbild sucht ueber die kommenden Akkorde die Umkehrung
        # mit der geringsten Fingerbewegung; die Handlage traegt weiter.
        assert "planKeyVoicing" in PAGE and "keyCandidates" in PAGE
        assert "lastKeyVoicing" in PAGE

    def test_keyboard_zeigt_die_gemessene_bassnote(self):
        # Die linke Hand: bei C/E gehoert das E unter den C-Dur-Griff - das ist
        # die Information, die der Akkordname allein nicht traegt.
        assert "bassPc" in PAGE

    def test_stufen_sind_abschaltbar(self):
        # Nashville-Stufen ueber den Akkorden: an/invertiert/aus im Dialog,
        # gemerkt wie die anderen Einstellungen, per Body-Klasse geschaltet
        # (kein Chip-Neuaufbau beim Umschalten).
        for wahl in ("on", "invert", "off"):
            assert f'data-degrees="{wahl}"' in PAGE, wahl
        assert "jampilot.degrees" in PAGE
        assert "nodegrees" in PAGE
        assert "setzeStufen" in PAGE

    def test_stufen_sind_invertierbar(self):
        # Dritter Modus: die Stufe gross, der Akkordname klein darueber - fuer
        # Spieler, die in Funktionen denken. Reines CSS ueber die Body-Klasse
        # und `order` (Name in eigenem Span). Wo KEINE Stufe steht (Tonart
        # fehlt noch, N/-/?), muss der Name gross bleiben - sonst zeigte der
        # Chip eine grosse Leerzeile; das leistet der :not(:empty)-Waechter.
        assert "invdegrees" in PAGE
        assert 'class="cname"' in PAGE
        assert ".degree:not(:empty)" in PAGE

    def test_stufe_steht_auch_am_grossen_akkord(self):
        # Nicht nur im Laufband: auch die grosse Ansicht traegt die Stufe -
        # klein darueber, im Invert-Modus gross. Im Bass-Modus ist es die
        # Stufe des GEMESSENEN Basstons ("auf welcher Stufe stehe ich"),
        # sonst die des Akkord-Grundtons.
        assert "#current .degree" in PAGE
        assert "stufeVon(bass || akkord)" in PAGE

    def test_stufen_zaehlen_von_der_dur_skala(self):
        # Die Stufe haengt nur am Grundton: feste Zwoelfertabelle relativ zur
        # Dur-Skala der Tonika, b markiert die Abweichung - keine Qualitaets-
        # Suffixe (Entwurf: docs/exploration/nashville-stufen.md).
        assert "stufeVon" in PAGE
        for stufe in ("♭2", "♭3", "♭5", "♭6", "♭7"):
            assert f'"{stufe}"' in PAGE, stufe

    def test_stufen_haengen_an_der_tonika(self):
        # Kommt die Tonart erstmals an oder wechselt sie, muessen die Chips
        # neu geschrieben werden - sonst stehen veraltete Stufen im Laufband.
        assert "stufenTonika" in PAGE

    def test_tonart_ist_anpinnbar(self):
        # Der Pin ersetzt die ERKANNTE Tonart durch eine feste: Wer mitspielt,
        # kennt die Tonart oft - und die Erkennungs-Restfehler sind nicht
        # billig zu heilen (tests/realaudio/REPORT_key_labels.md). Reines
        # Anzeige-Setting pro Geraet, gemerkt wie die Schreibweise.
        assert 'data-keypin="auto"' in PAGE
        assert "jampilot.keypin" in PAGE
        assert 'id="pinroots"' in PAGE and 'id="pinmodes"' in PAGE
        assert "setzeKeyPin" in PAGE and "pinAlsTonart" in PAGE

    def test_pin_steht_im_badge(self):
        # Der Pin ueberlebt den Songwechsel. Vergessen saehe eine feste
        # Tonart exakt wie eine erkannte aus - mit falschen Stufen ueber
        # allem. Darum der Hinweis im Badge, in der Warnfarbe des
        # Stummschalters (beides manuelle Eingriffe).
        assert '<span class="pin">pinned</span>' in PAGE
        assert "#keybadge .pin" in PAGE

    def test_erkennung_bleibt_unter_dem_pin_sichtbar(self):
        # Die Automatik-Option im Dialog zeigt weiter, was die Erkennung
        # meint - wer am eigenen Pin zweifelt, kann vergleichen, und beim
        # Zurueckschalten weiss man, was man bekommt.
        assert 'id="detkey"' in PAGE and "serverTonart" in PAGE


class TestBassPlaner:
    """Der kuerzeste-Wege-Planer des Bass-Griffbretts - als ECHTE Rechnung.

    Die Logik lebt als JavaScript in der Seite; String-Assertions sehen einen
    falschen Gewichtsfaktor nicht. Darum wird der Planer-Block hier
    ausgeschnitten und in Node ausgefuehrt. Ohne Node wird uebersprungen.
    """

    @staticmethod
    def _plan(pcs, last):
        import json
        import shutil
        import subprocess

        if shutil.which("node") is None:
            pytest.skip("kein node")
        start = PAGE.index("const BASS_TUNING")
        end = PAGE.index("// Die kommende Basslinie")
        harness = (PAGE[start:end]
                   + f"\nconsole.log(JSON.stringify("
                     f"planBassLine({json.dumps(pcs)}, {json.dumps(last)})));")
        out = subprocess.run(["node", "-e", harness], capture_output=True,
                             text=True, check=True)
        return json.loads(out.stdout)

    def test_quergriff_schlaegt_die_tiefe_lage(self):
        # Der gemeldete Bug: von D (A-Saite, 5. Bund) nach G zeigte der Planer
        # die E-Saite am 3. Bund - die Knotenkosten (tiefe Saite, tiefe Oktave)
        # ueberstimmten den kuerzesten Weg. Richtig ist der Quergriff:
        # D-Saite, 5. Bund, gleicher Bund, eine Saite weiter.
        pfad = self._plan([2, 7], {"s": 1, "f": 5})           # D -> G
        assert pfad[1] == {"s": 2, "f": 5}

    def test_isolierte_vorgabe_bleibt_idiomatisch(self):
        # Ohne Kontext entscheiden allein die Knotenkosten: Eb gehoert auf die
        # A-Saite (6. Bund), nicht hoch auf die E-Saite (11. Bund) - das
        # dokumentierte Beispiel aus dem Planer-Kommentar.
        pfad = self._plan([3], None)                          # Eb, isoliert
        assert pfad[0] == {"s": 1, "f": 6}

    def test_naher_lagenwechsel_bleibt_auf_der_saite(self):
        # Gegenprobe zur Gewichtung: C nach D (A-Saite, 5. Bund) ist am
        # kuerzesten zwei Buende runter auf derselben Saite - der staerkere
        # Uebergangsfaktor darf das nicht auf eine andere Saite draengen.
        pfad = self._plan([2, 0], {"s": 1, "f": 5})           # D -> C
        assert pfad[1] == {"s": 1, "f": 3}

    def test_ein_vamp_pendelt_auf_der_saite_statt_quer(self):
        # Der zweite gemeldete Bug: der RUNDWEG D -> C -> D. Der Planer sieht
        # die Rueckkehr und fand zweimal Saitenkreuzen bei stehendem Bund
        # (C auf der G-Saite - eine Oktave zu hoch!) billiger als zweimal
        # zwei Buende auf der A-Saite. Der paarweise Test oben sieht das
        # nicht, erst die Linie mit Rueckkehr. Verlangt a - b < 0.6.
        pfad = self._plan([2, 0, 2], {"s": 1, "f": 5})        # D -> C -> D
        assert pfad == [{"s": 1, "f": 5}, {"s": 1, "f": 3}, {"s": 1, "f": 5}]

    def test_der_quergriff_gewinnt_auch_im_rundweg(self):
        # Und die Gegenrichtung des Vamps: D -> G -> D bleibt der Quergriff
        # am 5. Bund - hier ist Saitenkreuzen richtig, weil der Bund steht.
        pfad = self._plan([2, 7, 2], {"s": 1, "f": 5})        # D -> G -> D
        assert pfad == [{"s": 1, "f": 5}, {"s": 2, "f": 5}, {"s": 1, "f": 5}]


class TestTonartPin:
    """Die Vorzeichen-Logik des Pins - als ECHTE Rechnung gegen tonality.

    `accidentalForKey` in der Seite spiegelt tonality.accidental_for_key
    (der Server schickt beim Pin ja keine Schreibweise mit). String-
    Assertions saehen eine verrutschte Quintenzirkel-Menge nicht - darum
    wird der Block ausgeschnitten und in Node gegen das Python-Original
    gerechnet. Ohne Node wird uebersprungen.
    """

    def test_vorzeichen_spiegeln_tonality(self):
        import json
        import shutil
        import subprocess

        if shutil.which("node") is None:
            pytest.skip("kein node")
        from jampilot.chroma import NOTE_NAMES
        from jampilot.tonality import accidental_for_key

        note_pc = PAGE.index("const NOTE_PC")
        start = PAGE.index("const SHARP_MAJOR_PCS")
        harness = (PAGE[note_pc:PAGE.index("};", note_pc) + 2] + "\n"
                   + PAGE[start:PAGE.index("let keyPin")] + """
const out = {};
for (const root of Object.keys(NOTE_PC))
  out[root] = [accidentalForKey(root, false), accidentalForKey(root, true)];
console.log(JSON.stringify(out));""")
        ergebnis = subprocess.run(["node", "-e", harness], capture_output=True,
                                  text=True, check=True)
        js = json.loads(ergebnis.stdout)
        for pc, name in enumerate(NOTE_NAMES):
            assert js[name][0] == accidental_for_key(pc, False), f"{name}-Dur"
            assert js[name][1] == accidental_for_key(pc, True), f"{name}-Moll"


@pytest.fixture
def server():
    """Echter Server auf einem freien Port - die Token-Pruefung sitzt im
    Request-Pfad, ein Test gegen die Klasse allein saehe sie nie."""
    display = web.start(0)
    display.set_mute_toggle(lambda: True)
    port = display._server.server_address[1]
    token = display.url.split("k=")[1]
    yield f"http://127.0.0.1:{port}", token
    display.stop()


class TestToken:
    """Die Steuer-POSTs sind bewusst im LAN erreichbar - eingreifen darf nur,
    wer die URL samt Session-Token hat (Terminal oder QR-Code)."""

    def _post(self, url):
        req = urllib.request.Request(url, method="POST")
        return urllib.request.urlopen(req, timeout=5)

    def test_post_ohne_token_wird_abgelehnt(self, server):
        base, _ = server
        for pfad in ("/mute", "/control-guitar"):
            with pytest.raises(urllib.error.HTTPError) as fehler:
                self._post(base + pfad)
            assert fehler.value.code == 403, pfad

    def test_post_mit_falschem_token_wird_abgelehnt(self, server):
        base, _ = server
        with pytest.raises(urllib.error.HTTPError) as fehler:
            self._post(base + "/mute?k=falsch")
        assert fehler.value.code == 403

    def test_post_mit_token_schaltet(self, server):
        base, token = server
        with self._post(f"{base}/mute?k={token}") as antwort:
            assert json.loads(antwort.read())["muted"] is True

    def test_qr_verlangt_das_token(self, server):
        # Der QR traegt die URL SAMT Token - offen ausgeliefert waere er die
        # Hintertuer, ueber die sich jeder im LAN das Token holt.
        base, token = server
        with pytest.raises(urllib.error.HTTPError) as fehler:
            urllib.request.urlopen(base + "/qr.svg", timeout=5)
        assert fehler.value.code == 403
        with urllib.request.urlopen(f"{base}/qr.svg?k={token}", timeout=5) as ok:
            assert b"svg" in ok.read()

    def test_die_anzeige_selbst_bleibt_offen(self, server):
        # Anschauen ist harmlos und soll reibungslos bleiben - nur Eingriffe
        # brauchen das Token.
        base, _ = server
        with urllib.request.urlopen(base + "/", timeout=5) as antwort:
            assert antwort.status == 200


class TestStummImBroadcaster:
    def test_republish_aendert_nur_das_gewuenschte_feld(self):
        b = ChordBroadcaster()
        b.publish({"t": 12.0, "chords": [{"c": "C", "at": 11.0}], "muted": False})
        q, letzter = b.subscribe()          # der letzte Zustand kommt als Rueckgabe,
        assert json.loads(letzter)["muted"] is False   # nicht ueber die Queue

        b.republish(muted=True)

        zustand = json.loads(q.get_nowait())
        assert zustand["muted"] is True
        assert zustand["t"] == 12.0                    # Zeit unangetastet
        assert zustand["chords"] == [{"c": "C", "at": 11.0}]   # Akkorde auch

    def test_republish_erreicht_alle_geraete(self):
        # Laptop und Handy haengen gleichzeitig dran. Wer auf dem einen pausiert,
        # muss es auf dem anderen SOFORT sehen - nicht erst beim naechsten
        # Analysetakt, sonst zeigen zwei Geraete 250ms lang Verschiedenes an.
        b = ChordBroadcaster()
        b.publish({"t": 1.0, "muted": False})
        laptop, _ = b.subscribe()
        handy, _ = b.subscribe()

        b.republish(muted=True)

        assert json.loads(laptop.get_nowait())["muted"] is True
        assert json.loads(handy.get_nowait())["muted"] is True

    def test_republish_ohne_vorherigen_zustand_stuerzt_nicht_ab(self):
        # Jemand schaltet stumm, bevor die erste Analyse durch ist.
        b = ChordBroadcaster()
        q, _ = b.subscribe()
        b.republish(muted=True)
        assert json.loads(q.get_nowait()) == {"muted": True}


class TestStummAufDerSeite:
    def test_leertaste_schaltet_stumm(self):
        assert 'ev.code === "Space"' in PAGE
        assert "umschalten()" in PAGE

    def test_es_gibt_einen_knopf_fuer_geraete_ohne_tastatur(self):
        # Die Anzeige steht meistens auf einem Handy. Ohne Knopf waere die Pause
        # dort nicht erreichbar - ein Tippen irgendwohin ist schon fuer Vollbild
        # vergeben.
        assert 'id="mute"' in PAGE
        assert '$("mute").addEventListener("click"' in PAGE

    def test_der_zustand_ist_sichtbar(self):
        assert 'id="mutebadge"' in PAGE
        assert "body.muted" in PAGE

    def test_die_wahrheit_kommt_vom_server(self):
        # Nicht optimistisch umschalten: Sonst laufen zwei Geraete auseinander,
        # wenn beide gleichzeitig druecken.
        assert 'fetch("/mute" + location.search, { method: "POST" })' in PAGE
        assert "(await antwort.json()).muted" in PAGE

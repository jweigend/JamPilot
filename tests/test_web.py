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
        broadcaster.publish({"t": 1.0, "frontier": 3.0,
                             "committed": [{"c": "C", "at": 0.5}]})
        broadcaster.publish({"t": 2.0, "frontier": 4.0,
                             "committed": [{"c": "C", "at": 0.5},
                                           {"c": "G", "at": 4.0}]})
        (zustand,) = _leeren(q)
        assert zustand["t"] == 2.0
        assert len(zustand["committed"]) == 2   # Historie steckt im Snapshot

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
            "t": 12.0, "frontier": 14.0, "committed": [{"c": "A#", "at": 10.0}],
            "key": {"tonic": "F", "minor": False, "acc": "flat", "label": "F-Dur"},
        })
        (zustand,) = _leeren(q)
        assert zustand["committed"][0]["c"] == "A#", "Akkorde gehen kanonisch raus"
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

    def test_lagenwahl_im_pausierten_record_modus(self):
        # Wer im Record-Modus anhaelt, kann die Lage der Stelle durchschalten:
        # zwei Pfeile und der Stand ("2/3") unter dem Griffbild. Sichtbar nur
        # bei pausiertem Mitschnitt - waehrend der Fahrt spraenge ein schon
        # gezeigtes Griffbild um (docs/exploration/lagenwahl-im-record-modus.md).
        assert 'id="fbswitch"' in PAGE
        assert "wechsleLage" in PAGE and "lagenKontext" in PAGE
        assert "body.recording.rec-paused #fbswitch" in PAGE

    def test_lagenwahl_ankert_die_stelle_fuer_alle_drei_instrumente(self):
        # Die Wahl ist ein Anker auf dem Event (Onset als Schluessel,
        # publish-once macht ihn stabil): dieselbe Stelle sieht bei jedem
        # Durchlauf gleich aus - fuer Gitarre, Keyboard UND Bass.
        assert "fbPins" in PAGE and "kbPins" in PAGE and "bassPins" in PAGE
        assert "fbPins.get(key)" in PAGE      # der Anker ueberstimmt den Planer
        assert "kbPins.get(key)" in PAGE
        assert "planBassLine(line, lastBassPos, fest)" in PAGE

    def test_lagenwahl_rechnet_folgegriffe_vom_anker_neu(self):
        # Ein Anker invalidiert nach vorn: alles schon Entschiedene ab diesem
        # Onset wird verworfen und vom Anker aus neu geplant (er wird der
        # feste Startknoten, wie sonst lastVoicing). Davor bleibt alles stehen.
        assert "voicings.delete(k)" in PAGE
        assert "kbVoicings.delete(k)" in PAGE
        assert "lastVoicing = v; fbShown" in PAGE

    def test_lagenwahl_anker_fallen_mit_dem_mitschnitt(self):
        # R aus verwirft den Mitschnitt - die Anker zeigen dann auf
        # Stream-Zeiten, zu denen es kein Audio mehr gibt, und fallen mit.
        assert "fbPins.clear()" in PAGE
        assert "kbPins.clear()" in PAGE
        assert "bassPins.clear()" in PAGE

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


@pytest.fixture(autouse=True)
def _eigenes_config_home(tmp_path, monkeypatch):
    """Das Token ist persistent (XDG_CONFIG_HOME) - Tests gehoeren nicht an
    die echte Konfiguration des Nutzers, und frisch soll es auch sein."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))


class TestPersistentesToken:
    """Die Seite am Notenstaender bleibt offen, waehrend die Anwendung neu
    startet. Wuerfelte jeder Start ein neues Token, liefe dort jeder Eingriff
    (Record, Mute) still in ein 403 - die Anzeige (ohne Token) verbindet sich
    ja anstandslos neu und sieht voellig gesund aus."""

    def test_neustart_behaelt_das_token(self):
        erstes = web._persistent_token()
        assert web._persistent_token() == erstes

    def test_tokendatei_gehoert_nur_dem_nutzer(self, tmp_path):
        web._persistent_token()
        datei = tmp_path / "jampilot" / "token"
        assert datei.stat().st_mode & 0o777 == 0o600

    def test_unlesbares_config_home_faellt_auf_lauf_token_zurueck(self, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", "/proc/gibt-es-nicht")
        assert web._persistent_token()  # kein Absturz, Token nur fuer den Lauf


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
        for pfad in ("/mute", "/control-guitar", "/record"):
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

    def test_symbol_ist_offen_und_verlinkt(self, server):
        # Browser holen /favicon.ico ungefragt; die Seite selbst zeigt auf
        # /icon.png (Tab und "Zum Home-Bildschirm" auf dem Handy). Beides ohne
        # Token: Ein Bild verraet nichts.
        base, _ = server
        for pfad in ("/icon.png", "/favicon.ico"):
            with urllib.request.urlopen(base + pfad, timeout=5) as antwort:
                assert antwort.headers["Content-Type"] == "image/png", pfad
                assert antwort.read()[:8] == b"\x89PNG\r\n\x1a\n", pfad
        assert 'rel="icon" type="image/png" href="/icon.png"' in PAGE
        assert 'rel="apple-touch-icon" href="/icon.png"' in PAGE


class TestStummImBroadcaster:
    def test_republish_aendert_nur_das_gewuenschte_feld(self):
        b = ChordBroadcaster()
        b.publish({"t": 12.0, "committed": [{"c": "C", "at": 11.0}],
                   "muted": False})
        q, letzter = b.subscribe()          # der letzte Zustand kommt als Rueckgabe,
        assert json.loads(letzter)["muted"] is False   # nicht ueber die Queue

        b.republish(muted=True)

        zustand = json.loads(q.get_nowait())
        assert zustand["muted"] is True
        assert zustand["t"] == 12.0                    # Zeit unangetastet
        assert zustand["committed"] == [{"c": "C", "at": 11.0}]   # Akkorde auch

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

    def test_stumm_friert_nichts_mehr_ein(self):
        """Stumm ist stumm - alle Ansichten laufen weiter.

        Frueher fror der grosse Akkord beim Stummschalten ein und das Laufband
        wurde gedimmt: der Versuch, aus dem Stummschalter ein "jetzt in Ruhe
        ansehen" zu machen, solange es keinen Transport gab. Den gibt es jetzt
        hinter R - und er haelt den TON an, nicht nur das Bild.
        """
        assert "frozenSeg" not in PAGE
        assert "currentAudible" not in PAGE
        assert "body.muted #lane" not in PAGE

    def test_der_stummknopf_ist_ein_lautsprecher(self):
        # Pause/Play auf dem Stummknopf war eine Notluege; neben einem echten
        # Transport waere sie eine verwirrende. Und der tote Selektor auf ein
        # #pause, das es nie gab, darf nicht zurueckkommen.
        assert "#mute .ic-play" not in PAGE and 'id="pause"' not in PAGE
        assert "body.muted #mute .ic-off" in PAGE

    def test_die_wahrheit_kommt_vom_server(self):
        # Nicht optimistisch umschalten: Sonst laufen zwei Geraete auseinander,
        # wenn beide gleichzeitig druecken.
        assert 'fetch("/mute" + location.search, { method: "POST" })' in PAGE
        assert "(await antwort.json()).muted" in PAGE


class TestRecordSteuerung:
    """Der eine POST, mit dem Browser und Handy den Record-Modus bedienen."""

    def _post(self, url):
        req = urllib.request.Request(url, method="POST")
        return urllib.request.urlopen(req, timeout=5)

    @pytest.fixture
    def server_mit_record(self):
        display = web.start(0)
        aufrufe = []

        def steuerung(befehl):
            aufrufe.append(befehl)
            return {"recording": befehl != "toggle", "record_pending": False,
                    "paused": befehl == "pause", "epoch": len(aufrufe), "hint": None}

        display.set_record_control(steuerung)
        port = display._server.server_address[1]
        token = display.url.split("k=")[1]
        yield f"http://127.0.0.1:{port}", token, aufrufe
        display.stop()

    def test_ohne_stream_kommt_503_statt_absturz(self, server):
        base, token = server
        with pytest.raises(urllib.error.HTTPError) as fehler:
            self._post(f"{base}/record?k={token}&cmd=toggle")
        assert fehler.value.code == 503

    def test_alle_befehle_gehen_durch(self, server_mit_record):
        base, token, aufrufe = server_mit_record
        for cmd in ("toggle", "pause", "prev", "next", "start", "end"):
            with self._post(f"{base}/record?k={token}&cmd={cmd}") as antwort:
                json.loads(antwort.read())
        assert aufrufe == ["toggle", "pause", "prev", "next", "start", "end"]

    def test_unbekannter_befehl_wird_abgewiesen(self, server_mit_record):
        base, token, aufrufe = server_mit_record
        with pytest.raises(urllib.error.HTTPError) as fehler:
            self._post(f"{base}/record?k={token}&cmd=rewind")
        assert fehler.value.code == 400 and aufrufe == []


class TestSeiteKenntDenRecordModus:
    def test_leertaste_bleibt_stumm_r_nimmt_auf(self):
        assert "Space = mute" in PAGE and "R = record" in PAGE
        assert 'recordBefehl("toggle")' in PAGE

    def test_pfeile_home_end_und_p_sind_transport(self):
        for cmd in ("prev", "next", "start", "end", "pause"):
            assert f'recordBefehl("{cmd}")' in PAGE, cmd

    def test_die_leiste_hat_fuenf_knoepfe_und_einen_roten_punkt(self):
        assert 'id="transport" hidden' in PAGE and 'id="rec" hidden' in PAGE
        for cmd in ("start", "prev", "pause", "next", "end"):
            assert f'data-cmd="{cmd}"' in PAGE, cmd
        # Keine Sekundenangabe in der Buehnenanzeige - der Modus, nicht der
        # Rueckstand.
        assert "behind live" not in PAGE

    def test_die_uhr_wird_bei_spruengen_neu_gestellt(self):
        assert "state.epoch !== epoch" in PAGE and "offsetSamples = []" in PAGE
        assert "if (frozenAt !== null) return frozenAt;" in PAGE

    def test_ein_gescheitertes_r_erklaert_sich(self):
        # Die einzige Schrift des Record-Modus - nur im Fehlerfall, kurz.
        assert 'id="recbadge" hidden' in PAGE
        assert "if (state.record_hint) zeigeRecordHinweis(state.record_hint)" in PAGE


class TestTaktstriche:
    """Beats sind ein zweiter Publish-once-Kanal, die Striche abschaltbar."""

    def test_taktstriche_sind_abschaltbar(self):
        for wahl in ("on", "off"):
            assert f'data-beats="{wahl}"' in PAGE, wahl
        assert "jampilot.beats" in PAGE
        assert "nobeats" in PAGE

    def test_die_seite_liest_den_beat_kanal(self):
        assert "state.beats" in PAGE
        assert "syncBeats" in PAGE
        assert 'className = b.n === 1 ? "beat bar" : "beat"' in PAGE

    def test_beats_fahren_im_snapshot_mit(self):
        broadcaster = ChordBroadcaster()
        q, _ = broadcaster.subscribe()
        broadcaster.publish({"t": 1.0, "frontier": 3.0, "committed": [],
                             "beats": [{"at": 2.0, "n": 1}, {"at": 2.5, "n": 2}]})
        assert _leeren(q)[0]["beats"] == [{"at": 2.0, "n": 1}, {"at": 2.5, "n": 2}]


class TestBassPlanerMitLage:
    """Mit gemessener Tonhoehe ({pc, p}) bleiben nur die Griffe, die genau
    diesen Ton geben - der Handweg entscheidet nur noch zwischen ihnen."""

    _plan = staticmethod(TestBassPlaner._plan)

    def test_e1_liegt_auf_der_leeren_e_saite(self):
        # Ohne Lage waere E von der A-Saite/5. Bund aus der Quergriff
        # (D-Saite, 2. Bund) - mit E1 gibt es nur die leere E-Saite.
        pfad = self._plan([{"pc": 4, "p": 28}], {"s": 1, "f": 5})
        assert pfad[0] == {"s": 0, "f": 0}

    def test_e2_waehlt_zwischen_a7_und_d2_nach_handweg(self):
        pfad = self._plan([{"pc": 4, "p": 40}], {"s": 1, "f": 7})
        assert pfad[0] == {"s": 1, "f": 7}
        pfad = self._plan([{"pc": 4, "p": 40}], {"s": 2, "f": 3})
        assert pfad[0] == {"s": 2, "f": 2}

    def test_e3_liegt_hoch_auf_der_g_saite(self):
        pfad = self._plan([{"pc": 4, "p": 52}], None)
        assert pfad[0] == {"s": 3, "f": 9}

    def test_lage_ausserhalb_des_fensters_laesst_alle_griffe_zu(self):
        # G3 (55) liegt erst im 12. Bund - dann gilt wieder der Handweg.
        pfad = self._plan([{"pc": 7, "p": 55}], {"s": 1, "f": 5})
        assert pfad[0] == {"s": 2, "f": 5}

    def test_ohne_lage_wie_bisher(self):
        pfad = self._plan([{"pc": 2, "p": None}, {"pc": 7, "p": None}], {"s": 1, "f": 5})
        assert pfad[1] == {"s": 2, "f": 5}


class TestSeiteAlsGanzes:
    """Die Seite als Ganzes in Node (tests/seite_harness.js): das komplette
    Skript in einer vm, mit DOM-Attrappe, stellbarer Uhr und einem
    EventSource, dem der Test die Zustaende des Servers einzeln zustellt.

    Die Fehler aus dem Review 2026-11 (docs/exploration/code-review-2026-11.md)
    waren Zustandsfehler: Sie zeigen sich erst in einer FOLGE von Zustaenden.
    Ohne Node wird uebersprungen.
    """

    VOLL = """
      const voll = (t, extra = {}) => ({ t, frontier: t + 2, committed: [
        { at: Math.floor(t) - 1, c: "C", b: "C", p: 36 },
        { at: Math.floor(t) + 1, c: "F", b: "F", p: 41 }],
        beats: [], envelope: null, key: null, muted: false,
        control_guitar: false, recording: false, record_pending: false,
        paused: false, epoch: 0, record_hint: null, ...extra });
      const lauf = (p, t, n) => {
        for (let i = 0; i < n; i++) { p.tick(250); t += 0.25; p.msg(voll(t)); p.frame(); }
        return t; };
    """

    @classmethod
    def _szenario(cls, js):
        import json
        import shutil
        import subprocess
        from pathlib import Path

        if shutil.which("node") is None:
            pytest.skip("kein node")
        hier = Path(__file__).parent
        seite = hier.parent / "jampilot" / "data" / "index.html"
        kopf = (f"const {{ seite }} = require({json.dumps(str(hier / 'seite_harness.js'))});\n"
                f"const p = seite({json.dumps(str(seite))});\n" + cls.VOLL)
        out = subprocess.run(["node", "-e", kopf + js], capture_output=True,
                             text=True, check=True)
        return json.loads(out.stdout)

    def test_ein_zustand_ohne_position_verstellt_die_uhr_nicht(self):
        # Stummschalten zwischen Stream-Start und erstem Analyse-Takt: Der
        # Server hat noch keinen Zustand, in den er mischen koennte, und
        # schickt nur {muted: true}. Die Uhr wurde davon NaN - fuer immer.
        s = self._szenario("""
          p.open(); p.msg({ muted: true }); p.frame();
          const davor = p.stand();
          const t = lauf(p, 2.0, 8);
          const s = p.stand();
          console.log(JSON.stringify({ davor: [davor.offset, davor.idle],
            fehler: s.now - t, hoerbar: s.hoerbar && s.hoerbar.c }));
        """)
        assert s["davor"] == [None, "Starting up"]
        assert abs(s["fehler"]) < 0.05
        assert s["hoerbar"] == "C"

    def test_abgeschaltet_steht_stopped_da_und_kein_alter_akkord(self):
        # engine.stop() mischt `running: false` in den letzten Zustand - samt
        # den Akkorden von vorher. Die Seite zeigte den letzten unbegrenzt als
        # laufend, mit gruenem Punkt.
        s = self._szenario("""
          p.open(); const t = lauf(p, 600.0, 20);
          p.msg({ ...voll(t, { recording: true }), running: false });
          p.tick(60000); p.frame();
          const s = p.stand();
          console.log(JSON.stringify({ idle: s.idle, sichtbar: s.idleSichtbar,
            events: s.events.length, recording: s.recording, offset: s.offset }));
        """)
        assert s == {"idle": "Stopped", "sichtbar": True, "events": 0,
                     "recording": False, "offset": None}

    def test_wieder_einschalten_stellt_die_uhr_sofort_neu(self):
        # Der neue Stream zaehlt wieder ab null, der Epoch steht wieder auf 0.
        # Der Minimum-Filter hielt die alte Zeitrechnung 10-20 s lang fest.
        s = self._szenario("""
          p.open(); let t = lauf(p, 3600.0, 60);
          p.msg({ ...voll(t), running: false }); p.frame();
          p.tick(5000); p.msg({ running: true }); p.frame();
          const start = p.stand().idle;
          t = lauf(p, -3.0, 2);
          console.log(JSON.stringify({ start, fehler: p.stand().now - t }));
        """)
        assert s["start"] == "Starting up"
        assert abs(s["fehler"]) < 0.05

    def test_neustart_des_programms_bei_offener_seite(self):
        # Kein Stopp-Zustand, kein {running: true} gesehen (Verbindung war
        # weg): Die Seite erkennt die neue Sitzung allein daran, dass die
        # Position rueckwaerts laeuft, ohne dass ein Epoch es ansagt.
        s = self._szenario("""
          p.open(); let t = lauf(p, 3600.0, 60);
          p.error(); p.tick(8000); p.open();
          t = lauf(p, -3.0, 2);
          console.log(JSON.stringify({ fehler: p.stand().now - t }));
        """)
        assert abs(s["fehler"]) < 0.05

    def test_eine_pause_ist_kein_sitzungswechsel(self):
        # Gegenprobe zur Rueckwaerts-Regel: Pausiert steht `t`, und ein
        # nachgereichter Zustand mit der Position von einem Takt frueher
        # (republish) darf die Uhr nicht verwerfen.
        s = self._szenario("""
          p.open(); let t = lauf(p, 100.0, 40);
          const vorher = p.stand().offset;
          p.msg(voll(t - 0.25)); p.frame();
          console.log(JSON.stringify({ gleich: Math.abs(p.stand().offset - vorher) < 0.3 }));
        """)
        assert s["gleich"]

    def test_griffbild_gehoert_zum_laufenden_akkord(self):
        # sus2, dim und m7b5 gibt es nur als A-Form. Der Planer fragte nur den
        # E-Katalog, liess den laufenden Akkord fallen und zeichnete den
        # NAECHSTEN: unter "Bdim" stand das offene C.
        s = self._szenario("""
          p.open(); p.instrument("guitar");
          p.msg({ ...voll(10.5), committed: [{ at: 10, c: "Bdim" },
                  { at: 11, c: "C" }, { at: 11.8, c: "Am" }] });
          const v = p.fn.decideVoicing({ at: 10, c: "Bdim" });
          const hoch = ["Gdim", "G#m7b5", "Gsus2"].map(c => {
            const m = c.match(/^([A-G]#?)(.*)$/);
            return p.fn.candidates(m[1], m[2]).map(x => x.frets); });
          console.log(JSON.stringify({ bdim: v && v.frets, hoch,
            d: p.fn.candidates("D", "").map(x => [x.shape, x.base]) }));
        """)
        assert s["bdim"] == [None, 2, 3, 4, 3, None]          # B D F, A-Form
        # G und G# haben in diesen Qualitaeten nur die hohe A-Form - besser
        # als ein leeres Feld.
        assert s["hoch"] == [[[None, 10, 11, 12, 11, None]],
                             [[None, 11, 12, 11, 12, None]],
                             [[None, 10, 12, 12, 10, 10]]]
        # ... und wo es eine E-Form gibt, bleibt die Barre-Grenze bei Bund 9.
        assert s["d"] == [["A", 5], ["open", 0]]

    def test_klaviatur_antwortet_nicht_mit_dem_nachfolger(self):
        # Dieselbe Sicherung wie beim Griffbild: Hat der laufende Akkord keine
        # Umkehrung, zeigt die Klaviatur nichts - nicht den naechsten Akkord.
        # Mit dem vollen Katalog tritt der Fall nicht ein; der Test stellt
        # ihn mit einem Fenster, dessen erster Eintrag keine Kandidaten hat.
        s = self._szenario("""
          p.open(); p.instrument("keys");
          const ohne = { root: "C", q: "unbekannt", name: "Cunbekannt" };
          const c = { root: "C", q: "", name: "C" };
          const leer = p.fn.planKeyVoicing([ohne, c], null);
          const mitC = p.fn.planKeyVoicing([c, ohne], null);
          p.msg({ ...voll(10.5), committed: [{ at: 10, c: "Bdim" },
                  { at: 11, c: "C" }] });
          const v = p.fn.decideKeyVoicing({ at: 10, c: "Bdim" });
          console.log(JSON.stringify({ leer, vollNotes: mitC && mitC.notes,
            bdim: v && v.notes.map(n => n % 12).sort((a, b) => a - b) }));
        """)
        assert s["leer"] is None
        assert s["vollNotes"]                                  # C selbst geht
        assert s["bdim"] == [2, 5, 11]                         # B D F, nicht C E G

    def test_chip_laeuft_durch_die_jetzt_linie_und_blasst_aus(self):
        # Der Chip haelt an der JETZT-Linie nicht an (bis 11.11.2026 staute
        # er sich dort und blasste im Stand aus): er laeuft im selben Tempo
        # weiter nach links. Davor steht er in voller Farbe - auch am
        # rechten Rand, nicht erst kurz vor der Linie.
        s = self._szenario("""
          p.open();
          const z = t => ({ ...voll(t), committed: [
            { at: 12.5, c: "C", b: "C", p: 36 }, { at: 14, c: "F", b: "F", p: 41 }] });
          let t = 10; const bilder = [];
          for (let i = 0; i < 28; i++) {
            p.tick(125); t += 0.125; p.msg(z(t)); p.frame();
            bilder.push({ now: p.stand().now, chips: p.chips() });
          }
          console.log(JSON.stringify(bilder));
        """)
        jetzt_x = 140.0                    # 14 % von 1000 px (Attrappe)
        pps = 830.0 / 2.8                  # 83 % der Breite fuer 2,8 s Vorlauf
        davor = [b for b in s if b["now"] < 12.4 and len(b["chips"]) == 2]
        dahinter = [b for b in s if 12.55 < b["now"] < 12.8]
        assert davor and dahinter
        for b in davor:                    # Zukunft: volle Farbe, beide
            assert [c["deckung"] for c in b["chips"]] == [1, 1]
        for b in dahinter:
            c, f = b["chips"]
            vorbei = b["now"] - 12.5
            assert c["x"] == pytest.approx(jetzt_x - vorbei * pps, abs=0.5)
            assert c["deckung"] == pytest.approx(1 - vorbei / 0.35, abs=0.01)
            assert f["deckung"] == 1
            assert f["x"] - c["x"] == pytest.approx(1.5 * pps, abs=0.5)  # ein Tempo
        # ... und nach 0,35 s ist er weg.
        assert s[-1]["now"] > 12.9
        assert [c["at"] for c in s[-1]["chips"]] == [14]

    def test_huellkurve_wird_nur_im_ausklang_geglaettet(self):
        # Der Abkling-Folger: hoch sofort und in voller Hoehe (die
        # Anschlagkante ist die Information), runter hoechstens exponentiell
        # - der Saegezahn eines tiefen Basstons im Ausklang verschwindet.
        s = self._szenario("""
          const roh = { t0: 5, dt: 0.0125,
            bass: [0, 0, 1, 0.2, 0.9, 0.1, 0.8, 0, 0, 0, 0, 0, 0.7, 0],
            full: [0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3] };
          const glatt = p.fn.glaetteHuellkurve(roh);
          console.log(JSON.stringify({ roh, glatt }));
        """)
        roh, glatt = s["roh"], s["glatt"]
        assert (glatt["t0"], glatt["dt"]) == (roh["t0"], roh["dt"])   # Zeitachse bleibt
        assert glatt["full"] == pytest.approx(roh["full"])            # Flaches bleibt flach
        b = glatt["bass"]
        assert len(b) == len(roh["bass"])
        assert b[:3] == [0, 0, 1]                    # Kante: derselbe Block, volle Hoehe
        assert b[12] == pytest.approx(0.7)           # der zweite Anschlag ebenso
        assert all(g >= r for g, r in zip(b, roh["bass"]))
        # Der Saegezahn im Ausklang: roh faellt die Kurve von Block zu Block
        # auf ein Fuenftel und springt zurueck - geglaettet gibt sie je Block
        # hoechstens 8 % nach (exp(-12,5 ms / 150 ms) = 0,92).
        assert min(y / x for x, y in zip(roh["bass"][2:7], roh["bass"][3:8])) < 0.2
        assert all(y >= 0.92 * x for x, y in zip(b[2:12], b[3:12]))
        assert b[11] < 0.6                           # ... aber er klingt wirklich ab

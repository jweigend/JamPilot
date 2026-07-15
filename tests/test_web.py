"""SSE-Verteilung: bei Rueckstau gewinnt der NEUE Zustand, nicht der alte.

Dazu der Vertrag der Seite: Akkorde gehen KANONISCH raus (immer mit Kreuz),
die Schreibweise entscheidet der Browser aus Tonart + Einstellung.
"""

import json
import queue

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

    def test_alle_drei_instrumente_stehen_zur_wahl(self):
        # Chords, Bass und - neu - Guitar. Ohne die Optionen gibt es keinen Modus.
        for inst in ("chords", "bass", "guitar"):
            assert f'data-inst="{inst}"' in PAGE, inst

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
        assert 'fetch("/mute", { method: "POST" })' in PAGE
        assert "(await antwort.json()).muted" in PAGE

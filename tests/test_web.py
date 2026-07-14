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

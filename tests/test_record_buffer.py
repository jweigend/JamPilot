"""Der Mitschnitt (Record-Modus): aufnehmen, anhalten, zurueck, wieder vor.

Die Bloecke tragen fortlaufende Zahlen (Block k besteht aus lauter k). So sagt
ein Blick auf die Ausgabe, WELCHE Stelle des Mitschnitts gerade gespielt wird -
und Lueckenlosigkeit ist eine Aussage ueber eine Zahlenfolge, nicht ueber Audio.
"""

import numpy as np
import pytest

from jampilot import record_buffer
from jampilot.record_buffer import RecordBuffer, plan

SR = 1000
F = 100                     # Blockgroesse
CH = 2


def puffer(minuten=0.1, aufnahme=True):
    """Mitschnitt fuer 6 s bei 1 kHz - 60 Bloecke. Standardmaessig AN."""
    p = RecordBuffer(SR, CH, minuten, blocksize=F)
    if aufnahme:
        p.start_record()
    return p


def block(k: int) -> np.ndarray:
    return np.full((F, CH), float(k), dtype=np.float32)


def spiele(p: RecordBuffer, k: int) -> np.ndarray:
    """Block k durchschicken; zurueck kommt, was zu hoeren ist.

    Block k liegt bei Stream-Position k*F - genau die Zahl, die die
    Verzoegerungsstufe dem Mitschnitt mitgibt.
    """
    b = block(k)
    p.process(b, k * F)
    return b


def welcher(aus: np.ndarray) -> float:
    """Die Blocknummer, die hier klingt - gemessen in der MITTE.

    Die Raender koennen ueberblendet sein; die Mitte eines Blocks ist immer
    der reine Wert.
    """
    return float(aus[F // 2, 0])


class TestLiveDurchreichen:
    def test_ohne_pause_ist_die_ausgabe_bitgleich(self):
        # Das ist die Zusage, auf der alles andere steht: Wer nie pausiert,
        # hoert exakt das, was ohne Mitschnitt herauskaeme. Kein Filter, keine
        # Umrechnung, kein Pegel.
        p = puffer()
        for k in range(20):
            aus = spiele(p, k)
            assert np.array_equal(aus, block(k))

    def test_live_meldet_keinen_rueckstand(self):
        p = puffer()
        for k in range(5):
            spiele(p, k)
        assert p.live and p.offset_seconds == 0.0 and not p.paused


class TestPause:
    def test_pausiert_schweigt_der_lautsprecher(self):
        p = puffer()
        for k in range(5):
            spiele(p, k)
        p.toggle_pause()
        erster = spiele(p, 5)
        # Der erste Block wird AUSGEBLENDET, nicht abgeschnitten - sonst
        # knackt es. Nach der Rampe ist er still.
        assert erster[-1, 0] == 0.0
        for k in range(6, 12):
            assert not spiele(p, k).any()

    def test_der_rueckstand_waechst_mit_der_pausendauer(self):
        p = puffer()
        for k in range(5):
            spiele(p, k)
        p.toggle_pause()
        for k in range(5, 15):
            spiele(p, k)
        # Zehn Bloecke Pause = zehn Bloecke Rueckstand. Der erste Block der
        # Pause (5) wurde nur ausgeblendet und gilt als ungehoert - er wird
        # beim Fortsetzen wiederholt, siehe test_fortsetzen_verliert_nichts.
        assert p.offset_seconds == pytest.approx(10 * F / SR)

    def test_fortsetzen_verliert_nichts(self):
        # Der eigentliche Zweck: Was waehrend der Pause lief, ist danach da -
        # der Reihe nach, ohne Luecke.
        p = puffer()
        for k in range(5):
            spiele(p, k)
        p.toggle_pause()
        for k in range(5, 15):
            spiele(p, k)
        p.toggle_pause()                    # weiter
        gehoert = [welcher(spiele(p, k)) for k in range(15, 25)]
        # Weiter geht es bei Block 5 - dem Block, der beim Pausieren
        # ausgeblendet wurde -, und von da an lueckenlos.
        assert gehoert == [5, 6, 7, 8, 9, 10, 11, 12, 13, 14]

    def test_pause_am_anschlag_laeuft_nicht_ueber(self):
        # Wer die Pause vergisst, darf keinen Absturz und keinen Sprung ins
        # Nirgendwo bekommen: Der Rueckstand steht am Puffer-Ende still.
        p = puffer(minuten=0.05)            # 3 s = 30 Bloecke
        spiele(p, 0)
        p.toggle_pause()
        for k in range(1, 200):
            spiele(p, k)
        assert p.behind_limit
        assert p.offset_seconds <= p.capacity_seconds

    def test_nach_ueberlanger_pause_holt_das_fortsetzen_wieder_ein(self):
        # Rechnerisch laeuft die Leseposition waehrend einer vergessenen Pause
        # immer weiter zurueck; der Puffer haelt aber nur seine Laenge. Beim
        # Fortsetzen muss daraus wieder eine gueltige Stelle werden - und
        # gemeldet werden darf ohnehin nur, was noch da ist.
        p = puffer(minuten=0.05)            # 3 s = 30 Bloecke
        spiele(p, 0)
        p.toggle_pause()
        for k in range(1, 200):
            spiele(p, k)
        gemeldet = p.offset_seconds
        assert gemeldet <= p.capacity_seconds
        p.toggle_pause()                    # weiter
        gehoert = [welcher(spiele(p, 200 + i)) for i in range(3)]
        # Es geht am AELTESTEN noch vorhandenen Material weiter, lueckenlos -
        # und nicht irgendwo im Nirgendwo.
        assert gehoert[1] == gehoert[0] + 1 and gehoert[2] == gehoert[1] + 1
        assert gehoert[0] > 160             # nicht der Anfang von vor 200 Bloecken


class TestSpringen:
    def test_zurueck_holt_aelteres_material(self):
        p = puffer()
        for k in range(30):
            spiele(p, k)
        p.seek(-5 * F / SR)                 # fuenf Bloecke zurueck
        assert welcher(spiele(p, 30)) == 25

    def test_vorwaerts_endet_an_der_live_kante(self):
        p = puffer()
        for k in range(30):
            spiele(p, k)
        p.seek(-10 * F / SR)
        p.seek(60.0)                        # weit ueber JETZT hinaus
        assert p.offset_seconds == 0.0
        assert welcher(spiele(p, 30)) == 30

    def test_zurueck_endet_am_anfang_des_mitschnitts(self):
        p = puffer(minuten=0.05)            # 3 s
        for k in range(10):
            spiele(p, k)
        p.seek(-3600.0)                     # eine Stunde zurueck gibt es nicht
        assert 0 < p.offset_seconds <= p.capacity_seconds

    def test_zu_jetzt_hebt_auch_die_pause_auf(self):
        p = puffer()
        for k in range(20):
            spiele(p, k)
        p.toggle_pause()
        for k in range(20, 30):
            spiele(p, k)
        p.to_now()
        assert not p.paused and p.offset_seconds == 0.0
        assert welcher(spiele(p, 30)) == 30


class TestUhrSpruenge:
    def test_jeder_sprung_erhoeht_die_epoche(self):
        # Die Anzeige stellt an dieser Zahl ihre Uhr neu. Bliebe sie stehen,
        # zoege der Browser seinen Schaetzwert sanft nach - und zeigte nach
        # einem Rueckwaertssprung sekundenlang die falsche Stelle.
        p = puffer()
        for k in range(20):
            spiele(p, k)
        anfang = p.epoch
        p.toggle_pause()
        p.toggle_pause()
        p.seek(-1.0)
        p.to_now()
        assert p.epoch == anfang + 4

    def test_ein_sprung_der_nichts_bewegt_zaehlt_nicht(self):
        # An der Live-Kante nach vorn zu springen ist keine Bewegung - und
        # duerfte darum die Uhr der Anzeige nicht neu stellen.
        p = puffer()
        for k in range(20):
            spiele(p, k)
        anfang = p.epoch
        p.seek(5.0)
        assert p.epoch == anfang


class TestUeberblendung:
    def test_kein_sprung_im_signal_beim_pausieren(self):
        # Ein harter Schnitt ist ein Knacken. Gemessen wird die groesste
        # Differenz zweier benachbarter Abtastwerte: Bei einer Rampe ueber
        # 15 Frames von Pegel 5 auf 0 ist das ein Drittel des Pegels, bei
        # einem harten Schnitt der volle Pegel.
        p = puffer()
        for k in range(5):
            spiele(p, k)
        p.toggle_pause()
        aus = spiele(p, 5)
        assert np.abs(np.diff(aus[:, 0])).max() < 5.0

    def test_fortsetzen_ohne_pegelloch(self):
        # Beim Fortsetzen wird von derselben Stelle auf dieselbe Stelle
        # ueberblendet - rechnerisch die Identitaet. Ein Pegelloch hier waere
        # ein Fehler in der Ueberblendung, kein Kompromiss.
        p = puffer()
        for k in range(5):
            spiele(p, k)
        p.toggle_pause()
        spiele(p, 5)
        p.toggle_pause()
        aus = spiele(p, 6)
        assert np.allclose(aus, 5.0)

    def test_kuerzerer_callbackblock_beim_pausieren_crasht_nicht(self):
        # Host-APIs sollen zwar die konfigurierte Blockgroesse liefern; wenn ein
        # Treiber doch einmal kuerzer ankommt, darf die Ueberblendung nicht an
        # einer zu langen Rampe scheitern.
        p = puffer()
        for k in range(5):
            spiele(p, k)
        p.toggle_pause()
        kurz = np.full((8, CH), 5.0, dtype=np.float32)   # kuerzer als FADE
        p.process(kurz, 5 * F)
        assert kurz.shape == (8, CH)
        assert np.all(np.isfinite(kurz))


class TestSpeicherplanung:
    def test_genug_speicher_gibt_den_wunsch_frei(self):
        minuten, hinweis = plan(30.0, 48000, 2, verfuegbar=8 * 2**30)
        assert minuten == 30.0 and hinweis is None

    def test_knapper_speicher_kuerzt_statt_abzubrechen(self):
        # Lieber fuenf Minuten Mitschnitt als keinen: Die Pausetaste ist auch
        # dann noch nuetzlich, und ein Startabbruch waere die schlechteste
        # aller Antworten.
        minuten, hinweis = plan(30.0, 48000, 2,
                                verfuegbar=record_buffer.HEADROOM_BYTES
                                + 10 * 60 * 48000 * 2 * 4)
        assert 0 < minuten < 30.0
        assert "shortened" in hinweis

    def test_zu_wenig_speicher_schaltet_den_mitschnitt_ab(self):
        minuten, hinweis = plan(30.0, 48000, 2, verfuegbar=2**20)
        assert minuten == 0.0
        assert "not enough free memory" in hinweis

    def test_null_minuten_bleiben_null_ohne_hinweis(self):
        assert plan(0.0, 48000, 2, verfuegbar=8 * 2**30) == (0.0, None)

    def test_unbekannter_speicher_wagt_den_versuch(self):
        # Auf Systemen, wo wir die freie Menge nicht sicher erfahren, wird
        # nicht geraten: Der Versuch scheitert notfalls mit MemoryError, und
        # den faengt die Engine ab.
        minuten, hinweis = plan(30.0, 48000, 2, verfuegbar=None) \
            if record_buffer.verfuegbarer_speicher() is None else (30.0, None)
        assert minuten == 30.0

    def test_die_kosten_stehen_fest(self):
        # 48 kHz, stereo, float32 - die Zahl aus der --help und der Doku.
        assert record_buffer.bytes_pro_sekunde(48000, 2) * 60 == 23_040_000


class TestReservierung:
    def test_der_speicher_ist_beim_anlegen_schon_da(self):
        # "Gleich reservieren" heisst: angefasst, nicht nur zugesagt. Sonst
        # kaeme der Seitenfehler im Audio-Callback - und das ist ein Aussetzer.
        p = puffer()
        assert p._ring.shape == (int(0.1 * 60 * SR), CH)
        assert not p._ring.any()            # beschrieben und damit vorhanden

    def test_puffer_kleiner_als_ein_block_reicht_das_signal_durch(self):
        # Entartetes Geraet (winziger Puffer, riesiger Block): lieber
        # unveraendert durchreichen als in den Ringpuffer greifen.
        p = RecordBuffer(SR, CH, minutes=0.001, blocksize=F)   # 60 Frames
        p.start_record()
        aus = spiele(p, 7)
        assert np.array_equal(aus, block(7))


class TestModus:
    """Der Record-Modus als Schalter - und die Zusage, die ihn tragbar macht."""

    def test_aus_ist_bitgleich_und_ruehrt_den_ring_nicht_an(self):
        # Die wichtigste Zeile des Konzepts: Wer R nie drueckt, bekommt das
        # Programm von vorher. Nicht "fast", sondern Byte fuer Byte - und der
        # Ring bleibt leer, es wurde nicht einmal geschrieben.
        p = puffer(aufnahme=False)
        for k in range(1, 30):
            aus = spiele(p, k)
            assert np.array_equal(aus, block(k))
        assert not p._ring.any()
        assert p.offset_seconds == 0.0 and not p.recording and not p.paused

    def test_aus_sind_alle_transportbefehle_folgenlos(self):
        p = puffer(aufnahme=False)
        for k in range(10):
            spiele(p, k)
        anfang = p.epoch
        assert p.toggle_pause() is False
        assert p.seek(-1.0) == 0.0
        p.to_now(); p.to_start()
        assert p.epoch == anfang and p.offset_seconds == 0.0

    def test_der_anfang_der_aufnahme_ist_die_untere_grenze(self):
        # Was vor dem R im Ring lag, ist Material von frueher - verworfen. Ein
        # Sprung zurueck endet am Anfang DIESER Aufnahme, nicht am Pufferende.
        p = puffer(aufnahme=False)
        for k in range(20):
            spiele(p, k)                     # laeuft, wird nicht aufgezeichnet
        p.start_record()
        for k in range(20, 30):
            spiele(p, k)                     # Bloecke 20..29 sind die Aufnahme
        p.seek(-3600.0)
        assert p.offset_seconds == pytest.approx(10 * F / SR)  # bis Block 20
        assert welcher(spiele(p, 30)) == 20

    def test_aus_schalten_geht_zurueck_an_die_live_kante(self):
        p = puffer()
        for k in range(20):
            spiele(p, k)
        p.seek(-1.0)
        p.toggle_pause()
        p.stop_record()
        assert not p.recording and not p.paused and p.offset_seconds == 0.0
        assert np.array_equal(spiele(p, 20), block(20))       # bitgleich

    def test_die_uhr_ist_die_der_verzoegerungsstufe(self):
        # Kein eigener Zaehler, der "angeglichen" wird: `process` bekommt die
        # Stream-Position mit, und die Leseposition liegt exakt darauf.
        p = puffer(aufnahme=False)
        for k in range(50):
            spiele(p, k)
        p.start_record()
        spiele(p, 50)
        assert p.play_position_frames == 51 * F
        p.toggle_pause()
        for k in range(51, 60):
            spiele(p, k)
        assert p.play_position_frames == 51 * F                # steht exakt

    def test_ein_zweites_r_beginnt_eine_neue_aufnahme(self):
        p = puffer()
        for k in range(30):
            spiele(p, k)
        p.stop_record()
        for k in range(30, 40):
            spiele(p, k)
        p.start_record()
        for k in range(40, 45):
            spiele(p, k)
        p.seek(-3600.0)
        assert welcher(spiele(p, 45)) == 40      # nicht 0, nicht 30

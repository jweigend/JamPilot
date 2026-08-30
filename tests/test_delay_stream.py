"""Ringpuffer und Ausgabeuhr - die Zeitbasis der gesamten Anzeige."""

from unittest.mock import PropertyMock, patch

import numpy as np
import pytest

from jampilot.delay_stream import DelayedLoopback


class Zeit:
    """PortAudios time_info."""

    def __init__(self, dac: float):
        self.outputBufferDacTime = dac


@pytest.fixture
def loop():
    with patch("sounddevice.Stream"):
        stream = DelayedLoopback(None, None, delay_seconds=0.5, samplerate=1000,
                                 blocksize=64, channels=2, analysis_seconds=1.0)
    stream._stream.latency = (0.05, 0.09)
    return stream


def _rampe_einspeisen(loop, bloecke: int, blocksize: int = 64, dac_start: float = 0.0):
    """Sample an Stream-Position p bekommt den Wert p - dann verraet der
    Puffferinhalt sofort, ob die Indexrechnung stimmt."""
    position = 0
    for i in range(bloecke):
        indata = np.tile(
            np.arange(position, position + blocksize, dtype=np.float32)[:, None], (1, 2))
        outdata = np.zeros((blocksize, 2), dtype=np.float32)
        dac = dac_start + i * blocksize / loop.samplerate
        loop._callback(indata, outdata, blocksize, Zeit(dac), None)
        position += blocksize


class TestRingpuffer:
    def test_zaehlt_eingegangene_frames(self, loop):
        _rampe_einspeisen(loop, bloecke=30)
        assert loop.captured_frames == 30 * 64

    @pytest.mark.parametrize("laenge", [1, 300, 500, 1000])
    def test_liefert_das_fenster_an_der_richtigen_position(self, loop, laenge):
        _rampe_einspeisen(loop, bloecke=30)      # 1920 Frames durch 1000er Puffer
        ende = loop.captured_frames
        fenster = loop.audio_ending_at(ende, laenge)
        assert np.array_equal(fenster, np.arange(ende - laenge, ende, dtype=np.float32))

    def test_liest_auch_zurueckliegende_positionen(self, loop):
        _rampe_einspeisen(loop, bloecke=30)
        ende = loop.captured_frames - 700
        fenster = loop.audio_ending_at(ende, 200)
        assert np.array_equal(fenster, np.arange(ende - 200, ende, dtype=np.float32))

    @pytest.mark.parametrize("ende_offset,laenge", [
        (0, 1001),      # laenger als der Puffer
        (-900, 200),    # schon ueberschrieben
        (10, 100),      # noch nicht eingelesen
    ])
    def test_ausserhalb_liefert_none_statt_muell(self, loop, ende_offset, laenge):
        _rampe_einspeisen(loop, bloecke=30)
        ende = loop.captured_frames + ende_offset
        assert loop.audio_ending_at(ende, laenge) is None

    def test_ueberlebt_mehrere_wraparounds(self, loop):
        _rampe_einspeisen(loop, bloecke=200)     # 12800 Frames, 1000er Puffer
        ende = loop.captured_frames
        fenster = loop.audio_ending_at(ende, 999)
        assert np.array_equal(fenster, np.arange(ende - 999, ende, dtype=np.float32))


class TestAusgabeuhr:
    def test_delay_wird_auf_frames_gerundet(self, loop):
        assert loop.delay_frames == 500          # 0.5s @ 1000 Hz
        assert loop.delay_seconds == 0.5

    def test_delay_unter_einem_block_wird_angehoben(self):
        with patch("sounddevice.Stream"):
            winzig = DelayedLoopback(None, None, delay_seconds=0.0,
                                     samplerate=1000, blocksize=64)
        assert winzig.delay_frames == 64         # nie kleiner als ein Block

    def test_dac_uhr_liefert_den_ringpuffer_rueckstand(self, loop):
        _rampe_einspeisen(loop, bloecke=30, dac_start=0.09)
        # "Jetzt" = DAC-Zeit des letzten ausgegebenen Blocks.
        letzte_dac = 0.09 + 29 * 64 / loop.samplerate
        type(loop._stream).time = PropertyMock(return_value=letzte_dac)

        rueckstand = loop.captured_seconds - loop.audible_position()
        # Delay plus der Block, der noch nicht ausgegeben wurde.
        assert loop.delay_seconds <= rueckstand <= loop.delay_seconds + 64 / 1000 + 1e-6

    def test_faellt_bei_unbrauchbarer_dac_zeit_zurueck(self, loop):
        _rampe_einspeisen(loop, bloecke=30, dac_start=0.09)
        type(loop._stream).time = PropertyMock(return_value=999999.0)  # Unsinn

        erwartet = (loop.captured_seconds - loop.delay_seconds - loop.output_latency)
        assert loop.audible_position() == pytest.approx(erwartet)

    def test_ohne_anker_faellt_zurueck(self, loop):
        erwartet = -loop.delay_seconds - loop.output_latency
        assert loop.audible_position() == pytest.approx(erwartet)


class TestCallback:
    def test_zaehlt_xruns_statt_eine_liste_wachsen_zu_lassen(self, loop):
        assert loop.xruns == 0
        assert loop.last_status is None

        indata = np.zeros((64, 2), dtype=np.float32)
        for _ in range(5):
            loop._callback(indata, np.zeros((64, 2), np.float32), 64,
                           Zeit(0.0), "input overflow")
        assert loop.xruns == 5
        assert loop.last_status == "input overflow"
        assert not hasattr(loop, "status_messages")   # keine wachsende Liste mehr

    def test_gibt_verzoegertes_signal_aus(self, loop):
        # Der Ringpuffer ist 500 Frames lang: die ersten 500 ausgegebenen Frames
        # sind Stille, danach kommt das Eingangssignal wieder heraus.
        ausgaben = []
        position = 0
        for _ in range(16):                       # 1024 Frames
            indata = np.tile(
                np.arange(position, position + 64, dtype=np.float32)[:, None], (1, 2))
            outdata = np.zeros((64, 2), dtype=np.float32)
            loop._callback(indata, outdata, 64, Zeit(0.0), None)
            ausgaben.append(outdata[:, 0].copy())
            position += 64

        ausgabe = np.concatenate(ausgaben)
        assert np.all(ausgabe[:500] == 0)                     # Ringpuffer noch leer
        assert np.array_equal(ausgabe[500:1024],
                              np.arange(0, 524, dtype=np.float32))  # um 500 verzoegert


class TestBlockgroesse:
    def test_uebergrosser_callbackblock_beim_stummschalten_crasht_nicht(self, loop):
        # Selbst wenn ein Treiber mehr Frames liefert als beim Streambau
        # angekuendigt, darf der Fade nicht an den vorbereiteten Arbeitsarrays
        # scheitern. Lieber ein sauber behandelter Block als ein Callback-Crash.
        loop.toggle_mute()
        frames = 96                          # groesser als das konfigurierte 64
        indata = np.ones((frames, 2), dtype=np.float32)
        outdata = np.ones((frames, 2), dtype=np.float32)
        loop._callback(indata, outdata, frames, Zeit(0.0), None)
        assert outdata.shape == (frames, 2)
        assert np.all(np.isfinite(outdata))


class TestKontrollgitarre:
    @staticmethod
    def _stille(loop, bloecke=16):
        chunks = []
        for i in range(bloecke):
            out = np.zeros((64, 2), dtype=np.float32)
            loop._callback(np.zeros_like(out), out, 64, Zeit(i * .064), None)
            chunks.append(out.copy())
        return np.concatenate(chunks)

    def test_ist_standardmaessig_aus(self, loop):
        loop.set_control_timeline([(0.0, "Am")])
        assert not np.any(self._stille(loop))

    def test_erklingt_exakt_auf_der_verzoegerten_streamposition(self, loop):
        loop.set_control_timeline([(0.0, "Am")])
        assert loop.toggle_control_guitar() is True
        audio = self._stille(loop)
        assert not np.any(audio[:500])           # Ringdelay noch nicht vorbei
        assert np.any(audio[500:])               # Onset bei Streamposition null

    def test_timeline_snapshot_nimmt_zukuenftigen_fehler_zurueck(self, loop):
        loop.set_control_timeline([(0.0, "A")])
        loop.set_control_timeline([])             # Interpreter revidiert Segment
        loop.toggle_control_guitar()
        assert not np.any(self._stille(loop))

    def test_senkt_original_nur_im_kontrollmodus_ab(self, loop):
        from jampilot.control_guitar import PLAYBACK_GAIN

        # Ring direkt mit einem konstanten Originalsignal fuellen, ohne einen
        # Gitarrenanschlag in die Timeline zu legen.
        loop._ring[:] = 1.0
        normal = np.zeros((64, 2), dtype=np.float32)
        loop._callback(np.zeros_like(normal), normal, 64, Zeit(0.0), None)
        assert np.allclose(normal, 1.0)

        loop._ring[:] = 1.0
        loop.toggle_control_guitar()
        diagnose = np.zeros((64, 2), dtype=np.float32)
        loop._callback(np.zeros_like(diagnose), diagnose, 64, Zeit(.064), None)
        assert np.allclose(diagnose, PLAYBACK_GAIN)


class TestStumm:
    """STUMM, nicht ANGEHALTEN - und der Unterschied ist der ganze Punkt.

    Wuerde der Schalter den Ringpuffer einfrieren, waere er in Wahrheit
    "Verzoegerung vergroessern": Man kaeme mit jeder stummen Sekunde eine Sekunde
    weiter hinter die Quelle, und der Vorlauf - der Sinn des Programms - waere
    hinueber. Stattdessen laeuft alles weiter, nur der Lautsprecher schweigt.
    """

    @staticmethod
    def _block(loop, position, blocksize=64, wert=None):
        indata = (np.full((blocksize, 2), wert, dtype=np.float32) if wert is not None
                  else np.tile(np.arange(position, position + blocksize,
                                         dtype=np.float32)[:, None], (1, 2)))
        outdata = np.zeros((blocksize, 2), dtype=np.float32)
        loop._callback(indata, outdata, blocksize, Zeit(position / loop.samplerate), None)
        return outdata[:, 0].copy()

    def test_stumm_nach_dem_ausblenden(self, loop):
        _rampe_einspeisen(loop, 16)               # Ringpuffer fuellen
        assert loop.toggle_mute() is True
        self._block(loop, 1024)                   # dieser Block blendet aus
        stille = self._block(loop, 1088)
        assert np.all(stille == 0.0)

    def test_aufheben_bringt_den_ton_zurueck(self, loop):
        _rampe_einspeisen(loop, 16)
        loop.toggle_mute()
        self._block(loop, 1024)
        assert loop.toggle_mute() is False       # wieder laut
        self._block(loop, 1088)                   # blendet ein
        wieder_da = self._block(loop, 1152)
        assert np.any(wieder_da != 0.0)

    def test_der_puffer_laeuft_stumm_weiter(self, loop):
        """Die Verzoegerung darf durch das Stummschalten NICHT wachsen."""
        _rampe_einspeisen(loop, 16)
        vorher = loop.captured_frames
        loop.toggle_mute()
        for i in range(8):
            self._block(loop, 1024 + i * 64)
        # Der Eingang wurde weiter eingelesen - Analyse und Zeitrechnung laufen.
        assert loop.captured_frames == vorher + 8 * 64
        # Und das stumme Material liegt im Analysepuffer, wie immer.
        assert loop.audio_ending_at(loop.captured_frames, 64) is not None

    def test_blendet_aus_statt_zu_springen(self, loop):
        """Ein harter Schnitt auf Null ist ein Sprung im Signal - das knackt."""
        _rampe_einspeisen(loop, 8)
        # Gleichsignal: jeder Sprung in der Ausgabe kommt dann vom Schalter,
        # nicht vom Eingang.
        for i in range(10):
            self._block(loop, 512 + i * 64, wert=1.0)
        loop.toggle_mute()
        ausblendung = self._block(loop, 1152, wert=1.0)

        assert ausblendung[0] > 0.9 and ausblendung[-1] < 0.1   # wirklich geblendet
        spruenge = np.abs(np.diff(ausblendung))
        assert spruenge.max() < 0.1, f"Sprung von {spruenge.max():.2f} - das knackt"
        # Monoton fallend: keine Zacken, die man als Zwitschern hoeren wuerde.
        assert np.all(np.diff(ausblendung) <= 1e-6)


class TestCountdown:
    """Der Einzaehler in die Anfangsstille: 3 - 2 - 1, dann Musik."""

    def _loop(self, delay, samplerate=1000, blocksize=50):
        with patch("sounddevice.Stream"):
            loop = DelayedLoopback(None, None, delay_seconds=delay,
                                   samplerate=samplerate, blocksize=blocksize,
                                   channels=2, analysis_seconds=1.0)
        loop._stream.latency = (0.05, 0.09)
        return loop

    def _ausgabe(self, loop, frames=None, eingang=None, blocksize=50):
        """Eingang einspeisen (Rampe oder gegebenes Signal), Ausgabe sammeln."""
        if eingang is None:
            eingang = np.arange(frames, dtype=np.float32)
        out = []
        for start in range(0, len(eingang) - blocksize + 1, blocksize):
            indata = np.tile(eingang[start : start + blocksize, None], (1, 2))
            outdata = np.zeros((blocksize, 2), dtype=np.float32)
            loop._callback(indata, outdata, blocksize, Zeit(0.0), None)
            out.append(outdata[:, 0].copy())
        return np.concatenate(out)

    def test_toene_liegen_auf_den_restsekunden(self):
        loop = self._loop(delay=4.0)
        ausgabe = self._ausgabe(loop, 4000)
        for start in (1000, 2000, 3000):        # -3s, -2s, -1s vor der Musik
            assert np.abs(ausgabe[start : start + 80]).max() > 0.1, start
        for still in (500, 1500, 2500, 3500):   # dazwischen bleibt Stille
            assert np.abs(ausgabe[still : still + 100]).max() == 0.0, still

    def test_der_letzte_ton_ist_betont(self):
        loop = self._loop(delay=4.0)
        ausgabe = self._ausgabe(loop, 4000)
        assert (np.abs(ausgabe[3000:3200]).max()
                > np.abs(ausgabe[1000:1200]).max())

    def test_endet_exakt_mit_der_fuellphase(self):
        """Ab der ersten Musik ist die Ausgabe das reine verzoegerte Signal."""
        loop = self._loop(delay=2.0)
        ausgabe = self._ausgabe(loop, 3000)
        assert np.array_equal(ausgabe[2000:3000],
                              np.arange(0, 1000, dtype=np.float32))

    def test_unter_einer_sekunde_delay_bleibt_es_still(self):
        loop = self._loop(delay=0.5)
        ausgabe = self._ausgabe(loop, 500)
        assert np.abs(ausgabe).max() == 0.0

    def test_zaehlt_auch_eine_spaeter_gestartete_quelle_ein(self):
        """Der eigentliche Fall: JamPilot laeuft, dann startet die Quelle."""
        loop = self._loop(delay=2.0)
        eingang = np.concatenate([np.zeros(3000, dtype=np.float32),
                                  np.full(2000, 0.5, dtype=np.float32)])
        ausgabe = self._ausgabe(loop, eingang=eingang)
        # Quelle startet bei 3000, hoerbar ab 5000 - der 1er-Ton eine Sekunde
        # davor, dazwischen Stille, dann kommt die Musik unverfaelscht.
        assert np.abs(ausgabe[4000:4140]).max() > 0.1
        assert np.abs(ausgabe[4200:5000]).max() == 0.0
        assert np.array_equal(ausgabe[4990:5000], np.zeros(10, dtype=np.float32))
        assert np.all(ausgabe[5000:5100] == 0.5)

    def test_eine_kurze_luecke_zaehlt_nicht_ein(self):
        """Break im Song / Titelluecke: kuerzer als der Puffer -> keine Toene.

        Waehrend so einer Luecke spielt der Ausgang noch altes Material;
        Einzaehlen waere falsch und wuerde in die Musik hineinpiepsen."""
        loop = self._loop(delay=2.0)
        eingang = np.concatenate([np.full(2000, 0.5, dtype=np.float32),
                                  np.zeros(1000, dtype=np.float32),
                                  np.full(2000, 0.5, dtype=np.float32)])
        ausgabe = self._ausgabe(loop, eingang=eingang)
        # Die Luecke erscheint am Ausgang bei [4000, 5000) - und bleibt leer
        # (ein falscher 1er-Ton laege genau dort, bei 4000).
        assert np.abs(ausgabe[4000:5000]).max() == 0.0


class TestMitschnittAngehaengt:
    """Die Naht zwischen Verzoegerungsstufe und Mitschnitt (Record-Modus).

    Hier wird nur geprueft, WO der Mitschnitt sitzt und WAS er der Stufe
    kostet - was er kann, steht in test_record_buffer.py. Die Lage ist die
    eigentliche Entwurfsentscheidung: hinter allem, was dem Signal noch
    beigemischt wird, und VOR der Stummschaltung.
    """

    def _mitschnitt(self, loop, minuten=0.05, an=True):
        from jampilot.record_buffer import RecordBuffer

        puffer = RecordBuffer(loop.samplerate, loop.channels, minuten,
                              blocksize=64)
        loop.attach_record(puffer)
        if an:
            puffer.start_record()
        return puffer

    def test_ohne_mitschnitt_bleibt_alles_wie_vorher(self, loop):
        assert loop.record_offset_seconds == 0.0
        assert loop.record_capacity_seconds == 0.0
        assert loop.recording is False and loop.record_paused is False
        _rampe_einspeisen(loop, 16)
        assert loop.heard_position() == loop.audible_position()

    def test_eingehaengt_aber_aus_ist_die_uhr_dieselbe(self, loop):
        # Die Zusage des Modus: R nie gedrueckt (oder wieder aus) heisst
        # buchstaeblich dieselbe Funktion, nicht nur dieselbe Zahl.
        self._mitschnitt(loop, an=False)
        _rampe_einspeisen(loop, 20)
        assert loop.heard_position() == loop.audible_position()
        assert loop.recording is False

    def test_der_mitschnitt_aendert_die_verzoegerung_nicht(self, loop):
        """Der Kern der Trennung: Die Zeitbasis der ANALYSE bleibt konstant."""
        puffer = self._mitschnitt(loop)
        _rampe_einspeisen(loop, 16)
        vorher = loop.delay_seconds
        puffer.toggle_pause()
        for _ in range(20):
            _rampe_einspeisen(loop, 1)
        assert loop.delay_seconds == vorher
        assert loop.delay_frames == len(loop._ring)
        assert loop.record_offset_seconds > 0.0 and loop.record_paused

    def test_stumm_geschaltetes_wird_nicht_als_stille_mitgeschnitten(self, loop):
        """Wer stumm schaltet und spaeter zurueckspringt, will die Musik."""
        puffer = self._mitschnitt(loop)
        _rampe_einspeisen(loop, 16)
        loop.toggle_mute()
        for _ in range(12):
            _rampe_einspeisen(loop, 1)
        assert not np.any(_letzter_ausgang(loop))  # der Lautsprecher schweigt
        loop.toggle_mute()
        aufgezeichnet = np.zeros((64, 2), dtype=np.float32)
        puffer._lies(aufgezeichnet, 0, 64)
        assert np.any(aufgezeichnet)

    def test_die_hoerbare_stelle_steht_waehrend_der_pause(self, loop):
        """`heard_position()` friert ein, ohne dass eine zweite Uhr angehalten wird."""
        puffer = self._mitschnitt(loop, minuten=0.5)
        _rampe_einspeisen(loop, 40)
        puffer.toggle_pause()
        _rampe_einspeisen(loop, 1)
        stand = loop.heard_position()
        for _ in range(30):
            _rampe_einspeisen(loop, 1)
            assert loop.heard_position() == pytest.approx(stand, abs=1e-6)
        puffer.toggle_pause()
        for _ in range(5):
            _rampe_einspeisen(loop, 1)
        assert loop.heard_position() > stand

    def test_pausiert_steht_die_hoerbare_stelle_EXAKT(self, loop):
        """Kein Saegezahn im Stillstand - mitten im Block abgetastet.

        `audible_position()` laeuft zwischen zwei Callbacks kontinuierlich
        weiter, der Versatz waechst ruckweise. Ihre Differenz saegt mit einer
        Blockdauer Amplitude; das Laufband zittert. `heard_position()` rechnet
        pausiert darum aus den Frame-Zaehlern. Ohne das Abtasten ZWISCHEN den
        Callbacks saehe der Test nichts - er traefe immer dieselbe Phase.
        """
        puffer = self._mitschnitt(loop, minuten=0.5)
        _rampe_einspeisen(loop, 30)
        puffer.toggle_pause()
        werte = []
        for _ in range(10):
            _rampe_einspeisen(loop, 1)
            for teilschritt in (0.2, 0.5, 0.9):
                loop._stream.time = (loop.captured_frames
                                     + teilschritt * 64) / loop.samplerate
                werte.append(loop.heard_position())
        assert max(werte) - min(werte) == pytest.approx(0.0, abs=1e-9)

    def test_zurueckspringen_zieht_die_hoerbare_stelle_zurueck(self, loop):
        puffer = self._mitschnitt(loop, minuten=0.5)
        _rampe_einspeisen(loop, 40)
        vorher = loop.heard_position()
        puffer.seek(-0.5)
        assert loop.heard_position() == pytest.approx(vorher - 0.5, abs=1e-6)
        puffer.to_now()
        assert loop.heard_position() == pytest.approx(vorher, abs=1e-6)

    def test_die_uhr_des_mitschnitts_ist_die_der_stufe(self, loop):
        # Kein Angleichen, kein Versatz: `process` bekommt `_frames_seen` mit.
        puffer = self._mitschnitt(loop, an=False)
        _rampe_einspeisen(loop, 25)
        puffer.start_record()
        _rampe_einspeisen(loop, 3)
        assert puffer.play_position_frames == loop.captured_frames


def _letzter_ausgang(loop):
    """Einen einzelnen Block durchschicken und zurueckgeben."""
    indata = np.ones((64, 2), dtype=np.float32)
    outdata = np.zeros((64, 2), dtype=np.float32)
    loop._callback(indata, outdata, 64, Zeit(0.0), None)
    return outdata

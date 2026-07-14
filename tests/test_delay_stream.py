"""Ringpuffer und Ausgabeuhr - die Zeitbasis der gesamten Anzeige."""

from unittest.mock import PropertyMock, patch

import numpy as np
import pytest

from chordify.delay_stream import DelayedLoopback


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

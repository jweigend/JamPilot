"""Huellkurve unter dem Laufband (envelope.py)."""

import numpy as np

from jampilot.envelope import Envelope, block_rms, lowpass

SR = 48000
HOP = 12000          # 0,25 s


def _ton(freq, sekunden, amp=0.5):
    t = np.arange(int(sekunden * SR)) / SR
    return amp * np.sin(2 * np.pi * freq * t)


class TestBloecke:
    def test_blockraster_aus_hop(self):
        env = Envelope(SR, HOP)
        assert env.block_frames == 600                 # 12,5 ms
        assert abs(env.block_seconds - 0.0125) < 1e-9

    def test_block_rms_laesst_rest_weg(self):
        assert len(block_rms(np.ones(2500), 1000)) == 2
        assert np.allclose(block_rms(np.ones(2000), 1000), 1.0)

    def test_tiefpass_trennt_bass_von_hoehen(self):
        sig = _ton(60, 1.0) + _ton(2000, 1.0)
        tief = lowpass(sig, SR)[SR // 2:]          # Einschwingen weglassen
        # Der 60-Hz-Anteil bleibt (RMS 0,5/sqrt2, Butterworth-Flanke bei 30 Hz
        # kostet ein wenig), die 2 kHz sind weg (-36 dB).
        assert abs(np.sqrt(np.mean(tief ** 2)) - 0.5 / np.sqrt(2)) < 0.05
        assert np.sqrt(np.mean(lowpass(_ton(2000, 1.0), SR) ** 2)) < 0.01


class TestAufbau:
    def test_bass_reagiert_nur_auf_tiefes(self):
        # 1 s Stille, 1 s 2 kHz, 1 s 60 Hz
        audio = np.concatenate([np.zeros(SR), _ton(2000, 1.0), _ton(60, 1.0)])
        env = Envelope(SR, HOP)
        env.add(audio, len(audio))
        full = np.array(env.full)
        bass = np.array(env.bass)
        assert len(full) == len(bass) == 3 * 80
        # Die mittleren Bloecke (nur Hoehen) sind im Mix laut, im Tiefband leise.
        assert full[100] > 0.3 and bass[100] < 0.02
        # Die hinteren (nur Bass) in beiden laut.
        assert full[200] > 0.3 and bass[200] > 0.3
        # Stille ist still.
        assert full[10] == 0.0 and bass[10] == 0.0

    def test_hopweise_gleich_wie_am_stueck(self):
        rng = np.random.default_rng(1)
        audio = rng.standard_normal(4 * SR) * 0.1 + _ton(55, 4.0)
        ganz = Envelope(SR, HOP)
        ganz.add(audio, len(audio))
        stueck = Envelope(SR, HOP)
        fenster = 2 * SR
        for ende in range(fenster, len(audio) + 1, HOP):
            stueck.add(audio[ende - fenster: ende], ende)
        assert len(stueck.full) == len(ganz.full)
        assert np.allclose(stueck.full, ganz.full, rtol=1e-6)
        # IIR mit Zustand ueber die Hops: hopweise IST am Stueck.
        assert np.allclose(stueck.bass, ganz.bass, rtol=1e-6)

    def test_uebersprungener_hop_ohne_luecke(self):
        audio = _ton(80, 3.0)
        env = Envelope(SR, HOP)
        env.add(audio[: SR], SR)
        env.add(audio[: 3 * SR], 3 * SR)          # zwei Hops auf einmal
        assert len(env.full) == 3 * 80
        assert env.end_seconds == 3.0

    def test_audio_aus_dem_puffer_wird_mit_nullen_gefuellt(self):
        env = Envelope(SR, HOP)
        env.add(_ton(80, 1.0), SR)
        # Naechstes Fenster beginnt erst bei 2 s - 1 s fehlt.
        env.add(_ton(80, 1.0), 3 * SR)
        assert len(env.full) == 3 * 80
        assert all(v == 0.0 for v in env.full[80:160])
        assert env.full[200] > 0.3

    def test_erstes_fenster_beginnt_auf_blockraster(self):
        env = Envelope(SR, HOP)
        env.add(np.zeros(1000), 1300)            # Audio ab Frame 300
        assert env._start == 600                 # naechste Rasterlinie
        assert env.end_seconds == 1200 / SR


class TestLesen:
    def _voll(self):
        env = Envelope(SR, HOP)
        env.add(_ton(80, 10.0), 10 * SR)
        return env

    def test_fenster_schneidet_und_traegt_achse(self):
        env = self._voll()
        w = env.window(2.0, 3.0)
        assert w["t0"] == 2.0 and w["dt"] == 0.0125
        assert len(w["full"]) == len(w["bass"]) == 81
        assert env.window(20.0, 25.0) is None
        assert Envelope(SR, HOP).window(0.0, 1.0) is None

    def test_prune_haelt_rueckhalt(self):
        env = self._voll()
        env.prune(heard_pos=8.0)                 # Standard: 2 s zurueck
        assert env.start_seconds == 6.0
        assert env.window(5.0, 5.5) is None
        assert len(env.window(6.0, 6.5)["full"]) == 41
        env.prune(heard_pos=9.0, rueckhalt=30.0)  # Mitschnitt: nichts weg
        assert env.start_seconds == 6.0

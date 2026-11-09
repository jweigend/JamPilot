"""Bass-Stem fuer die Huellkurve (stems.py) und sein Zusammenspiel mit
envelope.Envelope."""

import os
import threading
import time

import numpy as np
import pytest

from jampilot import stems as S
from jampilot.envelope import Envelope

SR = 48000
HOP = 12000          # 0,25 s


def warte_bis(bedingung, sekunden=5.0):
    ende = time.monotonic() + sekunden
    while not bedingung():
        assert time.monotonic() < ende, "Timeout"
        time.sleep(0.01)


class FakeModel:
    """Trennt nichts: gibt den Eingang halbiert zurueck - so laesst sich
    pruefen, dass Kern und Kontext richtig geschnitten werden."""
    provider = "FakeExecutionProvider"

    def __init__(self):
        self.calls = []

    def separate(self, audio, samplerate):
        self.calls.append(len(audio))
        return np.asarray(audio, dtype=np.float32) * 0.5


class TestAssemble:
    def test_ueberlappende_stuecke_werden_ein_puffer(self):
        a = np.arange(10, dtype=np.float32)
        start, out = S.assemble([(100, a[:6]), (103, a[3:])])
        assert start == 100 and len(out) == 10
        assert np.array_equal(out, a)

    def test_luecke_bleibt_null(self):
        start, out = S.assemble([(0, np.ones(4, np.float32)), (8, np.ones(2, np.float32))])
        assert start == 0 and len(out) == 10
        assert list(out) == [1, 1, 1, 1, 0, 0, 0, 0, 1, 1]


class TestWorker:
    def test_kern_kommt_geschnitten_zurueck(self):
        w = S.BassStemWorker(model_factory=FakeModel)
        try:
            warte_bis(lambda: w.ready)
            assert w.provider == "FakeExecutionProvider"
            audio = np.arange(1000, dtype=np.float32)
            # Audio ab Frame 5000, Kern [5300, 5800)
            assert w.submit(audio, SR, 5000, 5300, 5800)
            warte_bis(lambda: w.runs == 1)
            [(bass, core_end)] = w.poll()
            assert core_end == 5800 and len(bass) == 500
            assert np.allclose(bass, audio[300:800] * 0.5)
        finally:
            w.stop()

    def test_rueckstau_wird_zu_einem_lauf(self):
        block = threading.Event()
        fakes = []

        class Langsam(FakeModel):
            def __init__(self):
                super().__init__()
                fakes.append(self)

            def separate(self, audio, samplerate):
                block.wait()
                return super().separate(audio, samplerate)

        w = S.BassStemWorker(model_factory=Langsam)
        try:
            warte_bis(lambda: w.ready)
            hop = np.ones(300, np.float32)
            w.submit(hop, SR, 0, 100, 200)           # der Worker holt ihn sofort
            warte_bis(lambda: w.pending() == 0)
            w.submit(hop, SR, 100, 200, 300)         # zwei weitere stauen sich
            w.submit(hop, SR, 200, 300, 400)
            block.set()
            warte_bis(lambda: w.runs == 2)
            ergebnisse = w.poll()
            assert [e[1] for e in ergebnisse] == [200, 400]
            assert len(ergebnisse[1][0]) == 200      # Kern [200, 400) in EINEM Lauf
            assert fakes[0].calls == [300, 400]      # zweiter Lauf: Audio [100, 500)
        finally:
            block.set()
            w.stop()

    def test_zu_viel_rueckstau_opfert_das_aelteste(self):
        block = threading.Event()

        class Langsam(FakeModel):
            def separate(self, audio, samplerate):
                block.wait()
                return super().separate(audio, samplerate)

        w = S.BassStemWorker(model_factory=Langsam)
        try:
            warte_bis(lambda: w.ready)
            hop = np.ones(1, np.float32)
            w.submit(hop, 100, 0, 0, 1)
            warte_bis(lambda: w.pending() == 0)
            for k in range(1, 8):                    # 7 Kerne a 1 s bei sr 100 -> > MAX_BACKLOG
                w.submit(np.ones(100, np.float32), 100, k * 100, k * 100, (k + 1) * 100)
            assert w.dropped >= 1
            assert w.pending() <= int(S.MAX_BACKLOG) + 1
        finally:
            block.set()
            w.stop()

    def test_kaputtes_modell_meldet_sich(self):
        def kaputt():
            raise RuntimeError("no such file")
        w = S.BassStemWorker(model_factory=kaputt)
        warte_bis(lambda: w.error is not None)
        assert "no such file" in w.error
        assert not w.submit(np.zeros(10, np.float32), SR, 0, 0, 10)
        w.stop()


class TestEnvelopeMitStem:
    def test_stem_kurve_laeuft_hinterher_und_holt_auf(self):
        env = Envelope(SR, HOP, separated=True)
        audio = np.ones(2 * SR)
        env.add(audio, 2 * SR)
        assert len(env.full) == 160 and env.bass == []       # Bass kommt separat
        env.add_bass(np.full(HOP, 0.5), SR + HOP)             # Kern [1.0, 1.25) s
        # Davor Nullen (Luecke), dann der Kern; der Bass bleibt kuerzer als der Mix.
        assert len(env.bass) == 100
        assert all(v == 0.0 for v in env.bass[:80]) and all(v == 0.5 for v in env.bass[80:])
        assert env.bass_end_seconds == 1.25 and env.end_seconds == 2.0
        env.add_bass(np.full(HOP, 0.5), SR + 2 * HOP)         # naechster Hop schliesst an
        assert len(env.bass) == 120

    def test_fenster_traegt_kuerzere_bass_kurve(self):
        env = Envelope(SR, HOP, separated=True)
        env.add(np.ones(2 * SR), 2 * SR)
        env.add_bass(np.ones(SR), SR)
        w = env.window(0.0, 2.0)
        assert len(w["full"]) == 160 and len(w["bass"]) == 80

    def test_prune_haelt_beide_kurven_auf_einer_achse(self):
        env = Envelope(SR, HOP, separated=True)
        env.add(np.ones(10 * SR), 10 * SR)
        env.add_bass(np.ones(3 * SR), 3 * SR)                 # Bass nur bis 3 s
        env.prune(heard_pos=8.0)                              # alles vor 6 s weg
        assert env.start_seconds == 6.0 and env.bass == []
        env.add_bass(np.full(SR, 0.7), 9 * SR)                # [8, 9) s
        # Nullen fuer [6, 8), dann die Werte - Block i liegt bei 6 s + i*12,5 ms.
        assert len(env.bass) == 240
        assert env.bass[159] == 0.0 and env.bass[160] == pytest.approx(0.7)
        assert env.window(8.0, 8.1)["bass"][0] == pytest.approx(0.7)

    def test_ohne_trennung_bandpass_wie_zuvor(self):
        env = Envelope(SR, HOP)
        t = np.arange(SR) / SR
        env.add(0.5 * np.sin(2 * np.pi * 60 * t), SR)
        assert len(env.bass) == 80 and env.bass[-1] > 0.3


@pytest.mark.skipif(not (S.onnxruntime_available() and os.path.exists(S.MODEL_PATH)),
                    reason="kein onnxruntime oder Modell")
class TestModell:
    def test_trennt_gehaltenen_bass_von_kicks(self):
        sr = 44100
        t = np.arange(int(2.0 * sr)) / sr
        bass = 0.3 * np.sin(2 * np.pi * 55 * t) * (1 + 0.3 * np.sin(2 * np.pi * 110 * t))
        kick = np.zeros_like(t)
        for k0 in np.arange(0.1, 2.0, 0.5):
            i = int(k0 * sr); n = int(0.08 * sr)
            kick[i:i + n] += 0.8 * np.sin(2 * np.pi * 60 * np.arange(n) / sr) \
                * np.exp(-np.arange(n) / (0.02 * sr))
        m = S.BassStemModel()
        out_bass = m.separate(bass, sr)
        out_kick = m.separate(kick, sr)
        assert len(out_bass) == len(bass)
        rms = lambda y: float(np.sqrt(np.mean(np.asarray(y) ** 2)))
        # Der gehaltene Bass bleibt weitgehend, die Kicks verlieren deutlich mehr.
        assert rms(out_bass) / rms(bass) > 0.5
        assert rms(out_kick) / rms(kick) < 0.5 * rms(out_bass) / rms(bass)

    def test_andere_rate_gleiche_laenge(self):
        m = S.BassStemModel()
        y = np.random.default_rng(0).standard_normal(int(1.75 * 48000)).astype(np.float32) * 0.1
        assert len(m.separate(y, 48000)) == len(y)

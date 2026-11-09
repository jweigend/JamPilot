"""Open-Unmix (Target "bass") nach ONNX exportieren - Reproduktion von
jampilot/data/umxhq_bass_int8.onnx (docs/exploration/bass-stem-huellkurve.md).

Braucht eine eigene Umgebung mit torch (CPU), openunmix, onnx, onnxruntime:
    python -m venv /tmp/umxenv && /tmp/umxenv/bin/pip install \
        --index-url https://download.pytorch.org/whl/cpu torch && \
        /tmp/umxenv/bin/pip install openunmix onnx onnxruntime onnxscript
    /tmp/umxenv/bin/python tests/reference/export_umx_bass.py [zielordner]

Schreibt umx_umxhq_bass.onnx und umx_umxl_bass.onnx (fp32, dynamische
Frame-Achse) sowie umx_umxhq_int8_bass.onnx (dynamisch quantisiert) in den
Zielordner (Default: aktuelles Verzeichnis) und prueft ORT gegen torch.
UMX-L ist nur zum Vergleich: seine Gewichte sind CC BY-NC-SA, UMX-HQ MIT.
"""
import sys, os
ZIEL = sys.argv[1] if len(sys.argv) > 1 else "."
import time, warnings
warnings.filterwarnings("ignore")
import numpy as np, torch, onnx, onnxruntime as ort
import torch.nn.functional as F
import openunmix

class Dyn(torch.nn.Module):
    """OpenUnmix.forward mit dynamischer Framezahl (x.shape statt x.data.shape,
    reshape mit -1), sonst identisch."""
    def __init__(self, m): super().__init__(); self.m = m
    def forward(self, x):
        m = self.m
        x = x.permute(3, 0, 1, 2)
        nb_frames, nb_samples = x.shape[0], x.shape[1]
        mix = x
        x = x[..., : m.nb_bins]
        x = (x + m.input_mean) * m.input_scale
        x = m.fc1(x.reshape(-1, 2 * m.nb_bins))
        x = m.bn1(x)
        x = torch.tanh(x.reshape(nb_frames, nb_samples, m.hidden_size))
        lstm_out = m.lstm(x)
        x = torch.cat([x, lstm_out[0]], -1)
        x = F.relu(m.bn2(m.fc2(x.reshape(-1, x.shape[-1]))))
        x = m.bn3(m.fc3(x))
        x = x.reshape(nb_frames, nb_samples, 2, m.nb_output_bins)
        x = x * m.output_scale + m.output_mean
        x = F.relu(x) * mix
        return x.permute(1, 2, 3, 0)

torch.set_num_threads(4)
for name, fn in [("umxhq", openunmix.umxhq_spec), ("umxl", openunmix.umxl_spec)]:
    m = fn(targets=["bass"])["bass"].eval()
    d = Dyn(m).eval()
    x = torch.rand(1, 2, 2049, 259) * 0.1
    path = os.path.join(ZIEL, f"umx_{name}_bass.onnx")
    with torch.no_grad():
        ref = m(x); ref2 = d(x)
        assert torch.allclose(ref, ref2, atol=1e-5), "Wrapper weicht ab"
        torch.onnx.export(d, x, path, input_names=["mag"], output_names=["bass_mag"],
                          dynamic_axes={"mag": {3: "frames"}, "bass_mag": {3: "frames"}},
                          opset_version=17, dynamo=False)
    onnx.checker.check_model(onnx.load(path))
    so = ort.SessionOptions(); so.intra_op_num_threads = 4
    s = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
    y = s.run(None, {"mag": x.numpy()})[0]
    err = float(np.max(np.abs(y - ref.numpy())) / (np.max(np.abs(ref.numpy())) + 1e-9))
    x2 = (torch.rand(1, 2, 2049, 300) * 0.1).numpy()
    y2 = s.run(None, {"mag": x2})[0]; assert y2.shape[-1] == 300
    t = time.perf_counter(); n = 5
    for _ in range(n): s.run(None, {"mag": x.numpy()})
    dt = (time.perf_counter() - t) / n
    so1 = ort.SessionOptions(); so1.intra_op_num_threads = 1
    s1 = ort.InferenceSession(path, so1, providers=["CPUExecutionProvider"])
    s1.run(None, {"mag": x.numpy()})
    t = time.perf_counter()
    for _ in range(3): s1.run(None, {"mag": x.numpy()})
    dt1 = (time.perf_counter() - t) / 3
    print(f"{name}: {os.path.getsize(path)/1e6:.1f} MB, {dt*1000:.0f} ms je 6-s-Block (4 Threads), {dt1*1000:.0f} ms (1 Thread), rel. Fehler ORT/torch {err:.1e}", flush=True)

# int8: dynamische Quantisierung der Gewichte (MatMul/LSTM), 9 MB statt 36.
from onnxruntime.quantization import quantize_dynamic, QuantType
quantize_dynamic(os.path.join(ZIEL, "umx_umxhq_bass.onnx"),
                 os.path.join(ZIEL, "umx_umxhq_int8_bass.onnx"), weight_type=QuantType.QInt8)
print("int8:", os.path.getsize(os.path.join(ZIEL, "umx_umxhq_int8_bass.onnx")) / 1e6, "MB")

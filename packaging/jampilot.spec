# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spec: JamPilot als EINE ausfuehrbare Datei.

    pyinstaller packaging/jampilot.spec --noconfirm     ->  dist/jampilot

GEBAUT WIRD IMMER AUF DEM ZIELSYSTEM. PyInstaller kann nicht cross-kompilieren:
Es sammelt die nativen Bibliotheken ein, die auf DIESER Maschine liegen
(libportaudio, libsndfile, libllvmlite, die BLAS von numpy/scipy). Ein
Linux-Build auf einem Mac gibt es nicht. Also: Linux-Binary auf Linux, macOS
getrennt fuer arm64 und x86_64 - siehe .github/workflows/build.yml.

Was das Bundle NICHT mitbringen kann, weil es Systemteile sind:
  * macOS: BlackHole (Audiotreiber, eigener Installer)
  * Linux: pactl / PipeWire-PulseAudio (ruft routing.py als externes Programm)
Beides bleibt eine Voraussetzung auf dem Zielrechner, siehe README.
"""

import os

from PyInstaller.utils.hooks import collect_all

projekt = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))  # noqa: F821

datas, binaries, hiddenimports = [], [], []

# Diese Pakete laden ihre Submodule zur Laufzeit (lazy_loader) oder bringen
# native Bibliotheken mit - beides sieht der statische Import-Scanner nicht:
#   soundfile   -> libsndfile
#   sounddevice -> libportaudio      (ohne das gibt es keine Audiogeraete)
#   llvmlite    -> libllvmlite       (numbas JIT, ~170 MB, unvermeidbar)
for paket in ("librosa", "numba", "llvmlite", "soundfile", "sounddevice",
              "soxr", "lazy_loader", "audioread", "msgpack"):
    d, b, h = collect_all(paket)
    datas += d
    binaries += b
    hiddenimports += h

excludes = [
    # Nur, was NACHWEISLICH nicht importiert wird. Jeder weitere Ausschluss
    # wurde ausprobiert und endete im Absturz: sklearn, pooch, joblib,
    # scipy.sparse.csgraph und narwhals zieht librosa auf unserem Pfad selbst
    # herein - auch wenn wir keine einzige ihrer Funktionen aufrufen.
    #
    # Der Test dafuer ist `dist/jampilot selftest`: Er zieht librosa, numba und
    # beide CQTs durch und faellt sofort ueber jedes fehlende Modul - ohne dass
    # eine Soundkarte noetig waere. Wer hier Megabytes sparen will, muss ihn
    # nach JEDER Aenderung laufen lassen.
    "matplotlib", "IPython", "tkinter", "pytest", "_pytest",
    "PIL", "Pillow",     # qrcode laeuft ueber die SVG-Fabrik, nicht ueber Pillow
]

a = Analysis(
    [os.path.join(projekt, "packaging", "entry.py")],
    pathex=[projekt],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

# onefile: alles in EINE Datei. Der Preis steht im README - die Datei entpackt
# sich bei jedem Start nach /tmp, das kostet ~2,5 s. Fuer ein Werkzeug, das man
# einmal pro Session startet und laufen laesst, ist das der richtige Tausch.
# Wer den schnelleren Start braucht, haengt a.binaries/a.datas an ein COLLECT
# statt an die EXE (onedir: ~0,45 s Start, aber ein Ordner statt einer Datei).
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="jampilot",
    debug=False,
    strip=False,
    upx=False,          # UPX zerlegt die signierten dylibs unter macOS
    console=True,       # Terminal-Programm: die Ausgabe IST die Oberflaeche
)

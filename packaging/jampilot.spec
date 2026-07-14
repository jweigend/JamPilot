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
# PySide6 steht bewusst NICHT in dieser Liste: Fuer Qt bringt PyInstaller einen
# eigenen Hook mit, der genau die benoetigten Bibliotheken und Plattform-Plugins
# einsammelt. Es zusaetzlich per collect_all einzuziehen holt die ganze
# Qt-Welt herein und kostete gemessen 38 MB - ohne dass etwas mehr funktioniert.
for paket in ("librosa", "numba", "llvmlite", "soundfile", "sounddevice",
              "soxr", "lazy_loader", "audioread", "msgpack"):
    d, b, h = collect_all(paket)
    datas += d
    binaries += b
    hiddenimports += h

# numbas JIT-Cache (.nbc/.nbi) NICHT mitnehmen. collect_all sammelt alles ein, was
# in den Paketverzeichnissen liegt - und dazu gehoeren die vorkompilierten
# Artefakte, die numba beim Entwickeln neben librosas Quellen ablegt. Im Bundle
# passen sie nicht mehr zu den Pfaden, unter denen sie entstanden sind. Was dann
# passiert, ist schlimmer als ein sauberer Fehler: Mal greift der Cache, mal
# nicht. Beobachtet wurde ein Absturz beim Warmup
#
#   NotImplementedError: No definition for lowering static_setitem(...)
#
# der bei JEDEM ZWEITEN Start kam und beim naechsten wieder verschwand. Ohne die
# Dateien uebersetzt numba im Bundle selbst - deterministisch, und ein paar
# hundert Millisekunden langsamer beim ersten Aufruf.
#
# Nebeneffekt, der genauso wichtig ist: Das Bundle haengt damit nicht mehr davon
# ab, was im Entwickler-venv zufaellig schon uebersetzt war. Ein reproduzierbarer
# Bau darf so etwas nicht einsammeln.
datas = [(quelle, ziel) for quelle, ziel in datas
         if not quelle.endswith((".nbc", ".nbi"))]

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

    # Qt ist gross, und PyInstaller nimmt per Default ALLES mit. Das
    # Kontrollfenster braucht genau drei Module: QtCore, QtGui, QtWidgets.
    # Alles andere - die QML/Quick-Welt, 3D, Multimedia, Netzwerkstacks - fliegt
    # raus. Was hier faelschlich stehen bleibt, meldet sich sofort beim Start.
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtUiTools",
    "PySide6.QtConcurrent", "PySide6.QtXml", "PySide6.QtSvgWidgets",
    "shiboken6.support",
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

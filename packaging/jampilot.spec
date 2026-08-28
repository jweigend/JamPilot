# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-Spec: JamPilot als eigenstaendiges Programm.

    pyinstaller packaging/jampilot.spec --noconfirm

    Linux/macOS  ->  dist/jampilot          EINE Datei (onefile)
    Windows      ->  dist/JamPilot/         ein Ordner (onedir)

GEBAUT WIRD IMMER AUF DEM ZIELSYSTEM. PyInstaller kann nicht cross-kompilieren:
Es sammelt die nativen Bibliotheken ein, die auf DIESER Maschine liegen
(libportaudio, libsndfile, libllvmlite, die BLAS von numpy/scipy). Ein
Linux-Build auf einem Mac gibt es nicht. Also: Linux-Binary auf Linux, macOS
getrennt fuer arm64 und x86_64, Windows auf Windows - siehe
.github/workflows/build.yml.

WARUM WINDOWS EINEN ORDNER BEKOMMT UND KEINE EINZELNE DATEI. Das ist keine
technische Einschraenkung, sondern eine Auslieferungsentscheidung, und sie ist
in docs/exploration/windows-portierung.md vorgezeichnet: Eine unsignierte
onefile-Exe dieser Groesse (gemessen 150 MB gepackt, 363 MB ausgepackt), die
sich bei jedem Start selbst nach %TEMP% auspackt, IST technisch ein Packer - und
wird von SmartScreen und Virenscannern auch so behandelt. Der Ordner umgeht
diese Heuristik, startet nebenbei in ~0.45 s statt ~2.5 s, und im ZIP ist er
genauso ein Download wie eine Datei. Verloren geht nur das Versprechen "eine
Datei".

Was das Bundle NICHT mitbringen kann, weil es Systemteile sind:
  * macOS: BlackHole (Audiotreiber, eigener Installer)
  * Linux: pactl / PipeWire-PulseAudio (ruft routing.py als externes Programm)
Beides bleibt eine Voraussetzung auf dem Zielrechner, siehe README. Windows
braucht seit der stummen Umleitung (wincapture.py) gar nichts mehr.
"""

import os
import re
import sys

from PyInstaller.utils.hooks import collect_all

projekt = os.path.dirname(os.path.dirname(os.path.abspath(SPEC)))  # noqa: F821

# Die Versionsnummer wird GELESEN, nicht hier gepflegt: Sie steht in
# jampilot/__init__.py, und ein zweites Vorkommen waere eines, das irgendwann
# etwas anderes sagt als das Programm selbst. Importieren geht nicht - die Spec
# laeuft im PyInstaller-Prozess, ohne das Projekt auf dem Pfad.
with open(os.path.join(projekt, "jampilot", "__init__.py"), encoding="utf-8") as f:
    VERSION = re.search(r'^__version__ = "([^"]+)"', f.read(), re.M).group(1)

ist_windows = sys.platform == "win32"

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

# [POC-BTC] Die Modellgewichte des BTC-Erkenners (11 MB) liegen als Paketdaten
# neben dem Code; der statische Scanner sieht nur Importe, keine Datendateien.
# Genauso die Web-Anzeige (index.html), die web.py beim Import laedt.
datas += [(os.path.join(projekt, "jampilot", "data", "btc_large_voca.npz"),
           os.path.join("jampilot", "data")),
          (os.path.join(projekt, "jampilot", "data", "index.html"),
           os.path.join("jampilot", "data"))]

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

# onefile (Linux/macOS): alles in EINE Datei. Der Preis steht im README - die
# Datei entpackt sich bei jedem Start nach /tmp, das kostet ~2,5 s. Fuer ein
# Werkzeug, das man einmal pro Session startet und laufen laesst, ist das der
# richtige Tausch.
#
# onedir (Windows): dieselben Bestandteile, nur haengen sie am COLLECT statt an
# der EXE. Begruendung im Kopf dieser Datei - SmartScreen, und nebenbei ~0,45 s
# Start. Fuer den Rest der Spec aendert sich dadurch nichts.
mitgeben = [] if ist_windows else [a.binaries, a.datas]

exe = EXE(
    pyz,
    a.scripts,
    *mitgeben,
    [],
    exclude_binaries=ist_windows,
    name="jampilot",
    debug=False,
    strip=False,
    upx=False,          # UPX zerlegt die signierten dylibs unter macOS
    console=True,       # bleibt ein CLI-Programm: `jampilot analyze`, `selftest` ...
)

# Der Ordner heisst JamPilot, nicht jampilot: Ihn sieht der Nutzer im Explorer,
# und er ist es, der ausgepackt wird. Die Exe darin behaelt die
# Kommandozeilen-Schreibweise, damit `jampilot devices` ueberall gleich aussieht.
if ist_windows:
    coll = COLLECT(                                                 # noqa: F821
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="JamPilot",
    )

# macOS: zusaetzlich ein richtiges .app-Buendel.
#
# Eine nackte Unix-Binary laesst sich im Finder zwar doppelklicken, oeffnet dabei
# aber ein Terminal - und, weit schlimmer, sie bekommt KEINE Mikrofonfreigabe.
# macOS verlangt dafuer NSMicrophoneUsageDescription in der Info.plist; ohne den
# Eintrag liefert das Audio-Eingabegeraet einfach Stille, ohne dass irgendwo eine
# verstaendliche Meldung erscheint. Genau der Eintrag steht hier.
#
# Das .app umschliesst dieselbe Binary. `jampilot` von der Kommandozeile bleibt
# also, wie es war; das Buendel ist der Weg fuer alle, die doppelklicken.
if sys.platform == "darwin":
    app = BUNDLE(                                                   # noqa: F821
        exe,
        name="JamPilot.app",
        icon=None,
        bundle_identifier="de.jweigend.jampilot",
        info_plist={
            "CFBundleName": "JamPilot",
            "CFBundleDisplayName": "JamPilot",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            # Ohne diesen Text kein Ton - und zwar stumm, nicht mit Fehler.
            "NSMicrophoneUsageDescription":
                "JamPilot reads your system audio (via a loopback device such as "
                "BlackHole) to show the chords before you hear them.",
            # Kein Dock-Icon-Flackern beim Start des Kontrollfensters.
            "LSBackgroundOnly": False,
        },
    )

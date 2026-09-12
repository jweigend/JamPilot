"""JamPilot - verzoegertes Audio-Loopback mit Akkorderkennung und Vorlauf."""

# DIE Quelle der Versionsnummer. pyproject.toml liest sie hier heraus
# (tool.setuptools.dynamic), packaging/jampilot.spec ebenso fuer die Info.plist
# des macOS-Buendels, und packaging/build.ps1 fuer den Namen des Windows-ZIP.
# Eine zweite Stelle waere eine Stelle, die irgendwann etwas anderes sagt - und
# genau das war sie: pyproject stand auf 0.1.0, als hier schon 1.1.1 stand.
__version__ = "1.4.0"

import os

# OpenBLAS auf EINEN Thread, bevor irgendwo numpy geladen wird (cli.py tut das
# als Erstes; beide Einstiege - `python -m jampilot` und packaging/entry.py -
# importieren zuerst dieses Paket). Sonst legt OpenBLAS je logischer CPU einen
# Thread an, und die drehen nach jeder Matrixmultiplikation ~100 ms lang im
# Leerlauf weiter: Auf dem Proberaum-PC (2x10 Kerne) waren das zwoelf Threads
# mit je 57 % CPU, rund sechs Kerne dauerhaft - und der Hop wurde damit nicht
# schneller, sondern langsamer (Verfeinerung 143 statt 110 ms, gemessen mit
# tests/reference/messung_audio_aussetzer.py). Die Matrizen des Modells sind
# zu klein, um von Threads zu profitieren; die CQT rechnet in numpys FFT, die
# ohnehin einen Thread nutzt. Und auf einem Rechner, dessen Audio-Graph ohne
# Echtzeit-Prioritaet laeuft, sind sechs drehende Kerne genau die Last, die
# den Audio-Callback zu spaet drankommen laesst. setdefault: Wer es anders
# will, setzt die Variable selbst. Details: docs/exploration/audio-aussetzer-analyse.md.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

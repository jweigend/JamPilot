"""JamPilot - verzoegertes Audio-Loopback mit Akkorderkennung und Vorlauf."""

# DIE Quelle der Versionsnummer. pyproject.toml liest sie hier heraus
# (tool.setuptools.dynamic), packaging/jampilot.spec ebenso fuer die Info.plist
# des macOS-Buendels, und packaging/build.ps1 fuer den Namen des Windows-ZIP.
# Eine zweite Stelle waere eine Stelle, die irgendwann etwas anderes sagt - und
# genau das war sie: pyproject stand auf 0.1.0, als hier schon 1.1.1 stand.
__version__ = "1.3.0"

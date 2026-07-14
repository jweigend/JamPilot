"""Einstiegspunkt fuer das PyInstaller-Bundle.

Warum nicht `jampilot/__main__.py`? Das benutzt `from .cli import main` - einen
RELATIVEN Import. PyInstaller fuehrt das Startskript als Top-Level-Modul aus, es
liegt dann in keinem Paket, und der relative Import schlaegt fehl
("attempted relative import with no known parent package"). Also ein eigener
Einstieg mit absolutem Import.
"""

from jampilot.cli import main

main()

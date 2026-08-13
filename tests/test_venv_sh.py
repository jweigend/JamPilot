"""run.sh darf nicht an Pfaden mit Leerzeichen sterben.

Der echte Fall: Clone nach `~/Área de trabalho/test/JamPilot` (portugiesischer
Desktop). Die Umgebung wurde angelegt, dann passierte NICHTS - kein Fenster,
keine Meldung, Exit-Code 2. Der Taeter war _qt_pruefen in packaging/venv.sh:
ein absichtlich ungequoteter Glob (`ls $plugin`), der den Pfad an den
Leerzeichen zerlegte; ls scheiterte, die Zuweisung trug den Exit-Code, und
`set -euo pipefail` beendete das Skript wortlos.

Getestet wird die Funktion direkt unter denselben Bedingungen: set -euo
pipefail, ein WURZEL-Pfad mit Leerzeichen und Umlaut, DISPLAY gesetzt. Die
Datei libqxcb.so ist leer - auch das ist Absicht: an ihr scheitert ldd, und
dessen Pipeline war die ZWEITE Stelle mit demselben Fehler.
"""

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _qt_pruefen_in(wurzel: Path) -> subprocess.CompletedProcess:
    skript = (
        "set -euo pipefail; "
        f'WURZEL="{wurzel}"; '
        f'. "{REPO}/packaging/venv.sh"; '
        "_qt_pruefen; "
        "echo DURCHGELAUFEN"
    )
    return subprocess.run(
        ["bash", "-c", skript],
        capture_output=True,
        text=True,
        env={**os.environ, "DISPLAY": ":0"},   # sonst: headless, frueher Ausstieg
    )


def test_qt_pruefen_ueberlebt_leerzeichen_und_umlaute_im_pfad(tmp_path):
    wurzel = tmp_path / "Área de trabalho" / "test" / "JamPilot"
    plugin = wurzel / ".venv/lib/python3.12/site-packages/PySide6/Qt/plugins/platforms/libqxcb.so"
    plugin.parent.mkdir(parents=True)
    plugin.write_bytes(b"")   # kein echtes ELF: ldd muss daran scheitern duerfen

    ergebnis = _qt_pruefen_in(wurzel)

    assert ergebnis.returncode == 0, (
        f"_qt_pruefen hat das Skript beendet (rc={ergebnis.returncode}) - "
        f"stderr: {ergebnis.stderr!r}"
    )
    assert "DURCHGELAUFEN" in ergebnis.stdout


def test_qt_pruefen_ohne_venv_ist_kein_fehler(tmp_path):
    # Frischer Checkout, .venv existiert noch gar nicht: nichts zu pruefen.
    wurzel = tmp_path / "Área de trabalho" / "JamPilot"
    wurzel.mkdir(parents=True)

    ergebnis = _qt_pruefen_in(wurzel)

    assert ergebnis.returncode == 0, ergebnis.stderr
    assert "DURCHGELAUFEN" in ergebnis.stdout

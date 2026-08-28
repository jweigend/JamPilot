"""Der Doppelklick-Weg unter Linux: ein .desktop-Starter.

Eine nackte Binary laesst sich im Dateimanager NICHT per Doppelklick starten, und
zwar nicht aus Versehen, sondern von Entwurf wegen. `dist/jampilot` hat den
MIME-Typ application/x-executable; dafuer ist kein Programm registriert, und
Nemo (Cinnamon) wie Nautilus (GNOME) bieten das Ausfuehren nur fuer ausfuehrbare
TEXT-Dateien an ("executable-text-activation"). Fuer eine Binaerdatei gibt es
diesen Weg gar nicht erst. Der Doppelklick tut also - nichts. Kein Fenster, keine
Meldung, kein Fehler. Genau so wurde es berichtet.

Der vorgesehene Weg ist ein Starter: eine .desktop-Datei sagt, WIE das Programm
heisst, WAS gestartet wird und dass dafuer KEIN Terminal noetig ist. Das ist
unter Linux der Doppelklick, und nebenbei der Eintrag im Anwendungsmenue.

    jampilot install              Eintrag im Anwendungsmenue (der uebliche Weg)
    jampilot install --to dist    JamPilot.desktop neben die Binary legen
    jampilot install --remove     wieder entfernen

Unter macOS gibt es das nicht und braucht es nicht: Dort baut die Spec ein
richtiges JamPilot.app - siehe packaging/jampilot.spec.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

NAME = "JamPilot"
DATEI = "jampilot.desktop"
SYMBOL = "jampilot"                  # Name im Icon-Thema, siehe symbol()
SYMBOL_QUELLE = Path(__file__).with_name("data") / "icon.png"


def _xdg_data_home() -> Path:
    """XDG_DATA_HOME beachten und nicht ~/.local/share festnageln.

    Wer es umsetzt, hat einen Grund - und der Dateimanager sucht dann auch nur
    dort.
    """
    return Path(os.environ.get("XDG_DATA_HOME")
                or os.path.join(Path.home(), ".local", "share"))


def menue() -> Path:
    """Das Verzeichnis, in dem Anwendungsstarter des Nutzers liegen."""
    return _xdg_data_home() / "applications"


def symbol() -> Path:
    """Wohin das Programmsymbol kommt, damit `Icon=jampilot` es findet.

    Der Starter sagt nur einen NAMEN, keinen Pfad - und den loest der Desktop
    ueber das Icon-Thema auf. Ein Pfad ginge auch, aber ins onefile-Bundle
    zeigt keiner: Die Binary packt sich bei jedem Start woanders nach /tmp aus.
    hicolor ist das Thema, in das jedes andere zurueckfaellt; 256 px reicht fuer
    Menue, Fensterleiste und Dock.
    """
    return _xdg_data_home() / "icons" / "hicolor" / "256x256" / "apps" / f"{SYMBOL}.png"


def programm() -> Path:
    """Der Pfad, der im Starter stehen muss - absolut.

    Ein Starter wird aus jedem beliebigen Verzeichnis aufgerufen; ein relativer
    Pfad zeigt darin ins Leere. Im Bundle ist `sys.executable` die Binary selbst
    (PyInstaller setzt das auf die Datei, nicht auf den Entpackordner) - genau
    die soll gestartet werden. Aus dem Quellbaum heraus ist es der Interpreter,
    dann muss der Konsolenbefehl `jampilot` her.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    gefunden = shutil.which("jampilot")
    if gefunden:
        return Path(gefunden).resolve()
    raise SystemExit(
        "jampilot is not on your PATH, so a launcher could not point at it.\n"
        "Install the package ('pip install -e .') or build the binary first "
        "('packaging/build.sh'), then run this again from the binary:\n"
        "    ./dist/jampilot install")


def _exec_wert(pfad: Path) -> str:
    """Exec= nach den Regeln der Desktop-Entry-Spec.

    Die Spec quotet nicht wie die Shell: Anfuehrungszeichen und Backslash werden
    mit Backslash geschuetzt, und gequotet wird nur, was es noetig hat. Ein Pfad
    mit Leerzeichen (~/Downloads/JamPilot 0.1/jampilot) ist keine Ausnahme,
    sondern das, was beim Auspacken herauskommt.
    """
    text = str(pfad)
    if not any(zeichen in text for zeichen in ' \t"\'\\><~|&;$*?#()`'):
        return text
    geschuetzt = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{geschuetzt}"'


def eintrag(pfad: Path) -> str:
    """Der Inhalt der .desktop-Datei.

    `Terminal=false` ist der Kern der Sache: JamPilot bringt sein Fenster selbst
    mit. StartupWMClass verbindet dieses Fenster mit dem Starter - ohne den
    Eintrag steht das Fenster in der Fensterleiste ohne Namen und ohne Symbol
    neben dem Starter, als waeren es zwei Programme.
    """
    return "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        f"Name={NAME}",
        "Comment=The chords of your system audio, seconds before you hear them",
        f"Exec={_exec_wert(pfad)}",
        # Ein Name aus dem Icon-Thema; install() legt die Datei dorthin, wo der
        # Desktop danach sucht (symbol()).
        f"Icon={SYMBOL}",
        "Terminal=false",
        "Categories=AudioVideo;Audio;Music;",
        "StartupNotify=true",
        "StartupWMClass=jampilot",
        "",
    ])


def _nachbereiten(ziel: Path, ins_menue: bool) -> None:
    """Was der Dateimanager sonst nicht mitbekommt.

    `update-desktop-database` bringt den Eintrag ins Menue, ohne dass man sich
    abmelden muss - aber NUR im Menueverzeichnis. Auf ein beliebiges Verzeichnis
    losgelassen legt es dort eine mimeinfo.cache ab: Muell neben der Binary, den
    niemand bestellt hat und der im Auslieferungsordner nichts zu suchen hat.

    Nemo und Nautilus starten einen Starter, der irgendwo im Dateisystem liegt,
    ausserdem nur, wenn er als vertrauenswuerdig markiert ist - sonst kommt statt
    des Programms ein Dialog ("Untrusted application launcher"). Wer ihn selbst
    gerade angelegt hat, hat ihm bereits vertraut.
    """
    if ins_menue and shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(ziel.parent)],
                       capture_output=True, check=False)
    if shutil.which("gio"):
        subprocess.run(["gio", "set", str(ziel), "metadata::trusted", "true"],
                       capture_output=True, check=False)


def install(nach: str | None = None, entfernen: bool = False) -> Path:
    """Starter anlegen (oder entfernen). Gibt den Pfad der Datei zurueck."""
    if sys.platform == "darwin":
        raise SystemExit(
            "macOS does not use .desktop launchers - the build produces a real "
            "JamPilot.app that you can double-click (see packaging/jampilot.spec).")
    if not sys.platform.startswith("linux"):
        raise SystemExit(f"No launcher support for {sys.platform}.")

    # Neben der Binary heisst er JamPilot.desktop (den Namen sieht man im
    # Ordner), im Menue jampilot.desktop (den Namen sieht niemand, er muss nur
    # eindeutig sein und zur StartupWMClass passen).
    ziel = Path(nach).expanduser().resolve() / f"{NAME}.desktop" if nach \
        else menue() / DATEI

    if entfernen:
        if ziel.exists():
            ziel.unlink()
            print(f"Removed {ziel}")
        else:
            print(f"Nothing to remove ({ziel} does not exist).")
        if symbol().exists():
            symbol().unlink()
        return ziel

    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(eintrag(programm()), encoding="utf-8")
    # Ausfuehrbar, damit der Dateimanager ihn auch IM ORDNER doppelklicken laesst
    # und nicht als Textdatei oeffnet.
    ziel.chmod(0o755)
    # Das Symbol kommt IMMER ins Icon-Thema des Nutzers, auch bei `--to dist`:
    # Der Starter dort ist ohnehin an diesen Rechner gebunden (absoluter Exec-
    # Pfad), und neben die Binary gehoert nichts, was man nicht ausliefert.
    symbol().parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SYMBOL_QUELLE, symbol())
    _nachbereiten(ziel, ins_menue=not nach)

    print(f"Launcher written: {ziel}")
    if nach:
        print("Double-click it in the file manager (the binary itself cannot be "
              "double-clicked - it is not a launcher).")
    else:
        print(f"{NAME} is now in your application menu. "
              f"'jampilot install --remove' takes it out again.")
    return ziel

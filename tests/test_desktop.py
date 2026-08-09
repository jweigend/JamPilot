"""Der Starter fuer den Doppelklick.

Warum es diese Tests gibt: Der Doppelklick auf `dist/jampilot` tat NICHTS - kein
Fenster, keine Meldung, kein Fehler. Nicht weil das Programm abstuerzte, sondern
weil der Dateimanager eine Binaerdatei gar nicht erst startet (MIME-Typ
application/x-executable, kein Programm dafuer registriert). Der .desktop-Starter
ist der Weg, den Linux dafuer vorsieht - und ein Starter mit falschem Pfad oder
`Terminal=true` scheitert genauso stumm wie vorher. Also wird er geprueft.
"""

import sys
from pathlib import Path, PurePosixPath

import pytest

from jampilot import desktop

linux_only = pytest.mark.skipif(not sys.platform.startswith("linux"),
                                reason="Starter gibt es nur unter Linux")


class TestEintrag:
    # PurePosixPath, nicht Path: Der Inhalt der .desktop-Datei ist reine
    # Textformung und laesst sich ueberall pruefen - `Path` aber uebersetzt
    # "/opt/jampilot" auf einem Windows-Rechner in "\opt\jampilot", und dann
    # scheiterten diese drei Tests an der Plattform des Pruefers statt an einem
    # Fehler. Ein Linux-Pfad soll hier ein Linux-Pfad bleiben.
    def test_die_tragenden_zeilen(self):
        text = desktop.eintrag(PurePosixPath("/opt/jampilot/jampilot"))
        assert text.startswith("[Desktop Entry]\n")
        assert "Exec=/opt/jampilot/jampilot" in text
        # Ohne das hier startet gar nichts oder es startet falsch:
        assert "Type=Application" in text
        assert "Terminal=false" in text      # JamPilot bringt sein Fenster selbst
        assert "Name=JamPilot" in text

    def test_pfad_mit_leerzeichen_wird_gequotet(self):
        """~/Downloads/JamPilot 0.1/jampilot ist der Normalfall, nicht die Ausnahme.

        Ungequotet liest der Starter daraus zwei Argumente - und startet nichts.
        """
        text = desktop.eintrag(PurePosixPath("/home/j/Jam Pilot/jampilot"))
        assert 'Exec="/home/j/Jam Pilot/jampilot"' in text

    def test_anfuehrungszeichen_im_pfad_werden_geschuetzt(self):
        text = desktop.eintrag(PurePosixPath('/home/j/wei"rd/jampilot'))
        assert r'Exec="/home/j/wei\"rd/jampilot"' in text


@linux_only
class TestInstall:
    def test_schreibt_starter_und_macht_ihn_ausfuehrbar(self, tmp_path, monkeypatch):
        monkeypatch.setattr(desktop, "programm", lambda: Path("/opt/jampilot/jampilot"))
        ziel = desktop.install(nach=str(tmp_path))

        assert ziel == tmp_path / "JamPilot.desktop"
        assert "Exec=/opt/jampilot/jampilot" in ziel.read_text()
        # Nemo und Nautilus zeigen einen Starter ohne x-Bit als TEXTDATEI an,
        # statt ihn zu starten. Der Doppelklick oeffnet dann einen Editor.
        assert ziel.stat().st_mode & 0o111

    def test_kein_muell_neben_der_binary(self, tmp_path, monkeypatch):
        """`--to dist` legt EINE Datei an, sonst nichts.

        `update-desktop-database` gehoert ins Menueverzeichnis. Auf dist/
        losgelassen legt es dort eine mimeinfo.cache ab - im Ordner, den man
        ausliefert.
        """
        monkeypatch.setattr(desktop, "programm", lambda: Path("/opt/jampilot/jampilot"))
        desktop.install(nach=str(tmp_path))

        assert [p.name for p in tmp_path.iterdir()] == ["JamPilot.desktop"]

    def test_ins_menue_ohne_ziel(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        monkeypatch.setattr(desktop, "programm", lambda: Path("/opt/jampilot/jampilot"))

        ziel = desktop.install()

        assert ziel == tmp_path / "applications" / "jampilot.desktop"
        assert ziel.exists()

    def test_remove_nimmt_ihn_wieder_weg(self, tmp_path, monkeypatch):
        monkeypatch.setattr(desktop, "programm", lambda: Path("/opt/jampilot/jampilot"))
        ziel = desktop.install(nach=str(tmp_path))
        assert ziel.exists()

        desktop.install(nach=str(tmp_path), entfernen=True)
        assert not ziel.exists()

    def test_remove_ohne_starter_ist_kein_fehler(self, tmp_path, monkeypatch):
        monkeypatch.setattr(desktop, "programm", lambda: Path("/opt/jampilot/jampilot"))
        desktop.install(nach=str(tmp_path), entfernen=True)   # darf nicht werfen


class TestProgramm:
    def test_im_bundle_zeigt_er_auf_die_binary(self, monkeypatch, tmp_path):
        """Im Bundle ist sys.executable die Binary selbst - genau die muss rein.

        Ein Starter wird aus irgendeinem Verzeichnis aufgerufen; ein relativer
        Pfad oder der Interpreter waere darin wertlos.
        """
        binary = tmp_path / "jampilot"
        binary.touch()
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(binary))

        assert desktop.programm() == binary.resolve()

"""Gibt es ein neueres Release? Eine Frage an GitHub, einmal pro Start.

Wer JamPilot als Binary heruntergeladen hat, erfaehrt von einer neuen Version
sonst nur, wenn er von selbst auf die Release-Seite schaut - und das tut
niemand. Das Kontrollfenster zeigt deshalb eine kleine Schaltflaeche, sobald
ein neueres Release liegt (gui.py), und die fuehrt auf die Download-Seite.

Was dieses Modul NICHT tut: herunterladen, auspacken, die laufende Binary
ersetzen. Das waere unter Windows ein Ordner mit ~1700 Dateien, die gerade
benutzt werden, unter macOS ein unsigniertes .app in Quarantaene - und in
jedem Fall ein Programm, das sich selbst ueberschreibt, ohne dass eine
Signatur sagt, womit. Die Schaltflaeche zeigt den Weg; gehen tut ihn der
Nutzer.

Es ist die EINZIGE Stelle, an der JamPilot ins Internet geht. Deshalb drei
Regeln, die hier nicht verhandelbar sind:

1. Uebertragen wird nichts ausser der Anfrage selbst (und im User-Agent die
   eigene Versionsnummer, die GitHub fuer API-Aufrufe verlangt). Kein
   Zaehler, keine Kennung, kein Ton.
2. Abschaltbar: `--no-update-check`.
3. Scheitern ist still. Kein Netz, eine Firewall, GitHub nicht erreichbar,
   eine unerwartete Antwort: Dann gibt es keine Schaltflaeche, und sonst
   aendert sich nichts. Ein Proberaum ohne WLAN ist der Normalfall, kein
   Fehler.

Aus der Antwort wird genau EINE Sache benutzt: die Versionsnummer, und die
erst, nachdem sie als drei Zahlen gelesen wurde. Die Adresse, die die
Schaltflaeche oeffnet, steht fest im Programm - nichts, was aus dem Netz
kommt, landet in einem Link oder als freier Text im Fenster.
"""

import json
import re
import ssl
import urllib.request

from . import __version__

# `releases/latest` liefert das juengste VEROEFFENTLICHTE Release - Entwuerfe
# und Vorabversionen sind dort von GitHub aus nicht dabei.
RELEASES_API = "https://api.github.com/repos/jweigend/JamPilot/releases/latest"
# Wohin die Schaltflaeche fuehrt. Fest, nicht aus der Antwort gelesen.
RELEASES_SEITE = "https://github.com/jweigend/JamPilot/releases/latest"

# Eine Sekunde reicht in aller Regel; fuenf sind die Geduld fuer ein lahmes
# WLAN. Laenger zu warten lohnt nicht - die Abfrage laeuft im Hintergrund, und
# wer kein Netz hat, soll nicht einen Thread minutenlang im Verbindungsaufbau
# stehen haben.
TIMEOUT = 5.0
# Die Antwort ist wenige Kilobyte gross (Release-Text plus Asset-Liste). Die
# Grenze ist dafuer da, dass ein Irrlaeufer nicht beliebig viel Speicher fuellt:
# Was laenger ist, wird abgeschnitten, ist dann kein JSON mehr und faellt weg.
MAX_BYTES = 1 << 20

_VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


def version_tupel(text) -> tuple[int, int, int] | None:
    """"v1.5.2" oder "1.5.2" -> (1, 5, 2); alles andere -> None.

    Streng mit Absicht: Ein Tag wie "v1.6.0-rc1" oder "nightly" ist kein
    Release, auf das die Schaltflaeche zeigen soll. Und ein Vergleich von
    Zeichenketten hielte "1.10.0" fuer aelter als "1.9.0".
    """
    treffer = _VERSION.fullmatch(text.strip()) if isinstance(text, str) else None
    return tuple(int(teil) for teil in treffer.groups()) if treffer else None


def tls_kontext() -> ssl.SSLContext:
    """Zertifikatspruefung, die auch im Bundle Wurzelzertifikate findet.

    Pythons Standardkontext sucht die Wurzelzertifikate dort, wo OpenSSL beim
    BAUEN sie erwartet hat. Im PyInstaller-Bundle ist das der Pfad des
    CI-Runners: Auf einem Ubuntu-Ziel stimmt er zufaellig, auf Fedora
    (/etc/pki) oder macOS nicht - dort schluege jede Verbindung mit
    CERTIFICATE_VERIFY_FAILED fehl, still, und die Schaltflaeche erschiene
    einfach nie. certifi bringt die Wurzeln als Datei mit (es steht in der
    Sperrdatei und kommt ueber librosa -> pooch -> requests ohnehin ins
    Bundle); sie werden ZUSAETZLICH zu denen des Systems geladen.

    Geprueft wird immer. Eine Abfrage ohne Zertifikatspruefung waere eine,
    der jedes Hotel-WLAN eine "neue Version" unterschieben koennte.
    """
    kontext = ssl.create_default_context()
    try:
        import certifi

        kontext.load_verify_locations(cafile=certifi.where())
    except (ImportError, OSError, ssl.SSLError):
        pass                 # dann eben nur die Wurzeln des Systems
    return kontext


def _neuestes_tag(timeout: float = TIMEOUT) -> str | None:
    """Der Tag-Name des juengsten Releases, so wie GitHub ihn nennt."""
    anfrage = urllib.request.Request(RELEASES_API, headers={
        "Accept": "application/vnd.github+json",
        # GitHub weist API-Aufrufe ohne User-Agent ab.
        "User-Agent": f"JamPilot/{__version__}",
    })
    with urllib.request.urlopen(anfrage, timeout=timeout,
                                context=tls_kontext()) as antwort:
        daten = json.loads(antwort.read(MAX_BYTES))
    return daten.get("tag_name") if isinstance(daten, dict) else None


def neuere_version(aktuell: str = __version__, abrufen=_neuestes_tag) -> str | None:
    """"1.5.2", wenn auf GitHub ein neueres Release liegt - sonst None.

    Wirft NIE. Jeder Fehler auf dem Weg (kein Netz, Zeitueberschreitung,
    Rate-Limit, kaputtes JSON, ein Tag, das keine Version ist) heisst
    dasselbe wie "nichts Neues": None. Die Rueckgabe ist aus den gelesenen
    Zahlen NEU zusammengesetzt, nicht der Text aus dem Netz.

    Gedacht fuer einen Hintergrundthread - der Aufruf blockiert bis zu
    TIMEOUT Sekunden.
    """
    try:
        neueste = version_tupel(abrufen())
    except Exception:
        return None
    eigene = version_tupel(aktuell)
    if neueste is None or eigene is None or neueste <= eigene:
        return None
    return ".".join(str(teil) for teil in neueste)

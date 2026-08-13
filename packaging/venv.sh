# Die Umgebung herstellen - einmal teuer, danach umsonst.
#
# Wird von run.sh und packaging/build.sh EINGEBUNDEN (source), nicht ausgefuehrt.
#
# Das Problem, das dieses Stueck loest: Ein frischer Checkout von GitHub ist eine
# Kette aus Schritten, von denen jeder einzeln schiefgehen kann - venv anlegen,
# pip aktualisieren, 34 Pakete installieren, PortAudio finden. Wer mittendrin
# Strg+C drueckt oder dessen WLAN wegbricht, hat danach ein Verzeichnis .venv,
# das AUSSIEHT wie eine fertige Umgebung und es nicht ist. Der naechste Start
# scheitert dann an "No module named librosa" - und der Grund liegt drei Tage
# zurueck.
#
# Deshalb: Ein Stempel, der den Sollzustand beschreibt (Sperrdatei + Python), und
# der wird ERST GESCHRIEBEN, WENN ALLES DURCH IST. Kein Stempel = die Umgebung
# ist unfertig, egal wie voll das Verzeichnis aussieht. Stimmt der Stempel, ist
# nichts zu tun: Das ist der Normalfall und kostet Millisekunden, keine Minuten.

STEMPEL_SCHEMA=1        # hochzaehlen, wenn sich die Logik hier aendert

# macOS kennt kein sha256sum - dort heisst es `shasum -a 256`. Ohne Argument
# lesen beide von der Standardeingabe.
pruefsumme() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$@" | cut -d' ' -f1
    else
        shasum -a 256 "$@" | cut -d' ' -f1
    fi
}

# Ein Python, das neu genug ist. NICHT einfach `python3`: macOS liefert je nach
# Version noch 3.9 aus, und JamPilot braucht 3.10 (die neue Typ-Schreibweise
# `str | None`). Lieber hier eine klare Ansage als spaeter ein SyntaxError.
python_finden() {
    local kandidat
    for kandidat in "${PYTHON:-}" python3.13 python3.12 python3.11 python3.10 python3; do
        [ -n "$kandidat" ] || continue
        command -v "$kandidat" >/dev/null 2>&1 || continue
        if "$kandidat" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
           2>/dev/null; then
            command -v "$kandidat"
            return 0
        fi
    done
    echo "JamPilot braucht Python 3.10 oder neuer - gefunden wurde keines." >&2
    echo "  macOS:  brew install python@3.12" >&2
    echo "  Ubuntu: sudo apt install python3 python3-venv" >&2
    return 1
}

_fingerabdruck() {
    # Woran haengt die Umgebung? An der Sperrdatei und an dem Python, mit dem sie
    # gebaut wurde. Aendert sich eines von beiden, ist der Stempel ungueltig -
    # ein Systemupdate von Python 3.11 auf 3.12 laesst ein venv zurueck, dessen
    # Interpreter ins Leere zeigt, und genau das faellt hier auf.
    local py="$1"
    printf '%s %s %s' \
        "$(pruefsumme "$WURZEL/requirements.lock")" \
        "$("$py" -c 'import platform, sys; print(sys.version.split()[0], platform.machine())')" \
        "$STEMPEL_SCHEMA"
}

# Sind die Pakete wirklich da? Ein Stempel bezeugt nur, dass pip einmal
# durchgelaufen ist - nicht, dass seither niemand aufgeraeumt hat.
#
# Geprueft wird mit find_spec, nicht mit `import`: Das sucht die Module bloss im
# Dateisystem, statt sie auszufuehren. librosa zu importieren kostet ueber eine
# Sekunde (numba, scipy, sklearn haengen daran) - und diese Sekunde wuerde bei
# JEDEM Start anfallen. So kostet die Pruefung Millisekunden.
_pakete_da() {
    "$1" - <<'PYTHON' 2>/dev/null
import importlib.util as u
import sys

sys.exit(1 if [m for m in ("numpy", "librosa", "sounddevice", "soundfile",
                           "qrcode", "PySide6")
               if u.find_spec(m) is None] else 0)
PYTHON
}

_venv_anlegen() {
    local system_py
    system_py="$(python_finden)" || return 1
    echo "==> lege .venv an  ($system_py)"
    if ! "$system_py" -m venv "$1"; then
        echo >&2
        echo "Das venv liess sich nicht anlegen. Unter Debian/Ubuntu fehlt dafuer" >&2
        echo "meist ein Paket:  sudo apt install python3-venv" >&2
        return 1
    fi
}

# Setzt VENV_PY auf den Interpreter der fertigen Umgebung.
venv_sicherstellen() {
    local venv="$WURZEL/.venv"
    local py="$venv/bin/python"
    local stempel="$venv/.jampilot-stempel"

    # Interpreter da UND pip da? Beides zusammen in einem Aufruf, mit find_spec
    # statt `import pip` - das kostet Millisekunden statt einer Zehntelsekunde
    # und faellt damit im Normalfall nicht ins Gewicht.
    #
    # Warum pip ueberhaupt mitpruefen: `python -m venv` legt zuerst die
    # Interpreter-Symlinks an, holt DANN pip und schreibt zuletzt die
    # activate-Skripte. Bricht es in der Mitte ab, bleibt ein .venv zurueck,
    # dessen Interpreter tadellos startet und in dem trotzdem kein pip liegt.
    # Ohne diese Pruefung laeuft der Aufruf unten in "No module named pip" -
    # eine Meldung, die nicht sagt, dass das venv der Schuldige ist.
    if [ ! -x "$py" ] \
       || ! "$py" -c 'import importlib.util as u, sys; sys.exit(0 if u.find_spec("pip") else 1)' 2>/dev/null; then
        # Kein brauchbarer Interpreter: entweder gibt es noch nichts, oder ein
        # abgebrochener Versuch hat einen halben Ordner hinterlassen, oder ein
        # System-Update hat den Symlink ins Leere zeigen lassen.
        if [ -e "$venv" ]; then
            echo "==> .venv ist unbrauchbar (abgebrochen oder verwaist) - wird neu angelegt"
            rm -rf "$venv"
        fi
        _venv_anlegen "$venv" || return 1

    elif [ "$(cat "$stempel" 2>/dev/null || true)" = "$(_fingerabdruck "$py")" ]; then
        if _pakete_da "$py"; then
            VENV_PY="$py"                # DER NORMALFALL: nichts zu tun
            return 0
        fi
        # Der Stempel sagt "fertig", die Pakete sagen etwas anderes. Dann ist die
        # Umgebung beschaedigt - und sie wird WEGGEWORFEN, nicht repariert.
        #
        # Warum nicht einfach `pip install` daruebergiessen? Weil pip das nicht
        # heilt: Fehlt ein Paketverzeichnis, liegt sein .dist-info aber noch da,
        # haelt pip es fuer installiert und tut nichts. Nachgemessen - genau das
        # passierte, und JamPilot lief danach ohne librosa STILL VERSTUEMMELT an
        # ("Inversions: skipped"), ohne dass irgendwo stand, warum. Ein venv ist
        # billig; eine Stunde Fehlersuche ist es nicht.
        echo "==> .venv ist beschaedigt (Pakete fehlen) - wird neu angelegt"
        rm -rf "$venv"
        _venv_anlegen "$venv" || return 1
    fi

    # Der Stempel passt nicht (frisches venv, geaenderte Sperrdatei, neues
    # Python). pip bringt die Umgebung auf den Stand der Sperrdatei - bei einer
    # blossen Versionsaenderung kostet das Sekunden, nicht Minuten.
    echo "==> installiere die Abhaengigkeiten aus requirements.lock"
    echo "    (das dauert beim ALLERERSTEN Mal ein paar Minuten - danach nie wieder)"
    "$py" -m pip install --quiet --upgrade pip
    "$py" -m pip install --quiet -r "$WURZEL/requirements.lock"

    # Erst jetzt. Bricht oben irgendetwas ab, gibt es keinen gueltigen Stempel -
    # und der naechste Aufruf installiert zu Ende, statt mit einer halben
    # Umgebung loszulaufen und an einer nichtssagenden Meldung zu sterben.
    printf '%s' "$(_fingerabdruck "$py")" > "$stempel"
    VENV_PY="$py"
}

# Was das venv NICHT mitbringen kann, weil es vom System kommt.
#
# sounddevice ist nur die Huelle um PortAudio. Unter Linux liegt die Bibliothek
# NICHT im Wheel - fehlt sie, laesst sich das Modul nicht einmal importieren, und
# die Meldung ("PortAudio library not found") sagt nicht, was zu tun ist. Unter
# macOS bringt das Wheel sie mit; dort fehlt statt dessen BlackHole, aber das
# merkt man erst beim Abhoeren, nicht beim Import.
system_pruefen() {
    _qt_pruefen
    "$VENV_PY" -c "import sounddevice" 2>/dev/null && return 0
    echo >&2
    echo "PortAudio fehlt - ohne die Bibliothek findet JamPilot kein Audiogeraet:" >&2
    if [ "$(uname)" = "Darwin" ]; then
        echo "  brew install portaudio" >&2
    else
        echo "  sudo apt install libportaudio2      # Debian/Ubuntu" >&2
        echo "  sudo dnf install portaudio          # Fedora" >&2
    fi
    return 1
}

# Dasselbe Spiel fuer die Oberflaeche - nur lauter im Scheitern.
#
# Das PySide6-Wheel bringt Qt mit, aber nicht die X11-Bibliotheken, auf denen
# Qts xcb-Plugin aufsetzt. Unter Ubuntu 24.04 fehlt regelmaessig
# libxcb-cursor0, das Qt seit 6.5 voraussetzt. Was der Nutzer dann sieht:
#
#   Could not load the Qt platform plugin "xcb" in "" even though it was found.
#   Reinstalling the application may fix this problem.
#
# Beides fuehrt in die Irre - "even though it was found" meint das Plugin, nicht
# dessen Abhaengigkeiten, und neu installieren hilft null, weil das Fehlende gar
# nicht aus dem Wheel kommt. Qt ruft danach abort(); der Prozess stirbt mit 134,
# und abfangen laesst sich das in Python nicht. Also hier, vorher.
#
# WARNUNG, kein Abbruch: `devices`, `analyze`, `cleanup` und `selftest` (das Qt
# offscreen laedt) laufen ohne xcb einwandfrei. Die sollen weiter laufen - nur
# eben mit dem Hinweis im Ruecken, falls als naechstes das Fenster drankommt.
_qt_pruefen() {
    [ "$(uname)" = "Linux" ] || return 0        # nur Linux baut Qt auf xcb auf
    [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] || return 0    # headless: kein Fenster gewollt
    command -v ldd >/dev/null 2>&1 || return 0

    # Der Glob laeuft als Array, nicht durch ein ungequotetes `ls`: Bei einem
    # Pfad mit Leerzeichen (~/Área de trabalho/...) zerlegte die Shell das
    # ls-Argument in Woerter, ls scheiterte - und unter `set -e` beendete die
    # fehlgeschlagene Zuweisung das ganze Skript. Wortlos, direkt nach dem
    # venv-Aufbau. Im Array bleibt der feste Teil gequotet, nur das * wirkt;
    # trifft es nichts, steht das Muster woertlich da und existiert nicht.
    local plugin fehlend kandidaten
    kandidaten=( "$WURZEL"/.venv/lib/python3*/site-packages/PySide6/Qt/plugins/platforms/libqxcb.so )
    plugin="${kandidaten[0]}"
    [ -e "$plugin" ] || return 0

    # `|| true`, weil auch diese Pipeline unter `set -euo pipefail` steht: Ein
    # ldd, das an der Datei scheitert, darf eine Warnung kosten - nicht den Start.
    fehlend="$(ldd "$plugin" 2>/dev/null | awk '/not found/ {print "  " $1}' | sort -u || true)"
    [ -n "$fehlend" ] || return 0

    echo >&2
    echo "Hinweis: Qt kann kein Fenster oeffnen - dem xcb-Plugin fehlen" >&2
    echo "Systembibliotheken, die NICHT im PySide6-Wheel stecken:" >&2
    echo "$fehlend" >&2
    echo >&2
    echo "  sudo apt install libxcb-cursor0     # Debian/Ubuntu, deckt den Normalfall" >&2
    echo "  sudo dnf install xcb-util-cursor    # Fedora" >&2
    echo >&2
    echo "Ohne das laufen devices/analyze/selftest weiter - das Fenster nicht." >&2
}

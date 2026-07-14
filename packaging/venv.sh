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

    if [ ! -x "$py" ] || ! "$py" -c "pass" 2>/dev/null; then
        # Kein Interpreter: entweder gibt es noch nichts, oder ein abgebrochener
        # Versuch hat einen leeren Ordner hinterlassen, oder ein System-Update
        # hat den Symlink ins Leere zeigen lassen.
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

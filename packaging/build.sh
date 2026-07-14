#!/usr/bin/env bash
#
# Baut JamPilot als EINE ausfuehrbare Datei - reproduzierbar.
#
#   packaging/build.sh              baut mit dem aktuellen Interpreter
#   packaging/build.sh --venv       baut in einem frischen venv aus requirements.lock
#   packaging/build.sh --check      baut ZWEIMAL und prueft, ob es bitgleich ist
#
# "Reproduzierbar" heisst hier: Gleicher Commit + gleiche Sperrdatei + gleiche
# Plattform => bitgleiche Binary. Nachgemessen, nicht behauptet - `--check` ist
# genau dieser Test.
#
# Ohne PYTHONHASHSEED ist der Bau NICHT reproduzierbar - zwei Baeufe aus
# denselben Quellen ergaben zwei verschiedene SHA-256. Der Grund ist nichts
# Zeitliches, sondern die Iterationsreihenfolge von Mengen und Dicts: Sie
# wandert ins Inhaltsverzeichnis des Archivs. Ein fester Seed genuegt.
#
# SOURCE_DATE_EPOCH setzen wir trotzdem, aber ehrlicherweise als Guerteltier:
# Nachgemessen aendert es bei PyInstaller 6.21 GAR NICHTS am Ergebnis (der Hash
# mit und ohne ist identisch; die .pyc-Zeitstempel werden offenbar schon selbst
# normalisiert). Allein gesetzt reicht es NICHT - ohne festen Hashseed sind die
# Baeufe weiter verschieden. Es steht hier, weil es die Konvention ist und eine
# kuenftige Version es beachten koennte. Wer es entfernt, bricht nichts.
#
# Was NICHT reproduzierbar ist und auch nicht sein kann: ein Bau auf einer
# anderen Plattform. PyInstaller buendelt die nativen Bibliotheken der Maschine,
# auf der es laeuft. Linux != macOS, und arm64 != x86_64.

set -euo pipefail

cd "$(dirname "$0")/.."
projekt="$PWD"

modus="${1:-}"

# --- Determinismus -----------------------------------------------------------
export PYTHONHASHSEED=0
export SOURCE_DATE_EPOCH="$(git log -1 --pretty=%ct 2>/dev/null || echo 1700000000)"
export PYTHONDONTWRITEBYTECODE=1

if ! git diff --quiet HEAD 2>/dev/null; then
    echo "WARNUNG: Das Arbeitsverzeichnis ist schmutzig. SOURCE_DATE_EPOCH kommt"
    echo "         vom letzten Commit - der Bau ist dann NICHT an den Quellstand"
    echo "         gebunden, die er beschreibt."
fi

# --- Interpreter waehlen -----------------------------------------------------
if [ "$modus" = "--venv" ]; then
    # Frisches venv aus der Sperrdatei: das ist der Bau, den auch die CI macht.
    # requirements.txt taugt dafuer NICHT - es sagt "librosa>=0.10", und was
    # daraus wird, entscheidet der Kalender.
    echo "==> frisches venv aus requirements.lock"
    rm -rf .build-venv
    python3 -m venv .build-venv
    .build-venv/bin/pip install --quiet --upgrade pip
    .build-venv/bin/pip install --quiet -r requirements.lock
    PY=".build-venv/bin/python"
else
    PY="${PY:-.venv/bin/python}"
    [ -x "$PY" ] || PY="python3"
fi

bauen() {
    rm -rf build dist
    "$PY" -m PyInstaller packaging/jampilot.spec --noconfirm --log-level WARN
}

# macOS kennt kein sha256sum - dort heisst es `shasum -a 256`.
pruefsumme() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    else
        shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

# --- Bauen -------------------------------------------------------------------
echo "==> Interpreter:        $PY"
echo "==> SOURCE_DATE_EPOCH:  $SOURCE_DATE_EPOCH  ($(git log -1 --pretty=%h 2>/dev/null || echo '?'))"
echo "==> baue ..."
bauen

# Der Test, der zaehlt - und er braucht keine Soundkarte. Der Selbsttest zieht
# librosa, numba und beide CQTs durch und faellt ueber jedes Modul, das
# PyInstaller nicht mitgenommen hat. Ein Bundle, das startet, ist noch kein
# Bundle, das rechnet.
echo "==> Selbsttest aus dem Bundle ..."
./dist/jampilot selftest

hash1="$(pruefsumme dist/jampilot)"

if [ "$modus" = "--check" ]; then
    echo "==> zweiter Bau (Reproduzierbarkeit pruefen) ..."
    cp dist/jampilot /tmp/jampilot-lauf1
    bauen
    hash2="$(pruefsumme dist/jampilot)"
    echo
    echo "    Lauf 1: $hash1"
    echo "    Lauf 2: $hash2"
    if [ "$hash1" = "$hash2" ]; then
        echo "    -> BITGLEICH. Reproduzierbar."
    else
        echo "    -> VERSCHIEDEN. Der Bau ist nicht reproduzierbar."
        exit 1
    fi
fi

# --- Der Doppelklick ----------------------------------------------------------
# Eine nackte Binary laesst sich im Dateimanager NICHT starten: Sie hat den
# MIME-Typ application/x-executable, dafuer ist kein Programm registriert, und
# der Doppelklick tut nichts - kein Fenster, keine Meldung. Der Starter daneben
# ist der Weg, den Linux dafuer vorsieht. Er entsteht hier, nach dem --check:
# der zweite Bau raeumt dist/ ab und wuerde ihn sonst mitnehmen.
#
# Unter macOS baut die Spec ein richtiges JamPilot.app - dort gibt es das nicht.
if [ "$(uname)" = "Linux" ]; then
    echo "==> Starter fuer den Doppelklick ..."
    ./dist/jampilot install --to dist
fi

echo
echo "  fertig:  dist/jampilot  ($(du -h dist/jampilot | cut -f1))"
echo "  sha256:  $hash1"

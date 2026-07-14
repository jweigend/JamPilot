#!/usr/bin/env bash
#
# Baut JamPilot als EINE ausfuehrbare Datei - reproduzierbar.
#
#   packaging/build.sh              baut, wenn sich etwas geaendert hat (sonst nicht)
#   packaging/build.sh --force      baut in jedem Fall neu
#   packaging/build.sh --venv       baut in einem frischen venv aus requirements.lock
#   packaging/build.sh --check      baut ZWEIMAL und prueft, ob es bitgleich ist
#
# Der uebliche Weg ist `./run.sh --bundle` - das ist dasselbe Skript, nur richtet
# es vorher die Umgebung ein, falls sie fehlt.
#
# Gebaut wird nur, was gebaut werden muss: Ein Stempel in dist/ haelt fest, aus
# welchen Quellen die Binary entstand. Sind sie unveraendert, waeren die drei
# Minuten PyInstaller vergeudet - herauskommen wuerde (siehe --check) bitgenau
# dieselbe Datei.
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
WURZEL="$PWD"

# shellcheck source=packaging/venv.sh
. "$WURZEL/packaging/venv.sh"      # venv_sicherstellen, pruefsumme, python_finden

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
if [ -n "${PY:-}" ]; then
    # Von aussen vorgegeben - so ruft die CI dieses Skript (PY=python), sie hat
    # die Pakete schon systemweit installiert und braucht kein venv.
    :
elif [ "$modus" = "--venv" ]; then
    # Frisches venv aus der Sperrdatei, bewusst OHNE Zwischenspeicher: Das ist
    # der Bau von ganz vorn, mit dem sich die Reproduzierbarkeit beweisen laesst.
    # requirements.txt taugt dafuer NICHT - es sagt "librosa>=0.10", und was
    # daraus wird, entscheidet der Kalender.
    echo "==> frisches venv aus requirements.lock"
    rm -rf .build-venv
    "$(python_finden)" -m venv .build-venv
    .build-venv/bin/pip install --quiet --upgrade pip
    .build-venv/bin/pip install --quiet -r requirements.lock
    PY=".build-venv/bin/python"
else
    # Der normale Weg: dasselbe .venv wie beim Starten, und es wird nur dann
    # angelegt oder nachinstalliert, wenn wirklich etwas fehlt.
    venv_sicherstellen
    PY="$VENV_PY"
fi

bauen() {
    rm -rf build dist
    "$PY" -m PyInstaller packaging/jampilot.spec --noconfirm --log-level WARN
}

# Woraus die Binary besteht. Aendert sich hieran nichts, ist ein Neubau
# vergeudete Zeit - PyInstaller braucht dafuer jedes Mal Minuten, und
# herauskommen wuerde (siehe --check) bitgenau dasselbe.
quellstempel() {
    cat jampilot/*.py packaging/jampilot.spec packaging/entry.py requirements.lock \
        | pruefsumme
}

# --- Bauen -------------------------------------------------------------------
echo "==> Interpreter:        $PY"
echo "==> SOURCE_DATE_EPOCH:  $SOURCE_DATE_EPOCH  ($(git log -1 --pretty=%h 2>/dev/null || echo '?'))"

# Steht die Binary schon da und hat sich an den Quellen nichts geaendert, ist
# nichts zu tun. Das ist der haeufigste Fall - und der einzige Grund, warum sich
# `run.sh --bundle` zweimal hintereinander aufrufen laesst, ohne dass man
# Minuten verliert. `--check` beweist die Reproduzierbarkeit und muss dafuer
# zwingend neu bauen; `--force` ist der Holzhammer fuer alle anderen Faelle.
if [ "$modus" != "--check" ] && [ "$modus" != "--force" ] \
   && [ -x dist/jampilot ] \
   && [ "$(cat dist/.quellstempel 2>/dev/null || true)" = "$(quellstempel)" ]; then
    echo "==> dist/jampilot ist aktuell - kein Neubau."
    echo "    (packaging/build.sh --force baut trotzdem neu)"
    aktuell=1
else
    aktuell=0
    echo "==> baue ..."
    bauen

    # Der Test, der zaehlt - und er braucht keine Soundkarte. Der Selbsttest
    # zieht librosa, numba und beide CQTs durch und faellt ueber jedes Modul,
    # das PyInstaller nicht mitgenommen hat. Ein Bundle, das startet, ist noch
    # kein Bundle, das rechnet.
    echo "==> Selbsttest aus dem Bundle ..."
    ./dist/jampilot selftest
fi

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

# Der Stempel steht ERST HIER - nach dem Bau und nach dem Selbsttest. Ein Bau,
# der auf halber Strecke abbrach, hinterlaesst keinen, und der naechste Aufruf
# baut ihn zu Ende, statt eine halbe dist/ fuer fertig zu halten. (Nach --check
# ebenfalls: dessen zweiter Bau raeumt dist/ ab und nimmt den Stempel mit.)
if [ "$aktuell" = "0" ]; then
    quellstempel > dist/.quellstempel
fi

# --- Der Doppelklick ----------------------------------------------------------
# Eine nackte Binary laesst sich im Dateimanager NICHT starten: Sie hat den
# MIME-Typ application/x-executable, dafuer ist kein Programm registriert, und
# der Doppelklick tut nichts - kein Fenster, keine Meldung. Der Starter daneben
# ist der Weg, den Linux dafuer vorsieht. Er entsteht hier, nach dem --check:
# der zweite Bau raeumt dist/ ab und wuerde ihn sonst mitnehmen.
#
# Unter macOS baut die Spec ein richtiges JamPilot.app - dort gibt es das nicht.
#
# Nur wenn er fehlt: Das Anlegen ruft die Binary auf, und die entpackt sich dafuer
# erst einmal (~2.5s). Bei einem Bau faellt das nicht auf; bei einem Aufruf, der
# gar nichts zu tun hat, waere es der groesste Posten.
if [ "$(uname)" = "Linux" ] && [ ! -f dist/JamPilot.desktop ]; then
    echo "==> Starter fuer den Doppelklick ..."
    ./dist/jampilot install --to dist
fi

echo
echo "  fertig:  dist/jampilot  ($(du -h dist/jampilot | cut -f1))"
echo "  sha256:  $hash1"

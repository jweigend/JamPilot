#!/usr/bin/env bash
#
# JamPilot starten - aus einem frischen Checkout heraus, ohne Vorbereitung.
#
#   ./run.sh                    starten (richtet beim ersten Mal alles ein)
#   ./run.sh --delay 6          jede Option von `jampilot run`
#   ./run.sh selftest           jeder andere Befehl (devices, analyze, cleanup ...)
#   ./run.sh --bundle           die eigenstaendige Binary + Doppelklick-Starter bauen
#   ./run.sh --neu              die Umgebung wegwerfen und neu aufsetzen
#
# Der erste Aufruf legt .venv an und installiert die Abhaengigkeiten - das dauert
# ein paar Minuten. JEDER WEITERE Aufruf ueberspringt das: Ein Stempel in .venv
# haelt fest, gegen welche Sperrdatei und welches Python installiert wurde. Passt
# er, ist nichts zu tun. Passt er nicht (Sperrdatei geaendert, Python
# aktualisiert, Installation abgebrochen), wird nachinstalliert - von selbst.
#
# Zum Bauen der Binary ist das GENAUSO: `--bundle` baut nur, wenn sich an den
# Quellen wirklich etwas geaendert hat. Sonst steht die fertige Datei ja schon da.

set -euo pipefail

WURZEL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$WURZEL"

# shellcheck source=packaging/venv.sh
. "$WURZEL/packaging/venv.sh"

if [ "${1:-}" = "--neu" ]; then
    echo "==> werfe .venv weg"
    rm -rf "$WURZEL/.venv"
    shift
fi

if [ "${1:-}" = "--bundle" ]; then
    shift
    exec "$WURZEL/packaging/build.sh" "$@"
fi

venv_sicherstellen
system_pruefen

exec "$VENV_PY" -m jampilot "$@"

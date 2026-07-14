#!/usr/bin/env bash

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python="$root/.venv/bin/python"

if [[ ! -x "$python" ]]; then
    echo "JamPilot virtual environment not found: $python" >&2
    echo "Create it with:" >&2
    echo "  python3 -m venv .venv" >&2
    echo "  .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

cd "$root"
exec "$python" -m jampilot "$@"
#!/usr/bin/env bash
# Always run Cluny with this repo's venv (avoids broken PATH / Homebrew python).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV_BIN="$ROOT/.venv/bin"
if [[ ! -x "$VENV_BIN/cluny" ]]; then
  echo "Missing $VENV_BIN/cluny. Run: ./setup_venv.sh" >&2
  exit 1
fi
export PATH="$VENV_BIN:$PATH"
exec "$VENV_BIN/cluny" "$@"

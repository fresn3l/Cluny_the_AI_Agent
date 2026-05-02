#!/usr/bin/env bash
# Create .venv in this repo and install Cluny in editable mode.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Need python3 on PATH (or set PYTHON=/path/to/python3)." >&2
  exit 1
fi

echo "Using: $($PY -c 'import sys; print(sys.executable)')"

if [[ ! -d .venv ]]; then
  "$PY" -m venv .venv
fi

./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -e .

echo ""
echo "Done. Use one of:"
echo "  ./run_cluny.sh stats"
echo "  ./run_cluny.sh ask \"Your question\""
echo "  source .venv/bin/activate   # then: cluny stats"
echo ""
echo "If 'cluny' is still not found after activate, use ./run_cluny.sh instead."

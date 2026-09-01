#!/usr/bin/env bash
# Build Cluny.app with py2app (menu bar accessory, HTTP brain).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Run ./setup_venv.sh first."
  exit 1
fi

"$ROOT/.venv/bin/pip" install -q py2app ".[api]"

rm -rf build dist
"$ROOT/.venv/bin/python" macos/setup_py2app.py py2app

echo ""
echo "Built: $ROOT/dist/Cluny.app"
echo "Install: cp -R dist/Cluny.app ~/Applications/"
echo "Test:    open dist/Cluny.app"

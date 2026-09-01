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

chmod +x macos/create_dmg.sh

echo ""
echo "Built: $ROOT/dist/Cluny.app"
if [[ -d "$ROOT/dist/Cluny.app" ]]; then
  SIZE_MB=$(du -sm "$ROOT/dist/Cluny.app" | awk '{print $1}')
  echo "Bundle size: ${SIZE_MB} MB"
fi

echo "Verifying imports (dev venv; bundle import parity)..."
"$ROOT/.venv/bin/python" macos/verify_bundle.py

echo ""
echo "Install: cp -R dist/Cluny.app ~/Applications/"
echo "DMG:     ./macos/create_dmg.sh"
echo "Test:    open dist/Cluny.app"

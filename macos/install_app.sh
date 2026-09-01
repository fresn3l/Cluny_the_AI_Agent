#!/usr/bin/env bash
# Build Cluny.app and install to ~/Applications for Dock / Spotlight launch.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x "$ROOT/.venv/bin/cluny" ]]; then
  echo "Setting up virtualenv first..."
  "$ROOT/setup_venv.sh"
fi

"$ROOT/macos/build_app.sh"

DEST="$HOME/Applications/Cluny.app"
mkdir -p "$HOME/Applications"
rm -rf "$DEST"
cp -R "$ROOT/macos/Cluny.app" "$DEST"

echo ""
echo "Installed: $DEST"
echo ""
echo "Next steps:"
echo "  1. Open Cluny from Spotlight (Cmd+Space) or Login Items"
echo "  2. Look for the blue menu bar icon (top-right)"
echo "  3. Click the icon → Ask / Capture / Task / Glance"
echo "  4. Tray menu → Open full window for the full chat UI"
echo ""
echo "Full window only from Terminal: ./run_cluny.sh gui"
echo "If you move the Cluny repo, run ./macos/install_app.sh again."

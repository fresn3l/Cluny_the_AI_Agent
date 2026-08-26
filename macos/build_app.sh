#!/usr/bin/env bash
# Build macos/Cluny.app (Dock-ready GUI launcher).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/macos/Cluny.app"
MACOS="$APP/Contents/MacOS"
RES="$APP/Contents/Resources"

rm -rf "$APP"
mkdir -p "$MACOS" "$RES"

cp "$ROOT/macos/Info.plist" "$APP/Contents/Info.plist"
cp "$ROOT/macos/cluny-gui" "$MACOS/cluny-gui"
chmod +x "$MACOS/cluny-gui"

printf '%s\n' "$ROOT" > "$RES/cluny_repo.txt"

echo "Built $APP"
echo "Install to Applications: ./macos/install_app.sh"

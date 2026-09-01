#!/usr/bin/env bash
# Build a drag-to-Applications DMG from dist/Cluny.app.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/dist/Cluny.app"
DMG="$ROOT/dist/Cluny.dmg"
STAGING="$(mktemp -d)"

cleanup() {
  rm -rf "$STAGING"
}
trap cleanup EXIT

if [[ ! -d "$APP" ]]; then
  echo "Run ./macos/build_py2app.sh first (missing $APP)."
  exit 1
fi

cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

rm -f "$DMG"
hdiutil create \
  -volname "Cluny" \
  -srcfolder "$STAGING" \
  -ov \
  -format UDZO \
  "$DMG" >/dev/null

echo ""
echo "DMG: $DMG"
ls -lh "$DMG"

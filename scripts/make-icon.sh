#!/bin/sh
# Draws Milo's app icon from the rig into assets/Milo.icns and assets/icon.png. Run after changing how he looks.
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SET="$(mktemp -d)/Milo.iconset"
MILO_ICONSET="$SET" swift test --package-path "$ROOT/app" --filter WrenIconTests >/dev/null
iconutil -c icns "$SET" -o "$ROOT/assets/Milo.icns"
echo "wrote $ROOT/assets/Milo.icns"
cp "$SET/icon_128x128@2x.png" "$ROOT/assets/icon.png"

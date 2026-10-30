#!/bin/sh
# Build Milo.app into ./build. Usage: scripts/build-app.sh [--open]
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/build/Milo.app"

swift build -c release --package-path "$ROOT/app"
BIN="$(swift build -c release --package-path "$ROOT/app" --show-bin-path)/Milo"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/Milo"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>dev.nkls.milo</string>
  <key>CFBundleName</key><string>Milo</string>
  <key>CFBundleExecutable</key><string>Milo</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSUIElement</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>Milo listens only while you hold the fn or right Option key.</string>
  <key>MiloBrainDir</key><string>$ROOT/brain</string>
</dict>
</plist>
PLIST
codesign --force --sign - "$APP"
echo "built $APP"
if [ "${1:-}" = "--open" ]; then open "$APP"; fi

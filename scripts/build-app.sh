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
  <key>NSCalendarsFullAccessUsageDescription</key><string>Milo looks at your calendar and puts appointments in it when you ask him to.</string>
  <key>NSRemindersFullAccessUsageDescription</key><string>Milo reads and adds reminders when you ask him to.</string>
  <key>NSAppleEventsUsageDescription</key><string>Milo reads your mail and notes, writes mail drafts and notes when you ask. He never sends mail.</string>
  <key>MiloBrainDir</key><string>$ROOT/brain</string>
</dict>
</plist>
PLIST
# A stable identity keeps macOS permissions (Accessibility, Screen Recording) across rebuilds; an ad-hoc
# signature changes every build, so macOS forgets them. Make one with scripts/make-signing-identity.sh.
IDENTITY="${MILO_SIGN_IDENTITY:-Milo Dev}"
if security find-identity -p codesigning | grep -q "\"$IDENTITY\""; then
  codesign --force --sign "$IDENTITY" "$APP"
else
  echo "no \"$IDENTITY\" signing identity, signing ad-hoc: permissions reset on every rebuild"
  codesign --force --sign - "$APP"
fi
echo "built $APP"
# A running brain keeps its old code: the app joins whatever brain holds the lock. Stop the one this
# checkout started, so the next launch loads the new code. MILO_KEEP_BRAIN=1 leaves it running.
LOCK="${MILO_HOME:-$HOME/Milo}/run/brain.lock"
if [ "${MILO_KEEP_BRAIN:-}" != 1 ] && [ -f "$LOCK" ]; then
  PID=$(cat "$LOCK" 2>/dev/null || true)
  if [ -n "$PID" ] && ps -o command= -p "$PID" 2>/dev/null | grep -q "$ROOT/brain/"; then
    kill -TERM "$PID" && echo "stopped the running brain ($PID) so the next launch loads the new code"
  fi
fi
if [ "${1:-}" = "--open" ]; then open "$APP"; fi

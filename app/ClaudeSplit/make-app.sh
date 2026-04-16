#!/bin/bash
# Build the SPM executable and wrap it as ClaudeSplit.app
# so notifications, LSUIElement (menu-bar-only), and app identity work.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── Build release binary ──────────────────────────────────────────
echo "Building release binary..."
swift build -c release

BIN=".build/release/ClaudeSplit"
if [ ! -f "$BIN" ]; then
  echo "Binary missing: $BIN"
  exit 1
fi

# ── Build .app bundle ─────────────────────────────────────────────
APP="build/ClaudeSplit.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
mkdir -p "$APP/Contents/Resources"

cp "$BIN" "$APP/Contents/MacOS/ClaudeSplit"

cat > "$APP/Contents/Info.plist" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>ClaudeSplit</string>
    <key>CFBundleDisplayName</key>
    <string>claude-split</string>
    <key>CFBundleIdentifier</key>
    <string>dev.claudesplit.monitor</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleExecutable</key>
    <string>ClaudeSplit</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

echo ""
echo "Built: $APP"
echo ""
echo "Run with:"
echo "  open $APP"
echo ""
echo "Or copy to /Applications:"
echo "  cp -R $APP /Applications/"

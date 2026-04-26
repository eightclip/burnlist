#!/bin/bash
# Build Burnlist.app — a tiny launcher bundle that downloads its dependencies
# (Python, ffmpeg, yt-dlp) on first launch into ~/Library/Application Support.
# Result is ~3 MB on disk; ~150 MB downloaded on first run per Mac.
#
# We build in /tmp because ~/Documents is under iCloud's file provider,
# which constantly re-tags files with xattrs that `codesign` rejects.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Burnlist"
WORK_DIR="/tmp/burnlist-build-$$"
APP_DIR="$WORK_DIR/${APP_NAME}.app"
DIST_DIR="$PROJECT_DIR/dist"

trap 'rm -rf "$WORK_DIR"' EXIT
mkdir -p "$WORK_DIR" "$DIST_DIR"

echo "==> Generating app icon…"
# We need Pillow once just to draw the icon. Use the system Python if present,
# otherwise download a small Python just for this build step.
HOST_PY=""
for cand in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [ -x "$cand" ] && "$cand" -c 'import sys' 2>/dev/null; then
    HOST_PY="$cand"; break
  fi
done
if [ -z "$HOST_PY" ]; then
  echo "    No usable system python3 found — downloading a tiny one for icon build…"
  curl -L --fail --progress-bar \
    "https://github.com/astral-sh/python-build-standalone/releases/download/20241016/cpython-3.11.10+20241016-aarch64-apple-darwin-install_only_stripped.tar.gz" \
    -o "$WORK_DIR/py.tar.gz"
  tar -xzf "$WORK_DIR/py.tar.gz" -C "$WORK_DIR"
  HOST_PY="$WORK_DIR/python/bin/python3"
fi
ICON_PKG="$WORK_DIR/icon-pkg"
mkdir -p "$ICON_PKG"
"$HOST_PY" -m pip install --quiet --target "$ICON_PKG" Pillow
if [ -f "$PROJECT_DIR/icon.png" ]; then
  echo "    Using $PROJECT_DIR/icon.png as source…"
  PYTHONPATH="$ICON_PKG" "$HOST_PY" "$PROJECT_DIR/prepare_icon.py"
else
  echo "    No icon.png found — generating from scratch…"
  PYTHONPATH="$ICON_PKG" "$HOST_PY" "$PROJECT_DIR/generate_icon.py"
fi
ICONSET="$WORK_DIR/Burnlist.iconset"
mkdir "$ICONSET"
for sz in 16 32 64 128 256 512; do
  sips -z $sz $sz /tmp/burnlist-icon.png --out "$ICONSET/icon_${sz}x${sz}.png" >/dev/null
  sips -z $((sz*2)) $((sz*2)) /tmp/burnlist-icon.png --out "$ICONSET/icon_${sz}x${sz}@2x.png" >/dev/null
done
cp /tmp/burnlist-icon.png "$ICONSET/icon_512x512@2x.png"
iconutil -c icns "$ICONSET" -o "$WORK_DIR/Burnlist.icns"

echo "==> Assembling .app bundle…"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources"

cp "$WORK_DIR/Burnlist.icns"     "$APP_DIR/Contents/Resources/Burnlist.icns"
cp "$PROJECT_DIR/server.py"      "$APP_DIR/Contents/Resources/server.py"
cp "$PROJECT_DIR/index.html"     "$APP_DIR/Contents/Resources/index.html"
cp "$PROJECT_DIR/launcher.sh"    "$APP_DIR/Contents/MacOS/$APP_NAME"
cp "$PROJECT_DIR/setup.sh"       "$APP_DIR/Contents/Resources/setup.sh"
chmod +x "$APP_DIR/Contents/MacOS/$APP_NAME" "$APP_DIR/Contents/Resources/setup.sh"

cat > "$APP_DIR/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>${APP_NAME}</string>
  <key>CFBundleIdentifier</key>
  <string>com.eightclip.burnlist</string>
  <key>CFBundleName</key>
  <string>${APP_NAME}</string>
  <key>CFBundleDisplayName</key>
  <string>Burnlist</string>
  <key>CFBundleVersion</key>
  <string>1.0.0</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleIconFile</key>
  <string>Burnlist</string>
  <key>LSMinimumSystemVersion</key>
  <string>11.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

echo "==> Clearing extended attributes…"
xattr -cr "$APP_DIR" 2>/dev/null || true
find "$APP_DIR" -name ".DS_Store" -delete 2>/dev/null || true

echo "==> Code signing (ad-hoc)…"
codesign --force --deep --sign - "$APP_DIR"

echo "==> Verifying signature…"
codesign --verify --verbose "$APP_DIR" 2>&1 | tail -3

echo "==> Copying signed bundle to $DIST_DIR (stripping xattrs)…"
rm -rf "$DIST_DIR/${APP_NAME}.app"
ditto --norsrc --noextattr --noqtn "$APP_DIR" "$DIST_DIR/${APP_NAME}.app"

echo
echo "✓ Built: $DIST_DIR/${APP_NAME}.app"
du -sh "$DIST_DIR/${APP_NAME}.app"

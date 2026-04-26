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

echo "==> Compiling AppleScript wrapper into .app stub…"
osacompile -o "$APP_DIR" "$PROJECT_DIR/burnlist.applescript"

echo "==> Installing app resources…"
cp "$WORK_DIR/Burnlist.icns"  "$APP_DIR/Contents/Resources/applet.icns"
cp "$PROJECT_DIR/launcher.sh" "$APP_DIR/Contents/Resources/launcher.sh"
cp "$PROJECT_DIR/setup.sh"    "$APP_DIR/Contents/Resources/setup.sh"
cp "$PROJECT_DIR/server.py"   "$APP_DIR/Contents/Resources/server.py"
cp "$PROJECT_DIR/index.html"  "$APP_DIR/Contents/Resources/index.html"
chmod +x "$APP_DIR/Contents/Resources/launcher.sh" \
         "$APP_DIR/Contents/Resources/setup.sh"

echo "==> Patching Info.plist…"
PB=/usr/libexec/PlistBuddy
PLIST="$APP_DIR/Contents/Info.plist"
# osacompile produces Info.plist with CFBundleName=applet etc. — rebrand it.
$PB -c "Set :CFBundleName Burnlist"        "$PLIST"
$PB -c "Set :CFBundleDisplayName Burnlist" "$PLIST" 2>/dev/null || \
  $PB -c "Add :CFBundleDisplayName string Burnlist" "$PLIST"
$PB -c "Set :CFBundleIdentifier com.eightclip.burnlist" "$PLIST" 2>/dev/null || \
  $PB -c "Add :CFBundleIdentifier string com.eightclip.burnlist" "$PLIST"
$PB -c "Set :CFBundleShortVersionString 1.1.0" "$PLIST" 2>/dev/null || \
  $PB -c "Add :CFBundleShortVersionString string 1.1.0" "$PLIST"
$PB -c "Set :CFBundleVersion 1.1.0" "$PLIST" 2>/dev/null || \
  $PB -c "Add :CFBundleVersion string 1.1.0" "$PLIST"
$PB -c "Add :NSHighResolutionCapable bool true" "$PLIST" 2>/dev/null || true

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

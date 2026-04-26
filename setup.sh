#!/bin/bash
# Burnlist first-run setup. Downloads Python, ffmpeg, yt-dlp into the support dir
# for the host architecture. Called by launcher.sh inside a Terminal window.

set -e

ARCH="$1"
DEST="$2"

PY_VERSION="3.11.10"
PY_DATE="20241016"
PY_BASE="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_DATE}"

case "$ARCH" in
  arm64)
    PY_URL="${PY_BASE}/cpython-${PY_VERSION}+${PY_DATE}-aarch64-apple-darwin-install_only_stripped.tar.gz"
    FFMPEG_URL="https://www.osxexperts.net/ffmpeg711arm.zip"
    ;;
  x86_64)
    PY_URL="${PY_BASE}/cpython-${PY_VERSION}+${PY_DATE}-x86_64-apple-darwin-install_only_stripped.tar.gz"
    FFMPEG_URL="https://evermeet.cx/ffmpeg/getrelease/zip"
    ;;
  *)
    echo "Unsupported arch: $ARCH"
    exit 1
    ;;
esac

YTDLP_URL="https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos"

cd "$DEST"

cat <<BANNER
============================================================
  Burnlist setup — downloading audio tools (one-time)
  Architecture: $ARCH
  Destination:  $DEST
============================================================
BANNER

echo
echo "[1/4] Downloading Python…"
curl -L --fail --progress-bar "$PY_URL" -o python.tar.gz
echo "      Extracting…"
rm -rf python
tar -xzf python.tar.gz
rm python.tar.gz

echo
echo "[2/4] Downloading ffmpeg…"
curl -L --fail --progress-bar "$FFMPEG_URL" -o ffmpeg.zip
unzip -q -o ffmpeg.zip
rm -f ffmpeg.zip
rm -rf __MACOSX
chmod +x ffmpeg

echo
echo "[3/4] Downloading yt-dlp…"
curl -L --fail --progress-bar "$YTDLP_URL" -o yt-dlp
chmod +x yt-dlp

echo
echo "[4/4] Installing mutagen (Python audio tag library)…"
"$DEST/python/bin/python3" -m pip install --quiet --upgrade pip >/dev/null
"$DEST/python/bin/python3" -m pip install --quiet mutagen

# Sanity check
[ -x "$DEST/python/bin/python3" ] || { echo "ERROR: python missing"; exit 1; }
[ -x "$DEST/ffmpeg" ]              || { echo "ERROR: ffmpeg missing"; exit 1; }
[ -x "$DEST/yt-dlp" ]              || { echo "ERROR: yt-dlp missing"; exit 1; }
"$DEST/python/bin/python3" -c "import mutagen" || { echo "ERROR: mutagen import failed"; exit 1; }

touch "$DEST/.ready"

cat <<DONE

============================================================
  ✓ Setup complete. You can close this Terminal window —
    Burnlist will start automatically.
============================================================
DONE

# Auto-close after a short pause so user can see the success message.
sleep 3
osascript -e 'tell application "Terminal" to close (every window whose name contains "setup.sh")' 2>/dev/null || true

#!/bin/bash
# Burnlist launcher: bootstraps dependencies on first run, then runs the server.

set -u

DIR="$(cd "$(dirname "$0")" && pwd)"
RES="$DIR/../Resources"
SUPPORT="$HOME/Library/Application Support/Burnlist"

ARCH="$(uname -m)"
case "$ARCH" in
  arm64|x86_64) ;;
  *)
    osascript -e "display alert \"Burnlist\" message \"Unsupported architecture: $ARCH\"" >/dev/null
    exit 1
    ;;
esac

PYTHON="$SUPPORT/python/bin/python3"
FFMPEG="$SUPPORT/ffmpeg"
YTDLP="$SUPPORT/yt-dlp"
READY_MARKER="$SUPPORT/.ready"

needs_setup() {
  [ ! -f "$READY_MARKER" ] || [ ! -x "$PYTHON" ] || [ ! -x "$FFMPEG" ] || [ ! -x "$YTDLP" ]
}

if needs_setup; then
  mkdir -p "$SUPPORT"
  rm -f "$READY_MARKER"

  ANSWER=$(osascript <<EOF
display dialog "Burnlist needs to download about 150 MB of audio tools (Python, ffmpeg, yt-dlp) into:

~/Library/Application Support/Burnlist

This is a one-time setup. It takes 1–3 minutes depending on your connection." \
buttons {"Quit","Continue"} default button "Continue" with title "Burnlist Setup" with icon caution
EOF
)
  if [[ "$ANSWER" != *"Continue"* ]]; then
    exit 0
  fi

  # Open Terminal showing the install in progress.
  osascript <<EOF
tell application "Terminal"
  activate
  do script "clear; bash '$RES/setup.sh' '$ARCH' '$SUPPORT'"
end tell
EOF

  # Poll until setup completes (or user gives up).
  WAITED=0
  while needs_setup; do
    sleep 2
    WAITED=$((WAITED + 2))
    if [ "$WAITED" -gt 600 ]; then
      osascript -e 'display alert "Burnlist" message "Setup is taking unusually long. Check the Terminal window for errors, then re-launch Burnlist."' >/dev/null
      exit 1
    fi
  done

  osascript -e 'display notification "Setup complete — launching Burnlist…" with title "Burnlist"' >/dev/null
fi

# Always copy the latest server.py / index.html shipped in the bundle.
cp "$RES/server.py"  "$SUPPORT/server.py"
cp "$RES/index.html" "$SUPPORT/index.html"

if lsof -ti :7474 >/dev/null 2>&1; then
  open "http://localhost:7474"
  exit 0
fi

export FFMPEG_BIN="$FFMPEG"
export YTDLP_BIN="$YTDLP"
export PATH="$SUPPORT:$PATH"

cd "$SUPPORT"
(sleep 2 && open "http://localhost:7474") &
exec "$PYTHON" "$SUPPORT/server.py"

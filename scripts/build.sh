#!/usr/bin/env bash
# End-to-end macOS build for Video Frames.
#
# Produces a self-contained dist/Video Frames.app that runs on any Apple
# Silicon Mac with macOS 11+ — no Homebrew or ffmpeg install required.
# (Intel Macs require running this script on an Intel host because PyQt6
# wheels are arch-specific.)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "$(uname)" != "Darwin" ]]; then
  echo "build.sh: macOS host required" >&2
  exit 1
fi

PYTHON="${PYTHON:-${ROOT}/venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

echo "==> Using Python: $PYTHON"
echo "==> Host arch:    $(uname -m)"

echo "==> Step 1: ensure build deps (PyInstaller, imageio-ffmpeg, PyQt6)"
"$PYTHON" -m pip install --quiet --upgrade pip
"$PYTHON" -m pip install --quiet -r requirements.txt
"$PYTHON" -m pip install --quiet pyinstaller

echo "==> Step 2: ensure AppIcon.icns exists"
if [[ ! -f assets/AppIcon.icns ]]; then
  echo "    generating AppIcon.icns (Pillow required)"
  "$PYTHON" -m pip install --quiet Pillow
  "$PYTHON" scripts/make_icon.py
else
  echo "    already present (delete assets/AppIcon.icns to regenerate)"
fi

echo "==> Step 3: clean previous build artifacts"
rm -rf build "dist/Video Frames.app" dist/VideoFrames

echo "==> Step 4: pyinstaller (bundles ffmpeg via imageio-ffmpeg)"
"$PYTHON" -m PyInstaller VideoFrames.spec --noconfirm

APP="dist/Video Frames.app"
if [[ ! -d "$APP" ]]; then
  echo "build failed: $APP not produced" >&2
  exit 1
fi

echo "==> Step 5: strip quarantine from bundled files"
xattr -dr com.apple.quarantine "$APP" 2>/dev/null || true

echo "==> Step 6: ad-hoc codesign (required on Apple Silicon)"
# Sign every Mach-O inside Frameworks first (binaries we bundled keep their
# original signatures; re-signing ad-hoc ensures the whole bundle is internally
# consistent so it will launch on Apple Silicon).
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP" && echo "    signature OK"

SIZE=$(du -sh "$APP" | awk '{print $1}')
echo
echo "Done. $APP ($SIZE)"
echo
echo "To distribute:"
echo "  1) zip it:   ditto -c -k --keepParent \"$APP\" 'VideoFrames.zip'"
echo "  2) Recipients may see a Gatekeeper prompt the first time. They can"
echo "     right-click the app and choose 'Open', or run:"
echo "       xattr -dr com.apple.quarantine '/Applications/Video Frames.app'"

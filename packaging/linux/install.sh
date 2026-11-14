#!/bin/bash
# Transactional per-user install. Preserve the previous app if staging/activation fails.
set -euo pipefail
umask 077
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
DEST="$DATA/IDRA"
BIN="$HOME/.local/bin"
APPS="$DATA/applications"
ICONS="$DATA/icons/hicolor/256x256/apps"

fail() { printf 'IDRA installation error: %s\n' "$*" >&2; exit 1; }
warn() { printf 'IDRA warning: %s\n' "$*" >&2; }
[ -x "$HERE/IDRA/IDRA" ] && [ -x "$HERE/IDRA/idra-cli" ] || fail "Extract the entire release archive before running install.sh"
[ ! -L "$DEST" ] || fail "Refusing to replace an installation path that is a symbolic link"
mkdir -p "$DATA"
STAGE="$(mktemp -d "$DATA/.IDRA.stage.XXXXXXXX")"
BACKUP="$DATA/.IDRA.backup.$$"
[ ! -e "$BACKUP" ] || fail "A backup path already exists: $BACKUP"
old_moved=0
activated=0
committed=0
cleanup() {
  status=$?
  trap - EXIT
  if [ "$committed" -ne 1 ] && [ "$old_moved" -eq 1 ]; then
    # Rollback is best-effort only if the original app was safely moved aside.
    rm -rf -- "$DEST"
    mv -- "$BACKUP" "$DEST" || warn "Manual restore needed: $BACKUP"
  elif [ "$committed" -ne 1 ] && [ "$activated" -eq 1 ]; then
    rm -rf -- "$DEST"
  fi
  if [ -d "$STAGE" ]; then rm -rf -- "$STAGE"; fi
  exit "$status"
}
trap cleanup EXIT

printf 'Staging IDRA in %s\n' "$STAGE"
cp -a "$HERE/IDRA/." "$STAGE/"
cp -- "$HERE/uninstall.sh" "$STAGE/uninstall.sh"
chmod 755 "$STAGE/uninstall.sh"
if ! check="$("$STAGE/idra-cli" --help 2>&1)"; then
  printf '%s\n' "$check" | tail -5 >&2
  fail "Staged IDRA CLI cannot launch on this host (check glibc and dependencies)"
fi
if [ -d "$DEST" ]; then
  mv -- "$DEST" "$BACKUP"
  old_moved=1
fi
mv -- "$STAGE" "$DEST"
activated=1
mkdir -p "$BIN" "$APPS" "$ICONS"
cp -- "$HERE/idra.png" "$ICONS/idra.png"
ln -sfn "$DEST/idra-cli" "$BIN/idra"
cat > "$APPS/idra.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=IDRA
GenericName=Screen session recorder
Comment=Local-first desktop recording and dataset preparation
Exec="$DEST/IDRA"
Icon=$ICONS/idra.png
Terminal=false
Categories=Utility;AudioVideo;Recorder;
DESKTOP
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPS" >/dev/null 2>&1 || true
fi
committed=1
if [ "$old_moved" -eq 1 ]; then rm -rf -- "$BACKUP"; fi
printf 'IDRA installed: %s\n' "$DEST"
if [ -x "$DEST/_internal/bin/ffmpeg" ]; then
  echo "FFmpeg: bundled inside the app."
elif command -v ffmpeg >/dev/null 2>&1; then
  if ! ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libx264; then
    warn "This FFmpeg has no libx264 encoder. Install your distribution's full FFmpeg package."
  fi
else
  warn "FFmpeg is unavailable. Install it before recording."
fi
if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
  warn "Wayland capture is unsupported. Use an X11 desktop session."
fi
case ":$PATH:" in *":$BIN:"*) ;; *) warn "Add $BIN to your PATH to run 'idra' from a terminal." ;; esac
printf 'Your recordings and ~/.idra settings remain unchanged.\n'

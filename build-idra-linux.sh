#!/bin/bash
# Build IDRA for this Linux computer:  ./build-idra-linux.sh  [--skip-tests] [--no-browser]
cd "$(dirname "$0")" || exit 1
python_ok() {
  "$1" -c 'import sys, venv, ensurepip; sys.exit(0 if (3, 11) <= sys.version_info[:2] < (3, 15) else 1)' >/dev/null 2>&1
}
PY=""
for c in python3.13 python3.12 python3.11 python3.14 python3; do
  p="$(command -v "$c" 2>/dev/null || true)"
  if [ -n "$p" ] && python_ok "$p"; then PY="$p"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3.11-3.14 with the venv module is needed. For example:"
  echo "  Ubuntu/Debian: sudo apt install python3 python3-venv"
  echo "  Fedora:        sudo dnf install python3"
  echo "  Arch:          sudo pacman -S python"
  exit 1
fi
exec "$PY" packaging/build_app.py "$@"

#!/bin/bash
# Double-click in Finder to build IDRA for this Mac (Apple Silicon or Intel, macOS 13+).
cd "$(dirname "$0")" || exit 1
clear
echo "Building IDRA for macOS. The first build takes 5-15 minutes; leave this window open."
python_ok() {
  "$1" -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] < (3, 15) else 1)' >/dev/null 2>&1
}
find_python() {
  local c
  for c in /opt/homebrew/bin/python3.13 /usr/local/bin/python3.13 \
           /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 \
           /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 \
           /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
           /opt/homebrew/bin/python3.11 /usr/local/bin/python3.11 \
           $(command -v python3.13 python3.12 python3.11 python3 2>/dev/null || true); do
    if [ -x "$c" ] && python_ok "$c"; then echo "$c"; return 0; fi
  done
  return 1
}
PY="$(find_python || true)"
if [ -z "$PY" ]; then
  BREW="$(command -v brew || true)"
  for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [ -z "$BREW" ] && [ -x "$b" ]; then BREW="$b"; fi
  done
  if [ -n "$BREW" ]; then
    echo "Installing Python 3.13 with Homebrew (one-time)..."
    "$BREW" install python@3.13 && PY="$(find_python || true)"
  fi
fi
if [ -z "$PY" ]; then
  echo "Python 3.11-3.14 is needed. Install Homebrew from https://brew.sh and run this again,"
  echo "or install Python 3.13 from https://www.python.org/downloads/macos/."
  status=1
else
  "$PY" packaging/build_app.py "$@"
  status=$?
fi
echo
if [ "$status" -eq 0 ]; then open dist; else echo "The build stopped (code $status). The reason is printed in red above."; fi
echo "Press Return to close this window."
read -r _
exit "$status"

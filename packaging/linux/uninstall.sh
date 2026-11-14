#!/bin/bash
# Removes IDRA for the current user. Recordings (~/IDRA-recordings) and settings (~/.idra) are kept.
set -u
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -f "$HOME/.local/bin/idra" "$DATA/applications/idra.desktop" "$DATA/icons/hicolor/256x256/apps/idra.png"
rm -rf "${DATA:?}/IDRA"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA/applications" >/dev/null 2>&1
echo "IDRA was removed. Your recordings and settings were kept."

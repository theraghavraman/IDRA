#!/bin/bash
# Developer ID signing/notarization must be executed on macOS with authorized credentials.
set -euo pipefail
MODE="${1:?Usage: sign-and-notarize.sh sign-app <IDRA.app> | notarize-dmg <IDRA.dmg>}"
TARGET="${2:?Provide native .app or .dmg path}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ "$(uname -s)" = "Darwin" ] || { echo 'macOS is required' >&2; exit 2; }
case "$MODE" in
  sign-app)
    : "${IDRA_DEVELOPER_ID_APPLICATION:?Set full Developer ID Application identity}"
    [ -d "$TARGET" ] || { echo "Missing app bundle: $TARGET" >&2; exit 2; }
    codesign --force --options runtime --timestamp --deep \
      --entitlements "$HERE/entitlements.plist" \
      --sign "$IDRA_DEVELOPER_ID_APPLICATION" "$TARGET"
    codesign --verify --deep --strict --verbose=2 "$TARGET"
    codesign -dv --verbose=4 "$TARGET" 2>&1
    echo 'Signed app; next run packaging/build_app.py --package-only to create the DMG.'
    ;;
  notarize-dmg)
    : "${IDRA_NOTARY_KEYCHAIN_PROFILE:?Set the notarytool keychain profile name}"
    [ -f "$TARGET" ] || { echo "Missing DMG: $TARGET" >&2; exit 2; }
    xcrun notarytool submit "$TARGET" --keychain-profile "$IDRA_NOTARY_KEYCHAIN_PROFILE" --wait
    xcrun stapler staple "$TARGET"
    xcrun stapler validate "$TARGET"
    echo 'Notarization/stapling succeeded. Record Gatekeeper, TCC and runtime test evidence separately.'
    ;;
  *) echo 'Unknown mode: use sign-app or notarize-dmg' >&2; exit 2 ;;
esac

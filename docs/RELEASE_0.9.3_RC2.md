# IDRA v0.9.3-rc2: hardening release and acceptance checklist

**Status:** source-only release candidate; not yet ready for general distribution. Current test results are in the [README Status section](../README.md#status).

This candidate follows the independent v0.9.3-rc1 Linux/X11 acceptance work. It is an updated source archive, **not** a signed native Windows/macOS/Linux binary. Historical 0.9.2 executable acceptance claims do not certify this version.

## Implemented in rc2

1. **Crash recovery: extra video frames after a forced stop.** Under a confirmed contiguous, clean frame journal, recovery can preserve the entire original media in `reports/recovered-video-original-*.mkv` and re-encode only the first N video frames matching N persisted frame records. The new canonical media is checked with `ffprobe` and SHA-256; the original hash and path are logged. No frame or event metadata is fabricated, and the session remains `INTERRUPTED` with `RECOVERY_VIDEO_TAIL_TRIMMED`. If the video has too few frames, no frame count, damaged journal, or failed transcoding, recovery refuses reconciliation, retains available media, and flags manual review. Export of interrupted sessions still requires a separate opt-in, and every visual export still requires explicit review attestation.
2. **Linux installer: transactional upgrade and rollback.** Stage all files before touching the previous install, run CLI preflight, atomically activate on the same filesystem, then create launchers. On a failed stage or post-activation step the prior application is retained/restored. Keep contributor recordings/settings untouched.
3. **Windows installer: transactional upgrade and rollback (source-only).** Stage/validate native executables before replacing an existing installation, then rollback on failure. Removed `Unblock-File`. Added a production option that rejects installs whose executable signatures are not valid (`IDRA_REQUIRE_SIGNED_INSTALL=1`). This PowerShell script still requires native Windows testing.
4. **Native signing helpers.** `packaging/windows/sign-native.ps1` is provided for a legitimate Windows publisher certificate; `packaging/macos/sign-and-notarize.sh` signs with Developer ID and notarizes/staples a DMG using a configured Apple keychain profile. No credentials are in source. Neither helper has been run yet, because no signing certificate is set up.
5. **Builder support for signed-native package reuse.** `python packaging/build_app.py --package-only` smoke-tests and packages an existing native build without rebuilding and invalidating external signatures. Packages identify the rc2 candidate.
6. **Provisional dependency inventory and fail-closed evidence gate.** `scripts/generate_sbom.py` inventories the *current Python environment* in CycloneDX format with explicit limitations; it is NOT a binary SBOM. `scripts/release_gate.py` checks OS-specific evidence flags, file existence and SHA-256 against a template and returns `NO_GO` until release-owner and legal fields are present. It does not establish independently that manual attestations are true.

## Mandatory target acceptance matrix

| Gate | Linux physical X11 | Windows 10/11 x64 | macOS arm64 | macOS Intel |
|---|---|---|---|---|
| Native GUI, screen recording, input hooks | Pending | Pending | Pending | Pending |
| Global stop with keyboard telemetry OFF | Pending | Pending | Pending | Pending |
| Signed/notarized native build and clean install | Pending | Pending | Pending | Pending |
| Multi-hour capture, disk pressure, abort/recovery | Pending | Pending | Pending | Pending |
| Privacy/adversarial input/browser provenance | Pending | Pending | Pending | Pending |
| Legal licensing, binary SBOM, vulnerability and release approval | Pending | Pending | Pending | Pending |

Controlled Xvfb source capture, core tests, and standalone installer simulations are **not substitutes** for these native gates.

## Release criteria

- All source hashes match `RELEASE_CONTENTS.json`; publish and externally sign archive/checksum with approved publisher key.
- On each target architecture run tests **from the same source ZIP** and the packaged app's diagnostics/demo/export/verify workflow.
- Manually record a consented harmless screen, keyboard-category-only telemetry, window context and managed-browser data, with the dedicated emergency stop listener while keyboard telemetry is disabled.
- Verify secure clean install, update failure rollback, uninstall, signed installer and stable settings/recording preservation.
- Collect complete **binary** SBOM, vulnerability review, PyQt6/Qt license decision, FFmpeg/libx264 build provenance and redistribution compliance, and Playwright/Chromium notice/review. Obtain documented legal and management signoff.

See `docs/PRODUCTION_RELEASE_RUNBOOK.md` and `docs/release_acceptance_template.json` for actionable command sequences and the evidence form. Automated `GO_REQUIRES_HUMAN_AUTHENTICITY_REVIEW` is not authorization to release without human signoff.

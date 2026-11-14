# IDRA v0.9.3-rc2 - native release operator runbook

**This is an execution checklist for the authorized release team, not evidence that a production build exists.** All commands must be executed on computers the team controls, using authorized test windows/content and relevant code-signing identities.

## 1. Integrity + baseline tests (each target OS)

Extract the exact source archive and check its published SHA-256 and `RELEASE_CONTENTS.json`. From the project root with Python 3.11-3.14, FFmpeg/libx264, and the project dependencies installed:

```bash
python -m pytest -q -ra
python -m compileall -q src tests packaging scripts
python scripts/static_audit.py
python -m idra diagnostics
python -m idra --storage ./test-recordings demo --seconds 2 --export ./test-dataset
python -m idra verify-export ./test-dataset
python scripts/generate_sbom.py --out ./reports/provisional-python-sbom.cdx.json --evidence ./reports/sbom-limitations.json
python scripts/native_acceptance_runner.py --source-root . --out ./reports/native-acceptance --pytest
```

> Run tests in a clean *target build environment*. The Python SBOM represents the environment, not the actual PyInstaller distribution. Extract and inspect the final bundle for a production-level component inventory.

## 2. Build and test native packages

**Windows x64 (PowerShell / Python):**

```powershell
python packaging/build_app.py --no-package
$env:IDRA_SIGN_CERT_THUMBPRINT = 'YOUR-AUTHORIZED-CERTIFICATE-THUMBPRINT'
powershell -NoProfile -File packaging/windows/sign-native.ps1
python packaging/build_app.py --package-only
# On a clean test PC, verify signatures for IDRA.exe and idra-cli.exe.
# For production-signature requirement, set IDRA_REQUIRE_SIGNED_INSTALL=1 before install.
```

Use an enterprise-approved PowerShell script execution policy (do not bypass organizational controls).
Sign only with an authorized enterprise publishing certificate; verify with `Get-AuthenticodeSignature` and Windows SDK `signtool verify /pa /v`. Preserve signed source PowerShell scripts, certificate subject/chain, timestamp verification and exact ZIP checksum. Test installation, forced mid-copy failure, rollback and SmartScreen behavior on Windows 10/11. Do not suppress the Mark-of-the-Web security signal as a workaround.

**macOS arm64 and Intel (execute on each native Mac):**

```bash
python3 packaging/build_app.py --no-package
export IDRA_DEVELOPER_ID_APPLICATION='Developer ID Application: YOUR AUTHORIZED ENTITY (TEAMID)'
packaging/macos/sign-and-notarize.sh sign-app dist/IDRA.app
python3 packaging/build_app.py --package-only
export IDRA_NOTARY_KEYCHAIN_PROFILE='YOUR_NOTARYTOOL_PROFILE'
packaging/macos/sign-and-notarize.sh notarize-dmg dist/IDRA-0.9.3-rc2-macos-arm64.dmg
codesign --verify --deep --strict --verbose=2 dist/IDRA.app
spctl --assess --type execute --verbose=4 dist/IDRA.app
```

The DMG filename differs for macOS Intel. Preserve notarization IDs and logs, hardened-runtime entitlement review and Gatekeeper/TCC allow/deny/revoke/relaunch screenshots. Validate screen capture, global shortcut, window context, Retina/multi-display and media player. An ad-hoc signature does **not** meet this gate.

**Linux X11 physical x86_64:**

```bash
python3 packaging/build_app.py
# Install the newly built IDRA-0.9.3-rc2-linux-x86_64.tar.gz on a separate test account.
# Verify XDG_SESSION_TYPE=x11; run its bundled CLI smoke, graphical capture and global shortcut.
```

Test X11 input listeners with a second test window focused, FFmpeg encoder availability and acceptable frame drops. Test recovery under forced process termination; verify that recorded originals remain preserved when a journal-aligned video prefix is generated. Validate installed launcher, permissions, rollback and that `~/IDRA-recordings` is not removed.

## 3. Hardware privacy and reliability acceptance

Use a non-sensitive generated desktop and a separate consented test profile. Verify no printable keys, clipboard, form values or browser credentials appear in journals; test injected browser events and ensure unverified claims cannot be promoted into trusted human actions. Test monitor changes, HiDPI/scaling, input coordinate mapping, session pause/resume, 2+ hour soak, low disk, FFmpeg failure, force kill, restarted session and interrupted media exclusion. A valid checksum **does not** establish the content is suitable for AI training.

## 4. Commercial licensing decision (legal counsel required)

- **PyQt6:** Riverbank's available GPLv3 or commercial terms are separate from Qt. For GPL-incompatible proprietary distribution, obtain the appropriate commercial rights; also review the Qt runtime license.
- **FFmpeg/libx264:** A shipped FFmpeg build with `--enable-gpl` and libx264 has GPL obligations. Obtain exact build flags, license notice/corresponding source and legal assessment for the intended distribution model; review alternatives if those obligations cannot be met.
- **Chromium/Playwright:** review Redistributable binaries, components, notices and optional browser download strategy.
- **SBOM:** enumerate actual frozen executable contents, DLL/Qt plugins, Node/Chromium, FFmpeg and transitive Python wheels, hashes and CVE review; compare with declared pins, and secure the legal team's approval.

Official references: https://en.riverbankcomputing.com/software/pyqt , https://ffmpeg.org/legal.html , https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution

## 5. Fail-closed release gate

Copy `docs/release_acceptance_template.json` to a release evidence record outside the source archive. Populate it with real artifacts and authenticated test reports. Use absolute paths for evidence files and finalized signed/native artifact hashes. Then:

```bash
python scripts/release_gate.py --evidence /path/to/approved-evidence.json --report /path/to/gate-result.json
```

A missing target, evidence file, signature assertion, signed artifact, or legal approval returns exit code 2 and `NO_GO`. Even a complete result reports `GO_REQUIRES_HUMAN_AUTHENTICITY_REVIEW`, because a local JSON gate cannot certify certificate identity or legal authorization. The designated release owner makes the final decision.

# Security Policy

## Supported versions

IDRA is pre-1.0. Only the latest release candidate on `main` receives security fixes.

| Version      | Supported |
|--------------|-----------|
| 0.9.3-rc2    | Yes       |
| < 0.9.3-rc2  | No        |

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report privately through GitHub: go to this repository's **Security** tab and choose
**Report a vulnerability** (GitHub private vulnerability reporting).

Include what you can of:

- the affected version or commit and your OS
- steps to reproduce, or a proof of concept
- the impact you expect (for example: data leaving the machine, redaction bypass,
  recording without consent, installer privilege issues)

You should get an acknowledgement within 7 days. Please give us a reasonable window to ship a
fix before disclosing publicly.

**Never attach real screen recordings, exported datasets or settings files to a report.**
Use the synthetic demo (`python -m idra demo`) or a minimal fixture to reproduce.

## Scope

In scope:

- capture continuing after Stop/Pause, or starting without the consent flow
- secret or URL redaction bypasses in recorded metadata
- recordings, logs or settings written outside the configured storage folder or with
  overly broad file permissions
- any network transmission of recorded data (IDRA is designed to be fully local)
- path traversal or code execution via crafted sessions, exports or ZIP archives
- installer, update and rollback scripts (`packaging/`)

Out of scope:

- issues in third-party dependencies (PyQt6, FFmpeg, Playwright/Chromium, etc.); report those
  upstream, though we welcome a heads-up if IDRA's usage makes them exploitable
- unsigned local builds you made yourself; official builds are not yet published

## Handling secrets in this repository

This repository must never contain API keys, signing certificates, notarization credentials,
real recordings or personal settings. Signing scripts in `packaging/` reference credentials only
by name at run time (a Windows certificate-store thumbprint, a macOS keychain profile); the
secrets themselves stay in the operator's OS credential store. Strings that look like secrets in `tests/` are fake
fixtures used to test redaction.

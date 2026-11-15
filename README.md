# Intelligent Data Recording Agent (IDRA)

**Version 0.9.3-rc2 · Local-first desktop recording and dataset preparation · Source-only release candidate**

IDRA records an explicitly authorized desktop session (screen video plus privacy-minimized mouse,
keyboard-category, window-context and managed-browser metadata), encodes H.264 media, and exports
validated computer-use trajectories. Everything stays on your machine; IDRA has no network upload
or telemetry service.

[![Tests](https://github.com/theraghavraman/IDRA/actions/workflows/tests.yml/badge.svg)](https://github.com/theraghavraman/IDRA/actions/workflows/tests.yml)

## Status

0.9.3-rc2 is a source release; there are no signed installers yet.

**Tested**

- **CI on every push** ([Tests workflow](https://github.com/theraghavraman/IDRA/actions/workflows/tests.yml)):
  - Linux on Python 3.11 and 3.13: 172 passed, 1 skipped. This includes real FFmpeg X11 capture, MSS, Pynput and Chromium tests on an isolated Xvfb display, plus the Linux installer rollback.
  - macOS arm64 on Python 3.13: 167 passed, 6 skipped (the Linux-only tests).
  - Ruff runs in CI and passes.
- **On an M2 Mac** (macOS 27, Python 3.13): the full suite, including the PyQt6 GUI tests, and the synthetic demo (record, H.264 encode, export, `verify-export`), which passed every check.

**Not yet tested**

- A real screen-recording session on a physical Mac or Windows PC with OS permissions granted.
- Multi-hour recordings.
- Signed and notarized builds.
- Windows.

mypy still reports type errors (mostly Optional narrowing and Qt stubs) that are not yet fixed.

## What's in 0.9.3-rc2

- **Crash recovery:** interrupted sessions keep the original video untouched and get a canonical
  re-encoded prefix that matches the durable frame journal. Sessions stay `INTERRUPTED`; no frames or
  events are invented.
- **Transactional installers:** Linux and Windows per-user install/update with rollback. Recording
  and settings folders are never touched. (Windows script is statically reviewed only.)
- **Release tooling:** signing/notarization helpers, provisional CycloneDX SBOM generator, and a
  fail-closed release evidence gate (`scripts/release_gate.py`).

Full history: [`CHANGELOG.md`](CHANGELOG.md).

## Quick start (from source)

Requires **Python 3.11–3.14** and **FFmpeg** with `libx264` and `ffprobe` on your `PATH`.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps --no-build-isolation -e .
python -m playwright install chromium   # optional: managed-browser capture
python -m idra diagnostics
python -m idra gui
```

Platform notes: [`docs/MACOS_SETUP.md`](docs/MACOS_SETUP.md) and [`docs/PLATFORMS.md`](docs/PLATFORMS.md).

### Building a local app

There are no prebuilt binaries in this repository. To build one yourself:

- **macOS:** run `Build IDRA (macOS).command`
- **Linux:** run `./build-idra-linux.sh`, then `packaging/linux/install.sh`
- **Windows:** run `Build IDRA (Windows).bat`, then `packaging/windows/Install IDRA.cmd`

Builds you make are unsigned and for personal/testing use. Read the licensing note below before
sharing them.

### Synthetic demo (no screen capture)

Runs a watermarked synthetic capture through the real encoder, journal, validator and exporter
without touching your screen or importing Qt:

```bash
PYTHONPATH=src python -m idra --storage ./demo-recordings demo --seconds 3 --export ./demo-dataset
PYTHONPATH=src python -m idra verify-export ./demo-dataset
```

## Recording workflow

1. **Settings / diagnostics:** pick a private local storage folder, check FFmpeg/libx264 and OS
   permissions, and define optional pixel masks.
2. **Recording studio:** enter a session label and task prompt, choose display and sampling rates and
   input channels (mouse on by default, keyboard categories off by default), confirm both consent
   checkboxes, and start.
3. **While recording:** use **Pause** before private content and **Resume** after, add notes or task
   boundaries, then **Stop and finalize** (or `Ctrl+Alt+Shift+F8`).
4. **Session explorer / Timeline:** inspect manifests and frames, recover interrupted sessions, and
   step through events alongside the video.
5. **Dataset studio:** preview trajectories, run quality validation, set deterministic
   train/validation/test splits, and export.

## CLI

```bash
python -m idra --storage ./local-recordings list
python -m idra --storage ./local-recordings inspect SESSION_UUID
python -m idra --storage ./local-recordings validate SESSION_UUID --full-decode
python -m idra --storage ./local-recordings export SESSION_UUID --out ./dataset
python -m idra --storage ./local-recordings export SESSION_UUID --out ./reviewed-dataset --include-media --media-reviewed
python -m idra --storage ./local-recordings recover SESSION_UUID --confirm
python -m idra --storage ./local-recordings retention --days 30
python -m idra --storage ./local-recordings delete SESSION_UUID --confirm
```

## Tests

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m pytest -q
python -m compileall -q src tests scripts packaging
PYTHONPATH=src python scripts/static_audit.py
```

Last recorded rc2 run: 160 passed, 13 skipped, 0 failed (Linux, source tree). Tests that need a real
display, native input hooks or packaging tools skip when those aren't available. See
[`docs/TESTING.md`](docs/TESTING.md).

## Privacy and data handling

- Recordings are stored only in the folder you choose. **Never commit recordings or your
  `~/.idra/settings.json`.** `.gitignore` already excludes `local-recordings/`, `demo-recordings/`
  and `demo-dataset/`.
- Text that looks like secrets (API keys, tokens, PEM keys, passwords) is redacted from captured
  metadata, and URLs are reduced to their origin by default. This is best-effort, not a guarantee;
  review media before sharing an export.
- Details: [`docs/PRIVACY.md`](docs/PRIVACY.md). To report a vulnerability, see [`SECURITY.md`](SECURITY.md).

## Licensing

IDRA's own source is [MIT](LICENSE). Its dependencies are not: **PyQt6** is GPLv3 or commercial, and
FFmpeg builds with **libx264** are GPL. Hosting this source is fine, but distributing built binaries
(for example on GitHub Releases) carries those obligations. See
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and get a license review before shipping builds.

## Project map

```text
src/idra/
  app/              lifecycle controller, runtime, settings, CLI, state machine
  ui/               PyQt6 studio (six screens), consent dialog, widgets, workers
  capture/          MSS and FFmpeg/X11 capture, bounded capture/encode pipeline
  inputs/           privacy-minimized keyboard/mouse hooks, frontmost-app context
  browser/          managed Playwright Chromium context and injected DOM event script
  synchronization/  monotonic session clock and video PTS mapping
  events/           versioned Pydantic v2 schemas (schema 1.0)
  storage/          SQLite WAL indexes, fsync journals, locks, crash recovery
  segmentation/     task boundaries and bounded trajectories
  media/            FFmpeg encode/transcode/clip, OpenCV frame extraction
  datasets/         quality validation, exports, re-import verifier
  privacy/          telemetry minimization, secret redaction, URL sanitizing, pixel masks
  diagnostics/      dependency, permission and ingestion benchmark checks
  logging/          rotating private application logs
docs/  examples/  packaging/  reports/  scripts/  tests/
```

More: [`DOCUMENTATION.md`](DOCUMENTATION.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md),
[`docs/SCHEMA.md`](docs/SCHEMA.md), [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md),
[`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md).

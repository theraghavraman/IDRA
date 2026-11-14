# IDRA v0.9.3-rc2 - Source-only hardening candidate

> **NO-GO: NOT PRODUCTION ACCEPTED.** This rc2 source package adds crash-media reconciliation,
> transactional installers, and release evidence/signing tools. It is not a native signed build.
> Linux virtual-X11 source tests do not replace physical Linux, Windows or macOS acceptance.
> **Required:** [rc2 acceptance ledger](docs/RELEASE_0.9.3_RC2.md) and
> [production release runbook](docs/PRODUCTION_RELEASE_RUNBOOK.md).
> Historical v0.9.2 performance/build claims below are retained only for reference.

# Intelligent Data Recording Agent (IDRA)

**Version 0.9.2 | Local-first desktop recording and dataset preparation**

> **Start here: [`DOCUMENTATION.md`](DOCUMENTATION.md).**
> - **macOS (Apple Silicon / Intel):** Open `dist/IDRA-0.9.2-macos-arm64.dmg` (or drag `dist/IDRA.app` to Applications), or rebuild via `Build IDRA (macOS).command`.
> - **Linux:** Extract `IDRA-0.9.2-linux-x86_64.tar.gz` and run `./install.sh`, or build via `./build-idra-linux.sh`.
> - **Windows:** Double-click `Build IDRA (Windows).bat`, then run `Install IDRA.cmd`.
> - **What changed:** [`CHANGELOG.md`](CHANGELOG.md).

IDRA captures an explicitly authorized desktop session, records privacy-minimized mouse, keyboard-category, window-context, and managed-browser metadata, encodes H.264 media, and exports validated computer-use trajectories.

## Release Highlights (0.9.2 Modernized)

- **Modern Studio Interface:** All six PyQt6 workspace screens (`Dashboard`, `Recording studio`, `Session explorer`, `Timeline`, `Dataset studio`, `Settings / diagnostics`) feature a dark obsidian/slate design system with live state pill badges, structured cards, monospace JSON inspectors, dark video/frame preview monitors, and non-blocking background workers.
- **Verified Cross-Platform & macOS arm64 Build:** Automated test suite passes with **145 passed, 0 failed, 0 errors** on macOS Apple Silicon (`arm64`, Python 3.13, Qt 6.10.0, FFmpeg with `libx264`) and **146 passed** on Linux `x86_64` with isolated X11 capture.
- **Hardened Lifecycle & Bug Fixes:** Deterministic startup event ordering (`state_change` precedes Frame 0 and input hooks start after entering `RECORDING`), guaranteed X11 pipe cleanup, loop-safe trajectory stride sampling, defensive form/JSON validation in Studio and Settings, keyboard-navigable Timeline scrubbing, and background job progress isolation.

## Quick Start from Source

Requires **Python 3.11–3.14** and **FFmpeg** (with `libx264` and `ffprobe`) installed on your system:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps --no-build-isolation -e .
python -m playwright install chromium
python -m idra diagnostics
python -m idra gui
```

### Engine-Only Synthetic Demonstration

Runs a watermarked synthetic capture through the real FFmpeg encoder, SQLite/JSONL journal writer, quality validator, and dataset exporter without capturing your screen or importing Qt:

```bash
PYTHONPATH=src python -m idra --storage ./demo-recordings demo --seconds 3 --export ./demo-dataset
PYTHONPATH=src python -m idra verify-export ./demo-dataset
```

## Recording & Dataset Workflow

1. **Settings / diagnostics**: Configure a dedicated private local folder, verify `FFmpeg`/`libx264` and OS permissions, and define optional normalized pixel masks.
2. **Recording studio**: Enter a session label and task prompt, select your display and sampling rates, choose input telemetry channels (mouse on by default; keyboard categories off by default), and click **Start recording**. Confirm both consent checkboxes.
3. **Live Controls & Annotations**: Use **Pause** before opening private content, **Resume** afterward, add live notes or task boundaries (`Start task` / `Mark task complete`), and click **Stop and finalize** (or press `Ctrl+Alt+Shift+F8`).
4. **Session explorer & Timeline**: Browse recorded sessions, inspect `manifest.json` and Frame 0 previews, recover interrupted sessions, or step through events alongside synchronized video frames in **Timeline**.
5. **Dataset studio**: Preview segmented trajectories, run quality validation (`reports/quality.json` & `reports/quality.html`), configure deterministic `train`/`validation`/`test` splits, and export portable datasets.

## Useful CLI Commands

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

## Tests & Quality Checks

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m pytest -q
python -m compileall -q src tests scripts packaging
PYTHONPATH=src python scripts/static_audit.py
PYTHONPATH=src python scripts/benchmark.py --minimum-seconds 5
```

## Project Map

```text
src/idra/
  app/                lifecycle controller, runtime helpers, settings, CLI, state machine
  ui/                 modernized six-screen PyQt6 studio, consent modal, custom widgets, workers
  capture/            MSS, explicit FFmpeg/X11 fallback, bounded capture/encode pipeline
  inputs/             privacy-minimized keyboard/mouse hooks and frontmost app-context watcher
  browser/            managed Playwright Chromium context and injected DOM event script
  synchronization/    monotonic session clock and nominal CFR video PTS mapping
  events/             strict versioned Pydantic v2 schemas (Schema 1.0)
  storage/            SQLite WAL indexes, fsync append journals, advisory locks, crash recovery
  segmentation/       task boundaries and deterministic bounded trajectories
  media/              FFmpeg H.264 encoding, transcoding, clipping, and OpenCV frame extraction
  datasets/           streaming quality validation, portable exports, and re-import verifier
  privacy/            telemetry minimization, secret regex redaction, URL sanitization, pixel masks
  diagnostics/        dependency, permission, and bounded ingestion benchmark checks
  logging/            rotating private application logs
tests/ scripts/ docs/ examples/ reports/ packaging/
```

Detailed engineering references: [`DOCUMENTATION.md`](DOCUMENTATION.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/SCHEMA.md`](docs/SCHEMA.md), [`docs/PRIVACY.md`](docs/PRIVACY.md), [`docs/PLATFORMS.md`](docs/PLATFORMS.md), [`docs/MACOS_SETUP.md`](docs/MACOS_SETUP.md), [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md), [`docs/TESTING.md`](docs/TESTING.md), [`docs/ACCEPTANCE.md`](docs/ACCEPTANCE.md).

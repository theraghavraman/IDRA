# IDRA 0.9.1 - Test and build report

Recorded: 2026-10-18 (UTC). Environment: Python 3.12.3, Linux x86_64, FFmpeg 6.1.1 (libx264), Qt 6.10.0. Details in `environment.json`.

**Classification: tested source release with Apple Silicon packaging. Not yet executed on macOS hardware; production acceptance not claimed.**

## Test suite

| Result | Count |
|---|---:|
| Passed | 142 |
| Failed | 0 |
| Skipped | 7 |
| Collected | 149 |

Statement coverage: **72.07%** (0.9.0: 56.88%), mainly because the GUI and native tests now execute. Raw evidence: `pytest-output.txt`, `pytest.xml`, `coverage.json`.

Skipped: six managed-browser tests (Playwright's Chromium download is blocked in this environment) and one test that applies only when Qt is absent.

New in this run compared with 0.9.0:
- All 8 GUI tests ran (0.9.0: all skipped). They gave 12 consecutive clean runs after fixing two start-up and quit races that caused intermittent hangs.
- Native MSS capture and native pynput hooks ran on an isolated Xvfb display (0.9.0: skipped).
- Eleven new tests in `tests/test_runtime.py` and two in `tests/test_gui.py` cover every 0.9.1 fix. macOS-only paths are exercised through controlled fakes.

## End-to-end recording (manual harness, isolated Xvfb 1280x720)

The real `MainWindow` recorded with native MSS capture and live pynput mouse hooks. The harness generated real mouse moves and clicks with xdotool, then ran start → pause → resume → stop. The result was **COMPLETED**: 29 frames, 22 events (6 clicks), and full-decode validation with 0 errors, 0 warnings and 0 dropped frames. Export and re-import verification passed. Before the 0.9.1 fix, the same run ended **FAILED** (`INPUT_SHUTDOWN_TIMEOUT`).

## Frozen application

`packaging/macos/IDRA.spec` was built with PyInstaller 6.22.3 on Linux, which is the same spec the Mac build uses. With a minimal environment (`env -i`, PATH=/usr/bin:/bin), the frozen executable passed these checks:
- synthetic record → encode → export → verify-export
- diagnostics, with all package versions reported from bundled metadata
- the CLI help
- GUI launch on X11 and offscreen
- launch with a corrupt settings file (the file was preserved and defaults were used)

No errors or native crashes were logged.

## Build script

`packaging/macos/build_macos_app.sh` passes `bash -n` and shellcheck. A run on a simulated Mac (stubbed `uname`/`sw_vers`) completed every step up to PyInstaller: Python discovery, FFmpeg/libx264 check, clean environment install, and the full test suite (142 passed). This run caught and fixed a pipefail defect that would have stopped the build on every Mac. The PyInstaller, signing, smoke-test and DMG steps require macOS.

## Static checks

- **ruff** (first run for this project): no remaining pyflakes or bugbear defects in `src/` except one reviewed false positive. That finding is B023, about a closure that is invoked within its own loop iteration. Unused imports were removed. Import-order and one-line-statement style findings were left as is.
- **mypy:** the findings are typing gaps in untyped code (Optional narrowing, Windows-only ctypes, Qt stubs). One finding was a real latent defect, a spin box that shadowed `QWidget.width()`, and it was fixed.
- **AST audit:** `static-audit.json`.

## Benchmark

`benchmark.json` records a five-second synthetic journal-ingestion measurement of about 7,700 events/second with no dropped events. This exceeds the 1,000 events/second target. It is not a desktop capture benchmark.

## Outstanding (requires a Mac)

- macOS permission prompts and the TCC workflow in the packaged app
- the pynput keyboard guard on macOS 14 and later
- MSS on Retina and multi-monitor setups, including coordinate calibration
- Qt multimedia playback on macOS
- managed-browser HTTP navigation
- multi-hour soak testing, sleep/wake, and display hotplug
- signing and notarization for distribution to other Macs

The build script's tests and smoke test are the first check. `MAC_APP_GUIDE.md` lists the recommended first-use steps.

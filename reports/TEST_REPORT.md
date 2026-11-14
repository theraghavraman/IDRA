# IDRA 0.9.2 - Test and Build Report

Updated 2026-10-18 on **macOS Apple Silicon (`arm64`, Python 3.13.16, PyQt6 6.10.0, FFmpeg with `libx264`)** and **Linux `x86_64` (Python 3.12.3, FFmpeg 6.1.1, Qt 6.10.0)**. Earlier reports are archived in `0.9.0/` and `0.9.1/`.

## Automated Test Suite Summary

| Environment | Passed | Failed | Errors | Skipped | Notes |
|---|---:|---:|---:|---:|---|
| **macOS `arm64` (Python 3.13.16)** | **145** | **0** | **0** | **10** | Includes all 10 PyQt6 GUI tests (`tests/test_gui.py`), lifecycle, crash recovery, media, dataset export/verification, and runtime tests. Skips are 6 Chromium tests (when Chromium binary is not installed), 3 Linux Xvfb-only tests, and 1 missing-Qt-only test. |
| **Linux `x86_64` (Python 3.12.3)** | **146** | **0** | **0** | **7** | Includes offscreen GUI tests and isolated Xvfb native MSS + `pynput` capture tests. |

## New Verification & Bug-Fix Coverage in 0.9.2 (Updated)

- **Modernized PyQt6 Studio UI (`tests/test_gui.py`)**:
  - Verified 6-screen navigation, status pill transitions, `ConsentDialog` dual-checkbox gating, responsive `QThread` workers, worker cancellation, full synthetic recording (`start` -> `pause` -> `resume` -> `stop`), exception hook dialogs, unavailable storage fallback, whitespace mask & X11 region validation (`test_settings_and_studio_validation_edge_cases`), and empty selection inspector cleanup (`test_library_empty_selection_clears_inspector`).
- **Controller & Pipeline Fixes**:
  - Verified initial `state_change` (`RECORDING`) event ordering prior to Frame 0 and immediate input readiness upon entering `RECORDING`.
  - Verified guaranteed `stdout` pipe closure in `FFmpegX11Source.close()`.
  - Eliminated the `Ruff B023` loop-variable closure in `trajectories()`.
- **Sandboxed Browser Fixture Resilience (`tests/test_browser.py`)**:
  - Fixed `web_page` fixture setup so environments that restrict local TCP socket binding (`PermissionError` / `OSError`) degrade gracefully instead of failing with a setup error.

## Static & Packaging Verification

- **Static AST & Bytecode Audit (`scripts/static_audit.py`)**: `status: passed` across all **51 Python modules** in `src/` (0 syntax errors, 0 unsafe `eval`/`exec`/`os.system`/`os.popen` calls, 0 `shell=True` calls).
- **macOS Native App Bundle (`dist/IDRA.app` & `dist/IDRA-0.9.2-macos-arm64.dmg`)**: Rebuilt with the modernized UI and bug fixes, ad-hoc code-signed (`codesign --verify --deep --strict`), and smoke-tested end-to-end (`diagnostics`, `demo`, `export`, `verify-export`).

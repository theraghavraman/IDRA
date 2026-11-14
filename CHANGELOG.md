## 0.9.3-rc2 (source-only; release acceptance pending)

- Improved interrupted-session recovery: preserve untouched video, optionally re-encode a
  checksum-tracked canonical prefix only when the durable frame journal is contiguous and
  contains fewer frames than salvageable video. Never synthesize missing frames or mark
  the session `COMPLETED`; require interrupted-session export opt-in and review.
- Transactional Linux and Windows per-user install/update scripts with rollback and no
  automatic removal of Windows Mark-of-the-Web. Linux upgrade and rollback tested locally;
  Windows installer execution remains pending native acceptance.
- Native signing/notarization operator helpers and `--package-only` builder option,
  preserving external signatures across packaging (tools not executed on Windows/macOS here).
- Source-level provisional CycloneDX environment inventory and fail-closed multi-platform
  release evidence gate. Neither substitutes for a binary SBOM, actual signature verification,
  software license clearance or release-owner approval.
- Added recovery video tail, installer rollback, release evidence and tampering regressions.

## 0.9.3-rc1 (source-only; production acceptance pending)

- Repackaged source with an independently verifiable per-file SHA-256 inventory (pending final build).
- Redacted complete PEM private-key blocks, including unclosed and truncated text.
- Added a minimal emergency-stop hotkey listener independent of keyboard telemetry opt-in;
  platform permissions can prevent activation, in which case the interface/manifest reports it.
- Removed unverified page-supplied `is_trusted` claims from managed-browser action records;
  all binding-sourced actions are explicitly observed-only, and trajectories count them as
  unverified browser actions. This is provenance labeling, **not proof of human action**.
- Added regression tests for multiline redaction, stop-listener privacy and forged browser trust.
- Maintained the 0.9.2 dataset schema and modular architecture. No packaged Windows/macOS
  acceptance tests or external license audit were performed for this candidate.

# Changelog

## 0.9.2 (Updated) - 2026-10-18

UI modernization, architectural audit, bug fixes, macOS arm64 verification, and cross-platform packaging.

### UI Modernization & UX Standards
- Redesigned all six PyQt6 workspace screens (`Dashboard`, `Recording studio`, `Session explorer`, `Timeline`, `Dataset studio`, `Settings / diagnostics`) and `ConsentDialog` with a cohesive dark obsidian/slate studio design system (`#0B0F17` canvas, `#111827` elevated cards, `#10B981` emerald primary actions, `#DC2626` danger controls).
- Added a structured top header bar with live state pill badges (`IDLE`, `STARTING`, `RECORDING`, `PAUSED`, `STOPPING`, `COMPLETED`, `FAILED`, `INTERRUPTED`), a dedicated navigation sidebar with emergency shortcut reference, and a non-contending bottom activity/progress bar.
- Upgraded `Session explorer`, `Timeline`, `Dataset studio`, and `Settings / diagnostics` with monospace JSON inspectors (`monoEditor`), dark video/frame preview monitors (`previewBox`), semantic state coloring in tables, and a native directory browser (`Browse...`) for local storage selection.

### Bug Fixes
- **Controller Startup Ordering (`idra.app.controller`)**: Queued the initial `state_change` (`RECORDING`) event immediately after journal start, transitioned to `RECORDING` before starting input/context listeners so early input events are never dropped and Frame 0 never precedes the `RECORDING` state event, and reset `self.session_lock` cleanly across sessions.
- **X11 Capture Pipe Cleanup (`idra.capture.sources`)**: Guaranteed `p.stdout.close()` inside a `try...finally` block in `FFmpegX11Source.close()` even if process termination times out.
- **Trajectory Stride Closure (`idra.segmentation.trajectories`)**: Bound `target_t_ns=event.t_ns` explicitly in `sampled()` to eliminate the loop-variable closure hazard (`Ruff B023`).
- **Studio Display Fallback (`idra.ui.studio`)**: Prevented `TypeError` when `self.monitor.currentData()` is `None` or display enumeration returns no rows, while preserving monitor selection across refreshes.
- **Settings Validation (`idra.ui.settings_page`)**: Fixed `JSONDecodeError` when the pixel masks editor contains only whitespace and added explicit validation for four comma-separated integers on the X11 region field.
- **Library Selection & Recovery Sync (`idra.ui.library`, `idra.ui.window`)**: Cleared stale manifest JSON and frame preview when all sessions are deselected or deleted, and automatically refreshed the session list after crash recovery or failed recording startup.
- **Timeline Keyboard Navigation & Pagination (`idra.ui.timeline`)**: Enabled Up/Down keyboard arrow navigation in the event table via `currentCellChanged` and prevented forward pagination from stranding the view on an empty page when event count is a multiple of 500.
- **Background Worker Progress Isolation (`idra.ui.window`)**: Prevented parallel read-only background jobs from overwriting the footer status text and progress bar of active blocking jobs.
- **Quality HTML Report (`idra.datasets.quality`)**: Added the issue `Line` column and clean embedded stylesheet to `reports/quality.html`.
- **Browser Test Fixture & Offline Builder (`tests/test_browser.py`, `packaging/build_app.py`)**: Handled restricted local socket binding (`OSError` / `PermissionError`) gracefully in `web_page` fixture setup so in-memory tests and skip checks do not error out, and allowed `build_app.py` to reuse pre-installed virtualenv packages when offline.

### Cross-Platform Packaging (0.9.2 Base)
- One cross-platform builder, `packaging/build_app.py` (standard library only), with double-click launchers `Build IDRA (macOS).command`, `Build IDRA (Windows).bat` and `build-idra-linux.sh`.
- Windows package: `IDRA.exe` (windowed) plus `idra-cli.exe` (console), FFmpeg bundled, and per-user installer/uninstaller scripts.
- Linux package: per-user `install.sh` and `uninstall.sh`, applications-menu entry, `idra` command, and Wayland detection before recording.
- macOS Apple Silicon (`arm64`) package: `dist/IDRA.app` and `dist/IDRA-0.9.2-macos-arm64.dmg` built, ad-hoc signed, and verified.

## 0.9.1 - 2026-10-18

Stability release and Apple Silicon desktop app packaging.

Fixed:
- Keyboard capture could never start on macOS: the permission check read pynput's class-level `IS_TRUSTED`, which is always False before a listener runs. It now queries Accessibility/Input Monitoring status from the OS.
- Process abort on macOS 14+ when keyboard capture starts: pynput 1.8.x reads the keyboard layout (Text Input Source APIs) on its listener thread, which macOS terminates. The layout context is now computed once on the main thread at start-up.
- FFmpeg/ffprobe not found when the app is opened from Finder (minimal PATH). Lookup now covers bundled binaries, PATH, /opt/homebrew/bin, /usr/local/bin and /opt/local/bin.
- An unhandled exception in any GUI slot aborted the application (PyQt6 qFatal). Exceptions from the GUI and worker threads are now logged and shown as a dialog; recording continues. Native crashes are written to logs/native-crash.log.
- A corrupt settings file prevented launch. It is now preserved as settings.json.unreadable-<timestamp> and defaults are used, with a notice.
- An unavailable storage folder (e.g. disconnected drive) prevented launch. The GUI falls back to ~/IDRA-recordings for that session, with a notice.
- A complete recording was marked FAILED when an input listener exited slowly (reproduced on X11 in an end-to-end GUI recording). Slow listener shutdown is now a manifest warning, and X11 listeners are woken so they exit promptly.
- Start-up race: the initial session listing blocked recording controls and could trigger "Another operation is active"; quitting during it raised an unnecessary prompt. Read-only background listings are now non-blocking and cancelled silently on quit.
- Recording studio replaced QWidget.width() with a spin box attribute; renamed.
- Diagnostics in a packaged app reported every Python package as missing; package metadata is now bundled and diagnostics falls back to module versions.

## 0.9.0 - 2026-10-16

Initial integrated source release: strict minimized event/frame/session/trajectory models; common timebase; bounded native/synthetic capture adapters and FFmpeg encoder; one durable journal writer with rebuildable indexes; consent-based lifecycle and recovery; six PyQt6 screens; managed Playwright instrumentation; real FFmpeg/OpenCV transforms; quality validation; deterministic trajectories/splits; metadata-only or explicitly reviewed-media export; re-import checks; diagnostics, tests, synthetic examples and source release tooling.

# Architecture and lifecycle

## Boundaries and layered design

IDRA is structured around strict separation between presentation, orchestration, capture/telemetry ingestion, durable storage, and dataset preparation:

1. **Desktop UI Layer (`idra.ui`)**:
   - Owns the six PyQt6 workspace screens (`DashboardPage`, `StudioPage`, `LibraryPage`, `TimelinePage`, `DatasetPage`, `SettingsPage`), the consent modal (`ConsentDialog`), system tray controls, and the design system (`window.py`, `widgets.py`).
   - Submits all blocking I/O, capture startup, validation, recovery, media processing, and export work to `QThread` workers (`Worker`).
   - Separates blocking user-initiated operations from parallel read-only background jobs (such as session listings and frame previews) so background updates never overwrite active operation progress or block recording controls.
2. **CLI Layer (`idra.app.cli`)**:
   - Exposes every engine capability (`gui`, `diagnostics`, `record`, `demo`, `list`, `rescan`, `inspect`, `recover`, `delete`, `retention`, `validate`, `export`, `verify-export`, `process`) without importing Qt unless `gui` is invoked.
3. **Runtime Layer (`idra.app.runtime`)**:
   - Handles cross-platform executable resolution (app bundle `bin/`, `PATH`, Homebrew, MacPorts, WinGet, Chocolatey, Scoop), macOS TCC permission preflight and prompts (`Screen Recording`, `Accessibility`, `Input Monitoring`), the macOS 14+ `pynput` main-thread Text Input Source guard, Windows hidden-console subprocess flags (`CREATE_NO_WINDOW`), Wayland detection on Linux, and `faulthandler` native crash logging.
4. **Session Controller (`idra.app.controller`)**:
   - Owns a single recording session's state machine, shared monotonic/UTC clock (`SessionClock`), capture pipeline, append-only journal writer, input listeners, optional window-context watcher, and optional managed Playwright browser.

`ScreenSource` defines `open()`, `grab()`, `close()`, `interrupt()`, geometry, timestamp kind, and synthetic provenance. `MSSSource` captures monitor pixels on the capture thread; `FFmpegX11Source` is an explicit Linux/X11 fallback with guaranteed pipe cleanup. `SyntheticSource` is restricted to `demo` and automated tests and must match the manifest's `synthetic` flag.

## Capture and journaling pipeline

The capture worker acquires a frame, checks display geometry stability and minimum free disk reserve, resizes to even output dimensions, applies normalized solid pixel masks (`apply_masks`), and submits the masked frame to a bounded queue. The encoder worker streams raw BGR frames to FFmpeg (`libx264` inside Matroska `.mkv`), writes periodic PNG keyframes, computes SHA-256 and Laplacian-variance blur scores, and submits `Frame` metadata to the journal.

A single `Journal` worker batches strict Pydantic model serialization (`Event` and `Frame`) to canonical JSONL files (`events.jsonl`, `frames.jsonl`) and rebuildable SQLite indexes (`index.sqlite3`). The SQLite transaction is committed only after journal `flush()` and `os.fsync()`. Frame metadata uses bounded waiting; event submissions under extreme queue pressure are rejected and counted rather than hidden.

## Recording state machine

`IDLE -> STARTING -> RECORDING <-> PAUSED -> STOPPING -> COMPLETED` with explicit `FAILED` and `INTERRUPTED` outcomes:

- Consent is verified before entering `STARTING`.
- During startup, the journal opens first, the initial `state_change` (`RECORDING`) event is queued at the start of the timeline, the capture pipeline verifies its first frame, and the controller transitions to `RECORDING` before input and context hooks begin emitting events so early user actions are never dropped.
- Startup cancellation coordinates with the startup thread via `start_done` so `stop()` never races with in-flight component creation.
- `pause()` transitions to `PAUSED`, halting event acceptance and closing the screen source; `resume()` reopens the screen source and resumes capture. No synthetic blank frames are inserted for paused intervals.
- `stop()` halts input, context, browser, and capture/encoder workers in deterministic order, flushes and closes the journal, verifies output media, computes SHA-256 checksums, persists the final `Manifest`, and releases the per-session advisory lock (`.session.lock`).

## Storage layout

```text
<private-root>/
  library.sqlite3
  logs/
    application.log
    native-crash.log
  sessions/<uuid>/
    manifest.json
    events.jsonl
    frames.jsonl
    index.sqlite3
    .session.lock
    media/screen.mkv
    media/frames/frame_XXXXXXXX.png
    processed/                 derived media from GUI/CLI processing
    reports/quality.json
    reports/quality.html
    reports/recovery.json
```

All directories are created with `0700` permissions and files with `0600` on POSIX systems. Symlinks and path traversal segments (`..`, backslashes, drive prefixes) are rejected by `contained()`.

## Synchronization

Host monotonic timestamps (`t_ns` from `perf_counter_ns`) are authoritative; `utc` is derived from the session's initial UTC anchor. Frames record `capture_started_t_ns`, `t_ns` (acquisition completion or receive time), and nominal constant-frame-rate playback `pts_ns`. Consumers join events to frames via `frame_index` and `t_ns` (using `neighboring_frames` within a 3-second bound).

Playwright DOM instrumentation runs exclusively inside IDRA's explicitly launched Chromium context. Calibration runs on the browser owner loop (`calibrate_pages`), never inside synchronous JS binding callbacks, preventing callback reentrancy deadlocks.

## Fault containment, validation, and recovery

After an abnormal exit or crash, `recover()` acquires `.session.lock`, quarantines any incomplete trailing JSONL line into `reports/partial_*.bin`, truncates the journal to the last complete newline, rebuilds `index.sqlite3` from schema-valid canonical records, salvages readable `screen.partial.mkv` video if valid, and marks the session `INTERRUPTED`.

`validate_session()` cross-checks canonical JSONL records against `index.sqlite3`, verifies sequence monotonicity, coordinate bounds, redaction compliance, screenshot and media SHA-256 digests, and video frame counts, emitting both `reports/quality.json` and a styled `reports/quality.html`.

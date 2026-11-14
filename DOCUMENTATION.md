> **2026-11-10 candidate notice:** The sections below describe the historical 0.9.2 product.
> The latest source-only rc2 candidate remains **NO-GO** for production. Follow
> `docs/RELEASE_0.9.3_RC2.md` and `docs/PRODUCTION_RELEASE_RUNBOOK.md` instead of assuming
> historical native package verification applies to the updated code.

# IDRA 0.9.2 Documentation & Architecture Reference

IDRA (**Intelligent Data Recording Agent**) is a local-first desktop application and CLI engine that records explicitly authorized screen sessions alongside privacy-minimized mouse, keyboard, window-context, and managed-browser metadata, transforming raw interactions into validated, deterministic datasets of computer-use trajectories. It runs natively on **macOS** (Apple Silicon & Intel), **Windows 10/11**, and **Linux (X11)**. Every recording, index, and exported dataset stays strictly on your computer: IDRA contains no cloud upload or telemetry code, and requires no paid developer certificate to build or run.

## Contents

1. [Downloads & Quick Start at a Glance](#1-downloads--quick-start-at-a-glance)
2. [System Requirements](#2-system-requirements)
3. [Installation & Building from Source](#3-installation--building-from-source)
4. [First Launch & Operating System Permissions](#4-first-launch--operating-system-permissions)
5. [Modern Studio UI & Operational Workflow](#5-modern-studio-ui--operational-workflow)
6. [Command-Line Reference](#6-command-line-reference)
7. [Storage Architecture & Portable Dataset Layout](#7-storage-architecture--portable-dataset-layout)
8. [Privacy, Redaction & Threat Model](#8-privacy-redaction--threat-model)
9. [System Architecture & Lifecycle Analysis](#9-system-architecture--lifecycle-analysis)
10. [Quality Validation, Trajectory Segmentation & Bug Fixes](#10-quality-validation-trajectory-segmentation--bug-fixes)
11. [Troubleshooting](#11-troubleshooting)
12. [Uninstalling](#12-uninstalling)
13. [Verification Status & Known Limitations](#13-verification-status--known-limitations)

---

## 1. Downloads & Quick Start at a Glance

| Platform | What You Receive | Action |
|---|---|---|
| **macOS 13+** (Apple Silicon `arm64` / Intel `x86_64`) | Source package with one-click builder & prebuilt `dist/IDRA-0.9.2-macos-arm64.dmg` (`dist/IDRA.app`) | Open `dist/IDRA-0.9.2-macos-arm64.dmg` and drag **IDRA** to **Applications**, or double-click `Build IDRA (macOS).command` to rebuild (Section 3.3) |
| **Linux x86_64** | Ready-made installer tarball (`IDRA-0.9.2-linux-x86_64.tar.gz`) or `./build-idra-linux.sh` | Extract and run `./install.sh` (Section 3.1) or build via `./build-idra-linux.sh` (Section 3.4) |
| **Windows 10/11 (x64)** | Source package with one-click builder (`Build IDRA (Windows).bat`) | Double-click `Build IDRA (Windows).bat`, then run `Install IDRA.cmd` from the generated zip (Section 3.2) |

The cross-platform builder (`packaging/build_app.py`) compiles native bundles on the target OS, runs the automated test suite, freezes the application with PyInstaller, smoke-tests the binary (`diagnostics` -> `demo` -> `export` -> `verify-export`), and packages the native installer.

---

## 2. System Requirements

| Requirement | macOS | Windows | Linux |
|---|---|---|---|
| **Operating System** | macOS 13 Ventura or newer | Windows 10 or 11 (64-bit) | X11 desktop session; prebuilt binary targets glibc 2.39+ (Ubuntu 24.04+, Debian 13+, Fedora 40+) |
| **Processor** | Apple Silicon (`arm64`) or Intel (`x86_64`) | `x64` | `x86_64` prebuilt; any architecture when built from source |
| **FFmpeg with H.264 (`libx264`)** | Installed automatically via Homebrew or resolved from `/opt/homebrew/bin` / `/usr/local/bin` | Installed automatically via `winget` (`Gyan.FFmpeg`) and bundled into the app | Distribution `ffmpeg` package with `libx264` |
| **Build Prerequisites** | Python 3.11–3.14 & Homebrew | Python 3.11–3.14 & `winget` | Python 3.11–3.14 with `venv` |
| **Disk Space** | ~1.5 GB for build environment + storage for recordings (default 1024 MiB stop reserve) | Same | Same |
| **OS Permissions** | Screen Recording (required); Accessibility & Input Monitoring (for mouse/keyboard metadata) | None | Local X11 display access |

---

## 3. Installation & Building from Source

### 3.1 Linux: Prebuilt App

```bash
tar -xzf IDRA-0.9.2-linux-x86_64.tar.gz
cd IDRA-0.9.2-linux-x86_64
./install.sh
```

Installs to `~/.local/share/IDRA` without `sudo`, registers a desktop launcher, and links `idra` into `~/.local/bin`. Ensure `ffmpeg` is installed (`sudo apt install ffmpeg`, `sudo dnf install ffmpeg`, or `sudo pacman -S ffmpeg`).

### 3.2 Windows: Build & Install

1. Extract the project archive.
2. Double-click **`Build IDRA (Windows).bat`**. Missing Python 3.13 or FFmpeg dependencies are installed via `winget`, and FFmpeg is bundled inside the resulting application.
3. Extract `dist\IDRA-0.9.2-windows-x64.zip` and double-click **`Install IDRA.cmd`**.
4. If Windows SmartScreen prompts *"Windows protected your PC"*, click **More info > Run anyway** (shown once for unsigned local builds).

The installer copies IDRA to `%LOCALAPPDATA%\Programs\IDRA`, creates Start Menu and Desktop shortcuts, and adds `idra-cli` to your user `PATH`.

### 3.3 macOS: Install or Rebuild

1. To install the built bundle directly, open `dist/IDRA-0.9.2-macos-arm64.dmg` and drag **IDRA.app** to **Applications**.
2. To rebuild from source, double-click **`Build IDRA (macOS).command`** or run:
   ```bash
   python3 packaging/build_app.py
   ```
3. The builder verifies Python 3.11–3.14 and FFmpeg (`libx264`), reuses or creates the build virtual environment (`build/venv-macos-arm64`), runs the automated test suite, packages `dist/IDRA.app` with an ad-hoc local code signature (`codesign --sign -`), executes the end-to-end smoke test, and produces `dist/IDRA-0.9.2-macos-arm64.dmg`.

### 3.4 Building from Source with Custom Flags

```bash
./build-idra-linux.sh                 # Linux wrapper
python3 packaging/build_app.py        # Direct cross-platform builder
```

| Builder Flag | Effect |
|---|---|
| `--skip-tests` | Skip running the `pytest` suite prior to packaging |
| `--no-browser` | Skip downloading Playwright Chromium (managed-browser capture remains optional) |
| `--no-bundle-ffmpeg` | Do not copy static FFmpeg binaries into the bundle; rely on system FFmpeg |
| `--no-package` | Produce `dist/IDRA.app` or `dist/IDRA/` without creating the outer `.dmg` / `.zip` / `.tar.gz` |

---

## 4. First Launch & Operating System Permissions

- **macOS**:
  1. Launch **IDRA** and open **Settings / diagnostics**.
  2. Click **Screen Recording...**, enable **IDRA** in **System Settings > Privacy & Security > Screen Recording**, then quit (`Cmd+Q`) and relaunch IDRA.
  3. For mouse and keyboard category metadata, click **Accessibility...** and **Input Monitoring...**, enable **IDRA**, and relaunch.
  4. Click **Run diagnostics (no capture)** to confirm `FFmpeg`, `H.264 encoder`, and `screen_recording` report `PASS`.
- **Windows**: No special OS permissions are required. Keyboard telemetry records only normalized key categories (`modifier`, `navigation`, `editing`, `function`, `protected`), never typed characters.
- **Linux**: Requires an **X11 (`Xorg`)** desktop session. If running Wayland, IDRA detects `XDG_SESSION_TYPE=wayland` (or `WAYLAND_DISPLAY` without `DISPLAY`) and displays an actionable guide to switch to Xorg at login.

---

## 5. Modern Studio UI & Operational Workflow

IDRA features a dark obsidian/slate **Local-First Studio UI** designed for clarity, high-contrast telemetry visibility, and non-blocking responsiveness:

- **Persistent Top Header Bar**: Displays the application identity, `LOCAL-FIRST STUDIO` badge, privacy posture summary, a dynamically colored state pill (`IDLE`, `STARTING`, `RECORDING`, `PAUSED`, `STOPPING`, `COMPLETED`, `FAILED`, `INTERRUPTED`), and the always-accessible **`STOP AND FINALIZE`** emergency control.
- **Left Navigation Sidebar**: Provides one-click switching across the six operational workspaces and displays the emergency stop shortcut (`Ctrl+Alt+Shift+F8`).
- **Bottom Activity & Progress Bar**: Tracks active background worker threads (`QThread`) with a progress bar and **`Cancel operation`** button. Read-only background tasks (such as session table refreshes and frame previews) run in parallel without overwriting active foreground operation status.

### The Six Operational Screens

| Screen | Capabilities & Layout |
|---|---|
| **1. Dashboard** | Live pipeline status banner (state, output resolution, bounded frame/record queue depths, privacy/failure alerts), a 4×2 grid of real-time metric cards (`Session Time`, `Encoded Frames`, `Mouse / Scroll Events`, `Key Categories`, `Screenshots`, `Disk Free`, `Dropped Frames / Events`, `Managed Browser`), and a color-coded **Recent sessions** table. |
| **2. Recording studio** | Top **Recording Transport Bar** (`Start recording`, `Pause`, `Resume`, `Stop and finalize`, live status summary), a two-column configuration grid (**Session & Display Capture** on the left; **Telemetry Channels & Managed Playwright Browser** on the right), and a **Live Task Boundaries & Annotations** bar (`Add note`, `Start task`, `Mark task complete`). |
| **3. Session explorer** | Search and filter bar (`Search / refresh`, `Rescan storage`), quick actions (`Open folder`, `Timeline / play`, `Recover interrupted`, `Delete selected`), a multi-select sessions table with semantic state badges, and a split inspector pairing a monospace **Session Manifest & Provenance (JSON)** viewer with a dark **Canonical Video Frame 0 Preview** monitor. |
| **4. Timeline** | Integrated `QtMultimedia` video player with seek bar (when supported by the platform), event-type and time-window filter bar with pagination (`Apply`, `Previous`, `Next`), keyboard- and click-navigable event table, and a synchronized split inspector displaying the **Event Record Payload (JSON)** beside the decoded **Synchronized Recorded Frame** and PTS mapping. |
| **5. Dataset studio** | Side-by-side cards for **Trajectory Segmentation & Splits** (inactivity threshold, frame-context stride, max actions, navigation boundaries, session vs. task split unit, ratios, deterministic seed) and **Export Policy & Quality Validation** (media inclusion, explicit visual review attestation, interrupted-session opt-in, full video decode check), a monospace JSON output console, and a **Media Processing** panel (`inspect`, `transcode`, `extract`, `clip`). |
| **6. Settings / diagnostics** | Side-by-side cards for **Storage, Executables & Retention** (with a `Browse...` directory selector, FFmpeg/FFprobe/Chromium paths, disk stop reserve, retention days, X11 display/region) and **Privacy Minimization & Pixel Masks** (URL origin vs. path policy, opt-in browser labels/titles, JSON normalized pixel masks), paired with configuration/retention tools, one-click macOS permission helpers, and a JSON diagnostics console. |

---

## 6. Command-Line Reference

Global flags (`--storage <folder>`, `--settings <file>`) precede the subcommand:

```bash
idra [--storage PATH] [--settings FILE] <command> [options]
```

| Command | Purpose |
|---|---|
| `gui` | Launch the PyQt6 desktop studio (default when no subcommand is given) |
| `diagnostics [--probe-screen --consent] [--output FILE]` | Inspect Python pins, FFmpeg/libx264, Chromium, disk reserve, and OS permissions; optionally capture and discard one test frame |
| `record --consent --label NAME [--task TEXT] [--seconds N] [--keyboard] [--no-mouse] [--browser]` | Record a desktop session from the terminal (`Ctrl+C` or `Ctrl+Alt+Shift+F8` stops and finalizes) |
| `demo [--seconds N] [--export DIR]` | Run a watermarked synthetic recording through the real FFmpeg/journal pipeline and optionally export a verified dataset |
| `list [--search TEXT] [--offset N]` | List indexed sessions in reverse chronological order |
| `rescan` | Reconcile `library.sqlite3` with on-disk `sessions/<uuid>/manifest.json` files |
| `inspect SESSION_ID` | Print a session's complete `manifest.json` |
| `validate SESSION_ID [--full-decode] [--strict-timing] [--max-gap S]` | Run streaming schema, index-consistency, coordinate, checksum, and media validation; writes `reports/quality.json` and `reports/quality.html` |
| `export SESSION_ID... --out DIR [--include-media --media-reviewed] [--split-unit session\|task]` | Segment trajectories, assign deterministic splits, export JSONL/CSV/manifest, and run `verify-export` |
| `verify-export DIR` | Independently re-import and verify a portable dataset's checksums, schemas, foreign keys, and media assets |
| `process SESSION_ID inspect\|transcode\|clip\|extract [options]` | Run non-destructive FFmpeg/OpenCV operations into `sessions/<id>/processed/` |
| `recover SESSION_ID --confirm` | Quarantine incomplete JSONL tails, rebuild `index.sqlite3`, salvage readable MKV video, and mark the session `INTERRUPTED` |
| `delete SESSION_ID --confirm` | Atomically move a non-active session to trash and remove it |
| `retention --days N [--apply --confirm]` | Preview or permanently delete sessions older than `N` days |

---

## 7. Storage Architecture & Portable Dataset Layout

### Local Storage Hierarchy

| Item | Default Location |
|---|---|
| **Recordings Root** | `~/IDRA-recordings/` (Windows: `%USERPROFILE%\IDRA-recordings`), configurable in Settings |
| **User Settings** | `~/.idra/settings.json` (corrupt files are backed up as `settings.json.unreadable-<timestamp>` and replaced with safe defaults) |
| **Application & Crash Logs** | `<recordings>/logs/application.log` (rotating) and `<recordings>/logs/native-crash.log` |
| **Installed Application** | macOS: `/Applications/IDRA.app` · Windows: `%LOCALAPPDATA%\Programs\IDRA` · Linux: `~/.local/share/IDRA` |

Each recorded session is isolated under `<recordings>/sessions/<uuid>/` with `0700` directory and `0600` file permissions on POSIX:
- `manifest.json`: Versioned `Manifest` containing state, settings snapshot, consent attestation, geometry, counters, warnings, failure codes, operation log, and SHA-256 checksums.
- `events.jsonl` & `frames.jsonl`: Append-only, `fsync`-backed canonical journals.
- `index.sqlite3`: Rebuildable WAL-mode SQLite index for fast timeline filtering and neighbor frame lookups.
- `.session.lock`: Cross-process advisory lock (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows).
- `media/screen.mkv` & `media/frames/frame_XXXXXXXX.png`: H.264 canonical video and sampled PNG screenshots with pre-applied privacy masks.
- `reports/quality.json`, `reports/quality.html`, `reports/recovery.json`: Validation and crash-recovery reports.

### Portable Export Layout

Exported datasets are staged in a hidden `.partial` directory, verified via `verify_export()`, and atomically renamed to the target folder:
- `manifest.json`: Dataset schema `1.0`, provenance, session summaries, split counts, and SHA-256 file checksums.
- `events.jsonl` & `events.csv`: Sanitized events (with spreadsheet formula injection protection in CSV).
- `frames.jsonl`: Frame metadata with `media_available` flags.
- `trajectories.jsonl`: Bounded action sequences linked to `before_frame` and `after_frame` indices.
- `splits.jsonl`: Deterministic `train`, `validation`, and `test` assignments (`SHA-256(seed + ":" + key)`).
- `assets.jsonl` & `sessions/<uuid>/...`: Included media assets (only when `--include-media --media-reviewed` is attested) and per-session `quality.json`.

---

## 8. Privacy, Redaction & Threat Model

1. **Mandatory Per-Session Consent**: Every GUI and CLI recording requires explicit attestation of recording authorization and visible-content risk.
2. **Strict Telemetry Minimization**:
   - **Keyboard**: Printable characters, keycodes, and scan codes are never read or stored. Keys are mapped strictly to five categories (`modifier`, `navigation`, `editing`, `function`, `protected`). Printable keys record `key_category="protected"` with `key_name=None`.
   - **Clipboard & Raw Text**: Clipboard contents are never accessed. `payload.text` is forbidden on all events except explicit user `annotation` and `task_boundary` events, where known secret patterns (`Bearer ...`, `sk-...`, `AKIA...`, `password=...`, `api_key=...`) are automatically redacted.
   - **Managed Browser**: Instrumentation runs only in IDRA's ephemeral Playwright Chromium context, never in the user's personal browsers. Form values (`.value`), cookies, and DOM snapshots are never read. URLs default to `origin` only (`scheme://host:port`), stripping paths, query strings, fragments, and credentials.
   - **Pre-Storage Pixel Masks**: Normalized rectangular masks (`x`, `y`, `width`, `height` in `[0, 1]`) zero out fixed screen regions in memory before video encoding or PNG writing.

---

## 9. System Architecture & Lifecycle Analysis

```
+-----------------------------------------------------------------------------------+
|                        Presentation & Entry Layer                                 |
|  +-------------------------------------+   +-----------------------------------+  |
|  | PyQt6 Studio GUI (idra.ui.window)   |   | Headless CLI (idra.app.cli)       |  |
|  | 6 Screens + Worker QThreads         |   | 14 Subcommands (Zero Qt import)   |  |
|  +------------------+------------------+   +-----------------+-----------------+  |
+---------------------|----------------------------------------|--------------------+
                      +-------------------+--------------------+
                                          v
+-----------------------------------------------------------------------------------+
|                     Runtime & Session Orchestration Layer                         |
|  Runtime (idra.app.runtime): FFmpeg lookup, macOS TCC & pynput guard, crash log   |
|  SessionController (idra.app.controller):                                         |
|    IDLE -> STARTING -> RECORDING <-> PAUSED -> STOPPING -> COMPLETED / FAILED     |
|    Shared SessionClock (perf_counter_ns + UTC anchor) & SessionLock (.session.lock)|
+----------+------------------------------+------------------------------+----------+
           |                              |                              |
           v                              v                              v
+----------------------+      +-----------------------+      +----------------------+
| CapturePipeline      |      | Input & Context Hooks |      | ManagedBrowser       |
| - Capture thread:    |      | - pynput mouse/kb     |      | - Ephemeral Chromium |
|   MSS / FFmpeg X11   |      |   (categories only)   |      | - JS binding allow-  |
|   -> Resize -> Masks |      | - Global F8 stop hook |      |   list & rate limit  |
| - Encoder thread:    |      | - ContextWatcher:     |      | - Loop-owned clock   |
|   FFmpeg libx264 MKV |      |   frontmost app/PID   |      |   calibration        |
|   + PNG keyframes    |      +-----------+-----------+      +-----------+----------+
+----------+-----------+                  |                              |
           | Frame metadata               | Normalized Events            | Browser Events
           +------------------------------+------------------------------+
                                          v
+-----------------------------------------------------------------------------------+
|                        Durable Persistence & Recovery Layer                       |
|  Journal (idra.storage.journal): Single bounded writer thread                     |
|    Batch -> events.jsonl & frames.jsonl -> flush + os.fsync -> index.sqlite3      |
|  Repository (idra.storage.repository) & Recovery (idra.storage.recovery)          |
+-----------------------------------------+-----------------------------------------+
                                          v
+-----------------------------------------------------------------------------------+
|                      Dataset Preparation & Verification Layer                     |
|  Quality (idra.datasets.quality) -> Trajectories (idra.segmentation.trajectories) |
|  -> Export & Deterministic Splits (idra.datasets.export) -> Re-import Verifier    |
+-----------------------------------------------------------------------------------+
```

### Architectural Verification Summary

A full cross-check of the implementation against `docs/ARCHITECTURE.md` and `docs/SCHEMA.md` confirmed:
- **Strict Component Boundaries**: Capture, input, browser, storage, segmentation, and export modules never import `PyQt6`. All slow GUI operations run on `QThread` workers.
- **Single-Writer Durable Journaling**: `Journal._run` writes canonical JSONL lines, flushes and `os.fsync`s file descriptors, and only then commits `index.sqlite3` in `WAL` mode.
- **Monotonic Timebase Integrity**: `SessionClock` anchors a single monotonic origin (`perf_counter_ns`) and UTC start timestamp; pauses stop capture and event acceptance without mutating historical timestamps.
- **Loop-Owned Browser Calibration**: `Instrumentation.calibrate()` executes only from `ManagedBrowser._run`'s owner loop, avoiding Playwright callback reentrancy deadlocks.

---

## 10. Quality Validation, Trajectory Segmentation & Bug Fixes

### Bugs Identified & Resolved in This Release

1. **Startup Event Ordering & Early Input Retention (`src/idra/app/controller.py`)**:
   - *Issue*: Previously, `SessionController.start()` started `CapturePipeline` and `InputRecorder` before transitioning to `State.RECORDING` and before emitting the initial `state_change` (`RECORDING`) event. As a result, Frame 0 carried an earlier timestamp than the `RECORDING` state change, and early mouse/keyboard callbacks during browser/context startup were silently dropped. Additionally, `self.session_lock` was not reset on the controller instance at the start of a new session.
   - *Fix*: Queued the initial `state_change` (`RECORDING`) event immediately after journal startup, transitioned to `State.RECORDING` as soon as the capture pipeline is ready (before starting input/context hooks), and explicitly reset `self.session_lock = None` on startup initialization.
2. **X11 Fallback Subprocess Pipe Cleanup (`src/idra/capture/sources.py`)**:
   - *Issue*: In `FFmpegX11Source.close()`, if `p.wait(timeout=5)` raised `subprocess.TimeoutExpired`, `p.stdout.close()` was bypassed, leaking the pipe descriptor.
   - *Fix*: Wrapped process termination and `wait()` in a `try...finally` block so `p.stdout.close()` is guaranteed to execute.
3. **Trajectory Stride Closure Binding (`src/idra/segmentation/trajectories.py`)**:
   - *Issue*: The nested `sampled()` helper inside `trajectories()` closed over the loop variable `event` (`Ruff B023`).
   - *Fix*: Bound `target_t_ns=event.t_ns` as an explicit parameter default on `sampled()`.
4. **Recording Studio Monitor Fallback Crash (`src/idra/ui/studio.py`)**:
   - *Issue*: If display detection returned an empty list or the monitor combo box had `None` data, `int(self.monitor.currentData())` in `StudioPage.apply_to()` raised an unhandled `TypeError`.
   - *Fix*: Added safe fallback resolution (`int(monitor_data) if monitor_data is not None else 1`) and preserved the user's selected monitor across display refreshes.
5. **Settings Whitespace Mask Crash & X11 Region Validation (`src/idra/ui/settings_page.py`)**:
   - *Issue*: Clearing the pixel masks editor to whitespace (`"   "`) bypassed `or "[]"` and raised a raw `JSONDecodeError`. Entering fewer or more than four values in the X11 region field raised a raw Python unpack error.
   - *Fix*: Stripped mask text before fallback (`self.masks.toPlainText().strip() or "[]"`), wrapped JSON parsing with a clear validation message, and added explicit four-integer validation for the X11 region field.
6. **Session Explorer Stale Inspector & Recovery State Sync (`src/idra/ui/library.py`, `src/idra/ui/window.py`)**:
   - *Issue*: Deleting the last session or deselecting all sessions returned early in `selection_changed()` without clearing the JSON manifest viewer or frame preview. Completing crash recovery updated the JSON text box but left the session's state column stale in the Session Explorer table and Dashboard. Similarly, a failed recording start did not refresh the session list.
   - *Fix*: Cleared `self.metadata` and `self.preview` whenever selection becomes empty, and triggered background session list refreshes after session recovery and after failed recording startups.
7. **Timeline Keyboard Navigation & Empty-Page Pagination (`src/idra/ui/timeline.py`)**:
   - *Issue*: Timeline event inspection only responded to mouse clicks (`cellClicked`), ignoring keyboard arrow navigation, and clicking `Next` when total events was an exact multiple of 500 stranded the table on an empty page.
   - *Fix*: Connected `currentCellChanged` for seamless keyboard scrubbing and added automatic offset rollback when a forward page contains zero events.
8. **Background Job Progress Bar Contention (`src/idra/ui/window.py`)**:
   - *Issue*: Non-blocking parallel jobs (`Loading sessions`, `Loading session preview`) overwrote the footer status text and progress bar of active blocking operations (`Validating sessions`, `Exporting dataset`).
   - *Fix*: Scoped footer progress updates so active blocking jobs always retain ownership of the status label and progress bar until completion.
9. **Quality HTML Report Line Numbers & Styling (`src/idra/datasets/quality.py`)**:
   - *Issue*: `reports/quality.html` omitted the `line` number field present in `QualityReport.issues` and lacked table styling.
   - *Fix*: Included the `Line` column and clean embedded CSS styling in `reports/quality.html`.
10. **Sandboxed Socket Binding in Browser Test Fixture (`tests/test_browser.py`) & Offline Builder Package Check (`packaging/build_app.py`)**:
    - *Issue*: The `web_page` pytest fixture unconditionally bound a local TCP socket during setup, raising `PermissionError` in restricted environments even for in-memory DOM tests or when Chromium was absent. Additionally, `build_app.py` attempted network `pip install` even when all packages were already installed in the build virtualenv.
    - *Fix*: Made `web_page` gracefully degrade `url=None` on `OSError` (skipping only the live HTTP navigation test when socket binding is disallowed) and updated `install_packages()` in `build_app.py` to reuse pre-installed virtualenv packages without network calls.

---

## 11. Troubleshooting

| Symptom | Resolution |
|---|---|
| `Executable unavailable: ffmpeg` or missing `libx264` | macOS: `brew install ffmpeg` · Windows: `winget install Gyan.FFmpeg` · Linux: install your distribution's `ffmpeg` package, or set the full binary path in **Settings / diagnostics**. |
| macOS: `SCREEN_PERMISSION_REQUIRED` or black video | Open **Settings / diagnostics**, click **Screen Recording...**, enable **IDRA** in System Settings, then quit (`Cmd+Q`) and relaunch IDRA. |
| macOS: `INPUT_PERMISSION_REQUIRED` or `INPUT_LISTENER_START_FAILED` | Grant **Accessibility** and **Input Monitoring** to IDRA in System Settings and relaunch, or uncheck mouse/keyboard capture in **Recording studio**. |
| Linux: `Wayland session detected` | Log out, select the **Xorg** / **on Xorg** session from the login screen gear menu, and log back in. |
| Linux: Qt `xcb` error on startup | Install the XCB cursor library: `sudo apt install libxcb-cursor0` (Fedora: `sudo dnf install xcb-util-cursor`). |
| Managed browser unavailable | Run `python -m playwright install chromium` or configure a local Chromium path in **Settings / diagnostics**. |
| Recording marked `FAILED` or `INTERRUPTED` | Select the session in **Session explorer** to inspect `failure_codes` in `manifest.json`. Use **Recover interrupted** (`idra recover <ID> --confirm`) to salvage interrupted sessions. |

---

## 12. Uninstalling

| Platform | Procedure |
|---|---|
| **macOS** | Drag **IDRA** from `/Applications` to the Trash and remove IDRA from **System Settings > Privacy & Security** lists. |
| **Windows** | Right-click `uninstall-idra.ps1` in `%LOCALAPPDATA%\Programs\IDRA` and select **Run with PowerShell**. |
| **Linux** | Run `~/.local/share/IDRA/uninstall.sh`. |

Uninstalling removes the application while preserving your recordings (`~/IDRA-recordings`) and settings (`~/.idra`). Remove those folders manually if you no longer need them.

---

## 13. Verification Status & Known Limitations

| Verification Area | Status & Evidence |
|---|---|
| **Automated Test Suite (macOS arm64 & Linux x86_64)** | **145 passed, 0 failed, 0 errors**, 10 environment-appropriate skips (Chromium/X11-only tests on macOS; 146 passed on Linux X11). |
| **Modern PyQt6 Studio GUI** | **10/10 GUI tests passed** (`tests/test_gui.py`), verifying all 6 redesigned screens, consent gating, responsive worker threads, cancellation, synthetic recording pause/resume/stop, exception-hook dialogs, storage fallback, and form/selection edge cases. |
| **Static AST & Bytecode Audit** | **51/51 Python modules parsed and compiled cleanly** (`scripts/static_audit.py` -> `passed`, 0 unsafe execution or `shell=True` issues). |
| **macOS Native Application Bundle (`arm64`)** | Built and verified (`dist/IDRA.app` and `dist/IDRA-0.9.2-macos-arm64.dmg`), ad-hoc signed, and smoke-tested end-to-end (`diagnostics`, `demo`, `export`, `verify-export`). |
| **Linux Native Application Bundle (`x86_64`)** | Built and verified via `build-idra-linux.sh`, installed via `install.sh`, and tested with live X11 capture and mouse input. |

### Known Limitations

- Full Wayland screen capture is unsupported on Linux; use an X11 (`Xorg`) desktop session.
- High-DPI and multi-monitor pointer coordinate mapping should be calibrated on the target hardware setup.
- Passing structural and checksum validation confirms data integrity, not downstream machine-learning suitability.
- Fixed pixel masks redact static screen regions; pause recording before opening sensitive content in dynamic windows.

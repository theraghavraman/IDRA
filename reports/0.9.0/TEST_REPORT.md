# IDRA 0.9.0 - Test and build report

Recorded: 2026-10-16T10:20:52.975417+00:00

**Release classification: integrated tested source package; production desktop acceptance NOT achieved.**

## Executed suite

| Result | Count |
|---|---:|
| Passed | 127 |
| Failed | 0 |
| Skipped | 9 |
| Collected | 136 |

Suite elapsed time: 20.06 seconds in this environment. Overall Python statement coverage: **56.88%** (2195 of 3859 statements). Excluding the GUI directory, statement coverage is 78.21% (2189/2799); this does not remove unverified GUI code from the product or certify native hooks. Raw evidence: `pytest.xml`, `pytest-output.txt`, `pytest-report.json`, `coverage.json`.

Skipped cases: six actual GUI tests (missing PyQt6/pytest-qt), one MSS native test (missing package), one Pynput native test (missing package), and one localhost HTTP navigation test (Chromium administrator policy). The five executed browser tests used **real Chromium with in-memory synthetic pages**. No skipped, mocked or unexecuted native behavior is counted as verified hardware functionality.

## Verified behaviors and scope

Actual FFmpeg encoding and ffprobe frame-count inspection; actual OpenCV frame extraction, PNG generation, hashes and deduplication; actual transcode and playback-time clipping; bounded journal ingestion and SQLite persistence; recording pause/resume/stop; missing-dependency and controlled failure handling; actual abrupt subprocess exit and explicit recovery; privacy normalizers and browser value exclusion; deterministic trajectories/splits; deliberate quality defects; metadata-only and reviewed-media exports; independent re-import; path/overwrite protections; canonical-journal/index consistency checks; and CLI workflows.

Native screen capture was exercised by actual FFmpeg x11grab on a **new isolated Xvfb desktop containing only a synthetic labeled window**. This is not macOS or Windows capture verification. Browser DOM tests do not establish successful HTTP navigation or compatibility with arbitrary websites. The global native input hook was not executed.

## Static checks

All 50 application Python modules parsed and compiled. A limited AST audit found no direct eval/exec/os.system/os.popen or literal shell=True calls. The audit scope is recorded in `static-audit.json`. It is not a general security proof.

**Ruff: NOT RUN. mypy: NOT RUN.** Their packages were unavailable. No style-clean/type-clean result is claimed. A complete transitive dependency hash lock, CVE review, license audit, native signing/notarization and multi-platform CI remain outstanding.

## Measured ingestion workload

56,909 synthetic events persisted and read back in 5.014 seconds: **11,350 events/second**, with 0 dropped records. Queue capacity 256, measured queue peak 256. Python tracemalloc peak 1,082,707 bytes; journal size 48,339,320 bytes. The controlled target of 1,000 events/second was met.

This is a five-second synthetic ingestion measurement on the recorded Linux environment, **not** a desktop FPS benchmark, end-to-end native-input latency measurement, memory bound for native codecs, or multi-hour stability certification. See `benchmark.json` for all parameters and limitations.

## Build and installation checks

The project's pure-Python wheel built with the pinned installed setuptools backend using `pip wheel --no-deps --no-build-isolation`. It was installed into a new target directory with `pip install --no-deps --target ...`. Import resolution was checked against that target; the packaged browser JavaScript asset was present. A real synthetic recording/export and export re-import succeeded from the installed wheel while reusing the existing dependency runtime. See `wheel-build.txt`, `wheel-install.txt`, `wheel-demo.txt` and `wheel-verification.json`.

**This is not a fresh dependency installation.** The wheel does not include Qt, Chromium, FFmpeg or other native dependencies, and it is not a standalone executable.

The final source ZIP has a per-file SHA-256 inventory. Exact-archive fresh-extraction verification is published as the separate `IDRA_Clean_Extraction_Report.json` beside the ZIP, avoiding a circular checksum. That companion report records the exact archive hash and outcomes of extracted-source tests, compilation and a synthetic encode/export/re-import workflow. A report for a different ZIP digest is not interchangeable.

## Environment

Python 3.13.5, Linux-6.18.44-x86_64-with-glibc2.41, x86_64. ffmpeg version 7.1.5-0+deb13u1 Copyright (c) 2000-2026 the FFmpeg developers. Chromium 144.0.7559.96 built on Debian GNU/Linux 13 (trixie). Core package versions and missing dependencies are recorded in `environment.json`; honest default diagnostics, including FAIL/UNKNOWN/NOT_RUN, are in `diagnostics.json`.

## Remaining production gates

Run the GUI and native input/capture tests on target machines; validate macOS permissions and Retina/multi-monitor coordinates; verify visible status/global stop; perform a clean full dependency installation; exercise allowed managed-browser HTTP navigation, actual browser crash, multi-hour recording, sleep/wake, display hotplug, true disk exhaustion and native video playback. Review privacy/media handling and dependency redistribution obligations. See `docs/ACCEPTANCE.md` for severity-ranked gaps.

No native executable, universally compatible desktop build, production-readiness certification, or private recording is included.

# Testing strategy and evidence

## What the suite exercises

Unit tests cover schema constraints, aware UTC/elapsed timestamps, privacy normalization, protected keys, URL minimization, pixel masks, state transitions, path validation, private writes, advisory locks, queue bounds and drop counters. No fabricated desktop stream is substituted for a failed native test.

Integration tests use a labeled generated screen source through the real controller, FFmpeg encoder, screenshots, JSONL writer and SQLite indexes. They exercise pause/resume, source/permission/dependency/storage error paths, real process death, tail recovery, deterministic trajectories, quality failure fixtures, safe media processing, export and independent re-import.

Chromium DOM integration runs a real browser with synthetic in-memory pages. It exercises click, input, scroll, sensitive form exclusion, optional label policy, binding rejection, pause, timestamp calibration and controller persistence. A separate real local HTTP navigation test remains in the suite; administrator policy caused that test to skip here. The in-memory tests do not claim to verify HTTP navigation or all arbitrary websites.

Native capture uses a newly allocated Xvfb display with a synthetic labeled window and real FFmpeg x11grab. MSS and Pynput tests also target that isolated display but are skipped when the packages are absent. No test is permitted to use a real person's desktop as its fixture.

Six GUI tests target actual PyQt6 widgets and workers when PyQt6/pytest-qt are present. They cover screen count/navigation, consent, worker responsiveness/cancellation and fixture recording controls. They were not executed in this build. Headless/offscreen GUI tests, when run later, still do not certify native rendering, permissions or multimedia playback.

## Commands

`python -m pytest -q` runs available checks and reports missing prerequisites. For authoritative release evidence, use `python -m pytest -q --junitxml=reports/pytest.xml --cov=idra --cov-report=json:reports/coverage.json --cov-report=term-missing` and retain stdout/stderr. Skipped cases are not passed cases. Coverage measures only executed Python paths; unexecuted GUI/native code reduces total coverage and remains a release risk.

`python scripts/static_audit.py` parses/compiles modules and checks a small explicit set of unsafe execution patterns. It does not perform full linting, typing, dependency vulnerability scanning or prove security. Ruff/mypy were missing and were not run; their separate commands are documented without a false passing result.

## Performance evidence

`python scripts/benchmark.py --events 20000 --minimum-seconds 5` generates a sustained bounded event-journal workload, persists all accepted events, measures elapsed time, queue peak, journal bytes and Python-tracked allocation peak, then verifies row count. The rate target is 1,000 generated events/second on the measured machine; the script reports whether that target was reached, rather than asserting a universal rate across hardware.

See `reports/benchmark.json` for the actual measurement. This workload does not certify 60-FPS full-resolution capture, native hook latency, battery use, GPU buffers or multi-hour operation. Frame-queue capacity and bounded iteration are architectural limits, not benchmark results. Multi-hour desktop soak, disk-volume exhaustion, hotplug, sleep/wake and permissions-changing-mid-session tests remain pending.

## Defect fixtures and examples

`examples/synthetic_dataset` includes real encoded synthetic media, JSONL trajectories, CSV and a checked manifest. `sample-quality.json` is a full-decode quality result for that fixture. `deliberately_defective_fixture/events.jsonl` is intentionally invalid, not a usable dataset. `defective-quality.json` demonstrates duplicate/schema/coordinate/missing-screenshot detection; `scripts/make_examples.py` reproduces the corruption in temporary storage from scratch. Never merge these fixtures into real recordings without preserving `synthetic=true`.

## Release reproducibility

The package script allowlists source/tests/docs/examples/reports and emits per-file SHA-256 inventory. The verifier rejects unsafe ZIP paths/symlinks, checks CRC and inventory, extracts into a fresh directory, runs tests and a real synthetic encode/export/re-import workflow from that directory. It reuses the installed runtime and explicitly labels fresh dependency installation unverified. The report records the exact ZIP digest; changing the ZIP requires rerunning verification.

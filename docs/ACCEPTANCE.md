> **Current release gate:** v0.9.3-rc1 is a source-only candidate; see
> [RELEASE_0.9.3_RC1.md](RELEASE_0.9.3_RC1.md). Older tables below are historical v0.9.2
> evidence and should not be used as acceptance for the current candidate.

# Release gates and outstanding issues

## 0.9.2 status changes

| Acceptance area | 0.9.2 status |
|---|---|
| Linux packaged app | Built from a clean copy with `build-idra-linux.sh`; installed with `install.sh`; real X11 recording with live mouse input COMPLETED, validation 0 errors; GUI launch; uninstall verified |
| Windows packaged app | Builder, installer and Windows code paths written and unit-tested with simulated conditions; NOT EXECUTED on Windows |
| macOS packaged app | Builder written; NOT EXECUTED on macOS |

## 0.9.1 status changes

| Acceptance area | 0.9.1 status |
|---|---|
| Six-screen GUI launches and remains responsive | Verified offscreen and on X11 (xcb); 8 GUI tests, 12 consecutive clean runs |
| Native MSS capture | Verified on isolated X11; macOS/Windows still NOT VERIFIED |
| Native pynput hooks | Verified on isolated X11 with real injected mouse input; macOS still NOT VERIFIED |
| End-to-end GUI recording (start/pause/resume/stop) with real capture | Verified on X11: COMPLETED, full-decode validation 0 errors/0 warnings |
| Frozen application build | Verified with PyInstaller on Linux (GUI launch, demo, export, verify, diagnostics); macOS .app build is produced and smoke-tested by `packaging/macos/build_macos_app.sh` on the target Mac |
| Ruff / mypy | Run. Ruff: no remaining pyflakes/bugbear findings except one reviewed false positive (B023, closure invoked within the iteration); style findings (import order, one-line statements) not reformatted. mypy: findings are typing gaps in untyped code (Optional narrowing, Windows-only ctypes, Qt stubs); none indicated a runtime defect after review |
| macOS permission workflow, Retina/multi-monitor alignment, signed distribution | NOT VERIFIED (requires Mac hardware) |

The 0.9.0 matrix below is retained unchanged for traceability.


**Release classification: tested source package with important unverified desktop capabilities. Production acceptance is NOT achieved.**

The attached engineering specification requires verification of every critical acceptance gate, not just code presence. This matrix intentionally separates implemented code, controlled evidence and unverified behavior. Passing synthetic/core tests does not certify a deployable macOS application.

| Acceptance area | Status in this release |
|---|---|
| Application engine launches with documented source commands | Verified through CLI and synthetic integration |
| Six-screen GUI launches and remains responsive | Implemented; GUI execution NOT VERIFIED |
| Recording state machine and clean finalization | Verified with real media and controlled fixtures |
| Native screen capture produces actual media | Verified for isolated Linux FFmpeg/X11 only |
| MSS screen capture on macOS/Windows | Implemented; NOT VERIFIED |
| Input timestamps/persistence and category privacy | Verified with controlled ingestion/normalizer tests; native Pynput hooks NOT VERIFIED |
| Browser action instrumentation | Verified with real Chromium in-memory DOM; local HTTP navigation NOT VERIFIED |
| FFmpeg/OpenCV media operations | Verified with generated media; nondefault codec support varies by native build |
| Timestamp references and trajectory generation | Verified with fixtures; native compositor/DPI accuracy NOT VERIFIED |
| Exports, split references and re-import | Verified with metadata-only and reviewed-media fixtures |
| Deliberately corrupted quality fixture | Verified; all expected defect categories detected |
| Recovery after abnormal process exit | Verified with real subprocess termination; power-loss hardware behavior NOT VERIFIED |
| Missing dependencies, controlled errors and low-disk reserve | Verified in available paths; native macOS permission denial NOT VERIFIED |
| No automatic recorder uploads | No upload implementation present; limited static review only, not a full network audit |
| Test accounting and source ZIP integrity | See machine-readable reports and exact-archive clean-extraction report |
| Fresh installation from network on target OS | NOT VERIFIED: dependency retrieval unavailable here |
| Multi-hour capture and real storage exhaustion | NOT VERIFIED |
| Ruff/mypy and complete supply-chain review | NOT RUN / incomplete; not falsely marked clean |
| Signed executable distribution | Not supplied |

## Severity-ranked outstanding work

**Release blocker (verification):** Full GUI startup and control integration, macOS permission workflow, native MSS/Pynput capture, Retina/multi-monitor alignment and clean target dependency installation must pass before production use. These are unverified areas, not a claim that the implementations are known to work or known to fail.

**High (reliability/privacy validation):** Confirm continuously visible recording status and global stop behavior on the target desktop; run multi-hour soak, sleep/wake, display hotplug, permissions revocation, actual disk exhaustion and browser crash tests. Inspect actual media for private pixels; fixed masks are not automatic password recognition.

**Medium (engineering hardening):** Run and resolve Ruff/mypy findings; produce platform-specific transitive hash locks and an audited dependency/license inventory. Validate Qt multimedia playback, optional application-context adapters and native packaging. Expand adversarial manifest/index/filesystem corruption coverage and portability tests. Test additional native codecs and operating systems before advertising support.

**Known design limits:** No complete Wayland backend; no observation of arbitrary existing browser windows; no raw text/clipboard/full DOM capture; no cloud uploads; no cryptographic signing of dataset provenance; no general visual-secret detector; no claim that schema-valid data is suitable for training. Exported portable manifests use explicit structural/reference checks rather than their own strict Pydantic model in this version.

## Target sign-off

A release owner should record OS/architecture, Python/native dependency versions, permission approvals, all test results including skips, a harmless manual capture, coordinate calibration, media review, and clean-install evidence. Until then, preserve this package's source-release classification rather than removing the limitations from its documentation.

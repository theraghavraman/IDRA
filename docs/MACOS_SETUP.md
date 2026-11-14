# macOS setup and target-machine verification

**0.9.1:** for the packaged app, follow `DOCUMENTATION.md` and `Build IDRA (macOS).command` (which runs `packaging/build_app.py`). In the app, permissions are granted to **IDRA** itself (Settings / diagnostics has buttons that trigger each macOS prompt). The guidance below applies when running from source, where permissions belong to Terminal or your IDE.

**Status: implementation present; no macOS hardware execution was available for this release.**

## Baseline

The pinned PyQt6/Qt 6.10 line targets macOS 13 or newer. Do not assume this package can run on macOS Catalina 10.15 or another older release. Supporting an older system would require a separately resolved and tested Qt/dependency baseline, not simply ignoring an installer error. Use a supported Python 3.13 interpreter for the closest match to the tested Python version; Apple Silicon and Intel native package resolution both remain to be checked.

Create a new virtual environment and install the requirements as shown in README. Install FFmpeg/ffprobe separately using your trusted package manager or FFmpeg's documented distribution route. Run `ffmpeg -version`, `ffprobe -version` and `python -m idra diagnostics`. Missing `libx264` is a real blocker, not a success warning.

Install Chromium with `python -m playwright install chromium` to use the managed-browser workflow. Existing Safari/Chrome sessions are not instrumented. A system Chromium executable can be explicitly configured, but compatibility must be checked; the Linux tests used a system browser because the Playwright browser download was unavailable.

## Permissions

Screen Recording (or Screen & System Audio Recording, depending on macOS version) must be granted to the actual application launching Python: Terminal, an IDE, or a future packaged app. Accessibility and/or Input Monitoring are required for relevant native hooks. The precise prompting and attribution depends on how Python was launched.

Use System Settings > Privacy & Security and grant only the permissions required for your selected features. Quit and reopen the actual launcher after changing permissions. No code in IDRA bypasses TCC or automatically grants privileges. A diagnostics result of UNKNOWN means the API could not establish status; it does not mean granted.

After granting screen permission, run an explicit consented probe:

```bash
python -m idra diagnostics --probe-screen --consent
```

The probe captures and discards one frame; it does not store a screenshot. The normal diagnostics command does not capture the screen.

## Required local acceptance sequence

Use a dedicated synthetic test account or a harmless local test document, not private work. Keep recording status visible. Select the intended monitor; confirm the preview/frame has expected content and resolution rather than assuming a nonempty buffer proves permission success. Exercise start, pause, resume, stop, then inspect video, events and quality report.

Check pointer/frame alignment at the monitor's four corners, across Retina scaling and any second display. Test keyboard categories, modifier keys and the global stop hook only after expressly enabling keyboard capture. Confirm no typed phrase appears in event journals. A phrase may still be visible in the screen recording unless masked or paused: this is a different privacy channel.

Test managed browser clicks, scrolling, password inputs, navigation, disconnection, permissions denied, missing FFmpeg, low disk reserve, suspend/resume and a forced application exit. Use recovery on the interrupted recording and verify it remains labeled INTERRUPTED. Run GUI tests and manually inspect video playback on the actual Qt multimedia backend.

## Packaging and distribution

This archive contains source, not a signed/notarized macOS app. PyInstaller, signing, hardened runtime, entitlements and notarization are not executed or certified here. Permission identity can change when moving from Terminal to an app bundle. A separately built native application must repeat the permission and lifecycle checks.

## Primary references

- Qt 6.10 supported macOS baseline: https://doc.qt.io/qt-6.10/macos.html
- Apple screen/system audio capture access: https://support.apple.com/guide/mac-help/control-access-screen-system-audio-recording-mchld6aa7d23/mac
- Pynput platform limitations: https://pynput.readthedocs.io/en/latest/limitations.html
- MSS examples: https://python-mss.readthedocs.io/examples.html
- Playwright Python installation: https://playwright.dev/python/docs/intro
- FFmpeg documentation: https://ffmpeg.org/documentation.html

These references describe upstream behavior. They are not evidence that this project's complete macOS integration has been exercised.

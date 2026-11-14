# Diagnostics and troubleshooting

Run `python -m idra diagnostics` before trying capture. A PASS means that named check ran successfully, not that every downstream feature works. UNKNOWN and NOT_RUN are not success. Reports can be saved with `--output diagnostics.json`. Probe capture only with `--probe-screen --consent`.

| Symptom/code | Meaning and action |
|---|---|
| GUI dependencies unavailable | Install pinned full requirements in the active environment. Engine-only commands do not supply Qt. Check macOS version against Qt baseline. |
| Executable unavailable / libx264 unavailable | Install or configure FFmpeg and ffprobe; the FFmpeg build needs libx264. pip alone does not install the native binaries. |
| SCREEN_PERMISSION_REQUIRED | Grant screen capture to the actual launcher in macOS settings and restart it. Permission checks do not bypass consent. |
| INPUT_LISTENER_STOPPED_UNEXPECTEDLY | The native hook stopped. Inspect OS permissions/session support, then repeat a controlled test. Failed capture must not be treated as complete. |
| MSS missing / selected monitor unavailable | Install MSS or reselect an enumerated monitor. Display numbering may change after hotplug. |
| X11_CAPTURE_FAILED | Check local display authorization, configured region, and x11grab support. Full Wayland is unsupported. |
| BROWSER_UNAVAILABLE | Install Playwright Chromium or configure an explicit compatible executable. Normal app launch does not disable sandbox/security policy. |
| Administrator blocks localhost/site | Follow organizational policy. Do not disable policy to make a check green. In this build local navigation was skipped. |
| INSUFFICIENT_STORAGE | Increase available storage or select a private volume; stop reserves are configured in MiB. The application must retain an incomplete/failed manifest on write errors. |
| FRAME/EVENT_INDEX_MISMATCH | A rebuildable SQLite index disagrees with its canonical journal. Preserve a copy, stop the session, then explicitly recover; recovered sessions remain INTERRUPTED. |
| EVENT_JOURNAL / FRAME_JOURNAL | Journal is malformed, partial or missing. Recovery quarantines only an incomplete final line; full bad records remain visible for inspection. |
| FILE_CHECKSUM / SCREENSHOT_CHECKSUM | Bytes differ from the registered checksum. Inspect provenance rather than overwrite expected hashes to hide the failure. |
| FULL_DECODE_NOT_RUN | Normal validation inspects metadata; select full decode/count for a stronger media scan. Even full decode is not a proof of semantic visual quality. |
| TIMING_UNCERTAINTY | Some records use host receive times. Use authoritative frame-index mapping and choose strict timing thresholds when receive timing is unacceptable. |
| Session busy | Another recorder/export/recovery holds the advisory lock. Do not delete the lock file to bypass a live process. Inspect that process and stop it normally. |
| MP4 duration differs from elapsed time | Pauses and dropped observations are not synthesized into the video. Read SCHEMA.md; clipping is in playback time. |

## Recovery commands

```bash
python -m idra --storage ./local-recordings list
python -m idra --storage ./local-recordings recover SESSION_UUID --confirm
python -m idra --storage ./local-recordings validate SESSION_UUID --full-decode
```

Recovery never relabels interrupted work as completed. An interrupted session that has no hard errors may be explicitly exported with `--allow-incomplete`; task completion remains unconfirmed/interrupted. Failed quality checks cannot be bypassed through this option.

## Media commands

```bash
python -m idra --storage ./local-recordings process SESSION_UUID inspect
python -m idra --storage ./local-recordings process SESSION_UUID transcode --out ./derived.mp4 --width 1280
python -m idra --storage ./local-recordings process SESSION_UUID clip --out ./clip.mp4 --start 1 --duration 2
python -m idra --storage ./local-recordings process SESSION_UUID extract --out ./extracted --every-n 5 --deduplicate
```

Use new output paths. Cancelled FFmpeg output is removed; cancelled frame extraction intentionally retains a marked partial directory and manifest. Some inspections/copy checks are non-interruptible until their current bounded operation ends. Stalled processing is stopped by a watchdog, not reported as successful completion.

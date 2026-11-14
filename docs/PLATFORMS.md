# Platform and dependency boundaries

| Area | Delivered implementation | Evidence in this build |
|---|---|---|
| Core Python services | Python 3.11-3.14 declared | Executed on Python 3.13.5 / Linux x86_64 only |
| Desktop GUI | Six PyQt6 screens, Qt workers and multimedia timeline | Compiled; GUI tests skipped because dependencies are absent |
| macOS capture | MSS monitor capture; CoreGraphics permission preflight | No macOS hardware or native package test |
| Windows capture | MSS monitor capture | No Windows execution or DPI calibration |
| Linux capture | MSS and explicit FFmpeg/X11 region | FFmpeg/X11 captured an isolated Xvfb test desktop; MSS unavailable |
| Wayland | No full capture/input backend | Explicitly unsupported; XWayland is not claimed to cover all apps |
| Input hooks | Pynput mouse/keyboard category hooks | Normalizer/lifecycle logic tested; native hooks skipped |
| Browser DOM events | Managed Chromium, binding and init script | Real in-memory Chromium tests passed |
| Browser HTTP navigation | Start/load/failure event handling | Local HTTP test blocked by administrator policy and skipped |
| Media | FFmpeg libx264, ffprobe, OpenCV | Real encode, inspect, transcode, clip, extract, hash and corruption checks |
| Packaging | Source ZIP, package build configuration, inventory verifier | See raw build and clean-extraction reports |

## Dependency choices

The recorded test environment uses Pydantic 2.13.5, NumPy 2.3.5, OpenCV 4.13.0.92, Playwright 1.57.0 and FFmpeg/ffprobe 7.1.5. The preinstalled environment contains both OpenCV GUI and headless distributions; a clean target environment should install only the declared headless package because Qt is provided separately through PyQt6. Dependency diagnostics reports package presence/version, not full compatibility.

PyQt6 6.10.0, Qt 6.10.0, MSS 10.1.0 and Pynput 1.8.1 are declared pins but were not installed or runtime-verified in this container. Exact native wheel availability, transitive dependencies and signing requirements must be validated on each target architecture. Python 3.11/3.12/3.14 are not represented by executed test runs.

FFmpeg is deliberately an external executable: builds differ by platform and enabled codecs. `libx264` is required for canonical recording. Native system frameworks and permissions are not Python dependencies. No universal native binary is promised.

## Windows

Use a new PowerShell virtual environment, put FFmpeg/ffprobe on PATH, and configure the desired monitor. Native input hooks and MSS can use different coordinate conventions on scaled/multi-monitor desktops; inspect calibration before using coordinates as labels. Windows filesystem permission/locking behavior is not claimed equivalent to POSIX mode bits. Long paths and non-ASCII paths need target-machine checks. Unicode filenames are handled through Python Path/argument lists, not shell commands.

## Linux

The explicit fallback uses a local X11 display string such as `:0` and configured region; choose the display only with consent. Tests allocate a new display around `:190` and render a labeled xmessage window there. They never capture an existing DISPLAY. Local X authority, display permissions and FFmpeg x11grab support are prerequisites. Headless core processing and synthetic demonstrations need no desktop server.

Qt's platform plugin and multimedia codec availability depend on the target distribution. Offscreen GUI unit tests are not a substitute for native display/playback verification. Multi-hour capture, actual disk exhaustion, suspend/resume, display hotplug, elevated Windows input and macOS permission changes remain release gates.
